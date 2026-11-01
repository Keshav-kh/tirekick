"""FastAPI app: webhook, report page, dev simulator. Owner: A.

Run:  uvicorn tirekick.app:app --reload --port 8000
"""

from __future__ import annotations

import json
import logging
import re
import uuid

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from pydantic import BaseModel

from tirekick import orchestrator, store
from tirekick.config import data_path, dev_mode, env
from tirekick.report.render import render_report
from tirekick.whatsapp.webhook import IncomingMessage, parse_incoming, verify_signature

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="TireKick")
FRAME_NAME = re.compile(r"^EV-\d{2}(_hl)?\.jpg$")


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/webhook")
def webhook_verify(request: Request):
    q = request.query_params
    if q.get("hub.mode") == "subscribe" and q.get("hub.verify_token") == env("WHATSAPP_VERIFY_TOKEN"):
        return PlainTextResponse(q.get("hub.challenge", ""))
    raise HTTPException(status_code=403, detail="verification failed")


@app.post("/webhook")
async def webhook_receive(request: Request, background: BackgroundTasks) -> dict:
    raw = await request.body()
    secret = env("WHATSAPP_APP_SECRET")
    if secret and not verify_signature(raw, request.headers.get("X-Hub-Signature-256"), secret):
        raise HTTPException(status_code=403, detail="bad signature")
    for msg in parse_incoming(json.loads(raw or b"{}")):
        background.add_task(orchestrator.handle_message, msg)  # reply 200 fast; work in background
    return {"ok": True}


@app.get("/r/{deal_id}", response_class=HTMLResponse)
def report_page(deal_id: str) -> str:
    deal = store.get_deal(deal_id)
    if deal is None:
        raise HTTPException(status_code=404, detail="no such deal")
    return render_report(deal)


@app.get("/r/{deal_id}/frames/{name}")
def report_frame(deal_id: str, name: str):
    if not FRAME_NAME.match(name) or not re.match(r"^DEAL-\d{4}$", deal_id):
        raise HTTPException(status_code=404)
    path = data_path("frames", deal_id, name)
    if not path.exists():
        raise HTTPException(status_code=404)
    return FileResponse(path)


# --------------------------------------------------------------------------- dev only


class SimulatedMessage(BaseModel):
    from_: str
    text: str = ""
    media_path: str | None = None
    media_type: str | None = None
    button_id: str | None = None

    model_config = {"populate_by_name": True, "extra": "ignore"}


@app.post("/dev/simulate")
async def dev_simulate(request: Request) -> dict:
    """Fake an incoming WhatsApp message: {"from": "15551230001", "text": "...", "media_path": "x.mp4"}."""
    if not dev_mode():
        raise HTTPException(status_code=404)
    body = await request.json()
    body["from_"] = body.pop("from", body.get("from_", ""))
    sim = SimulatedMessage.model_validate(body)
    media_type = sim.media_type or ("video/mp4" if (sim.media_path or "").lower().endswith((".mp4", ".mov"))
                                    else "image/jpeg" if sim.media_path else None)
    msg = IncomingMessage(
        wa_id=sim.from_, message_id=f"sim-{uuid.uuid4().hex[:10]}",
        type="video" if (media_type or "").startswith("video") else "image" if media_type else
        ("interactive" if sim.button_id else "text"),
        text=sim.text, mime_type=media_type, button_id=sim.button_id, local_media_path=sim.media_path,
    )
    orchestrator.handle_message(msg)  # synchronous in dev so the caller sees the result
    return {"ok": True, "outbox": dev_outbox(10)["messages"]}


@app.get("/dev/outbox")
def dev_outbox(limit: int = 50) -> dict:
    if not dev_mode():
        raise HTTPException(status_code=404)
    path = data_path("outbox.jsonl")
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    return {"messages": [json.loads(l) for l in lines[-limit:]]}
