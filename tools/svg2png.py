"""把报告里的每个 <svg> 光栅化成 PNG，用来肉眼验收。

没有浏览器可用，而报告里的图表是纯内联 SVG，只用到 rect / line / polyline /
circle / text 五种元素，所以这里写一个够用的迷你光栅器：
读 HTML → 抽出每个 SVG → 在深色底上按属性画出来。

它不是为了正确渲染 SVG 规范，而是为了回答「这张图看起来对不对」。
"""

from __future__ import annotations

import os
import re
import sys

from PIL import Image, ImageDraw, ImageFont

FONTS = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
]
_fc: dict = {}


def font(size: int, bold=False):
    key = (round(size), bold)
    if key in _fc:
        return _fc[key]
    path = FONTS[1] if bold and os.path.exists(FONTS[1]) else FONTS[0]
    try:
        f = ImageFont.truetype(path, max(6, round(size)))
    except OSError:
        f = ImageFont.load_default()
    _fc[key] = f
    return f


NUM = re.compile(r"-?\d+(?:\.\d+)?")
ATTR = re.compile(r"([a-zA-Z_:][-\w:.]*)\s*=\s*\"([^\"]*)\"")


def wash(c: str) -> tuple:
    c = (c or "").strip()
    if c.startswith("#"):
        h = c[1:]
        if len(h) == 3:
            h = "".join(ch * 2 for ch in h)
        try:
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
        except ValueError:
            return (255, 0, 255)
    m = re.match(r"rgba?\(([^)]+)\)", c)
    if m:
        parts = [p.strip() for p in m.group(1).split(",")]
        try:
            return tuple(int(float(p)) for p in parts[:3])
        except ValueError:
            return (255, 0, 255)
    named = {"white": (255, 255, 255), "black": (0, 0, 0), "none": None}
    return named.get(c.lower(), (255, 0, 255))


def blend(base, col, alpha: float, box_img, draw):
    pass  # 用带 alpha 的覆盖层逐元素画，见 draw_into


def _paint(img: Image.Image, fn) -> None:
    """把单个图形画到透明图层再合成。

    PIL 的 ImageDraw 在 RGBA 图上写像素时会**直接覆盖** alpha，不会混合，
    所以 SVG 里的 opacity 必须自己走一层 alpha_composite，否则所有半透明
    色块都会渲染成满不透明 —— 热力图会变成一块死板的满色墙。
    """
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    fn(ImageDraw.Draw(layer))
    img.alpha_composite(layer)


