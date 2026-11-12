"""解析层单元测试。不依赖 pytest，直接 python tools/test_parse.py。"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from billbook import categorize, parse, stats  # noqa: E402

OK = 0
FAIL = 0


def check(name, cond, extra=""):
    global OK, FAIL
    if cond:
        OK += 1
    else:
        FAIL += 1
        print(f"  ✗ {name} {extra}")


def eq(name, got, want):
    check(name, got == want, f"(got {got!r}, want {want!r})")


# ---------------------------------------------------------------- 金额

eq("金额：纯数字", parse.parse_amount("123.45"), 123.45)
eq("金额：千分位", parse.parse_amount("1,234.56"), 1234.56)
eq("金额：带人民币符号", parse.parse_amount("¥99.00"), 99.0)
eq("金额：全角符号", parse.parse_amount("￥1,280.00"), 1280.0)
eq("金额：负号取绝对值", parse.parse_amount("-38.50"), 38.5)
eq("金额：空串", parse.parse_amount(""), None)
eq("金额：占位符", parse.parse_amount("&nbsp;"), None)
eq("金额：横杠", parse.parse_amount("-"), None)
eq("金额：两边空格", parse.parse_amount("  7.5  "), 7.5)

# ---------------------------------------------------------------- 时间

eq("时间：标准", parse.parse_time("2025-03-05 14:22:01"), datetime(2025, 3, 5, 14, 22, 1))
eq("时间：斜杠", parse.parse_time("2025/03/05 14:22:01"), datetime(2025, 3, 5, 14, 22, 1))
eq("时间：只有日期", parse.parse_time("2025-03-05"), datetime(2025, 3, 5))
eq("时间：中文年月日", parse.parse_time("2025年3月5日 14:22"), datetime(2025, 3, 5, 14, 22))
eq("时间：没有秒", parse.parse_time("2025-03-05 14:22"), datetime(2025, 3, 5, 14, 22))
eq("时间：垃圾", parse.parse_time("不是时间"), None)

# ---------------------------------------------------------------- 收支判定

eq("收支：支出", parse._kind_of("支出", 10), "expense")
eq("收支：收入", parse._kind_of("收入", 10), "income")
eq("收支：不计收支", parse._kind_of("不计收支", 10), "neutral")
# 微信把「收/支」留空时，必须靠说明兜底，否则信用卡还款会被算成支出
eq("收支：空列+还款", parse._kind_of("", 3000, "信用卡还款", "投资理财"), "neutral")
eq("收支：空列+自动转入", parse._kind_of("", 500, "余额宝-自动转入", "投资理财"), "neutral")
eq("收支：空列+正常消费", parse._kind_of("", 30, "牛肉面", "餐饮美食"), "expense")
eq("收支：空列+退款", parse._kind_of("", 259, "退款-尺码不对", "日用百货"), "expense")


# ---------------------------------------------------------------- 解析真文件

def write_csv(path, body, encoding="utf-8-sig"):
    with open(path, "w", encoding=encoding, newline="") as f:
        f.write(body)


# 不能用 tempfile.mkdtemp()：这个沙箱里系统临时目录建出来的子目录 ACL 被抹掉，
# 写文件会报 PermissionError。放到项目自己的 out/ 下。
tmp = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "out", "testtmp"))
os.makedirs(tmp, exist_ok=True)


def tpath(name):
    p = os.path.join(tmp, name)
    return p


# 支付宝：前面有 4 行说明，第 5 行才是表头
alipay = tpath("a.csv")
write_csv(alipay, (
    "支付宝交易记录明细查询\n"
    "账号:[x@y.com]\n"
    "起始日期:[2025-01-01] 终止日期:[2025-12-31]\n"
    "--------------------交易记录明细列表--------------------\n"
    "交易时间,交易分类,交易对方,商品说明,收/支,金额,收/付款方式,交易状态,交易订单号,商家订单号,备注\n"
    '2025-01-02 12:30:00,餐饮美食,星巴克,"拿铁,大杯",支出,"38.00",花呗,交易成功,T1,M1,\n'
    '2025-01-03 09:00:00,转账红包,张三,转账,收入,"500.00",余额,交易成功,T2,M2,\n'
    "2025-01-04 09:00:00,投资理财,招商银行,信用卡还款,不计收支,\"3,000.00\",余额宝,交易成功,T3,M3,\n"
))
recs, meta = parse.parse_file(alipay)
eq("支付宝：记录数", len(recs), 3)
eq("支付宝：来源", meta["source"], "alipay")
eq("支付宝：跳过行", meta["skipped"], 0)
eq("支付宝：第一条金额", recs[0].amount, 38.0)
eq("支付宝：第一条收支", recs[0].kind, "expense")
eq("支付宝：逗号在引号里没被切开", recs[0].desc, "拿铁,大杯")
eq("支付宝：收入", recs[1].kind, "income")
eq("支付宝：不计收支", recs[2].kind, "neutral")
eq("支付宝：千分位金额", recs[2].amount, 3000.0)

# GBK 编码的账单也要能读
gbk = tpath("b.csv")
write_csv(gbk, (
    "交易时间,交易分类,交易对方,商品说明,收/支,金额,收/付款方式,交易状态,交易订单号,商家订单号,备注\n"
    "2025-02-01 08:00:00,餐饮美食,兰州牛肉面,牛肉面,支出,18.00,余额宝,交易成功,T9,M9,\n"
), encoding="gb18030")
recs2, _ = parse.parse_file(gbk)
eq("GBK 账单可读", len(recs2), 1)
eq("GBK 中文没乱码", recs2[0].party, "兰州牛肉面")

# 目录里混进一个不是账单的文件：要报错，不能默默产出 0 条
junk = tpath("junk.csv")
write_csv(junk, "a,b,c\n1,2,3\n")
try:
    parse.parse_file(junk)
    check("非账单文件应报错", False)
except ValueError as e:
    check("非账单文件应报错", "找不到表头" in str(e), str(e))

# 表头顺序被打乱（平台改版常常重排）仍然要对
shuffled = tpath("c.csv")
write_csv(shuffled, (
    "金额,交易对方,交易时间,收/支,商品说明,交易分类,支付方式,交易状态,订单号\n"
    "25.00,瑞幸咖啡,2025-03-01 10:00:00,支出,生椰拿铁,餐饮美食,余额宝,交易成功,X1\n"
))
r3, _ = parse.parse_file(shuffled)
eq("列序打乱可解析", len(r3), 1)
eq("列序打乱：金额", r3[0].amount, 25.0)
eq("列序打乱：对方", r3[0].party, "瑞幸咖啡")
eq("列序打乱：时间", r3[0].when, datetime(2025, 3, 1, 10, 0))

# ---------------------------------------------------------------- 去重

a = parse.Record(datetime(2025, 5, 1, 10, 0), "expense", 50, "A", "x", "", "", "", "1", "alipay")
b = parse.Record(datetime(2025, 5, 1, 10, 0), "expense", 50, "A", "x", "", "", "", "2", "wechat")
c = parse.Record(datetime(2025, 5, 1, 10, 5), "expense", 50, "A", "x", "", "", "", "3", "wechat")
out, dropped = parse.dedupe([a, b, c])
eq("去重：两条重复", dropped, 1)
eq("去重：剩 2 条", len(out), 2)

# ---------------------------------------------------------------- 分类

def cls(party="", desc="", raw="", kind="expense"):
    r = parse.Record(datetime(2025, 1, 1), kind, 10, party, desc, raw, "", "", "", "x")
    return categorize.classify(r)


eq("分类：星巴克→餐饮", cls("星巴克咖啡"), "餐饮")
eq("分类：地铁→交通", cls("北京地铁", "乘车码"), "交通")
eq("分类：房租→住房", cls("链家地产", "房租"), "住房")
eq("分类：宽带→通讯", cls("中国电信", "宽带续费"), "通讯")
eq("分类：iCloud→会员订阅", cls("Apple", "iCloud 存储空间"), "会员订阅")
eq("分类：Apple Store 买电脑不该算订阅", cls("Apple Store", "MacBook Pro"), "数码")
eq("分类：京东→数码", cls("京东商城", "显示器"), "数码")
eq("分类：原始分类兜底", cls("某某公司", "服务费", raw="医疗健康"), "医疗")
eq("分类：全都不认识→其他", cls("ZZZ", "QQQ"), "其他")
eq("分类：收入红包→人情", cls("老同学", "转账", kind="income"), "人情")
eq("分类：退款→退款", cls("淘宝", "退款", kind="income"), "退款")

# ---------------------------------------------------------------- 商家归一

def mer(party):
    return categorize.merchant(parse.Record(datetime(2025, 1, 1), "expense", 1, party, "", "", "", "", "", "x"))


eq("商家：去公司后缀", mer("上海星巴克咖啡经营有限公司"), "上海星巴克咖啡经营")
eq("商家：去门店", mer("北京全聚德(朝阳分店)"), "北京全聚德")
eq("商家：去星号", mer("**超市**"), "超市")
eq("商家：空→未知", mer(""), "未知")

# ---------------------------------------------------------------- 统计

recs = [
    parse.Record(datetime(2025, 1, 5, 9), "expense", 100, "A", "", "", "", "", "", "x"),
    parse.Record(datetime(2025, 1, 6, 9), "expense", 200, "B", "", "", "", "", "", "x"),
    parse.Record(datetime(2025, 2, 7, 21), "expense", 300, "C", "", "", "", "", "", "x"),
    parse.Record(datetime(2025, 2, 8, 21), "income", 900, "D", "", "", "", "", "", "x"),
]
for r in recs:
    r.cat = "其他"
st = stats.compute(recs, 2025)
eq("统计：总支出", st.total_expense, 600.0)
eq("统计：总收入", st.total_income, 900.0)
eq("统计：支出笔数", st.count_expense, 3)
eq("统计：一月", st.monthly[0], 300.0)
eq("统计：二月", st.monthly[1], 300.0)
eq("统计：中位数", st.median, 200.0)
eq("统计：结余率 1-600/900", round(1 - st.total_expense / st.total_income, 4), 0.3333)
# 1-05 到 2-08 = 34 天。这里算的是「账单跨度」，不是「有消费的天数」
eq("统计：天数覆盖", st.days, 34)

print()
print(f"{OK} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
