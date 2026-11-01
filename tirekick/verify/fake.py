"""Fixture implementations used when TIREKICK_FAKE_AI=1 (CONTRACTS section 3.4).

Same signatures as the real functions. A video path containing "shady" gives a RED report;
anything else gives a YELLOW report. Only network/model calls are faked: build_report,
scan_chat, issue_challenge and validate_vin are the real code, so fake mode exercises them.
A may add fixtures here; B keeps the signatures in sync.
"""

from __future__ import annotations

from tirekick.models import (
    LightName, LightObservation, Listing, PriceComps, ProofChallenge, ProofTakeAnalysis, Recall, VinDecode,
)

HONEST_VIN = "1HGCM82633A004352"   # valid check digit
SHADY_VIN = "1HGCM82643A004352"    # fails check digit


def parse_listing(text: str | None = None, image_paths: list[str] | None = None,
                  url: str | None = None, listing_id: str | None = None) -> Listing:
    return Listing(
        listing_id=listing_id or "L-fixture",
        source="facebook_marketplace", url=url,
        title="2003 Honda Accord EX - runs great", asking_price=4800, currency="USD",
        year=2003, make="Honda", model="Accord", trim="EX", engine="3.0L V6",
        mileage=128000, mileage_unit="mi", vin=HONEST_VIN, location="State College, PA",
        seller_name="Seller", raw_text=text or "",
    )


def analyze_proof_take(video_path: str, challenge: ProofChallenge, listing: Listing,
                       runs: int = 3) -> ProofTakeAnalysis:
    if "shady" in video_path.lower():
        return ProofTakeAnalysis(
            video_path=video_path, duration_s=38, code_read=None, code_matches=False,
            continuous_take=True, windshield_vin_read=SHADY_VIN, windshield_vin_timestamp_s=4,
            lights=[
                LightObservation(light=LightName.CHECK_ENGINE, lit_at_key_on=False, on_after_start=False,
                                 key_on_timestamp_s=14, confidence=0.8),
                LightObservation(light=LightName.AIRBAG, lit_at_key_on=True, on_after_start=False,
                                 key_on_timestamp_s=14, confidence=0.9),
            ],
            key_on_timestamp_s=14, engine_start_timestamp_s=21, engine_cold=None,
            model_notes="Small dark rectangle over the check-engine icon area.", runs=3, agreement=0.83,
        )
    lights = [
        LightObservation(light=l, lit_at_key_on=True, on_after_start=False,
                         key_on_timestamp_s=17, after_start_timestamp_s=26, confidence=0.9)
        for l in (LightName.CHECK_ENGINE, LightName.AIRBAG, LightName.ABS, LightName.BATTERY,
                  LightName.OIL_PRESSURE, LightName.BRAKE, LightName.TPMS)
    ]
    return ProofTakeAnalysis(
        video_path=video_path, duration_s=52, code_read=challenge.code, code_matches=True, code_timestamp_s=3,
        continuous_take=True, windshield_vin_read=HONEST_VIN, windshield_vin_timestamp_s=3,
        door_vin_read=HONEST_VIN, door_vin_timestamp_s=10, lights=lights,
        key_on_timestamp_s=17, engine_start_timestamp_s=24,
        odometer_read=129500, odometer_unit="mi", odometer_timestamp_s=20,
        engine_cold=True, temp_gauge_timestamp_s=21, runs=3, agreement=1.0,
    )


def decode_vin(vin: str) -> VinDecode:
    from tirekick.verify.vin import is_north_american, validate_vin

    valid, norm = validate_vin(vin)
    return VinDecode(vin=norm, check_digit_valid=valid, north_american=is_north_american(norm),
                     year=2003, make="Honda", model="Accord", trim="EX-V6", engine="3.0L 6cyl", body="Coupe")


def lookup_recalls(make: str, model: str, year: int) -> list[Recall]:
    return [Recall(
        campaign_number="15V320000", component="AIR BAGS",
        summary="Driver frontal air bag inflator may rupture during deployment.",
        consequence="Metal fragments could strike occupants.", remedy="Dealers replace the inflator free of charge.",
        report_date="2015-05-28",
    )]


def price_comps(listing: Listing) -> PriceComps:
    return PriceComps(currency=listing.currency, low=4300, median=4900, high=5600, n=5,
                      sources=["https://example.com/comp1", "https://example.com/comp2"],
                      note="fixture comps")
