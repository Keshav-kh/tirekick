"""build_report: applies SPEC section 6.3 rules C1-C13 IN CODE. Owner: B.

Starting price_impact values are from docs/workstream-B-intelligence.md section 4; tune them
and keep that table in sync.
"""

from __future__ import annotations

import shutil
import subprocess

from tirekick.config import data_path
from tirekick.models import (
    CRITICAL_IF_ON, MUST_LIGHT, Evidence, EvidenceSource, EvidenceType, Listing, PriceComps,
    ProofChallenge, ProofTakeAnalysis, Recall, Severity, VerificationReport, VinDecode,
)
from tirekick.verify.vin import is_north_american, normalize_vin, validate_vin

KM_PER_MI = 1.609344
MAKE_ALIASES = {"chevy": "chevrolet", "vw": "volkswagen", "mercedes": "mercedes-benz", "benz": "mercedes-benz"}
LIGHT_LABEL = {
    "check_engine": "check-engine", "airbag": "airbag", "abs": "ABS", "battery": "battery",
    "oil_pressure": "oil-pressure", "brake": "brake", "tpms": "tire-pressure", "coolant_temp": "coolant",
}
RECALL_IMPACT, RECALL_IMPACT_CAP = 100, 300
TRIM_MISMATCH_IMPACT = 500
LIGHT_ON_IMPACT = 150
EXTRA_MILES_RATE, EXTRA_MILES_CAP = 0.10, 1500


def _norm(s: str | None) -> str:
    s = (s or "").strip().lower()
    return MAKE_ALIASES.get(s, s)


def _loosely_equal(a: str | None, b: str | None) -> bool:
    a, b = _norm(a), _norm(b)
    return bool(a and b) and (a in b or b in a)


def _miles(value: int, unit: str | None) -> float:
    return value / KM_PER_MI if unit == "km" else float(value)


class _Builder:
    def __init__(self) -> None:
        self.items: list[Evidence] = []

    def add(self, type_: EvidenceType, severity: Severity, summary: str, source: EvidenceSource,
            detail: str = "", t0: float | None = None, t1: float | None = None, impact: int = 0,
            verified: bool = True) -> None:
        self.items.append(Evidence(
            id="", type=type_, severity=severity, summary=summary, detail=detail, source=source,
            clip_start_s=t0, clip_end_s=t1 if t1 is not None else (t0 + 2 if t0 is not None else None),
            price_impact=max(0, int(impact)), verified=verified,
        ))


