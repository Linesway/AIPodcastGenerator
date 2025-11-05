import os
import json
import argparse
from pathlib import Path

# add dotenv support to auto-load .env/
from dotenv import load_dotenv

from src.news import fetch_news
from src.generator import generate_turns_from_news
from src.tts import synthesize_turns
from src.audio import (
    audiosegment_from_bytes,
    concatenate_audio,
    normalize_loudness,
    save_audio,
)
from pydub import AudioSegment

def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def infer_voice_map(personas: dict):
    """
    Infer voice ids from env vars named CARTESIA_VOICE_<UPPER_NAME>,
    e.g. CARTESIA_VOICE_ALEX. Returns dict speaker->voice_id or raises.
    """
    vm = {}
    for name in personas.keys():
        env_key = f"CARTESIA_VOICE_{name.upper()}"
        val = os.environ.get(env_key)
        if val:
            vm[name] = val
    if len(vm) < 1:
        raise RuntimeError("No CARTESIA_VOICE_<NAME> env vars found. Provide voice_map via --voice-map or set envs.")
    return vm

def main():
    # Load environment variables from common dotenv locations.
    # This will NOT override already-set environment variables.
    load_dotenv(dotenv_path=".env", override=False)

    p = argparse.ArgumentParser(description="Produce a 2-host newscast audio file.")
    p.add_argument("--topics", required=True, help="Comma-separated topics/queries (e.g. 'tech,world')")
    p.add_argument("--personas", default="project/personas.json", help="Path to personas.json")
    p.add_argument("--voice-map", help="Optional path to JSON mapping speaker->cartesia_voice_id")
    p.add_argument("--output", default="episode.mp3")
    p.add_argument("--format", default="mp3", help="Audio format returned by TTS (mp3/wav)")
    p.add_argument("--length", type=int, default=90, help="Target length in seconds for script")
    args = p.parse_args()

    topics = [t.strip() for t in args.topics.split(",") if t.strip()]
    if not topics:
        raise SystemExit("No topics provided")

    # load personas file — require format:
    # "Name": {"description": "...", "voice": "cartesia-voice-id"}
    raw_personas = load_json(args.personas)
    personas = {}
    voice_map = {}

    for name, val in raw_personas.items():
        if not isinstance(val, dict):
            raise RuntimeError(
                f"Invalid personas.json format: each persona must be an object with 'description' and 'voice' (invalid entry for {name})"
            )
        description = val.get("description")
        voice = val.get("voice")
        if not isinstance(description, str) or not description.strip():
            raise RuntimeError(f"Missing or invalid 'description' for persona {name}")
        if not isinstance(voice, str) or not voice.strip():
            raise RuntimeError(f"Missing or invalid 'voice' for persona {name}")
        personas[name] = description.strip()
        voice_map[name] = voice.strip()

    # Allow CARTESIA_VOICE_<NAME> env vars to override embedded voices
    for name in list(personas.keys()):
        env_key = f"CARTESIA_VOICE_{name.upper()}"
        env_val = os.environ.get(env_key)
        if env_val:
            voice_map[name] = env_val

    if len(voice_map) < 1:
        raise RuntimeError("No CARTESIA voice IDs found; provide them in personas.json or as CARTESIA_VOICE_<NAME> env vars.")

    # Fetch headlines
    news = fetch_news(topics, max_articles=6)
    if not news:
        raise SystemExit("No news fetched for topics")

    # Generate script turns
    turns = generate_turns_from_news(news, personas, target_length_sec=args.length)

    # Synthesize each turn to bytes
    synthesized = synthesize_turns(turns, voice_map, fmt=args.format)

    # Convert bytes to AudioSegments and assemble
    segs = []
    for turn, audio_bytes in synthesized:
        seg = audiosegment_from_bytes(audio_bytes, fmt=args.format)
        # add a tiny pause after each turn
        segs.append(seg + AudioSegment.silent(duration=120))
    final = concatenate_audio(segs, crossfade_ms=0)
    final = normalize_loudness(final, target_dbfs=-16.0)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    save_audio(final, str(out_path), format=args.format)
    print(f"Wrote {out_path} ({final.duration_seconds:.1f}s)")

if __name__ == "__main__":
    main()