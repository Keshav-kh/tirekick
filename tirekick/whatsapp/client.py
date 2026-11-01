"""Outgoing WhatsApp messages + media download. Owner: A.

Dry-run: with TIREKICK_DEV=1 and no WHATSAPP_TOKEN, nothing is sent; every message is appended
to data/outbox.jsonl so /dev/simulate and tests can see what the bot would have said.
"""

from __future__ import annotations

import itertools
import json
import mimetypes

import httpx

from tirekick.config import data_path, dev_mode, env
from tirekick.models import utcnow

_counter = itertools.count(1)


def _base() -> str:
    return f"https://graph.facebook.com/{env('GRAPH_API_VERSION', 'v21.0')}"


def dry_run() -> bool:
    return dev_mode() and not env("WHATSAPP_TOKEN")


def _headers() -> dict:
    return {"Authorization": f"Bearer {env('WHATSAPP_TOKEN')}"}


def _outbox(entry: dict) -> str:
    msg_id = f"dry-{next(_counter)}"
    entry = {"id": msg_id, "at": utcnow().isoformat(), **entry}
    with data_path("outbox.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return msg_id


def _post(payload: dict) -> str:
    if dry_run():
        return _outbox(payload)
    url = f"{_base()}/{env('WHATSAPP_PHONE_NUMBER_ID')}/messages"
    resp = httpx.post(url, headers=_headers(), json={"messaging_product": "whatsapp", **payload}, timeout=20)
    resp.raise_for_status()
    return resp.json()["messages"][0]["id"]


def send_text(to: str, body: str) -> str:
    return _post({"to": to, "type": "text", "text": {"body": body[:4096], "preview_url": True}})


def send_buttons(to: str, body: str, buttons: list[tuple[str, str]]) -> str:
    """Interactive reply buttons, max 3. buttons = [(id, title<=20 chars), ...]."""
    return _post({
        "to": to, "type": "interactive",
        "interactive": {
            "type": "button", "body": {"text": body[:1024]},
            "action": {"buttons": [{"type": "reply", "reply": {"id": i, "title": t[:20]}} for i, t in buttons[:3]]},
        },
    })


def send_image(to: str, link: str, caption: str = "") -> str:
    return _post({"to": to, "type": "image", "image": {"link": link, "caption": caption[:1024]}})


def download_media(media_id: str) -> tuple[str, str]:
    """Return (local_path, mime_type). Saves to data/media/{media_id}.{ext}."""
    meta = httpx.get(f"{_base()}/{media_id}", headers=_headers(), timeout=20)
    meta.raise_for_status()
    info = meta.json()
    mime = info.get("mime_type", "application/octet-stream")
    ext = (mimetypes.guess_extension(mime.split(";")[0]) or ".bin").lstrip(".")
    blob = httpx.get(info["url"], headers=_headers(), timeout=120)
    blob.raise_for_status()
    path = data_path("media", f"{media_id}.{ext}")
    path.write_bytes(blob.content)
    return str(path), mime
