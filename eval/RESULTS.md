# Results (misses included)

_Last updated: Nov 3 2026, Afif (C)._

**Read this first.** We had no access to a real car during the hackathon. Every video test below uses
**AI-generated clips** (Higgsfield, Seedance 2.5) of a 2014 Honda Civic, stitched from 5-second pieces
with `eval/stitch_clips.py`. These results show how TireKick handles synthetic proof videos.
Real-dashboard accuracy and the false-alarm rate on honest sellers are **untested**, and testing them
is our first next step. The negotiation study uses **AI-played sellers**, not people.

## 1. Listing study (200 listings)

Source: the public Kaggle "US Cars" dataset (AuctionExport auction listings, ~2020), 200 clean-title US
listings under $15k, sampled with seed 42 by `eval/import_usa_cars.py`. We did not scrape any site.

| Metric | Value |
|---|---|
| Listings | 200 (174 North-American VINs) |
| Invalid VIN check digit | 0/174 (0%) |
| Year wrong vs VIN | 0/200 (0%) |
| Make wrong vs VIN | 1/200 (0.5%) |
| Model has ≥ 1 NHTSA recall | **192/200 (96%)** |

- The dataset's model field is often truncated (e.g. "door", "se"), so model mismatches (58%) reflect
  the dataset's data quality, not seller dishonesty. We don't report them as a finding.
- The dataset has no trim or description text, so trim mismatch and "the listing mentions the recall"
  can't be measured.
- Recalls are model-level (year/make/model), not VIN-level: the car's model has been recalled, not
  necessarily this exact car.

**Plus 3 current private-seller listings** (Craigslist Brooklyn, cars by owner, opened and screenshotted
by hand, `eval/data/demo_listings.csv`). All 3 VINs are valid and decode to the year/make/model listed,
and none of the 3 descriptions mention a recall:

| Listing | Asking | Seller says | NHTSA recalls for that year/make/model |
|---|---|---|---|
| 2020 Nissan Sentra S | $7,900 | "Runs and drives great" | 4 (incl. steering tie rods, headlights) |
| 2004 Honda Element LX | $2,700 | "Runs and drives excellent, clean title" | **11** (incl. driver and passenger airbag inflators) |
| 2005 Scion tC | $1,700 | "Runs and drives great, clean title" | 4 (incl. airbags, side airbags) |

Small mismatches a buyer could miss: the Element is listed as a "sedan" while its door sticker says MPV,
and the Scion is listed as a "Toyota". Recalls are model-level, not proof this exact car is unrepaired.

## 2. Light check (bulb check at key-on)

`python eval/light_check_eval.py eval/data/light_check.csv --runs 3`, 6 AI clips (4 full takes,
2 cropped to a dashboard close-up), 3 Muse Spark runs each, merged by majority vote.

| Metric | Value |
|---|---|
| Hidden-light catch rate | **0/3 (0%)** |
| False alarms on all-lights-on clips | 0/3 (0%) |
| Mean run agreement | 0.75 |

**Why every hidden light was missed:** Muse Spark did not say the check-engine light was *on*; it said
it **couldn't tell** (`lit_at_key_on = None`), even on the close-up, where it clearly reported the
battery, oil and ABS lights as lit. The report code only flags a light reported as *off*, and when some
lights are seen and none are off it adds a green "all N warning lights came on" line. So **a
hard-to-see dashboard currently passes.**

Fix (proposed to B): if any must-light (check-engine, airbag, ABS) is `None`, add a yellow
"couldn't confirm this light came on, please refilm the dashboard up close" and drop the green line.
Status: fix proposed to B, not yet applied at the time of writing.

## 3. Red team ("try to fool TireKick")

`python eval/redteam_eval.py eval/data/redteam.csv`. Six attempts on the AI-generated clips.

