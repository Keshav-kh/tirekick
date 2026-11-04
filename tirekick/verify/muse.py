"""Muse Spark client over the OpenAI-compatible Meta Model API. Owner: B.

Confirmed facts are recorded in docs/workstream-B-intelligence.md section 2 ("API notes"). In short:
- base URL https://api.meta.ai/v1, OpenAI Python SDK, model `muse-spark-1.3`
- Chat Completions: structured output via response_format={"type": "json_schema", ...};
  images as `image_url` parts (public URL or base64 data URL), user messages only, ~50 per request
- Responses API: structured output via text.format (NOT response_format), built-in
  `web_search` tool (Responses only) with `url_citation` annotations on output_text blocks
- retry 429 / 5xx / timeouts with backoff; never retry 400 / 401 / 404

Every call is logged to data/runs/{ms}_{tag}.json (request summary without base64 blobs,
raw response text, usage, latency, error) so C can evaluate and B can debug.
"""

from __future__ import annotations

import base64
import copy
import json
import logging
import mimetypes
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, TypeVar

from pydantic import BaseModel, ValidationError

from tirekick.config import data_path, env

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL = "muse-spark-1.3"
DEFAULT_BASE = "https://api.meta.ai/v1"
TIMEOUT_S = 120.0
BACKOFF_S = (1.0, 2.0, 4.0)      # waits between attempts on 429 / 5xx / timeout
INLINE_LIMIT_BYTES = 50 * 1024 * 1024  # documented inline (base64) limit per media item

_client = None
_log_lock = threading.Lock()
_log_seq = 0
_sleep: Callable[[float], None] = time.sleep  # tests monkeypatch this


class MuseError(RuntimeError):
    """A model call failed after retries (or permanently, e.g. HTTP 400)."""


# --------------------------------------------------------------------------- client + config


def api_key() -> str:
    # Our .env uses META_API_KEY; Meta's own docs and cookbook use MODEL_API_KEY. Accept both.
    return env("META_API_KEY") or env("MODEL_API_KEY")


def available() -> bool:
    return bool(api_key())


def client():
    global _client
    if _client is None:
        from openai import OpenAI

        # max_retries=0: the retry policy lives in _with_retries so it's logged and testable.
        _client = OpenAI(api_key=api_key() or "missing", base_url=env("META_API_BASE", DEFAULT_BASE),
                         timeout=TIMEOUT_S, max_retries=0)
    return _client


def model_id() -> str:
    return env("MUSE_MODEL", DEFAULT_MODEL)


# --------------------------------------------------------------------------- content parts


def _data_url(path: str | Path, default_mime: str) -> str:
    p = Path(path)
    mime = mimetypes.guess_type(p.name)[0] or default_mime
    return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode('ascii')}"


def image_part(path: str | Path) -> dict:
    """Chat Completions image part (base64 data URL). Images must go in a user message."""
    return {"type": "image_url", "image_url": {"url": _data_url(path, "image/jpeg")}}


def text_part(text: str) -> dict:
    return {"type": "text", "text": text}


def video_part_chat(path: str | Path, fps: float | None = None) -> dict:
    """Chat Completions video part. UNVERIFIED live: Meta's docs disagree on whether Chat
    Completions accepts video; proof_take tries the Responses form first."""
    part: dict = {"type": "video_url", "video_url": {"url": _data_url(path, "video/mp4")}}
    if fps:
        part["video_url"]["fps"] = fps
    return part


def video_part_responses(path: str | Path | None = None, file_id: str | None = None) -> dict:
    """Responses API `input_video` block: base64 data URL inline, or a Files API id."""
    if file_id:
        return {"type": "input_video", "file_id": file_id}
    return {"type": "input_video", "video_url": _data_url(path, "video/mp4")}


def upload_file(path: str | Path, purpose: str = "user_data") -> str:
    """Files API upload (the documented route for media over the inline limit)."""
    p = Path(path)
    mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    uploaded = _with_retries("upload", {"file": p.name, "bytes": p.stat().st_size},
                             lambda: client().files.create(file=(p.name, p.read_bytes(), mime), purpose=purpose))
    return uploaded.id


