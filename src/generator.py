import os
import json
import re
from typing import List, Dict, Any, Optional
import requests
from pathlib import Path

OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
OPENAI_CHAT_ENDPOINT = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-3.5-turbo"

# -----------------------------
# Prompt builder
# -----------------------------
def build_incremental_prompt(news_items: List[Dict[str, Any]],
                             personas: Dict[str, str],
                             previous_turns: List[Dict[str, str]],
                             target_turns_remaining: int = 40,
                             settings: Optional[Dict[str, Any]] = None) -> str:
    """
    Build a user prompt that includes previous dialogue, instructs the model
    to continue the conversation, and aims to produce multiple new turns.
    """
    persona_lines = "\n".join(f"{name}: {desc}" for name, desc in personas.items())
    headlines = "\n".join(
        f"- {i+1}. {it.get('title','').strip()} ({it.get('source','')}) — {it.get('summary','').strip()}"
        for i, it in enumerate(news_items)
    )

    settings_lines = []
    if settings:
        topics = settings.get("topics")
        if topics:
            if isinstance(topics, (list, tuple)):
                topics = ", ".join(str(t) for t in topics)
            settings_lines.append(f"Emphasize topics: {topics}")
        regions = settings.get("regions")
        if regions:
            if isinstance(regions, (list, tuple)):
                regions = ", ".join(str(r) for r in regions)
            settings_lines.append(f"Prefer regional angle(s): {regions}")
        pf = settings.get("profanity_filter")
        if pf is True:
            settings_lines.append("Profanity: avoid profanity; family-friendly language.")
        elif pf is False:
            settings_lines.append("Profanity: mild language allowed (occasional mild expletives OK).")

    settings_block = ("\n" + "\n".join(settings_lines) + "\n") if settings_lines else "\n"

    # Include previous dialogue
    prev_dialogue = json.dumps(previous_turns, ensure_ascii=False, indent=2) if previous_turns else "[]"

    prompt = (
        f"You will continue a fast-paced podcast script. "
        f"You should generate up to {target_turns_remaining} additional dialogue turns. "
        f"Each turn should be 1–3 sentences, energetic, witty, with follow-ups, callbacks, and jokes.\n\n"
        f"Hosts and personas:\n{persona_lines}\n\n"
        f"Headlines to cover:\n{headlines}\n\n"
        f"{settings_block}"
        f"Previous turns:\n{prev_dialogue}\n\n"
        "Requirements:\n"
        "- Output ONLY valid JSON: an array of objects with keys 'speaker' and 'text'.\n"
        "- 'speaker' must match one of the persona names exactly.\n"
        "- Keep each 'text' to 1–3 sentences; energetic banter, occasional light joke, quick transitions.\n"
        "- Cover each headline at least multiple times across the turns.\n"
        "- End with a short sign-off once the total target number of turns is reached.\n\n"
        "Return ONLY the JSON array and nothing else."
    )
    return prompt

# -----------------------------
# JSON parsing helpers
# -----------------------------
def _extract_json_array(text: str) -> Optional[str]:
    m = re.search(r"\[.*\]", text, flags=re.DOTALL)
    if not m:
        return None
    return m.group(0)

def parse_chat_output_to_turns(chat_output: str) -> List[Dict[str, str]]:
    def clean_json(s: str) -> str:
        s = re.sub(r",\s*([\]}])", r"\1", s)
        return s.strip()
    cleaned = clean_json(chat_output)
    try:
        parsed = json.loads(cleaned)
    except Exception:
        arr = _extract_json_array(cleaned)
        if not arr:
            raise ValueError("No JSON array found in model output")
        arr = clean_json(arr)
        parsed = json.loads(arr)
    if not isinstance(parsed, list):
        raise ValueError("Parsed JSON is not a list")
    turns = []
    for item in parsed:
        if not isinstance(item, dict):
            raise ValueError("Each turn must be an object")
        speaker = item.get("speaker")
        text = item.get("text")
        if not isinstance(speaker, str) or not isinstance(text, str):
            raise ValueError("Each turn must have 'speaker' and 'text' strings")
        turns.append({"speaker": speaker.strip(), "text": text.strip()})
    return turns

