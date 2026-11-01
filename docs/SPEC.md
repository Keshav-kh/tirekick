# TireKick: product spec

This is the source of truth for **what** we build. [CONTRACTS.md](CONTRACTS.md) says how the pieces connect. The three workstream docs say who builds what, and when.

---

## 1. One-line pitch

> Meta's Muse agent finds a car and haggles. **TireKick makes the car prove itself.**

## 2. The problem

- Buying a used car from a private seller (Facebook Marketplace, dubizzle) means trusting photos and a stranger's word.
- Meta launched **Muse**, a personal agent, on Sept 8, 2026. It can search Marketplace, message sellers and negotiate, but **nothing checks the car** ([Autolander](https://autolander.ai/guide/meta-muse-ai-agent-for-car-dealers/)).
- Sellers hide faults with tricks as simple as **tape over the check-engine light** ([WBTV](https://www.wbtv.com/2022/06/08/this-was-intentional-mechanic-warns-engine-light-tape-scam-used-cars/)).
- About **1 in 5 US vehicles has an open recall** (Carfax via [S&P](https://aftermarketinsight.spglobal.com/news/2171/carfax-says-high-number-of-cars-with-urgent-recalls-remain-unrepaired-in-us)).
- Car scams on Marketplace are well documented: fake listings, deposits for cars that don't exist, cloned listings ([ProPublica](https://www.propublica.org/article/facebook-grew-marketplace-to-1-billion-users-now-scammers-are-using-it-to-target-people-around-the-world), [The Drive](https://www.thedrive.com/features/ai-car-dealer-scams-are-infesting-facebook-marketplace-and-theyre-working.md)).
- **Our users** are students and young people buying a cheap first car from a private seller. They're often international students with no credit history who can't afford a dealer, and the WhatsApp-first dubizzle market in the UAE.

## 3. What TireKick is (and is not)

**Is:** a buyer's agent on WhatsApp. It:
1. reads a listing,
2. challenges the seller to film a proof-of-car take,
3. verifies that take,
4. builds an evidence report,
5. negotiates with that evidence, with the buyer approving every message.

**Is not:**
- a mechanical inspection (every report says this, and recommends a pre-purchase inspection)
- a payment system (it never moves money)
- an auto-poster or Marketplace scraper (no scraping; the buyer pastes listings)

## 4. Actors and channels

| Actor | Who in the demo | Channel |
|---|---|---|
| Buyer | A teammate ("Afif wants a 2015 Civic under $9,000") | WhatsApp chat with the TireKick bot |
| Seller | Two other teammates (Seller A: honest; Seller B: shady) | WhatsApp chat with the **same** TireKick bot number |
| TireKick | Our backend | WhatsApp Cloud API business number |

**WhatsApp constraint (important).** A WhatsApp business number can't start a free-form chat with a stranger. It needs either an approved template or a message from the user first, which opens a 24-hour window. Our flow gets around this: the buyer forwards the seller a **join link**, `https://wa.me/<BOT_NUMBER>?text=DEAL-4821`. The seller taps it and sends the pre-filled code, which opens the window. In the demo, every phone number is pre-registered as a test recipient (test numbers allow 5).

## 5. The end-to-end flow

```
BUYER                         TIREKICK                              SELLER
  │ 1. listing link/screenshot   │                                     │
  │    + "max 9000"  ───────────▶│ parse listing, VIN pre-check,       │
  │                              │ price comps                         │
  │◀── 2. summary + comps +      │                                     │
  │    "forward this link to     │                                     │
  │    the seller: wa.me/…DEAL"  │                                     │
  │ (buyer forwards the link)    │                                     │
  │                              │◀──────────── 3. "DEAL-4821" (opens 24h window)
  │                              │── 4. challenge: code K7Q2XM + ──────▶│
  │                              │     filming checklist               │
  │                              │◀──────────── 5. proof video (≤60 s, ≤16 MB)
  │                              │ 6. analyze take (Muse Spark),       │
  │                              │    VIN decode, recalls, scam scan,  │
  │                              │    build report                     │
  │◀── 7. verdict + report link  │                                     │
  │ RED → "walk away: reasons"   │── "buyer decided to pass" ─────────▶│ (after buyer OKs)
  │ GREEN/YELLOW →               │                                     │
  │◀── 8. draft opening offer    │                                     │
  │    citing evidence           │                                     │
  │ 9. "1" (approve) ───────────▶│── offer ───────────────────────────▶│
  │                              │◀──────────── 10. seller counters    │
  │◀── 11. draft counter (policy │                                     │
  │    checked)                  │                                     │
  │ … repeat until agreement, ceiling, or walk-away …                  │
  │◀── 12. "Deal at $8,150. Meet at <safe exchange zone>?"            │
  │ 13. "1" ────────────────────▶│── confirmation ────────────────────▶│
```

## 6. The proof-of-car challenge (the core idea)

### 6.1 What the seller is asked to do

The challenge message (exact text, owned by B, sent by A):

> Hi! I'm TireKick, helping a buyer who's interested in your **2015 Honda Civic**. To skip the back-and-forth, please send **one continuous video (no cuts), up to 60 seconds**:
> 1. Hold a paper with this code: **K7Q2XM**, next to the **VIN plate at the bottom of the windshield**. Keep both in frame.
> 2. Show the **VIN sticker on the driver's door jamb**.
> 3. Sit in the driver's seat. Turn the key to **ON without starting** (or press Start once without the brake). Hold for **5 seconds** on the dashboard so all the warning lights show.
> 4. Show the **odometer** and the **temperature gauge**.
> 5. **Start the engine** and keep the dashboard in view for **5 more seconds**.
>
> The engine should be **cold** (not driven in the last ~2 hours). The code expires in 24 hours.

### 6.2 Why it works

It is **liveness detection for a physical object**:

| Fake attempt | Caught by |
|---|---|
| A video of a different, healthy car | The code next to the VIN, and the windshield VIN must match the door VIN and the listing |
| An old video recorded before the listing | The one-time code can't be in it |
| Splicing a good dashboard onto this car | The continuous-take check (no cuts) and the code-to-dashboard continuity |
| Tape over the check-engine light, or a pulled bulb | The bulb check: the light must come on at key-on |
| A pre-warmed engine hiding cold-start problems | The temperature needle isn't at C, or the seller doesn't show it |
| Filming a screen that plays a video | Moiré, bezels, frame edges (Muse Spark asked explicitly) |

### 6.3 Checks performed

| # | Check | How | Evidence type if it fails | Default severity |
|---|---|---|---|---|
| C1 | The code is visible and matches | Muse Spark reads the code; compared in code | `code_missing` | red |
| C2 | One continuous take | Muse Spark reports cuts or jumps, with timestamps | `take_has_cuts` | red |
| C3 | Windshield VIN read | Muse Spark OCR, then the check digit | `vin_unreadable` / `vin_invalid` | yellow / red |
| C4 | Door VIN matches the windshield VIN | String compare | `vin_mismatch_doors` | red |
| C5 | VIN matches the listing (year, make, model, trim, engine) | NHTSA vPIC decode compared with the listing | `vin_listing_mismatch` | red if year, make or model differ; yellow if trim or engine differ |
| C6 | Recalls for this year, make and model | NHTSA Recalls API | `recall_found` | yellow |
| C7 | Bulb check: every expected light comes on at key-on | Muse Spark reports a per-light status | `warning_light_hidden` | red |
| C8 | No warning light on after the start | Muse Spark per-light status | `warning_light_on` | red for check-engine, airbag, oil or brake; yellow otherwise |
| C9 | Odometer matches the listing (±5%) | Muse Spark reads it; compared in code | `odometer_mismatch` | red if below the listing by more than 5%; yellow if above |
| C10 | Engine cold | Muse Spark reads the temperature needle | `engine_warm` | yellow |
| C11 | Not a screen recording | Muse Spark visual check | `screen_replay` | red |
| C12 | Chat red flags | Rules plus Muse Spark over the seller's messages | `scam_signal` | red |
| C13 | Price far below the comps (more than 30% under the median) | Comps compared in code | `price_below_market` | yellow (red when it comes with C12) |

**Overall verdict:**
- any **red** → `RED`: recommend walking away, no negotiation
- any **yellow** → `YELLOW`: negotiate, citing the yellows
- otherwise `GREEN`

All of this is computed **in code** from the evidence list, not by the model.

**Honesty notes (put these in the report UI):**
- **Recalls.** The NHTSA Recalls API returns recalls issued for that **year, make and model**. It does not say whether this particular VIN's recall is still unrepaired. The report says: *"Recalls exist for this model. Check whether this VIN's are repaired at nhtsa.gov/recalls."*
- **VIN check digit.** It's mandatory for North-American-market VINs (first character 1–5). Many GCC/UAE-market and imported cars don't use it, so for non-North-American VINs a failed check digit is a **yellow**, not a red.
- **Warning lights.** Which lights show at key-on varies by car. Treat **check engine, airbag/SRS and ABS** as "must light" for any car from 1996 on. The others are "expected".

## 7. Negotiation rules (hard rules, enforced in code)

1. **Ceiling.** No outgoing offer may exceed `buyer_ceiling`. This is enforced by `negotiate/policy.py`, never by the prompt.
2. **Evidence-only concessions.** Every price reduction TireKick asks for must cite at least one `Evidence.id` from the verified report. Policy rejects an offer that cites an unknown ID, or one with `verified=False`.
3. **No invented facts.** The drafted message may only mention facts that appear in the cited evidence `summary` fields, plus the comps. Policy checks that every cited ID exists. The prompt forbids anything else.
4. **Human approval.** Every message to the seller is shown to the buyer first, with reply options **1** send, **2** edit, **3** stop.
5. **No money, no addresses.** TireKick never asks for or sends payment details or home addresses. The meetup suggestion is a public **safe exchange zone** (many US police stations have them). Muse's real-world incident of sharing a seller's address is exactly what we design against ([Malwarebytes](https://www.malwarebytes.com/blog/news/2026/09/metas-muse-sent-a-facebook-marketplace-buyer-to-a-sellers-home)).
6. **Walk-away.** If the seller's lowest price is above the ceiling after 4 rounds, TireKick drafts a polite walk-away for the buyer to approve.
7. **Opening offer.** Start at the lower of the comps' low end and asking price minus 12%, then add the evidence-based deductions. Never open below 70% of the asking price, so it doesn't read as a lowball. B tunes this.

## 8. The report

There's a **WhatsApp summary** for the buyer, plus a **web page** at `/r/{deal_id}` rendered by A.

- **Header:** the car (decoded VIN, not the listing's claim), asking price, fair price range, overall verdict badge.
- **Evidence cards:** one per evidence item, sorted red, then yellow, then green. Each shows:
  - severity, a short summary, the detail
  - the source (video, VIN decode, recalls, chat, comps)
  - a **frame crop** at the clip timestamp, with a SAM 3.1 highlight where available
  - a "play clip" link (the start and end seconds)
- **Recalls:** a table of campaign number, component and summary, with the honesty note.
- **Negotiation transcript**, once one exists.
- **Questions for the pre-purchase inspection**, generated from the yellows.
- **Footer:** *"TireKick is not a mechanical inspection. Get an independent pre-purchase inspection before you pay."*

## 9. Meta tools and why each is load-bearing

| Tool | Used for | Without it |
|---|---|---|
| **Muse Spark** (Meta Model API) | Reading the proof take: code, VINs, per-light status at fixed moments, odometer, needle, cuts, screen replay. Parsing listing screenshots. Drafting offers. Scam signals. | No verification, no product |
| **SAM 3.1** | Cropping and highlighting each piece of evidence (the VIN plate, the dark check-engine icon) in the report frames | The report shows raw frames with no highlight. That's a nice-to-have, so plan for it to work, but don't block on it. |
| **WhatsApp Cloud API** | Both chats, media download | No product surface |
| *(pitch only)* **Muse Connector** | "TireKick as a tool Meta's Muse agent can call" | Positioning slide only, not built |

## 10. Evaluation (what we show the judges)

C runs all four studies. Details are in [workstream C](workstream-C-eval-demo.md).

| Study | n | Headline we want |
|---|---|---|
| **100-listing study** (hand-collected public listings that show a VIN; no scraping) | ~100 | "X% of listings misstate the year or trim; Y% are a model with recalls the listing never mentions" |
| **Red team**: teammates try to fake the proof take | 10+ attempts across 6 fake types | "TireKick caught N of M fakes" (show the misses too) |
| **Light check**: cold starts with and without a light taped over | 6–12 clips × 3 runs | Hidden-light catch rate and false alarms |
| **Negotiation study**: friends play sellers with a secret lowest price | 10 people | "TireKick got X% off on average vs Y% for students negotiating themselves" |

## 11. Demo (3 minutes, recorded with cached hero clips)

1. **0:00–0:20 Hook.** A real cold-start clip: *"Every warning light should come on at key-on. Watch this one."* The check-engine icon stays dark because it's taped over (labelled "staged"). TireKick flags it in red with the frame.
2. **0:20–1:10 Live chat.** The buyer pastes a listing, and TireKick returns the comps and a seller link. Seller A sends an honest proof take, and the result is GREEN or YELLOW. Seller B sends a different car, with no code and a request for a $500 deposit, and the result is RED with reasons.
3. **1:10–1:50 Negotiation with Seller A.** TireKick cites a recall and the comps. The buyer taps 1 each round. The deal comes in under the ceiling, with the savings on screen.
4. **1:50–2:30 Under the hood.** The challenge design, the VIN checks, the red-team catch rate.
5. **2:30–3:00 The real number** from 100 listings, and "Muse finds and haggles; TireKick makes the car prove itself."

## 12. Out of scope (do not build)

- Repaint, panel-gap, smoke or engine-knock detection. The judge flagged these as unproven and unreliable.
- Marketplace scraping, auto-posting, payments, financing, title transfer.
- A real Muse Connector integration (pitch slide only).
- Multi-language support (stretch goal: Arabic messages for dubizzle, only if everything else is done).
