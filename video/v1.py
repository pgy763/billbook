"""BillBook 视频 1 ——《你的年度账单多算了 6 万 2》

核心事实（全部来自 demo 账单实算，不是编的）：
  把「不计收支」当成支出 → 245,762 元
  正确的算法           → 183,070 元
  虚高 62,692 元，34.2%

这些「不计收支」是信用卡还款和余额宝自动转入：
钱从你的左口袋进右口袋，一分都没花出去。
微信导出时「收/支」这一列是**空的**，所以按列判断的工具全部会算错。

时长 40s，1080x1920，30fps。
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from video.kit import (  # noqa: E402
    ACCENT, BAD, BG, BG2, BLUE, DIM, FAINT, INK, PINK, WARN,
    Video, background, clamp, ease_in_out, ease_out, ease_out_back, ease_out_expo,
    fmt_int, font, glow_text, measure, norm, paragraph, rrect, text, wrap,
)

W, H = 1080, 1920
M = 88                      # 左右边距
DUR = 40.0

# ---------------------------------------------------------------- 数据

WRONG = 245_762.91
RIGHT = 183_070.45
DELTA = 62_692.46
OVER_PCT = 34.2

# 账单里真实存在的三条「不计收支」
NEUTRAL = [
    ("招商银行信用卡", "信用卡还款", 4603.71, "2025-09-20 08:00"),
    ("招商银行信用卡", "信用卡还款", 2124.16, "2025-03-20 08:00"),
    ("余额宝", "余额宝-自动转入", 1990.07, "2025-11-21 08:00"),
]

CATS = [
    ("住房", 66_103, 36.1),
    ("数码", 36_770, 20.1),
    ("购物", 19_467, 10.6),
    ("交通", 18_163, 9.9),
    ("餐饮", 14_872, 8.1),
    ("娱乐", 11_038, 6.0),
]


def human(v: float) -> str:
    return f"{v:,.0f}"


# ---------------------------------------------------------------- 通用件

def _alpha_text(img, xy, s, size, color, weight="bold", alpha=1.0, anchor="la"):
    """画一行半透明文字。

    直接 `ImageDraw.text` 不支持 alpha，所以走一层透明图层再合成 ——
    这样交叉淡入淡出时不会出现「先亮后暗」的闪跳。
    """
    if alpha <= 0.004:
        return
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).text(xy, s, font=font(int(size), weight),
                               fill=color + (int(255 * clamp(alpha)),), anchor=anchor)
    img.paste(Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB"))


def title_block(img, s, sub=None, y=300, size=64, color=INK):
    d = ImageDraw.Draw(img)
    lines = wrap(s, size, W - M * 2, "bold")
    for i, ln in enumerate(lines):
        text(d, (M, y + i * int(size * 1.28)), ln, size, color, "bold")
    yy = y + len(lines) * int(size * 1.28)
    if sub:
        for i, ln in enumerate(wrap(sub, 34, W - M * 2)):
            text(d, (M, yy + 18 + i * 48), ln, 34, DIM)
        yy += 18 + len(wrap(sub, 34, W - M * 2)) * 48
    return yy


def pill(d, x, y, s, fg, bg=None, size=26, pad_x=20, pad_y=10, radius=999):
    tw = measure(s, size, "bold")
    box = [x, y, x + tw + pad_x * 2, y + size + pad_y * 2]
    rrect(d, box, radius, fill=bg)
    text(d, (x + pad_x, y + pad_y), s, size, fg, "bold")
    return box


def card(d, box, fill=(20, 24, 34), outline=(38, 45, 60), radius=20, width=1):
    rrect(d, box, radius, fill=fill, outline=outline, width=width)


# ---------------------------------------------------------------- 场景 1：钩子

def scene_hook(img, t):
    d = ImageDraw.Draw(img)

    # 整块内容垂直居中，且全部落在 y<1200 的安全区里：竖屏信息流底部 35%
    # 被字幕、账号行和操作按钮盖住，落在那里等于没写。
    y0 = 420

    # 第一行在 1.0s 处换成第二行
    # 两行**不能重叠**：同一位置交叉淡出会糊成「比你花的钱单」，
    # 看起来像错别字。先让第一行彻底消失，再出第二行。
    a1 = 1.0 - ease_in_out(norm(t, 0.95, 1.20))
    a2 = ease_in_out(norm(t, 1.20, 1.45))
    if a1 > 0.01:
        _alpha_text(img, (M, y0), "你今年的账单", 46, DIM, "bold", a1)
        d = ImageDraw.Draw(img)
    if a2 > 0.01:
        _alpha_text(img, (M, y0), "比你花的钱", 46, DIM, "bold", a2)
        d = ImageDraw.Draw(img)

    # 「多算了」从 85% 不透明度起步并落定：竖屏首帧就是封面，
    # 交给一个从 0 淡入的空屏等于放弃封面（实测纯黑时 max 通道只有 28）。
    p = 0.85 + 0.15 * ease_out(norm(t, 0.0, 0.9))
    d.text((M, y0 + 90), "多算了", font=font(int(96 * (0.94 + 0.06 * p)), "bold"), fill=BAD)

    # 「6万2」三个字逐个落定。
    # 字号必须**固定**：早期版本让字号随入场进度长大，但字距仍按 190px 量，
    # 结果小字号的字之间裂出肉眼可见的缝（截图 t=0.5 上看得很清楚）。
    # 现在的做法是字号不动，只做向上位移 + 透明度。
    x = M
    for i, ch in enumerate("6万2"):
        k = 0.85 + 0.15 * ease_out(norm(t, i * 0.06, 0.30 + i * 0.06))
        _alpha_text(img, (x, y0 + 210 + (1 - k) * 34), ch, 180, BAD, "bold", k)
        d = ImageDraw.Draw(img)
        x += measure(ch, 180, "bold") + 16

    q = 0.85 + 0.15 * ease_out(norm(t, 0.2, 1.0))
    text(d, (M, y0 + 450), f"¥{human(DELTA)}", int(52 * (0.95 + 0.05 * q)), DIM, "bold")
    d.rectangle([M, y0 + 528, M + int(120 * ease_out(norm(t, 0.2, 1.0))), y0 + 532],
                fill=FAINT)
    lines = wrap("这不是估算。是把同一份账单，用两种算法各跑一遍的差额。",
                 31, W - M * 2)
    for i, ln in enumerate(lines):
        text(d, (M, y0 + 566 + i * 46), ln, 31, FAINT)


# ---------------------------------------------------------------- 场景 2：三条记录

def scene_records(img, t):
    d = ImageDraw.Draw(img)
    y = 400
    text(d, (M, y), "账单里有 24 笔这样的记录", 44, INK, "bold")
    text(d, (M, y + 64), "「收/支」这一列是空的", 32, DIM)

    top = 520
    ch = 172
    gap = 20
    for i, (party, desc, amt, when) in enumerate(NEUTRAL):
        k = ease_out(norm(t, 0.5 + i * 0.45, 1.1 + i * 0.45))
        if k <= 0:
            continue
        by = top + i * (ch + gap) + (1 - k) * 18
        box = [M, by, W - M, by + ch]
        card(d, box)
        # 左侧色条（注意 box = [x0, y0, x1, y1]，别把 x1 当 y0 用）
        d.rectangle([box[0], box[1] + 5, box[0] + 5, box[3] - 5], fill=WARN)
        text(d, (box[0] + 28, box[1] + 26), party, 32, INK, "bold")
        text(d, (box[0] + 28, box[1] + 74), desc, 26, DIM)
        text(d, (box[0] + 28, box[1] + 116), when, 22, FAINT)
        # 金额
        text(d, (box[2] - 26, box[1] + 28), f"¥{amt:,.2f}", 32, INK, "bold", anchor="ra")
        # 「收/支」空单元格
        cw, chh = 100, 48
        cx1 = box[2] - 26
        cbox = [cx1 - cw, box[1] + 98, cx1, box[1] + 98 + chh]
        rrect(d, cbox, 10, fill=(44, 36, 20), outline=WARN, width=2)
        text(d, ((cbox[0] + cbox[2]) / 2, (cbox[1] + cbox[3]) / 2), "空", 26, WARN, "bold", anchor="mm")

    k = ease_out(norm(t, 2.1, 2.8))
    if k > 0:
        yy = top + 3 * (ch + gap) + 26
        text(d, (M, yy), "合计 ¥62,692.46", int(44 * (0.82 + 0.18 * k)), BAD, "bold")
        text(d, (M, yy + 60), "一分钱都没花出去", 28, DIM)


# ---------------------------------------------------------------- 场景 3：算两遍

def scene_math(img, t):
    d = ImageDraw.Draw(img)
    text(d, (M, 210), "同一份账单，算两遍", 44, INK, "bold")

    # 上：错的
    y1 = 330
    a = ease_out(norm(t, 0.2, 1.0))
    if a > 0:
        card(d, [M, y1, W - M, y1 + 196], fill=(28, 20, 22), outline=(64, 34, 38))
        text(d, (M + 28, y1 + 22), "把「不计收支」当支出", 25, BAD, "bold")
        n = int(WRONG * a)
        text(d, (M + 28, y1 + 64), f"¥{human(n)}", 58, BAD, "bold")
        text(d, (M + 28, y1 + 146), "信用卡还款 + 余额宝转入全被算成了消费", 23, DIM)

    # 下：对的
    y2 = 570
    b = ease_out(norm(t, 1.5, 2.4))
    if b > 0:
        card(d, [M, y2, W - M, y2 + 196], fill=(16, 30, 30), outline=(30, 66, 62))
        text(d, (M + 28, y2 + 22), "排除中性交易", 25, ACCENT, "bold")
        n = int(RIGHT * b)
        text(d, (M + 28, y2 + 64), f"¥{human(n)}", 58, ACCENT, "bold")
        text(d, (M + 28, y2 + 146), "钱从你左口袋进右口袋，不是消费", 23, DIM)

    # 差额
    c = ease_out(norm(t, 2.6, 3.4))
    if c > 0:
        yy = 826
        text(d, (M, yy), "差", 32, DIM)
        text(d, (M + 56, yy - 6), f"¥{human(int(DELTA * c))}", int(54 * (0.85 + 0.15 * c)), WARN, "bold")
        text(d, (M, yy + 70), "相当于虚高 34.2%", 28, FAINT)

    # 24 笔的明细：两类各 12 笔，加起来正好是差额
    f = ease_out(norm(t, 3.0, 3.8))
    if f > 0:
        yy = 958
        text(d, (M, yy), "24 笔中性，分成两类", 27, DIM, "bold")
        rows = [
            ("信用卡还款", 12, 46_237.53),
            ("余额宝自动转入", 12, 16_454.93),
        ]
        for i, (name, cnt, amt) in enumerate(rows):
            ry = yy + 50 + i * 56
            text(d, (M, ry), name, 27, INK)
            text(d, (M + 300, ry), f"{cnt} 笔", 25, FAINT)
            text(d, (W - M, ry), f"¥{human(amt)}", 27, WARN, "bold", anchor="ra")

    # 结论条
    e = ease_out(norm(t, 3.4, 4.2))
    if e > 0:
        yy = 1120
        box = [M, yy, W - M, yy + 140]
        card(d, box, fill=(22, 20, 14), outline=(70, 58, 26))
        lines = wrap("几乎所有账单工具都会踩这个坑，因为「收/支」这一列，微信根本没有填。",
                     27, W - M * 2 - 56)
        for i, ln in enumerate(lines):
            text(d, (M + 28, yy + 30 + i * 44), ln, 27, WARN)


# ---------------------------------------------------------------- 场景 4：分类错位

def scene_cats(img, t):
    d = ImageDraw.Draw(img)
    text(d, (M, 210), "还有一处更隐蔽的错", 44, INK, "bold")
    text(d, (M, 272), "两个平台对同一件事，分类不一样", 29, DIM)

    # 对照卡
    y = 350
    k = ease_out(norm(t, 0.4, 1.1))
    if k > 0:
        half = (W - M * 2 - 24) / 2
        for i, (plat, cat, col, desc) in enumerate([
            ("支付宝", "餐饮美食", ACCENT, "星巴克 38.00"),
            ("微信", "商户消费", BLUE, "星巴克 38.00"),
        ]):
            bx = M + i * (half + 24)
            card(d, [bx, y, bx + half, y + 216],
                 fill=(18, 24, 32) if i == 0 else (18, 22, 34))
            text(d, (bx + 24, y + 20), plat, 23, FAINT, "bold")
            text(d, (bx + 24, y + 54), cat, 36, col, "bold")
            text(d, (bx + 24, y + 114), desc, 23, DIM)
            text(d, (bx + 24, y + 156), "同一杯咖啡", 23, FAINT)

    # 我们自己的类目
    y2 = 600
    b = ease_out(norm(t, 1.4, 2.2))
    if b > 0:
        text(d, (M, y2), "所以 BillBook 不用平台自带的分类", 31, INK, "bold")
        text(d, (M, y2 + 50), "改按「交易对方 + 商品说明」重新归成 13 类", 26, DIM)
        y2 += 116

    if b > 0:
        rows = CATS[:6]
        top = rows[0][1]
        for i, (name, amt, share) in enumerate(rows):
            q = ease_out(norm(t, 2.0 + i * 0.14, 2.6 + i * 0.14))
            if q <= 0:
                continue
            yy = y2 + i * 84
            text(d, (M, yy + 6), name, 28, INK)
            bw = (W - M * 2 - 420) * (amt / top) * q
            rrect(d, [M + 140, yy + 10, M + 140 + max(4, bw), yy + 38], 6,
                  fill=mixc(ACCENT, BAD, i / 6.0))
            text(d, (M + 140 + max(4, bw) + 16, yy + 8), f"¥{human(amt)}", 24, DIM)
            text(d, (W - M, yy + 8), f"{share}%", 24, FAINT, anchor="ra")

    # 关键一击：钱不是摊在 1,279 笔上的
    g = ease_out(norm(t, 3.3, 4.2))
    if g > 0:
        yy = 1128
        box = [M, yy, W - M, yy + 196]
        card(d, box, fill=(16, 24, 30), outline=(30, 60, 66))
        text(d, (M + 30, yy + 24), "但真正吃钱的只有两格", 27, ACCENT, "bold")
        # 两行对比
        rows = [
            ("住房 + 数码", "64 笔", 102_874, 56.2, ACCENT),
            ("其余 11 类", "1,215 笔", 80_197, 43.8, (90, 100, 122)),
        ]
        for i, (name, cnt, amt, pctv, col) in enumerate(rows):
            ry = yy + 74 + i * 58
            text(d, (M + 30, ry), name, 26, INK)
            # 笔数右对齐到条形起点左边，避免"1,215 笔"压到条上
            text(d, (M + 30 + 250, ry), cnt, 24, FAINT, anchor="ra")
            bar_w = 168 * (pctv / 56.2)
            rrect(d, [M + 30 + 272, ry + 6, M + 30 + 272 + max(5, bar_w * g), ry + 26],
                  5, fill=col)
            text(d, (W - M - 30, ry), f"¥{human(amt)}", 26, col, "bold", anchor="ra")


def mixc(a, b, k):
    k = clamp(k, 0, 1)
    return tuple(int(a[i] * (1 - k) + b[i] * k) for i in range(3))


# ---------------------------------------------------------------- 场景 5：结尾卡

def scene_card(img, t):
    d = ImageDraw.Draw(img)
    p = ease_out(norm(t, 0.3, 1.2))

    glow_text(img, (M - 6, 440), "BillBook", int(112 * (0.92 + 0.08 * p)), INK, "bold")
    d = ImageDraw.Draw(img)

    k = ease_out(norm(t, 0.8, 1.6))
    if k > 0:
        text(d, (M, 606), "把账单算对", max(1, int(44 * k)), ACCENT, "bold")

    lines = [
        ("支付宝 CSV + 微信 XLSX", "一个命令，两个平台混着读"),
        ("13 类消费，自己归类", "不看平台心情"),
        ("单文件 HTML 年报", "离线打开，不发网络请求"),
    ]
    for i, (a, b) in enumerate(lines):
        q = ease_out(norm(t, 1.4 + i * 0.22, 2.1 + i * 0.22))
        if q <= 0:
            continue
        yy = 726 + i * 112
        d.ellipse([M, yy + 12, M + 10, yy + 22], fill=ACCENT)
        text(d, (M + 28, yy), a, 31, INK, "bold")
        text(d, (M + 28, yy + 42), b, 25, DIM)

    q = ease_out(norm(t, 2.4, 3.2))
    if q > 0:
        box = [M, 1104, W - M, 1206]
        rrect(d, box, 18, fill=(16, 20, 28), outline=(40, 48, 64), width=2)
        text(d, (M + 30, 1132), "python -m billbook 账单.csv", 30, ACCENT, "bold")

    if q > 0.5:
        text(d, (M, 1246), "数据只留在你这台电脑上", 25, FAINT)


# ---------------------------------------------------------------- 时间轴

SCENES = [
    (0.0, 4.8, scene_hook),
    (4.8, 12.6, scene_records),
    (12.6, 21.4, scene_math),
    (21.4, 30.8, scene_cats),
    (30.8, DUR, scene_card),
]


def draw(t: float):
    img = background(W, H).convert("RGB")
    for i, (a, b, fn) in enumerate(SCENES):
        if not (a <= t < b):
            continue
        lt = t - a
        span = b - a
        # 场景内淡入淡出
        # 第一个场景完全不做淡入：竖屏信息流里第 0 帧就是封面，
        # 淡入等于交出去一张纯黑图（实测 max 通道值 28）。
        alpha = 1.0 if i == 0 else (lt / 0.14 if lt < 0.14 else 1.0)
        # 只保留 0.14s 的淡入，不做淡出 —— 硬切。原来的 0.30s 淡出
        # 会在每个切点留下一段接近全暗的空屏，短片节奏全被吃掉。
        alpha = clamp(alpha)

        if alpha >= 0.999:
            fn(img, lt)
        else:
            layer = img.copy()
            fn(layer, lt)
            img = Image.blend(img, layer, alpha)
        break
    return img


def main():
    args = sys.argv[1:]
    if args and args[0] == "stills":
        from video.kit import run
        ts = [float(x) for x in args[1:]] or [1.0, 6.0, 14.0, 24.0, 33.0]
        paths = run(draw, "out/v1", DUR, stills=ts)
        print("\n".join(str(p) for p in paths))
    else:
        from video.kit import run
        out = "out/v1-billbook.mp4"
        run(draw, out, DUR)
        print(f"wrote {out}")


if __name__ == "__main__":
    main()
