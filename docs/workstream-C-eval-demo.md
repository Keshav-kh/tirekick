# Workstream C: Evaluation, demo and submission (branch `eval-demo`)

**You own:** `eval/**`, `demo/**`, the results section of `README.md`, and the submission itself.
**You call:** B's functions (`tirekick.verify.*`) and `scripts/verify_clip.py`; A's `/dev/simulate` and the report page.

Judges skim thousands of entries. Your numbers and your video decide whether ours gets a second look. Past winners had proof beyond the demo, and you're building ours.

---

## 1. Deliverables, in priority order

| # | Deliverable | Done when | Due (ET) |
|---|---|---|---|
| C1 | Cold-start clips for B's day-1 test | 5–8 clips in Drive, labelled in `eval/data/light_check.csv` | **Sun Nov 1, 5 PM** |
| C2 | 100-listing VIN study | `eval/data/listings.csv` has ≥ 100 rows; `eval/vin_listing_study.py` output in `RESULTS.md` | Tue Nov 3, 6 PM |
| C3 | Red team | ≥ 10 fake attempts across 6 types, plus 5 honest controls, scored | Tue Nov 3, 6 PM |
| C4 | Light check eval | Catch rate and false-alarm rate over 3 runs per clip | Tue Nov 3, noon |
| C5 | Negotiation study | 10 participants × 2 conditions, results computed | Tue Nov 3, 8 PM |
| C6 | Demo video (≤ 3 min) | Recorded, captioned, uploaded | Wed Nov 4, 10 AM |
| C7 | Submission | Form filled in, README results final, repo visibility checked | **Wed Nov 4, noon** |

## 2. Filming guide (for every clip you or friends record)

