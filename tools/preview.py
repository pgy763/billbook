"""把报告渲染成 PNG 预览（开发用）。

    python tools/preview.py -o out/page.png -y 2025 -s 1.0 demo/*.csv demo/*.xlsx

注意：输出路径必须用 -o 显式给，不能靠位置参数——上一次运行生成的 out/page.png
本身也存在，用「路径是否存在」判断输入会把输出文件当成账单读进去。
"""

from __future__ import annotations

import argparse
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from billbook import categorize, parse, preview  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("-o", "--out", default="out/page.png")
    ap.add_argument("-y", "--year", type=int, default=2025)
    ap.add_argument("-s", "--scale", type=float, default=1.0)
    a = ap.parse_args()

    expanded: list[str] = []
    for f in a.files:
        hits = glob.glob(f) or ([f] if os.path.exists(f) else [])
        if not hits:
            print(f"  ! 找不到 {f}", file=sys.stderr)
        expanded.extend(hits)
    # 万一有人把输出路径也写进输入，跳过，避免读到自己
    out_abs = os.path.abspath(a.out).lower()
    expanded = [f for f in expanded if os.path.abspath(f).lower() != out_abs]

    recs = []
    for f in expanded:
        r, _ = parse.parse_file(f)
        recs.extend(r)
    categorize.classify_all(recs)
    recs, _ = parse.dedupe(recs)
    img = preview.build_page(recs, a.year, scale=a.scale)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    img.save(a.out)
    print(f"{a.out}  {img.width}x{img.height}")


if __name__ == "__main__":
    main()
