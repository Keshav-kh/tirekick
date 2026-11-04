# TireKick

**Meta's Muse agent finds a car and haggles. TireKick makes the car prove itself.**

Buying a used car from a stranger on Facebook Marketplace means trusting a few photos and a promise that it
"runs great". Sellers ask for deposits on cars that don't exist, and a strip of tape over the check-engine
light hides a fault. Meta's Muse agent can now find listings and negotiate for you, but nothing checks the
car.

TireKick is a buyer's agent that lives in WhatsApp. Before anyone talks price, the seller has to film one
short video that proves the car is real, is the car in the listing, and has nothing to hide on the
dashboard. TireKick checks that video with Muse Spark, runs the VIN through NHTSA, and only then negotiates
for the buyer, using what it found as leverage. The buyer approves every message before it goes out.

We built it for the Meta Global AI Developer Hackathon (Indie track, "Build for Your World") with first-time
buyers in mind: students and young people buying a cheap first car, often with no one to bring along to
look at it.

**Demo video:** https://youtu.be/oZptKwqpeaw

## How it works

1. **The buyer pastes a listing** (text or a screenshot) and their max price. Muse Spark reads it; code then
   checks that the price it found is really in the text and that the VIN is a valid VIN.
2. **TireKick looks up similar cars** with Muse Spark's web search. Only prices that come with a source link
   count, and the low, median and high are computed in code.
3. **The seller gets a one-time code** and a short checklist: hold the code next to the windshield VIN,
   show the door-jamb VIN, turn the key to ON so every warning light comes on, show the odometer, then start
   the engine. All in one continuous take.
4. **TireKick checks the video.** Muse Spark watches it three times and reports what it sees; the runs are
   merged by majority vote. Code then runs 13 checks:
   - the code is visible and matches, and the take has no cuts and isn't filmed off a screen
   - the windshield VIN passes the check digit and matches the door sticker and the listing
   - the NHTSA decode matches the listed year, make, model, trim and engine
   - NHTSA recalls for that model
   - every must-light comes on at key-on (a dark or unconfirmed check-engine, airbag or ABS light is flagged)
   - no warning light stays on after the start, the odometer matches the listing, the engine starts cold
   - red flags in the seller's messages (deposit before the video, gift cards, shipping, "I'm deployed")
   - a price far below similar cars
5. **The verdict is computed in code, never by the model:** any red flag means "don't buy", any yellow means
   "negotiate with care", otherwise "looks clean". The buyer gets a summary in the chat and a report page with
   a still frame for each finding (with a SAM 3.1 highlight where it can find one), the recall list, and
   questions to ask the mechanic.
6. **TireKick negotiates.** Every price comes from code: the opening offer is based on the comps and the
   findings, each counter moves a third of the way, and nothing ever goes above the buyer's max. Muse Spark
   only writes the words, and every draft is checked before the buyer sees it: it can only cite real
   findings, can't mention prices that aren't in the evidence, and can't ask for deposits, payment details
   or addresses. When the seller agrees, TireKick suggests meeting at a police station's safe exchange zone.

## Results

All numbers are from [eval/RESULTS.md](eval/RESULTS.md), which has the method and the caveats. We had no
real car during the hackathon, so the video tests use AI-generated clips and the negotiation study uses
AI-played sellers.

| Test | Result |
|---|---|
| Red team: 6 attempts to fool it (AI-generated take, old video or wrong code, a different car) | **6 of 6 caught**. The false-alarm rate on real, honest videos is untested. |
| Negotiation: 60 simulated negotiations | TireKick got **84%** of the possible discount, a student on their own got **51%**. Deals reached: **30/30** vs **15/30**. |
| 200 public listings (US Cars dataset) | **96%** are a model with at least one NHTSA recall. |
| Hidden check-engine light | **0 of 3 caught** when we measured: "can't tell" counted as a pass. That's fixed now (an unconfirmed light is flagged and the seller is asked to refilm) but not re-measured yet. |

## Try it yourself

### Re-run our red team on the clips we used (about 7 minutes)

You need Python 3.11+, ffmpeg (`brew install ffmpeg`, `winget install ffmpeg`, or `apt install ffmpeg`)
and a Meta Model API key.

