"""账单解析：支付宝 CSV / 微信支付 XLSX，统一成 Record。

设计原则：
1. 不猜文件格式，先看内容 —— 两个平台的导出格式每隔一两年就变一次，
   所以按**列名**映射字段，不按列号。
2. 表头行也不写死在第几行，扫到含「交易时间」和「金额」的那一行为止。
3. 金额、时间都写成宽松解析，脏数据跳过去而不是整个文件失败。
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

from . import xlsx

# ---------------------------------------------------------------- 记录

@dataclass
class Record:
    when: datetime
    kind: str          # expense / income / neutral
    amount: float      # 正数，单位元
    party: str         # 交易对方
    desc: str          # 商品说明
    raw_cat: str       # 平台自带的交易分类
    method: str        # 支付方式
    status: str
    order: str
    source: str        # alipay / wechat
    cat: str = ""      # 我们自己归类的结果
    _key: tuple = field(default=(), repr=False)

    @property
    def signed(self) -> float:
        if self.kind == "expense":
            return -self.amount
        if self.kind == "income":
            return self.amount
        return 0.0


# ---------------------------------------------------------------- 杂项

_AMOUNT = re.compile(r"-?\d[\d,]*\.?\d*")
_TIME_PATTERNS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M",
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%Y年%m月%d日 %H:%M:%S",
    "%Y年%m月%d日 %H:%M",
    "%Y年%m月%d日",
)


def parse_amount(s: str) -> float | None:
    if s is None:
        return None
    t = str(s).replace("\u00a5", "").replace("\uffe5", "").replace("¥", "")
    t = t.replace(",", "").replace(" ", "").replace("\u00a0", "").strip()
    if not t or t in {"&nbsp;", "-", "--"}:
        return None
    m = _AMOUNT.search(t)
    if not m:
        return None
    try:
        return abs(float(m.group(0)))
    except ValueError:
        return None


def parse_time(s: str) -> datetime | None:
    t = (s or "").strip()
    if not t:
        return None
    for p in _TIME_PATTERNS:
        try:
            return datetime.strptime(t, p)
        except ValueError:
            continue
    return None


def _norm_header(s: str) -> str:
    return re.sub(r"[\s\u3000()（）/、:]", "", (s or "")).lower()


# 表头别名：左边是归一化后的列名，右边是字段
_ALIASES = {
    "time": ("交易时间", "交易创建时间", "创建时间", "时间"),
    "kind": ("收支", "收支类型", "收/支"),
    "amount": ("金额", "金额元", "发生金额", "交易金额"),
    "party": ("交易对方", "对方", "商户名称", "对方名称"),
    "desc": ("商品说明", "商品", "商品名称", "交易说明", "备注说明"),
    "raw_cat": ("交易分类", "交易类型", "交易类别"),
    "method": ("收付款方式", "支付方式", "付款方式", "收付款"),
    "status": ("交易状态", "当前状态", "状态"),
    "order": ("交易订单号", "交易单号", "订单号", "商户单号"),
}


def _map_header(cells: Iterable[str]) -> dict[str, int]:
    norm = [_norm_header(c) for c in cells]
    out: dict[str, int] = {}
    for field_name, names in _ALIASES.items():
        for want in names:
            key = _norm_header(want)
            if key in norm:
                out[field_name] = norm.index(key)
                break
    return out


def _looks_like_header(cells: list[str]) -> bool:
    m = _map_header(cells)
    return "time" in m and "amount" in m


# ---------------------------------------------------------------- 读取

def _read_text(path) -> str:
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def _kind_of(raw: str, amount: float, desc: str = "", raw_cat: str = "") -> str:
    t = _norm_header(raw)
    if "不计收支" in t or "中性" in t:
        return "neutral"
    if t in {"支出", "支"} or t.startswith("支出"):
        return "expense"
    if t in {"收入", "收"} or t.startswith("收入"):
        return "income"
    # 微信的中性交易（信用卡还款、余额宝转入）「收/支」列是空的。
    # 不排除这些，支出会凭空多出几千块 —— 这是账单工具最容易错的地方。
    hay = f"{desc} {raw_cat}"
    if any(k in hay for k in ("还款", "自动转入", "转出到", "零钱转入", "不计收支")):
        return "neutral"
    return "expense"


def _rows_to_records(rows: list[list[str]], source: str) -> tuple[list[Record], int]:
    start = None
    cols: dict[str, int] = {}
    for i, row in enumerate(rows):
        if _looks_like_header(row):
            start, cols = i + 1, _map_header(row)
            break
    if start is None:
        raise ValueError("找不到表头（需要同时有「交易时间」和「金额」两列），这个文件不是账单导出格式？")

    out: list[Record] = []
    skipped = 0
    for row in rows[start:]:
        if not row or not any(c.strip() for c in row):
            continue

        def get(name: str) -> str:
            i = cols.get(name)
            return (row[i] if i is not None and i < len(row) else "").strip()

        when = parse_time(get("time"))
        amount = parse_amount(get("amount"))
        if when is None or amount is None:
            skipped += 1
            continue
        kind = _kind_of(get("kind"), amount, get("desc"), get("raw_cat"))
        if amount == 0 and kind != "neutral":
            kind = "neutral"
        out.append(
            Record(
                when=when,
                kind=kind,
                amount=amount,
                party=get("party").replace("&nbsp;", "").strip(),
                desc=get("desc").replace("&nbsp;", "").strip(),
                raw_cat=get("raw_cat"),
                method=get("method"),
                status=get("status"),
                order=get("order"),
                source=source,
            )
        )
    return out, skipped


def detect_source(path) -> str:
    name = str(path).lower()
    if name.endswith((".xlsx", ".xlsm")):
        return "wechat"
    if name.endswith(".csv"):
        text = _read_text(path)[:4000]
        if "微信" in text:
            return "wechat"
        return "alipay"
    return "alipay"


def parse_file(path) -> tuple[list[Record], dict]:
    """返回 (记录, 元信息)。多个文件可以各自调用再合并。"""
    source = detect_source(path)
    if source == "wechat" and str(path).lower().endswith((".xlsx", ".xlsm")):
        rows = xlsx.read_rows(path)
    else:
        text = _read_text(path)
        rows = [r for r in csv.reader(io.StringIO(text))]
    records, skipped = _rows_to_records(rows, source)
    return records, {"source": source, "skipped": skipped, "path": str(path)}


def dedupe(records: Iterable[Record]) -> tuple[list[Record], int]:
    """两个平台会导出重复记录（同一笔在支付宝和微信都出现，或用户导了两次）。

    指纹用「时间 + 金额 + 对方 + 收支」，不用订单号 —— 订单号在两个平台之间不通用。
    """
    seen: set[tuple] = set()
    out: list[Record] = []
    dropped = 0
    for r in records:
        key = (r.when.replace(second=0), round(r.amount, 2), r.party, r.kind)
        if key in seen:
            dropped += 1
            continue
        seen.add(key)
        r._key = key
        out.append(r)
    return out, dropped
