"""run_verification: the one call A makes after a proof video arrives. Owner: B."""

from __future__ import annotations

import logging

from tirekick.models import Deal, VerificationReport
from tirekick.verify.report_builder import build_report, extract_evidence_frames
from tirekick.verify.scam import scan_chat

log = logging.getLogger(__name__)


def run_verification(deal: Deal, video_path: str) -> VerificationReport:
    # Import the dispatching wrappers so fake mode applies here too.
    from tirekick import verify

    if deal.listing is None or deal.challenge is None:
        raise ValueError("run_verification needs deal.listing and deal.challenge")
    listing, challenge = deal.listing, deal.challenge

    analysis = verify.analyze_proof_take(video_path, challenge, listing)

    vin = analysis.windshield_vin_read or listing.vin
    vin_decode = None
    if vin:
        try:
            vin_decode = verify.decode_vin(vin)
        except Exception as e:  # noqa: BLE001 - network failure must not kill the report
            log.warning("vPIC decode failed: %s", e)

    make = (vin_decode.make if vin_decode else None) or listing.make
    model = (vin_decode.model if vin_decode else None) or listing.model
    year = (vin_decode.year if vin_decode else None) or listing.year
    recalls = []
    if make and model and year:
        try:
            recalls = verify.lookup_recalls(make, model, year)
        except Exception as e:  # noqa: BLE001
            log.warning("recalls lookup failed: %s", e)

    try:
        comps = verify.price_comps(listing)
    except Exception as e:  # noqa: BLE001
        log.warning("comps failed: %s", e)
        comps = None

    chat_evidence = scan_chat(deal.chat, listing, comps)
    report = build_report(deal.deal_id, listing, challenge, analysis, vin_decode, recalls, comps, chat_evidence)
    extract_evidence_frames(report, video_path)
    return report
