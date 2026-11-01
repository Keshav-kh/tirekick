# Evaluation (owner: C)

The full protocols are in [docs/workstream-C-eval-demo.md](../docs/workstream-C-eval-demo.md). This folder holds the data templates and the scoring scripts.

| Study | Data you fill in | Script | Output |
|---|---|---|---|
| 100-listing VIN study | `data/listings.csv` | `python eval/vin_listing_study.py eval/data/listings.csv` | `out/listings_scored.csv` + summary |
| Red team | `data/redteam.csv` (+ a listing JSON per car) | `python eval/redteam_eval.py eval/data/redteam.csv` | `out/redteam_scored.csv` + table |
| Light check | `data/light_check.csv` | `python eval/light_check_eval.py eval/data/light_check.csv --runs 3` | `out/light_check_scored.csv` |
| Negotiation study | `data/negotiation_study.csv` | `python eval/negotiation_study.py eval/data/negotiation_study.csv` | summary per condition |

- Clip paths in the CSVs are **local paths** to videos you downloaded from the shared Drive. Videos never go in git.
- Listing JSON files (for the red team) follow `tirekick.models.Listing`; see `samples/listing.json`.
- `eval/out/` is gitignored. Copy the final numbers into `RESULTS.md`, which **is** committed.
- The listing study and the real red-team runs need the real APIs, so unset `TIREKICK_FAKE_AI`.