def _video_checks(b: _Builder, a: ProofTakeAnalysis, challenge: ProofChallenge, listing: Listing) -> None:
    V = EvidenceSource.VIDEO
    # C1 code
    if not a.code_matches:
        b.add(EvidenceType.CODE_MISSING, Severity.RED,
              "The video doesn't show the requested code next to the VIN.", V,
              detail=f"Expected {challenge.code}, read {a.code_read!r}.", t0=a.code_timestamp_s)
    # C2 continuous take
    if not a.continuous_take:
        cuts = ", ".join(f"{t:g}s" for t in a.cut_timestamps_s) or "unknown points"
        b.add(EvidenceType.TAKE_HAS_CUTS, Severity.RED,
              f"The video has cuts at {cuts}; we need one continuous take.", V,
              t0=a.cut_timestamps_s[0] if a.cut_timestamps_s else None)
    # C11 screen replay
    if a.screen_replay_suspected:
        b.add(EvidenceType.SCREEN_REPLAY, Severity.RED, "The video appears to be filmed from a screen.", V)

    # C3/C4 VINs
    wv = a.windshield_vin_read
    if not wv:
        b.add(EvidenceType.VIN_UNREADABLE, Severity.YELLOW, "The windshield VIN wasn't readable.", V,
              t0=a.windshield_vin_timestamp_s)
    else:
        valid, norm = validate_vin(wv)
        if not valid:
            if is_north_american(norm):
                b.add(EvidenceType.VIN_INVALID, Severity.RED,
                      "The VIN read from the windshield fails the standard check digit.", V,
                      detail=f"Read {norm}.", t0=a.windshield_vin_timestamp_s)
            else:
                b.add(EvidenceType.VIN_INVALID, Severity.YELLOW,
                      "VIN check digit not applicable or failed (non-North-American VIN).", V,
                      detail=f"Read {norm}.", t0=a.windshield_vin_timestamp_s)
        if a.door_vin_read and normalize_vin(a.door_vin_read) != norm:
            b.add(EvidenceType.VIN_MISMATCH_DOORS, Severity.RED,
                  "The windshield VIN and the door-jamb VIN don't match.", V,
                  detail=f"Windshield {norm}, door {normalize_vin(a.door_vin_read)}.", t0=a.door_vin_timestamp_s)
        if listing.vin and normalize_vin(listing.vin) != norm:
            b.add(EvidenceType.VIN_LISTING_MISMATCH, Severity.RED,
                  "The VIN in the video doesn't match the VIN in the listing.", V,
                  detail=f"Video {norm}, listing {normalize_vin(listing.vin)}.", t0=a.windshield_vin_timestamp_s)

    # C7/C8 warning lights
    hidden_or_on = False
    for obs in a.lights:
        label = LIGHT_LABEL.get(obs.light.value, obs.light.value)
        if obs.lit_at_key_on is False:
            hidden_or_on = True
            sev = Severity.RED if obs.light in MUST_LIGHT else Severity.YELLOW
            b.add(EvidenceType.WARNING_LIGHT_HIDDEN, sev,
                  f"The {label} light didn't come on at key-on (bulb check).", V,
                  detail="A light that never comes on can hide a fault (tape or a pulled bulb).",
                  t0=obs.key_on_timestamp_s or a.key_on_timestamp_s)
        if obs.on_after_start:
            hidden_or_on = True
            critical = obs.light in CRITICAL_IF_ON
            b.add(EvidenceType.WARNING_LIGHT_ON, Severity.RED if critical else Severity.YELLOW,
                  f"The {label} light stays on after the engine starts.", V,
                  t0=obs.after_start_timestamp_s or a.engine_start_timestamp_s,
                  impact=0 if critical else LIGHT_ON_IMPACT)
    seen = [o for o in a.lights if o.lit_at_key_on is not None]
    if seen and not hidden_or_on:
        b.add(EvidenceType.POSITIVE, Severity.GREEN,
              f"All {len(seen)} warning lights came on at key-on and went off after the start.", V,
              t0=a.key_on_timestamp_s)

    # C9 odometer
    if a.odometer_read is not None and listing.mileage:
        read_mi = _miles(a.odometer_read, a.odometer_unit or listing.mileage_unit)
        listed_mi = _miles(listing.mileage, listing.mileage_unit)
        unit = a.odometer_unit or listing.mileage_unit
        if read_mi < listed_mi * 0.95:
            b.add(EvidenceType.ODOMETER_MISMATCH, Severity.RED,
                  f"The odometer reads {a.odometer_read:,} {unit}, the listing says {listing.mileage:,}.", V,
                  t0=a.odometer_timestamp_s)
        elif read_mi > listed_mi * 1.05:
            extra = read_mi - listed_mi
            b.add(EvidenceType.ODOMETER_MISMATCH, Severity.YELLOW,
                  f"The odometer reads {a.odometer_read:,} {unit}, higher than the {listing.mileage:,} listed.", V,
                  t0=a.odometer_timestamp_s, impact=min(EXTRA_MILES_CAP, int(extra * EXTRA_MILES_RATE)))
        else:
            b.add(EvidenceType.POSITIVE, Severity.GREEN,
                  f"Odometer {a.odometer_read:,} {unit} matches the listing.", V, t0=a.odometer_timestamp_s)

    # C10 cold engine
    if a.engine_cold is False:
        b.add(EvidenceType.ENGINE_WARM, Severity.YELLOW,
              "The engine looked warm at start; a cold start wasn't shown.", V, t0=a.temp_gauge_timestamp_s)


