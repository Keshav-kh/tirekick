"""C3: red team. Owner: C.

  python eval/redteam_eval.py eval/data/redteam.csv

Each row is one attempt to fool TireKick (or an honest control). A fake counts as CAUGHT if the
verdict is RED; "expected evidence hit" checks the right reason fired. Honest controls measure
false alarms (verdict RED on an honest clip).
"""

from __future__ import annotations

import sys
from collections import defaultdict

from _common import OUT, deal_for_clip, pct, read_rows, write_rows

from tirekick import verify


def main(path: str) -> None:
    rows = read_rows(path)
    results = []
    for r in rows:
        deal = deal_for_clip(r["listing_json"], r["challenge_code"], deal_id="DEAL-9000")
        report = verify.run_verification(deal, r["clip"])
        types = {e.type.value for e in report.evidence}
        expected = {t.strip() for t in (r.get("expected_evidence") or "").split(";") if t.strip()}
        results.append({
            "attempt_id": r["attempt_id"], "spoof_type": r["spoof_type"], "verdict": report.verdict.value,
            "caught": report.verdict.value == "red",
            "expected_hit": bool(expected & types) if expected else "",
            "evidence": ";".join(sorted(types)), "notes": r.get("notes", ""),
        })
    write_rows(OUT / "redteam_scored.csv", results)

    by_type = defaultdict(list)
    for x in results:
        by_type[x["spoof_type"]].append(x)
    print(f"{'type':16} {'caught':>12} {'right reason':>14}")
    fakes = [x for x in results if x["spoof_type"] != "honest"]
    for t, xs in sorted(by_type.items()):
        if t == "honest":
            continue
        print(f"{t:16} {pct(sum(x['caught'] for x in xs), len(xs)):>12} "
              f"{pct(sum(x['expected_hit'] is True for x in xs), len(xs)):>14}")
    honest = by_type.get("honest", [])
    print(f"\nOverall fakes caught: {pct(sum(x['caught'] for x in fakes), len(fakes))}")
    print(f"False alarms on honest clips: {pct(sum(x['caught'] for x in honest), len(honest))}")
    print("Explain every miss in eval/RESULTS.md.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "eval/data/redteam.csv")
