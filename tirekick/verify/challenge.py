"""The proof-of-car challenge (SPEC section 6.1). Owner: B; copy reviewed with A."""

from __future__ import annotations

import secrets
import uuid
from datetime import timedelta

from tirekick.models import Listing, ProofChallenge, utcnow

# No 0/O/Q, 1/I/L, 5/S, 8/B: easy to read on a handwritten card through a phone camera.
CODE_ALPHABET = "ACDEFGHJKMNPRTUVWXY234679"

CHALLENGE_TEMPLATE = """Hi! I'm TireKick, helping a buyer who's interested in your *{car}*. To skip the back-and-forth, please send *one continuous video (no cuts), up to 60 seconds*:

1. Hold a paper with this code: *{code}*, next to the *VIN plate at the bottom of the windshield*. Keep both in frame.
2. Show the *VIN sticker on the driver's door jamb*.
3. Sit in the driver's seat, turn the key to *ON without starting* (or press Start once without the brake) and hold *5 seconds* on the dashboard so all the warning lights show.
4. Show the *odometer* and the *temperature gauge*.
5. *Start the engine* and keep the dashboard in view for *5 more seconds*.

The engine should be *cold* (not driven in the last ~2 hours). The code expires in {ttl_hours} hours. Thanks!"""


def new_code(length: int = 6) -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))


def car_label(listing: Listing) -> str:
    parts = [str(listing.year) if listing.year else "", listing.make or "", listing.model or ""]
    label = " ".join(p for p in parts if p).strip()
    return label or listing.title or "car"


def issue_challenge(listing: Listing, deal_id: str, ttl_hours: int = 24) -> ProofChallenge:
    code = new_code()
    now = utcnow()
    return ProofChallenge(
        challenge_id=f"CH-{uuid.uuid4().hex[:8]}",
        deal_id=deal_id,
        code=code,
        issued_at=now,
        expires_at=now + timedelta(hours=ttl_hours),
        message_text=CHALLENGE_TEMPLATE.format(car=car_label(listing), code=code, ttl_hours=ttl_hours),
    )
