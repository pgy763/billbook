"""消费分类。

为什么不用「交易分类」列：支付宝叫「餐饮美食」，微信叫「商户消费」，
同一个人在两边的分类粒度完全不同，直接画图会把同类消费劈成两半。
所以这里自己按「对方 + 商品说明」的规则归类，两个平台的记录进同一套类目。
"""

from __future__ import annotations

import re
from collections import OrderedDict

# 顺序即优先级：先匹配到的赢。所以「酒店」要排在「餐饮」前面。
# 每条是 (类目, 关键词)。
RULES: list[tuple[str, tuple[str, ...]]] = [
    ("住房", ("房租", "租金", "物业", "房贷", "中介费", "水费", "电费", "燃气", "取暖")),
    ("交通", ("地铁", "公交", "打车", "滴滴", "出租车", "高铁", "火车", "12306", "加油", "停车",
             "etc", "航空", "机票", "共享单车", "哈啰", "青桔", "违章", "收费站")),
    ("医疗", ("医院", "药房", "药店", "诊所", "体检", "挂号", "口腔", "牙科", "眼科", "医保")),
    ("教育", ("学费", "培训", "课程", "书店", "图书", "网课", "考试", "报名费", "得到", "极客时间")),
    # 注意：这里不能写 "apple" / "store" 这种大词，否则 Apple Store 买电脑也会被算成订阅。
    ("会员订阅", ("大会员", "会员", "vip", "订阅", "icloud", "netflix", "spotify", "youtube",
                  "bilibili", "腾讯视频", "爱奇艺", "优酷", "网易云", "qq音乐", "百度网盘",
                  "阿里云", "github copilot", "notion", "chatgpt", "openai", "claude")),
    ("数码", ("京东", "电脑", "手机", "耳机", "键盘", "鼠标", "显示器", "硬盘", "充电", "数据线",
             "小米", "华为", "苹果", "apple store", "配件", "摄像头", "路由器")),
    ("餐饮", ("餐", "饭", "面", "粉", "粥", "烧烤", "火锅", "麻辣", "麻辣烫", "汉堡", "披萨",
             "麦当劳", "肯德基", "星巴克", "瑞幸", "咖啡", "奶茶", "茶饮", "蜜雪", "喜茶",
             "奈雪", "外卖", "饿了么", "美团", "小吃", "甜品", "烘焙", "蛋糕", "食堂", "food",
             "厨房", "超市", "便利店", "711", "全家", "罗森")),
    ("购物", ("淘宝", "天猫", "拼多多", "唯品会", "商场", "百货", "旗舰店", "专营店", "服饰",
             "鞋", "衣", "优衣库", "无印良品", "名创优品", "宜家", "家居", "日用", "文具",
             "化妆品", "护肤", "洗护", "母婴", "玩具", "宠物")),
    ("娱乐", ("电影", "影院", "ktv", "游戏", "steam", "playstation", "nintendo", "switch",
             "演唱会", "门票", "景区", "旅游", "酒店", "民宿", "携程", "飞猪", "去哪儿",
             "livehouse", "live house", "剧场", "话剧", "展览", "健身", "游泳", "球馆", "运动")),
    ("通讯", ("话费", "流量", "宽带", "中国移动", "中国联通", "中国电信", "手机充值")),
    ("人情", ("红包", "转账", "礼金", "份子", "压岁")),
    ("金融", ("还款", "信用卡", "花呗", "借呗", "白条", "利息", "手续费", "理财", "基金",
             "保险", "贷款", "保证金")),
]

CATS = [c for c, _ in RULES] + ["其他"]
CAT_COLOR = {
    "餐饮": "#fb923c",
    "购物": "#a78bfa",
    "交通": "#60a5fa",
    "住房": "#5eead4",
    "娱乐": "#f472b6",
    "数码": "#38bdf8",
    "医疗": "#f87171",
    "教育": "#fbbf24",
    "会员订阅": "#c084fc",
    "通讯": "#94a3b8",
    "人情": "#fda4af",
    "金融": "#64748b",
    "其他": "#475569",
}

# 平台原始分类 → 我们的类目，作为关键词没命中时的兜底
RAW_MAP = {
    "餐饮美食": "餐饮",
    "交通出行": "交通",
    "日用百货": "购物",
    "服饰装扮": "购物",
    "数码电器": "数码",
    "文化休闲": "娱乐",
    "医疗健康": "医疗",
    "教育培训": "教育",
    "住房物业": "住房",
    "生活服务": "其他",
    "投资理财": "金融",
    "保险": "金融",
    "转账红包": "人情",
    "充值缴费": "通讯",
    "商户消费": "",
    "扫二维码付款": "",
    "二维码收款": "",
}


def _hay(rec) -> str:
    return f"{rec.party} {rec.desc} {rec.raw_cat}".lower()


def classify(rec) -> str:
    """给单条记录打类目。收入里「转账/红包」归人情，其余归其他。"""
    hay = _hay(rec)
    if rec.kind == "income":
        if any(k in hay for k in ("红包", "转账", "退款")):
            return "退款" if "退款" in hay else "人情"
        return "收入"

    for cat, words in RULES:
        for w in words:
            if w in hay:
                return cat
    raw = RAW_MAP.get(rec.raw_cat.strip(), "")
    return raw or "其他"


def classify_all(records) -> None:
    for r in records:
        if r.kind == "neutral":
            r.cat = "不计收支"
        else:
            r.cat = classify(r)


# ---------------------------------------------------------------- 商家归一

_NOISE = re.compile(
    r"(有限公司|有限责任公司|分公司|股份公司|科技|网络|信息|技术|服务|商贸|实业|集团|"
    r"电子商务|文化|传媒|餐饮管理|食品|连锁|管理|咨询|门店|分店|\d+号店|"
    r"\(.*?\)|（.*?）|\s+)"
)


def merchant(rec) -> str:
    """把「上海星巴克咖啡经营有限公司北京朝阳分店」压成「上海星巴克咖啡经营」可读的名字。

    真实账单里的交易对方字段经常带公司后缀和一串门店名，
    不压一下的话「商家排行」会变成一堆互不相干的长串。
    """
    s = (rec.party or rec.desc or "未知").strip()
    s = re.sub(r"[*]+", "", s)
    s = _NOISE.sub("", s)
    s = s.strip(" ,.-_|")
    if len(s) > 16:
        s = s[:16]
    return s or "未知"


def top_categories(records, n=8):
    agg: dict[str, float] = {}
    for r in records:
        if r.kind != "expense":
            continue
        agg[r.cat] = agg.get(r.cat, 0.0) + r.amount
    items = sorted(agg.items(), key=lambda kv: -kv[1])
    return items[:n]


def monthly(records, year: int) -> list[float]:
    out = [0.0] * 12
    for r in records:
        if r.kind == "expense" and r.when.year == year:
            out[r.when.month - 1] += r.amount
    return out


def ordered_cats() -> "OrderedDict[str, str]":
    d: OrderedDict[str, str] = OrderedDict()
    for c in CATS:
        d[c] = CAT_COLOR.get(c, "#475569")
    d["退款"] = "#34d399"
    d["收入"] = "#22d3ee"
    d["不计收支"] = "#334155"
    return d