def _decode_checks(b: _Builder, d: VinDecode, listing: Listing) -> None:
    D = EvidenceSource.VIN_DECODE
    decoded = " ".join(str(x) for x in (d.year, d.make, d.model) if x)
    listed = " ".join(str(x) for x in (listing.year, listing.make, listing.model) if x)
    core_mismatch = (
        (listing.year and d.year and listing.year != d.year)
        or (listing.make and d.make and not _loosely_equal(listing.make, d.make))
        or (listing.model and d.model and not _loosely_equal(listing.model, d.model))
    )
    if core_mismatch:
        b.add(EvidenceType.VIN_LISTING_MISMATCH, Severity.RED,
              f"The VIN decodes to a {decoded}, not the {listed} in the listing.", D)
    elif listing.trim and d.trim and not _loosely_equal(listing.trim, d.trim):
        b.add(EvidenceType.VIN_LISTING_MISMATCH, Severity.YELLOW,
              f"The VIN decodes to the {d.trim} trim, not the {listing.trim} listed.", D,
              impact=TRIM_MISMATCH_IMPACT)
    elif decoded:
        b.add(EvidenceType.POSITIVE, Severity.GREEN, f"VIN decodes to a {decoded}, matching the listing.", D)


def build_report(deal_id: str, listing: Listing, challenge: ProofChallenge,
                 analysis: ProofTakeAnalysis | None, vin_decode: VinDecode | None,
                 recalls: list[Recall], comps: PriceComps | None,
                 chat_evidence: list[Evidence]) -> VerificationReport:
    b = _Builder()
    if analysis is None:
        b.add(EvidenceType.CODE_MISSING, Severity.RED, "No proof video was received.", EvidenceSource.VIDEO)
    else:
        _video_checks(b, analysis, challenge, listing)
    if vin_decode is not None:
        _decode_checks(b, vin_decode, listing)

    # C6 recalls (model-level)
    # vPIC components look like "AIR BAGS:FRONTAL:DRIVER SIDE:INFLATOR MODULE"; one item per top-level system
    recall_budget = RECALL_IMPACT_CAP
    seen_systems: set[str] = set()
    for r in recalls:
        system = (r.component.split(":")[0].strip().title() or "see details")
        if system in seen_systems:
            continue
        seen_systems.add(system)
        if len(seen_systems) > 3:
            break
        impact = min(RECALL_IMPACT, recall_budget)
        recall_budget -= impact
        b.add(EvidenceType.RECALL_FOUND, Severity.YELLOW,
              f"There's an NHTSA recall for this model: {system}.",
              EvidenceSource.RECALLS, detail=f"Campaign {r.campaign_number}. {r.summary[:240]}",
              impact=impact)

    # C13 price far below market
    if comps and comps.median and listing.asking_price < 0.7 * comps.median:
        b.add(EvidenceType.PRICE_BELOW_MARKET, Severity.YELLOW,
              f"The price is well below similar cars ({comps.median:,} median).", EvidenceSource.COMPS)

    # C12 chat evidence (from scan_chat) is appended as-is, then everything gets fresh ids
    evidence = b.items + [e.model_copy() for e in chat_evidence]
    for i, e in enumerate(evidence, start=1):
        e.id = f"EV-{i:02d}"

    verdict = VerificationReport.compute_verdict(evidence)
    total_impact = sum(e.price_impact for e in evidence if e.verified)
    fair_low = fair_high = None
    if comps and comps.low and comps.median:
        floor = int(listing.asking_price * 0.5)
        fair_low = max(floor, comps.low - total_impact)
        fair_high = max(floor, comps.median - total_impact)
    questions = [f"Ask the mechanic about: {e.summary}" for e in evidence if e.severity == Severity.YELLOW]
    if recalls:
        questions.append("Check this VIN at nhtsa.gov/recalls to confirm the recalls were repaired.")

    return VerificationReport(
        deal_id=deal_id, listing=listing, challenge=challenge, analysis=analysis,
        vin_decode=vin_decode, recalls=recalls, comps=comps, evidence=evidence, verdict=verdict,
        fair_price_low=fair_low, fair_price_high=fair_high, inspection_questions=questions,
    )


def extract_evidence_frames(report: VerificationReport, video_path: str) -> None:
    """Write data/frames/{deal}/{EV-xx}.jpg for evidence with a timestamp. No-op without ffmpeg."""
    if not shutil.which("ffmpeg"):
        return
    for e in report.evidence:
        if e.clip_start_s is None:
            continue
        out = data_path("frames", report.deal_id, f"{e.id}.jpg")
        result = subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{e.clip_start_s:.2f}", "-i", video_path,
             "-frames:v", "1", "-q:v", "3", str(out)],
            check=False,
        )
        if result.returncode == 0 and out.exists():
            e.frame_path = str(out)