# -----------------------------
# OpenAI API call
# -----------------------------
def generate_script_with_openai(prompt: str,
                                model: str = DEFAULT_MODEL,
                                temperature: float = 0.8,
                                max_tokens: int = 1500,
                                api_key_env: str = OPENAI_API_KEY_ENV,
                                timeout: int = 60) -> str:
    key = os.environ.get(api_key_env)
    if not key:
        raise RuntimeError(f"{api_key_env} environment variable not set")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a creative writer that outputs strict JSON when asked."},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "n": 1,
    }
    resp = requests.post(OPENAI_CHAT_ENDPOINT, headers=headers, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    try:
        return data["choices"][0]["message"]["content"]
    except Exception as exc:
        raise RuntimeError(f"Unexpected OpenAI response shape: {exc}")

# -----------------------------
# Save output
# -----------------------------
def save_script_to_folder(turns: List[Dict[str, str]], out_dir: str, basename: str = "script") -> Dict[str, str]:
    p = Path(out_dir)
    p.mkdir(parents=True, exist_ok=True)
    json_path = p / f"{basename}.json"
    txt_path = p / f"{basename}.txt"
    with json_path.open("w", encoding="utf-8") as jf:
        json.dump(turns, jf, ensure_ascii=False, indent=2)
    with txt_path.open("w", encoding="utf-8") as tf:
        for t in turns:
            tf.write(f"{t['speaker']}: {t['text']}\n\n")
    return {"json": str(json_path), "txt": str(txt_path)}

# -----------------------------
# Incremental generation
# -----------------------------
def generate_turns_from_news(news_items: List[Dict[str, Any]],
                             personas: Dict[str, str],
                             total_turns: int = 40,
                             model: str = DEFAULT_MODEL,
                             save_dir: Optional[str] = None,
                             save_basename: str = "script",
                             settings: Optional[Dict[str, Any]] = None,
                             chunk_size: int = 5,
                             **openai_kwargs) -> List[Dict[str, str]]:
    """
    Generate a long podcast script in multiple incremental GPT calls,
    appending previous dialogue each time, and save each incremental prompt.
    """
    all_turns: List[Dict[str, str]] = []

    # Create output and prompts folders
    if save_dir is None:
        save_dir = str(Path("./out"))
    Path(save_dir).mkdir(parents=True, exist_ok=True)
    prompts_dir = Path(save_dir) / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)

    iteration = 1
    while len(all_turns) < total_turns:
        turns_remaining = total_turns - len(all_turns)
        prompt = build_incremental_prompt(
            news_items, personas, all_turns,
            target_turns_remaining=min(chunk_size, turns_remaining),
            settings=settings
        )

        # Save the prompt for this iteration
        prompt_file = prompts_dir / f"prompt_{iteration:03d}.txt"
        prompt_file.write_text(prompt, encoding="utf-8")
        print(f"Saved prompt for iteration {iteration} to {prompt_file}")

        # Call OpenAI
        raw = generate_script_with_openai(prompt, model=model, **openai_kwargs)
        new_turns = parse_chat_output_to_turns(raw)
        print(f"Generated {len(new_turns)} new turns.")

        all_turns.extend(new_turns)

        # Safety: prevent infinite loop
        if len(new_turns) == 0:
            print("No new turns generated, stopping early.")
            break

        iteration += 1

    # Save final output
    saved = save_script_to_folder(all_turns, save_dir, basename=save_basename)
    raw_path = Path(save_dir) / f"{save_basename}.raw.txt"
    raw_path.write_text(json.dumps(all_turns, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote final script to {saved['json']} and {saved['txt']}")

    return all_turns
