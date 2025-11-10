import uuid
import string
from typing import Optional

_ALPHABET = string.digits + string.ascii_lowercase + string.ascii_uppercase  # base62


def _to_base62(num: int) -> str:
    if num == 0:
        return _ALPHABET[0]
    base = len(_ALPHABET)
    out = []
    while num:
        num, rem = divmod(num, base)
        out.append(_ALPHABET[rem])
    return "".join(reversed(out))


def short_uuid(prefix: Optional[str] = None) -> str:
    # Shorten 128-bit UUID -> int -> base62 (~22 symbs) ->cut to  10-12 symbs
    u = uuid.uuid4().int
    b62 = _to_base62(u)
    short = b62[:12]
    return f"{prefix}{short}" if prefix else short