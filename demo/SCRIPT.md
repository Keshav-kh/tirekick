# Demo script (3:00 max): owner C

Recorded, not live. Captions on every line (judges often watch muted). Anything staged or simulated is
labelled on screen. Runs in the web chat (`demo/webchat_server.py`), because our WhatsApp business account is
restricted until Meta business verification; it is the same bot code as the WhatsApp version.

**Two recordings to make (screen recording, 1080p):**
- **Rec A, real mode** (Muse Spark live): `TIREKICK_DEV=1 TIREKICK_DEMO_CODE=K7Q2XM uvicorn webchat_server:app --app-dir demo --port 8000`
  Buyer: "hi" → paste the Honda Element listing → "max 2500" → seller joins → seller sends `aigen_honest_01.mp4` → 🔴 verdict → open the report link.
- **Rec B, sample-data mode** (fixture verification, real flow): add `TIREKICK_FAKE_AI=1`, then:
  Buyer: "hi" → paste the 2003 Honda Accord sample listing → "max 5000" → seller joins → seller sends any clip
  with "honest" in the name → 🟡 verdict → tap Send → seller types "lowest i can do is 4600" → tap Send on the counter → seller types "ok deal".

| Time | On screen | Caption / voiceover |
|---|---|---|
| 0:00–0:12 | The real Craigslist listing: 2004 Honda Element, "Runs and drives excellent, clean title", $2,700 | "Private used-car listings all say the same thing. 'Runs great. Clean title.'" |
| 0:12–0:22 | The same listing, then a card: "NHTSA: 11 recalls for this model, including both front airbag inflators. The listing never mentions them." | "This one's model has 11 federal recalls, including the airbags. The listing never says so." |
| 0:22–0:35 | Title card: "Meta's Muse agent can find a car and haggle. Nothing checks the car." Then: "TireKick: the car proves itself before anyone haggles." | "Meta's Muse agent can find and haggle. TireKick makes the car prove itself first." |
| 0:35–0:55 | Rec A: buyer pastes the Element listing and "max 2500"; TireKick replies with comps, VIN check and the seller link | "The buyer pastes a listing and a max price. TireKick checks the VIN and finds comparable prices." |
| 0:55–1:10 | Rec A: seller joins; the challenge with code K7Q2XM | "The seller gets a one-time code and films one continuous take: the code next to the VIN, the door sticker, every warning light, the odometer, a cold start." |
| 1:10–1:40 | Rec A: seller sends the AI-generated video (sped up while it verifies); 🔴 lamp lights; the five reasons. Label: "AI-generated proof video (Higgsfield) · live Muse Spark analysis · sped up" | "Here a scammer sends an AI-generated video. Muse Spark watches it three times and reports facts; code decides. Five red flags: cuts, an invalid VIN, VINs that don't match each other or the listing, and the wrong mileage." |
| 1:40–1:48 | Rec A: the drafted walk-away, buyer taps Send | "TireKick drafts a polite pass. Nothing is sent without the buyer's tap." |
| 1:48–2:20 | Rec B: honest car → 🟡 (open recall); the offer cites the recall and comps; buyer taps Send; seller counters; TireKick counters; deal. Label: "Sample verification data" | "When the car checks out, TireKick negotiates, but it may only cite verified evidence, like an open recall, and it can never go over the buyer's max." |
| 2:20–2:45 | Results cards (from eval/RESULTS.md): "6/6 spoof attempts caught" · "84% vs 51% of the possible discount, 30/30 vs 15/30 deals (60 simulated negotiations)" · "96% of 200 listings are a model with a recall" · "Our miss: 0/3 hidden check-engine lights caught. Why, and the fix, are in our repo." | "We tried to break it. It caught every spoof we threw at it, it negotiates better than a student alone, and we publish our misses too." |
| 2:45–3:00 | End card: "TireKick: make the car prove itself." Repo link. "Built with Muse Spark, SAM 3.1 and the WhatsApp Cloud API." | "TireKick. Make the car prove itself." |

**Rules:** blur nothing personal in the Craigslist screenshot except the seller's contact (it's hidden
behind "show contact info" already). Keep the "AI-generated" and "sample data" labels on screen for the
whole segment they apply to. Don't claim the light check works; the results card states the miss.
