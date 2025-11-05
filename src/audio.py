import io
import os
from typing import List, Optional
from pydub import AudioSegment

def audiosegment_from_bytes(audio_bytes: bytes, fmt: str = "mp3") -> AudioSegment:
    """Load audio bytes (mp3/wav) into a pydub.AudioSegment."""
    return AudioSegment.from_file(io.BytesIO(audio_bytes), format=fmt)

def concatenate_audio(segments: List[AudioSegment], crossfade_ms: int = 0) -> AudioSegment:
    """Concatenate a list of AudioSegment objects. Optionally crossfade between segments."""
    if not segments:
        return AudioSegment.silent(duration=0)
    out = segments[0]
    for seg in segments[1:]:
        if crossfade_ms > 0:
            out = out.append(seg, crossfade=crossfade_ms)
        else:
            out = out + seg
    return out

def normalize_loudness(segment: AudioSegment, target_dbfs: float = -16.0) -> AudioSegment:
    """Normalize loudness to a target dBFS."""
    change_dB = target_dbfs - segment.dBFS
    return segment.apply_gain(change_dB)

def save_audio(segment: AudioSegment, path: str, format: str = "mp3") -> None:
    """Export the AudioSegment to disk."""
    segment.export(path, format=format)

    
def load_optional_audio(path: Optional[str]) -> Optional[AudioSegment]:
    """Load an audio file if path is provided and exists."""
    if not path:
        return None
    if not os.path.isfile(path):
        print(f"[warn] Intro/Outro file not found: {path}")
        return None
    return AudioSegment.from_file(path)

def apply_intro_outro(main_audio: AudioSegment, settings: dict) -> AudioSegment:
    """
    Wrap main audio with intro/outro if defined in settings.
    Applies optional music volume adjustment.
    """
    intro = load_optional_audio(settings.get("intro"))
    outro = load_optional_audio(settings.get("outro"))
    music_vol = settings.get("music_volume_db", 0.0)

    if intro:
        intro = intro.apply_gain(music_vol)

    if outro:
        outro = outro.apply_gain(music_vol)

    segments = []
    if intro:
        segments.append(intro)

    segments.append(main_audio)

    if outro:
        segments.append(outro)

    return concatenate_audio(segments, crossfade_ms=0)