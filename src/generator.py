import os
import json
import re
from typing import List, Dict, Any, Optional
import requests
from pathlib import Path

OPENAI_API_KEY_ENV = "OPENAI_API_KEY"
OPENAI_CHAT_ENDPOINT = "https://api.openai.com/v1/chat/completions"
DEFAULT_MODEL = "gpt-3.5-turbo"

def build_prompt(news_items: List[Dict[str, Any]],
                 personas: Dict[str, str],
                 target_length_sec: int = 90,
                 max_turns: int = 12) -> str:
    """
    Build a user prompt describing the personas and headlines.
    Instruct the model to return only JSON: an array of turns [{"speaker":"A","text":"..."}...].
    """
    persona_lines = "\n".join(f"{name}: {desc}" for name, desc in personas.items())
    headlines = "\n".join(
        f"- {i+1}. {it.get('title','').strip()} ({it.get('source','')}) — {it.get('summary','').strip()}"
        for i, it in enumerate(news_items)
    )
    prompt = (
        f"You will write a short, fast-paced podcast script ({target_length_sec} seconds total, "
        f"~{max_turns} short turns). Hosts and personas:\n\n{persona_lines}\n\n"
        f"Headlines to cover:\n{headlines}\n\n"
        "Requirements:\n"
        "- Output ONLY valid JSON: an array of objects with keys 'speaker' and 'text'.\n"
        "- 'speaker' must match one of the persona names exactly.\n"
        "- Keep each 'text' to 1-2 short sentences; energetic banter, occasional light joke, quick transitions.\n"
        "- Cover each headline at least briefly across the turns.\n"
        "- End with a short sign-off from both hosts.\n\n"
        "Example output:\n"
        "[{\"speaker\":\"HostA\",\"text\":\"...\"}, {\"speaker\":\"HostB\",\"text\":\"...\"}, ...]\n\n"
        "Return only the JSON array and nothing else."
    )
    return prompt

def _extract_json_array(text: str) -> Optional[str]:
    """Find the first JSON array in text and return it, else None."""
    # Look for the first balanced [] block - simple regex to find [ ... ]
    m = re.search(r"\[.*\]", text, flags=re.DOTALL)
    if not m:
        return None
    return m.group(0)

def parse_chat_output_to_turns(chat_output: str) -> List[Dict[str, str]]:
    """
    Parse a model output (string) into a list of turns.
    Attempts direct json.loads, then tries to extract a JSON array substring.
    Raises ValueError on failure.
    """
    try:
        parsed = json.loads(chat_output)
    except Exception:
        arr = _extract_json_array(chat_output)
        if not arr:
            raise ValueError("No JSON array found in model output")
        parsed = json.loads(arr)

    if not isinstance(parsed, list):
        raise ValueError("Parsed JSON is not a list")
    # Validate minimal structure
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

def generate_script_with_openai(prompt: str,
                                model: str = DEFAULT_MODEL,
                                temperature: float = 0.8,
                                max_tokens: int = 700,
                                api_key_env: str = OPENAI_API_KEY_ENV,
                                timeout: int = 30) -> str:
    """
    Call OpenAI Chat Completions API and return the assistant content as string.
    Requires OPENAI_API_KEY in env (or custom api_key_env).
    """
    key = os.environ.get(api_key_env)
    if not key:
        raise RuntimeError(f"{api_key_env} environment variable not set")

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
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
    # defensive extraction
    try:
        content = data["choices"][0]["message"]["content"]
    except Exception as exc:
        raise RuntimeError(f"Unexpected OpenAI response shape: {exc}")

    return content

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


def generate_turns_from_news(news_items: List[Dict[str, Any]],
                             personas: Dict[str, str],
                             target_length_sec: int = 90,
                             model: str = DEFAULT_MODEL,
                             save_dir: Optional[str] = None,
                             save_basename: str = "script",
                             **openai_kwargs) -> List[Dict[str, str]]:
    """
    Convenience: build prompt, call OpenAI, parse JSON, and return turns.
    """
    prompt = build_prompt(news_items, personas, target_length_sec)
    raw = generate_script_with_openai(prompt, model=model, **openai_kwargs)
    turns = parse_chat_output_to_turns(raw)

    # default save directory -> project/generated (relative to repo)
    if save_dir is None:
        # generator.py is in project/src -> project is two parents up from this file
        repo_project_dir = Path(__file__).resolve().parents[1]
        default_dir = repo_project_dir / "generated"
        save_dir = str(default_dir)

    out = Path(save_dir)
    out.mkdir(parents=True, exist_ok=True)
    # save parsed turns
    save_script_to_folder(turns, save_dir, basename=save_basename)
    # also save raw model output for debugging
    raw_path = out / f"{save_basename}.raw.txt"
    raw_path.write_text(raw, encoding="utf-8")

    return turns