"""BillBook 视频 2 ——《你的钱有作息》

审计一年 1,279 笔消费的时间戳，能还原出一个人的生活。
所有数字来自 demo 账单实算：

  328 天里有消费         → 一天都没断过，最长连续 29 天
  12:00 208 笔 / 18:00 248 笔 → 一年只有两个时刻你在花钱
  00:03 唯一一笔凌晨消费 → 双 11 的显示器
  每月 1 号 09:12        → 51 笔 66,414 元，36% 的钱在 1 号走掉
  中位数 25 元 vs 最大 14,999 元 → 差 597 倍

时长 42s，1080x1920，30fps。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageDraw  # noqa: E402

from video.kit import (  # noqa: E402
    ACCENT, BAD, BG, BG2, BLUE, DIM, FAINT, INK, PINK, WARN,
    Video, background, clamp, ease_in_out, ease_out, ease_out_back,
    fmt_int, font, glow_text, measure, norm, rrect, text, wrap,
)

W, H = 1080, 1920
M = 88
DUR = 42.0

# ---------------------------------------------------------------- 数据

HOUR_CNT = [1, 0, 0, 0, 0, 0, 0, 1, 107, 128, 12, 112, 208, 117, 1, 0,
            0, 0, 248, 116, 131, 94, 3, 0]
HOUR_AMT = [2799, 0, 0, 0, 0, 0, 0, 2480, 8948, 68365, 3703, 9001, 14261,
            8744, 3860, 0, 0, 0, 19825, 10168, 7549, 22365, 1002, 0]

DAYS = 328
STREAK = 29
MEDIAN = 25.13
BIGGEST = 14999.0
JAN1_CNT = 51
JAN1_AMT = 66414
JAN1_SHARE = 36.3

LATE = ("2025-11-11 00:03", "京东商城", "双11 显示器", 2799.0)

RENT = ("链家地产", "房租", 5200.0, "每月 1 号 09:12", 12)


def _alpha_text(img, xy, s, size, color, weight="bold", alpha=1.0, anchor="la"):
    if alpha <= 0.004:
        return
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).text(xy, s, font=font(max(1, int(size)), weight),
                               fill=color + (int(255 * clamp(alpha)),), anchor=anchor)
    img.paste(Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB"))


def card(d, box, fill=(20, 24, 34), outline=(38, 45, 60), radius=20, width=1):
    rrect(d, box, radius, fill=fill, outline=outline, width=width)


def human(v: float) -> str:
    return f"{v:,.0f}"


# ---------------------------------------------------------------- 场景 1：钩子

def scene_hook(img, t):
    d = ImageDraw.Draw(img)
    y0 = 340

    # 首帧就是封面：第 0 帧必须能完整读出结论，不能是计数动画的中间值
    # （早一版第一帧停在「180 天」，既不是真数也不像话）。
    k = 0.85 + 0.15 * ease_out(norm(t, 0.0, 0.9))
    _alpha_text(img, (M, y0), "你的账单里", 42, DIM, "bold", k)
    d = ImageDraw.Draw(img)

    text(d, (M, y0 + 76), f"{DAYS} 天", 140, INK, "bold")
    text(d, (M, y0 + 268), "有消费记录", 44, ACCENT, "bold")

    # 362 天的账单里只有 34 天一分没花 —— 说「一天都没断过」是假的，
    # 数字对不上就整个视频不可信了。
    k4 = ease_out(norm(t, 0.9, 1.9))
    if k4 > 0:
        text(d, (M, y0 + 360), f"全年 362 天，只有 {362 - DAYS} 天没花钱", 31, FAINT)
    k5 = ease_out(norm(t, 1.7, 2.6))
    if k5 > 0:
        text(d, (M, y0 + 412), f"最长连续 {STREAK} 天，天天有支出", 31, FAINT)


# ---------------------------------------------------------------- 场景 2：双峰

def scene_hours(img, t):
    d = ImageDraw.Draw(img)
    text(d, (M, 250), "一年 1,279 笔，只落在几个时刻", 41, INK, "bold")
    text(d, (M, 312), "按小时分开看", 29, DIM)

    # 图表区
    gx, gy = M, 470
    gw, gh = W - M * 2, 460
    base = gy + gh
    top = max(HOUR_CNT)

    # 网格
    for i in range(5):
        yy = int(base - gh * i / 4)
        d.rectangle([gx, yy, gx + gw, yy + 1], fill=(26, 31, 42))
        if i:
            text(d, (gx - 12, yy), str(int(top * i / 4)), 20, FAINT, anchor="ra")

    step = gw / 24
    bw = step * 0.62

    # 峰值标注
    peaks = {12: "午饭", 18: "下班"}
    draw_p = ease_out(norm(t, 0.5, 2.6))

    for h in range(24):
        v = HOUR_CNT[h]
        q = ease_out(norm(t, 0.35 + h * 0.045, 0.75 + h * 0.045))
        hh = gh * (v / top) * q
        if v and hh < 3:
            hh = 3
        x = gx + h * step + (step - bw) / 2
        is_peak = h in peaks
        col = ACCENT if is_peak else (58, 70, 92)
        if is_peak:
            col = ACCENT
        elif v:
            col = (72, 86, 112)
        if hh > 0:
            rrect(d, [x, base - hh, x + bw, base], 4, fill=col)
        # 小时标签（每 3 小时）
        if h % 3 == 0:
            text(d, (x + bw / 2, base + 14), str(h), 22, FAINT, anchor="ma")

    # 峰值气泡
    for h, label in peaks.items():
        q = ease_out(norm(t, 1.6 + (0.35 if h > 12 else 0), 2.3 + (0.35 if h > 12 else 0)))
        if q <= 0:
            continue
        x = gx + h * step + step / 2
        hh = gh * (HOUR_CNT[h] / top)
        by = base - hh - 70
        d.line([x, base - hh - 6, x, by + 26], fill=ACCENT, width=2)
        label_s = f"{HOUR_CNT[h]} 笔 · {label}"
        tw = measure(label_s, 24, "bold")
        box = [x - tw / 2 - 16, by - 6, x + tw / 2 + 16, by + 34]
        rrect(d, box, 10, fill=(14, 40, 38), outline=(40, 96, 88), width=1)
        text(d, (x, by + 5), label_s, 24, ACCENT, "bold", anchor="ma")

    # 结论
    k = ease_out(norm(t, 3.0, 3.9))
    if k > 0:
        yy = 1032
        text(d, (M, yy), "24 小时里，你有 10 个小时一分钱不花", max(1, int(33 * k)), INK, "bold")
        text(d, (M, yy + 52), "花的钱集中在 12 点和 18 点前后", 27, FAINT)


# ---------------------------------------------------------------- 场景 3：凌晨那一笔

def scene_late(img, t):
    d = ImageDraw.Draw(img)
    text(d, (M, 250), "但有一笔，落在所有人都在睡的时候", 38, INK, "bold")
    text(d, (M, 306), "00:00 — 07:00", 27, FAINT)

    # 夜间时间轴：横线在 y=700，柱子从线上长出来
    ty = 700
    d.rectangle([M, ty, W - M, ty + 2], fill=(40, 48, 64))
    for h in range(0, 8):
        x = M + (W - M * 2) * h / 7
        d.rectangle([x, ty - 6, x + 1, ty + 8], fill=(56, 66, 86))
        text(d, (x, ty + 20), f"{h}:00", 22, FAINT, anchor="ma")

    # 00:03 那一根（x 位置按分钟算，不是按小时）
    k = ease_out_back(norm(t, 0.8, 1.6))
    if k > 0:
        x = M + (W - M * 2) * (3 / 60) / 7
        hgt = 300 * k
        d.rectangle([x - 8, ty - hgt, x + 8, ty], fill=PINK)
        # 顶上一个圆点收尾
        r = int(9 * k)
        if r > 0:
            d.ellipse([x - r, ty - hgt - r * 2, x + r, ty - hgt], fill=PINK)
        g = ease_out(norm(t, 1.3, 2.1))
        if g > 0.01:
            _alpha_text(img, (x + 30, ty - hgt - 40), f"¥{human(LATE[3])}", 52, PINK, "bold", g)
            d = ImageDraw.Draw(img)

    # 明细卡
    k2 = ease_out(norm(t, 2.0, 2.9))
    if k2 > 0:
        yy = ty + 88 + (1 - k2) * 20
        card(d, [M, yy, W - M, yy + 186], fill=(30, 20, 30), outline=(72, 40, 66))
        # 左侧色条
        d.rectangle([M, yy + 6, M + 5, yy + 180], fill=PINK)
        text(d, (M + 28, yy + 22), LATE[0], 24, FAINT)
        text(d, (M + 28, yy + 60), LATE[1], 34, INK, "bold")
        text(d, (M + 28, yy + 112), LATE[2], 27, DIM)
        text(d, (W - M - 28, yy + 62), f"¥{human(LATE[3])}", 34, PINK, "bold", anchor="ra")

    k3 = ease_out(norm(t, 3.0, 3.9))
    if k3 > 0.01:
        _alpha_text(img, (M, 1024), "一年 1,279 笔，只有这一笔在天亮前", 29, ACCENT, "bold", k3)
        d = ImageDraw.Draw(img)
        _alpha_text(img, (M, 1076), "双 11 零点，你盯着购物车", 29, FAINT, "regular", k3)


# ---------------------------------------------------------------- 场景 4：1 号

def scene_first(img, t):
    d = ImageDraw.Draw(img)
    text(d, (M, 250), "还有一天，你根本没动过手", 38, INK, "bold")
    text(d, (M, 306), "每月 1 号，09:12，房租自动扣走 5,200", 27, DIM)

    # 一条按天切的钱：1 号 / 其余 30 天
    bx, by, bw, bh = M, 424, W - M * 2, 80
    rrect(d, [bx, by, bx + bw, by + bh], 12, fill=(24, 29, 40))
    k = ease_in_out(norm(t, 0.5, 1.8))
    fw = (bw - 8) * 0.363 * k
    if fw > 6:
        rrect(d, [bx + 4, by + 4, bx + 4 + fw, by + bh - 4], 10, fill=ACCENT)
    # 分割线
    if k > 0.99:
        sx = bx + 4 + (bw - 8) * 0.363
        d.rectangle([sx, by + 10, sx + 2, by + bh - 10], fill=(10, 12, 17))

    k2 = ease_out(norm(t, 1.2, 2.0))
    if k2 > 0.01:
        _alpha_text(img, (bx + 4 + 22, by + 24), "1 号", 29, (8, 14, 16), "bold", k2)
        d = ImageDraw.Draw(img)
        _alpha_text(img, (bx + 4 + (bw - 8) * 0.363 + 22, by + 24), "其余 30 天", 29, DIM, "bold", k2)
        d = ImageDraw.Draw(img)

    # 两个数
    k3 = ease_out(norm(t, 1.8, 2.7))
    if k3 > 0:
        yy = 570
        text(d, (M, yy), "每月 1 号的合计", 25, FAINT, "bold")
        text(d, (M, yy + 42), f"¥{human(int(JAN1_AMT * k3))}", 76, ACCENT, "bold")
        text(d, (M, yy + 142), f"{int(JAN1_CNT * k3)} 笔 · 占全年支出的 {JAN1_SHARE}%", 27, DIM)

    # 什么在这天扣
    k4 = ease_out(norm(t, 2.6, 3.5))
    if k4 > 0:
        yy = 812
        # 只列真实存在的：1 号那 51 笔里，12 笔是房租，其余 39 笔是当天
        # 顺手花的地铁/外卖/咖啡。宽带和话费并不在 1 号扣，不能编进去。
        rows = [
            ("链家地产", "12 笔 × 5,200", 62_400),
            ("其余 39 笔", "地铁 8 · 滴滴 7 · 外卖 5", 4_014),
        ]
        for i, (name, meta, amt) in enumerate(rows):
            q = ease_out(norm(t, 2.7 + i * 0.12, 3.2 + i * 0.12))
            if q <= 0:
                continue
            ry = yy + i * 74 + (1 - q) * 12
            text(d, (M, ry), name, 27, INK)
            text(d, (M + 320, ry + 4), meta, 22, FAINT)
            text(d, (W - M, ry), f"¥{human(amt)}", 27, WARN, "bold", anchor="ra")
            d.rectangle([M, ry + 48, W - M, ry + 49], fill=(24, 29, 40))

    k5 = ease_out(norm(t, 3.6, 4.4))
    if k5 > 0.01:
        _alpha_text(img, (M, 1046), "你可能不记得这笔钱", 29, FAINT, "regular", k5)
        d = ImageDraw.Draw(img)
        _alpha_text(img, (M, 1098), "但账单记得每一次", 29, ACCENT, "bold", k5)


# ---------------------------------------------------------------- 场景 5：中位数

def scene_median(img, t):
    d = ImageDraw.Draw(img)
    text(d, (M, 250), "最后看一眼，你的钱有多大", 38, INK, "bold")

    # 两个数字并排
    k = ease_out(norm(t, 0.4, 1.3))
    if k > 0:
        text(d, (M, 356), "中位数", 25, FAINT, "bold")
        text(d, (M, 400), f"¥{MEDIAN:.0f}", 88, INK, "bold")
        text(d, (M, 518), "一半的消费，不到 26 块", 25, DIM)

    k2 = ease_out(norm(t, 1.3, 2.2))
    if k2 > 0:
        text(d, (M, 612), "最大一笔", 25, FAINT, "bold")
        text(d, (M, 656), f"¥{human(BIGGEST)}", 88, BAD, "bold")
        text(d, (M, 774), "Apple Store，4 月 18 日", 25, DIM)

    # 倍数
    k3 = ease_out_back(norm(t, 2.3, 3.2))
    if k3 > 0:
        yy = 872
        text(d, (M, yy), "相差", 29, DIM)
        text(d, (M + 74, yy - 16), "597 倍", int(82 * (0.9 + 0.1 * k3)), WARN, "bold")

    k4 = ease_out(norm(t, 3.2, 4.0))
    if k4 > 0:
        # 卡片高度跟行数走，别留一大块空白
        lines = wrap("所以「我一年花了多少钱」这个数字，几乎不描述你平时怎么生活。",
                     27, W - M * 2 - 58)
        ch = 32 + len(lines) * 44 + 22
        yy = 986
        card(d, [M, yy, W - M, yy + ch], fill=(18, 24, 32), outline=(32, 44, 58))
        d.rectangle([M, yy + 6, M + 5, yy + ch - 6], fill=ACCENT)
        for i, ln in enumerate(lines):
            text(d, (M + 30, yy + 30 + i * 44), ln, 27, DIM)


# ---------------------------------------------------------------- 场景 6：结尾

def scene_card(img, t):
    d = ImageDraw.Draw(img)
    p = ease_out(norm(t, 0.3, 1.2))
    glow_text(img, (M - 6, 420), "BillBook", int(112 * (0.92 + 0.08 * p)), INK, "bold")
    d = ImageDraw.Draw(img)

    k = ease_out(norm(t, 0.8, 1.6))
    if k > 0.01:
        _alpha_text(img, (M, 586), "账单不只是钱，是作息", 42, ACCENT, "bold", k)
        d = ImageDraw.Draw(img)

    lines = [
        ("按小时看", "知道自己几点在花钱"),
        ("按日期看", "知道哪几天是自动扣的"),
        ("异常自动挑出来", "不用自己翻 1,279 行"),
    ]
    for i, (a, b) in enumerate(lines):
        q = ease_out(norm(t, 1.4 + i * 0.22, 2.1 + i * 0.22))
        if q <= 0:
            continue
        yy = 704 + i * 110
        d.ellipse([M, yy + 12, M + 10, yy + 22], fill=ACCENT)
        text(d, (M + 28, yy), a, 31, INK, "bold")
        text(d, (M + 28, yy + 42), b, 25, DIM)

    q = ease_out(norm(t, 2.4, 3.2))
    if q > 0:
        rrect(d, [M, 1074, W - M, 1180], 18, fill=(16, 20, 28),
              outline=(40, 48, 64), width=2)
        text(d, (M + 30, 1104), "python -m billbook 账单.csv", 30, ACCENT, "bold")

    if q > 0.5:
        text(d, (M, 1222), "数据只留在你这台电脑上", 25, FAINT)


# ---------------------------------------------------------------- 时间轴

SCENES = [
    (0.0, 5.2, scene_hook),
    (5.2, 13.6, scene_hours),
    (13.6, 21.0, scene_late),
    (21.0, 29.4, scene_first),
    (29.4, 36.4, scene_median),
    (36.4, DUR, scene_card),
]


def draw(t: float):
    img = background(W, H).convert("RGB")
    for a, b, fn in SCENES:
        if not (a <= t < b):
            continue
        lt = t - a
        span = b - a
        # 首个场景不做淡入：竖屏信息流里第 0 帧就是封面，
        # 淡入等于交出去一张纯黑图（实测 max 通道值 28）。
        alpha = 1.0 if a == 0.0 else (lt / 0.14 if lt < 0.14 else 1.0)
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
    from video.kit import run
    if args and args[0] == "stills":
        ts = [float(x) for x in args[1:]] or [1.0, 8.0, 17.0, 26.0, 33.0, 40.0]
        paths = run(draw, "out/v2", DUR, stills=ts)
        print("\n".join(str(p) for p in paths))
    else:
        out = "out/v2-rhythm.mp4"
        run(draw, out, DUR)
        print(f"wrote {out}")


if __name__ == "__main__":
    main()
