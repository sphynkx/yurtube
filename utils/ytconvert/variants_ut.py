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
    probe_data: Dict[str, Any],
    *,
    prefer_container: str = "mp4",
    include_audio: bool = True,
) -> List[Dict[str, Any]]:
    """
    Compute suggested conversion variants based on ffprobe data.

    :param probe_data: JSON-like result from ffprobe (streams, format, etc.)
    :param prefer_container: Preferred container format, default is "mp4"
    :param include_audio: Whether to include audio-only variants
    :return: List of suggested conversion variants
    """
    streams = probe_data.get("streams", [])
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), {})

    height = int(video_stream.get("height", 0))
    suggested: List[Dict[str, Any]] = []

    # Suggest video formats lower than source height
    for video_height in [144, 360, 720, 1080]:
        if height >= video_height:
            suggested.append(
                {
                    "kind": "video",
                    "variant_id": f"v:{video_height}p:{prefer_container}",
                    "label": f"{video_height}p",
                    "height": video_height,
                    "vcodec": "h264" if prefer_container == "mp4" else "vp9",
                    "acodec": "aac" if prefer_container == "mp4" else "opus",
                    "container": prefer_container,
                }
            )

    # Add audio-only format
    if include_audio and audio_stream:
        suggested.append(
            {
                "kind": "audio",
                "variant_id": "a:128k:mp3",
                "label": "Audio only (128k)",
                "acodec": "mp3",
                "container": "mp3",
                "audio_bitrate_kbps": 128,
            }
        )

    return suggested