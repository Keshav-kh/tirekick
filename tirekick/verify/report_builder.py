"""build_report: applies SPEC section 6.3 rules C1-C13 IN CODE. Owner: B.

Starting price_impact values are from docs/workstream-B-intelligence.md section 4; tune them
and keep that table in sync.
"""

from __future__ import annotations

import re
import shutil
import subprocess

from tirekick.config import data_path
from tirekick.models import (
    CRITICAL_IF_ON, MUST_LIGHT, Evidence, EvidenceSource, EvidenceType, Listing, PriceComps,
    ProofChallenge, ProofTakeAnalysis, Recall, Severity, VerificationReport, VinDecode,
)
from tirekick.verify.vin import _VIN_RE, is_north_american, normalize_vin, validate_vin

KM_PER_MI = 1.609344
MAKE_ALIASES = {"chevy": "chevrolet", "vw": "volkswagen", "mercedes": "mercedes-benz", "benz": "mercedes-benz"}
LIGHT_LABEL = {
    "check_engine": "check-engine", "airbag": "airbag", "abs": "ABS", "battery": "battery",
    "oil_pressure": "oil-pressure", "brake": "brake", "tpms": "tire-pressure", "coolant_temp": "coolant",
}
# price_impact constants: keep in sync with docs/workstream-B-intelligence.md section 4
RECALL_IMPACT, RECALL_IMPACT_CAP, RECALL_MAX_ITEMS = 100, 300, 3
TRIM_MISMATCH_IMPACT = 500
ENGINE_MISMATCH_IMPACT = 500
LIGHT_ON_IMPACT = 150
EXTRA_MILES_RATE, EXTRA_MILES_CAP = 0.10, 1500
ODOMETER_TOLERANCE = 0.05
PRICE_BELOW_MARKET_RATIO = 0.70      # C13: asking < 70% of the comps median
FAIR_PRICE_FLOOR_RATIO = 0.50
MUST_LIGHT_FROM_YEAR = 1996          # OBD-II: check-engine / airbag / ABS must sweep on at key-on


def _norm(s: str | None) -> str:
    s = (s or "").strip().lower()
    s = MAKE_ALIASES.get(s, s)
    return re.sub(r"[^a-z0-9]+", "", s)


def _loosely_equal(a: str | None, b: str | None) -> bool:
    a, b = _norm(a), _norm(b)
    return bool(a and b) and (a in b or b in a)


def _miles(value: int, unit: str | None) -> float:
    return value / KM_PER_MI if unit == "km" else float(value)


def _engine_facts(text: str | None) -> tuple[float | None, int | None]:
    """(displacement_l, cylinders) from strings like "3.0L V6", "2.4L 4cyl", "1.8 I4", "V8"."""
    t = (text or "").lower()
    disp = re.search(r"(\d\.\d)\s*-?\s*l(?:iter|itre)?\b", t) or re.search(r"\b(\d\.\d)\b", t)
    cyl = (re.search(r"\b[vi]-?(\d{1,2})\b", t) or re.search(r"\b(\d{1,2})\s*-?\s*cyl", t)
           or re.search(r"\b(\d{1,2})[- ]cylinder", t))
    return (float(disp.group(1)) if disp else None), (int(cyl.group(1)) if cyl else None)


def engine_mismatch(listed: str | None, decoded: str | None) -> bool:
    """True only when both sides state the same fact and it differs (unknown is not a mismatch)."""
    ld, lc = _engine_facts(listed)
    dd, dc = _engine_facts(decoded)
    if ld is not None and dd is not None and abs(ld - dd) > 0.15:
        return True
    return lc is not None and dc is not None and lc != dc


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


