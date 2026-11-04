"""scan_chat: scam signals in the seller's messages (SPEC C12). Owner: B.

1. Rules first: deterministic regexes, each match is one red scam_signal quoting the message.
2. Then ONE Muse Spark pass over the seller messages ("list any additional scam indicators,
   quoting the exact message"). A model finding is kept only if its quote appears verbatim in a
   seller message, checked here in code. Severity is decided in code from the finding's category,
   never by the model. The model pass is skipped in fake mode, without a key, or on any error.
"""

from __future__ import annotations

import logging
import re
from typing import Literal

from pydantic import BaseModel, Field

from tirekick.config import fake_ai
from tirekick.models import ChatMessage, ChatRole, Evidence, EvidenceSource, EvidenceType, Listing, PriceComps, Severity

log = logging.getLogger(__name__)

_F = re.IGNORECASE
DEPOSIT = re.compile(r"\b(deposits?|hold (it|the car) for you|holding fee|reserve it|reservation fee)\b", _F)
UNTRACEABLE = re.compile(
    r"\b(gift ?cards?|apple card|itunes card|steam card|google play card|crypto|bitcoin|btc|usdt|ethereum|"
    r"western union|moneygram)\b", _F)
P2P = re.compile(r"\b(zelle|cash ?app|venmo|paypal friends|wire( transfer)?)\b", _F)
SHIPPING = re.compile(
    r"\b(shipping|shipped|ship (it|the car|the vehicle)|transport company|shipping company|delivery agent|"
    r"ebay motors protection|escrow|google pay protection|vehicle protection program)\b", _F)
# Currently absent, not "moving out of state next month" (a common honest reason to sell).
ABSENT = re.compile(
    r"\b(deployed|deployment|stationed (overseas|abroad)|on a military base|"
    r"i'?m (currently |now |away )?(out of (the )?(state|country)|overseas|abroad)|"
    r"can'?t meet|cannot meet|unable to meet|not able to meet)\b", _F)
REFUSES = re.compile(
    r"\b(no video|no videos|can'?t (send|do|take) (a |any )?videos?|won'?t (send|do) (a |any )?videos?|"
    r"no inspections?|don'?t need (an )?inspection)\b", _F)
NEGATION = re.compile(r"\b(no|not|don'?t|doesn'?t|never|without|won'?t|zero)\b[\w\s,']{0,18}$", _F)

REASONS = {
    "deposit": "Asked for a deposit before showing the car on video.",
    "untraceable": "Asked for an untraceable payment method.",
    "p2p": "Asked for a peer-to-peer payment along with other red flags.",
    "shipping": "Mentions shipping, a transport company, or escrow, which is a common car-scam script.",
    "absent": "Says they can't meet in person, which is a common car-scam script.",
    "refuses": "Refused to send a proof video or allow an inspection.",
}

# --------------------------------------------------------------------------- model pass

ModelCategory = Literal[
    "deposit_or_prepayment", "untraceable_payment", "shipping_or_escrow", "seller_unavailable",
    "refuses_inspection", "pressure_or_urgency", "move_off_platform", "identity_or_story_inconsistency",
    "other",
]
# Code decides severity from the category. Categories the rules already treat as scams are red;
# softer, more ambiguous signals are yellow so one model misread can't fail an honest seller.
MODEL_RED = {"deposit_or_prepayment", "untraceable_payment", "shipping_or_escrow", "seller_unavailable",
             "refuses_inspection"}
MODEL_SUMMARY = {
    "deposit_or_prepayment": "Asked for money before the buyer has seen the car.",
    "untraceable_payment": "Asked for an untraceable payment method.",
    "shipping_or_escrow": "Proposes shipping or an escrow/protection service, a common car-scam script.",
    "seller_unavailable": "Says they can't meet in person, which is a common car-scam script.",
    "refuses_inspection": "Avoids a video, a test drive, or an inspection.",
    "pressure_or_urgency": "Pushes the buyer to decide or pay quickly.",
    "move_off_platform": "Asks to move the conversation or payment off the platform.",
    "identity_or_story_inconsistency": "The seller's story is inconsistent.",
    "other": "The chat shows another possible scam indicator.",
}
MAX_MODEL_FINDINGS = 3
MIN_QUOTE_CHARS = 8

CHAT_SYSTEM = (
    "You review a private used-car sale chat for scam indicators. You quote, you do not judge the car. "
    "Every finding must include `quote`: an exact, contiguous, copy-pasted substring of ONE seller message "
    "(no paraphrase, no ellipsis). If there are no indicators, return an empty list."
)
CHAT_USER = """Listing: {car}, asking {price}.
Seller messages, one per line, numbered:
{lines}

Rules already flagged these categories (do not repeat them): {already}.
List any ADDITIONAL scam indicators, quoting the exact message text."""


class ChatFinding(BaseModel):
    category: ModelCategory
    quote: str
    message_index: int | None = None
    explanation: str = ""