| Spoof type | Attempts | Caught (red) | Right reason |
|---|---|---|---|
| ai_generated | 2 | 2/2 (100%) | 2/2 (100%) |
| old_video (no code / wrong code) | 3 | 3/3 (100%) | 3/3 (100%) |
| different_car | 1 | 1/1 (100%) | 1/1 (100%) |
| spliced, taped_light, warm_engine, screen_replay | 0 | not tested (no real car) | |
| **All spoof attempts** | 6 | **6/6 (100%)** | 6/6 (100%) |
| Honest controls (false alarms) | 0 | **untested**: no real honest clips | |

"Right reason" = at least one of the evidence types we expected for that attack was in the report
(`eval/out/redteam_scored.csv`).

**How to read 6/6.** Every attempt was a spoof attempt, and every one was flagged red. With no honest
real-car clip in the set, we can't yet show that TireKick lets a genuine car through: a system that
flagged everything would also score 6/6. Measuring the false-alarm rate on real, honest proof takes is
the first thing we'd do with access to a car.

Observed while debugging: on the AI "honest" take, Muse Spark read the code K7Q2XM correctly and
reported that the windshield VIN and door VIN don't match (the AI invents both), which is a correct red flag.
The hidden-light clip (R02) was flagged red, but the light check itself did not catch the dark
check-engine light (see section 2), so that catch came from the other checks.

Misses: none among the 6 spoof attempts. The light-check gap in section 2 is the main known weakness.

## 4. Negotiation study (simulated sellers)

`python eval/sim_negotiation.py --repeats 3`: 10 seller personalities × 2 conditions × 3 repeats = 60
negotiations. Sellers are played by Muse Spark with a secret lowest price **enforced in code**.
"Student alone" is an AI buyer that only sees the listing; "TireKick" is B's real negotiation agent with
the verification report. Same budget and round limit for both.

| Condition | n | Surplus captured (mean / median) | Avg discount off asking | No deal |
|---|---|---|---|---|
| Student alone (AI buyer, listing only) | 30 | 0.51 / 0.50 | 7.3% | 15 of 30 |
| **TireKick** | 30 | **0.84 / 0.84** | **12.6%** | **0 of 30** |

Surplus captured = (asking − final) / (asking − seller's secret lowest price): 0 means the buyer paid
the asking price, 1 means they got the seller down to their secret floor.

**Headline:** against AI-played sellers, TireKick captured 84% of the available discount vs 51% for a
student negotiating alone with only the listing, and reached a deal in 30/30 negotiations vs 15/30.

Caveats:
- "No deal" includes running out of rounds (6 seller replies) as well as a real walk-away.
- Surplus and discount are averaged over **completed deals only**, so the student's figures cover just
  their 15 successful negotiations; averaging in the failures would make the gap larger, not smaller.
- The sellers are played by an LLM (Muse Spark), and the student buyer is too. Real people may
  negotiate differently; a study with real sellers is a next step.
- TireKick's edge here comes from the verification report (open recalls, higher real mileage, warning
  lights, price comps), which the student buyer never sees. That is the product's design, not a bias
  in the test.
- TireKick parser false agreements: **0** in 30 negotiations (the parser bug in section 5 exists but
  was not triggered by these sellers).

## 5. Bugs found by the evaluation (reported to B)

1. **Blurry dashboard passes:** "can't tell" on a must-light is treated as fine, and a green "all lights
   came on" line is added (`report_builder.py`). See §2.
2. **Silent failure without ffmpeg:** `analyze_proof_take` returns an empty "saw nothing" analysis
   instead of erroring, so a misconfigured server would pass every car.
3. **Negotiation parser:** `apply_seller_reply` treats "okay I can't go that low" as agreement (it sees
   "okay" and no price). Test: `tests/test_sim_negotiation.py::test_refusal_with_okay_is_not_agreement`. Not triggered in the 30 simulated TireKick negotiations.
4. **Scion recall lookup crashes:** NHTSA's VIN decoder returns make "Toyota", model "Scion tC", but
   the recalls API only accepts make "Scion", model "tC", so `lookup_recalls` gets HTTP 400 for every
   Scion. Fix: map Toyota "Scion X" to make "Scion", model "X" in `recalls.py` (found on the demo listing).