# --------------------------------------------------------------------------- logging


def _redact(obj: Any) -> Any:
    """Copy of a request with base64 media replaced by a size marker (keeps logs small)."""
    if isinstance(obj, dict):
        return {k: _redact(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact(v) for v in obj]
    if isinstance(obj, str) and obj.startswith("data:") and ";base64," in obj[:80]:
        return f"<{obj[5:obj.index(';')]} data URL, {len(obj)} chars>"
    return obj


def log_run(tag: str, payload: dict) -> Path:
    """data/runs/{ms}_{seq}_{tag}.json; the sequence number keeps parallel runs from colliding."""
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", tag)
    with _log_lock:
        global _log_seq
        _log_seq += 1
        seq = _log_seq
    path = data_path("runs", f"{int(time.time() * 1000)}_{seq:05d}_{safe}.json")
    try:
        path.write_text(json.dumps(payload, default=str, indent=2), encoding="utf-8")
    except OSError as e:  # logging must never break a call
        log.warning("could not write %s: %s", path, e)
    return path


def _usage(resp: Any) -> Any:
    u = getattr(resp, "usage", None)
    if u is None:
        return None
    return u.model_dump() if hasattr(u, "model_dump") else u


# --------------------------------------------------------------------------- retry policy


def _status(e: Exception) -> int | None:
    return getattr(e, "status_code", None)


def _retryable(e: Exception) -> bool:
    try:
        import openai
    except ImportError:  # pragma: no cover
        return False
    if isinstance(e, (openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError)):
        return True
    status = _status(e)
    return status is not None and (status == 429 or status >= 500)


def _with_retries(tag: str, request: dict, fn: Callable[[], Any]) -> Any:
    """Run fn with backoff on 429 / 5xx / timeout / connection errors. Logs every attempt."""
    attempts = len(BACKOFF_S) + 1
    for attempt in range(attempts):
        t0 = time.time()
        try:
            resp = fn()
            return resp
        except Exception as e:  # noqa: BLE001
            log_run(f"{tag}_error", {"attempt": attempt, "request": _redact(request), "error": repr(e),
                                     "status": _status(e), "latency_s": round(time.time() - t0, 2)})
            if _retryable(e) and attempt < attempts - 1:
                _sleep(BACKOFF_S[attempt])
                continue
            raise
    raise MuseError("unreachable")  # pragma: no cover


# --------------------------------------------------------------------------- JSON helpers


def _strip_fences(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    return t.strip()


def extract_json(text: str) -> str:
    """Best effort: the JSON object/array inside a reply that may have prose or fences around it."""
    t = _strip_fences(text)
    if t[:1] in "{[":
        return t
    starts = [i for i in (t.find("{"), t.find("[")) if i >= 0]
    if not starts:
        return t
    start = min(starts)
    end = max(t.rfind("}"), t.rfind("]"))
    return t[start:end + 1] if end > start else t


def strict_schema(schema: type[BaseModel]) -> dict:
    """Pydantic JSON schema made friendly for constrained decoding: $refs inlined (Meta rejects
    recursive $ref; inlining also avoids dialect differences), every object closed with
    additionalProperties=false and all keys required (nullable fields stay nullable)."""
    raw = schema.model_json_schema()
    defs = raw.pop("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                target = copy.deepcopy(defs[node["$ref"].split("/")[-1]])
                return walk(target)
            out: dict = {}
            for k, v in node.items():
                if k in ("default", "title"):        # schema keywords, not data
                    continue
                if k == "properties":                # keys here are field names: keep them all
                    out[k] = {name: walk(sub) for name, sub in v.items()}
                else:
                    out[k] = walk(v)
            if out.get("type") == "object" and "properties" in out:
                out["additionalProperties"] = False
                out["required"] = list(out["properties"].keys())
            return out
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(raw)


def _validate(text: str, schema: type[T]) -> T:
    return schema.model_validate_json(extract_json(text))


def _bad_request(e: Exception) -> bool:
    return _status(e) == 400


# --------------------------------------------------------------------------- Chat Completions


def chat_text(messages: list[dict], temperature: float | None = 0.4, tag: str = "chat") -> str:
    """Plain text completion (used by the negotiation agent)."""
    kwargs: dict = {"model": model_id(), "messages": messages}
    if temperature is not None:
        kwargs["temperature"] = temperature
    t0 = time.time()
    try:
        resp = _with_retries(tag, kwargs, lambda: client().chat.completions.create(**kwargs))
    except Exception as e:  # noqa: BLE001
        if temperature is not None and _bad_request(e) and "temperature" in str(e).lower():
            return chat_text(messages, temperature=None, tag=tag)
        raise
    text = resp.choices[0].message.content or ""
    log_run(tag, {"api": "chat.completions", "request": _redact(kwargs), "response": text,
                  "usage": _usage(resp), "latency_s": round(time.time() - t0, 2)})
    return text


def muse_json(messages: list[dict], schema: type[T], temperature: float | None = 0.2,
              tag: str = "muse", retries: int = 3) -> T:
    """Call Muse Spark (Chat Completions) and parse the reply into `schema`.

    1. response_format json_schema (constrained decoding, documented on Chat Completions).
    2. If the API rejects that with a 400, fall back to "JSON only" + the schema in the prompt.
    3. If the reply fails Pydantic validation, retry once with the error appended.
    429 / 5xx / timeouts are retried with backoff inside each attempt. Raises MuseError.
    """
    use_schema = True
    use_temperature = temperature is not None
    repaired = False
    msgs = list(messages)
    last_err: Exception | None = None
    for _ in range(retries + 1):
        kwargs: dict = {"model": model_id(), "messages": msgs}
        if use_temperature:
            kwargs["temperature"] = temperature
        if use_schema:
            kwargs["response_format"] = {"type": "json_schema", "json_schema": {
                "name": schema.__name__, "schema": strict_schema(schema)}}
        t0 = time.time()
        try:
            resp = _with_retries(tag, kwargs, lambda: client().chat.completions.create(**kwargs))
        except Exception as e:  # noqa: BLE001
            last_err = e
            msg = str(e).lower()
            if _bad_request(e) and use_temperature and "temperature" in msg:
                use_temperature = False
                continue
            if _bad_request(e) and use_schema:
                use_schema = False
                msgs = msgs + [{"role": "user", "content": "Reply with JSON only (no prose, no code fences), "
                                "matching this JSON schema:\n" + json.dumps(strict_schema(schema))}]
                continue
            raise MuseError(f"{tag}: model call failed: {e}") from e
        text = resp.choices[0].message.content or ""
        log_run(tag, {"api": "chat.completions", "structured": use_schema, "request": _redact(kwargs),
                      "response": text, "usage": _usage(resp), "latency_s": round(time.time() - t0, 2)})
        try:
            return _validate(text, schema)
        except (ValidationError, ValueError) as e:
            last_err = e
            if repaired:
                break
            repaired = True
            msgs = msgs + [{"role": "assistant", "content": text},
                           {"role": "user", "content": f"Your JSON failed validation: {e}. Reply with corrected JSON only."}]
    raise MuseError(f"{tag}: no valid JSON after retries: {last_err}")


# --------------------------------------------------------------------------- Responses API


def responses_json(content: list[dict], schema: type[T], instructions: str | None = None,
                   temperature: float | None = 0.2, tag: str = "muse_responses") -> T:
    """Responses API + text.format json_schema (used for native video). Same fallbacks as muse_json."""
    use_schema = True
    use_temperature = temperature is not None
    repaired = False
    extra: list[dict] = []
    last_err: Exception | None = None
    for _ in range(4):
        kwargs: dict = {"model": model_id(), "input": [{"role": "user", "content": content + extra}]}
        if instructions:
            kwargs["instructions"] = instructions
        if use_temperature:
            kwargs["temperature"] = temperature
        if use_schema:
            kwargs["text"] = {"format": {"type": "json_schema", "name": schema.__name__,
                                         "schema": strict_schema(schema)}}
        t0 = time.time()
        try:
            resp = _with_retries(tag, kwargs, lambda: client().responses.create(**kwargs))
        except Exception as e:  # noqa: BLE001
            last_err = e
            msg = str(e).lower()
            if _bad_request(e) and use_temperature and "temperature" in msg:
                use_temperature = False
                continue
            if _bad_request(e) and use_schema and ("text" in msg or "format" in msg or "schema" in msg):
                use_schema = False
                extra = extra + [{"type": "input_text", "text": "Reply with JSON only (no prose, no code fences), "
                                  "matching this JSON schema:\n" + json.dumps(strict_schema(schema))}]
                continue
            raise MuseError(f"{tag}: model call failed: {e}") from e
        text = getattr(resp, "output_text", "") or ""
        log_run(tag, {"api": "responses", "structured": use_schema, "request": _redact(kwargs),
                      "response": text, "usage": _usage(resp), "latency_s": round(time.time() - t0, 2)})
        try:
            return _validate(text, schema)
        except (ValidationError, ValueError) as e:
            last_err = e
            if repaired:
                break
            repaired = True
            extra = extra + [{"type": "input_text", "text": f"Your previous JSON failed validation: {e}. "
                              "Reply with corrected JSON only."}]
    raise MuseError(f"{tag}: no valid JSON after retries: {last_err}")


@dataclass
class Citation:
    url: str
    title: str = ""
    start_index: int | None = None
    end_index: int | None = None


@dataclass
class SearchResult:
    text: str
    citations: list[Citation] = field(default_factory=list)
    searched: bool = False           # did the model actually run a web_search_call?
    raw: dict = field(default_factory=dict)


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def parse_search_response(resp: Any) -> SearchResult:
    """Pull answer text, url_citation annotations and whether a search ran from a Responses object
    (SDK object or plain dict with the same wire fields)."""
    texts: list[str] = []
    cites: list[Citation] = []
    searched = False
    for item in _get(resp, "output", []) or []:
        kind = _get(item, "type")
        if kind == "web_search_call":
            searched = True
        if kind != "message":
            continue
        for block in _get(item, "content", []) or []:
            if _get(block, "type") != "output_text":
                continue
            texts.append(_get(block, "text", "") or "")
            for ann in _get(block, "annotations", []) or []:
                if _get(ann, "type") == "url_citation" and _get(ann, "url"):
                    cites.append(Citation(url=_get(ann, "url"), title=_get(ann, "title", "") or "",
                                          start_index=_get(ann, "start_index"), end_index=_get(ann, "end_index")))
    text = "".join(texts) or (_get(resp, "output_text", "") or "")
    raw = resp.model_dump() if hasattr(resp, "model_dump") else (resp if isinstance(resp, dict) else {})
    return SearchResult(text=text, citations=cites, searched=searched, raw=raw)


def web_search(prompt: str, instructions: str | None = None, context_size: str = "medium",
               tag: str = "web_search") -> SearchResult:
    """Responses API with the built-in web_search tool (not available on Chat Completions)."""
    kwargs: dict = {"model": model_id(), "input": prompt,
                    "tools": [{"type": "web_search", "search_context_size": context_size}]}
    if instructions:
        kwargs["instructions"] = instructions
    t0 = time.time()
    try:
        resp = _with_retries(tag, kwargs, lambda: client().responses.create(**kwargs))
    except Exception as e:  # noqa: BLE001
        raise MuseError(f"{tag}: web search call failed: {e}") from e
    result = parse_search_response(resp)
    log_run(tag, {"api": "responses+web_search", "request": kwargs, "response": result.text,
                  "searched": result.searched, "citations": [c.__dict__ for c in result.citations],
                  "usage": _usage(resp), "latency_s": round(time.time() - t0, 2)})
    return result
