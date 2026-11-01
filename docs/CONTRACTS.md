# Contracts between workstreams

This is what lets three people build in parallel and merge cleanly. **If you need to change anything in this file or in `tirekick/models.py`, open a small PR to `main` that touches only those two files and post it in the group chat before you merge.** Adding an optional field with a default is safe. Renaming or removing something breaks the other two branches.

---

## 1. Folder ownership (who may edit what)

| Path | Owner | Others may… |
|---|---|---|
| `tirekick/models.py`, `docs/CONTRACTS.md` | Shared (contract PRs only) | read |
| `tirekick/app.py`, `tirekick/orchestrator.py`, `tirekick/store.py`, `tirekick/whatsapp/**`, `tirekick/report/**` | **A** | read, and file issues |
| `tirekick/verify/**`, `tirekick/negotiate/**`, `scripts/**` | **B** | read, and call the public functions |
| `eval/**`, `demo/**` | **C** | read |
| `tirekick/verify/fake.py` | **B** writes it, **A** may add fixtures | add fixtures |
| `README.md`, `docs/SPEC.md`, `docs/WORKFLOW.md`, `samples/`, `tests/_fixtures.py`, `tests/conftest.py` | Shared | small edits are fine; say so in the PR |
| `tests/test_<area>.py` | The area's owner | add tests for your own area |

If you have to touch someone else's file, ask them first or open an issue. That rule is what keeps merges conflict-free.

## 2. Data models

These all live in `tirekick/models.py`; read the code for the exact fields. They're summarized here:

| Model | Produced by | Consumed by | Purpose |
|---|---|---|---|
| `Listing` | B `parse_listing` | A, B, C | The car as the seller advertises it |
| `ProofChallenge` | B `issue_challenge` | A sends `message_text` | The one-time code and filming instructions |
| `ProofTakeAnalysis` | B `analyze_proof_take` | B `build_report`, C eval | **Facts only** from the video, no verdicts |
| `VinDecode` | B `decode_vin` | B, C | NHTSA vPIC decode, plus the check-digit result |
| `Recall` | B `lookup_recalls` | B, A report page | Recalls for the year, make and model |
| `PriceComps` | B `price_comps` | B, A | Comparable prices, with source URLs |
| `Evidence` | B `build_report`, `scan_chat` | A report page, B negotiation, C eval | One finding with severity, a clip timestamp, an optional frame, and a price impact |
| `VerificationReport` | B `build_report` | A (WhatsApp summary, web page), B negotiation, C eval | Everything plus the **verdict, computed in code** |
| `ChatMessage` | A | B `scan_chat` | Normalized WhatsApp message |
| `Offer` | B `draft_offer` | A (shows it to the buyer for approval, then sends) | A draft message to the seller |
| `NegotiationState` | B `start_negotiation`, `apply_seller_reply` | A stores it, B updates it | Ceiling, rounds, turns |
| `Deal` | A | A, B `run_verification` | The whole conversation state, persisted by A |

**Evidence ID format:** `EV-01`, `EV-02`… numbered in the order `build_report` creates them. IDs only need to be unique within one report.

**Money:** whole units (`int`) in `Listing.currency`. There are no floats for money anywhere.

**Timestamps in video:** seconds from the start of the clip (`float`).

## 3. Public functions (the API between branches)

### 3.1 B → everyone: `tirekick.verify`

```python
from tirekick.verify import (
    parse_listing, issue_challenge, analyze_proof_take, validate_vin, decode_vin,
    lookup_recalls, price_comps, scan_chat, build_report, run_verification,
)

def parse_listing(text: str | None = None, image_paths: list[str] | None = None,
                  url: str | None = None, listing_id: str | None = None) -> Listing
    # Muse Spark reads pasted text and/or screenshots. Must not scrape the URL.
    # Raises ValueError if no asking price can be found.

def issue_challenge(listing: Listing, deal_id: str, ttl_hours: int = 24) -> ProofChallenge
    # 6-char code from an unambiguous alphabet (no 0/O/1/I). message_text is SPEC §6.1, filled in.

def analyze_proof_take(video_path: str, challenge: ProofChallenge, listing: Listing,
                       runs: int = 3) -> ProofTakeAnalysis
    # Muse Spark, structured output, `runs` samples merged by majority vote.
    # Never raises on a bad video; returns fields as None / False instead.

def validate_vin(vin: str) -> tuple[bool, str]
    # (check_digit_valid, normalized_vin). Pure function, no network.

def decode_vin(vin: str) -> VinDecode
    # NHTSA vPIC. Cache responses on disk (data/cache/vpic/). Timeout 10 s.

def lookup_recalls(make: str, model: str, year: int) -> list[Recall]
    # NHTSA Recalls API, model-level (NOT VIN-level). Cache on disk. Timeout 10 s.

def price_comps(listing: Listing) -> PriceComps
    # Muse Spark web search with citations. Cache by (year, make, model, trim, location).

def scan_chat(messages: list[ChatMessage], listing: Listing,
              comps: PriceComps | None) -> list[Evidence]
    # Rules first (deposit, gift card, shipping, refuses video), Muse Spark second.

def build_report(deal_id: str, listing: Listing, challenge: ProofChallenge,
                 analysis: ProofTakeAnalysis | None, vin_decode: VinDecode | None,
                 recalls: list[Recall], comps: PriceComps | None,
                 chat_evidence: list[Evidence]) -> VerificationReport
    # Applies SPEC §6.3 rules C1–C13 IN CODE. Assigns EV ids, price_impact, verdict,
    # fair price range, inspection questions. Extracts frame stills (ffmpeg) for evidence.

def run_verification(deal: Deal, video_path: str) -> VerificationReport
    # Convenience wrapper A calls: VIN from the video (fallback listing.vin) → decode →
    # recalls → comps → scan_chat(deal.chat) → build_report. Target: < 90 s total.
```