```bash
git clone https://github.com/Keshav-kh/tirekick.git && cd tirekick
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]" imageio-ffmpeg
echo "META_API_KEY=your-meta-model-api-key" > .env
python eval/stitch_clips.py                              # builds the test videos from the clips below
TIREKICK_RUNS=1 python eval/redteam_eval.py eval/data/redteam.csv
```

The last command runs all six spoof attempts through the real pipeline and prints how many were caught.
Per-attempt results go to `eval/out/redteam_scored.csv`. Drop `TIREKICK_RUNS=1` to use three model runs
per video, like the product does (slower, and it catches cuts more reliably).

To check a single video and see every finding:

```bash
python scripts/verify_clip.py --video eval/data/clips/aigen_hidden_01.mp4 --code K7Q2XM --listing eval/data/listings_json/civic_aigen.json --runs 1
```

### The clips we tested on

We generated these with Higgsfield (Seedance 2.5). They're in [eval/data/clips/](eval/data/clips/), and
`eval/stitch_clips.py` joins them into the full "proof videos" the evals use.

| Clip | What it shows |
|---|---|
| `paper.mp4` | The one-time code K7Q2XM on paper, next to the windshield VIN plate |
| `sticker.mp4` | The VIN sticker on the driver's door jamb |
| `odometer.mp4` | The odometer and temperature gauge |
| `dash_honest.mp4` | The dashboard at key-on with every warning light on |
| `dash_hidden.mp4` | The same dashboard with the check-engine light (and a few others) dark |

The stitched videos are `aigen_honest_01` (all four steps, honest dashboard), `aigen_hidden_01` (dark
check-engine light), and `aigen_nocode_01` / `aigen_nocode_02` (no code card, as if the video was filmed
before the challenge). Because they're stitched, every one of them has cuts, and TireKick should reject
all of them.

### Run the chat demo in your browser

Our WhatsApp business number is restricted until Meta business verification, so the demo runs the same bot
in a web page, with the buyer and seller side by side.

```bash
TIREKICK_DEV=1 TIREKICK_DEMO_CODE=K7Q2XM uvicorn webchat_server:app --app-dir demo --port 8000
```

Open http://localhost:8000/demo for the WhatsApp-style chat, or http://localhost:8000/demo/facebook for
a Marketplace and Messenger-style version. Paste a listing with a max price as the buyer, for example:

```
2003 Honda Accord EX, 128k miles, $4,800, runs great, VIN 1HGCM82633A004352. State College, PA. max 5000
```

Then click "Open link" on the seller's side and send one of the stitched clips from the paperclip menu.
Add `TIREKICK_FAKE_AI=1` to try the whole flow without an API key (canned answers).

### Run the tests

```bash
pytest
```

The tests need no network and no keys.

## What's in the repo

| Path | What it is |
|---|---|
| `tirekick/verify/` | Listing parser, proof-video analysis, VIN check and NHTSA decode, recalls, price comps, scam checks, the 13 report rules, SAM 3.1 highlights |
| `tirekick/negotiate/` | Offer amounts and the rules every draft has to pass, and the agent that writes the messages |
| `tirekick/orchestrator.py`, `tirekick/whatsapp/`, `tirekick/report/` | The WhatsApp conversation, webhook, buyer approvals, and the report page |
| `demo/` | The browser demos, the demo script, and `demo/video/`, the animated explainer (made with Remotion) |
| `eval/` | The red team, light check, negotiation study and listing study, with their data and results |
| `scripts/` | `verify_clip.py` (check one video), `day1_test.py` (dashboard light gates), `make_synthetic_clip.py` |
| `docs/` | The product spec, the contracts between the three of us, and each person's workstream notes |

## Built with

- **Muse Spark** (Meta Model API) to read listings, watch the proof video, search for comparable prices,
  scan the chat for scam signals, and write the negotiation messages
- **SAM 3.1** (Meta Model API) to highlight the evidence in the report's still frames
- **WhatsApp Cloud API** for the buyer and seller chats
- NHTSA **vPIC** (VIN decode) and **Recalls** APIs
- Python, FastAPI, Pydantic, pytest

## Limits

- TireKick is not a mechanical inspection. It always tells the buyer to get one before paying.
- Recalls are listed per model (year, make and model), not per VIN. The report says so and links to
  nhtsa.gov/recalls to check the specific car.
- Everything video-related was tested on AI-generated clips and AI-played sellers, not real cars or real
  people. Measuring false alarms on real, honest sellers is the first thing we'd do next.
- It never moves money and never shares an address.
