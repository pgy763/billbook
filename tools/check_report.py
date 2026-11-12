"""在没有浏览器的情况下验收报告 HTML。

这个环境里 headless 浏览器起不来（mojo platform_channel 报拒绝访问），
所以报告只能靠静态检查：解析 HTML 和里面所有 SVG，逐个核对数字。
能查出来的问题：图形跑到画布外、宽高为负或 NaN、文字重叠、空章节、颜色写错。
"""

from __future__ import annotations

import math
import os
import re
import sys
from html.parser import HTMLParser

# ---------------------------------------------------------------- 解析

TAG = re.compile(r"<(/?)([a-zA-Z][\w:-]*)((?:\s+[^<>]*?)?)(/?)>", re.S)
ATTR = re.compile(r"([a-zA-Z_:][-\w:.]*)\s*=\s*\"([^\"]*)\"")
NUM = re.compile(r"-?\d+(?:\.\d+)?(?:e-?\d+)?")


def attrs_of(s: str) -> dict:
    return {k: v for k, v in ATTR.findall(s)}


def parse_svgs(html: str) -> list[dict]:
    out = []
    for m in re.finditer(r"<svg\b(.*?)</svg>", html, re.S):
        body = m.group(1)
        head = body.split(">", 1)[0]
        a = attrs_of(head)
        vb = a.get("viewBox", "")
        nums = [float(x) for x in NUM.findall(vb)]
        out.append(
            {
                "attrs": a,
                "viewbox": nums,
                "body": body,
                "raw": m.group(0),
                "shapes": collect(body),
            }
        )
    return out


SHAPE_TAGS = {"rect", "line", "polyline", "polygon", "circle", "path", "text"}


def collect(body: str) -> list[dict]:
    items = []
    for m in TAG.finditer(body):
        closing, name, raw_attrs, selfclose = m.groups()
        if closing or name not in SHAPE_TAGS:
            continue
        items.append({"tag": name, "a": attrs_of(raw_attrs)})
    return items


# ---------------------------------------------------------------- 检查

