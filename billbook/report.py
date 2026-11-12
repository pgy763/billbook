"""年度报告：输出一个自包含的 HTML，双击就能看。

图表全部在 Python 里算好、拼成内联 SVG 写进 HTML，页面不需要任何网络请求，
也不依赖 JS 绘图库 —— 这样可以离线发给人看，也可以直接打印成 PDF。
页面上的 JS 只做三件事：滚动淡入、数字滚动、点击高亮。
"""

from __future__ import annotations

import html
import os
from datetime import date, datetime

from . import categorize, stats as stats_mod

# ---------------------------------------------------------------- 颜色

BG = "#0a0c11"
PANEL = "#111420"
LINE = "#1e2430"
INK = "#e8ecf4"
DIM = "#8b93a7"
FAINT = "#5f6779"
ACCENT = "#5eead4"
WARN = "#fbbf24"
BAD = "#f87171"

WEEK = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def money(v: float, sign: bool = False) -> str:
    s = f"{v:,.0f}"
    return ("+" if sign and v > 0 else "") + s


def money2(v: float) -> str:
    return f"{v:,.2f}"


def wan(v: float) -> str:
    return f"{v / 10000:.1f} 万"


def pct(v: float, digits: int = 1) -> str:
    return f"{v * 100:.{digits}f}%"


# ---------------------------------------------------------------- 图表

def svg_monthly(st: stats_mod.Stats, w=980, h=300) -> str:
    """月度支出柱 + 月收入折线。柱状比折线更容易看出「哪个月失控了」。"""
    pad_l, pad_r, pad_t, pad_b = 54, 16, 22, 40
    iw, ih = w - pad_l - pad_r, h - pad_t - pad_b
    vals = st.monthly
    hi = max(vals + st.monthly_in + [1])
    step = iw / 12.0
    bw = step * 0.52

    parts = [f'<svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-label="每月支出与收入">']
    # 网格
    for i in range(5):
        y = pad_t + ih - ih * i / 4
        parts.append(
            f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w - pad_r}" y2="{y:.1f}" '
            f'stroke="{LINE}" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{pad_l - 10:.1f}" y="{y + 4:.1f}" text-anchor="end" '
            f'font-size="11" fill="{FAINT}">{money(hi * i / 4)}</text>'
        )

    # 柱
    for i, v in enumerate(vals):
        bh = ih * (v / hi) if hi else 0
        x = pad_l + step * i + (step - bw) / 2
        y = pad_t + ih - bh
        op = 0.42 + 0.5 * (v / hi if hi else 0)
        parts.append(
            f'<rect class="bar" x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" '
            f'height="{max(0, bh):.1f}" rx="3" fill="{ACCENT}" opacity="{op:.2f}">'
            f'<title>{i + 1} 月 支出 ¥{money(v)}</title></rect>'
        )
        parts.append(
            f'<text x="{x + bw / 2:.1f}" y="{h - pad_b + 18}" text-anchor="middle" '
            f'font-size="11" fill="{DIM}">{i + 1}</text>'
        )

    # 收入折线
    pts = []
    for i, v in enumerate(st.monthly_in):
        x = pad_l + step * i + step / 2
        y = pad_t + ih - ih * (v / hi if hi else 0)
        pts.append(f"{x:.1f},{y:.1f}")
    if pts:
        parts.append(
            f'<polyline points="{" ".join(pts)}" fill="none" stroke="{WARN}" '
            f'stroke-width="2" stroke-linejoin="round" opacity=".85"/>'
        )
        for i, v in enumerate(st.monthly_in):
            if v <= 0:
                continue
            x = pad_l + step * i + step / 2
            y = pad_t + ih - ih * (v / hi if hi else 0)
            parts.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{WARN}">'
                f'<title>{i + 1} 月 收入 ¥{money(v)}</title></circle>'
            )
    parts.append("</svg>")
    return "".join(parts)


