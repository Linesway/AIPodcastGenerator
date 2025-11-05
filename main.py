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
    apply_intro_outro,
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
    p.add_argument("--topics", help="Comma-separated topics/queries (e.g. 'tech,world')")  # moved out of personas
    p.add_argument("--regions", help="Optional comma-separated regions (e.g. 'US,Europe')")
    p.add_argument("--personas", default="personas.json", help="Path to personas.json")
    p.add_argument("--voice-map", help="Optional path to JSON mapping speaker->cartesia_voice_id")
    p.add_argument("--output", default="episode.mp3")
    p.add_argument("--format", default="mp3", help="Audio format returned by TTS (mp3/wav)")
    p.add_argument("--length", type=int, default=90, help="Target length in seconds for script")
    p.add_argument("--minutes", type=float, help="Target length in minutes (overrides --length)")
    args = p.parse_args()

    # load personas file — require format:
    # "Name": {"description": "...", "voice": "cartesia-voice-id"}
    raw_personas = load_json(args.personas)

    # support optional top-level settings in personas.json
    settings = {}
    if isinstance(raw_personas, dict) and "settings" in raw_personas:
        settings = raw_personas.pop("settings") or {}

    # topics: prefer --topics CLI; fallback to personas.settings.topics for backward compatibility
    topics = []
    if args.topics:
        topics = [t.strip() for t in args.topics.split(",") if t.strip()]
    if not topics:
        raise SystemExit("No topics provided. Pass --topics (comma-separated).")
    
    # regions: CLI overrides; if provided, add into settings passed to generator
    if args.regions:
        settings["regions"] = [r.strip() for r in args.regions.split(",") if r.strip()]
    else:
        settings.pop("regions", None)  # ensure regions is **not** inherited accidentally

    personas = {}
    voice_map = {}
    persona_volume = {}   # optional per-persona dB adjustments (float)
    persona_pause = {}    # optional per-persona pause after turn (ms)

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

        # optional per-persona settings
        vol = val.get("volume_db")
        if isinstance(vol, (int, float)):
            persona_volume[name] = float(vol)
        pause = val.get("pause_ms")
        if isinstance(pause, int):
            persona_pause[name] = pause

    # Allow CARTESIA_VOICE_<NAME> env vars to override embedded voices
    for name in list(personas.keys()):
        env_key = f"CARTESIA_VOICE_{name.upper()}"
        env_val = os.environ.get(env_key)
        if env_val:
            voice_map[name] = env_val

    if len(voice_map) < 1:
        raise RuntimeError("No CARTESIA voice IDs found; provide them in personas.json or as CARTESIA_VOICE_<NAME> env vars.")
    
    # compute target length (seconds) — priority: --minutes arg > --length
    target_length_sec = args.length
    if getattr(args, "minutes", None) is not None:
        try:
            target_length_sec = int(float(args.minutes) * 60)
        except Exception:
            pass

    # Fetch headlines
    news = fetch_news(topics, max_articles=6)
    if not news:
        raise SystemExit("No news fetched for topics")

    # Ensure topics are passed into the generator via settings
    settings["topics"] = topics

    # Decide on total_turns: optionally derive from target_length_sec
    # Assume ~20 words per turn, ~120 WPM average speaking rate including pauses
    wpm = 120
    words_total = (wpm / 60.0) * target_length_sec
    approx_turns = max(int(words_total / 20), 5)  # ensure at least 5 turns

    # Call the new incremental generator
    turns = generate_turns_from_news(
        news_items=news,
        personas=personas,
        total_turns=approx_turns,
        save_dir="./out",
        save_basename="podcast_script",
        settings=settings,
        chunk_size=5,  # number of turns per GPT call
    )
    # Synthesize each turn to bytes
    # global pause (ms) and global volume_db (applied per-turn in TTS)
    global_pause_ms = int(settings.get("pause_ms", 120))
    global_volume_db = float(settings.get("volume_db", 0.0) or 0.0)
    synthesized = synthesize_turns(
        turns,
        voice_map,
        fmt=args.format,
        persona_volume=persona_volume,
        persona_pause=persona_pause,
        global_volume_db=global_volume_db,
        global_pause_ms=global_pause_ms,
    )

    # Convert bytes to AudioSegments and assemble
    segs = []
    for turn, audio_bytes in synthesized:
        seg = audiosegment_from_bytes(audio_bytes, fmt=args.format)
        # tts already applied per-person/global volume and trailing pause
        segs.append(seg)
    final = concatenate_audio(segs, crossfade_ms=0)
    final = normalize_loudness(final, target_dbfs=-16.0)

    final = apply_intro_outro(final, settings)

    # apply a global volume adjustment if requested
    if global_volume_db != 0.0:
        final = final + global_volume_db

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    save_audio(final, str(out_path), format=args.format)
    print(f"Wrote {out_path} ({final.duration_seconds:.1f}s)")

if __name__ == "__main__":
    main()