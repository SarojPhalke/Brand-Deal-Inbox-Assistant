import os
import re
import time

from dotenv import load_dotenv
from pydantic import ValidationError
from google import genai
from google.genai import types

load_dotenv()
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")  # override in .env if unavailable
_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


def _call_gemini(system: str, user: str) -> str:
    resp = _client.models.generate_content(
        model=MODEL,
        contents=user,
        config=types.GenerateContentConfig(
            system_instruction=system,
            temperature=0,
            response_mime_type="application/json",
        ),
    )
    return resp.text or ""


def _strip_fences(raw: str) -> str:
    # Safety net in case the model wraps JSON in ```json fences anyway.
    return re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())


def call_json(system: str, user: str, model_cls, retries: int = 2):
    last_err = None
    for attempt in range(retries + 1):
        prompt = user if last_err is None else (
            f"{user}\n\nYour previous reply was invalid: {last_err}\n"
            "Return only valid JSON matching the schema."
        )
        try:
            raw = _strip_fences(_call_gemini(system, prompt))
            return model_cls.model_validate_json(raw)
        except ValidationError as e:
            last_err = str(e)[:500]
        except Exception as e:  # rate limit, network, auth
            last_err = f"API error: {e}"
            time.sleep(2 ** attempt * 4)
    print(f"[llm] giving up after {retries + 1} attempts: {last_err}")
    return None