def svg_heat(matrix: list[list[float]], w=980, h=250) -> str:
    """matrix[weekday][hour] 金额矩阵 → 热力方块图。"""
    pad_l, pad_t = 58, 20
    cols, rws = 24, 7
    cw = (w - pad_l - 12) / cols
    ch = (h - pad_t - 26) / rws
    hi = max((v for r in matrix for v in r), default=0) or 1

    parts = [f'<svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-label="消费时段热力图">']
    for hh in range(0, 24, 3):
        x = pad_l + cw * hh
        parts.append(
            f'<text x="{x:.1f}" y="{h - 8}" font-size="11" fill="{FAINT}">{hh}时</text>'
        )
    for wd in range(rws):
        y = pad_t + ch * wd
        parts.append(
            f'<text x="{pad_l - 12:.1f}" y="{y + ch / 2 + 4:.1f}" text-anchor="end" '
            f'font-size="11" fill="{DIM}">{WEEK[wd]}</text>'
        )
        for hh in range(cols):
            v = matrix[wd][hh]
            t = v / hi
            # 空单元不画，否则整张图看起来像一块纹理地毯
            if v <= 0:
                parts.append(
                    f'<rect x="{pad_l + cw * hh + 1:.1f}" y="{y + 1:.1f}" '
                    f'width="{cw - 2:.1f}" height="{ch - 2:.1f}" rx="2" fill="{LINE}" opacity=".45"/>'
                )
                continue
            op = 0.16 + 0.84 * (t ** 0.55)
            parts.append(
                f'<rect x="{pad_l + cw * hh + 1:.1f}" y="{y + 1:.1f}" '
                f'width="{cw - 2:.1f}" height="{ch - 2:.1f}" rx="2" fill="{ACCENT}" '
                f'opacity="{op:.2f}"><title>{WEEK[wd]} {hh}:00 前后 ¥{money(v)}</title></rect>'
            )
    parts.append("</svg>")
    return "".join(parts)


