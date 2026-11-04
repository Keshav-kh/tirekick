"""Day-1 test (docs/workstream-B-intelligence.md section 0). Owner: B.

  python scripts/day1_test.py --clips eval/data/light_check.csv --runs 3
  python scripts/day1_test.py --clips eval/data/light_check.csv --runs 3 --mode native
  python scripts/day1_test.py --clips tests/fixtures/day1_sample.csv --fake     # plumbing check only

CSV columns (C's eval/data/light_check.csv): clip, year, make, model, code, vin, masked_light
(masked_light = the taped light, e.g. check_engine, or "none").

Each clip is analysed `runs` times, each time as ONE Muse Spark sample (analyze_proof_take with
runs=1), so you see raw run-to-run agreement rather than the product's majority vote (C's
eval/light_check_eval.py measures that). Prints the GO / NO-GO gates and a markdown table for the
group chat, and saves everything to data/runs/day1_<timestamp>.json.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tirekick.config import data_path  # noqa: E402
from tirekick.models import Listing, ProofChallenge, utcnow  # noqa: E402
from tirekick.verify import analyze_proof_take, muse, validate_vin  # noqa: E402
from tirekick.verify.vin import normalize_vin  # noqa: E402

SPEED_GATE_S = 60.0


def read_rows(path: str) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return [r for r in csv.DictReader(f) if (r.get("clip") or "").strip()]


def run_clip(row: dict, runs: int) -> dict:
    year = (row.get("year") or "").strip()
    listing = Listing(listing_id=row["clip"], asking_price=1, year=int(year) if year.isdigit() else None,
                      make=row.get("make") or None, model=row.get("model") or None)
    now = utcnow()
    code = (row.get("code") or "").strip().upper()
    challenge = ProofChallenge(challenge_id="CH-day1", deal_id="DEAL-0000", code=code or "AAAAAA",
                               issued_at=now, expires_at=now + timedelta(hours=1), message_text="")
    masked = (row.get("masked_light") or "none").strip().lower() or "none"
    expected_vin = normalize_vin(row.get("vin") or "")
    out = {"clip": row["clip"], "masked_light": masked, "has_code": bool(code), "has_vin": bool(expected_vin),
           "runs": []}
    for _ in range(runs):
        t0 = time.time()
        a = analyze_proof_take(row["clip"], challenge, listing, runs=1)
        vin = a.windshield_vin_read
        out["runs"].append({
            "seconds": round(time.time() - t0, 1),
            "ok": a.runs > 0,
            "lights_key_on": {o.light.value: o.lit_at_key_on for o in a.lights},
            "lights_after_start": {o.light.value: o.on_after_start for o in a.lights},
            "code_read": a.code_read, "code_ok": bool(code) and a.code_matches,
            "vin_read": vin, "vin_check_digit": bool(vin) and validate_vin(vin)[0],
            "vin_matches_label": bool(expected_vin) and normalize_vin(vin or "") == expected_vin,
            "continuous_take": a.continuous_take, "cuts": a.cut_timestamps_s,
            "odometer": a.odometer_read, "engine_cold": a.engine_cold, "notes": a.model_notes[:300],
        })
    rs = out["runs"]
    if masked != "none":
        out["caught_all_runs"] = all(r["lights_key_on"].get(masked) is False for r in rs)
        out["caught_runs"] = sum(r["lights_key_on"].get(masked) is False for r in rs)
    out["false_alarm_runs"] = sum(
        any(v is False and light != masked for light, v in r["lights_key_on"].items()) for r in rs)
    out["failed_runs"] = sum(not r["ok"] for r in rs)
    return out


def gates(results: list[dict], rows: list[dict]) -> dict:
    taped = [r for r in results if r["masked_light"] != "none"]
    honest = [r for r in results if r["masked_light"] == "none"]
    with_vin = [(res, row) for res, row in zip(results, rows) if (row.get("vin") or "").strip()]
    with_code = [(res, row) for res, row in zip(results, rows) if (row.get("code") or "").strip()]
    all_runs = [x for r in results for x in r["runs"]]
    return {
        "taped_caught_all_runs": (sum(r["caught_all_runs"] for r in taped), len(taped)),
        "honest_clips_with_false_alarm": (sum(r["false_alarm_runs"] > 0 for r in honest), len(honest)),
        "any_clip_false_alarm_runs": sum(r["false_alarm_runs"] for r in results),
        "vin_runs_pass_check_digit": (sum(x["vin_check_digit"] for res, _ in with_vin for x in res["runs"]),
                                      sum(len(res["runs"]) for res, _ in with_vin)),
        "vin_runs_match_label": (sum(x["vin_matches_label"] for res, _ in with_vin for x in res["runs"]),
                                 sum(len(res["runs"]) for res, _ in with_vin)),
        "code_runs_exact": (sum(x["code_ok"] for res, _ in with_code for x in res["runs"]),
                            sum(len(res["runs"]) for res, _ in with_code)),
        "slowest_run_s": max((x["seconds"] for x in all_runs), default=0.0),
        "mean_run_s": round(sum(x["seconds"] for x in all_runs) / len(all_runs), 1) if all_runs else 0.0,
        "failed_runs": sum(r["failed_runs"] for r in results),
    }


def verdicts(g: dict) -> dict[str, bool]:
    caught, taped = g["taped_caught_all_runs"]
    fa, _ = g["honest_clips_with_false_alarm"]
    vin_ok, vin_n = g["vin_runs_pass_check_digit"]
    code_ok, code_n = g["code_runs_exact"]
    return {
        "Lights": taped > 0 and caught == taped and fa == 0 and g["any_clip_false_alarm_runs"] == 0,
        "VIN and code": (vin_n == 0 or vin_ok == vin_n) and (code_n == 0 or code_ok == code_n) and (vin_n + code_n) > 0,
        "Speed": g["slowest_run_s"] <= SPEED_GATE_S and g["failed_runs"] == 0,
    }


def markdown(results: list[dict], g: dict, v: dict, mode: str, model: str, fake: bool) -> str:
    lines = []
    if fake:
        lines.append("**FAKE MODE: fixture data, NOT a real day-1 result.**\n")
    lines.append(f"Day-1 test, mode `{mode}`, model `{model}`, {len(results[0]['runs']) if results else 0} runs/clip\n")
    lines.append("| clip | taped | caught (runs) | false-alarm runs | code exact | VIN ok | slowest s |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in results:
        rs = r["runs"]
        caught = f"{r['caught_runs']}/{len(rs)}" if r["masked_light"] != "none" else "-"
        code = f"{sum(x['code_ok'] for x in rs)}/{len(rs)}" if r["has_code"] else "-"
        vin = f"{sum(x['vin_check_digit'] for x in rs)}/{len(rs)}" if r["has_vin"] else "-"
        lines.append(f"| {Path(r['clip']).name} | {r['masked_light']} | {caught} | {r['false_alarm_runs']} | "
                     f"{code} | {vin} | {max(x['seconds'] for x in rs):.1f} |")
    c, t = g["taped_caught_all_runs"]
    fa, h = g["honest_clips_with_false_alarm"]
    vo, vn = g["vin_runs_pass_check_digit"]
    co, cn = g["code_runs_exact"]
    lines.append("")
    lines.append(f"- **Lights: {'GO' if v['Lights'] else 'NO-GO'}**: taped caught in every run {c}/{t}; "
                 f"honest clips with any false alarm {fa}/{h}")
    lines.append(f"- **VIN and code: {'GO' if v['VIN and code'] else 'NO-GO'}**: VIN check digit {vo}/{vn} runs; "
                 f"code exact {co}/{cn} runs")
    lines.append(f"- **Speed: {'GO' if v['Speed'] else 'NO-GO'}**: slowest run {g['slowest_run_s']:.1f}s "
                 f"(mean {g['mean_run_s']:.1f}s, gate {SPEED_GATE_S:.0f}s); failed runs {g['failed_runs']}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clips", default="eval/data/light_check.csv")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--mode", choices=["frames", "native"], help="sets MUSE_VIDEO_MODE")
    ap.add_argument("--fake", action="store_true", help="fixture data (TIREKICK_FAKE_AI=1): checks the plumbing only")
    args = ap.parse_args()

    if args.fake:
        os.environ["TIREKICK_FAKE_AI"] = "1"
    if args.mode:
        os.environ["MUSE_VIDEO_MODE"] = args.mode
    fake = os.environ.get("TIREKICK_FAKE_AI", "0") == "1"
    if not fake and not muse.available():
        sys.exit("META_API_KEY (or MODEL_API_KEY) is not set. Put it in .env, or use --fake to test the plumbing.")
    if not Path(args.clips).exists():
        sys.exit(f"{args.clips} not found; C labels the clips there (clip,year,make,model,code,vin,masked_light)")
    rows = read_rows(args.clips)
    if not rows:
        sys.exit(f"no rows in {args.clips}")
    missing = [r["clip"] for r in rows if not fake and not Path(r["clip"]).exists()]
    if missing:
        sys.exit("clip files not found (download them from the Drive first):\n  " + "\n  ".join(missing))

    mode = os.environ.get("MUSE_VIDEO_MODE", "frames")
    print(("FAKE MODE (fixtures): " if fake else "") + f"{len(rows)} clips x {args.runs} runs, mode={mode}, "
          f"model={muse.model_id()}\n")
    results = []
    for row in rows:
        res = run_clip(row, args.runs)
        results.append(res)
        print(f"{Path(res['clip']).name:40} masked={res['masked_light']:13} "
              f"key_on[{res['masked_light'] if res['masked_light'] != 'none' else 'check_engine'}]="
              f"{[x['lights_key_on'].get(res['masked_light'] if res['masked_light'] != 'none' else 'check_engine') for x in res['runs']]} "
              f"t={[x['seconds'] for x in res['runs']]}")
    g = gates(results, rows)
    v = verdicts(g)
    md = markdown(results, g, v, mode, muse.model_id(), fake)
    print("\n" + md)
    out = data_path("runs", f"day1_{int(time.time())}.json")
    out.write_text(json.dumps({"fake": fake, "mode": mode, "model": muse.model_id(), "gates": g, "go": v,
                               "results": results}, indent=2, default=str), encoding="utf-8")
    print(f"\nraw results: {out}")


if __name__ == "__main__":
    main()
