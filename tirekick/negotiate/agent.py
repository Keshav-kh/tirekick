"""Negotiation agent: prices from policy.next_offer_amount, words from Muse Spark. Owner: B."""

from __future__ import annotations

import logging
import re

from tirekick.config import env, fake_ai
from tirekick.models import (
    ChatRole, EvidenceType, NegotiationState, NegotiationStatus, NegotiationTurn, Offer, VerificationReport,
)
from tirekick.negotiate.policy import PolicyViolation, check_offer, next_offer_amount
from tirekick.verify import prompts
from tirekick.verify.challenge import car_label

log = logging.getLogger(__name__)

ACCEPT = re.compile(r"\b(deal|ok(ay)?|yes|sure|works|accept(ed)?|agreed|sounds good)\b", re.IGNORECASE)
PRICE = re.compile(r"\$?\s?(\d{1,3}(?:,\d{3})+|\d{3,6})(?!\d)(\s?k\b)?|\b(\d+(?:\.\d+)?)\s?k\b", re.IGNORECASE)


def money(amount: int | None, currency: str) -> str:
    if amount is None:
        return ""
    return f"${amount:,}" if currency == "USD" else f"{currency} {amount:,}"


def start_negotiation(deal_id: str, report: VerificationReport, buyer_ceiling: int) -> NegotiationState:
    return NegotiationState(
        deal_id=deal_id, buyer_ceiling=buyer_ceiling, asking_price=report.listing.asking_price,
        currency=report.listing.currency, status=NegotiationStatus.IN_PROGRESS,
    )


def choose_cites(report: VerificationReport, limit: int = 2) -> list[str]:
    usable = [e for e in report.evidence if e.verified and e.severity.value == "yellow"]
    usable.sort(key=lambda e: (e.price_impact, e.type == EvidenceType.RECALL_FOUND), reverse=True)
    return [e.id for e in usable[:limit]]


def template_message(amount: int, report: VerificationReport, cites: list[str], currency: str) -> str:
    by_id = report.evidence_by_id()
    reasons = [by_id[c].summary.rstrip(".") for c in cites if c in by_id]
    parts = ["Thanks for the video!"]
    if reasons:
        parts.append(" ".join(r + "." for r in reasons))
    if report.comps and report.comps.low and report.comps.median:
        parts.append(f"Similar cars are going for {money(report.comps.low, currency)}-"
                     f"{money(report.comps.median, currency)}.")
    parts.append(f"Would you take {money(amount, currency)}?")
    return " ".join(parts)


def _model_message(state: NegotiationState, report: VerificationReport, amount: int, cites: list[str],
                   seller_message: str | None, buyer_instruction: str | None, violation: str | None) -> str:
    from tirekick.verify.muse import client, model_id

    by_id = report.evidence_by_id()
    facts = "\n".join(f"- {by_id[c].summary}" for c in cites if c in by_id) or "- (none)"
    comps = (f"{money(report.comps.low, state.currency)} to {money(report.comps.median, state.currency)}"
             if report.comps and report.comps.low and report.comps.median else "(none)")
    user = prompts.OFFER_USER.format(
        car=car_label(report.listing), asking=money(state.asking_price, state.currency),
        amount=money(amount, state.currency), facts=facts, comps=comps,
        seller_message=seller_message or "",
        buyer_instruction=f"Buyer's instruction: {buyer_instruction}" if buyer_instruction else "",
    )
    if violation:
        user += f"\nYour previous draft was rejected: {violation}. Fix that."
    resp = client().chat.completions.create(
        model=model_id(), temperature=0.4,
        messages=[{"role": "system", "content": prompts.OFFER_SYSTEM}, {"role": "user", "content": user}],
    )
    return (resp.choices[0].message.content or "").strip().strip('"')


def draft_offer(state: NegotiationState, report: VerificationReport, seller_message: str | None = None,
                buyer_instruction: str | None = None) -> Offer:
    """Always returns an Offer that passes check_offer."""
    amount = next_offer_amount(state, report)
    cites = choose_cites(report)
    is_final = state.last_seller_ask is not None and amount >= state.last_seller_ask
    if not fake_ai() and env("META_API_KEY"):
        violation = None
        for _ in range(2):
            try:
                text = _model_message(state, report, amount, cites, seller_message, buyer_instruction, violation)
                offer = Offer(amount=amount, cites=cites, message_text=text, is_final=is_final)
                check_offer(offer, state, report)
                return offer
            except PolicyViolation as e:
                violation = str(e)
            except Exception as e:  # noqa: BLE001 - model/API failure falls back to the template
                log.warning("offer drafting failed: %s", e)
                break
    offer = Offer(amount=amount, cites=cites, is_final=is_final,
                  message_text=template_message(amount, report, cites, state.currency))
    check_offer(offer, state, report)
    return offer


def final_offer(state: NegotiationState) -> Offer:
    amount = state.last_seller_ask if state.last_seller_ask is not None else state.last_offer
    text = (f"Great, {money(amount, state.currency)} works. Could we meet at a public safe exchange spot, "
            f"like a police station exchange zone? I'll have a quick pre-purchase inspection done first.")
    return Offer(amount=amount, message_text=text, is_final=True)


def walk_away_offer(state: NegotiationState) -> Offer:
    return Offer(amount=None, is_walk_away=True,
                 message_text="Thanks for your time! It's a bit above what I can do, so I'll pass for now. Good luck with the sale.")


def record_sent_offer(state: NegotiationState, offer: Offer) -> NegotiationState:
    """A calls this after the buyer approves and the message is sent."""
    s = state.model_copy(deep=True)
    s.turns.append(NegotiationTurn(role=ChatRole.TIREKICK, text=offer.message_text,
                                   amount=offer.amount, evidence_ids=offer.cites))
    if offer.amount is not None:
        s.last_offer = offer.amount
    if offer.is_walk_away:
        s.status = NegotiationStatus.WALKED_AWAY
    return s


def extract_price(text: str, asking: int) -> int | None:
    lo, hi = asking * 0.5, asking * 1.3
    found = None
    for m in PRICE.finditer(text or ""):
        if m.group(1):
            value = float(m.group(1).replace(",", "")) * (1000 if m.group(2) else 1)
        else:
            value = float(m.group(3)) * 1000
        if lo <= value <= hi:
            found = int(value)
    return found


def apply_seller_reply(state: NegotiationState, text: str) -> NegotiationState:
    s = state.model_copy(deep=True)
    price = extract_price(text, s.asking_price)
    s.turns.append(NegotiationTurn(role=ChatRole.SELLER, text=text, amount=price))
    s.rounds += 1
    s.status = NegotiationStatus.IN_PROGRESS
    if price is None and ACCEPT.search(text or "") and s.last_offer is not None:
        s.last_seller_ask = s.last_offer
        s.status = NegotiationStatus.AGREED
    elif price is not None:
        s.last_seller_ask = price
        if s.last_offer is not None and price <= s.last_offer:
            s.status = NegotiationStatus.AGREED
    if (s.status != NegotiationStatus.AGREED and s.rounds >= s.max_rounds
            and (s.last_seller_ask or s.asking_price) > s.buyer_ceiling):
        s.status = NegotiationStatus.WALKED_AWAY
    return s
