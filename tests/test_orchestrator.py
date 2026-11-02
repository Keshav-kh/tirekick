"""End-to-end chat flow with fake AI + dry-run WhatsApp (owner: A)."""

import json
import re
import uuid

from tirekick import config, orchestrator, store
from tirekick.models import DealStatus
from tirekick.whatsapp.webhook import IncomingMessage

BUYER, SELLER = "15550000001", "15550000002"
LISTING = "2003 Honda Accord EX, 128k miles, $4,800, runs great, VIN 1HGCM82633A004352. max 5000"


def say(wa_id, text="", media=None):
    orchestrator.handle_message(IncomingMessage(
        wa_id=wa_id, message_id=uuid.uuid4().hex, type="video" if media else "text", text=text,
        mime_type="video/mp4" if media else None, local_media_path=media,
    ))


def outbox():
    path = config.DATA_DIR / "outbox.jsonl"
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


def to(wa_id):
    return [m for m in outbox() if m["to"] == wa_id]


def deal_code():
    text = " ".join(m.get("text", {}).get("body", "") for m in to(BUYER))
    return re.search(r"DEAL-\d{4}", text).group(0)


def test_happy_path_ends_agreed_and_seller_only_gets_approved_messages():
    say(BUYER, LISTING)
    code = deal_code()
    say(SELLER, code)
    say(SELLER, media="clips/honest_accord_01.mp4")
    assert len(to(SELLER)) == 2                      # challenge + "got it" only, before any approval
    assert store.get_deal(code).status == DealStatus.NEGOTIATING
    say(BUYER, "1")                                  # approve opening offer
    assert len(to(SELLER)) == 3
    say(SELLER, "I can do 4,600")
    assert len(to(SELLER)) == 3                      # counter draft waits for approval
    say(BUYER, "1")
    say(SELLER, "ok deal")
    say(BUYER, "1")                                  # approve final confirmation
    deal = store.get_deal(code)
    assert deal.status == DealStatus.AGREED
    assert all("EV-" not in m.get("text", {}).get("body", "") for m in to(SELLER))


def test_shady_seller_is_rejected_then_buyer_can_pass():
    say(BUYER, LISTING)
    code = deal_code()
    say(SELLER, code)
    say(SELLER, "send $500 deposit first, I'm out of state")
    say(SELLER, media="clips/shady_accord.mp4")
    deal = store.get_deal(code)
    assert deal.status == DealStatus.REJECTED and deal.report.verdict.value == "red"
    before = len(to(SELLER))
    say(BUYER, "1")                                  # send the polite pass
    assert len(to(SELLER)) == before + 1
    assert store.get_deal(code).status == DealStatus.WALKED_AWAY


def test_duplicate_webhook_delivery_is_ignored():
    msg = IncomingMessage(wa_id=BUYER, message_id="dup-1", type="text", text="hi")
    orchestrator.handle_message(msg)
    orchestrator.handle_message(msg)
    assert len(to(BUYER)) == 1


def test_verification_crash_asks_seller_to_resend(monkeypatch):
    from tirekick import verify

    def boom(deal, path):
        raise RuntimeError("Muse down")

    real = verify.run_verification
    say(BUYER, LISTING)
    code = deal_code()
    say(SELLER, code)
    monkeypatch.setattr(verify, "run_verification", boom)
    say(SELLER, media="clips/honest_accord_01.mp4")
    assert store.get_deal(code).status == DealStatus.CHALLENGE_SENT
    assert "resend" in to(BUYER)[-1]["text"]["body"]
    monkeypatch.setattr(verify, "run_verification", real)
    say(SELLER, media="clips/honest_accord_01.mp4")   # the retry goes through
    assert store.get_deal(code).status == DealStatus.NEGOTIATING


def test_past_seller_can_join_a_new_deal_and_reset_unwedges():
    say(BUYER, LISTING)
    first = deal_code()
    say(SELLER, first)
    say(BUYER, "reset")
    assert store.get_deal(first).status == DealStatus.EXPIRED
    say(BUYER, LISTING)
    second = re.findall(r"DEAL-\d{4}", " ".join(m.get("text", {}).get("body", "") for m in to(BUYER)))[-1]
    assert second != first
    say(SELLER, second)
    assert store.get_deal(second).seller_wa_id == SELLER
    assert store.get_deal(second).status == DealStatus.CHALLENGE_SENT


def test_stale_deal_expires():
    from datetime import timedelta

    say(BUYER, LISTING)
    deal = store.get_deal(deal_code())
    deal.updated_at -= timedelta(hours=25)
    store._path(deal.deal_id).write_text(deal.model_dump_json(), encoding="utf-8")  # bypass save's timestamp
    assert store.find_active_deal_by_buyer(BUYER) is None


def test_messages_during_verification_are_not_blocked_or_clobbered(monkeypatch):
    from tirekick import verify

    real = verify.run_verification

    def slow(deal, path):  # a buyer message lands mid-verification; would deadlock if the lock were held
        say(BUYER, "reset")
        return real(deal, path)

    say(BUYER, LISTING)
    code = deal_code()
    say(SELLER, code)
    monkeypatch.setattr(verify, "run_verification", slow)
    say(SELLER, media="clips/honest_accord_01.mp4")
    deal = store.get_deal(code)
    assert deal.status == DealStatus.EXPIRED and deal.report is None   # stale result dropped, reset kept


def test_join_code_only_works_once_listing_is_ready():
    say(BUYER, "hi")                                  # deal exists but is still NEW
    code = deal_code() if "DEAL-" in str(to(BUYER)) else store.find_active_deal_by_buyer(BUYER).deal_id
    say(SELLER, code)
    deal = store.get_deal(code)
    assert deal.seller_wa_id is None and deal.status == DealStatus.NEW
