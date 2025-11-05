import os
import logging
from typing import List, Dict, Tuple
from cartesia import AsyncCartesia
import io
from pydub import AudioSegment

CARTESIA_API_KEY_ENV = "CARTESIA_API_KEY"
CARTESIA_BASE = os.environ.get("CARTESIA_BASE", "https://api.cartesia.ai")  # override if needed
DEFAULT_FORMAT = "mp3"  # change to "wav" if preferred

logger = logging.getLogger(__name__)


def synthesize_cartesia(text: str, voice_id: str, fmt: str = DEFAULT_FORMAT, timeout: int = 30) -> bytes:
    """
    Synthesize `text` with Cartesia TTS and return raw audio bytes.
    Uses the official AsyncCartesia client (streams bytes).
    """
    key = os.environ.get(CARTESIA_API_KEY_ENV)
    if not key:
        raise RuntimeError(f"{CARTESIA_API_KEY_ENV} environment variable not set")

    # pick reasonable model and output spec based on requested fmt
    model_id = os.environ.get("CARTESIA_MODEL_ID", "sonic-3")
    language = os.environ.get("CARTESIA_LANGUAGE", "en")

    if fmt.lower() == "wav":
        output_format = {
            "container": "wav",
            "sample_rate": 44100,
            "encoding": "pcm_s16le",
        }
    else:
        # best-effort for mp3; adjust if your Cartesia plan requires different keys
        output_format = {
            "container": fmt.lower(),
            "sample_rate": 44100,
            "encoding": fmt.lower(),
        }

    async def _fetch_bytes():
        client = AsyncCartesia(api_key=key, base_url=CARTESIA_BASE)
        try:
            bytes_iter = client.tts.bytes(
                model_id=model_id,
                transcript=text,
                voice={
                    "mode": "id",
                    "id": voice_id,
                },
                language=language,
                output_format=output_format,
            )
            buf = bytearray()
            async for chunk in bytes_iter:
                buf.extend(chunk)
            return bytes(buf)
        finally:
            # attempt graceful close if supported
            try:
                await client.close()
            except Exception:
                pass

    import asyncio
    try:
        return asyncio.run(_fetch_bytes())
    except Exception as exc:
        logger.exception("Cartesia TTS request failed: %s", exc)
        raise


def synthesize_turns(turns: List[Dict], voice_map: Dict[str, str], fmt: str = DEFAULT_FORMAT,
                     persona_volume: Dict[str, float] = None,
                     persona_pause: Dict[str, int] = None,
                     global_volume_db: float = 0.0,
                     global_pause_ms: int = 120) -> List[Tuple[Dict, bytes]]:
    """
    Synthesize each turn to bytes and apply optional per-person or global
    volume (dB) and trailing pause (ms). Returns list of (turn, audio_bytes).
    If persona_volume or persona_pause is None, they are ignored.
    """
    persona_volume = persona_volume or {}
    persona_pause = persona_pause or {}

    results: List[Tuple[Dict, bytes]] = []
    for t in turns:
        speaker = t.get("speaker")
        text = t.get("text", "")
        if speaker not in voice_map:
            raise KeyError(f"No voice mapped for speaker: {speaker}")
        voice_id = voice_map[speaker]
        audio = synthesize_cartesia(text, voice_id, fmt)

        # load into AudioSegment, apply volume and append pause, then re-export bytes
        try:
            seg = AudioSegment.from_file(io.BytesIO(audio), format=fmt)
        except Exception:
            # best-effort: if pydub fails, fall back to raw bytes unchanged
            results.append((t, audio))
            continue

        # apply per-person override -> global fallback
        vol = persona_volume.get(speaker, None)
        if vol is None:
            vol = global_volume_db
        if isinstance(vol, (int, float)) and vol != 0.0:
            seg = seg + float(vol)

        pause_ms = persona_pause.get(speaker, None)
        if pause_ms is None:
            pause_ms = int(global_pause_ms or 0)
        if isinstance(pause_ms, int) and pause_ms > 0:
            seg = seg + AudioSegment.silent(duration=pause_ms)

        out_buf = io.BytesIO()
        seg.export(out_buf, format=fmt)
        out_bytes = out_buf.getvalue()
        results.append((t, out_bytes))
    return results


def save_audio_bytes(path: str, audio_bytes: bytes) -> None:
    """Write audio bytes to disk."""
    with open(path, "wb") as f:
        f.write(audio_bytes)
        print(f"Wrote audio to {path}")