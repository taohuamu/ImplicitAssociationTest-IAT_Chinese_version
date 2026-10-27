# -*- coding: utf-8 -*-
"""
IAT 计分 —— 严格按 Greenwald, Nosek & Banaji (2003) 的改进算法（Table 4）。

Table 4 的 12 步对应到本文件：

  1. 只用区块 3、4、6、7                        -> combined
  2. 剔除反应时 > 10000ms 的试次；               -> rt_max
     剔除「>10% 试次快于 300ms」的被试           -> fast_rt / fast_pct_limit
  3. 保留区块内全部试次（不丢前两个）              -> 无操作
  4. 默认不做极端值处理                           -> delete_below_400 可开
  5. 逐区块算「正确试次」的均值与标准差            -> block_mean / block_sd
  6. 3&6 一个合并 SD、4&7 一个合并 SD，
     且只用正确试次计算                           -> pair_sd
  7. 错误试次替换：
       强制改正 -> 直接用改对后的反应时（原文允许的替代做法）
       不改正   -> 该区块正确均值 + 600ms
                                                 -> scoring_rt()
  8. 不做变换                                     -> 无操作
  9. 各区块取均值                                 -> block_mean_scoring
 10. 两个差值（6-3、7-4）                         -> d_pair
 11. 各自除以第 6 步的 SD                         -> d_pair
 12. 两个商取平均                                 -> D

用法：
    python score.py                 # 扫 data/ 目录
    python score.py 某文件.csv
    python score.py --error-rate-exclude 0.2 --delete-below-400
"""
import argparse
import csv
import glob
import math
import os
import statistics as st
import sys

import yaml

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 默认参数，对应 Greenwald et al. (2003) Table 4 的"改进算法"一列
DEFAULTS = {
    'rt_max': 10000.0,          # 剔除慢于该值的试次
    'fast_rt': 300.0,           # 「快速试次」阈值
    'fast_pct_limit': 0.10,     # 快速试次比例超过此值则剔除被试
    'error_rate_exclude': None,  # None = 不按错误率剔除（2003 改进算法没有这条）
    'delete_below_400': False,  # 对应 D2/D6 变体：删除 <400ms 的试次
    'error_penalty': 600.0,     # 错误试次惩罚（advance 模式用）
}

REQUIRED_COLS = {'participant', 'order', 'layout', 'block', 'block_kind',
                 'pairing', 'block_trials', 'trial_in_block', 'trial_type',
                 'stimulus', 'correct_key', 'first_key', 'first_key_correct',
                 'rt_correct', 'n_errors'}


def _f(x):
    """安全转 float，空值返回 None。"""
    if x is None:
        return None
    s = str(x).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _rt_ms(x):
    """CSV 里存的是秒，转成毫秒。"""
    v = _f(x)
    return None if v is None else v * 1000.0


def load_rows(paths):
    rows = []
    for p in paths:
        with open(p, encoding='utf-8-sig', newline='') as f:
            rows.extend(list(csv.DictReader(f)))
    return rows


def load_options(args):
    """优先级：命令行 > config.yaml 的 scoring 段 > DEFAULTS。"""
    opt = dict(DEFAULTS)
    cfg_path = os.path.join(BASE_DIR, 'config.yaml')
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, encoding='utf-8-sig') as f:
                cfg = yaml.safe_load(f) or {}
            sc = cfg.get('scoring') or {}
            for k in opt:
                if k in sc and sc[k] is not None:
                    opt[k] = sc[k]
        except Exception as e:
            print('读取 config.yaml 的 scoring 段失败，使用默认值：%s' % e)

    if getattr(args, 'error_rate_exclude', None) is not None:
        opt['error_rate_exclude'] = args.error_rate_exclude
    if getattr(args, 'delete_below_400', False):
        opt['delete_below_400'] = True
    if getattr(args, 'penalty', None) is not None:
        opt['error_penalty'] = args.penalty
    return opt


