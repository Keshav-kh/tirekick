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


def test_unsigned_webhook_rejected_outside_dev(monkeypatch):
    monkeypatch.delenv("TIREKICK_DEV")
    assert TestClient(app).post("/webhook", json=PAYLOAD).status_code == 403


def _deal_with_video(c, media_path):
    import re
    c.post("/dev/simulate", json={"from": "15550000001",
                                  "text": "2003 Honda Accord EX, 128k miles, $4,800, runs great. max 5000"})
    code = re.findall(r"DEAL-\d{4}", str(c.get("/dev/outbox").json()))[-1]
    c.post("/dev/simulate", json={"from": "15550000002", "text": code})
    c.post("/dev/simulate", json={"from": "15550000002", "media_path": str(media_path)})
    return code


def test_report_serves_proof_video_from_data_dir_only(tmp_path):
    from tirekick import config

    c = TestClient(app)
    inside = config.DATA_DIR / "media" / "proof.mp4"
    inside.parent.mkdir(parents=True, exist_ok=True)
    inside.write_bytes(b"\x00" * 1000)
    code = _deal_with_video(c, inside)
    assert 'class="play"' in c.get(f"/r/{code}").text
    r = c.get(f"/r/{code}/video", headers={"Range": "bytes=0-9"})
    assert r.status_code == 206 and len(r.content) == 10

    outside = tmp_path / "elsewhere.mp4"
    outside.write_bytes(b"\x00" * 10)
    c.post("/dev/simulate", json={"from": "15550000001", "text": "reset"})
    code = _deal_with_video(c, outside)
    assert c.get(f"/r/{code}/video").status_code == 404
    assert 'class="play"' not in c.get(f"/r/{code}").text
