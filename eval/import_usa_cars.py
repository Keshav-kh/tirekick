"""C2 data source: sample listings from the public "US Cars" dataset into eval/data/listings.csv. Owner: C.

  python eval/import_usa_cars.py               # 200 listings, under $15k, clean title, seed 42
  python eval/vin_listing_study.py eval/data/listings.csv

Source: the Kaggle "US Cars Dataset" (doaaalsenani/usa-cers-dataset), mirrored on GitHub. It was
scraped by its author from AuctionExport.com (North American car auctions) around 2020. We did not
scrape any site ourselves.

Honesty notes for RESULTS.md:
- These are AUCTION listings (mostly dealers), not private sellers, and about 2020, not today.
- The dataset's `model` column is often truncated or wrong (e.g. a Ford listed as "se"), so a model
  mismatch here mostly measures the dataset's own data quality. Report year/make separately.
- The listings have no description text, so "listing never mentions the recall" is trivially true;
  report only "model has >= 1 NHTSA recall".
"""

from __future__ import annotations

import argparse
import csv
import random
import urllib.request
from pathlib import Path

from _common import OUT, ROOT

URL = "https://raw.githubusercontent.com/rashida048/Datasets/master/USA_cars_datasets.csv"
CACHE = OUT / "usa_cars_raw.csv"
COLUMNS = ["listing_id", "source", "url", "date_collected", "year", "make", "model", "trim", "engine",
           "mileage", "mileage_unit", "asking_price", "currency", "vin", "mentions_recall", "notes"]


def load_raw() -> list[dict]:
    if not CACHE.exists():
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(URL, CACHE)
    with open(CACHE, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def eligible(r: dict, max_price: int, clean_only: bool) -> bool:
    vin = r["vin"].strip()
    try:
        price = float(r["price"])
    except ValueError:
        return False
    return (r["country"].strip() == "usa" and len(vin) == 17 and 500 <= price <= max_price
            and (not clean_only or r["title_status"].strip() == "clean vehicle"))


def to_row(r: dict) -> dict:
    return {
        "listing_id": f"usacars-{r[''].strip()}",
        "source": "kaggle_us_cars (AuctionExport, ~2020)",
        "url": "",
        "date_collected": "dataset",
        "year": r["year"].strip(),
        "make": r["brand"].strip(),
        "model": r["model"].strip(),
        "trim": "",
        "engine": "",
        "mileage": int(float(r["mileage"])),
        "mileage_unit": "mi",
        "asking_price": int(float(r["price"])),
        "currency": "USD",
        "vin": r["vin"].strip().upper(),
        "mentions_recall": "",
        "notes": f"title={r['title_status'].strip()}; lot={r['lot'].strip()}; state={r['state'].strip()}",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--max-price", type=int, default=15000)
    ap.add_argument("--include-salvage", action="store_true")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=str(ROOT / "eval" / "data" / "listings.csv"))
    args = ap.parse_args()

    pool = [r for r in load_raw() if eligible(r, args.max_price, not args.include_salvage)]
    sample = random.Random(args.seed).sample(pool, min(args.n, len(pool)))
    with open(args.out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(to_row(r) for r in sample)
    print(f"Eligible listings: {len(pool)}. Wrote {len(sample)} (seed {args.seed}) to {args.out}")
    print("Next: python eval/vin_listing_study.py eval/data/listings.csv   (needs internet for NHTSA)")


if __name__ == "__main__":
    main()
