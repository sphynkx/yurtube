import os
import json
import asyncio
from typing import Tuple, Dict, Optional, Callable

from services.ytcms.ytcms_client_srv import submit_and_wait
from services.ffmpeg_srv import async_extract_audio_demux, async_transcode_audio

from config.ytcms_cfg import (
    YTCMS_AUDIO_PREPROCESS,
    YTCMS_AUDIO_CODEC,
    YTCMS_AUDIO_SR,
    YTCMS_AUDIO_CHANNELS,
    YTCMS_AUDIO_BITRATE,
    )

async def generate_captions(
    video_id: str,
    storage_rel: str,
    src_path: str,  # absolute path to original.webm (or prepared audio), passed by caller
    lang: str = "auto",
    on_status: Optional[Callable[[str, str, str, int, float], None]] = None,
) -> Tuple[str, Dict]:
    loop = asyncio.get_running_loop()

    preprocess_mode = (YTCMS_AUDIO_PREPROCESS or "off").strip().lower()
    audio_codec = (YTCMS_AUDIO_CODEC or "mp3").strip().lower()
    audio_sr = int(YTCMS_AUDIO_SR)
    audio_ch = int(YTCMS_AUDIO_CHANNELS)
    audio_br = str(YTCMS_AUDIO_BITRATE or "48k")

    # Derive base directory from the absolute source path instead of STORAGE_ROOT
    # src_path is expected to be .../{storage_rel}/original.webm
    base_abs = os.path.dirname(src_path)
    captions_dir = os.path.join(base_abs, "captions")
    os.makedirs(captions_dir, exist_ok=True)

    # Choose upload path: either original video, or prepared audio file
    upload_path = src_path
    used_preprocess = "off"
    used_codec = None
    audio_tmp_path = None

    try:
        if preprocess_mode in ("demux", "transcode"):
            # Prepare a temp audio file inside captions dir
            if preprocess_mode == "demux":
                # Container/codec preserved, extension optional -> use .bin
                audio_tmp_path = os.path.join(captions_dir, "captions.audio.bin")
                ok = await async_extract_audio_demux(src_path, audio_tmp_path)
                if ok:
                    upload_path = audio_tmp_path
                    used_preprocess = "demux"
                    used_codec = "copy"
            else:
                # Transcode to a compact ASR-friendly audio
                # Pick extension by codec
                ext = {
                    "mp3": ".mp3",
                    "opus": ".opus",
                    "aac": ".m4a",
                    "flac": ".flac",
                    "wav": ".wav",
                }.get(audio_codec, ".mp3")
                audio_tmp_path = os.path.join(captions_dir, f"captions.audio{ext}")
                ok = await async_transcode_audio(
                    src_path,
                    audio_tmp_path,
                    codec=audio_codec,
                    channels=audio_ch,
                    sample_rate=audio_sr,
                    bitrate=audio_br,
                )
                if ok:
                    upload_path = audio_tmp_path
                    used_preprocess = "transcode"
                    used_codec = audio_codec
        # else: "off" → keep upload_path = src_path
    except Exception:
        # On any pre-process failure, fall back to original video upload
        upload_path = src_path
        used_preprocess = "off"
        used_codec = None

    # Run gRPC-client in executor
    result = await loop.run_in_executor(
        None,
        lambda: submit_and_wait(
            video_path=upload_path,
            video_id=video_id,
            lang=lang,
            task="transcribe",
            on_status=on_status,
        )
    )

    captions_dir = os.path.join(base_abs, "captions")
    os.makedirs(captions_dir, exist_ok=True)

    vtt_abs = os.path.join(captions_dir, "captions.vtt")
    meta_abs = os.path.join(captions_dir, "captions.meta.json")

    # Store VTT (ResultReply.content or .vtt)
    vtt_payload = getattr(result, "vtt", None) or getattr(result, "content", "") or ""
    with open(vtt_abs, "w", encoding="utf-8") as f:
        f.write(vtt_payload if vtt_payload.endswith("\n") else (vtt_payload + "\n"))

    # Metadata: add percent/progress/job_id and preprocessing info
    percent = getattr(result, "percent", -1)
    progress = getattr(result, "progress", -1.0)
    job_id = getattr(result, "job_id", None)

    meta: Dict = {
        "video_id": video_id,
        "lang": getattr(result, "detected_lang", None) or lang,
        "model": getattr(result, "model", None),
        "device": getattr(result, "device", None),
        "compute_type": getattr(result, "compute_type", None),
        "duration_sec": getattr(result, "duration_sec", None),
        "task": getattr(result, "task", "transcribe"),
        "job_id": job_id,
        "source": "ytcms",
        "percent": int(percent) if isinstance(percent, (int, float)) else -1,
        "progress": float(progress) if isinstance(progress, (int, float)) else -1.0,
        "preprocess": {
            "mode": used_preprocess,
            "codec": used_codec,
            "sr": audio_sr if used_preprocess == "transcode" else None,
            "channels": audio_ch if used_preprocess == "transcode" else None,
            "bitrate": audio_br if used_preprocess == "transcode" else None,
            "upload_path": os.path.relpath(upload_path, base_abs) if upload_path.startswith(base_abs) else None,
        },
    }

    with open(meta_abs, "w", encoding="utf-8") as mf:
        json.dump(meta, mf)

    # Cleanup temp audio (best-effort)
    try:
        if audio_tmp_path and os.path.isfile(audio_tmp_path):
            os.remove(audio_tmp_path)
    except Exception:
        pass

    rel_vtt = os.path.join(storage_rel, "captions", "captions.vtt")
    return rel_vtt, meta