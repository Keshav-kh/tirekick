"""Conversation state machine (docs/workstream-A-platform.md section 4). Owner: A.

This is a working v0 baseline so the team has an end-to-end path from day one (try it with
TIREKICK_FAKE_AI=1 TIREKICK_DEV=1 and /dev/simulate). A owns it: refine the copy, the edge
cases and the TODOs. Invariant: nothing goes to the seller unless the buyer approved it,
except the challenge message and the "got it" acknowledgement.
"""

from __future__ import annotations

import logging
import re
import threading

from tirekick import negotiate, store, verify
from tirekick.config import env
from tirekick.models import (
    ChatMessage, ChatRole, Deal, DealStatus, NegotiationStatus, Offer, Severity, VerificationReport,
)
from tirekick.whatsapp import client as wa
from tirekick.whatsapp.webhook import IncomingMessage

log = logging.getLogger(__name__)

DEAL_CODE = re.compile(r"\bDEAL-\d{4}\b", re.IGNORECASE)
MAX_PRICE = re.compile(r"\bmax(?:imum)?\s*(?:is|of|:)?\s*\$?\s*(\d{1,3}(?:,\d{3})+|\d+)(\s?k\b)?", re.IGNORECASE)
EV_ID = re.compile(r"\s*\(?\bEV-\d{2}\b\)?")
SEVERITY_ICON = {Severity.RED: "🔴", Severity.YELLOW: "🟡", Severity.GREEN: "🟢"}
APPROVAL_BUTTONS = [("send", "✅ Send"), ("edit", "✏️ Edit"), ("stop", "🛑 Stop")]
RESET_WORDS = {"reset", "new", "restart"}
# ponytail: one global lock around every deal read-modify-write so concurrent webhook tasks can't
# clobber each other's JSON. Verification (~90 s) runs outside it. Per-deal locks if throughput matters.
_LOCK = threading.Lock()

GREETING = ("Hi! I'm TireKick 🚗 Paste a car listing (link, text or screenshots) and your max price, "
            "e.g. 'max 9000'. I'll make the seller prove the car before we negotiate.")


# --------------------------------------------------------------------------- helpers


def _report_link(deal: Deal) -> str:
    return f"{env('PUBLIC_BASE_URL', 'http://localhost:8000').rstrip('/')}/r/{deal.deal_id}"


def _join_link(deal: Deal) -> str:
    return f"https://wa.me/{env('WHATSAPP_BOT_NUMBER', '15550000000')}?text={deal.deal_id}"


def parse_ceiling(text: str) -> int | None:
    m = MAX_PRICE.search(text or "")
    if not m:
        return None
    value = int(m.group(1).replace(",", ""))
    return value * 1000 if m.group(2) else value


def _record(deal: Deal, role: ChatRole, msg: IncomingMessage | None = None, text: str = "",
            media_path: str | None = None) -> None:
    deal.chat.append(ChatMessage(
        role=role, text=(msg.text if msg else text) or "",
        media_path=media_path, media_type=msg.mime_type if msg else None,
        wa_message_id=msg.message_id if msg else None,
    ))


def _media_path(msg: IncomingMessage) -> str | None:
    if msg.local_media_path:
        return msg.local_media_path
    if msg.media_id:
        path, mime = wa.download_media(msg.media_id)
        msg.mime_type = msg.mime_type or mime
        return path
    return None


def _choice(msg: IncomingMessage) -> str | None:
    if msg.button_id in {"send", "edit", "stop"}:
        return msg.button_id
    return {"1": "send", "2": "edit", "3": "stop"}.get((msg.text or "").strip())


def _show_draft(deal: Deal, draft: Offer, intro: str = "Draft to seller:") -> None:
    deal.pending_draft = draft
    deal.awaiting_edit = False
    wa.send_buttons(deal.buyer_wa_id, f'{intro}\n\n"{draft.message_text}"\n\nReply 1 to send, 2 to edit, 3 to stop.',
                    APPROVAL_BUTTONS)


