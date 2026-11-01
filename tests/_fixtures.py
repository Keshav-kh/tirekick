"""Shared builders for tests (no network, no model)."""

from datetime import timedelta

from tirekick.models import ProofChallenge, utcnow
from tirekick.verify import fake
from tirekick.verify.report_builder import build_report


def challenge(code="K7Q2XM"):
    now = utcnow()
    return ProofChallenge(challenge_id="CH-t", deal_id="DEAL-1234", code=code, issued_at=now,
                          expires_at=now + timedelta(hours=24), message_text="")


def honest_report():
    listing = fake.parse_listing(listing_id="DEAL-1234")
    ch = challenge()
    a = fake.analyze_proof_take("clips/honest.mp4", ch, listing)
    d = fake.decode_vin(a.windshield_vin_read)
    return build_report("DEAL-1234", listing, ch, a, d, fake.lookup_recalls("Honda", "Accord", 2003),
                        fake.price_comps(listing), [])


def shady_report():
    listing = fake.parse_listing(listing_id="DEAL-1234")
    ch = challenge()
    a = fake.analyze_proof_take("clips/shady.mp4", ch, listing)
    d = fake.decode_vin(a.windshield_vin_read)
    return build_report("DEAL-1234", listing, ch, a, d, [], fake.price_comps(listing), [])
