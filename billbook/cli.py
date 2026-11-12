"""命令行入口：把账单文件变成一份 HTML 年报。

    python -m billbook demo/*.csv demo/*.xlsx -o out/2025.html
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
import webbrowser

from . import parse, categorize, stats, report


def _expand(patterns: list[str]) -> list[str]:
    out: list[str] = []
    for p in patterns:
        hits = glob.glob(p)
        if not hits and os.path.exists(p):
            hits = [p]
        if not hits:
            print(f"  ! 找不到文件：{p}", file=sys.stderr)
        out.extend(hits)
    # 去重但保持顺序
    seen: set[str] = set()
    uniq = []
    for f in out:
        k = os.path.abspath(f).lower()
        if k not in seen:
            seen.add(k)
            uniq.append(f)
    return uniq


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    ap = argparse.ArgumentParser(
        prog="billbook",
        description="把支付宝 / 微信账单变成一份可离线打开的年度报告",
    )
    ap.add_argument("files", nargs="+", help="账单文件（CSV / XLSX），支持通配符")
    ap.add_argument("-o", "--out", default="billbook-report.html", help="输出 HTML 路径")
    ap.add_argument("-y", "--year", type=int, help="只统计这一年（默认取记录里最多的年份）")
    ap.add_argument("--open", action="store_true", help="生成后打开浏览器")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    files = _expand(args.files)
    if not files:
        print("没有可读的文件。", file=sys.stderr)
        return 2

    all_recs = []
    meta: dict[str, str] = {}
    for f in files:
        try:
            recs, m = parse.parse_file(f)
        except Exception as e:
            print(f"  ! {os.path.basename(f)}: {e}", file=sys.stderr)
            continue
        meta[os.path.basename(f)] = "微信支付" if m["source"] == "wechat" else "支付宝"
        if not args.quiet:
            note = f"，跳过 {m['skipped']} 行无法解析" if m["skipped"] else ""
            print(f"  读取 {os.path.basename(f)} → {len(recs):,} 条{note}")
        all_recs.extend(recs)

    if not all_recs:
        print("文件读到了但一条记录都没解析出来 —— 检查一下是不是账单导出格式？", file=sys.stderr)
        return 2

    categorize.classify_all(all_recs)
    records, dropped = parse.dedupe(all_recs)
    if dropped and not args.quiet:
        print(f"  去重 {dropped} 条（两个平台导了同一笔）")

    year = args.year
    if year is None:
        from collections import Counter

        year = Counter(r.when.year for r in records if r.kind == "expense").most_common(1)[0][0]

    in_year = [r for r in records if r.when.year == year]
    if not in_year:
        print(f"{year} 年没有任何记录，试试 -y 指定别的年份。", file=sys.stderr)
        return 2

    st = stats.compute(records, year)
    out = report.write(records, year, args.out, files, meta)

    if not args.quiet:
        print()
        print(f"  {year} 年")
        print(f"  支出  ¥{st.total_expense:,.2f}   （{st.count_expense:,} 笔）")
        print(f"  收入  ¥{st.total_income:,.2f}   （{st.count_income:,} 笔）")
        if st.total_income:
            print(f"  结余率 {(1 - st.total_expense / st.total_income) * 100:.1f}%")
        print(f"  日均  ¥{st.total_expense / max(1, st.days):,.2f}")
        print()
        print("  花在哪：")
        for c, a, n, sh in st.cats[:6]:
            bar = "█" * max(1, round(sh * 22))
            print(f"    {c:<6}{bar:<24}{sh * 100:5.1f}%  ¥{a:>12,.2f}")
        if st.merchants:
            print()
            print("  商家 Top5：")
            for name, a, n in st.merchants[:5]:
                print(f"    {name:<16} ¥{a:>10,.2f}  {n} 笔")
        print()
        print(f"  报告 → {out}")
        print(f"  {os.path.getsize(out) / 1024:.0f} KB，单文件、离线可开")

    if args.open:
        webbrowser.open("file:///" + os.path.abspath(out).replace("\\", "/"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
