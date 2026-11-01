"""Muse Spark client over the OpenAI-compatible Meta Model API. Owner: B.

TODO(B, day 1): confirm the model id, structured-output support and the video input
format on dev.meta.ai, then record them in docs/workstream-B-intelligence.md section 2.
"""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from tirekick.config import data_path, env

T = TypeVar("T", bound=BaseModel)

_client = None


def client():
    global _client
    if _client is None:
        from openai import OpenAI

        _client = OpenAI(
            api_key=env("META_API_KEY"),
            base_url=env("META_API_BASE", "https://api.meta.ai/v1"),
            timeout=120.0,
        )
    return _client


def model_id() -> str:
    return env("MUSE_MODEL", "muse-spark-1.3")


def image_part(path: str | Path) -> dict:
    data = base64.b64encode(Path(path).read_bytes()).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{data}"}}


def text_part(text: str) -> dict:
    return {"type": "text", "text": text}


def _log_raw(tag: str, payload: dict) -> None:
    path = data_path("runs", f"{int(time.time() * 1000)}_{tag}.json")
    path.write_text(json.dumps(payload, default=str, indent=2), encoding="utf-8")


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    return t.strip()


def muse_json(messages: list[dict], schema: type[T], temperature: float = 0.2,
              tag: str = "muse", retries: int = 3) -> T:
    """Call Muse Spark and parse the reply into `schema`.

    Tries JSON-schema structured output first; if the API rejects that parameter, falls back
    to "JSON only" + Pydantic validation with one repair retry. Raw outputs go to data/runs/.
    """
    json_schema = {"name": schema.__name__, "schema": schema.model_json_schema()}
    use_schema = True
    last_err: Exception | None = None
    msgs = list(messages)
    for attempt in range(retries):
        try:
            kwargs = {"model": model_id(), "messages": msgs, "temperature": temperature}
            if use_schema:
                kwargs["response_format"] = {"type": "json_schema", "json_schema": json_schema}
            resp = client().chat.completions.create(**kwargs)
            text = resp.choices[0].message.content or ""
            _log_raw(tag, {"attempt": attempt, "request_messages": len(msgs), "response": text})
            return schema.model_validate_json(_strip_fences(text))
        except ValidationError as e:  # model returned JSON that doesn't fit: ask it to repair once
            last_err = e
            msgs = msgs + [{"role": "user", "content": f"Your JSON failed validation: {e}. Reply with corrected JSON only."}]
        except Exception as e:  # noqa: BLE001 - API errors: schema unsupported, 429, 5xx
            last_err = e
            if use_schema and "response_format" in str(e):
                use_schema = False
                msgs = msgs + [{"role": "user", "content": "Reply with JSON only, matching this schema: "
                                + json.dumps(schema.model_json_schema())}]
                continue
            time.sleep(2 ** attempt)
    raise RuntimeError(f"muse_json failed after {retries} attempts: {last_err}")
