import os
import base64


def gen_id(length: int) -> str:
    """
    Generate a base64url id with exact length (no padding).
    """
    # Generate sufficient random bytes, then trim
    # 3 bytes -> 4 base64 chars; overshoot and slice
    raw = os.urandom((length * 3) // 4 + 2)
    s = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return s[:length]