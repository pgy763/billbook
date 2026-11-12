"""造一份演示账单（不是真实数据）。

用来跑通解析 / 分类 / 报告全链路，也用来录视频。
刻意造了几种真实账单里才会出现的脏东西：
  - 支付宝 CSV 前 4 行是导出说明，第 5 行才是表头
  - 金额带千分位逗号
  - 微信 xlsx 的「收/支」列有空的（中性交易），要靠原始分类兜底
  - 有一条记录在两个平台都出现（用户两边各导了一次）
"""

from __future__ import annotations

import csv
import os
import random
import zipfile
from datetime import datetime, timedelta
from xml.sax.saxutils import escape

random.seed(20251231)

YEAR = 2025
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.path.join(HERE, "..", "demo"))

# (交易对方, 商品说明, 平台分类, 常用支付方式, 金额区间, 频次/月)
MEALS = [
    ("星巴克咖啡", "星巴克咖啡", "餐饮美食", "信用卡", (28, 45), 6),
    ("瑞幸咖啡", "生椰拿铁", "餐饮美食", "余额宝", (12, 20), 9),
    ("麦当劳", "麦辣鸡腿堡套餐", "餐饮美食", "花呗", (25, 42), 4),
    ("老乡鸡", "老乡鸡外卖", "餐饮美食", "余额宝", (18, 35), 6),
    ("海底捞火锅", "海底捞火锅", "餐饮美食", "信用卡", (160, 380), 1),
    ("兰州牛肉面", "牛肉面", "餐饮美食", "余额宝", (15, 24), 5),
    ("盒马鲜生", "盒马鲜生", "日用百货", "花呗", (60, 220), 3),
    ("美团外卖", "美团外卖订单", "餐饮美食", "信用卡", (22, 48), 8),
]
TRAFFIC = [
    ("滴滴出行", "滴滴快车", "交通出行", "信用卡", (14, 46), 10),
    ("北京地铁", "地铁乘车码", "交通出行", "余额宝", (5, 9), 26),
    ("中国石化", "加油", "交通出行", "信用卡", (280, 420), 2),
    ("哈啰单车", "骑行卡", "交通出行", "余额宝", (1.5, 15), 6),
]
SHOP = [
    ("京东商城", "京东自营订单", "数码电器", "信用卡", (80, 900), 2),
    ("淘宝", "淘宝订单", "日用百货", "信用卡", (15, 260), 6),
    ("优衣库", "优衣库", "服饰装扮", "信用卡", (120, 480), 1),
    ("小米之家", "小米之家", "数码电器", "花呗", (99, 1200), 1),
    ("山姆会员店", "山姆会员商店", "日用百货", "信用卡", (200, 620), 1),
]
FUN = [
    ("猫眼电影", "电影票", "文化休闲", "信用卡", (40, 90), 1),
    ("KEEP健身", "健身月卡", "文化休闲", "余额宝", (99, 199), 1),
    ("锦江之星", "酒店住宿", "文化休闲", "信用卡", (220, 480), 1),
    ("大麦网", "演唱会门票", "文化休闲", "信用卡", (380, 980), 0.2),
]
SUBS = [
    ("哔哩哔哩", "大会员", "文化休闲", "花呗", (148, 168), 0.25),
    ("Apple", "iCloud 存储空间", "文化休闲", "信用卡", (6, 21), 1),
    ("网易云音乐", "黑胶会员", "文化休闲", "余额宝", (8, 15), 1),
    ("GitHub", "GitHub Copilot", "文化休闲", "信用卡", (68, 68), 1),
]
MED = [
    ("同仁堂药店", "感冒药", "医疗健康", "余额宝", (28, 86), 0.5),
    ("口腔医院", "洗牙", "医疗健康", "信用卡", (198, 380), 0.2),
]
EDU = [
    ("极客时间", "专栏", "教育培训", "花呗", (29, 199), 0.5),
    ("当当网", "技术书", "教育培训", "余额宝", (49, 128), 0.8),
]
BAD = [
    ("北京协和医院", "挂号费", "医疗健康", "余额宝", (50, 300), 0.1),
]

