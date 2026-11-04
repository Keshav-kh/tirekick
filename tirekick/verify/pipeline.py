"""run_verification: the one call A makes after a proof video arrives. Owner: B.

Target < 90 s end to end. The video analysis (3 runs, in parallel inside analyze_proof_take) is the
long pole, so comps (web search, ~20-30 s) run alongside it. VIN decode and recalls depend on the
VIN read from the video, so they follow. Every step except the analysis is optional: a failure is
logged and the report is built without it.

TIREKICK_RUNS overrides the number of Muse Spark samples (default 3; use 1 for cheap smoke tests).
SAM_HIGHLIGHTS=0 turns the SAM 3.1 overlays off.
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor

from tirekick.config import env, fake_ai
from tirekick.models import Deal, VerificationReport
from tirekick.verify.report_builder import build_report, extract_evidence_frames
from tirekick.verify.scam import scan_chat
from tirekick.verify.vin import _VIN_RE, normalize_vin

log = logging.getLogger(__name__)


def runs_setting(default: int = 3) -> int:
    try:
        return max(1, int(env("TIREKICK_RUNS", str(default))))
    except ValueError:
        return default


def run_verification(deal: Deal, video_path: str) -> VerificationReport:
    # Import the dispatching wrappers so fake mode applies here too.
    from tirekick import verify
    from tirekick.verify import muse

    if deal.listing is None or deal.challenge is None:
        raise ValueError("run_verification needs deal.listing and deal.challenge")
    listing, challenge = deal.listing, deal.challenge
    timings: dict[str, float] = {}
    t_start = time.time()

    def timed(name, fn, *args):
        t0 = time.time()
        try:
            return fn(*args)
        finally:
            timings[name] = round(time.time() - t0, 2)

    def safe_comps():
        try:
            return verify.price_comps(listing)
        except Exception as e:  # noqa: BLE001
            log.warning("comps failed: %s", e)
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        comps_future = pool.submit(timed, "comps", safe_comps)
        analysis = timed("analysis", verify.analyze_proof_take, video_path, challenge, listing, runs_setting())
        comps = comps_future.result()

    read = normalize_vin(analysis.windshield_vin_read or "")
    vin = read if _VIN_RE.match(read) else (listing.vin or None)
    vin_decode = None
    if vin:
        try:
            vin_decode = timed("vin_decode", verify.decode_vin, vin)
        except Exception as e:  # noqa: BLE001 - network failure must not kill the report
            log.warning("vPIC decode failed: %s", e)

    make = (vin_decode.make if vin_decode else None) or listing.make
    model = (vin_decode.model if vin_decode else None) or listing.model
    year = (vin_decode.year if vin_decode else None) or listing.year
    recalls = []
    if make and model and year:
        try:
            recalls = timed("recalls", verify.lookup_recalls, make, model, year)
        except Exception as e:  # noqa: BLE001
            log.warning("recalls lookup failed: %s", e)

    chat_evidence = timed("scan_chat", scan_chat, deal.chat, listing, comps)
    report = build_report(deal.deal_id, listing, challenge, analysis, vin_decode, recalls, comps, chat_evidence)
    timed("frames", extract_evidence_frames, report, video_path)
    if not fake_ai():
        from tirekick.verify.highlight import highlight_evidence
        timed("highlights", highlight_evidence, report)
    timings["total"] = round(time.time() - t_start, 2)
    if not fake_ai():
        muse.log_run("pipeline", {"deal_id": deal.deal_id, "video": video_path, "verdict": report.verdict.value,
                                  "timings_s": timings, "evidence": [e.type.value for e in report.evidence]})
    log.info("run_verification %s: %s in %.1fs %s", deal.deal_id, report.verdict.value, timings["total"], timings)
    return report
