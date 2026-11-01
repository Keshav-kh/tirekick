"""Run the whole verification on a local video. Owner: B (C uses it for the eval).

  python scripts/verify_clip.py --video clips/honest_civic_01.mp4 --code K7Q2XM --listing samples/listing.json
  python scripts/verify_clip.py --video clips/x.mp4 --code K7Q2XM --listing-text "2015 Honda Civic LX, 84k miles, $9,400"

  # cheap smoke test on the synthetic clip (1 run, frames mode), with pass/fail checks:
  python scripts/make_synthetic_clip.py
  python scripts/verify_clip.py --video data/clips/synthetic_cut.mp4 --code K7Q2XM \
      --listing samples/listing.json --runs 1 --check-synthetic

  # plumbing only, no key needed:
  python scripts/verify_clip.py --video data/clips/synthetic_cut.mp4 --code K7Q2XM --listing samples/listing.json --fake
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tirekick import verify  # noqa: E402
from tirekick.models import Deal, DealStatus, Listing, ProofChallenge, utcnow  # noqa: E402
from tirekick.verify import muse  # noqa: E402
from tirekick.verify.proof_take import scene_cuts  # noqa: E402

SYNTHETIC_VIN = "1HGCM82633A004352"


def synthetic_checks(report, code: str, cut_at: float) -> list[tuple[str, bool, str]]:
    a = report.analysis
    if a is None:
        return [("analysis", False, "no analysis")]
    near = [t for t in a.cut_timestamps_s if abs(t - cut_at) <= 1.5]
    return [
        ("code_read", a.code_read == code, f"read {a.code_read!r}, expected {code!r}"),
        ("windshield VIN", a.windshield_vin_read == SYNTHETIC_VIN,
         f"read {a.windshield_vin_read!r}, expected {SYNTHETIC_VIN}"),
        ("cut detected", a.continuous_take is False and bool(near),
         f"continuous_take={a.continuous_take}, cuts={a.cut_timestamps_s}, expected one near {cut_at:g}s"),
    ]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--video", required=True)
    ap.add_argument("--code", required=True, help="the 6-char challenge code shown in the video")
    ap.add_argument("--listing", help="path to a Listing JSON file")
    ap.add_argument("--listing-text", help="raw listing text (parsed with Muse Spark)")
    ap.add_argument("--deal-id", default="DEAL-0000")
    ap.add_argument("--runs", type=int, help="Muse Spark samples to merge (default 3; 1 for smoke tests)")
    ap.add_argument("--mode", choices=["frames", "native"], help="sets MUSE_VIDEO_MODE")
    ap.add_argument("--no-highlights", action="store_true", help="skip SAM 3.1 overlays")
    ap.add_argument("--fake", action="store_true", help="fixture AI (TIREKICK_FAKE_AI=1), no key needed")
    ap.add_argument("--check-synthetic", action="store_true",
                    help="assert code, windshield VIN and the cut on scripts/make_synthetic_clip.py output")
    ap.add_argument("--cut-at", type=float, default=6.0, help="where the synthetic clip's cut is")
    ap.add_argument("--out", help="write the full report JSON here")
    args = ap.parse_args()

    if args.fake:
        os.environ["TIREKICK_FAKE_AI"] = "1"
    if args.runs:
        os.environ["TIREKICK_RUNS"] = str(args.runs)
    if args.mode:
        os.environ["MUSE_VIDEO_MODE"] = args.mode
    if args.no_highlights:
        os.environ["SAM_HIGHLIGHTS"] = "0"
    fake = os.environ.get("TIREKICK_FAKE_AI", "0") == "1"
    if not fake and not muse.available():
        sys.exit("META_API_KEY (or MODEL_API_KEY) is not set. Put it in .env, or pass --fake for fixture data.")
    if not Path(args.video).is_file():
        sys.exit(f"video not found: {args.video}")

    if args.listing:
        listing = Listing.model_validate_json(Path(args.listing).read_text(encoding="utf-8"))
    elif args.listing_text:
        listing = verify.parse_listing(text=args.listing_text, listing_id=args.deal_id)
    else:
        sys.exit("give --listing or --listing-text")

    now = utcnow()
    challenge = ProofChallenge(challenge_id="CH-cli", deal_id=args.deal_id, code=args.code.upper(),
                               issued_at=now, expires_at=now + timedelta(hours=24), message_text="")
    deal = Deal(deal_id=args.deal_id, buyer_wa_id="cli", status=DealStatus.PROOF_RECEIVED,
                listing=listing, challenge=challenge)
    report = verify.run_verification(deal, args.video)

    banner = "FAKE MODE (fixture AI). " if fake else ""
    print(f"\n{banner}VERDICT: {report.verdict.value.upper()}   fair {report.fair_price_low}-{report.fair_price_high}"
          f"   comps n={report.comps.n if report.comps else 0}")
    for e in report.evidence:
        t = f"@{e.clip_start_s:g}s" if e.clip_start_s is not None else ""
        hl = " [hl]" if e.highlight_path else ""
        print(f"  {e.id} [{e.severity.value:6}] {e.type.value:22} {t:8} {e.summary}{hl}")
    a = report.analysis
    if a:
        print(f"\nanalysis: runs={a.runs} agreement={a.agreement} duration={a.duration_s}s code={a.code_read!r} "
              f"windshield_vin={a.windshield_vin_read!r} door_vin={a.door_vin_read!r}")
        print(f"          continuous_take={a.continuous_take} cuts={a.cut_timestamps_s} "
              f"ffmpeg_scene_cuts={scene_cuts(args.video)}")
        print(f"          notes={a.model_notes!r}")
    if args.out:
        Path(args.out).write_text(report.model_dump_json(indent=2), encoding="utf-8")
        print(f"report written to {args.out}")
    else:
        print(json.dumps({"verdict": report.verdict.value, "evidence": [e.type.value for e in report.evidence]}))

    if args.check_synthetic:
        checks = synthetic_checks(report, args.code.upper(), args.cut_at)
        print("\nSYNTHETIC CLIP CHECKS" + (" (fake mode: fixtures, not a real result)" if fake else ""))
        for name, ok, detail in checks:
            print(f"  {'PASS' if ok else 'FAIL'}  {name:15} {detail}")
        if not all(ok for _, ok, _ in checks):
            sys.exit(1)


if __name__ == "__main__":
    main()