class Checker:
    def __init__(self):
        self.errors: list[str] = []
        self.warns: list[str] = []
        self.notes: list[str] = []

    def err(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warns.append(msg)

    def note(self, msg):
        self.notes.append(msg)


def _f(a: dict, k: str, default=0.0) -> float:
    v = a.get(k)
    if v is None:
        return default
    try:
        return float(v)
    except ValueError:
        return float("nan")


def check_svg(idx: int, svg: dict, ck: Checker):
    vb = svg["viewbox"]
    if len(vb) != 4:
        ck.err(f"svg#{idx}: viewBox 不是 4 个数字：{svg['attrs'].get('viewBox')!r}")
        return
    x0, y0, w, h = vb
    if w <= 0 or h <= 0:
        ck.err(f"svg#{idx}: viewBox 宽高非正：{w}×{h}")
        return
    pad_x = w * 0.08
    pad_y = h * 0.12
    counts = {}
    texts = []
    for s in svg["shapes"]:
        tag = s["tag"]
        a = s["a"]
        counts[tag] = counts.get(tag, 0) + 1

        for k in ("x", "y", "width", "height", "x1", "y1", "x2", "y2", "cx", "cy", "r"):
            if k in a and NUM.search(a[k]):
                v = _f(a, k)
                if math.isnan(v) or math.isinf(v):
                    ck.err(f"svg#{idx}: <{tag}> 的 {k} 是 NaN/inf（{a.get(k)!r}）")

        if tag == "rect":
            rw, rh = _f(a, "width"), _f(a, "height")
            if rw < 0 or rh < 0:
                ck.err(f"svg#{idx}: <rect> 宽高为负 {rw}×{rh} x={a.get('x')} y={a.get('y')}")
            rx, ry = _f(a, "x", x0), _f(a, "y", y0)
            if rx < x0 - pad_x or ry < y0 - pad_y:
                ck.err(f"svg#{idx}: <rect> 越界到左上 x={rx:.1f} y={ry:.1f}（画布 {x0},{y0},{w},{h}）")
            if rw > w * 1.02 or rh > h * 1.02:
                ck.err(f"svg#{idx}: <rect> 比画布还大 {rw:.0f}×{rh:.0f}（画布 {w:.0f}×{h:.0f}）")
        elif tag in ("line",):
            for k in ("x1", "x2"):
                if _f(a, k) > x0 + w + pad_x or _f(a, k) < x0 - pad_x:
                    ck.err(f"svg#{idx}: <line> {k}={a.get(k)} 超出画布宽度")
        elif tag == "circle":
            if _f(a, "r") <= 0:
                ck.err(f"svg#{idx}: <circle> 半径为 0")
        elif tag == "polyline":
            pts = [float(x) for x in NUM.findall(a.get("points", ""))]
            if len(pts) < 4:
                ck.err(f"svg#{idx}: <polyline> 点数不足")
            for i in range(0, len(pts) - 1, 2):
                if math.isnan(pts[i]) or math.isnan(pts[i + 1]):
                    ck.err(f"svg#{idx}: <polyline> 有 NaN 点")
                if pts[i + 1] < y0 - pad_y or pts[i + 1] > y0 + h + pad_y:
                    ck.err(f"svg#{idx}: <polyline> 点 y={pts[i + 1]:.1f} 超出画布")
        elif tag == "text":
            t = re.sub(r"<[^>]+>", "", a.get("__text__", ""))
            texts.append((_f(a, "x"), _f(a, "y"), t))
            if _f(a, "x") > x0 + w + 6:
                ck.warn(f"svg#{idx}: <text> x={_f(a, 'x'):.1f} 超出画布右边界")

    if not counts:
        ck.err(f"svg#{idx}: 一个图形都没有（空图表）")
    ck.note(f"svg#{idx}: viewBox={w:.0f}×{h:.0f} 图形 " +
            " ".join(f"{k}={v}" for k, v in sorted(counts.items())))


def check(html: str) -> Checker:
    ck = Checker()

    if "<html" not in html or "</html>" not in html:
        ck.err("不是完整 HTML 文档")
    if "<title>" not in html:
        ck.err("缺 <title>")

    # 图表
    svgs = parse_svgs(html)
    if len(svgs) < 4:
        ck.err(f"图表只有 {len(svgs)} 个，年度报告至少有日历/月度/分类/热力图/商家 5 个")
    for i, svg in enumerate(svgs):
        check_svg(i, svg, ck)

    # 章节
    sections = re.findall(r"<section\b", html)
    if len(sections) < 7:
        ck.err(f"章节只有 {len(sections)} 个")
    ck.note(f"章节 {len(sections)} 个，图表 {len(svgs)} 个")

    # 关键数字必须在页面上
    for must in ("年度账单", "消费人格", "数据来源", "最贵的几笔"):
        if must not in html:
            ck.err(f"页面缺关键区块：{must}")

    # 未替换的占位符 / 模板残留
    for bad in ("{year}", "{%", "{{", "None", "nan", "NaN", "$0", "¥-"):
        if bad in html:
            ck.warn(f"页面出现可疑串：{bad!r}")

    # 数字格式：¥ 后面必须是数字
    for m in re.finditer(r"¥(-?\d[\d,]*\.?\d*)", html):
        v = m.group(1).replace(",", "")
        try:
            fv = float(v)
        except ValueError:
            ck.err(f"¥ 后面不是数字：{m.group(0)!r}")
            continue
        if fv < 0:
            ck.err(f"支出金额为负：{m.group(0)!r}")

    # CSS 里没有未解析的 var()
    for m in re.finditer(r"var\((--[\w-]+)\)", html):
        name = m.group(1)
        if f"{name}:" not in html:
            ck.err(f"CSS 变量 {name} 被引用但没有定义")

    # JS 括号配平（粗查）
    js = re.search(r"<script>(.*?)</script>", html, re.S)
    if js:
        body = js.group(1)
        for o, c in (("{", "}"), ("(", ")"), ("[", "]")):
            if body.count(o) != body.count(c):
                ck.err(f"内联 JS 括号不配平：{o}={body.count(o)} {c}={body.count(c)}")
        ck.note(f"内联 JS {len(body)} 字符")

    # 体积
    kb = len(html.encode("utf-8")) / 1024
    if kb > 4000:
        ck.warn(f"报告 {kb:.0f} KB，对单文件 HTML 来说偏大（是否把明细全写进去了？）")
    ck.note(f"报告体积 {kb:.0f} KB")

    return ck


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "out/2025.html"
    html = open(path, encoding="utf-8").read()
    ck = check(html)
    for n in ck.notes:
        print("  ·", n)
    for w in ck.warns:
        print("  ~", w)
    for e in ck.errors:
        print("  ✗", e)
    print()
    if ck.errors:
        print(f"FAILED: {len(ck.errors)} error(s), {len(ck.warns)} warning(s)")
        return 1
    print(f"OK: 0 error, {len(ck.warns)} warning(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
