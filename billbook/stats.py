"""统计：把一堆 Record 变成报告需要的全部数字。"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date

from . import categorize


@dataclass
class Stats:
    year: int
    total_expense: float = 0.0
    total_income: float = 0.0
    count_expense: int = 0
    count_income: int = 0
    days: int = 1
    monthly: list = field(default_factory=lambda: [0.0] * 12)
    monthly_in: list = field(default_factory=lambda: [0.0] * 12)
    monthly_cnt: list = field(default_factory=lambda: [0] * 12)
    cats: list = field(default_factory=list)          # [(cat, amount, count, share)]
    merchants: list = field(default_factory=list)     # [(name, amount, count)]
    hours: list = field(default_factory=lambda: [0.0] * 24)
    weekday: list = field(default_factory=lambda: [0.0] * 7)
    biggest: list = field(default_factory=list)       # Record 列表，按金额降序
    streaks: list = field(default_factory=list)
    dom: list = field(default_factory=lambda: [0.0] * 31)
    span: tuple = (None, None)
    median: float = 0.0
    first_half: float = 0.0
    second_half: float = 0.0


def _pct(a: float, b: float) -> float:
    return (a / b) if b else 0.0


def compute(records, year: int) -> Stats:
    st = Stats(year=year)
    exp = [r for r in records if r.kind == "expense" and r.when.year == year]
    inc = [r for r in records if r.kind == "income" and r.when.year == year]

    st.count_expense = len(exp)
    st.count_income = len(inc)
    st.total_expense = sum(r.amount for r in exp)
    st.total_income = sum(r.amount for r in inc)

    if exp:
        ds = sorted(r.when.date() for r in exp)
        st.span = (ds[0], ds[-1])
        st.days = max(1, (ds[-1] - ds[0]).days + 1)

    for r in exp:
        m = r.when.month - 1
        st.monthly[m] += r.amount
        st.monthly_cnt[m] += 1
        st.hours[r.when.hour] += r.amount
        st.weekday[r.when.weekday()] += r.amount
        st.dom[r.when.day - 1] += r.amount
    for r in inc:
        st.monthly_in[r.when.month - 1] += r.amount

    agg: dict[str, float] = defaultdict(float)
    cnt: dict[str, int] = defaultdict(int)
    for r in exp:
        agg[r.cat] += r.amount
        cnt[r.cat] += 1
    total = st.total_expense or 1.0
    st.cats = [
        (c, a, cnt[c], a / total)
        for c, a in sorted(agg.items(), key=lambda kv: -kv[1])
    ]

    magg: dict[str, float] = defaultdict(float)
    mcnt: dict[str, int] = defaultdict(int)
    for r in exp:
        k = categorize.merchant(r)
        magg[k] += r.amount
        mcnt[k] += 1
    st.merchants = [(k, v, mcnt[k]) for k, v in sorted(magg.items(), key=lambda kv: -kv[1])]

    # 「最贵的几笔」如果不去重，一年的房租会占满整张表 —— 真实账单里就是这样，
    # 每个月同一笔 5200 块。同一个商家最多留 2 笔，剩下的让给别的大额。
    seen_merchant: dict[str, int] = defaultdict(int)
    big = []
    for r in sorted(exp, key=lambda r: -r.amount):
        k = categorize.merchant(r)
        if seen_merchant[k] >= 2:
            continue
        seen_merchant[k] += 1
        big.append(r)
        if len(big) >= 12:
            break
    st.biggest = big

    amounts = sorted(r.amount for r in exp)
    if amounts:
        n = len(amounts)
        st.median = amounts[n // 2] if n % 2 else (amounts[n // 2 - 1] + amounts[n // 2]) / 2

    # 连着多少天有消费 —— 最有「人味」的一个指标
    dayset = {r.when.date() for r in exp}
    if dayset:
        run, best, best_span = 0, 0, None
        prev = None
        for d in sorted(dayset):
            run = run + 1 if prev and (d - prev).days == 1 else 1
            if run > best:
                best, best_span = run, (d, run)
            prev = d
        st.streaks = [("最长连续消费", best, best_span)]

    mid = date(year, 7, 1)
    st.first_half = sum(r.amount for r in exp if r.when.date() < mid)
    st.second_half = st.total_expense - st.first_half
    return st


def anomalies(records, st: Stats) -> list[dict]:
    """异常消费：单笔明显贵过你平时的水平。

    两个坑必须避开，否则输出会变成一句废话：
    1. 房租、房贷这种每月固定的大额，一定比日均高好几倍，但它不是「异常」。
       所以先看这笔是不是该商家的常态 —— 商家一年出现 6 次以上时，
       拿它自己的中位数当基准。
    2. 判据要相对自己而不是绝对金额，月薪三千和月薪三万的人都能用。
    """
    exp = [r for r in records if r.kind == "expense" and r.when.year == st.year]
    if not exp:
        return []

    from statistics import median as _median

    by_merchant: dict[str, list[float]] = defaultdict(list)
    for r in exp:
        by_merchant[categorize.merchant(r)].append(r.amount)
    med_of = {k: _median(v) for k, v in by_merchant.items()}

    monthly_mean = [a / 30.0 for a in st.monthly]
    overall = st.total_expense / max(1, st.days)

    out = []
    for r in exp:
        name = categorize.merchant(r)
        peers = by_merchant[name]
        if len(peers) >= 6:                     # 常客：和它自己比
            base = med_of[name]
            floor = 2.5
        else:                                   # 偶发：和你的日均比
            base = monthly_mean[r.when.month - 1] or overall
            floor = 3.0
        if not base:
            continue
        ratio = r.amount / base
        if r.amount >= 200 and ratio >= floor:
            out.append({
                "rec": r, "ratio": ratio, "base": base,
                "recurring": len(peers) >= 6,
            })
    out.sort(key=lambda d: -d["ratio"])
    return out[:8]


def week_rows(st: Stats) -> list[tuple[str, float, int]]:
    names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    return [(names[i], st.weekday[i], 0) for i in range(7)]


def hour_buckets(st: Stats) -> list[tuple[str, float]]:
    """24 小时压成 8 个时段，比 24 根柱子好读。"""
    labels = ["0-3", "3-6", "6-9", "9-12", "12-15", "15-18", "18-21", "21-24"]
    out = []
    for i, lab in enumerate(labels):
        out.append((lab, sum(st.hours[i * 3:(i + 1) * 3])))
    return out
