"""最小 xlsx 读取器。

微信导出的账单是 xlsx，而本工具不想依赖 openpyxl / pandas，
所以这里只实现账单用得到的那一小部分：sharedStrings + 第一个 sheet 的单元格。
够用就好，不追求兼容 Excel 的全部特性。
"""

from __future__ import annotations

import re
import zipfile
from xml.etree import ElementTree as ET

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_COL = re.compile(r"([A-Z]+)")


def _col_index(ref: str) -> int:
    """A1 -> 0, AB12 -> 27."""
    m = _COL.match(ref or "")
    if not m:
        return 0
    n = 0
    for ch in m.group(1):
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _shared_strings(zf: zipfile.ZipFile) -> list[str]:
    try:
        raw = zf.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ET.fromstring(raw)
    out = []
    for si in root.findall(_NS + "si"):
        # 富文本会被拆成多个 <t>，拼起来才是完整字符串
        out.append("".join(t.text or "" for t in si.iter(_NS + "t")))
    return out


def _first_sheet(zf: zipfile.ZipFile) -> str:
    names = [n for n in zf.namelist() if n.startswith("xl/worksheets/") and n.endswith(".xml")]
    if not names:
        raise ValueError("xlsx 里没有工作表")
    names.sort()
    return names[0]


def read_rows(path) -> list[list[str]]:
    """把第一个工作表读成按行的字符串二维表。空行保留为空列表。"""
    with zipfile.ZipFile(path) as zf:
        shared = _shared_strings(zf)
        root = ET.fromstring(zf.read(_first_sheet(zf)))

    rows: list[list[str]] = []
    sheet_data = root.find(_NS + "sheetData")
    if sheet_data is None:
        return rows

    for row in sheet_data.findall(_NS + "row"):
        cells: list[str] = []
        for c in row.findall(_NS + "c"):
            idx = _col_index(c.get("r", ""))
            while len(cells) < idx:  # 补空洞，保证列对齐
                cells.append("")
            kind = c.get("t", "n")
            if kind == "inlineStr":
                node = c.find(_NS + "is")
                val = "".join(t.text or "" for t in node.iter(_NS + "t")) if node is not None else ""
            else:
                v = c.find(_NS + "v")
                raw = v.text if v is not None and v.text is not None else ""
                if kind == "s":
                    try:
                        val = shared[int(raw)]
                    except (ValueError, IndexError):
                        val = raw
                else:
                    val = raw
            cells.append(val or "")
        rows.append(cells)
    return rows