- Phone in **landscape** if possible, at **720p or 1080p**, **≤ 60 s**, and **one continuous take** unless you're deliberately making a "spliced" fake.
- Follow the challenge checklist in [SPEC §6.1](SPEC.md#61-what-the-seller-is-asked-to-do).
- Use a cold engine (not driven in ~2 h) unless the clip is a "warm engine" fake.
- **Taped light:** use a small square of opaque tape on the **outside** of the dashboard glass, over the check-engine icon. **Never** tamper with wiring or bulbs, and remove the tape afterwards.
- **Consent:** whoever owns the car agrees in writing (a text message is fine) that the clip may appear in the demo. Blur license plates in the final video.
- Store clips in the shared **Google Drive** folder, `tirekick/clips/`, named `<type>_<car>_<nn>.mp4` (e.g. `honest_civic_01.mp4`, `taped_corolla_02.mp4`). **Don't commit videos to git.**

## 3. C2: the 100-listing VIN study

**The question:** how often do private used-car listings get the year, make, model or trim wrong compared with what the VIN decodes to, and how often is the car a model with NHTSA recalls that the listing never mentions?

**Collection protocol (by hand, no scraping):**
- Use public listings that **display a VIN** in the photos or text. Good sources are private-seller listings on sites that show VINs, plus Marketplace or dubizzle listings with a visible VIN plate photo.
- **Open each listing in a browser and copy the fields by hand.** Don't use bots or scrapers, and respect each site's terms.
- Record one row per listing in `eval/data/listings.csv`. Columns: `listing_id, source, url, date_collected, year, make, model, trim, engine, mileage, mileage_unit, asking_price, currency, vin, mentions_recall, notes`.
- Mix makes and price ranges; aim for most under $15k (our users).
- Split the work across all three teammates if you fall behind. 100 listings at about 2 minutes each is roughly 3.5 hours.

**Run:** `python eval/vin_listing_study.py eval/data/listings.csv`. It validates every VIN (check digit), decodes it with NHTSA vPIC, compares it with the listing, looks up recalls, and writes `eval/out/listings_scored.csv` plus a summary.

**Report (in `eval/RESULTS.md`):**
- % with an invalid VIN (for North-American VINs only)
- % where the year, make or model mismatches
- % where the trim mismatches
- % of cars whose year/make/model has ≥ 1 NHTSA recall, and of those, % where the listing doesn't mention it
- **Be honest:** if the mismatch rate is low, say so. The recall number is model-level, not VIN-level (see the SPEC honesty note).

## 4. C3: the red team ("try to fool TireKick")

Each teammate (and willing friends) tries to get a fake proof take accepted. Log each attempt in `eval/data/redteam.csv`: `attempt_id, spoof_type, clip, listing_json, challenge_code, expected_evidence, notes`.

| Spoof type | How to make it | Should trigger |
|---|---|---|
| `different_car` | Film car B while the listing and code are for car A (code card included) | `vin_listing_mismatch` / `vin_mismatch_doors` |
| `old_video` | Use a clip filmed **before** the challenge was issued (no code, or the wrong code) | `code_missing` |
| `spliced` | Edit two clips together (good dashboard from another car) | `take_has_cuts` |
| `taped_light` | Tape over the check-engine icon (see the filming guide) | `warning_light_hidden` |
| `warm_engine` | Drive 10 min first, then film | `engine_warm` |
| `screen_replay` | Play an honest clip on a laptop and film the screen with a phone | `screen_replay` |
| `honest` (control) | A real, correct proof take | **no red** (measures false alarms) |

Aim for 2 or more of each fake type plus **5 honest controls**.

**Run:** `python eval/redteam_eval.py eval/data/redteam.csv`, which calls B's pipeline on each clip.

**Report:** catch rate per type, the overall catch rate, the false-alarm rate on honest clips, and **every miss explained** (judges trust a team that shows its misses).

## 5. C4: the light check

From the C1 clips plus any extras (target 6–12 clips; at least 4 with a taped light), run `python eval/light_check_eval.py eval/data/light_check.csv --runs 3`.

Report:
- **hidden-light catch rate:** taped clips where `warning_light_hidden` fired
- **false alarms:** honest clips where any light was flagged
- **run agreement**

## 6. C5: the negotiation study (friends, about 4–5 hours total)

**The question:** does TireKick's evidence-based negotiation get a better price than a student negotiating alone?

**Setup:**
- Make **10 "car cards"**. Each has a listing (asking price), a seller fact sheet that matches a pre-built TireKick report (for example, an open recall and higher-than-listed mileage), and a **secret lowest price** the friend may accept.
- Each friend plays the **seller** twice, with **two different car cards**:
  - **Condition H (human):** a teammate negotiates as the buyer over normal WhatsApp for at most 5 minutes, with only the listing to go on.
  - **Condition T (TireKick):** the buyer side runs through TireKick. The buyer approves the drafts **without editing** them, and the friend chats with the bot.
- **Alternate the order:** odd-numbered friends do H first, even-numbered friends do T first. Alternate which car card goes with which condition too.
- **WhatsApp limit:** the test number allows only 5 recipients. Friends use one of 2 dedicated **seller phones** that are registered recipients. If A has time, they can use a simple web chat on `/dev/simulate` instead.
- Tell participants it's a hackathon study. No real money changes hands, and no names go in the results.

**Record** in `eval/data/negotiation_study.csv`: `participant, order, card_id, condition, asking, reservation, final_price, rounds, minutes, walked_away`.

**Run:** `python eval/negotiation_study.py eval/data/negotiation_study.csv`. Metric: **surplus captured** = (asking − final) / (asking − reservation). Report the mean, the median and the walk-away count per condition.

## 7. C6: the demo video (3 minutes, recorded)

The script is in `demo/SCRIPT.md`; use it as the starting point and adjust as needed. Recording rules:
- **Record; don't run it live.** B caches results for the hero clips so the timing is reliable.
- Screen-record WhatsApp on a phone (iOS screen recording or Android's built-in recorder) and the report page on a laptop.
- Label anything staged **on screen** ("staged: tape over the check-engine light").
- Add captions to every line (judges often watch muted).
- Show **real numbers** from `RESULTS.md`, with misses.
- End card: the team name, the repo link, "Built with Muse Spark, SAM 3.1 and WhatsApp."
- Export 1080p and upload it where the submission form asks (YouTube unlisted or a direct upload).

## 8. C7: the submission

- **Written description:** problem, solution, how it works, how each Meta tool is used (SPEC §9), results (from RESULTS.md), honest limits, what's next. Put a draft in `demo/SUBMISSION.md` and get a review from both teammates by Tue night.
- **Track and theme:** Indie track, "Build for Your World." Check the official rules in the participant portal for required fields, video length, and whether the repo must be public.
- **README:** fill in the results table and the demo video link.
- **Repo visibility:** the repo is **private** while we build. If the rules require a public repo, make it public on Wed morning, **after** checking that no keys are in the git history (`git log -p | grep -i "api_key\|token"`).

## 9. Your timeline

| When (ET) | Target |
|---|---|
| Sun Nov 1 | C1 clips to B by 5 PM; listing spreadsheet started (≥ 20); recruit 10 friends for the negotiation study |
| Mon Nov 2 | 50+ listings; film all red-team clips; book negotiation-study slots for Tue. **Integration 1 at 9 PM** |
| Tue Nov 3 | Run C3, C4, C5; finish C2; write RESULTS.md; record demo takes; submission draft. **Freeze at 9 PM** |
| Wed Nov 4 | Final edit by 10 AM, submit by noon |