class ChatFindings(BaseModel):
    findings: list[ChatFinding] = Field(default_factory=list)


def _canon(text: str) -> str:
    """Whitespace and typographic quotes normalized; case is kept (verbatim means verbatim)."""
    t = (text or "").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", t).strip()


def verbatim_in(quote: str, seller_texts: list[str]) -> str | None:
    """The seller message containing `quote` verbatim, or None. Checked in code, not trusted."""
    q = _canon(quote).strip(" \"'")
    if len(q) < MIN_QUOTE_CHARS:
        return None
    for text in seller_texts:
        if q in _canon(text):
            return text
    return None


def _model_pass(seller_texts: list[str], listing: Listing, already: set[str]) -> list[Evidence]:
    from tirekick.verify import muse
    from tirekick.verify.challenge import car_label

    if fake_ai() or not muse.available() or not seller_texts:
        return []
    lines = "\n".join(f"{i}. {t}" for i, t in enumerate(seller_texts, start=1))
    try:
        out = muse.muse_json(
            [{"role": "system", "content": CHAT_SYSTEM},
             {"role": "user", "content": CHAT_USER.format(
                 car=car_label(listing), price=f"{listing.asking_price:,} {listing.currency}",
                 lines=lines, already=", ".join(sorted(already)) or "none")}],
            ChatFindings, temperature=0.0, tag="scan_chat",
        )
    except Exception as e:  # noqa: BLE001 - the rules already ran; the model pass is optional
        log.warning("scan_chat model pass failed: %s", e)
        return []
    found: list[Evidence] = []
    seen_quotes: set[str] = set()
    for f in out.findings:
        source = verbatim_in(f.quote, seller_texts)
        q = _canon(f.quote).strip(" \"'")
        if source is None or q in seen_quotes:
            log.info("dropping non-verbatim or duplicate model finding: %r", f.quote)
            continue
        seen_quotes.add(q)
        found.append(Evidence(
            id="", type=EvidenceType.SCAM_SIGNAL,
            severity=Severity.RED if f.category in MODEL_RED else Severity.YELLOW,
            summary=MODEL_SUMMARY[f.category], detail=f'Seller wrote: "{q[:200]}"',
            source=EvidenceSource.CHAT,
        ))
        if len(found) >= MAX_MODEL_FINDINGS:
            break
    return found


# --------------------------------------------------------------------------- rules


def _snippet(text: str, match: re.Match, width: int = 80) -> str:
    start = max(0, match.start() - width // 2)
    return text[start:start + width].strip()


RULE_TO_MODEL = {"deposit": "deposit_or_prepayment", "untraceable": "untraceable_payment",
                 "p2p": "untraceable_payment", "shipping": "shipping_or_escrow", "absent": "seller_unavailable",
                 "refuses": "refuses_inspection"}


def _hit(regex: re.Pattern, text: str) -> re.Match | None:
    """First match that isn't negated just before it ("no deposit needed", "not shipping it")."""
    for m in regex.finditer(text):
        if not NEGATION.search(text[max(0, m.start() - 24):m.start()]):
            return m
    return None


def rule_findings(messages: list[ChatMessage]) -> dict[str, Evidence]:
    found: dict[str, Evidence] = {}
    proof_seen = False
    other_flags = False

    def flag(key: str, text: str, m: re.Match) -> None:
        if key not in found:
            found[key] = Evidence(
                id="", type=EvidenceType.SCAM_SIGNAL, severity=Severity.RED,
                summary=REASONS[key], detail=f'Seller wrote: "{_snippet(text, m)}"',
                source=EvidenceSource.CHAT,
            )

    p2p_hits: list[tuple[str, re.Match]] = []
    for msg in messages:
        if msg.role != ChatRole.SELLER:
            continue
        if msg.media_type and msg.media_type.startswith("video"):
            proof_seen = True
        text = msg.text or ""
        if (m := _hit(DEPOSIT, text)) and not proof_seen:
            flag("deposit", text, m); other_flags = True
        if m := _hit(UNTRACEABLE, text):
            flag("untraceable", text, m); other_flags = True
        if m := _hit(SHIPPING, text):
            flag("shipping", text, m); other_flags = True
        if m := _hit(ABSENT, text):
            flag("absent", text, m); other_flags = True
        if m := REFUSES.search(text):
            flag("refuses", text, m); other_flags = True
        if m := _hit(P2P, text):
            p2p_hits.append((text, m))
    if other_flags:
        for text, m in p2p_hits[:1]:
            flag("p2p", text, m)
    return found


def scan_chat(messages: list[ChatMessage], listing: Listing, comps: PriceComps | None) -> list[Evidence]:
    rules = rule_findings(messages)
    seller_texts = [m.text for m in messages if m.role == ChatRole.SELLER and m.text]
    already = {RULE_TO_MODEL[k] for k in rules}
    model = [e for e in _model_pass(seller_texts, listing, already)
             if e.summary not in {r.summary for r in rules.values()}]
    return list(rules.values()) + model
