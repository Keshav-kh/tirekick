# Workstream B: Verification and negotiation (branch `verification-negotiation`)

**You own:** `tirekick/verify/**`, `tirekick/negotiate/**`, `scripts/**`.
**Your public API** is fixed in [CONTRACTS.md §3.1–3.2](CONTRACTS.md#31-b--everyone-tirekickverify). A and C code against those signatures. Change the internals as much as you like, but **never the signatures** without a contract PR.

Your code decides whether a car passes. One principle governs everything: **the model reports facts, and code makes the decisions.** Muse Spark says what it saw; code applies the rules, computes prices and enforces the ceiling.

---

## 0. Day-1 test (do this first)

The one unproven assumption is whether Muse Spark reliably reads a dashboard at key-on. Test it before writing anything else.

1. Get clips from C, or film your own: **5 cold-start takes** (key ON, hold 5 s, start, hold 5 s). On **2 of them**, put a small piece of opaque tape over the check-engine icon on the **outside** of the dashboard glass. Film **1 take** with a code card next to the windshield VIN. Label every clip in `eval/data/light_check.csv`.
2. Find out how the Meta Model API accepts video. Check dev.meta.ai: the docs for the chat or Responses API and its multimodal input. Write down the answer in this doc, under the "API notes" heading in §2.
3. Run `python scripts/day1_test.py --clips eval/data/light_check.csv --runs 3`.
4. Gates:

| Gate | GO | If not |
|---|---|---|
| Lights | Both taped lights caught in **3/3** runs; **no** healthy light flagged | Switch to `MUSE_VIDEO_MODE=frames` (§2.2) and re-run. If it's still bad, the light check becomes yellow-only and the pitch leads with VIN and recalls. |
| VIN and code | The VIN read passes the check digit; the code is read exactly | Ask the seller for an extra close-up still of the VIN plate |
| Speed and cost | ≤ 60 s per run, and credits last | Downscale to 720p and cap clips at 60 s |

Post the table of results in the group chat by **9 PM ET Sun Nov 1**.

## 1. Deliverables, in priority order

| # | Function | File | Done when |
|---|---|---|---|
| B1 | `validate_vin`, `decode_vin` | `verify/vin.py` | ✅ The check digit is implemented and tested in the repo. Add a disk cache and the vPIC decode mapping. |
| B2 | `lookup_recalls` | `verify/recalls.py` | ✅ The API call is implemented. Add the cache and empty or error handling. |
| B3 | `analyze_proof_take` | `verify/proof_take.py` | It passes the day-1 gates on C's clips, with a 3-run vote |
| B4 | `issue_challenge` | `verify/challenge.py` | ✅ Implemented. Review the copy with A. |
| B5 | `build_report` + frame extraction | `verify/report_builder.py` | All of C1–C13 implemented; evidence frames written to `data/frames/` |
| B6 | `parse_listing` | `verify/listing.py` | Correct on 10 of C's listing screenshots |
| B7 | `run_verification` | `verify/__init__.py` | End to end in under 90 s on a real clip |
| B8 | `negotiate.*` | `negotiate/` | The policy tests pass; it never exceeds the ceiling or invents evidence |
| B9 | `price_comps` | `verify/comps.py` | Returns ≥ 3 cited prices for common cars; cached |
| B10 | `scan_chat` | `verify/scam.py` | Catches all 20 of C's scripted scam chats with < 10% false alarms on the legit set |
| B11 | SAM 3.1 highlights (stretch) | `verify/highlight.py` | VIN plate and dark icon highlighted in the report frames |

## 2. Muse Spark client (`verify/muse.py`)

The Meta Model API is **OpenAI-compatible**: base URL `https://api.meta.ai/v1`, using the `openai` Python SDK. Meta's blog example uses model `muse-spark-1.1`; **confirm the latest ID on dev.meta.ai** and put it in `MUSE_MODEL`.

```python
client = OpenAI(api_key=os.environ["META_API_KEY"], base_url=os.environ["META_API_BASE"])
```

Write one helper, `muse_json(messages, schema: type[BaseModel], temperature=0.2) -> BaseModel`:
- If the API supports `response_format={"type": "json_schema", ...}`, use it.
- Otherwise ask for "JSON only", parse it, validate it with the Pydantic schema, and **retry once** with the validation error appended.
- Save every raw response to `data/runs/` (C needs these for the eval, and you need them for debugging).
- Retry on 429/5xx with backoff (1 s, 2 s, 4 s), with a timeout of 120 s.

### 2.1 Video mode `native` (preferred)
Send the video as a multimodal content part, in whatever form Meta's docs specify: a file upload, a URL, or base64. The blog says Muse Spark understands "image, audio, video and document" input "in a single call."

### 2.2 Video mode `frames` (fallback; always works)
1. Get the duration with `ffprobe`.
2. Run `ffmpeg -i in.mp4 -vf fps=2,scale=960:-2 data/runs/<id>/f_%04d.jpg` to get 2 frames per second.
3. Send the frames as images. Before each one, put a text part `"t=3.5s"` so the model can cite timestamps.
4. Optional: `ffmpeg -i in.mp4 -ac 1 -ar 16000 out.wav`, then Muse Voice Transcribe, then add the transcript (useful for engine start sounds and the seller's narration).
5. Cap it at about 120 frames. For 60 s at 2 fps that's exactly 120.

Set the mode with `MUSE_VIDEO_MODE=native|frames`.

**API notes (filled in Sun Nov 1, by B's agent; "verified" = read in Meta's own published code/docs, not a live call):**

*Sources.* dev.meta.ai itself was not reachable from the cloud session (network policy), so these come from Meta's first-party GitHub repos [`meta-models/meta-model-cookbook`](https://github.com/meta-models/meta-model-cookbook) (`01_api_fundamentals` recipes 04, 07, 09, 10 and `07_sam`), [`meta-models/meta-sam`](https://github.com/meta-models/meta-sam) (`protocol/sam3.md`) and the Meta-published PyPI package `meta-sam-parser` 0.1.0. Items marked *(snippet)* come only from search-engine extracts of dev.meta.ai pages. **No live call has been made yet** (no `META_API_KEY` in the session): everything below still needs one smoke test with the real key.

- **Model ID used:** `muse-spark-1.3` (verified: the cookbook's canonical config). `muse-spark-1.3-contributor` is the discounted tier where prompts and completions may be used to train Meta models, so **don't use it for sellers' videos**. Base URL `https://api.meta.ai/v1`, OpenAI Python SDK; Meta's docs name the key `MODEL_API_KEY` (format `LLM|<id>|<secret>`), and our code accepts `META_API_KEY` or `MODEL_API_KEY`.
- **Structured output supported?** **Yes** (verified). Chat Completions: `response_format={"type": "json_schema", "json_schema": {"name", "schema"}}`, plus `additionalProperties: false` and `required`; `client.beta.chat.completions.parse(response_format=PydanticModel)` also works. Responses API: the parameter is `text.format`; sending `response_format` there returns 400. Recursive `$ref` schemas return 400 (our `strict_schema` inlines every `$ref`). `muse_json` still falls back to JSON-only plus Pydantic validation and one repair retry if the schema is rejected.
- **Image input format:** (verified) a `{"type": "image_url", "image_url": {"url": ...}}` part with a public URL or a base64 data URL, in **user messages only** (system or developer messages with images return 400). Formats: jpeg, jpg, png, gif, webp, x-icon. About **50 images per request**, 50 MB per inline image, and 1 GiB via the Files API. Responses-API shape: `{"type": "input_image", "image_url": "<url or data URL>"}`. Frames mode therefore caps at **48 frames** (2 fps up to 24 s, lower fps for longer clips).
- **Video input format:** **NOT verified for Muse Spark.**
  - *(snippet)* dev.meta.ai/docs/video-understanding: the Responses API takes an `input_video` block with `video_url` (public URL or base64 data URL) or `file_id` (Files API).
  - The `input_video` + `file_id` shape (upload with `purpose="user_data"`, MP4) **is** verified, but only for `sam-3.1` in the cookbook.
  - Chat Completions `video_url` part: Meta's pages disagree *(snippet)*. video-understanding says it's supported; coding-agents says video is Responses-only. The chat schema lists an optional `video_url.fps`.
  - Our `native` mode tries Responses `input_video` (data URL; Files API above ~35 MB), then Chat `video_url`, then falls back to frames automatically. A route that fails is skipped for the rest of the process.
- **Max video size and length:** unknown for Muse Spark. *(snippet)* There's a 50 MB inline limit (file-handling page). The 15,000-frame (about 10 min) cap is SAM 3.1's, not Muse's. We downscale to 720p and cap at 60 s before a native upload when a clip is over 20 MB or 60 s.
- **Web search:** (verified) **Responses API only**: `client.responses.create(model, input, tools=[{"type": "web_search", "search_context_size": "low|medium|high"}])`.
  - `output` is a list of `reasoning`, `web_search_call` and `message` items.
  - Citations come as `url_citation` annotations (`url`, `title`, `start_index`, `end_index`) on each `output_text` block.
  - The model may choose not to search, so check for a `web_search_call` item (comps does, and returns n=0 if no search ran).
  - Unknown: whether `text.format` can be combined with `web_search`. Comps asks for JSON in the prompt instead.
- **SAM 3.1:** (verified) model `sam-3.1`, Responses API with `stream=True`.
  - Input is a user message with `{"type": "input_text", "text": "<one noun phrase>"}` plus `{"type": "input_image", "image_url": "<data URL>"}`, or `{"type": "input_video", "file_id": ...}` for video.
  - Output is one `output_text` lane, one line per frame: `<Nf>id<|box;x1=;y1=;x2=;y2=;w=;h=[;c=]|><|mask;x=0;y=0;data=H,W,<base85>|>,...`. `x2` and `y2` are inclusive; masks are base85, not base64.
  - Pass `metadata={"include_confidence": "true"}` to get `c`.
  - The live API finalizes the lane with `response.content_part.done` (not `response.output_text.done`). `highlight.py` reads both, plus the deltas.
- **Errors, retries and limits:** (verified) errors use the OpenAI envelope. Retry 429, 5xx, timeouts and connection errors with backoff; never retry 400, 401 or 404. Rate-limit headers are `x-ratelimit-remaining-requests/-tokens`. Free tier: 2,400 requests/min and 800,000 tokens/min per team.
- **`temperature`:** not shown anywhere in Meta's examples (unknown). Our client drops it automatically if a 400 mentions it.
- **Latency per 60 s clip:** **pending** the first live run. `run_verification` logs per-step timings to `data/runs/*_pipeline.json`. A third party reports web search takes about 20–30 s and 15–35k input tokens per call (unverified); comps run in parallel with the video analysis.

## 3. `analyze_proof_take`: the prompt

System prompt (keep it in `verify/prompts.py`):

```
You are a meticulous vehicle-inspection video analyst. You report ONLY what is visible
or audible in the video, with timestamps in seconds. You never guess; if you cannot tell,
use null. You do not judge whether the car is good; you only report observations.
```

User prompt (fill in the template):

```
This is a seller's proof video for a used {year} {make} {model}. The seller was asked to,
in ONE continuous take: (1) hold a paper with code "{code}" next to the windshield VIN plate,
(2) show the driver door-jamb VIN sticker, (3) turn the key to ON without starting and hold on
the dashboard 5 s, (4) show odometer and temperature gauge, (5) start the engine and hold 5 s.

Report, as JSON matching the schema:
- code_read: the exact characters on the paper, or null. code_timestamp_s.
- continuous_take: true if there are no cuts/jumps; cut_timestamps_s for any discontinuity
  (sudden scene change, lighting jump, frame skip).
- screen_replay_suspected: true if this looks like a video of a screen (bezels, moiré, glare).
- windshield_vin_read / door_vin_read: 17 characters each, or null. Use only A-Z (no I, O, Q) and 0-9.
- key_on_timestamp_s: when the dashboard lights first come on; engine_start_timestamp_s.
- lights: for EACH of check_engine, airbag, abs, battery, oil_pressure, brake, tpms:
  lit_at_key_on (true/false/null), on_after_start (true/false/null), timestamps, confidence 0-1.
  A light whose icon area stays dark at key-on while other lights are lit -> lit_at_key_on=false.
  Note any tape, sticker, or obstruction over an icon in model_notes.
- odometer_read (integer), odometer_unit ("mi"/"km"), odometer_timestamp_s.
- engine_cold: true if the temperature needle is at/near C before start, false if mid/high, null
  if no needle visible. temp_gauge_timestamp_s.
- model_notes: anything else relevant (one or two sentences).
```

**3-run merge** (`runs=3`, temperature 0.3):
- Per light, take the majority of `lit_at_key_on` and `on_after_start`, ignoring nulls. A tie gives `None`.
- `agreement` = fraction of (light × field) pairs where all 3 runs agreed.
- For VINs and the code, prefer the reading that **passes the check digit** (for the code: matches exactly). Otherwise take the most common string.
- `continuous_take` = **all** runs say true (being conservative here is good).
- Keep all raw outputs in `raw_outputs`.

## 4. `build_report`: rules C1–C13 in code

Implement exactly the table in [SPEC §6.3](SPEC.md#63-checks-performed). Starting values for `price_impact` (tune them, and document what you settle on):

| Evidence | Severity | price_impact | Summary template (quoted to the seller, so keep it factual and polite) |
|---|---|---|---|
| `code_missing` | red | 0 | "The video doesn't show the requested code next to the VIN." |
| `code_missing` (analysis failed: every model run errored) | red | 0 | "The proof video couldn't be analyzed; please send a new one." (the only video item in that case) |
| `take_has_cuts` | red | 0 | "The video has cuts at {t}s; we need one continuous take." |
| `screen_replay` | red | 0 | "The video appears to be filmed from a screen." |
| `vin_unreadable` (nothing read, or not 17 valid VIN characters) | yellow | 0 | "The windshield VIN wasn't readable." |
| `vin_invalid` (NA VIN) | red | 0 | "The VIN read from the windshield fails the standard check digit." |
| `vin_invalid` (non-NA) | yellow | 0 | "VIN check digit not applicable or failed (non-North-American VIN)." |
| `vin_mismatch_doors` | red | 0 | "The windshield VIN and the door-jamb VIN don't match." |
| `vin_listing_mismatch` (video VIN differs from the listing's VIN) | red | 0 | "The VIN in the video doesn't match the VIN in the listing." |
| `vin_listing_mismatch` (year/make/model) | red | 0 | "The VIN decodes to a {decoded}, not the {listed} in the listing." |
| `vin_listing_mismatch` (trim) | yellow | 500 (`TRIM_MISMATCH_IMPACT`) | "The VIN decodes to the {trim} trim, not the {listed_trim} listed." |
| `vin_listing_mismatch` (engine: displacement differs by more than 0.15 L, or cylinder count differs) | yellow | 500 (`ENGINE_MISMATCH_IMPACT`) | "The VIN decodes to a {engine} engine, not the {listed_engine} listed." |
| `recall_found` | yellow | 100 each (`RECALL_IMPACT`), one item per top-level system, at most 3 items and 300 in total | "There's an NHTSA recall for this model: {component}." |
| `warning_light_hidden` (check-engine, airbag, ABS; car 1996 or newer) | red | 0 | "The {light} light didn't come on at key-on (bulb check)." |
| `warning_light_hidden` (other lights, or a pre-1996 car) | yellow | 0 | same |
| `warning_light_hidden` (no light seen on at key-on at all) | yellow | 0 | "The key-on bulb check (all warning lights on) wasn't clearly shown." |
| `warning_light_on` (critical: check-engine, airbag, oil, brake) | red | 0 | "The {light} light stays on after the engine starts." |
| `warning_light_on` (other) | yellow | 150 (`LIGHT_ON_IMPACT`) | "The {light} light stays on after the engine starts." |
| `odometer_mismatch` (lower than listed by more than 5%) | red | 0 | "The odometer reads {read}, the listing says {listed}." |
| `odometer_mismatch` (higher than listed by more than 5%) | yellow | 0.10 × extra miles, capped at 1500 (`EXTRA_MILES_RATE`, `EXTRA_MILES_CAP`) | "The odometer reads {read}, higher than the {listed} listed." |
| `engine_warm` | yellow | 0 | "The engine looked warm at start; a cold start wasn't shown." |
| `scam_signal` (rules; model findings in a "hard" category) | red | 0 | from `scan_chat` |
| `scam_signal` (model findings: pressure, off-platform, inconsistent story, other) | yellow | 0 | from `scan_chat` (quote checked verbatim in code) |
| `price_below_market` (asking < 70% of the comps median) | yellow; **red** if the chat also has a red `scam_signal` | 0 | "The price is well below similar cars ({median} median)." |
| `positive` | green | 0 | "All {n} warning lights came on at key-on and went off after the start." / "The windshield VIN matches the door-jamb sticker and the listing." / "Odometer {read} matches the listing." / "VIN decodes to a {car}, matching the listing." |

The constants live at the top of `tirekick/verify/report_builder.py`; keep this table in sync with them.

- **Evidence frames:** for each item with `clip_start_s`, run `ffmpeg -ss {t} -i video -frames:v 1 data/frames/{deal}/{EV-xx}.jpg`.
- **Fair price range:** comps low–median, minus the sum of `price_impact`, clamped to ≥ 50% of asking.
- **Inspection questions:** one per yellow ("Ask the mechanic to confirm the airbag recall was completed").
- **Verdict:** `VerificationReport.compute_verdict(evidence)`. It's already implemented; **don't let the model decide.**

## 5. VIN and recalls (B1 and B2 already work; harden them)

- `validate_vin` implements the ISO 3779 / 49 CFR 565 check digit (position 9; weights 8,7,6,5,4,3,2,10,0,9,8,7,6,5,4,3,2; a remainder of 10 gives `X`). The tests are in `tests/test_vin.py`.
- **North American** = first character 1–5. Only then is a bad check digit red.
- `decode_vin` calls `https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/{vin}?format=json` and maps `ModelYear`, `Make`, `Model`, `Trim`, `DisplacementL` plus `EngineCylinders`, `BodyClass` and `ErrorText`. TODO: the disk cache.
- `lookup_recalls` calls `https://api.nhtsa.gov/recalls/recallsByVehicle?make=..&model=..&modelYear=..`. This is **model-level**, so state that in the report (SPEC honesty note). TODO: the disk cache.
- **Comparing the listing with the decode:** case-insensitive. Normalize make aliases ("Chevy" → "Chevrolet"). For trims, do a fuzzy contains match ("LX" vs "LX Sedan"). An unknown decoded trim means no trim mismatch.

## 6. `scan_chat` (scam signals)

Rules first (regex, case-insensitive). Each match becomes one red `scam_signal` that quotes the message:
- `deposit|hold it for you|holding fee`, when it comes **before** the seller has sent a proof video
- `gift ?card|apple card|steam card|crypto|bitcoin|usdt|western union|moneygram`
- `zelle|cash ?app|venmo|wire`, when it comes together with deposit, shipping or unseen language
- `shipping|shipped|transport company|ebay motors protection|escrow`
- `deployed|military|out of (the )?(state|country)|can'?t meet`
- refusing video or inspection: `no video|can'?t (send|do) (a )?video|no inspection`

Then **one** Muse Spark pass over the whole seller chat: "List any additional scam indicators, quoting the exact message". Only add items it quotes **verbatim**; check this in code.

## 7. Negotiation (`negotiate/`): prices in code, words by the model

- **`policy.py`** (✅ the core is implemented and tested):
  - `next_offer_amount(state, report)`, a deterministic concession schedule:
    - Round 0: `open = max(0.70 × ask, min(comps.low or ask, ask × 0.88) − Σ price_impact)`, rounded down to $50.
    - Each later round: `prev + (seller_ask − prev) / 3`, rounded to $50, **never above `buyer_ceiling`**.
    - If `seller_ask ≤ prev_offer`, accept at `seller_ask`.
  - `check_offer(offer, state, report)` raises `PolicyViolation` when:
    - the amount is over the ceiling,
    - a cited ID is unknown or unverified,
    - a reduction cites no evidence,
    - the text contains a money figure that isn't the offer, asking, or comps,
    - or the text contains payment or address words.
- **`agent.py`:** `draft_offer` gets the amount from `next_offer_amount`, picks the 1–2 strongest cited evidence items (highest `price_impact`, then recalls), and asks Muse Spark for **one short, friendly WhatsApp message** that:
  - uses only the given facts and the given amount,
  - mentions evidence by its plain summary (you can keep `EV-03` in the buyer's preview but strip the IDs before sending to the seller; that's A's job, with the format agreed with A),
  - stays under 320 characters.

  Run `check_offer`. On a violation, retry once with the violation text added. On a second failure, use the template: *"Thanks! Based on {summary}, would you take {amount}?"*
- **`apply_seller_reply`:** extract the seller's number (the plausible price range is 0.5–1.3 × asking). Acceptance words (`deal|ok|okay|yes|sure|works|accept`) with no new number mean acceptance at `last_offer`. Increment `rounds`. After `max_rounds`, if the ask is still above the ceiling, set `WALKED_AWAY` (and draft a walk-away offer).

## 8. Scripts you own

- `scripts/verify_clip.py`: run the whole verification on a local video and print the report as JSON plus a summary table. C uses it for the eval.
- `scripts/day1_test.py`: the gates table from §0.

## 9. Tests you own

`tests/test_vin.py` (✅), `tests/test_policy.py` (✅). Add:
- `build_report` rules: one test per evidence type using a hand-built `ProofTakeAnalysis` (no API calls).
- The 3-run merge logic.
- `scan_chat` rules on C's scripted chats once they exist.
- Mock the network in tests. CI has no API keys.

## 10. Your timeline

| When (ET) | Target |
|---|---|
| Sun Nov 1, by 9 PM | Day-1 test result posted; `muse.py` working |
| Mon Nov 2, by 6 PM | B3, B5, B7 real; B1/B2 caches. **Integration 1 at 9 PM** |
| Tue Nov 3, by 6 PM | B8, B9, B10 (and B11 if there's time). **Freeze at 9 PM** |
| Wed Nov 4, morning | Cache the hero-clip results and freeze the prompts; on call |
