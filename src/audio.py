import io
from typing import List
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