"""Web chat demo: buyer and seller side by side in the browser, no WhatsApp needed. Owner: C.

Runs the real TireKick app (same orchestrator, verification and negotiation code as WhatsApp) and adds
a demo page on top of A's /dev/simulate and /dev/outbox. It does not change any app code.

  TIREKICK_DEV=1 uvicorn webchat_server:app --app-dir demo --port 8000
  open http://localhost:8000/demo

Add TIREKICK_FAKE_AI=1 to run without API keys (fixture answers).
Set TIREKICK_DEMO_CODE=K7Q2XM to make every challenge use that code, so a pre-recorded proof clip can
match it. Demo recordings only: label it on screen ("staged: pre-recorded proof clip").
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse

from tirekick.app import app  # the real app: webhook, report page, /dev/simulate, /dev/outbox
from tirekick.config import data_path, dev_mode, env
from tirekick.verify import challenge as _challenge

if env("TIREKICK_DEMO_CODE"):
    _DEMO_CODE = env("TIREKICK_DEMO_CODE").strip().upper()
    _challenge.new_code = lambda length=6: _DEMO_CODE  # issue_challenge looks this up at call time

ROOT = Path(__file__).resolve().parents[1]
PAGE = Path(__file__).with_name("webchat.html")
CLIP_DIRS = [ROOT / "eval" / "data" / "clips", ROOT / "demo" / "clips"]


@app.get("/demo", response_class=HTMLResponse)
def demo_page() -> str:
    if not dev_mode():
        raise HTTPException(status_code=404, detail="set TIREKICK_DEV=1")
    return PAGE.read_text(encoding="utf-8")


@app.get("/demo/clips")
def demo_clips() -> dict:
    """Videos already on this machine that the seller can 'send' as a proof take."""
    clips = []
    for d in CLIP_DIRS:
        if d.exists():
            clips += [str(p) for p in sorted(d.glob("*.mp4")) + sorted(d.glob("*.mov"))]
    return {"clips": clips}


@app.post("/demo/upload")
async def demo_upload(request: Request, name: str = "upload.bin") -> dict:
    """Save an uploaded video or screenshot (raw request body) so /dev/simulate can treat it like WhatsApp media."""
    if not dev_mode():
        raise HTTPException(status_code=404)
    suffix = Path(name).suffix.lower() or ".bin"
    if suffix not in {".mp4", ".mov", ".jpg", ".jpeg", ".png", ".webp"}:
        raise HTTPException(status_code=400, detail="send a video (.mp4/.mov) or an image")
    dest = data_path("webchat_uploads", f"{uuid.uuid4().hex[:10]}{suffix}")
    with dest.open("wb") as f:
        async for chunk in request.stream():
            f.write(chunk)
    return {"path": str(dest)}
