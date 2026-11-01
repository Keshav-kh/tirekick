"""Public verification API (CONTRACTS section 3.1). Owner: B.

Functions that call the network or the model dispatch to `fake.py` when TIREKICK_FAKE_AI=1,
checked at call time. Pure functions always run the real code.
"""

from __future__ import annotations

from tirekick.config import fake_ai
from tirekick.models import (
    ChatMessage, Deal, Evidence, Listing, PriceComps, ProofChallenge, ProofTakeAnalysis, Recall,
    VerificationReport, VinDecode,
)
from tirekick.verify.challenge import issue_challenge
from tirekick.verify.report_builder import build_report
from tirekick.verify.scam import scan_chat
from tirekick.verify.vin import validate_vin

__all__ = [
    "parse_listing", "issue_challenge", "analyze_proof_take", "validate_vin", "decode_vin",
    "lookup_recalls", "price_comps", "scan_chat", "build_report", "run_verification",
]


def parse_listing(text: str | None = None, image_paths: list[str] | None = None,
                  url: str | None = None, listing_id: str | None = None) -> Listing:
    if fake_ai():
        from tirekick.verify import fake
        return fake.parse_listing(text, image_paths, url, listing_id)
    from tirekick.verify.listing import parse_listing as real
    return real(text, image_paths, url, listing_id)


def analyze_proof_take(video_path: str, challenge: ProofChallenge, listing: Listing,
                       runs: int = 3) -> ProofTakeAnalysis:
    if fake_ai():
        from tirekick.verify import fake
        return fake.analyze_proof_take(video_path, challenge, listing, runs)
    from tirekick.verify.proof_take import analyze_proof_take as real
    return real(video_path, challenge, listing, runs)


def decode_vin(vin: str) -> VinDecode:
    if fake_ai():
        from tirekick.verify import fake
        return fake.decode_vin(vin)
    from tirekick.verify.vin import decode_vin as real
    return real(vin)


def lookup_recalls(make: str, model: str, year: int) -> list[Recall]:
    if fake_ai():
        from tirekick.verify import fake
        return fake.lookup_recalls(make, model, year)
    from tirekick.verify.recalls import lookup_recalls as real
    return real(make, model, year)


def price_comps(listing: Listing) -> PriceComps:
    if fake_ai():
        from tirekick.verify import fake
        return fake.price_comps(listing)
    from tirekick.verify.comps import price_comps as real
    return real(listing)


def run_verification(deal: Deal, video_path: str) -> VerificationReport:
    from tirekick.verify.pipeline import run_verification as impl
    return impl(deal, video_path)


# Re-exported for type checkers / IDEs
_ = (ChatMessage, Evidence)
