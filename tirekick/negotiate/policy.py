"""Negotiation hard rules (SPEC section 7), enforced in code. Owner: B.

Prices come from next_offer_amount (deterministic); the model only writes words.
check_offer is the last gate before a draft is shown to the buyer.
"""

from __future__ import annotations

import re

from tirekick.models import NegotiationState, Offer, VerificationReport


class PolicyViolation(Exception):
    pass


STEP = 50
FORBIDDEN = re.compile(
    r"\b(zelle|venmo|cash ?app|paypal|wire|bank|account number|routing|deposit|gift ?cards?|crypto|"
    r"bitcoin|address|apartment|apt\.|my home|my house)\b",
    re.IGNORECASE,
)
# Money = a currency marker or a k-suffix. Plain numbers (mileage, years) are not treated as prices.
MONEY = re.compile(
    r"(?:\$|\busd\s?|\baed\s?|\bdhs?\.?\s?)(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?(\s?k\b)?"
    r"|\b(\d+(?:\.\d+)?)\s?k\b",
    re.IGNORECASE,
)


def round_down(x: float, step: int = STEP) -> int:
    return int(x // step * step)


def money_figures(text: str) -> set[int]:
    found: set[int] = set()
    for m in MONEY.finditer(text or ""):
        if m.group(1):
            value = float(m.group(1).replace(",", "") + (f".{m.group(2)}" if m.group(2) else ""))
            if m.group(3):
                value *= 1000
        else:
            value = float(m.group(4)) * 1000
        found.add(int(round(value)))
    return found


def next_offer_amount(state: NegotiationState, report: VerificationReport) -> int:
    """Deterministic concession schedule. Never above the buyer's ceiling or the asking price."""
    ask, ceiling = state.asking_price, state.buyer_ceiling
    impacts = sum(e.price_impact for e in report.evidence if e.verified)
    if state.last_offer is None:
        comps_low = report.comps.low if report.comps and report.comps.low else ask
        base = min(comps_low, ask * 0.88) - impacts
        amount = round_down(max(ask * 0.70, base))
    else:
        seller = state.last_seller_ask if state.last_seller_ask is not None else ask
        if seller <= state.last_offer:
            return min(seller, ceiling)
        if seller - state.last_offer <= 150 and seller <= ceiling:
            return seller
        amount = max(round_down(state.last_offer + (seller - state.last_offer) / 3), state.last_offer)
    return min(amount, ceiling, ask)


def allowed_figures(state: NegotiationState, report: VerificationReport, offer: Offer) -> set[int]:
    allowed = {state.asking_price}
    if offer.amount is not None:
        allowed.add(offer.amount)
    if report.comps:
        allowed |= {v for v in (report.comps.low, report.comps.median, report.comps.high) if v}
    by_id = report.evidence_by_id()
    for cid in offer.cites:
        if cid in by_id:
            allowed |= money_figures(by_id[cid].summary)
    return allowed


def check_offer(offer: Offer, state: NegotiationState, report: VerificationReport) -> None:
    """Raise PolicyViolation if the draft breaks any SPEC section 7 rule."""
    if FORBIDDEN.search(offer.message_text or ""):
        raise PolicyViolation("message mentions payment details, a deposit, or an address")
    by_id = report.evidence_by_id()
    for cid in offer.cites:
        if cid not in by_id:
            raise PolicyViolation(f"cites unknown evidence id {cid}")
        if not by_id[cid].verified:
            raise PolicyViolation(f"cites unverified evidence {cid}")
    if offer.is_walk_away:
        return
    if offer.amount is None:
        raise PolicyViolation("offer has no amount")
    if offer.amount > state.buyer_ceiling:
        raise PolicyViolation(f"amount {offer.amount} exceeds the buyer ceiling {state.buyer_ceiling}")
    has_comps = bool(report.comps and report.comps.n >= 3)
    if offer.amount < state.asking_price and not offer.cites and not has_comps and not offer.is_final:
        raise PolicyViolation("a price reduction must cite verified evidence or comps")
    stray = money_figures(offer.message_text) - allowed_figures(state, report, offer)
    if stray:
        raise PolicyViolation(f"message mentions prices not in the evidence: {sorted(stray)}")
