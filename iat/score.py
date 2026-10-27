#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
IAT 计分：D 分数（主）+ Greenwald 1998 对数法（参考）+ 剔除清单

用法：
    python score.py                   读 iat/data/ 下所有 csv
    python score.py --data 某个目录
    python score.py a.csv b.csv       直接指定文件

D1 算法（Nosek et al., 2007 / Greenwald et al., 2003）：
    1. 只用联合区块（配对标签为 compatible / incompatible 的区块）
    2. 剔除 rt > 10000 ms 的试次
    3. 错误试次使用"改正后正确反应"的反应时（数据里的 rt_correct），
       这与 IAT 惯例一致，因此不再额外加惩罚
    4. 按区块长度配对：短块对（如 20 试次的两个）算 D_a，长块对（40 试次）算 D_b
       D_a = (M_不相容 - M_相容) / SD(该对全部试次)
    5. D1 = mean(D_a, D_b)
    正值 = 相容条件（如 花-积极）反应更快，即对目标概念持更积极的内隐态度
"""

import argparse
import csv
import glob
import math
import os
import statistics as st
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

RT_MAX = 10000.0      # ms，超过则剔除该试次
FAST_RT = 300.0       # ms，低于此为"快速试次"
FAST_PCT_LIMIT = 0.10  # 快速试次比例上限
ACC_LIMIT = 0.80      # 正确率下限（即错误率上限 20%）


def load_rows(paths):
    rows = []
    for p in paths:
        with open(p, 'r', encoding='utf-8-sig', newline='') as f:
            for r in csv.DictReader(f):
                rows.append(r)
    return rows


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _rt_ms(v):
    """数据文件里的反应时以秒存储，这里统一转成毫秒。"""
    x = _f(v)
    return None if x is None else x * 1000.0


def score_participant(pid, rows):
    combined = [r for r in rows if r.get('pairing') in ('compatible', 'incompatible')]
    order = rows[0].get('order', '') if rows else ''
    layout = rows[0].get('layout', '') if rows else ''

    # 基本统计（全部联合试次）
    n_total = len(combined)
    n_correct = sum(1 for r in combined if str(r.get('first_key_correct')) == '1')
    rt_all = [_rt_ms(r.get('rt_correct')) for r in combined]
    rt_all = [x for x in rt_all if x is not None and x <= RT_MAX]
    n_fast = sum(1 for x in rt_all if x < FAST_RT)
    acc = (n_correct / n_total) if n_total else float('nan')
    pct_fast = (n_fast / len(rt_all)) if rt_all else float('nan')

    # 按 (配对, 区块长度) 归组
    cells = {}
    for r in combined:
        rt = _rt_ms(r.get('rt_correct'))
        if rt is None or rt > RT_MAX:
            continue
        key = (r['pairing'], int(r['block_trials']))
        cells.setdefault(key, []).append(rt)

    means = {}
    for (pairing, size), vals in cells.items():
        means[(pairing, size)] = st.mean(vals)

    d_a = d_b = None
    note = ''
    sizes = sorted({k[1] for k in cells})
    pair_ds = []
    for size in sizes:
        comp = cells.get(('compatible', size))
        inc = cells.get(('incompatible', size))
        if comp and inc:
            pooled = comp + inc
            sd = st.stdev(pooled) if len(pooled) > 1 else 0
            if sd > 0:
                pair_ds.append((size, (st.mean(inc) - st.mean(comp)) / sd))
    if len(pair_ds) >= 2:
        pair_ds.sort()
        d_a, d_b = pair_ds[0][1], pair_ds[-1][1]
        d1 = (d_a + d_b) / 2
        variant = 'D1(两段SD)'
    elif len(pair_ds) == 1:
        d1 = pair_ds[0][1]
        variant = 'D1(单段SD)'
        note = '仅一组可配对区块'
    else:
        comp = [x for k, v in cells.items() if k[0] == 'compatible' for x in v]
        inc = [x for k, v in cells.items() if k[0] == 'incompatible' for x in v]
        if comp and inc and len(comp) + len(inc) > 1:
            sd = st.stdev(comp + inc)
            d1 = (st.mean(inc) - st.mean(comp)) / sd if sd > 0 else float('nan')
            variant = 'D(合并SD)'
            note = '区块长度不对应，改用全体合并SD'
        else:
            d1 = float('nan')
            variant = '-'
            note = '数据不足'

    m_comp = st.mean([x for k, v in cells.items() if k[0] == 'compatible' for x in v]) \
        if any(k[0] == 'compatible' for k in cells) else float('nan')
    m_inc = st.mean([x for k, v in cells.items() if k[0] == 'incompatible' for x in v]) \
        if any(k[0] == 'incompatible' for k in cells) else float('nan')

    # Greenwald 1998 对数法（参考）
    def clamp_log(vals):
        return [math.log(min(max(v, 300.0), 3000.0)) for v in vals]

    comp_all = [x for k, v in cells.items() if k[0] == 'compatible' for x in v]
    inc_all = [x for k, v in cells.items() if k[0] == 'incompatible' for x in v]
    d1998 = float('nan')
    if comp_all and inc_all:
        d1998 = st.mean(clamp_log(inc_all)) - st.mean(clamp_log(comp_all))

    # 剔除判断
    reasons = []
    if n_total == 0:
        reasons.append('没有联合区块数据')
    if acc == acc and acc < ACC_LIMIT:
        reasons.append('正确率 %.1f%% < %.0f%%' % (acc * 100, ACC_LIMIT * 100))
    if pct_fast == pct_fast and pct_fast > FAST_PCT_LIMIT:
        reasons.append('快速试次 %.1f%% > %.0f%%' % (pct_fast * 100, FAST_PCT_LIMIT * 100))
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
        'D1a': round(d_a, 4) if d_a is not None else '',
        'D1b': round(d_b, 4) if d_b is not None else '',
        'D_variant': variant,
        'D_1998_log': round(d1998, 4) if d1998 == d1998 else '',
        'exclude': 'YES' if reasons else 'NO',
        'exclude_reason': '；'.join(reasons),
        'note': note,
    }


def main():
    ap = argparse.ArgumentParser(description='IAT 计分')
    ap.add_argument('files', nargs='*', help='要计分的 csv 文件；留空则扫描 --data 目录')
    ap.add_argument('--data', default=os.path.join(BASE_DIR, 'data'))
    ap.add_argument('--out', default=None)
    args = ap.parse_args()

    if args.files:
        paths = args.files
    else:
        paths = sorted(glob.glob(os.path.join(args.data, '*.csv')))
        paths = [p for p in paths if not os.path.basename(p).startswith('processed')]

    if not paths:
        sys.exit('没有找到数据文件（%s 下没有 csv）。' % args.data)

    by_pid = {}
    for p in paths:
        rows = load_rows([p])
        if not rows:
            continue
        pid = rows[0].get('participant') or os.path.basename(p).split('_')[0]
        prev = by_pid.get(pid)
        if prev is None:
            by_pid[pid] = rows
        else:
            # 同一被试编号出现在多个文件里（重跑、或编号重复），
            # 不能把两次的数据拼在一起，否则试次会重复、D 值失真
            keep, drop = (rows, prev) if len(rows) > len(prev) else (prev, rows)
            print('警告：被试 %s 有多个数据文件，只使用试次较多的那份（%d 行，忽略 %d 行）'
                  % (pid, len(keep), len(drop)))
            by_pid[pid] = keep

    results = [score_participant(pid, rows) for pid, rows in sorted(by_pid.items())]

    out = args.out or os.path.join(args.data, 'processed.csv')
    fields = ['participant', 'order', 'layout', 'n_test_trials', 'accuracy', 'pct_fast',
              'mean_rt_compatible', 'mean_rt_incompatible', 'D1', 'D1a', 'D1b',
              'D_variant', 'D_1998_log', 'exclude', 'exclude_reason', 'note']
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in results:
            w.writerow(r)

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
                 st.stdev(valid) if len(valid) > 1 else 0, min(valid), max(valid)))
        excl = [r['participant'] for r in results if r['exclude'] == 'YES']
        if excl:
            print('被剔除：%s' % '、'.join(excl))
    print('结果已写入：%s' % out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