def _video_checks(b: _Builder, a: ProofTakeAnalysis, challenge: ProofChallenge, listing: Listing,
                  car_year: int | None = None) -> None:
    V = EvidenceSource.VIDEO
    if a.runs == 0:
        # Every model run failed (corrupt file, wrong format, API down). Listing "no code, cuts,
        # no VIN..." would quote made-up reasons to the seller, so report exactly one fact.
        b.add(EvidenceType.CODE_MISSING, Severity.RED,
              "The proof video couldn't be analyzed; please send a new one.", V,
              detail=a.model_notes[:300])
        return
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
    wv = normalize_vin(a.windshield_vin_read or "")
    if not wv or not _VIN_RE.match(wv):
        # nothing read, or not 17 valid VIN characters: an OCR failure, not proof of a fake
        b.add(EvidenceType.VIN_UNREADABLE, Severity.YELLOW, "The windshield VIN wasn't readable.", V,
              detail=f"Read {wv!r}." if wv else "", t0=a.windshield_vin_timestamp_s)
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
        door = normalize_vin(a.door_vin_read or "")
        if door and door != norm:
            b.add(EvidenceType.VIN_MISMATCH_DOORS, Severity.RED,
                  "The windshield VIN and the door-jamb VIN don't match.", V,
                  detail=f"Windshield {norm}, door {door}.", t0=a.door_vin_timestamp_s)
        listed_vin = normalize_vin(listing.vin or "")
        if listed_vin and listed_vin != norm:
            b.add(EvidenceType.VIN_LISTING_MISMATCH, Severity.RED,
                  "The VIN in the video doesn't match the VIN in the listing.", V,
                  detail=f"Video {norm}, listing {listed_vin}.", t0=a.windshield_vin_timestamp_s)
        if valid and door == norm and (not listed_vin or listed_vin == norm):
            b.add(EvidenceType.POSITIVE, Severity.GREEN,
                  "The windshield VIN matches the door-jamb sticker" + (" and the listing." if listed_vin else "."),
                  V, t0=a.door_vin_timestamp_s)

    # C7/C8 warning lights
    year = car_year or listing.year
    must_light = MUST_LIGHT if (year is None or year >= MUST_LIGHT_FROM_YEAR) else frozenset()
    sweep_shown = any(o.lit_at_key_on for o in a.lights)
    flagged = False
    if not sweep_shown:
        # No light seen on at key-on at all: step 3 wasn't shown (or wasn't readable). We can't
        # call any single light "hidden", but a bulb check we never saw can't pass either.
        b.add(EvidenceType.WARNING_LIGHT_HIDDEN, Severity.YELLOW,
              "The key-on bulb check (all warning lights on) wasn't clearly shown.", V,
              detail="Ask for a clip of the dashboard at key-on, before starting the engine.",
              t0=a.key_on_timestamp_s)
        flagged = True
    for obs in a.lights:
        label = LIGHT_LABEL.get(obs.light.value, obs.light.value)
        if sweep_shown and obs.lit_at_key_on is False:
            flagged = True
            sev = Severity.RED if obs.light in must_light else Severity.YELLOW
            b.add(EvidenceType.WARNING_LIGHT_HIDDEN, sev,
                  f"The {label} light didn't come on at key-on (bulb check).", V,
                  detail="A light that never comes on can hide a fault (tape or a pulled bulb).",
                  t0=obs.key_on_timestamp_s or a.key_on_timestamp_s)
        if obs.on_after_start:
            flagged = True
            critical = obs.light in CRITICAL_IF_ON
            b.add(EvidenceType.WARNING_LIGHT_ON, Severity.RED if critical else Severity.YELLOW,
                  f"The {label} light stays on after the engine starts.", V,
                  t0=obs.after_start_timestamp_s or a.engine_start_timestamp_s,
                  impact=0 if critical else LIGHT_ON_IMPACT)
    if sweep_shown:
        # A must-light the model couldn't see ("can't tell", or not reported at all) is not a pass:
        # a blurry or far-away dashboard would otherwise hide a taped check-engine light.
        by_name = {o.light: o for o in a.lights}
        for name in sorted(must_light, key=lambda n: n.value):
            obs = by_name.get(name)
            if obs is None or obs.lit_at_key_on is None:
                flagged = True
                label = LIGHT_LABEL.get(name.value, name.value)
                b.add(EvidenceType.WARNING_LIGHT_HIDDEN, Severity.YELLOW,
                      f"We couldn't confirm the {label} light came on at key-on.", V,
                      detail="Ask the seller to refilm the dashboard up close at key-on, before starting.",
                      t0=(obs.key_on_timestamp_s if obs else None) or a.key_on_timestamp_s)
    lit = [o for o in a.lights if o.lit_at_key_on]
    if lit and not flagged:
        off_after = all(o.on_after_start is False for o in lit)
        b.add(EvidenceType.POSITIVE, Severity.GREEN,
              f"All {len(lit)} warning lights came on at key-on"
              + (" and went off after the start." if off_after else "."), V, t0=a.key_on_timestamp_s)

    # C9 odometer
    if a.odometer_read is not None and listing.mileage:
        read_mi = _miles(a.odometer_read, a.odometer_unit or listing.mileage_unit)
        listed_mi = _miles(listing.mileage, listing.mileage_unit)
        unit = a.odometer_unit or listing.mileage_unit
        if read_mi < listed_mi * (1 - ODOMETER_TOLERANCE):
            b.add(EvidenceType.ODOMETER_MISMATCH, Severity.RED,
                  f"The odometer reads {a.odometer_read:,} {unit}, the listing says {listing.mileage:,}.", V,
                  t0=a.odometer_timestamp_s)
        elif read_mi > listed_mi * (1 + ODOMETER_TOLERANCE):
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
    else:
        soft = False
        if listing.trim and d.trim and not _loosely_equal(listing.trim, d.trim):
            soft = True
            b.add(EvidenceType.VIN_LISTING_MISMATCH, Severity.YELLOW,
                  f"The VIN decodes to the {d.trim} trim, not the {listing.trim} listed.", D,
                  impact=TRIM_MISMATCH_IMPACT)
        if engine_mismatch(listing.engine, d.engine):
            soft = True
            b.add(EvidenceType.VIN_LISTING_MISMATCH, Severity.YELLOW,
                  f"The VIN decodes to a {d.engine} engine, not the {listing.engine} listed.", D,
                  impact=ENGINE_MISMATCH_IMPACT)
        if decoded and not soft:
            b.add(EvidenceType.POSITIVE, Severity.GREEN, f"VIN decodes to a {decoded}, matching the listing.", D)


