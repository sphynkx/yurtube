# Client utils for ytsprites service


def normalize_vtt(vtt_text: str) -> str:
    s = vtt_text or ""
    return s if s.endswith("\n") else (s + "\n")


def prefix_sprite_paths(vtt_text: str, prefix: str = "sprites/") -> str:
    """
    Sets "sprites/" prefix for sprite files into VTT.
    """
    if not vtt_text:
        return vtt_text
    lines = vtt_text.splitlines()
    out = []
    for ln in lines:
        # Save timings
        if "-->" in ln:
            out.append(ln)
            continue
        t = ln.strip()
        # Save empties and WEBVTT header
        if not t or t.upper() == "WEBVTT":
            out.append(ln)
            continue
        # If prefix exists - dont touch
        if t.startswith(prefix):
            out.append(ln)
            continue
        if (t.endswith(".jpg") or t.endswith(".png")) or ("#xywh=" in t):
            out.append(prefix + ln)
        else:
            out.append(ln)
    return "\n".join(out)