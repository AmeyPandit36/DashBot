"""Deterministic, line-aware document chunking for contextual retrieval.

Line-awareness matters for glossaries: a chunk must not merge unrelated metric
definitions, otherwise retrieved evidence becomes ambiguous.
"""
from __future__ import annotations

import re


def _split_long_line(line: str, max_chars: int) -> list[str]:
    if len(line) <= max_chars:
        return [line]
    parts: list[str] = []
    current = ""
    for sentence in re.split(r"(?<=[.!?])\s+", line):
        if len(current) + len(sentence) + 1 <= max_chars:
            current = f"{current} {sentence}".strip()
        else:
            if current:
                parts.append(current)
            while len(sentence) > max_chars:
                parts.append(sentence[:max_chars])
                sentence = sentence[max_chars:]
            current = sentence
    if current:
        parts.append(current)
    return parts


def chunk_text(text: str, max_chars: int = 900, overlap: int = 120) -> list[str]:
    text = (text or "").replace("\r\n", "\n").strip()
    if not text:
        return []

    lines: list[str] = []
    for block in re.split(r"\n\s*\n", text):
        for raw_line in block.split("\n"):
            line = raw_line.rstrip()
            if not line.strip():
                continue
            lines.extend(_split_long_line(line, max_chars))

    chunks: list[str] = []
    current = ""
    for line in lines:
        candidate = f"{current}\n{line}".strip() if current else line
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = line
    if current:
        chunks.append(current)

    if overlap and len(chunks) > 1:
        with_overlap = [chunks[0]]
        for idx in range(1, len(chunks)):
            tail = chunks[idx - 1][-overlap:]
            if " " in tail:
                tail = tail.split(" ", 1)[1]
            with_overlap.append(f"{tail}\n{chunks[idx]}".strip())
        chunks = with_overlap
    return chunks
