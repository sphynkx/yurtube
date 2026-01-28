from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


# YouTube-like baseline ladder (heights in pixels)
_DEFAULT_HEIGHTS = [2160, 1440, 1080, 720, 480, 360, 240]


def _choose_suggested_video_heights(src_height: int, ladder: Optional[List[int]] = None) -> List[int]:
    if not src_height or src_height <= 0:
        return []
    heights = ladder or list(_DEFAULT_HEIGHTS)

    below = [h for h in heights if h < src_height]

    # If source is very small, don't offer ladder
    if src_height <= 360:
        return []

    # Offer up to 3 lower tiers
    return below[:3]


def _mk_video_variant_id(height: int, vcodec: str, acodec: str, container: str) -> str:
    return f"v:{int(height)}p:{vcodec}+{acodec}:{container}"


def _mk_audio_variant_id(bitrate_kbps: int, acodec: str, container: str) -> str:
    return f"a:{int(bitrate_kbps)}k:{acodec}:{container}"


def _parse_video_variant_id(variant_id: str) -> Optional[Tuple[int, str, str, str]]:
    """
    Parse v:<height>p:<vcodec>+<acodec>:<container>
    Return (height, vcodec, acodec, container) or None.
    """
    s = (variant_id or "").strip()
    m = re.match(r"^v:(\d+)p:([^:+]+)\+([^:]+):([a-zA-Z0-9]+)$", s)
    if not m:
        return None
    return int(m.group(1)), m.group(2), m.group(3), m.group(4)


def _parse_audio_variant_id(variant_id: str) -> Optional[Tuple[int, str, str]]:
    """
    Parse a:<bitrate>k:<acodec>:<container>
    Return (bitrate_kbps, acodec, container) or None.
    """
    s = (variant_id or "").strip()
    m = re.match(r"^a:(\d+)k:([^:]+):([a-zA-Z0-9]+)$", s)
    if not m:
        return None
    return int(m.group(1)), m.group(2), m.group(3)


def compute_suggested_variants(
    probe_data: Dict[str, Any],
    *,
    prefer_container: str = "mp4",
    include_audio: bool = True,
) -> List[Dict[str, Any]]:
    """
    Backend "plan" variants (may include both mp4 and webm for each height).
    UI must be given a filtered/cleaned list via variants_for_ui().

    NOTE about compatibility:
      - older code calls compute_suggested_variants(..., prefer_container="mp4", include_audio=True)
      - we keep prefer_container to avoid TypeError
      - but per product requirements we always generate:
          mp4 video (h264+aac) AND webm video (vp9+opus)
        so prefer_container is effectively limited to mp4 (anything else falls back to mp4).

    Video:
      - mp4: h264+aac
      - webm: vp9+opus
    Audio:
      - mp3: mp3 in mp3   (fixes "m4a instead of mp3")
      - ogg: opus in ogg  (fixes "ogg not created")
    """
    # Accept prefer_container for backward compatibility, but enforce mp4 as main visible container
    prefer_container = (prefer_container or "mp4").lower()
    if prefer_container != "mp4":
        prefer_container = "mp4"

    streams = probe_data.get("streams", []) or []

    # probe_data comes from two places:
    # - /internal/ytconvert/probe -> full ffprobe json (streams list)
    # - upload_rout.py stage0 helper -> {"width","height","vcodec","acodec"...} (no streams)
    # Handle both.
    if streams:
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), {}) or {}
        audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), {}) or {}
        src_height = int(video_stream.get("height", 0) or 0)
        has_audio = bool(audio_stream)
    else:
        src_height = int(probe_data.get("height", 0) or 0)
        # best-effort: if upload helper detected an audio codec string, treat as audio present
        has_audio = bool((probe_data.get("acodec") or "").strip())

    suggested_heights = _choose_suggested_video_heights(src_height)

    suggested: List[Dict[str, Any]] = []

    for h in suggested_heights:
        # mp4 video (visible in UI)
        suggested.append(
            {
                "kind": "video",
                "variant_id": _mk_video_variant_id(h, "h264", "aac", prefer_container),
                "label": f"{h}p",
                "height": h,
                "vcodec": "h264",
                "acodec": "aac",
                "container": prefer_container,
            }
        )
        # webm video (backend-required, not shown in UI)
        suggested.append(
            {
                "kind": "video",
                "variant_id": _mk_video_variant_id(h, "vp9", "opus", "webm"),
                "label": f"{h}p",
                "height": h,
                "vcodec": "vp9",
                "acodec": "opus",
                "container": "webm",
            }
        )

    if include_audio and has_audio:
        # mp3
        suggested.append(
            {
                "kind": "audio",
                "variant_id": _mk_audio_variant_id(128, "mp3", "mp3"),
                "label": "mp3",
                "acodec": "mp3",
                "container": "mp3",
                "audio_bitrate_kbps": 128,
            }
        )
        # ogg/opus
        suggested.append(
            {
                "kind": "audio",
                "variant_id": _mk_audio_variant_id(128, "opus", "ogg"),
                "label": "ogg",
                "acodec": "opus",
                "container": "ogg",
                "audio_bitrate_kbps": 128,
            }
        )

    return suggested


def variants_for_ui(all_variants: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Return a UI-safe list:
      - hide webm video entries
      - for video show only resolution label (e.g. "720p") without container/codec text
      - for audio show only mp3 and ogg labels
    """
    out: List[Dict[str, Any]] = []
    for v in all_variants or []:
        kind = (v.get("kind") or "").lower()
        container = (v.get("container") or "").lower()

        if kind == "video":
            if container == "webm":
                continue
            out.append(
                {
                    "kind": "video",
                    "variant_id": v.get("variant_id"),
                    "label": v.get("label") or "",
                    "height": v.get("height") or 0,
                }
            )
        elif kind == "audio":
            if container not in ("mp3", "ogg"):
                continue
            out.append(
                {
                    "kind": "audio",
                    "variant_id": v.get("variant_id"),
                    "label": "mp3" if container == "mp3" else "ogg",
                    "audio_bitrate_kbps": v.get("audio_bitrate_kbps") or 0,
                }
            )
    return out


def expand_requested_variant_ids(requested_variant_ids: List[str]) -> List[str]:
    """
    Critical behavior:
      - if user requested any mp4 video variant (e.g. v:144p:h264+aac:mp4),
        automatically add corresponding webm variant (v:144p:vp9+opus:webm).
      - preserve any explicitly requested webm if present
      - keep audio as-is
    """
    req = [str(x).strip() for x in (requested_variant_ids or []) if str(x).strip()]
    out: List[str] = []
    seen = set()

    def _add(x: str):
        if x not in seen:
            seen.add(x)
            out.append(x)

    for vid in req:
        _add(vid)
        pv = _parse_video_variant_id(vid)
        if not pv:
            continue

        height, vcodec, acodec, container = pv
        if container.lower() == "mp4":
            _add(_mk_video_variant_id(height, "vp9", "opus", "webm"))

    return out