def buyer_summary(deal: Deal, report: VerificationReport) -> str:
    car = " ".join(str(x) for x in (
        (report.vin_decode.year if report.vin_decode else None) or report.listing.year,
        (report.vin_decode.make if report.vin_decode else None) or report.listing.make,
        (report.vin_decode.model if report.vin_decode else None) or report.listing.model,
    ) if x)
    head = {Severity.RED: "🛑 *Don't buy this one.*", Severity.YELLOW: f"⚠️ *{car}*: OK to negotiate, a few flags",
            Severity.GREEN: f"✅ *{car}*: looks clean"}[report.verdict]
    lines = [head]
    if report.fair_price_low and report.fair_price_high and report.verdict != Severity.RED:
        lines.append(f"Asking {negotiate.agent.money(report.listing.asking_price, report.listing.currency)} · "
                     f"Fair {negotiate.agent.money(report.fair_price_low, report.listing.currency)}-"
                     f"{negotiate.agent.money(report.fair_price_high, report.listing.currency)}")
    order = {Severity.RED: 0, Severity.YELLOW: 1, Severity.GREEN: 2}
    for e in sorted(report.evidence, key=lambda e: order[e.severity])[:5]:
        lines.append(f"{SEVERITY_ICON[e.severity]} {e.summary}")
    lines.append(f"Full report: {_report_link(deal)}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- entry point


def handle_message(msg: IncomingMessage) -> None:
    with _LOCK:
        job = _route(msg)
    if job:
        _verify_and_report(*job)


def _route(msg: IncomingMessage) -> tuple[str, str] | None:
    """Returns (deal_id, video_path) when a proof video needs verifying outside the lock."""
    if store.already_processed(msg.message_id):
        return
    if (msg.text or "").strip().lower() in RESET_WORDS:
        return _reset(msg.wa_id)
    code = DEAL_CODE.search(msg.text or "")  # before the seller lookup, so a past seller can join a new deal
    if code:
        deal = store.get_deal(code.group(0).upper())
        if (deal and deal.status == DealStatus.LISTING_PARSED and store.is_active(deal)
                and deal.seller_wa_id is None and msg.wa_id != deal.buyer_wa_id):
            return on_seller_join(deal, msg)
    seller_deal = store.find_deal_by_seller(msg.wa_id)
    if seller_deal:
        return on_seller_message(seller_deal, msg)
    return on_buyer_message(msg)


def _reset(wa_id: str) -> None:
    for deal in store.active_deals_for(wa_id):
        deal.status = DealStatus.EXPIRED
        deal.pending_draft = None
        store.save_deal(deal)
        if wa_id == deal.seller_wa_id:
            wa.send_text(deal.buyer_wa_id, f"The seller left {deal.deal_id}. Paste another listing anytime.")
    wa.send_text(wa_id, GREETING)


# --------------------------------------------------------------------------- buyer side


def on_buyer_message(msg: IncomingMessage) -> None:
    deal = store.find_active_deal_by_buyer(msg.wa_id)
    if deal is None:
        deal = Deal(deal_id=store.new_deal_id(), buyer_wa_id=msg.wa_id)
    media = _media_path(msg) if (msg.media_id or msg.local_media_path) else None
    _record(deal, ChatRole.BUYER, msg, media_path=media)

    if deal.status == DealStatus.NEW:
        _collect_listing(deal, msg)
    elif deal.pending_draft is not None and deal.status in {DealStatus.NEGOTIATING, DealStatus.REJECTED}:
        _handle_approval(deal, msg)
    else:
        wa.send_text(deal.buyer_wa_id, f"Deal {deal.deal_id} is {deal.status.value.replace('_', ' ')}. "
                                       f"Report: {_report_link(deal)}")
    store.save_deal(deal)


def _collect_listing(deal: Deal, msg: IncomingMessage) -> None:
    ceiling = parse_ceiling(msg.text)
    if ceiling:
        deal.buyer_ceiling = ceiling
    buyer_msgs = [m for m in deal.chat if m.role == ChatRole.BUYER]
    text = "\n".join(MAX_PRICE.sub("", m.text).strip() for m in buyer_msgs if m.text).strip()
    images = [m.media_path for m in buyer_msgs if m.media_path and (m.media_type or "").startswith("image")]
    has_listing = len(text) >= 40 or bool(images)

    if not has_listing and not deal.buyer_ceiling:
        wa.send_text(deal.buyer_wa_id, GREETING)
        return
    if not has_listing:
        wa.send_text(deal.buyer_wa_id, "Got your max. Now paste the listing (text or screenshots).")
        return
    if not deal.buyer_ceiling:
        wa.send_text(deal.buyer_wa_id, "Got the listing. What's your max price? e.g. 'max 9000'")
        return

    url = next((w for w in text.split() if w.startswith("http")), None)
    try:
        deal.listing = verify.parse_listing(text=text, image_paths=images or None, url=url, listing_id=deal.deal_id)
    except ValueError as e:
        wa.send_text(deal.buyer_wa_id, f"I couldn't read that listing ({e}). Try pasting the full text or a screenshot.")
        return
    try:
        comps = verify.price_comps(deal.listing)
    except Exception:  # noqa: BLE001
        comps = None
    deal.status = DealStatus.LISTING_PARSED
    l = deal.listing
    lines = [f"📋 *{l.year or ''} {l.make or ''} {l.model or ''} {l.trim or ''}*".replace("  ", " "),
             f"Asking {negotiate.agent.money(l.asking_price, l.currency)} · your max "
             f"{negotiate.agent.money(deal.buyer_ceiling, l.currency)}"]
    if comps and comps.low and comps.median:
        lines.append(f"Similar cars: {negotiate.agent.money(comps.low, l.currency)}-"
                     f"{negotiate.agent.money(comps.median, l.currency)} ({comps.n} found)")
    if l.vin:
        valid, _ = verify.validate_vin(l.vin)
        lines.append("VIN in listing passes the check digit ✅" if valid else "⚠️ The listing's VIN fails the check digit")
    lines.append(f"\nForward this link to the seller. When they tap it, I'll send them the proof challenge:\n{_join_link(deal)}")
    wa.send_text(deal.buyer_wa_id, "\n".join(lines))


def _handle_approval(deal: Deal, msg: IncomingMessage) -> None:
    draft = deal.pending_draft
    assert draft is not None
    if deal.awaiting_edit and _choice(msg) is None:
        new = negotiate.draft_offer(deal.negotiation, deal.report, buyer_instruction=msg.text)
        return _show_draft(deal, new, "Updated draft:")
    choice = _choice(msg)
    if choice == "send":
        wa.send_text(deal.seller_wa_id, EV_ID.sub("", draft.message_text).strip())
        _record(deal, ChatRole.TIREKICK, text=draft.message_text)
        if deal.negotiation is not None:
            deal.negotiation = negotiate.record_sent_offer(deal.negotiation, draft)
        deal.pending_draft = None
        if draft.is_walk_away:
            deal.status = DealStatus.WALKED_AWAY
            wa.send_text(deal.buyer_wa_id, "Sent. Deal closed. Paste another listing anytime.")
        elif draft.is_final:
            deal.status = DealStatus.AGREED
            wa.send_text(deal.buyer_wa_id, f"🤝 Done. Get a pre-purchase inspection before you pay. "
                                           f"Report: {_report_link(deal)}")
        else:
            wa.send_text(deal.buyer_wa_id, "Sent ✅ I'll show you the seller's reply.")
    elif choice == "edit":
        deal.awaiting_edit = True
        wa.send_text(deal.buyer_wa_id, "How should I change it? (e.g. 'be friendlier', 'mention the recall only')")
    elif choice == "stop":
        if draft.is_walk_away:
            deal.pending_draft = None
            deal.status = DealStatus.WALKED_AWAY
            wa.send_text(deal.buyer_wa_id, "OK, nothing sent. Deal closed.")
        else:
            state = deal.negotiation
            _show_draft(deal, negotiate.walk_away_offer(state), "Walk away? Draft to seller:")
    else:
        wa.send_text(deal.buyer_wa_id, "Reply 1 to send, 2 to edit, 3 to stop.")


# --------------------------------------------------------------------------- seller side


def on_seller_join(deal: Deal, msg: IncomingMessage) -> None:
    deal.seller_wa_id = msg.wa_id
    _record(deal, ChatRole.SELLER, msg)
    deal.challenge = verify.issue_challenge(deal.listing, deal.deal_id)
    wa.send_text(deal.seller_wa_id, deal.challenge.message_text)
    deal.status = DealStatus.CHALLENGE_SENT
    wa.send_text(deal.buyer_wa_id, "Seller joined ✅ I've sent them the proof-video challenge.")
    store.save_deal(deal)


def on_seller_message(deal: Deal, msg: IncomingMessage) -> tuple[str, str] | None:
    media = _media_path(msg) if (msg.media_id or msg.local_media_path) else None
    _record(deal, ChatRole.SELLER, msg, media_path=media)
    is_video = bool(media) and ((msg.mime_type or "").startswith("video") or msg.type == "video"
                                or (media or "").lower().endswith((".mp4", ".mov")))

    if deal.status == DealStatus.CHALLENGE_SENT and is_video:
        deal.chat[-1].media_type = deal.chat[-1].media_type or "video/mp4"
        wa.send_text(deal.seller_wa_id, "Got it, thanks! Checking now.")
        wa.send_text(deal.buyer_wa_id, "🎥 Proof video received. Verifying (about 1 minute)…")
        deal.status = DealStatus.PROOF_RECEIVED
        store.save_deal(deal)
        return deal.deal_id, media
    elif deal.status == DealStatus.CHALLENGE_SENT:
        if "?" in (msg.text or ""):
            wa.send_text(deal.seller_wa_id, "Just send the one-take video whenever you're ready. The steps are in my message above 🙂")
    elif deal.status == DealStatus.NEGOTIATING and deal.negotiation is not None:
        _on_seller_counter(deal, msg.text or "")
    store.save_deal(deal)


def _verify_and_report(deal_id: str, video_path: str) -> None:
    """Runs unlocked; re-takes the lock and reloads the deal to apply the result."""
    report = None
    try:
        report = verify.run_verification(store.get_deal(deal_id), video_path)
    except Exception:  # noqa: BLE001 - never leave the deal stuck in PROOF_RECEIVED
        log.exception("verification failed for %s", deal_id)
    with _LOCK:
        deal = store.get_deal(deal_id)  # fresh copy: messages may have arrived meanwhile
        if deal.status != DealStatus.PROOF_RECEIVED:  # e.g. buyer typed "reset" while we waited
            return
        _apply_report(deal, report)
        store.save_deal(deal)


def _apply_report(deal: Deal, report: VerificationReport | None) -> None:
    if report is None:
        deal.status = DealStatus.CHALLENGE_SENT
        wa.send_text(deal.seller_wa_id, "Sorry, I couldn't process that video. Could you send the take again?")
        wa.send_text(deal.buyer_wa_id, "⚠️ I couldn't check that video, so I've asked the seller to resend it.")
        return
    deal.report = report
    wa.send_text(deal.buyer_wa_id, buyer_summary(deal, report))
    if report.verdict == Severity.RED:
        deal.status = DealStatus.REJECTED
        deal.negotiation = negotiate.start_negotiation(deal.deal_id, report, deal.buyer_ceiling or report.listing.asking_price)
        _show_draft(deal, negotiate.walk_away_offer(deal.negotiation), "I recommend walking away. Send a polite pass?")
        return
    deal.status = DealStatus.NEGOTIATING
    deal.negotiation = negotiate.start_negotiation(deal.deal_id, report, deal.buyer_ceiling or report.listing.asking_price)
    _show_draft(deal, negotiate.draft_offer(deal.negotiation, report), "Opening offer, draft to seller:")


def _on_seller_counter(deal: Deal, text: str) -> None:
    state = negotiate.apply_seller_reply(deal.negotiation, text)
    deal.negotiation = state
    if state.status == NegotiationStatus.AGREED:
        _show_draft(deal, negotiate.final_offer(state), f"Seller agreed at "
                    f"{negotiate.agent.money(state.last_seller_ask, state.currency)} 🎉 Confirm with:")
    elif state.status == NegotiationStatus.WALKED_AWAY:
        _show_draft(deal, negotiate.walk_away_offer(state), "Seller is still above your max. Walk away with:")
    else:
        seller_ask = negotiate.agent.money(state.last_seller_ask, state.currency) if state.last_seller_ask else "no number"
        _show_draft(deal, negotiate.draft_offer(state, deal.report, seller_message=text),
                    f"Seller replied ({seller_ask}). Counter-offer draft:")