def score_participant(pid, rows, opt):
    rt_max = float(opt['rt_max'])
    fast_rt = float(opt['fast_rt'])
    fast_limit = float(opt['fast_pct_limit'])
    penalty = float(opt['error_penalty'])
    drop_fast_400 = bool(opt['delete_below_400'])

    combined = [r for r in rows if r.get('pairing') in ('compatible', 'incompatible')]
    order = rows[0].get('order', '') if rows else ''
    layout = rows[0].get('layout', '') if rows else ''

    # ---- 第 2 步：剔除 > 10000ms；统计快速试次比例 ----
    n_total = len(combined)
    n_correct = sum(1 for r in combined if str(r.get('first_key_correct')) == '1')
    acc = (n_correct / n_total) if n_total else float('nan')

    ok_rows = []
    for r in combined:
        rt = _rt_ms(r.get('rt_correct'))
        if rt is None or rt > rt_max:
            continue
        ok_rows.append((r, rt))

    rts_for_fast = [rt for _, rt in ok_rows]          # 快速试次统计用全部试次
    n_fast = sum(1 for x in rts_for_fast if x < fast_rt)
    pct_fast = (n_fast / len(rts_for_fast)) if rts_for_fast else float('nan')

    # ---- 第 4 步（可选）：删除 < 400ms（D2/D6 变体） ----
    if drop_fast_400:
        ok_rows = [(r, rt) for r, rt in ok_rows if rt >= 400.0]

    # ---- 第 5 步：逐区块算正确试次的均值与 SD ----
    by_block = {}
    for r, rt in ok_rows:
        by_block.setdefault(r['block'], []).append((r, rt))

    block_mean_c = {}
    block_sd_c = {}
    for b, items in by_block.items():
        cs = [rt for r, rt in items if str(r.get('first_key_correct')) == '1']
        if cs:
            block_mean_c[b] = st.mean(cs)
            block_sd_c[b] = st.stdev(cs) if len(cs) > 1 else 0.0

    # ---- 第 7 步：错误试次的替换值 ----
    def scoring_rt(r, rt):
        if str(r.get('first_key_correct')) == '1':
            return rt
        mode = (r.get('error_mode') or 'correct').lower()
        if mode == 'advance':
            # 不改正：该区块正确均值 + 惩罚
            base = block_mean_c.get(r['block'])
            return (base if base is not None else rt) + penalty
        # 强制改正：rt_correct 本身已是"改对后"的时间，含天然惩罚，不再加
        return rt

    block_scoring = {}
    block_correct_rts = {}
    for b, items in by_block.items():
        block_scoring[b] = [scoring_rt(r, rt) for r, rt in items]
        block_correct_rts[b] = [rt for r, rt in items
                                if str(r.get('first_key_correct')) == '1']

    # ---- 第 9~12 步：按区块长度配对，各算一个 D，再平均 ----
    by_size = {}
    for b, items in by_block.items():
        size = int(items[0][0]['block_trials'])
        pairing = items[0][0]['pairing']
        by_size.setdefault(size, {})[pairing] = b

    pair_ds = []
    for size in sorted(by_size):
        pair = by_size[size]
        b_comp = pair.get('compatible')
        b_inc = pair.get('incompatible')
        if not b_comp or not b_inc:
            continue
        # 第 6 步：合并 SD，只用正确试次
        sd_pool = block_correct_rts[b_comp] + block_correct_rts[b_inc]
        if len(sd_pool) < 2:
            continue
        sd = st.stdev(sd_pool)
        if sd <= 0:
            continue
        m_comp = st.mean(block_scoring[b_comp])
        m_inc = st.mean(block_scoring[b_inc])
        pair_ds.append((size, (m_inc - m_comp) / sd, m_comp, m_inc))

    note = ''
    if len(pair_ds) >= 2:
        pair_ds.sort()
        d1 = sum(p[1] for p in pair_ds) / len(pair_ds)
        d_a = pair_ds[0][1]
        d_b = pair_ds[-1][1]
        variant = 'D1(两段SD)'
    elif len(pair_ds) == 1:
        d1 = pair_ds[0][1]
        d_a = pair_ds[0][1]
        d_b = float('nan')
        variant = 'D1(单段SD)'
        note = '只有一组可配对的区块，无法按两段平均'
    else:
        # 区块长度对不上（例如 greenwald5），退化为全体合并 SD
        all_c = [x for b in block_correct_rts for x in block_correct_rts[b]]
        sc_comp = [x for b in by_block if by_block[b][0][0]['pairing'] == 'compatible'
                   for x in block_scoring[b]]
        sc_inc = [x for b in by_block if by_block[b][0][0]['pairing'] == 'incompatible'
                  for x in block_scoring[b]]
        if sc_comp and sc_inc and len(all_c) > 1:
            sd = st.stdev(all_c)
            d1 = (st.mean(sc_inc) - st.mean(sc_comp)) / sd if sd > 0 else float('nan')
            d_a = d_b = float('nan')
            variant = 'D(合并SD)'
            note = '区块长度不对应，退回全体合并 SD'
        else:
            d1 = d_a = d_b = float('nan')
            variant = '-'
            note = '数据不足'

    m_comp = st.mean([x for b in block_scoring
                      if by_block[b][0][0]['pairing'] == 'compatible'
                      for x in block_scoring[b]]) \
        if any(by_block[b][0][0]['pairing'] == 'compatible' for b in by_block) else float('nan')
    m_inc = st.mean([x for b in block_scoring
                     if by_block[b][0][0]['pairing'] == 'incompatible'
                     for x in block_scoring[b]]) \
        if any(by_block[b][0][0]['pairing'] == 'incompatible' for b in by_block) else float('nan')

    # ---- Greenwald(1998) 对数法，仅作参考 ----
    def clamp_log(vals):
        return [math.log(min(max(v, 300.0), 3000.0)) for v in vals]

    comp_all = [x for b in block_scoring if by_block[b][0][0]['pairing'] == 'compatible'
                for x in block_scoring[b]]
    inc_all = [x for b in block_scoring if by_block[b][0][0]['pairing'] == 'incompatible'
               for x in block_scoring[b]]
    d1998 = float('nan')
    if comp_all and inc_all:
        d1998 = st.mean(clamp_log(inc_all)) - st.mean(clamp_log(comp_all))

    # ---- 剔除判断 ----
    reasons = []
    if n_total == 0:
        reasons.append('没有联合区块数据')
    if pct_fast == pct_fast and pct_fast > fast_limit:
        reasons.append('快速试次 %.1f%% > %.0f%%' % (pct_fast * 100, fast_limit * 100))
    err_limit = opt.get('error_rate_exclude')
    if err_limit is not None and acc == acc and (1 - acc) > float(err_limit):
        reasons.append('错误率 %.1f%% > %.0f%%' % ((1 - acc) * 100, float(err_limit) * 100))
    if d1 != d1:
        reasons.append('D 分数无法计算')

    return {
        'participant': pid,
        'order': order,
        'layout': layout,
        'n_test_trials': n_total,
        'accuracy': round(acc, 4) if acc == acc else '',
        'pct_fast': round(pct_fast, 4) if pct_fast == pct_fast else '',
        'mean_rt_compatible': round(m_comp, 1) if m_comp == m_comp else '',
        'mean_rt_incompatible': round(m_inc, 1) if m_inc == m_inc else '',
        'D1': round(d1, 4) if d1 == d1 else '',
        'D1a': round(d_a, 4) if d_a == d_a else '',
        'D1b': round(d_b, 4) if d_b == d_b else '',
        'D_variant': variant,
        'D_1998_log': round(d1998, 4) if d1998 == d1998 else '',
        'exclude': 'YES' if reasons else 'NO',
        'exclude_reason': '；'.join(reasons),
        'note': note,
    }


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors='replace')
        except Exception:
            pass

    ap = argparse.ArgumentParser(description='IAT 计分（Greenwald et al., 2003 改进算法）')
    ap.add_argument('files', nargs='*', help='要计分的 csv 文件；留空则扫描 --data 目录')
    ap.add_argument('--data', default=os.path.join(BASE_DIR, 'data'))
    ap.add_argument('--out', default=None)
    ap.add_argument('--error-rate-exclude', type=float, default=None,
                    help='错误率超过该比例则剔除被试（默认不启用）')
    ap.add_argument('--delete-below-400', action='store_true',
                    help='删除快于 400ms 的试次（D2/D6 变体）')
    ap.add_argument('--penalty', type=float, default=None,
                    help='advance 模式下错误试次的时间惩罚（默认 600ms）')
    args = ap.parse_args()

    opt = load_options(args)
    out = args.out or os.path.join(args.data, 'processed.csv')
    out_abs = os.path.abspath(out)

    if args.files:
        paths = list(args.files)
    else:
        paths = sorted(glob.glob(os.path.join(args.data, '*.csv')))
    paths = [p for p in paths if os.path.abspath(p) != out_abs
             and not os.path.basename(p).startswith('processed')]

    if not paths:
        sys.exit('没有找到数据文件（%s 下没有 csv）。' % args.data)

    by_pid = {}
    for p in paths:
        rows = load_rows([p])
        if not rows:
            continue
        missing = REQUIRED_COLS - set(rows[0].keys())
        if missing:
            print('跳过 %s：不是 IAT 数据文件（缺少列 %s）'
                  % (os.path.basename(p), '、'.join(sorted(missing))))
            continue
        pid = rows[0].get('participant') or os.path.basename(p).split('_')[0]
        prev = by_pid.get(pid)
        if prev is None:
            by_pid[pid] = rows
        else:
            keep, drop = (rows, prev) if len(rows) > len(prev) else (prev, rows)
            print('警告：被试 %s 有多个数据文件，只使用试次较多的那份（%d 行，忽略 %d 行）'
                  % (pid, len(keep), len(drop)))
            by_pid[pid] = keep

    results = [score_participant(pid, rows, opt) for pid, rows in sorted(by_pid.items())]

    fields = ['participant', 'order', 'layout', 'n_test_trials', 'accuracy', 'pct_fast',
              'mean_rt_compatible', 'mean_rt_incompatible', 'D1', 'D1a', 'D1b',
              'D_variant', 'D_1998_log', 'exclude', 'exclude_reason', 'note']
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in results:
            w.writerow(r)

    print('算法：Greenwald et al. (2003) Table 4 改进算法')
    print('   剔除 RT > %.0fms；快速试次(<%.0fms) >%.0f%% 剔除被试%s%s'
          % (opt['rt_max'], opt['fast_rt'], opt['fast_pct_limit'] * 100,
             '；删除 <400ms 试次' if opt['delete_below_400'] else '',
             ('；错误率 >%.0f%% 剔除' % (opt['error_rate_exclude'] * 100))
             if opt['error_rate_exclude'] is not None else '；不按错误率剔除'))
    print('=' * 78)
    print('%-10s %-4s %6s %7s %7s %8s %8s %s'
          % ('被试', '顺序', '试次', '正确率', '快速%', 'D1', 'D1998', '剔除'))
    print('-' * 78)
    for r in results:
        print('%-10s %-4s %6s %7s %7s %8s %8s %s'
              % (r['participant'], r['order'], r['n_test_trials'],
                 r['accuracy'], r['pct_fast'], r['D1'], r['D_1998_log'],
                 r['exclude_reason'] or r['exclude']))
    print('-' * 78)

    valid = [r['D1'] for r in results if r['exclude'] == 'NO' and isinstance(r['D1'], float)]
    if valid:
        print('有效被试 %d 人，D1 均值 %.3f，标准差 %.3f，范围 %.2f ~ %.2f'
              % (len(valid), st.mean(valid),
                 st.stdev(valid) if len(valid) > 1 else 0.0,
                 min(valid), max(valid)))
    else:
        print('没有有效被试（全部被剔除）。')
    print('结果已写入：%s' % out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
