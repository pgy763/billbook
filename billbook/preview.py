"""在无浏览器环境下把年度报告「画」出来。

为什么需要：这台机器上 headless 浏览器起不来（mojo platform_channel 报拒绝访问），
所以没法截图验收 HTML。而报告是纯静态的，布局又是我们自己定的，
那就用 Pillow 按同一套数据、同一套样式重画一遍 —— 用来验收排版，
顺便当成视频素材（在真实页面上滚动，比一堆卡片拼贴可信得多）。
"""

from __future__ import annotations

import math
import os

from PIL import Image, ImageDraw, ImageFont

from . import categorize, stats as stats_mod

# ---------------------------------------------------------------- 基础

BG = (10, 12, 17)
PANEL = (17, 20, 32)
LINE = (30, 36, 48)
INK = (232, 236, 244)
DIM = (139, 147, 167)
FAINT = (95, 103, 121)
ACCENT = (94, 234, 212)
WARN = (251, 191, 36)
BAD = (248, 113, 113)

FONT_DIR = r"C:\Windows\Fonts"
_fc: dict = {}


def font(size: float, bold: bool = False):
    key = (round(size), bold)
    if key in _fc:
        return _fc[key]
    name = "msyhbd.ttc" if bold else "msyh.ttc"
    path = os.path.join(FONT_DIR, name)
    if not os.path.exists(path):
        path = os.path.join(FONT_DIR, "simhei.ttf")
    try:
        f = ImageFont.truetype(path, max(7, round(size)))
    except OSError:
        f = ImageFont.load_default()
    _fc[key] = f
    return f


def rgb(hexstr: str) -> tuple:
    h = hexstr.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def money(v: float) -> str:
    return f"{v:,.0f}"


def money2(v: float) -> str:
    return f"{v:,.2f}"


def pct(v: float, d: int = 1) -> str:
    return f"{v * 100:.{d}f}%"


def text(d, xy, s, size, color, bold=False, anchor="la"):
    d.text(xy, s, size, color, bold, anchor)


def tlen(d, s, size, bold=False) -> float:
    """宽度测量。所有绘制都走 _Scaled，它的 textlength 会自己除回 scale。"""
    return d.textlength(s, size, bold)


def wrap(d, s, size, max_w, bold=False) -> list[str]:
    """按宽度断行。中文逐字断，拉丁按词断。"""
    out, cur = [], ""
    for ch in s:
        if ch == "\n":
            out.append(cur)
            cur = ""
            continue
        trial = cur + ch
        if tlen(d, trial, size, bold) <= max_w:
            cur = trial
        else:
            if ch.isascii() and ch != " " and cur and cur[-1].isascii() and cur[-1] != " ":
                cut = cur.rfind(" ")
                if cut > 0:
                    out.append(cur[:cut])
                    cur = cur[cut + 1:] + ch
                    continue
            out.append(cur)
            cur = ch
    if cur:
        out.append(cur)
    return out


def para(d, xy, s, size, color, max_w, bold=False, lh=1.7):
    x, y = xy
    lines = wrap(d, s, size, max_w, bold)
    for i, ln in enumerate(lines):
        d.text((x, y + i * size * lh), ln, size, color, bold)


# ---------------------------------------------------------------- 页面

W = 1120           # 逻辑宽度，跟 CSS 的 max-width 一致
PAD = 40           # .wrap 左右 padding


class Page:
    """按顺序往下画，自动累积高度。"""

    def __init__(self, w=W, scale=1.0):
        self.w = w
        self.scale = scale
        self.H = 0
        self.ops = []      # (kind, payload) —— 两遍绘制：先量高，再画图

    def need(self, h):
        self.H += h

    # 为了简单，这里不做真正的两遍布局，直接用一张超长图往下画
    def img(self, h):
        return Image.new("RGB", (int(self.w * self.scale), int(h * self.scale)), BG)


def build_page(records, year: int, scale: float = 1.0, width: int = W) -> Image.Image:
    """把整份报告画成一张长图。"""
    st = stats_mod.compute(records, year)
    anoms = stats_mod.anomalies(records, st)

    mat = [[0.0] * 24 for _ in range(7)]
    day_totals: dict = {}
    for r in records:
        if r.kind == "expense" and r.when.year == year:
            mat[r.when.weekday()][r.when.hour] += r.amount
            d0 = r.when.date()
            day_totals[d0] = day_totals.get(d0, 0.0) + r.amount

    total_h = _measure(st, anoms, day_totals, width)
    img = Image.new("RGB", (int(width * scale), int(total_h * scale)), BG)
    # 始终用 _Scaled 包一层：它和 ImageDraw 的签名不同（参数顺序、颜色类型），
    # 混用会报 `TypeError: object of type 'bool' has no len()`（anchor 传成了 bold）。
    _draw(_Scaled(img, scale), st, anoms, day_totals, year, width, mat)
    return img


