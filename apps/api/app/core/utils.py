"""Small shared helpers."""
from __future__ import annotations

import re
import uuid


def slugify(value: str, fallback: str = "workspace") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")[:60]
    return slug or f"{fallback}-{uuid.uuid4().hex[:6]}"


def unique_suffix() -> str:
    return uuid.uuid4().hex[:6]
