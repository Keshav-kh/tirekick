"""Incoming webhook: signature check + payload flattening. Owner: A."""

from __future__ import annotations

import hashlib
import hmac

from pydantic import BaseModel


class IncomingMessage(BaseModel):
    wa_id: str                       # sender, digits only
    message_id: str
    type: str                        # text | image | video | interactive | document | ...
    text: str = ""
    media_id: str | None = None
    mime_type: str | None = None
    button_id: str | None = None     # interactive reply id ("send" / "edit" / "stop")
    local_media_path: str | None = None  # set by /dev/simulate instead of media_id


def verify_signature(raw_body: bytes, header: str | None, app_secret: str) -> bool:
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


def parse_incoming(payload: dict) -> list[IncomingMessage]:
    out: list[IncomingMessage] = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            for m in value.get("messages") or []:  # "statuses" events are ignored
                mtype = m.get("type", "")
                msg = IncomingMessage(wa_id=m.get("from", ""), message_id=m.get("id", ""), type=mtype)
                if mtype == "text":
                    msg.text = (m.get("text") or {}).get("body", "")
                elif mtype in {"image", "video", "document", "audio"}:
                    media = m.get(mtype) or {}
                    msg.media_id = media.get("id")
                    msg.mime_type = media.get("mime_type")
                    msg.text = media.get("caption", "") or ""
                elif mtype == "interactive":
                    reply = (m.get("interactive") or {}).get("button_reply") or {}
                    msg.button_id = reply.get("id")
                    msg.text = reply.get("title", "")
                elif mtype == "button":  # template quick-reply
                    msg.text = (m.get("button") or {}).get("text", "")
                out.append(msg)
    return out
