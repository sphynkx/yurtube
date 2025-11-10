from typing import Any, Dict


def text_size_bytes(text: str) -> int:
    return len(text.encode("utf-8"))


def estimate_root_comment_entry_size(cid: str, entry: Dict[str, Any]) -> int:
    # Rough estimate for approx_size (keys + values)
    s = len(cid)
    for k, v in entry.items():
        s += len(k)
        if isinstance(v, str):
            s += len(v)
        elif isinstance(v, dict):
            for kk, vv in v.items():
                s += len(kk)
                if isinstance(vv, str):
                    s += len(vv)
                elif isinstance(vv, int):
                    s += 8
        elif isinstance(v, int):
            s += 8
        elif isinstance(v, bool):
            s += 1
        elif v is None:
            s += 1
    # some overhead
    return s + 64