QUESTION_BY_TYPE = {
    EvidenceType.RECALL_FOUND: "Ask the mechanic to confirm this recall was completed: {s}",
    EvidenceType.WARNING_LIGHT_ON: "Ask the mechanic to scan for fault codes: {s}",
    EvidenceType.WARNING_LIGHT_HIDDEN: "Ask the mechanic to check every dashboard warning bulb works: {s}",
    EvidenceType.ODOMETER_MISMATCH: "Ask the mechanic to check wear against the mileage: {s}",
    EvidenceType.ENGINE_WARM: "Ask the mechanic to start the engine cold during the inspection: {s}",
    EvidenceType.VIN_LISTING_MISMATCH: "Ask the mechanic to confirm the trim and engine: {s}",
}


def inspection_question(e: Evidence) -> str:
    return QUESTION_BY_TYPE.get(e.type, "Ask the mechanic about: {s}").format(s=e.summary)


def build_report(deal_id: str, listing: Listing, challenge: ProofChallenge,
                 analysis: ProofTakeAnalysis | None, vin_decode: VinDecode | None,
                 recalls: list[Recall], comps: PriceComps | None,
                 chat_evidence: list[Evidence]) -> VerificationReport:
    b = _Builder()
    if analysis is None:
        b.add(EvidenceType.CODE_MISSING, Severity.RED, "No proof video was received.", EvidenceSource.VIDEO)
    else:
        _video_checks(b, analysis, challenge, listing, car_year=vin_decode.year if vin_decode else None)
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
        if len(seen_systems) >= RECALL_MAX_ITEMS:
            break
        seen_systems.add(system)
        impact = min(RECALL_IMPACT, recall_budget)
        recall_budget -= impact
        b.add(EvidenceType.RECALL_FOUND, Severity.YELLOW,
              f"There's an NHTSA recall for this model: {system}.",
              EvidenceSource.RECALLS, detail=f"Campaign {r.campaign_number}. {r.summary[:240]}",
              impact=impact)

    # C13 price far below market; red when the chat also shows a scam signal (C12)
    if comps and comps.median and comps.n > 0 and listing.asking_price < PRICE_BELOW_MARKET_RATIO * comps.median:
        scam = any(e.type == EvidenceType.SCAM_SIGNAL and e.severity == Severity.RED for e in chat_evidence)
        b.add(EvidenceType.PRICE_BELOW_MARKET, Severity.RED if scam else Severity.YELLOW,
              f"The price is well below similar cars ({comps.median:,} median).", EvidenceSource.COMPS,
              detail=f"Asking {listing.asking_price:,} vs a median of {comps.median:,} from {comps.n} comparable listings."
              + (" Combined with the chat red flags, this matches a common scam pattern." if scam else ""))

    # C12 chat evidence (from scan_chat) is appended as-is, then everything gets fresh ids
    evidence = b.items + [e.model_copy() for e in chat_evidence]
    for i, e in enumerate(evidence, start=1):
        e.id = f"EV-{i:02d}"

    verdict = VerificationReport.compute_verdict(evidence)
    total_impact = sum(e.price_impact for e in evidence if e.verified)
    fair_low = fair_high = None
    if comps and comps.low and comps.median:
        floor = int(listing.asking_price * FAIR_PRICE_FLOOR_RATIO)
        fair_low = max(floor, comps.low - total_impact)
        fair_high = max(floor, comps.median - total_impact)
    questions = [inspection_question(e) for e in evidence if e.severity == Severity.YELLOW]
    if recalls:
        questions.append("Check this VIN at nhtsa.gov/recalls to confirm the recalls were repaired.")
    questions = list(dict.fromkeys(questions))

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