def draw_into(img: Image.Image, svg_body: str, scale: float, ox=0.0, oy=0.0):
    def paint(fn):
        _paint(img, fn)

    for m in re.finditer(r"<(rect|line|polyline|polygon|circle|text)\b([^<>]*?)(/?)>", svg_body, re.S):
        tag = m.group(1)
        a = dict(ATTR.findall(m.group(2)))
        start_end = m.end()
        body = ""
        if tag == "text" and not m.group(3):
            close = svg_body.find("</text>", start_end)
            if close > 0:
                body = re.sub(r"<[^>]+>", "", svg_body[start_end:close]).strip()

        def n(k, dflt=0.0):
            v = a.get(k)
            if not v:
                return dflt
            mm = NUM.search(v)
            return float(mm.group(0)) if mm else dflt

        op = max(0.0, min(1.0, n("opacity", 1.0)))
        if op <= 0.01:
            continue
        alpha = int(round(255 * op))
        fill = wash(a.get("fill", "#000"))
        stroke = wash(a.get("stroke", "none")) if a.get("stroke") else None
        sw = n("stroke-width", 1.0)

        if tag == "rect":
            x, y = n("x") * scale + ox, n("y") * scale + oy
            w, h = n("width") * scale, n("height") * scale
            if w <= 0.4 or h <= 0.4:
                continue
            r = n("rx", 0) * scale
            box = [x, y, x + w, y + h]
            f, s = fill, stroke

            def fn(d, box=box, r=r, f=f, s=s, alpha=alpha, sw=sw):
                if r > 0.5:
                    d.rounded_rectangle(box, radius=r, fill=f + (alpha,))
                else:
                    d.rectangle(box, fill=f + (alpha,))
                if s and sw:
                    d.rectangle(box, outline=s + (alpha,), width=max(1, round(sw * scale)))

            paint(fn)
        elif tag == "line":
            x1, y1 = n("x1") * scale + ox, n("y1") * scale + oy
            x2, y2 = n("x2") * scale + ox, n("y2") * scale + oy
            col = stroke or (60, 70, 90)
            wline = max(1, round(sw * scale))
            paint(lambda d, c=col, w=wline, a1=(x1, y1), a2=(x2, y2), al=alpha:
                  d.line([a1, a2], fill=c + (al,), width=w))
        elif tag in ("polyline", "polygon"):
            pts = [float(v) for v in NUM.findall(a.get("points", ""))]
            xy = [(pts[i] * scale + ox, pts[i + 1] * scale + oy) for i in range(0, len(pts) - 1, 2)]
            if len(xy) >= 2:
                tag_, f, s, wline = tag, fill, stroke, max(1, round(sw * scale))

                def fn(d, xy=xy, tag_=tag_, f=f, s=s, wline=wline, alpha=alpha):
                    if tag_ == "polygon" and f:
                        d.polygon(xy, fill=f + (alpha,))
                    if s:
                        d.line(xy, fill=s + (alpha,), width=wline, joint="curve")

                paint(fn)
        elif tag == "circle":
            cx, cy, r = n("cx") * scale + ox, n("cy") * scale + oy, n("r") * scale
            if r <= 0.3:
                continue
            col = fill or stroke
            if col:
                box = [cx - r, cy - r, cx + r, cy + r]
                paint(lambda d, box=box, c=col, alpha=alpha: d.ellipse(box, fill=c + (alpha,)))
        elif tag == "text" and body:
            size = n("font-size", 12) * scale
            if size < 4:
                continue
            col = fill or (255, 255, 255)
            fnt = font(size, bold="bold" in a.get("font-weight", ""))
            anchor = a.get("text-anchor", "start")
            x, y = n("x") * scale + ox, n("y") * scale + oy
            try:
                tw = img.width and ImageDraw.Draw(img).textlength(body, font=fnt)
            except Exception:
                tw = len(body) * size * 0.6
            if anchor == "middle":
                x -= tw / 2
            elif anchor == "end":
                x -= tw
            paint(lambda d, x=x, y=y, c=col, alpha=alpha, fnt=fnt, sz=size:
                  d.text((x, y - sz * 0.78), body, font=fnt, fill=c + (alpha,)))


def rasterize(svg: str, bg="#0a0c11", scale=1.0, pad=10) -> Image.Image:
    head = svg.split(">", 1)[0]
    a = dict(ATTR.findall(head))
    vb = [float(v) for v in NUM.findall(a.get("viewBox", ""))]
    if len(vb) != 4:
        raise ValueError("svg 没有 viewBox：" + a.get("viewBox", "")[:60])
    _, _, w, h = vb
    W = int(w * scale) + pad * 2
    H = int(h * scale) + pad * 2
    img = Image.new("RGBA", (W, H), wash(bg) + (255,))
    body = svg.split(">", 1)[1]
    body = body[: body.rfind("</svg>")] if "</svg>" in body else body
    draw_into(img, body, scale, pad, pad)
    return img


def main():
    html_path = sys.argv[1] if len(sys.argv) > 1 else "out/2025.html"
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "out/charts"
    scale = float(sys.argv[3]) if len(sys.argv) > 3 else 1.2
    os.makedirs(out_dir, exist_ok=True)
    html = open(html_path, encoding="utf-8").read()
    svgs = re.findall(r"<svg\b.*?</svg>", html, re.S)
    print(f"{len(svgs)} 个图表")
    for i, svg in enumerate(svgs):
        img = rasterize(svg, scale=scale)
        p = os.path.join(out_dir, f"chart{i}.png")
        img.convert("RGB").save(p)
        print(f"  {p}  {img.width}x{img.height}")


if __name__ == "__main__":
    main()
