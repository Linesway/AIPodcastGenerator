# Two‑Host Newscast — README

A small pipeline that: fetches news, asks ChatGPT to write a short two‑host script, synthesizes each turn with Cartesia TTS, and assembles an episode MP3.

Features:
- Intro/Outro Music if provided
- Filters for profanity/topics/regions etc.
- Target podcast length
- Pause durations between speakers
- Ability to have more than 2 hosts
- Personas

Example:
[example.mp3](https://github.com/user-attachments/files/23374651/example.mp3)

# Requirements
- Python 3.8+
- ffmpeg installed and on PATH (see below)
- NewsAPI key
- A Cartesia TTS API key
- OpenAI key

Install ffmpeg if not installed already:
winget install --id=Gyan.FFmpeg -e

1. Ensure a .env file exists in the main folder. /.env.example can be used as a reference. 

2. Modify the personas file to adjust voices, personalities, filters, names, etc.
- `./personas.json` must be an object mapping persona name -> object with `description` and `voice` keys.
- Intro/Outro music is optional and can be defined in `./personas.json`

# Running the app (from repository root)

Example 1:
```powershell
python main.py --personas personas.json --minutes 7 --topics tech,world
```

Example 2:
```powershell
python main.py --personas personas.json --topics "tech,world" --regions "US" --minutes 2 --output "news-briefing.mp3"  --format mp3
  ```

Notes
- Ensure `ffmpeg` is on PATH before running the app; pydub uses it to read/export audio.
- `./out` contains the output news, podcast script, and intermediate prompts.
- Keep API keys out of version control; use environment variables or a local `.env`.

Intro/Outro Music (Creative Commons)
https://transistor.fm/free-podcast-intro-music/
