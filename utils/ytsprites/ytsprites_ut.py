# Client utils for ytsprites service

def normalize_vtt(vtt_text: str) -> str:
    """
    Possible fix for VTT: adds `\n` if not exist
    """
    s = vtt_text or ""
    return s if s.endswith("\n") else (s + "\n")