class _Scaled:
    """把绘制坐标乘以 scale，这样同一套布局代码能出 1x 预览和 2x 海报。"""

    def __init__(self, img, s):
        self.img = img
        self.s = s
        self.d = ImageDraw.Draw(img)

    def text(self, xy, s, size, color, bold=False, anchor="la"):
        self.d.text((xy[0] * self.s, xy[1] * self.s), s,
                    font=font(size * self.s, bold), fill=color, anchor=anchor)

    def textlength(self, s, size, bold=False):
        return self.d.textlength(s, font=font(size * self.s, bold)) / self.s

    def rectangle(self, box, fill=None, outline=None, width=1):
        b = [box[0] * self.s, box[1] * self.s, box[2] * self.s, box[3] * self.s]
        self.d.rectangle(b, fill=fill, outline=outline, width=max(1, round(width * self.s)))

    def rounded(self, box, r, fill=None, outline=None, width=1):
        b = [box[0] * self.s, box[1] * self.s, box[2] * self.s, box[3] * self.s]
        self.d.rounded_rectangle(b, radius=r * self.s, fill=fill, outline=outline,
                                 width=max(1, round(width * self.s)))

    def line(self, xy, fill, width=1):
        self.d.line([xy[0] * self.s, xy[1] * self.s, xy[2] * self.s, xy[3] * self.s],
                    fill=fill, width=max(1, round(width * self.s)))

    def ellipse(self, box, fill=None):
        b = [box[0] * self.s, box[1] * self.s, box[2] * self.s, box[3] * self.s]
        self.d.ellipse(b, fill=fill)


def _measure(st, anoms, day_totals, w) -> float:
    """粗量高度。多留比少留安全，底部多一截深色也不算错。"""
    h = 0
    h += 330                      # hero
    h += 190                      # kpi 两行
    if day_totals:
        h += 76 + 250 + 64        # 日历
    h += 76 + 260 + 64        # 月度
    h += 76 + (len(st.cats) * 40) + 44
    h += 76 + 220 + 64        # 热力
    h += 76 + (min(10, len(st.merchants)) * 30) + 44
    h += 76 + (min(8, len(st.biggest)) * 40) + 44
    if anoms:
        h += 76 + min(6, len(anoms)) * 74 + 44
    h += 76 + 200 + 80        # 人格 + footer
    h += 90                      # footer
    return h


