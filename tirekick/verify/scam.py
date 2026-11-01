"""scan_chat: scam signals in the seller's messages (SPEC C12). Owner: B.

Rules first (deterministic, testable); an optional Muse Spark pass is a TODO and may only
add items it quotes verbatim from the chat.
"""

from __future__ import annotations

import re

from tirekick.models import ChatMessage, ChatRole, Evidence, EvidenceSource, EvidenceType, Listing, PriceComps, Severity

_F = re.IGNORECASE
DEPOSIT = re.compile(r"\b(deposit|hold (it|the car) for you|holding fee|reserve it)\b", _F)
UNTRACEABLE = re.compile(r"\b(gift ?cards?|apple card|steam card|crypto|bitcoin|btc|usdt|western union|moneygram)\b", _F)
P2P = re.compile(r"\b(zelle|cash ?app|venmo|wire( transfer)?)\b", _F)
SHIPPING = re.compile(r"\b(shipping|shipped|transport company|ebay motors protection|escrow)\b", _F)
ABSENT = re.compile(r"\b(deployed|military|out of (the )?(state|country)|can'?t meet)\b", _F)
REFUSES = re.compile(r"\b(no video|can'?t (send|do) (a )?video|won'?t send (a )?video|no inspection)\b", _F)

REASONS = {
    "deposit": "Asked for a deposit before showing the car on video.",
    "untraceable": "Asked for an untraceable payment method.",
    "p2p": "Asked for a peer-to-peer payment along with other red flags.",
    "shipping": "Mentions shipping, a transport company, or escrow, which is a common car-scam script.",
    "absent": "Says they can't meet in person, which is a common car-scam script.",
    "refuses": "Refused to send a proof video or allow an inspection.",
}


def _snippet(text: str, match: re.Match, width: int = 60) -> str:
    start = max(0, match.start() - width // 2)
    return text[start:start + width].strip()


def scan_chat(messages: list[ChatMessage], listing: Listing, comps: PriceComps | None) -> list[Evidence]:
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
        if (m := DEPOSIT.search(text)) and not proof_seen:
            flag("deposit", text, m); other_flags = True
        if m := UNTRACEABLE.search(text):
            flag("untraceable", text, m); other_flags = True
        if m := SHIPPING.search(text):
            flag("shipping", text, m); other_flags = True
        if m := ABSENT.search(text):
            flag("absent", text, m); other_flags = True
        if m := REFUSES.search(text):
            flag("refuses", text, m); other_flags = True
        if m := P2P.search(text):
            p2p_hits.append((text, m))
    if other_flags:
        for text, m in p2p_hits[:1]:
            flag("p2p", text, m)

    # TODO(B): one Muse Spark pass over the seller chat for subtler signals; keep only items
    # whose quoted text appears verbatim in a seller message (check in code).
    return list(found.values())