FIXED = [
    ("链家地产", "房租", "住房物业", "银行卡转账", (5200, 5200), "rent"),
    ("国家电网", "电费", "充值缴费", "支付宝", (120, 420), "monthly"),
    ("中国移动", "话费充值", "充值缴费", "余额宝", (100, 100), "monthly"),
    ("中国电信", "宽带续费", "充值缴费", "信用卡", (1200, 1200), "yearly"),
]


def _add(rows, when, party, desc, cat, method, amount, kind="支出", status="交易成功"):
    rows.append({
        "when": when, "party": party, "desc": desc, "cat": cat,
        "method": method, "amount": round(amount, 2), "kind": kind, "status": status,
    })


def build():
    rows = []
    start = datetime(YEAR, 1, 1)
    # 每月固定支出
    for m in range(1, 13):
        _add(rows, datetime(YEAR, m, 1, 9, 12), "链家地产", "房租", "住房物业", "银行卡转账", 5200)
        _add(rows, datetime(YEAR, m, 6, 10, 30), "国家电网", "电费", "充值缴费", "支付宝",
             random.uniform(120, 420))
        _add(rows, datetime(YEAR, m, 8, 20, 5), "中国移动", "话费充值", "充值缴费", "余额宝", 100)
        _add(rows, datetime(YEAR, m, 10, 9, 0), "北京银行", "工资", "转账红包", "银行卡", 
             random.uniform(17500, 18500), kind="收入")
    _add(rows, datetime(YEAR, 3, 12, 11, 0), "中国电信", "宽带续费", "充值缴费", "信用卡", 1200)

    for group, scale in ((MEALS, 1.0), (TRAFFIC, 1.0), (SHOP, 1.0), (FUN, 1.0),
                         (SUBS, 1.0), (MED, 1.0), (EDU, 1.0)):
        for party, desc, cat, method, (lo, hi), freq in group:
            n = int(round(freq * 12 * scale * random.uniform(0.75, 1.25)))
            for _ in range(n):
                m = random.randint(1, 12)
                d = random.randint(1, 28)
                h = random.choice([8, 9, 11, 12, 12, 13, 18, 18, 19, 20, 21])
                _add(rows, datetime(YEAR, m, d, h, random.randint(0, 59)),
                     party, desc, cat, method, random.uniform(lo, hi))

    # 几笔「异常」大额：换电脑、看病、回家机票
    _add(rows, datetime(YEAR, 4, 18, 21, 40), "Apple Store", "MacBook Pro", "数码电器", "信用卡", 14999)
    _add(rows, datetime(YEAR, 7, 2, 14, 20), "北京大学口腔医院", "智齿手术", "医疗健康", "信用卡", 3860)
    _add(rows, datetime(YEAR, 1, 24, 7, 30), "中国国航", "北京-成都 机票", "交通出行", "信用卡", 2480)
    _add(rows, datetime(YEAR, 10, 1, 18, 5), "携程旅行", "国庆 酒店 3 晚", "文化休闲", "信用卡", 2280)
    _add(rows, datetime(YEAR, 11, 11, 0, 3), "京东商城", "双11 显示器", "数码电器", "信用卡", 2799)

    # 退款 / 转账 / 红包
    _add(rows, datetime(YEAR, 5, 9, 13, 10), "淘宝", "退款-尺码不对", "日用百货", "花呗", 259, kind="收入")
    for m in (2, 6, 9):
        _add(rows, datetime(YEAR, m, 14, 22, 12), "老同学", "转账", "转账红包", "余额", 
             random.uniform(200, 800), kind="收入")
        _add(rows, datetime(YEAR, m, 14, 22, 15), "老同学", "转账", "转账红包", "余额",
             random.uniform(100, 500))
    # 不计收支（中性）：信用卡还款、余额宝转入 —— 这类占比很高，不排除会虚增支出
    for m in range(1, 13):
        _add(rows, datetime(YEAR, m, 20, 8, 0), "招商银行信用卡", "信用卡还款", "投资理财", "余额宝",
             random.uniform(2000, 6000), kind="不计收支")
        _add(rows, datetime(YEAR, m, 21, 8, 0), "余额宝", "余额宝-自动转入", "投资理财", "余额",
             random.uniform(500, 2000), kind="不计收支")
    return rows


