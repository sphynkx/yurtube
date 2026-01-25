from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


# YouTube-like baseline ladder (heights in pixels)
_DEFAULT_HEIGHTS = [2160, 1440, 1080, 720, 480, 360, 240]


@dataclass(frozen=True)
class VariantPlan:
    """
    Stage-0 plan object (no actual files yet).
    """
    kind: str               # "video" | "audio"
    label: str              # "720p" | "Audio only"
    container: str          # "mp4" | "webm" | "m4a" | "mp3"
    vcodec: Optional[str] = None
    acodec: Optional[str] = None
    height: Optional[int] = None
    audio_bitrate_kbps: Optional[int] = None


def _choose_suggested_video_heights(src_height: int, ladder: Optional[List[int]] = None) -> List[int]:
    if not src_height or src_height <= 0:
        return []
    heights = ladder or list(_DEFAULT_HEIGHTS)

    # Only offer below source height
    below = [h for h in heights if h < src_height]

    # If source is very small, don't spam
    if src_height <= 360:
        return []

    # Keep it reasonable: offer up to 3 lower tiers
    return below[:3]


def _variant_id(v: VariantPlan) -> str:
    """
    Stable ID used by UI and gRPC contract.

    Examples:
      - v:1440p:h264+aac:mp4
      - a:128k:aac:m4a
    """
    if v.kind == "video":
        h = int(v.height or 0)
        vc = (v.vcodec or "auto").lower()
        ac = (v.acodec or "auto").lower()
        cont = (v.container or "auto").lower()
        return f"v:{h}p:{vc}+{ac}:{cont}"

    # audio
    abr = int(v.audio_bitrate_kbps or 0)
    ac = (v.acodec or "auto").lower()
    cont = (v.container or "auto").lower()
    return f"a:{abr}k:{ac}:{cont}"


def compute_suggested_variants(
    source_info: Dict[str, Any],
    *,
    prefer_container: str = "mp4",
    include_audio: bool = True,
) -> List[Dict[str, Any]]:
    """
    Compute suggested conversion variants lower than the source.

    Input source_info expects at least:
      - {"height": int, "width": int, "duration_sec": float|int, ...}

    Output is a list of dicts ready for templating/logging, e.g.:
      [
        {"variant_id":"v:720p:h264+aac:mp4","kind":"video","label":"720p","height":720,"container":"mp4","vcodec":"h264","acodec":"aac"},
        {"variant_id":"a:128k:aac:m4a","kind":"audio","label":"Audio only (128k)","container":"m4a","acodec":"aac","audio_bitrate_kbps":128},
      ]
    """
    h = int(source_info.get("height") or 0)
    suggested: List[VariantPlan] = []

    # Video ladder
    for vh in _choose_suggested_video_heights(h):
        # For stage-0 we only "suggest"; codecs can be revised later
        if prefer_container.lower() == "webm":
            suggested.append(
                VariantPlan(kind="video", label=f"{vh}p", container="webm", vcodec="vp9", acodec="opus", height=vh)
            )
        else:
            suggested.append(
                VariantPlan(kind="video", label=f"{vh}p", container="mp4", vcodec="h264", acodec="aac", height=vh)
            )

    # Audio-only
    if include_audio:
        suggested.append(
            VariantPlan(kind="audio", label="Audio only (128k)", container="m4a", acodec="aac", audio_bitrate_kbps=128)
        )

    # Convert to dicts (stable fields)
    out: List[Dict[str, Any]] = []
    for v in suggested:
        out.append(
            {
                "variant_id": _variant_id(v),
                "kind": v.kind,
                "label": v.label,
                "container": v.container,
                "vcodec": v.vcodec,
                "acodec": v.acodec,
                "height": v.height,
                "audio_bitrate_kbps": v.audio_bitrate_kbps,
            }
        )
    return out