def _draw(d, st, anoms, day_totals, year, w, mat):
    x = PAD
    inner = w - PAD * 2
    y = 0.0

    def hr():
        nonlocal y
        d.line([PAD, y, w - PAD, y], LINE, 1)

    def label(s):
        """章节标题。下面留 30px：图表的第一行坐标标签是画在画布顶部的，
        留 12px 会和标题叠在一起（第一版就把「按月看」和「27,305」压成了一行）。"""
        nonlocal y
        y += 46
        d.text((x, y), s, 12.5, FAINT, False)
        y += 30

    # ---------- hero
    y = 96
    d.text((x, y), f"{year} 年度账单", 14, FAINT, False)
    y += 40
    d.text((x, y), money(st.total_expense), 96, INK, True)
    tw = tlen(d, money(st.total_expense), 96, True)
    d.text((x + tw + 14, y + 54), "元", 36, DIM, True)
    y += 132
    save = 1 - st.total_expense / st.total_income if st.total_income else 0
    para(d, (x, y),
         f"这一年你花了 ¥{money(st.total_expense)}，收入 ¥{money(st.total_income)}，"
         f"结余率 {pct(save)}。一共 {st.count_expense:,} 笔支出，覆盖 {st.days} 天。",
         16.5, DIM, inner - 40, lh=1.75)
    y += 78

    # ---------- kpi（4 列 × 2 行）
    per_day = st.total_expense / max(1, st.days)
    sat = max(range(7), key=lambda i: st.weekday[i]) if st.total_expense else 0
    peak = max(range(12), key=lambda i: st.monthly[i]) if st.total_expense else 0
    WEEK = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    cells = [
        ("日均消费", f"¥{money(per_day)}"),
        ("中位数单笔", f"¥{money2(st.median)}"),
        ("每天平均笔数", f"{st.count_expense / max(1, st.days):.1f} 笔"),
        ("最常去的商家", st.merchants[0][0] if st.merchants else "-"),
        ("花钱最多的星期", WEEK[sat]),
        ("花钱最多的月份", f"{peak + 1} 月"),
        ("结余率", pct(save)),
        ("有消费的天数", f"{len(day_totals)} 天"),
    ]
    cw = (inner - 14 * 3) / 4
    for i, (k, v) in enumerate(cells):
        cx = x + (i % 4) * (cw + 14)
        cy = y + (i // 4) * 92
        d.rounded([cx, cy, cx + cw, cy + 80], 12, fill=PANEL, outline=LINE, width=1)
        d.text((cx + 18, cy + 16), k, 11.5, FAINT, False)
        d.text((cx + 18, cy + 36), v, 21, INK, True)
    y += 2 * 92 + 24

    # ---------- 日历
    hr()
    label("这一年，钱是怎么流走的")
    ch = 250
    _calendar(d, day_totals, year, x, y, inner, ch)
    y += ch + 30
    if day_totals:
        d.text((x, y), f"最深的一天 ¥{money(max(day_totals.values()))}", 12, DIM, False)
        d.text((x + 260, y), f"有消费 {len(day_totals)} 天", 12, DIM, False)
        d.text((x + 420, y), f"{st.days - len(day_totals)} 天一分没花", 12, DIM, False)
    y += 34

    # ---------- 月度
    hr()
    label("按月看")
    _monthly(d, st, x, y, inner, 260)
    y += 260 + 12
    d.rounded([x, y + 4, x + 9, y + 13], 2, fill=ACCENT)
    d.text((x + 16, y), "支出", 12, DIM, False)
    d.rounded([x + 74, y + 4, x + 83, y + 13], 2, fill=WARN)
    d.text((x + 90, y), "收入", 12, DIM, False)
    d.text((x + 150, y), f"最高的一个月是 {peak + 1} 月，¥{money(st.monthly[peak])}", 12, DIM, False)
    y += 34

    # ---------- 分类
    hr()
    label("钱花在哪")
    row_h = 40
    hi = max((a for _, a, _, _ in st.cats), default=1) or 1
    for i, (name, amt, cnt, share) in enumerate(st.cats):
        yy = y + i * row_h
        col = rgb(categorize.CAT_COLOR.get(name, "#475569"))
        d.text((x, yy + 8), name, 13.5, INK, False)
        bw = (inner - 210) * (amt / hi)
        d.rounded([x + 86, yy + 11, x + 86 + max(3, bw), yy + row_h - 12], 4, fill=col)
        d.text((x + 86 + max(3, bw) + 10, yy + 9), f"¥{money(amt)} · {pct(share)}", 12.5, DIM, False)
    y += len(st.cats) * row_h + 20

    # ---------- 热力
    hr()
    label("你在什么时间花钱")
    _heat(d, mat, x, y, inner, 220)
    y += 220 + 12
    peak_cell = max(((v, wd, h) for wd in range(7) for h, v in enumerate(mat[wd])))
    d.text((x, y), f"最集中的时段是 {WEEK[peak_cell[1]]} {peak_cell[2]}:00 前后，"
                   f"合计 ¥{money(peak_cell[0])}", 12, DIM, False)
    y += 34

    # ---------- 商家
    hr()
    label("你和谁打交道最多")
    rows = st.merchants[:10]
    mh = rows[0][1] if rows else 1
    for i, (name, amt, cnt) in enumerate(rows):
        yy = y + i * 30
        d.text((x, yy + 4), f"{i + 1:02d}", 12.5, DIM, False)
        nm = name if len(name) <= 14 else name[:13] + "…"
        d.text((x + 26, yy + 4), nm, 13, INK, False)
        bw = (inner - 330) * (amt / mh)
        d.rounded([x + 180, yy + 8, x + 180 + max(3, bw), yy + 19], 3, fill=ACCENT)
        d.text((x + inner - 78, yy + 4), f"¥{money(amt)}", 12.5, INK, False, anchor="ra")
        d.text((x + inner, yy + 4), f"{cnt} 笔", 11.5, FAINT, False, anchor="ra")
    y += len(rows) * 30 + 20

    # ---------- 最贵几笔
    hr()
    label("最贵的几笔")
    for i, r in enumerate(st.biggest[:8]):
        yy = y + i * 40
        d.text((x, yy + 4), f"{r.when:%m-%d %H:%M}", 12.5, DIM, False)
        d.text((x + 96, yy + 4), r.party[:16], 13.5, INK, False)
        d.text((x + 330, yy + 4), (r.desc or "-")[:22], 12.5, DIM, False)
        tag = r.cat
        tw2 = tlen(d, tag, 11)
        d.rounded([x + 580, yy + 5, x + 580 + tw2 + 16, yy + 25], 10,
                  fill=(24, 40, 40))
        d.text((x + 588, yy + 9), tag, 11, ACCENT, False)
        d.text((x + inner, yy + 4), f"¥{money2(r.amount)}", 13.5, INK, False, anchor="ra")
    y += 8 * 40 + 20

    # ---------- 异常
    if anoms:
        hr()
        label("这几笔，比你平时贵得多")
        for i, an in enumerate(anoms[:6]):
            r = an["rec"]
            yy = y + i * 74
            d.rectangle([x, yy + 2, x + 3, yy + 62], fill=BAD)
            d.text((x + 20, yy), f"{r.party} · ¥{money2(r.amount)}", 14.5, INK, True)
            how = (f"是它自己平时（¥{money(an['base'])}）的 {an['ratio']:.1f} 倍"
                   if an["recurring"] else f"是当月日均的 {an['ratio']:.1f} 倍")
            d.text((x + 20, yy + 26), f"{r.when:%Y-%m-%d %H:%M} · {r.cat} · {how}", 12.5, DIM, False)
        y += min(6, len(anoms)) * 74 + 10

    # ---------- 人格
    hr()
    label("你的消费人格")
    from .report import persona
    name, desc = persona(st)
    card_h = 96 + 13.5 * 1.7 * max(1, len(wrap(d, desc, 13.5, inner - 56)))
    d.rounded([x, y, x + inner, y + card_h], 14, fill=PANEL, outline=LINE, width=1)
    d.text((x + 28, y + 24), "PERSONA", 11.5, FAINT, False)
    d.text((x + 28, y + 44), name, 30, INK, True)
    para(d, (x + 28, y + 92), desc, 13.5, DIM, inner - 56, lh=1.7)

    # ---------- footer
    # 必须画在卡片外面。卡片高度随文案行数变，所以 footer 用 card_h 推下去，
    # 写死 110 时两行文案会压到卡片底边上。
    d.text((x, y + card_h + 40), "BillBook · 只在这台电脑上算，不上传任何数据", 12, FAINT, False)


# ---------------------------------------------------------------- 子图

def _calendar(d, day_totals, year, x, y, w, h):
    from datetime import date
    cols, rows = 53, 7
    cw = w / cols
    ch = h / rows
    hi = max(day_totals.values(), default=0) or 1
    first = date(year, 1, 1)
    off = first.weekday()
    for m in range(1, 13):
        idx = (date(year, m, 1) - first).days + off
        d.text((x + (idx // 7) * cw, y + h + 12), f"{m}月", 10.5, FAINT, False)
    for day, v in day_totals.items():
        idx = (day - first).days + off
        col, row = divmod(idx, 7)
        t = (v / hi) ** 0.55
        k = 0.10 + 0.88 * t
        c = tuple(int(ACCENT[i] * k + BG[i] * (1 - k)) for i in range(3))
        d.rectangle([x + col * cw, y + row * ch,
                     x + col * cw + cw - 1.8, y + row * ch + ch - 1.8], fill=c)


def _monthly(d, st, x, y, w, h):
    pad_l, pad_b = 54, 26
    iw, ih = w - pad_l - 6, h - pad_b
    hi = max(st.monthly + st.monthly_in + [1])
    step = iw / 12
    bw = step * 0.52
    for i in range(5):
        yy = y + ih - ih * i / 4
        d.line([x + pad_l, yy, x + w, yy], LINE, 1)
        d.text((x + pad_l - 10, yy - 7), money(hi * i / 4), 11, FAINT, False, anchor="ra")
    for i, v in enumerate(st.monthly):
        bh = ih * (v / hi)
        bx = x + pad_l + step * i + (step - bw) / 2
        d.rounded([bx, y + ih - bh, bx + bw, y + ih], 3, fill=ACCENT)
        d.text((bx + bw / 2, y + ih + 8), str(i + 1), 11, DIM, False, anchor="ma")
    pts = []
    for i, v in enumerate(st.monthly_in):
        pts.append((x + pad_l + step * i + step / 2, y + ih - ih * (v / hi)))
    for a, b in zip(pts, pts[1:]):
        d.line([a[0], a[1], b[0], b[1]], WARN, 2)


def _heat(d, mat, x, y, w, h):
    pad_l = 46
    cw = (w - pad_l) / 24
    ch = (h - 24) / 7
    hi = max((v for r in mat for v in r), default=0) or 1
    WEEK = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    for hh in range(0, 24, 3):
        d.text((x + pad_l + cw * hh, y + h - 14), f"{hh}时", 11, FAINT, False)
    for wd in range(7):
        yy = y + ch * wd
        d.text((x + pad_l - 12, yy + ch / 2 - 7), WEEK[wd], 11, DIM, False, anchor="ra")
        for hh in range(24):
            v = mat[wd][hh]
            if v <= 0:
                d.rectangle([x + pad_l + cw * hh + 1, yy + 1,
                             x + pad_l + cw * hh + cw - 1, yy + ch - 1],
                            fill=(20, 24, 34))
                continue
            t = (v / hi) ** 0.55
            k = 0.16 + 0.84 * t
            c = tuple(int(ACCENT[i] * k + BG[i] * (1 - k)) for i in range(3))
            d.rectangle([x + pad_l + cw * hh + 1, yy + 1,
                         x + pad_l + cw * hh + cw - 1, yy + ch - 1], fill=c)