# ---------------------------------------------------------------- 写文件

def write_alipay(rows, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        f.write("支付宝交易记录明细查询\n")
        f.write("账号:[pgy763@example.com]\n")
        f.write("起始日期:[2025-01-01 00:00:00]    终止日期:[2025-12-31 23:59:59]\n")
        f.write("---------------------------------交易记录明细列表------------------------------------\n")
        w = csv.writer(f)
        w.writerow(["交易时间", "交易分类", "交易对方", "商品说明", "收/支", "金额",
                    "收/付款方式", "交易状态", "交易订单号", "商家订单号", "备注"])
        for r in sorted(rows, key=lambda x: x["when"]):
            w.writerow([
                r["when"].strftime("%Y-%m-%d %H:%M:%S"),
                r["cat"], r["party"], r["desc"], r["kind"],
                f"{r['amount']:,.2f}", r["method"], r["status"],
                f"2025{r['when']:%m%d}{random.randint(100000,999999)}",
                "", "",
            ])


def write_wechat(rows, path):
    """手搓一个最小的 xlsx。openpyxl 没装，所以自己拼 zip + xml。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    header = ["交易时间", "交易类型", "交易对方", "商品", "收/支", "金额(元)",
              "支付方式", "当前状态", "交易单号", "商户单号", "备注"]
    table = [header]
    for r in sorted(rows, key=lambda x: x["when"]):
        table.append([
            r["when"].strftime("%Y-%m-%d %H:%M:%S"), r["cat"], r["party"], r["desc"],
            "" if r["kind"] == "不计收支" else r["kind"],
            f"{r['amount']:.2f}", r["method"], r["status"],
            f"4200{r['when']:%m%d}{random.randint(100000,999999)}", "", "/",
        ])

    # 共享字符串表：所有单元格都走 inlineStr，省掉 sharedStrings 的转义麻烦
    def cell(ref, val):
        return f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{escape(str(val))}</t></is></c>'

    def col(i):
        s, i = "", i + 1
        while i:
            i, rem = divmod(i - 1, 26)
            s = chr(65 + rem) + s
        return s

    body = []
    for ri, row in enumerate(table, 1):
        cells = "".join(cell(f"{col(ci)}{ri}", v) for ci, v in enumerate(row) if v != "")
        body.append(f'<row r="{ri}">{cells}</row>')

    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(body)}</sheetData></worksheet>'
    )
    ct = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '</Types>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>'
    )
    wb = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="账单明细" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    wbrels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '</Relationships>'
    )
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", rels)
        z.writestr("xl/workbook.xml", wb)
        z.writestr("xl/_rels/workbook.xml.rels", wbrels)
        z.writestr("xl/worksheets/sheet1.xml", sheet)


def main():
    rows = build()
    # 切一半到微信，模拟「早几年用微信、后几年用支付宝」
    alipay = [r for r in rows if r["method"] in ("花呗", "余额宝", "支付宝", "银行卡转账")]
    wechat = [r for r in rows if r["method"] in ("信用卡", "余额", "银行卡")]
    write_alipay(alipay, os.path.join(OUT, "alipay_record_2025.csv"))
    write_wechat(wechat, os.path.join(OUT, "微信支付账单(20250101-20251231).xlsx"))
    print(f"alipay {len(alipay)} 行 -> demo/alipay_record_2025.csv")
    print(f"wechat {len(wechat)} 行 -> demo/微信支付账单(20250101-20251231).xlsx")


if __name__ == "__main__":
    main()
