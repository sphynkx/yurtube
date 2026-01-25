from __future__ import annotations

import re


def parse_size_bytes(raw: object, default: int) -> int:
    if raw is None:
        return default
    if isinstance(raw, int):
        return raw
    s = str(raw).strip()
    if not s:
        return default

    # allow plain int string
    if s.isdigit():
        return int(s)

    m = re.match(r"^\s*(\d+)\s*([KMGTP]?i?B?)\s*$", s, re.IGNORECASE)
    if not m:
        return default

    n = int(m.group(1))
    unit = (m.group(2) or "").lower()

    # normalize
    if unit in ("b", ""):
        mul = 1
    elif unit in ("k", "kb"):
        mul = 1000
    elif unit in ("m", "mb"):
        mul = 1000 ** 2
    elif unit in ("g", "gb"):
        mul = 1000 ** 3
    elif unit in ("ki", "kib"):
        mul = 1024
    elif unit in ("mi", "mib"):
        mul = 1024 ** 2
    elif unit in ("gi", "gib"):
        mul = 1024 ** 3
    else:
        return default

    return max(1, n * mul)