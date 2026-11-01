import hashlib
import hmac

from fastapi.testclient import TestClient

from tirekick.app import app
from tirekick.whatsapp.webhook import parse_incoming, verify_signature

PAYLOAD = {"entry": [{"changes": [{"value": {"messages": [
    {"from": "15550000001", "id": "wamid.1", "type": "text", "text": {"body": "hello"}},
    {"from": "15550000002", "id": "wamid.2", "type": "video", "video": {"id": "MEDIA1", "mime_type": "video/mp4"}},
    {"from": "15550000001", "id": "wamid.3", "type": "interactive",
     "interactive": {"type": "button_reply", "button_reply": {"id": "send", "title": "Send"}}},
], "statuses": [{"id": "x"}]}}]}]}


def test_signature():
    body = b'{"a":1}'
    sig = "sha256=" + hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    assert verify_signature(body, sig, "secret")
    assert not verify_signature(body, sig, "other")
    assert not verify_signature(body, None, "secret")


def test_parse_incoming():
    msgs = parse_incoming(PAYLOAD)
    assert [m.type for m in msgs] == ["text", "video", "interactive"]
    assert msgs[0].text == "hello" and msgs[1].media_id == "MEDIA1" and msgs[2].button_id == "send"


def test_health_and_verify_handshake(monkeypatch):
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "tok")
    c = TestClient(app)
    assert c.get("/health").json() == {"ok": True}
    r = c.get("/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "tok", "hub.challenge": "42"})
    assert r.status_code == 200 and r.text == "42"
    assert c.get("/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "bad"}).status_code == 403


def test_dev_simulate_and_report_page():
    c = TestClient(app)
    r = c.post("/dev/simulate", json={"from": "15550000001",
                                      "text": "2003 Honda Accord EX, 128k miles, $4,800, runs great. max 5000"})
    assert r.status_code == 200 and r.json()["outbox"]
    import re
    code = re.search(r"DEAL-\d{4}", str(r.json()["outbox"])).group(0)
    page = c.get(f"/r/{code}")
    assert page.status_code == 200 and "TIREKICK" in page.text
