#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
内隐联想测验（IAT）中文版 · 配置驱动实现

用法：
    python run.py --check-only          只校验配置、打印试次分配，不弹窗口
    python run.py --id T001             正式施测（编号必填，或启动后弹框填）
    python run.py --id T001 --seed 42   固定试次随机顺序，便于复现

设计原则：
    1. 实验内容全部来自 config.yaml，代码里不出现任何具体词语
    2. 配置有问题就在启动时停下并说明原因，不带着错误跑完 200 试次
    3. 检查模式不依赖 PsychoPy，可以在没装图形库的机器上做配置校验
"""

import argparse
import csv
import datetime as _dt
import json
import os
import random
import re
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 试次类型：1/2 为两个概念，3/4 为两个属性
T_CONCEPT_1, T_CONCEPT_2, T_ATTR_1, T_ATTR_2 = 1, 2, 3, 4
TYPE_NAMES = {T_CONCEPT_1: 'concept_1', T_CONCEPT_2: 'concept_2',
              T_ATTR_1: 'attribute_1', T_ATTR_2: 'attribute_2'}

SIDES = ('left', 'right')

# 中文字体候选（按优先级）
CJK_FONTS_WIN = [('Microsoft YaHei', ('msyh.ttc', 'msyhbd.ttc')),
                 ('SimHei', ('simhei.ttf',))]
CJK_FONTS_MAC = [('PingFang SC', '/System/Library/Fonts/PingFang.ttc'),
                 ('Hiragino Sans GB', '/System/Library/Fonts/Hiragino Sans GB.ttc')]


# ---------------------------------------------------------------------------
# 区块布局
#   plan : [(试次类型, 该类型试次数), ...]
#   phase: first = 概念处于初始侧；second = 概念左右互换侧
#   score: 是否进入 D 分数计算
# ---------------------------------------------------------------------------
LAYOUTS = {
    'nosek7': [
        dict(no=1, kind='concept', phase='first', instr='b1', score=False,
             plan=[(T_CONCEPT_1, 10), (T_CONCEPT_2, 10)]),
        dict(no=2, kind='attribute', phase='first', instr='b2', score=False,
             plan=[(T_ATTR_1, 10), (T_ATTR_2, 10)]),
        dict(no=3, kind='combined', phase='first', instr='b3', score=True,
             plan=[(T_CONCEPT_1, 5), (T_CONCEPT_2, 5), (T_ATTR_1, 5), (T_ATTR_2, 5)]),
        dict(no=4, kind='combined', phase='first', instr='b4', score=True,
             plan=[(T_CONCEPT_1, 10), (T_CONCEPT_2, 10), (T_ATTR_1, 10), (T_ATTR_2, 10)]),
        dict(no=5, kind='concept', phase='second', instr='b5', score=False,
             plan=[(T_CONCEPT_1, 20), (T_CONCEPT_2, 20)]),
        dict(no=6, kind='combined', phase='second', instr='b6', score=True,
             plan=[(T_CONCEPT_1, 5), (T_CONCEPT_2, 5), (T_ATTR_1, 5), (T_ATTR_2, 5)]),
        dict(no=7, kind='combined', phase='second', instr='b7', score=True,
             plan=[(T_CONCEPT_1, 10), (T_CONCEPT_2, 10), (T_ATTR_1, 10), (T_ATTR_2, 10)]),
    ],
    'greenwald5': [
        dict(no=1, kind='attribute', phase='first', instr='b2', score=False,
             plan=[(T_ATTR_1, 10), (T_ATTR_2, 10)]),
        dict(no=2, kind='concept', phase='first', instr='b1', score=False,
             plan=[(T_CONCEPT_1, 10), (T_CONCEPT_2, 10)]),
        dict(no=3, kind='combined', phase='first', instr='b3', score=True,
             plan=[(T_CONCEPT_1, 5), (T_CONCEPT_2, 5), (T_ATTR_1, 5), (T_ATTR_2, 5)]),
        dict(no=4, kind='concept', phase='second', instr='b5', score=False,
             plan=[(T_CONCEPT_1, 20), (T_CONCEPT_2, 20)]),
        dict(no=5, kind='combined', phase='second', instr='b7', score=True,
             plan=[(T_CONCEPT_1, 10), (T_CONCEPT_2, 10), (T_ATTR_1, 10), (T_ATTR_2, 10)]),
    ],
}


# ---------------------------------------------------------------------------
# 配置读取与校验
# ---------------------------------------------------------------------------
def load_config(path):
    try:
        import yaml
    except ImportError:
        sys.exit("缺少 PyYAML。请先运行：\n    python -m pip install pyyaml")
    if not os.path.exists(path):
        sys.exit("找不到配置文件：%s" % path)
    with open(path, 'r', encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
    if not isinstance(cfg, dict):
        sys.exit("配置文件格式错误：顶层应当是一个映射（key: value）。")
    return cfg


def _flip(side):
    return 'left' if side == 'right' else 'right'


def validate(cfg):
    """返回错误列表；空列表表示配置可用。"""
    errs = []

    exp = cfg.get('experiment') or {}
    layout = exp.get('layout', 'nosek7')
    if layout not in LAYOUTS:
        errs.append("experiment.layout 只能是 %s，当前为 %r"
                    % (' / '.join(LAYOUTS), layout))

    keys = cfg.get('keys') or {}
    kl, kr = keys.get('left'), keys.get('right')
    if not kl or not kr:
        errs.append("keys.left 与 keys.right 都必须填写")
    elif str(kl).lower() == str(kr).lower():
        errs.append("keys.left 与 keys.right 不能是同一个键（当前都是 %r）" % kl)
    elif len(str(kl)) != 1 or len(str(kr)) != 1:
        errs.append("keys.left / keys.right 必须是单个字符（如 e、i、f、j）")

    concepts = cfg.get('concepts') or []
    attributes = cfg.get('attributes') or []
    if len(concepts) != 2:
        errs.append("concepts 必须正好是 2 个概念词，当前是 %d 个" % len(concepts))
    if len(attributes) != 2:
        errs.append("attributes 必须正好是 2 个属性词，当前是 %d 个" % len(attributes))
    if errs:
        return errs

    for group_name, group in (('concepts', concepts), ('attributes', attributes)):
        for i, item in enumerate(group):
            tag = "%s[%d]" % (group_name, i)
            if not item.get('name'):
                errs.append("%s 缺少 name" % tag)
            if item.get('side') not in SIDES:
                errs.append("%s.side 必须是 left 或 right，当前为 %r" % (tag, item.get('side')))
            ex = item.get('exemplars') or []
            if not ex:
                errs.append("%s.exemplars 不能为空" % tag)
            elif len(set(map(str, ex))) != len(ex):
                errs.append("%s.exemplars 有重复词语" % tag)
            elif any(str(w).strip() == '' for w in ex):
                errs.append("%s.exemplars 里存在空字符串" % tag)

    if errs:
        return errs

    if concepts[0]['side'] == concepts[1]['side']:
        errs.append("两个概念词必须在不同侧（现在都在 %s 侧）" % concepts[0]['side'])
    if attributes[0]['side'] == attributes[1]['side']:
        errs.append("两个属性词必须在不同侧（现在都在 %s 侧）" % attributes[0]['side'])

    # 每个概念的侧必须与某个属性相同，否则不存在相容配对
    attr_sides = {a['side'] for a in attributes}
    for c in concepts:
        if c['side'] not in attr_sides:
            errs.append(
                "概念「%s」在 %s 侧，但两个属性分别在 left / right …… 没有属性与它同侧。"
                "请检查 concepts 与 attributes 的 side 设置。" % (c['name'], c['side']))

    instr = cfg.get('instructions') or {}
    need = ['consent', 'thanks'] + [b['instr'] for b in LAYOUTS[layout]]
    for key in need:
        if not instr.get(key):
            errs.append("instructions.%s 缺失或为空" % key)

    return errs


# ---------------------------------------------------------------------------
# 被试编号
# ---------------------------------------------------------------------------
class BadCode(Exception):
    pass


def parse_code(code):
    """T+数字 = 正顺序（概念按配置侧），F+数字 = 反顺序（概念左右互换）。"""
    code = (code or '').strip()
    m = re.fullmatch(r'([TtFf])\s*[-_]?\s*(\d+)', code)
    if not m:
        raise BadCode(
            "被试编号格式不对：%r\n"
            "正确写法是 T 或 F 开头，后面跟数字，例如 T001、F12、F003。\n"
            "  T = 正顺序（概念按配置的左右侧）\n"
            "  F = 反顺序（概念左右互换，用于平衡配对顺序）" % code)
    order = m.group(1).upper()
    return order, '%s%s' % (order, m.group(2))


# ---------------------------------------------------------------------------
# 试次构建
# ---------------------------------------------------------------------------
def _concept_sides(cfg, order, phase):
    """返回 {试次类型: 该区块内所处的侧}。"""
    first = cfg['concepts'][0]['side'] if order == 'T' else _flip(cfg['concepts'][0]['side'])
    side_c1 = first if phase == 'first' else _flip(first)
    return {T_CONCEPT_1: side_c1, T_CONCEPT_2: _flip(side_c1)}


def _attr_sides(cfg):
    return {T_ATTR_1: cfg['attributes'][0]['side'],
            T_ATTR_2: cfg['attributes'][1]['side']}


def _side_of(ttype, c_sides, a_sides):
    return c_sides[ttype] if ttype in c_sides else a_sides[ttype]


def _exemplars_of(cfg, ttype):
    if ttype == T_CONCEPT_1:
        return [str(w) for w in cfg['concepts'][0]['exemplars']]
    if ttype == T_CONCEPT_2:
        return [str(w) for w in cfg['concepts'][1]['exemplars']]
    if ttype == T_ATTR_1:
        return [str(w) for w in cfg['attributes'][0]['exemplars']]
    return [str(w) for w in cfg['attributes'][1]['exemplars']]


def _name_of(cfg, ttype):
    if ttype == T_CONCEPT_1:
        return cfg['concepts'][0]['name']
    if ttype == T_CONCEPT_2:
        return cfg['concepts'][1]['name']
    if ttype == T_ATTR_1:
        return cfg['attributes'][0]['name']
    return cfg['attributes'][1]['name']


def _make_pool(words, n, rng):
    """取 n 个刺激并尽量使每个词出现次数相差不超过 1。"""
    pool = []
    while len(pool) < n:
        batch = list(words)
        rng.shuffle(batch)
        pool.extend(batch)
    return pool[:n]


def build_blocks(cfg, order, rng):
    """按布局生成每个区块及其完整试次列表。"""
    layout = cfg['experiment'].get('layout', 'nosek7')
    a_sides = _attr_sides(cfg)
    blocks = []

    for spec in LAYOUTS[layout]:
        c_sides = _concept_sides(cfg, order, spec['phase'])
        sides = {}
        sides.update(c_sides)
        sides.update(a_sides)

        trials = []
        for ttype, n in spec['plan']:
            for word in _make_pool(_exemplars_of(cfg, ttype), n, rng):
                trials.append(dict(type=ttype, word=word, side=sides[ttype]))
        rng.shuffle(trials)

        # 配对属性：概念之间的相容关系由"概念1 与 属性1 是否同侧"决定
        if spec['kind'] == 'combined':
            pairing = 'compatible' if c_sides[T_CONCEPT_1] == a_sides[T_ATTR_1] else 'incompatible'
        else:
            pairing = ''

        blocks.append(dict(
            no=spec['no'], kind=spec['kind'], instr=spec['instr'],
            score=spec['score'], pairing=pairing,
            c_sides=c_sides, a_sides=a_sides, sides=sides,
            trials=trials, n_trials=len(trials),
        ))
    return blocks


def block_labels(cfg, block):
    """返回左右两侧的标签，概念与属性分开给，绘制时分别放在上下两行。"""
    out = {'concept_left': [], 'concept_right': [], 'attr_left': [], 'attr_right': []}
    if block['kind'] in ('concept', 'combined'):
        for ttype in (T_CONCEPT_1, T_CONCEPT_2):
            k = 'concept_left' if block['c_sides'][ttype] == 'left' else 'concept_right'
            out[k].append(_name_of(cfg, ttype))
    if block['kind'] in ('attribute', 'combined'):
        for ttype in (T_ATTR_1, T_ATTR_2):
            k = 'attr_left' if block['a_sides'][ttype] == 'left' else 'attr_right'
            out[k].append(_name_of(cfg, ttype))
    return out


def block_label_text(lab):
    """把标签拼成指导语里用的字符串。"""
    left = lab['concept_left'] + lab['attr_left']
    right = lab['concept_right'] + lab['attr_right']
    return " 或 ".join(left), " 或 ".join(right)


# ---------------------------------------------------------------------------
# 检查模式（不依赖 PsychoPy）
# ---------------------------------------------------------------------------
def run_check(cfg, order):
    keys = cfg['keys']
    blocks = build_blocks(cfg, order, random.Random(0))

    print("=" * 78)
    print("IAT 配置自检 · 布局 %s · 被试顺序 %s（%s）"
          % (cfg['experiment'].get('layout'), order,
             '正顺序：概念按配置侧' if order == 'T' else '反顺序：概念左右互换'))
    print("=" * 78)
    print("按键：左 = %s    右 = %s" % (keys['left'], keys['right']))
    print("概念：%s" % "，".join("%s(%s)" % (c['name'], c['side']) for c in cfg['concepts']))
    print("属性：%s" % "，".join("%s(%s)" % (a['name'], a['side']) for a in cfg['attributes']))
    print()

    header = "%-3s %-10s %-6s %-8s %-28s %s" % ("块", "类型", "试次", "配对", "左侧 / 右侧", "参与计分")
    print(header)
    print("-" * 78)
    total = 0
    for b in blocks:
        lstr, rstr = block_label_text(block_labels(cfg, b))
        print("%-3d %-10s %-6d %-8s %-28s %s" % (
            b['no'], b['kind'], b['n_trials'], b['pairing'] or '-',
            "%s  |  %s" % (lstr, rstr), "是" if b['score'] else "否"))
        total += b['n_trials']
    print("-" * 78)
    print("合计 %d 试次，预计用时约 %.1f 分钟" % (total, total * 1.5 / 60))
    print()

    print("刺激平衡性检查（每个区块内各词的呈现次数）")
    ok = True
    for b in blocks:
        counts = {}
        for t in b['trials']:
            counts[t['word']] = counts.get(t['word'], 0) + 1
        per_type = {}
        for t in b['trials']:
            per_type.setdefault(t['type'], []).append(counts[t['word']])
        for ttype, lst in per_type.items():
            if max(lst) - min(lst) > 1:
                ok = False
                print("  ✗ 区块 %d 类型 %s 分布不均：%s"
                      % (b['no'], TYPE_NAMES[ttype], sorted(lst)))
    if ok:
        print("  ✓ 所有区块内各刺激呈现次数相差不超过 1")

    print()
    print("计分区块配对：")
    for b in blocks:
        if b['score']:
            print("  区块 %d：%s，%d 试次" % (b['no'], b['pairing'], b['n_trials']))
    print()
    print("自检通过。可以加 --id 参数正式施测。")
    return 0


# ---------------------------------------------------------------------------
# 正式施测（需要 PsychoPy）
# ---------------------------------------------------------------------------
def pick_cjk_font(preferred):
    if preferred and str(preferred).lower() != 'auto':
        return str(preferred)
    if sys.platform.startswith('win'):
        root = os.path.join(os.environ.get('WINDIR', r'C:\Windows'), 'Fonts')
        for name, files in CJK_FONTS_WIN:
            if any(os.path.exists(os.path.join(root, f)) for f in files):
                return name
        return 'Microsoft YaHei'
    if sys.platform == 'darwin':
        for name, path in CJK_FONTS_MAC:
            if os.path.exists(path):
                return name
        return 'PingFang SC'
    return 'Noto Sans CJK SC'


def run_experiment(cfg, code, order, seed):
    try:
        from psychopy import core, event, gui, visual
    except ImportError:
        sys.exit("没有找到 PsychoPy。\n"
                 "请用 PsychoPy 官方独立版运行本脚本，或执行：\n"
                 "    python -m pip install psychopy")

    exp = cfg['experiment']
    win_cfg = cfg.get('window') or {}
    keys = cfg['keys']
    kl, kr = str(keys['left']).lower(), str(keys['right']).lower()
    timing = cfg.get('timing') or {}
    stim_delay = float(timing.get('stim_delay', 0.3))
    rt_timeout = float(timing.get('rt_timeout', 0) or 0)
    font = pick_cjk_font(exp.get('font', 'auto'))
    instr = cfg['instructions']

    rng = random.Random(seed)
    blocks = build_blocks(cfg, order, rng)

    win = visual.Window(
        size=tuple(win_cfg.get('size', [1366, 768])),
        fullscr=bool(win_cfg.get('fullscreen', True)),
        color=win_cfg.get('background', 'black'),
        colorSpace='rgb', units='norm', allowGUI=False, screen=0)
    win.mouseVisible = False

    def text(msg, height=0.05, color='white', pos=(0, 0), wrap=1.6):
        return visual.TextStim(win, text=msg, font=font, pos=pos, height=height,
                               color=color, wrapWidth=wrap, units='norm',
                               colorSpace='rgb')

    def wait_keys(accepted, label):
        event.clearEvents()
        while True:
            pressed = event.getKeys(keyList=list(accepted) + ['escape'])
            if 'escape' in pressed:
                raise SystemExit("被试中止（Esc）")
            if pressed:
                return pressed[0]
            win.flip()

    data_dir = os.path.join(BASE_DIR, 'data')
    os.makedirs(data_dir, exist_ok=True)
    stamp = _dt.datetime.now()
    stem = os.path.join(data_dir, "%s_%s" % (code, stamp.strftime('%Y%m%d_%H%M%S')))

    with open(stem + '.json', 'w', encoding='utf-8') as f:
        json.dump(dict(participant=code, order=order, config=cfg,
                       started=stamp.isoformat(), seed=seed),
                  f, ensure_ascii=False, indent=2)

    fields = ['participant', 'order', 'layout', 'block', 'block_kind', 'pairing',
              'block_trials', 'trial_in_block', 'trial_type', 'stimulus',
              'stim_side', 'correct_key', 'first_key', 'first_key_correct',
              'rt_first', 'rt_correct', 'n_errors', 'timestamp']
    fh = open(stem + '.csv', 'w', encoding='utf-8-sig', newline='')
    writer = csv.DictWriter(fh, fieldnames=fields)
    writer.writeheader()
    fh.flush()

    # ---------------- 知情同意 ----------------
    try:
        text(instr['consent'], height=0.042).draw()
        win.flip()
        wait_keys(('space',), 'consent')

        for block in blocks:
            lab = block_labels(cfg, block)
            ltxt, rtxt = block_label_text(lab)
            body = instr[block['instr']].format(L=ltxt, R=rtxt,
                                                KEY_L=kl.upper(), KEY_R=kr.upper())

            instr_stim = text(body, height=0.042)
            instr_stim.draw()
            win.flip()
            wait_keys((kl, kr), 'instruction')

            GREEN = [0, 1, 0]
            combined = (block['kind'] == 'combined')
            # 概念标签（白）：单独出现时居上；联合区块时占上方一行
            cl_y = 0.85
            # 属性标签（绿）：单独出现时也居上，便于阅读；联合区块时占下方一行
            at_y = 0.55 if combined else 0.85

            side_labels = []
            if block['kind'] in ('concept', 'combined'):
                side_labels += [text(n, height=0.085, pos=(-0.6, cl_y)) for n in lab['concept_left']]
                side_labels += [text(n, height=0.085, pos=(0.6, cl_y)) for n in lab['concept_right']]
            if block['kind'] in ('attribute', 'combined'):
                side_labels += [text(n, height=0.085, color=GREEN, pos=(-0.6, at_y)) for n in lab['attr_left']]
                side_labels += [text(n, height=0.085, color=GREEN, pos=(0.6, at_y)) for n in lab['attr_right']]
            if combined:
                side_labels.append(text("或", height=0.07, color=GREEN, pos=(-0.6, 0.70)))
                side_labels.append(text("或", height=0.07, color=GREEN, pos=(0.6, 0.70)))

            stim = text("", height=0.13)
            mark = text("X", height=0.2, color=[1, 0.2, 0.2], pos=(0, -0.45))

            # ---------------- 逐试次 ----------------
            for i, trial in enumerate(block['trials'], start=1):
                stim.text = trial['word']
                correct_key = kl if trial['side'] == 'left' else kr

                for s in side_labels:
                    s.setAutoDraw(True)
                stim.setAutoDraw(False)
                mark.setAutoDraw(False)
                win.flip()

                # t=0 约等于标签出现的那一帧
                clock = core.Clock()
                event.clearEvents()

                # 刺激"真正"出现于屏幕的时刻。不用标称的 stim_delay——那会带来
                # 系统偏差；也不用翻转回调——回调在 flip 返回后才执行，会偏晚。
                # win.flip() 返回 glFinish 记录的真实翻转时刻，但它与 core.getTime()
                # 同一基准，而 Clock 的基准是绝对单调时钟，必须换算后再相减。
                onset = {'t': None}
                try:
                    _to_clock = (core.monotonicClock.getLastResetTime()
                                 - clock.getLastResetTime())
                    _use_flip_time = True
                except Exception:
                    _to_clock = 0.0
                    _use_flip_time = False

                first_key = None
                rt_first = None
                rt_correct = None
                n_err = 0
                mark_on = False
                done = False

                while not done:
                    # 1) 先取按键。timeStamped 用的是事件时间，不是轮询时刻
                    for item in event.getKeys(keyList=[kl, kr, 'escape'],
                                              timeStamped=clock):
                        if isinstance(item, str):
                            k, kt = item, clock.getTime()
                        else:
                            k, kt = item[0], item[-1]
                        if k == 'escape':
                            raise SystemExit("被试中止（Esc）")
                        if onset['t'] is None or kt < onset['t']:
                            continue  # 刺激出现之前的按键不予采信
                        rt = kt - onset['t']
                        if first_key is None:
                            first_key = k
                            rt_first = rt
                        if k == correct_key:
                            rt_correct = rt
                            done = True
                            break  # 本帧后续按键不再计入错误
                        n_err += 1
                        mark_on = True
                    if done:
                        break

                    # 2) 刺激还没出现：只推进帧，并记录这一帧的真实显示时刻
                    if onset['t'] is None:
                        if clock.getTime() >= stim_delay:
                            stim.setAutoDraw(True)
                            t_abs = win.flip()
                            if _use_flip_time and t_abs is not None:
                                onset['t'] = t_abs + _to_clock
                            else:
                                onset['t'] = clock.getTime()
                        else:
                            win.flip()
                        continue

                    # 3) 刺激已出现：显示红 X、检查超时
                    if mark_on:
                        mark.setAutoDraw(True)
                    if rt_timeout > 0 and (clock.getTime() - onset['t']) > rt_timeout:
                        done = True
                        break
                    win.flip()

                for s in side_labels:
                    s.setAutoDraw(False)
                stim.setAutoDraw(False)
                mark.setAutoDraw(False)
                win.flip()

                writer.writerow(dict(
                    participant=code, order=order, layout=exp.get('layout', 'nosek7'),
                    block=block['no'], block_kind=block['kind'], pairing=block['pairing'],
                    block_trials=block['n_trials'], trial_in_block=i,
                    trial_type=TYPE_NAMES[trial['type']], stimulus=trial['word'],
                    stim_side=trial['side'], correct_key=correct_key,
                    first_key=first_key or '',
                    first_key_correct=int(first_key == correct_key) if first_key else 0,
                    rt_first='%.4f' % rt_first if rt_first is not None else '',
                    rt_correct='%.4f' % rt_correct if rt_correct is not None else '',
                    n_errors=n_err,
                    timestamp=_dt.datetime.now().isoformat(timespec='seconds')))
                fh.flush()
    except SystemExit:
        fh.close()
        win.close()
        print("被试中止（Esc）。已完成的试次已保存：%s.csv" % stem)
        raise
    finally:
        if not fh.closed:
            fh.close()

    # ---------------- 致谢 ----------------
    text(instr['thanks'], height=0.06).draw()
    win.flip()
    core.wait(3)
    event.clearEvents()
    wait_keys((kl, kr, 'space', 'return'), 'thanks')
    win.close()

    print("数据已保存：%s.csv" % stem)
    return 0


# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description='IAT 中文版')
    ap.add_argument('--config', default=os.path.join(BASE_DIR, 'config.yaml'))
    ap.add_argument('--id', dest='code', help='被试编号，T+数字 或 F+数字')
    ap.add_argument('--check-only', action='store_true', help='只校验配置，不弹窗口')
    ap.add_argument('--seed', type=int, default=None, help='随机种子（复现试次顺序）')
    args = ap.parse_args()

    cfg = load_config(args.config)
    errs = validate(cfg)
    if errs:
        print("配置有 %d 处问题，已停止：\n" % len(errs))
        for i, e in enumerate(errs, 1):
            print("  %d) %s" % (i, e))
        print()
        return 1

    if args.check_only:
        code = args.code or 'T001'
        try:
            order, _ = parse_code(code)
        except BadCode as e:
            print(e)
            return 1
        return run_check(cfg, order)

    code = args.code
    if not code:
        try:
            from psychopy import gui
        except ImportError:
            sys.exit("没有找到 PsychoPy，无法弹出输入框。\n"
                     "请用 --id 参数指定编号，例如：python run.py --id T001")
        for attempt in range(3):
            dlg = gui.Dlg(title='IAT 被试信息')
            dlg.addField('被试编号（T+数字=正顺序，F+数字=反顺序）:', '')
            dlg.addField('主试姓名（可留空）:', '')
            res = dlg.show()
            if not dlg.OK:
                sys.exit("已取消。")
            try:
                order, code = parse_code(res[0])
                break
            except BadCode as e:
                errdlg = gui.Dlg(title='编号格式错误')
                errdlg.addText(str(e).replace('\n', ' '))
                errdlg.show()
                print(e)
                if attempt == 2:
                    sys.exit("编号连续 3 次不正确，已退出。")
    else:
        try:
            order, code = parse_code(code)
        except BadCode as e:
            print(e)
            return 1

    return run_experiment(cfg, code, order, args.seed)


if __name__ == '__main__':
    sys.exit(main())
