from __future__ import annotations

from typing import Optional


def _titlecase_english(s: str) -> str:
    """
    Minimal prettifier: capitalize first letter (similar to previous Babel behavior).
    """
    t = (s or "").strip()
    if not t:
        return ""
    return t[:1].upper() + t[1:]


def _normalize_lang_code(code: str) -> str:
    """
    Normalize language codes coming from services:
    - trim
    - underscores -> hyphens
    - keep as-is otherwise
    """
    c = (code or "").strip()
    if not c:
        return ""
    return c.replace("_", "-")


def lang_display_name_en(code: str) -> str:
    """
    Convert language code (2- or 3-letter ISO / BCP47 variants) to English display name.

    Strategy:
      1) Try Babel (best for BCP47 / script / region variants).
      2) Fallback to pycountry (best for ISO 639-3 three-letter codes).
      3) Fallback to the original code.

    Returns the code itself when no mapping found.
    """
    c = _normalize_lang_code(code)
    if not c:
        return ""

    # --- 1) Babel ---
    try:
        from babel.core import Locale  # type: ignore

        loc_code = c.replace("-", "_")
        try:
            loc = Locale.parse(loc_code)
        except Exception:
            base = loc_code.split("_", 1)[0]
            loc = Locale.parse(base)
        name = loc.get_display_name("en")
        if name:
            return _titlecase_english(name)
    except Exception:
        pass

    # --- 2) pycountry fallback ---
    # Handle "xxx-Latn" / "xx-YY": use only base subtag for pycountry.
    base = c.split("-", 1)[0].strip().lower()
    if base:
        try:
            import pycountry  # type: ignore

            lang_obj: Optional[object] = None

            if len(base) == 2:
                lang_obj = pycountry.languages.get(alpha_2=base)
            elif len(base) == 3:
                # alpha_3 is the modern key; also try bibliographic if present
                lang_obj = pycountry.languages.get(alpha_3=base) or pycountry.languages.get(bibliographic=base)

            if lang_obj is not None:
                nm = getattr(lang_obj, "name", None)
                if isinstance(nm, str) and nm.strip():
                    return _titlecase_english(nm)
        except Exception:
            pass

    # --- 3) fallback ---
    return c