### 3.2 B → A: `tirekick.negotiate`

```python
from tirekick.negotiate import (
    start_negotiation, draft_offer, apply_seller_reply, record_sent_offer, final_offer,
    walk_away_offer, check_offer, next_offer_amount, PolicyViolation,
)

def start_negotiation(deal_id: str, report: VerificationReport, buyer_ceiling: int) -> NegotiationState

def draft_offer(state: NegotiationState, report: VerificationReport,
                seller_message: str | None = None, buyer_instruction: str | None = None) -> Offer
    # The amount comes from next_offer_amount (code); Muse Spark writes the words.
    # Then check_offer() runs. If the policy fails, it retries once with the violation in
    # the prompt; after that it returns a safe templated offer.
    # The returned Offer ALWAYS passes check_offer.

def apply_seller_reply(state: NegotiationState, text: str) -> NegotiationState
    # Extracts the seller's counter price (if any), appends a turn, bumps rounds,
    # and sets status AGREED or WALKED_AWAY when appropriate.

def record_sent_offer(state: NegotiationState, offer: Offer) -> NegotiationState
    # A calls this AFTER the buyer approves and the message is sent; updates last_offer and turns.

def final_offer(state: NegotiationState) -> Offer       # "deal at $X, meet at a safe exchange zone"
def walk_away_offer(state: NegotiationState) -> Offer   # polite pass

def check_offer(offer: Offer, state: NegotiationState, report: VerificationReport) -> None
    # Raises PolicyViolation. Rules (SPEC §7): amount <= ceiling; every cited id exists and
    # is verified; any offer below asking cites >= 1 id OR relies on comps with n >= 3;
    # the only $ figures in the text are the offer, the asking price, the comps, or figures in
    # the cited evidence; no payment / deposit / address words.
```

### 3.3 A → everyone: HTTP endpoints

| Method and path | Purpose | Notes |
|---|---|---|
| `GET /health` | Liveness | Returns `{"ok": true}` |
| `GET /webhook` | WhatsApp verification handshake | Echoes `hub.challenge` if `hub.verify_token` matches |
| `POST /webhook` | Incoming WhatsApp messages | Checks the `X-Hub-Signature-256` HMAC, then hands off to the orchestrator. Returns 200 fast and does the work in the background. |
| `GET /r/{deal_id}` | The HTML report page | Public link in the demo; unguessable IDs in production |
| `GET /r/{deal_id}/frames/{name}` | Evidence frame images | Served from `data/frames/{deal_id}/` |
| `POST /dev/simulate` | **Dev only** (`TIREKICK_DEV=1`): fake an incoming message | Body `{"from": "15551230001", "text": "...", "media_path": "samples/x.mp4"}`. Lets B and C test the full flow without phones. |

### 3.4 Fake mode (so A isn't blocked on B)

With `TIREKICK_FAKE_AI=1`, every `tirekick.verify` and `tirekick.negotiate` function returns fixture data from `tirekick/verify/fake.py`:
- a video path containing `shady` gives a **RED** report (code missing, VIN mismatch, deposit request)
- any other path gives a **YELLOW** report (one recall, odometer fine, all lights swept on)

A develops and demos the whole chat flow with fakes. B replaces them with the real functions; **the signatures must not change.**

## 4. Files on disk (all under `data/`, which is gitignored)

```
data/
  deals/{deal_id}.json          A: Deal.model_dump_json()
  media/{wa_media_id}.{ext}     A: downloaded WhatsApp media
  frames/{deal_id}/{EV-xx}.jpg  B: evidence stills (and *_hl.jpg SAM highlights)
  cache/vpic/{vin}.json         B
  cache/recalls/{make}_{model}_{year}.json   B
  cache/comps/{hash}.json       B
  runs/{timestamp}_{clip}.json  B/C: raw Muse Spark outputs for eval and debugging
```

## 5. Environment variables (`.env`, never committed)

| Var | Used by | Meaning |
|---|---|---|
| `META_API_KEY` | B | Meta Model API key |
| `META_API_BASE` | B | Default `https://api.meta.ai/v1` (OpenAI-compatible) |
| `MUSE_MODEL` | B | Muse Spark model ID. **Check the exact ID on dev.meta.ai** (Meta's blog example uses `muse-spark-1.1`; Connect announced 1.3). |
| `SAM_MODEL` | B | SAM 3.1 model or endpoint ID; check the dev.meta.ai docs |
| `WHATSAPP_TOKEN` | A | Cloud API access token |
| `WHATSAPP_PHONE_NUMBER_ID` | A | The bot's phone number ID |
| `WHATSAPP_BOT_NUMBER` | A | The bot's number, digits only, for `wa.me` links |
| `WHATSAPP_VERIFY_TOKEN` | A | Any string; must match the one set in the Meta app dashboard |
| `WHATSAPP_APP_SECRET` | A | For the webhook signature check |
| `GRAPH_API_VERSION` | A | Default `v21.0`; use the latest one your Meta app dashboard shows |
| `PUBLIC_BASE_URL` | A | For report links, e.g. `https://tirekick.example.com` |
| `TIREKICK_FAKE_AI` | all | `1` = use the fixtures |
| `TIREKICK_DEV` | A | `1` = enable `/dev/simulate` |
