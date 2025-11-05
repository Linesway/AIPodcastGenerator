# Two‑Host Newscast — README

A small pipeline that: fetches news, asks ChatGPT to write a short two‑host script, synthesizes each turn with Cartesia TTS, and assembles an episode MP3.

Prereqs
- Python 3.8+
- ffmpeg installed and on PATH (see below)

Install ffmpeg
winget install --id=Gyan.FFmpeg -e

Add a .env file in the main folder
# .env example
NEWSAPI_KEY= 
OPENAI_API_KEY=
CARTESIA_API_KEY=

Personas file (required format)
- `project/personas.json` must be an object mapping persona name -> object with `description` and `voice` keys.
- Example:
```json
{
  "Alex": {
    "description": "Energetic, upbeat host — quick jokes, enthusiastic transitions.",
    "voice": "cartesia-voice-id-for-alex"
  },
  "Sam": {
    "description": "Dry-witted co-host — concise and skeptical.",
    "voice": "cartesia-voice-id-for-sam"
  }
}
```

# run the app (from repository root)
```powershell
python main.py --personas personas.json --minutes 7 --topics tech,world
```

Notes
- Ensure `ffmpeg` is on PATH before running the app; pydub uses it to read/export audio.
- If you see "No module named project", run from the repository root or set `PYTHONPATH="."`.
- Keep API keys out of version control; use environment variables or a local `.env`.
