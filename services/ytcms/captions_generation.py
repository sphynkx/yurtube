import os
import io
import json
import asyncio
import tempfile
import shutil
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
    src_path: str,
    lang: str = "auto",
    on_status: Optional[Callable[[str, str, str, int, float], None]] = None,
    storage_client=None,
) -> Tuple[str, Dict]:
    """
    Generate subtitles and write to storage via StorageClient.open_writer (remote-compatible stream writer).
    Returns (rel_vtt, meta).
    """
    loop = asyncio.get_running_loop()

    preprocess_mode = (YTCMS_AUDIO_PREPROCESS or "off").strip().lower()
    audio_codec = (YTCMS_AUDIO_CODEC or "mp3").strip().lower()
    audio_sr = int(YTCMS_AUDIO_SR)
    audio_ch = int(YTCMS_AUDIO_CHANNELS)
    audio_br = str(YTCMS_AUDIO_BITRATE or "48k")

    if storage_client is None:
        raise RuntimeError("storage_client required for remote-safe captions generation")

    tmp_dir = tempfile.mkdtemp(prefix="ytcms_")
    try:
        upload_path = src_path
        used_preprocess = "off"
        used_codec = None
        audio_tmp_path = None

        try:
            if preprocess_mode in ("demux", "transcode"):
                if preprocess_mode == "demux":
                    audio_tmp_path = os.path.join(tmp_dir, "captions.audio.bin")
                    ok = await async_extract_audio_demux(src_path, audio_tmp_path)
                    if ok:
                        upload_path = audio_tmp_path
                        used_preprocess = "demux"
                        used_codec = "copy"
                else:
                    exts = {"mp3": ".mp3", "opus": ".opus", "aac": ".m4a", "flac": ".flac", "wav": ".wav"}
                    ext = exts.get(audio_codec, ".mp3")
                    audio_tmp_path = os.path.join(tmp_dir, f"captions.audio{ext}")
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
        except Exception:
            upload_path = src_path
            used_preprocess = "off"
            used_codec = None

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

        captions_rel_dir = storage_client.join(storage_rel, "captions")
        vtt_rel = storage_client.join(captions_rel_dir, "captions.vtt")
        meta_rel = storage_client.join(captions_rel_dir, "captions.meta.json")

        # Create captions dir
        mk = storage_client.mkdirs(captions_rel_dir, exist_ok=True)
        if hasattr(mk, "__await__"):
            await mk

        # Prepare VTT payload
        vtt_payload = getattr(result, "vtt", None) or getattr(result, "content", "") or ""
        if not vtt_payload.endswith("\n"):
            vtt_payload = vtt_payload + "\n"
        vtt_bytes = vtt_payload.encode("utf-8")

        # Write VTT via open_writer
        w_vtt = storage_client.open_writer(vtt_rel, overwrite=True)
        if hasattr(w_vtt, "__await__"):
            w_vtt = await w_vtt
        if hasattr(w_vtt, "__aenter__"):
            async with w_vtt as f:
                wr = f.write(vtt_bytes)
                if hasattr(wr, "__await__"):
                    await wr
        else:
            with w_vtt as f:
                f.write(vtt_bytes)

        # Metedata
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
                "upload_path": os.path.basename(upload_path),
            },
        }
        meta_bytes = json.dumps(meta).encode("utf-8")

        w_meta = storage_client.open_writer(meta_rel, overwrite=True)
        if hasattr(w_meta, "__await__"):
            w_meta = await w_meta
        if hasattr(w_meta, "__aenter__"):
            async with w_meta as f:
                wr = f.write(meta_bytes)
                if hasattr(wr, "__await__"):
                    await wr
        else:
            with w_meta as f:
                f.write(meta_bytes)

        return vtt_rel, meta

    finally:
        try:
            shutil.rmtree(tmp_dir)
        except Exception:
            pass