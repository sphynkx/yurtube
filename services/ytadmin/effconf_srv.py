from __future__ import annotations
import os
import hashlib
from typing import Dict, List, Tuple

REDACT_PLACEHOLDER = "********"


def _redact_value(key: str, value: str, redact_keys: List[str]) -> str:
    for rk in redact_keys:
        if rk and key.strip().upper() == rk.strip().upper():
            return REDACT_PLACEHOLDER
    return value


def collect_effective_config(
    whitelist: List[str],
    redact_keys: List[str],
) -> Tuple[Dict[str, str], List[str], str]:
    """
    Returns (config_map, redacted_keys, config_hash):
    - config_map: only whitelisted keys; secrets are obfuscated.
    - redacted_keys: which keys were obfuscated.
    - config_hash: SHA256 hash of sorted pairs for version verification.
    """
    cfg: Dict[str, str] = {}
    redacted: List[str] = []

    for k in whitelist:
        v = os.getenv(k)
        if v is None:
            continue
        masked = _redact_value(k, v, redact_keys)
        if masked == REDACT_PLACEHOLDER:
            redacted.append(k)
        cfg[k] = masked

    blob = "|".join(f"{k}={cfg[k]}" for k in sorted(cfg.keys()))
    digest = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    return cfg, redacted, digest