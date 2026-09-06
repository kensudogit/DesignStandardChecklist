"""Markdown / プレーンテキスト。ページ番号は存在しないので None。"""

from __future__ import annotations

import re

from app.core.parsers.base import Block, ParsedDocument

MD_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
# 表形式の Markdown 行 (| a | b |)
MD_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
MD_TABLE_SEP = re.compile(r"^\s*\|[\s:\-|]+\|\s*$")


def parse(data: bytes) -> ParsedDocument:
    """Markdown / テキストを Block にする。見出し記法と表記法だけ解釈する。"""
    text = _decode(data)
    blocks: list[Block] = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        m = MD_HEADING.match(line)
        if m:
            blocks.append(Block(text=m.group(2).strip(), heading_level=len(m.group(1))))
            continue
        # |---|---| の区切り行は中身が無いので落とす
        if MD_TABLE_SEP.match(line):
            continue
        if MD_TABLE_ROW.match(line):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            joined = " / ".join(c for c in cells if c)
            if joined:
                blocks.append(Block(text=joined, is_table=True))
            continue
        blocks.append(Block(text=line.strip()))
    return ParsedDocument(blocks=blocks, meta={"format": "text"})


def _decode(data: bytes) -> str:
    """文字コードを推定して復号する。

    日本語の標準書は cp932 で保存されていることが多いため、UTF-8 の次に試す。
    どれでも読めなければ、置換文字を許して読み進める。1文字の不明で
    文書全体を捨てるより、残りを解析できた方が役に立つ。
    """
    for enc in ("utf-8-sig", "utf-8", "cp932", "shift_jis", "euc_jp"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")