def bars_categories(cats, w=980) -> str:
    """类目横条。比饼图好：能直接读数值，且类目多时不挤。"""
    if not cats:
        return ""
    hi = max(a for _, a, _, _ in cats) or 1
    row_h, gap = 34, 12
    h = len(cats) * (row_h + gap)
    parts = [f'<svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-label="消费分类">']
    for i, (name, amt, cnt, share) in enumerate(cats):
        y = i * (row_h + gap)
        col = categorize.CAT_COLOR.get(name, "#475569")
        bw = (w - 210) * (amt / hi)
        parts.append(
            f'<text x="0" y="{y + 21}" font-size="14" fill="{INK}">{esc(name)}</text>'
        )
        parts.append(
            f'<rect x="86" y="{y + 6}" width="{max(2, bw):.1f}" height="{row_h - 8}" '
            f'rx="4" fill="{col}" opacity=".9"><title>{esc(name)} ¥{money(amt)}</title></rect>'
        )
        parts.append(
            f'<text x="{86 + max(2, bw) + 10:.1f}" y="{y + 21}" font-size="12.5" fill="{DIM}">'
            f'¥{money(amt)} · {pct(share)}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def bars_merchants(rows, w=980, n=10) -> str:
    rows = rows[:n]
    if not rows:
        return ""
    hi = rows[0][1] or 1
    row_h = 30
    h = len(rows) * row_h + 8
    parts = [f'<svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-label="商家排行">']
    for i, (name, amt, cnt) in enumerate(rows):
        y = i * row_h + 4
        bw = (w - 330) * (amt / hi)
        parts.append(f'<text x="0" y="{y + 15}" font-size="12.5" fill="{DIM}">{i + 1:02d}</text>')
        label = name if len(name) <= 14 else name[:13] + "…"
        parts.append(f'<text x="26" y="{y + 15}" font-size="13" fill="{INK}">{esc(label)}</text>')
        parts.append(
            f'<rect x="180" y="{y + 4}" width="{max(2, bw):.1f}" height="12" rx="3" '
            f'fill="{ACCENT}" opacity=".55"><title>{esc(name)}</title></rect>'
        )
        parts.append(
            f'<text x="{w - 96}" y="{y + 15}" font-size="12.5" fill="{INK}" text-anchor="end">'
            f'¥{money(amt)}</text>'
        )
        parts.append(
            f'<text x="{w}" y="{y + 15}" font-size="11.5" fill="{FAINT}" text-anchor="end">'
            f'{cnt} 笔</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def svg_calendar(day_totals: dict, year: int, w=980) -> str:
    """一年一张日历网格。每个月的空白列保留，位置才认得出是几月。"""
    cols = 53
    rows = 7
    cell = (w - 30) / cols
    h = rows * cell + 26
    hi = max(day_totals.values(), default=0) or 1
    first = date(year, 1, 1)
    offset = first.weekday()

    parts = [f'<svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-label="全年消费日历">']
    for m in range(1, 13):
        d = date(year, m, 1)
        idx = (d - first).days + offset
        col = idx // 7
        x = col * cell
        parts.append(
            f'<text x="{x:.1f}" y="{h - 6}" font-size="10" fill="{FAINT}">{m}月</text>'
        )
    for day, v in day_totals.items():
        idx = (day - first).days + offset
        col, row = divmod(idx, 7)
        x, y = col * cell, row * cell
        t = (v / hi) ** 0.55
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{cell - 1.6:.1f}" height="{cell - 1.6:.1f}" '
            f'rx="1.6" fill="{ACCENT}" opacity="{0.10 + 0.88 * t:.2f}"><title>'
            f'{day.isoformat()} ¥{money(v)}</title></rect>'
        )
    parts.append("</svg>")
    return "".join(parts)


# ---------------------------------------------------------------- 文案生成

def persona(st: stats_mod.Stats) -> tuple[str, str]:
    """根据数据给一个「消费人格」。不是随机贴标签，是按最显著的统计特征选。"""
    cats = {c: s for c, _, _, s in st.cats}
    per_day = st.total_expense / max(1, st.days)
    food = cats.get("餐饮", 0)
    shop = cats.get("购物", 0)
    traffic = cats.get("交通", 0)
    digital = cats.get("数码", 0)
    sub = cats.get("会员订阅", 0)
    house = cats.get("住房", 0)

    if house >= 0.30:
        return "房奴型", "三分之一以上的钱给了房子，剩下的每一笔都在精打细算。"
    if digital >= 0.15:
        return "装备党", "钱花在能跑分的东西上。你对硬件参数的熟悉程度超过对自己胃口的了解。"
    if sub >= 0.05:
        return "订阅收藏家", "每个月的自动续费加起来是一笔真金白银。你可能已经忘了其中两个。"
    if food >= 0.20:
        return "干饭人", "一天三顿都在付钱，餐饮是第一大支出。外卖平台的会员你应该是开着的。"
    if shop >= 0.22:
        return "剁手党", "购物占比最高。快递员认识你家门，比物业还熟。"
    if traffic >= 0.18:
        return "在路上", "交通支出排在前列。这一年你移动的距离，可能比很多人一年走的路都长。"
    if per_day < 300:
        return "省钱模式", f"日均 {money(per_day)} 元，这一年你过得很克制。"
    return "平稳型", "没有极端偏好，各项支出分布均匀 —— 这在统计上其实很少见。"


def fun_facts(st: stats_mod.Stats, records) -> list[tuple[str, str]]:
    out = []
    per_day = st.total_expense / max(1, st.days)
    out.append(("日均消费", f"¥{money(per_day)}"))
    out.append(("中位数单笔", f"¥{money2(st.median)}"))
    if st.count_expense:
        out.append(("每天平均笔数", f"{st.count_expense / max(1, st.days):.1f} 笔"))
    if st.merchants:
        out.append(("最常去的商家", st.merchants[0][0]))
    # 最贵的一杯咖啡 / 一份饭之类的对比没有数据支撑，宁可不下结论
    sat = max(range(7), key=lambda i: st.weekday[i]) if st.total_expense else 0
    out.append(("花钱最多的星期", WEEK[sat]))
    peak = max(range(12), key=lambda i: st.monthly[i]) if st.total_expense else 0
    out.append(("花钱最多的月份", f"{peak + 1} 月"))
    save_rate = 1 - (st.total_expense / st.total_income) if st.total_income else 0
    out.append(("结余率", pct(save_rate)))
    return out


# ---------------------------------------------------------------- 模板

CSS = f"""
:root{{
  --bg:{BG}; --panel:{PANEL}; --line:{LINE}; --ink:{INK}; --dim:{DIM};
  --faint:{FAINT}; --accent:{ACCENT}; --warn:{WARN}; --bad:{BAD};
}}
*{{box-sizing:border-box}}
html,body{{margin:0;padding:0;background:var(--bg);color:var(--ink)}}
body{{
  font-family:"Microsoft YaHei","PingFang SC","Hiragino Sans GB",-apple-system,sans-serif;
  -webkit-font-smoothing:antialiased; line-height:1.6;
}}
.wrap{{max-width:1120px;margin:0 auto;padding:0 40px}}
section{{padding:68px 0;border-top:1px solid var(--line)}}
section:first-of-type{{border-top:none}}
h2{{font-size:13px;font-weight:600;color:var(--faint);letter-spacing:.14em;
   text-transform:uppercase;margin:0 0 26px}}
.chart{{width:100%;height:auto;display:block;overflow:visible}}
.hero{{padding:110px 0 84px;border-top:none}}
.hero .year{{font-size:15px;color:var(--faint);letter-spacing:.3em;margin-bottom:22px}}
.hero .big{{font-size:clamp(54px,9vw,104px);font-weight:700;letter-spacing:-.03em;
  line-height:1.02;margin:0}}
.hero .big .unit{{font-size:.36em;font-weight:600;color:var(--dim);margin-left:.14em;
  letter-spacing:0}}
.hero .sub{{margin-top:26px;font-size:17px;color:var(--dim);max-width:640px}}
.hero .sub b{{color:var(--ink);font-weight:600}}
.kpi{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:14px;
  margin-top:52px}}
.kpi .cell{{background:var(--panel);border:1px solid var(--line);border-radius:12px;
  padding:18px 20px}}
.kpi .k{{font-size:11.5px;color:var(--faint);letter-spacing:.06em}}
.kpi .v{{font-size:23px;font-weight:700;margin-top:6px;letter-spacing:-.01em}}
.legend{{display:flex;gap:22px;flex-wrap:wrap;margin-top:14px;font-size:12px;color:var(--dim)}}
.legend i{{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:6px}}
table{{width:100%;border-collapse:collapse;font-size:13.5px}}
th{{text-align:left;font-size:11px;color:var(--faint);letter-spacing:.08em;font-weight:600;
  padding:0 10px 10px;border-bottom:1px solid var(--line)}}
th.r,td.r{{text-align:right}}
td{{padding:11px 10px;border-bottom:1px solid rgba(30,36,48,.6);color:var(--ink)}}
td.m{{color:var(--dim)}}
.tag{{display:inline-block;font-size:11px;padding:2px 8px;border-radius:999px;
  background:rgba(94,234,212,.12);color:var(--accent)}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:40px}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:26px 28px}}
.card .name{{font-size:12px;color:var(--faint);letter-spacing:.1em}}
.card .title{{font-size:30px;font-weight:700;margin:8px 0 10px;letter-spacing:-.01em}}
.card .desc{{font-size:14px;color:var(--dim);line-height:1.75}}
.anom{{border-left:3px solid var(--bad);padding:2px 0 2px 16px;margin:18px 0}}
.anom .t{{font-size:14.5px;font-weight:600}}
.anom .d{{font-size:12.5px;color:var(--dim);margin-top:3px}}
footer{{padding:56px 0 80px;border-top:1px solid var(--line);color:var(--faint);font-size:12.5px}}
.reveal{{opacity:0;transform:translateY(14px);transition:opacity .6s ease,transform .6s ease}}
.reveal.on{{opacity:1;transform:none}}
@media print{{
  body{{background:#fff;color:#111}}
  section{{border-color:#ddd;page-break-inside:avoid}}
  .card,.kpi .cell{{background:#f7f7f8;border-color:#e0e0e0}}
  .reveal{{opacity:1;transform:none}}
}}
@media (max-width:760px){{
  .wrap{{padding:0 20px}}
  .grid2{{grid-template-columns:1fr;gap:22px}}
  section{{padding:48px 0}}
}}
"""

JS = """
const io = new IntersectionObserver((es)=>{
  for(const e of es){ if(e.isIntersecting){ e.target.classList.add('on'); io.unobserve(e.target); } }
},{threshold:.08});
document.querySelectorAll('.reveal').forEach(n=>io.observe(n));
// 数字从 0 滚到大数字，纯装饰但会让首屏有「在算」的感觉
document.querySelectorAll('[data-count]').forEach(n=>{
  const target = parseFloat(n.dataset.count);
  const dec = parseInt(n.dataset.dec||'0',10);
  const dur = 900; const t0 = performance.now();
  const fmt = v => v.toLocaleString('zh-CN',{minimumFractionDigits:dec,maximumFractionDigits:dec});
  function step(t){
    const p = Math.min(1,(t-t0)/dur);
    const e = 1-Math.pow(1-p,3);
    n.textContent = fmt(target*e);
    if(p<1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
});
"""


def build(records, year: int, sources: list[str], meta: dict) -> str:
    st = stats_mod.compute(records, year)
    anoms = stats_mod.anomalies(records, st)

    # 星期 × 小时 矩阵
    mat = [[0.0] * 24 for _ in range(7)]
    day_totals: dict[date, float] = {}
    for r in records:
        if r.kind == "expense" and r.when.year == year:
            mat[r.when.weekday()][r.when.hour] += r.amount
            d = r.when.date()
            day_totals[d] = day_totals.get(d, 0.0) + r.amount

    name, desc = persona(st)
    facts = fun_facts(st, records)
    save_rate = 1 - (st.total_expense / st.total_income) if st.total_income else 0.0

    top_month = max(range(12), key=lambda i: st.monthly[i]) if st.total_expense else 0
    biggest = st.biggest

    H = []
    A = H.append
    A(f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">')
    A(f'<meta name="viewport" content="width=device-width,initial-scale=1">')
    A(f"<title>{year} 年度账单 · BillBook</title>")
    A(f"<style>{CSS}</style></head><body>")

    # hero
    A('<div class="wrap">')
    A('<section class="hero">')
    A(f'<div class="year">{year} 年度账单</div>')
    A(
        f'<h1 class="big"><span data-count="{st.total_expense:.0f}">0</span>'
        f'<span class="unit">元</span></h1>'
    )
    A(
        f'<div class="sub">这一年你花了 <b>¥{money(st.total_expense)}</b>，'
        f'收入 <b>¥{money(st.total_income)}</b>，'
        f'结余率 <b>{pct(save_rate)}</b>。'
        f'一共 <b>{st.count_expense:,}</b> 笔支出，覆盖 <b>{st.days}</b> 天。</div>'
    )
    A('<div class="kpi">')
    for k, v in facts:
        A(f'<div class="cell"><div class="k">{esc(k)}</div><div class="v">{esc(v)}</div></div>')
    A("</div>")
    A("</section>")

    # 全年日历
    if day_totals:
        A('<section class="reveal"><h2>这一年，钱是怎么流走的</h2>')
        A(svg_calendar(day_totals, year))
        A(
            f'<div class="legend"><span>最深的一天 ¥{money(max(day_totals.values()))}</span>'
            f'<span>有消费 {len(day_totals)} 天</span>'
            f'<span>{st.days - len(day_totals)} 天一分没花</span></div>'
        )
        A("</section>")

    # 月度
    A('<section class="reveal"><h2>按月看</h2>')
    A(svg_monthly(st))
    A(
        f'<div class="legend"><span><i style="background:{ACCENT}"></i>支出</span>'
        f'<span><i style="background:{WARN}"></i>收入</span>'
        f'<span>最高的一个月是 {top_month + 1} 月，¥{money(st.monthly[top_month])}</span></div>'
    )
    A("</section>")

    # 分类
    A('<section class="reveal"><h2>钱花在哪</h2>')
    A(bars_categories(st.cats))
    A("</section>")

    # 时段
    A('<section class="reveal"><h2>你在什么时间花钱</h2>')
    A(svg_heat(mat))
    peak_cell = max(((v, w, h) for w in range(7) for h, v in enumerate(mat[w])))
    A(
        f'<div class="legend"><span>最集中的时段是 {WEEK[peak_cell[1]]} {peak_cell[2]}:00 前后，'
        f'合计 ¥{money(peak_cell[0])}</span></div>'
    )
    A("</section>")

    # 商家 + 大额
    A('<section class="reveal"><h2>你和谁打交道最多</h2>')
    A(bars_merchants(st.merchants))
    A("</section>")

    A('<section class="reveal"><h2>最贵的几笔</h2>')
    A("<table><thead><tr><th>时间</th><th>商家</th><th>说明</th><th>分类</th>"
      '<th class="r">金额</th></tr></thead><tbody>')
    for r in biggest:
        A(
            f'<tr><td class="m">{r.when:%m-%d %H:%M}</td><td>{esc(r.party)}</td>'
            f'<td class="m">{esc(r.desc or "-")}</td>'
            f'<td><span class="tag">{esc(r.cat)}</span></td>'
            f'<td class="r">¥{money2(r.amount)}</td></tr>'
        )
    A("</tbody></table>")
    A("</section>")

    # 异常
    if anoms:
        A('<section class="reveal"><h2>这几笔，比你平时贵得多</h2>')
        for d in anoms[:6]:
            r = d["rec"]
            if d["recurring"]:
                how = f"是它自己平时（¥{money(d['base'])}）的 {d['ratio']:.1f} 倍"
            else:
                how = f"是当月日均的 {d['ratio']:.1f} 倍"
            A(
                f'<div class="anom"><div class="t">{esc(r.party)} · ¥{money2(r.amount)}</div>'
                f'<div class="d">{r.when:%Y-%m-%d %H:%M} · {esc(r.cat)} · {esc(how)}</div></div>'
            )
        A(
            '<div class="legend"><span>判据：单笔 ≥ 200 元；常去的商家（一年 6 笔以上）'
            "和它自己的中位数比，偶发的和当月日均比。用「相对自己」而不是绝对金额，"
            "收入高低不同的人都适用。</span></div>"
        )
        A("</section>")

    # 人格卡
    A('<section class="reveal"><h2>你的消费人格</h2>')
    A('<div class="card">')
    A(f'<div class="name">PERSONA</div><div class="title">{esc(name)}</div>')
    A(f'<div class="desc">{esc(desc)}</div>')
    A("</div></section>")

    # 数据来源
    A('<section class="reveal"><h2>数据来源</h2>')
    A("<table><thead><tr><th>文件</th><th>平台</th><th class=\"r\">记录数</th></tr></thead><tbody>")
    for s in sources:
        A(f'<tr><td>{esc(s)}</td><td class="m">{esc(meta.get(s, ""))}</td><td class="r">-</td></tr>')
    A("</tbody></table>")
    A(
        f'<div class="legend"><span>共 {len(records):,} 条记录，'
        f'去重后用于统计 {st.count_expense + st.count_income:,} 条收支</span></div>'
    )
    A("</section>")

    A("</div>")
    A(f"<footer><div class=\"wrap\">BillBook · 只在这台电脑上算，不上传任何数据 · "
      f"生成于 {datetime.now():%Y-%m-%d %H:%M}</div></footer>")
    A(f"<script>{JS}</script></body></html>")
    return "".join(H)


def write(records, year: int, out_path: str, sources=None, meta=None) -> str:
    sources = sources or []
    meta = meta or {}
    html_text = build(records, year, sources, meta)
    parent = os.path.dirname(os.path.abspath(out_path))
    os.makedirs(parent, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_text)
    return out_path
