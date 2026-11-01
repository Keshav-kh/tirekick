# Workstream A: Platform (branch `platform-whatsapp`)

**You own:** `tirekick/app.py`, `tirekick/orchestrator.py`, `tirekick/store.py`, `tirekick/whatsapp/**`, `tirekick/report/**`, plus deployment.
**You call (never edit):** `tirekick.verify.*` and `tirekick.negotiate.*` (B). Signatures are in [CONTRACTS.md §3](CONTRACTS.md#3-public-functions-the-api-between-branches).
**You're not blocked on B:** run with `TIREKICK_FAKE_AI=1` until B merges.

Your job is to make the chat feel effortless and never break on camera.

---

## 1. Deliverables, in priority order

| # | Deliverable | Done when |
|---|---|---|
| A1 | Meta app + WhatsApp Cloud API test number + webhook verified | `GET /webhook` handshake passes in the Meta dashboard; a message to the bot shows up in your logs |
| A2 | Send/receive text, download media | The bot echoes text; a sent video lands in `data/media/` |
| A3 | `/dev/simulate` endpoint | B and C can drive the whole flow from `curl` with no phones |
| A4 | Store (JSON file per deal) | Deals survive a server restart |
| A5 | Orchestrator state machine (§4) | The full happy path and the RED path both work with fakes |
| A6 | Buyer approvals (1 send / 2 edit / 3 stop) | No seller message ever goes out unapproved |
| A7 | Report page `/r/{deal_id}` (§6) | Looks good in a screen recording on desktop and phone |
| A8 | Stable deployment | A public HTTPS URL that doesn't change between restarts |
| A9 | Copy polish | Every bot message reads well out loud (it'll be in the video) |

Stretch goals, only after A1–A9: show the SAM 3.1 highlight images on cards, and an Arabic message variant for dubizzle.

## 2. WhatsApp Cloud API setup (do this first, about 1–2 hours)

1. Go to **developers.facebook.com**, then **My Apps**, then **Create App**. Choose type **Business**, then add the **WhatsApp** product.
2. In **WhatsApp > API Setup**, you get a **test phone number**, a **temporary access token** (24 h) and a **Phone number ID**.
   - Add up to **5 recipient numbers**: the 3 teammates, plus 2 spares for the negotiation study. Each recipient must confirm by code.
   - For a token that doesn't expire mid-demo, create a **System User** in Business Settings and give it a permanent token with `whatsapp_business_messaging` permission. Do this before Integration 1.
3. In **WhatsApp > Configuration > Webhook**:
   - Callback URL: `https://<your-ngrok-or-host>/webhook`
   - Verify token: the same string as `WHATSAPP_VERIFY_TOKEN` in `.env`
   - Subscribe to the **`messages`** field.
4. Copy the App Secret (**App settings > Basic**) into `WHATSAPP_APP_SECRET`.
5. Put the numbers in `.env` (see `.env.example`).

**Constraints we design around**
- The bot can only send **free-form** messages within **24 hours of the user's last message**. Outside that window it needs an approved **template**. Our flow always has the user message first: the buyer starts, and the seller taps a `wa.me` join link that pre-fills `DEAL-xxxx`.
- Media limits: video is about **16 MB**, so ask for **720p, ≤60 s**. If a seller sends a bigger file, reply asking for a shorter take, or accept a Google Drive or other link (B can download a direct link).
- Webhooks can be **retried and duplicated**. De-duplicate on `messages[].id`.
- Respond `200` to the webhook **immediately** and do the work in a background task (FastAPI `BackgroundTasks`). Verification takes 30–90 s.
- WhatsApp's policy bans general-purpose AI chatbots (since Jan 15, 2026), but a task-specific assistant is fine. Keep every message on-task.

## 3. Code you'll write

### 3.1 `tirekick/whatsapp/client.py`
```python
def send_text(to: str, body: str) -> str                    # returns wa message id
def send_image(to: str, image_path_or_url: str, caption: str = "") -> str
def send_buttons(to: str, body: str, buttons: list[tuple[str, str]]) -> str  # interactive reply buttons (max 3)
def download_media(media_id: str) -> tuple[str, str]        # (local_path, mime_type)
```
- Send: `POST https://graph.facebook.com/{GRAPH_API_VERSION}/{PHONE_NUMBER_ID}/messages` with a Bearer token.
- Download: `GET /{media_id}` returns a `url`, then `GET url` with the Bearer token returns the bytes. Save to `data/media/{media_id}.{ext}`.
- Use **interactive reply buttons** for approvals: "✅ Send", "✏️ Edit", "🛑 Stop". Also accept a typed `1`, `2` or `3` as a fallback.

### 3.2 `tirekick/whatsapp/webhook.py`
- `verify_signature(raw_body: bytes, header: str, app_secret: str) -> bool`: the `X-Hub-Signature-256` header is `sha256=<hex HMAC-SHA256 of the raw body with the app secret>`. Compare in constant time.
- `parse_incoming(payload: dict) -> list[IncomingMessage]`: flatten `entry[].changes[].value.messages[]` into `from`, `id`, `type`, text body, media id, mime type, and interactive button reply id. Ignore `statuses` events.

### 3.3 `tirekick/store.py` (already has a working JSON-file version; extend it)
- `save_deal(deal)`, `get_deal(deal_id)`, `find_deal_by_seller(wa_id)`, `find_active_deal_by_buyer(wa_id)`, `new_deal_id()`
- Write atomically (write a temp file, then `os.replace`) so a crash can't corrupt a deal.

### 3.4 `tirekick/orchestrator.py` (the heart of A's work)
`handle_message(msg: IncomingMessage) -> None` routes by **who** is talking:
- `msg.from` is a seller on an active deal → `on_seller_message`
- text matches `DEAL-\d{4}` → seller joining → `on_seller_join`
- otherwise → buyer → `on_buyer_message`

## 4. The state machine (implement exactly this)

| State | Trigger | Action | Next state |
|---|---|---|---|
| (none) | Buyer: any message | Create the deal. Reply: *"Hi! Paste a car listing (link, text or screenshots) and your max price, e.g. 'max 9000'."* | `NEW` |
| `NEW` | Buyer: listing text, screenshots, or "max N" | Collect until we have a listing and a ceiling. `verify.parse_listing(...)`. Store `buyer_ceiling`. | `LISTING_PARSED` |
| `LISTING_PARSED` | (on entry) | Send the summary: the car, asking price, a quick listing-VIN check if a VIN was shown, and the comps (`verify.price_comps`). Then: *"Forward this link to the seller: https://wa.me/<BOT>?text=DEAL-4821"* | (wait) |
| `LISTING_PARSED` | Seller: `DEAL-4821` | Bind `seller_wa_id`. `verify.issue_challenge(...)`. Send `challenge.message_text` to the seller. Tell the buyer *"Seller joined, challenge sent."* | `CHALLENGE_SENT` |
| `CHALLENGE_SENT` | Seller: text | Append to the chat (it feeds `scan_chat`). If they ask something, give a short helpful reply (resend the checklist). | (same) |
| `CHALLENGE_SENT` | Seller: video | `download_media`. Seller: *"Got it, checking now."* Buyer: *"Proof video received, verifying (~1 min)…"* Run `verify.run_verification(deal, path)` in the background. | `PROOF_RECEIVED` |
| `PROOF_RECEIVED` | Verification done, verdict **RED** | Buyer: the RED summary (top 3 reds), the report link, *"Recommend walking away. Send polite pass to seller? 1 yes / 3 no"* | `REJECTED` |
| `PROOF_RECEIVED` | Verification done, **GREEN/YELLOW** | Buyer: the summary and report link. `negotiate.start_negotiation`, then `negotiate.draft_offer` gives the opening offer. Show the draft with approval buttons. | `NEGOTIATING` (with `pending_draft`) |
| `NEGOTIATING` | Buyer: **1/Send** | Send `pending_draft.message_text` to the seller. Record the turn. Clear `pending_draft`. | (same) |
| `NEGOTIATING` | Buyer: **2/Edit**, then the buyer's text | Re-draft with the buyer's instruction (pass it to `draft_offer` as context), then show the new draft. | (same) |
| `NEGOTIATING` | Buyer: **3/Stop** | Draft a polite walk-away and ask once more: 1 send / 3 cancel. | `WALKED_AWAY` once sent |
| `NEGOTIATING` | Seller: text | `negotiate.apply_seller_reply`. If status is `AGREED`: draft the final confirmation (`is_final`) with the meetup suggestion. Otherwise `draft_offer(state, report, seller_text)` and show the draft to the buyer. | `AGREED` or (same) |
| `AGREED` | Buyer: 1 | Send the confirmation. Buyer: *"Done. Get a pre-purchase inspection before you pay. Report: <link>"* | (end) |
| any | 24 h without activity | Mark expired | `EXPIRED` |

**Invariant:** there's no code path that sends to the seller without `pending_draft` being approved, except the challenge message and the "got it" acknowledgement. Write a test for this.

## 5. WhatsApp copy (keep it short; it's read aloud in the video)

- Buyer summary, GREEN or YELLOW:
  > ✅ **2015 Honda Civic LX** (VIN matches)
  > Asking $9,400 · Fair price $8,300–8,900
  > 🟡 Recall: airbag inflator (check it's repaired)
  > 🟢 All 7 warning lights came on at key-on
  > 🟢 Odometer 84,120 mi matches the listing
  > Full report: https://…/r/DEAL-4821
- Buyer summary, RED:
  > 🛑 **Don't buy this one.**
  > 🔴 No code in the video. It may not be this car.
  > 🔴 VIN on the dash ≠ VIN in the listing
  > 🔴 Asked for a $500 deposit before a viewing
  > Report: https://…/r/DEAL-4822
- Draft-approval message:
  > **Draft to seller:**
  > "Thanks for the video! Given the open airbag recall (EV-03) and similar Civics at $8,300–8,900, would you take $8,100?"
  > [✅ Send] [✏️ Edit] [🛑 Stop]

## 6. Report page `/r/{deal_id}` (Jinja2, a single file, no build step)

Use `tirekick/report/templates/report.html`, which has a starter you can restyle. The sections are listed in [SPEC §8](SPEC.md#8-the-report):
1. **Hero:** the decoded car name, the verdict badge (red/yellow/green), asking price vs fair range.
2. **Evidence cards:** sorted red → yellow → green. Each shows the frame image (`/r/{id}/frames/EV-xx.jpg`), the summary, the detail, the source chip, and the clip time ("at 0:07").
3. **Recalls table,** with the honesty note.
4. **Negotiation transcript** (chat bubbles).
5. **Inspection questions.**
6. **Disclaimer footer.**

Design: big, readable, mobile-first. It's filmed for the demo, so test it at 390 px wide and 1440 px wide.

## 7. Deployment (by Integration 1, Mon 9 PM ET)

- **Dev:** `uvicorn tirekick.app:app --reload` plus `ngrok http 8000`. Note that the ngrok URL changes on restart unless you have a reserved domain.
- **Demo:** any always-on host with HTTPS and a persistent disk for `data/`, such as Render, Railway or Fly.io. Steps:
  - Start command: `uvicorn tirekick.app:app --host 0.0.0.0 --port $PORT`
  - Set every `.env` var in the host's dashboard.
  - Point the WhatsApp webhook at the stable URL and set `PUBLIC_BASE_URL`.
  - `ffmpeg` must be available on the host (B uses it for frames). Use a Dockerfile if the host doesn't provide it.
- Add a `/health` uptime check.

## 8. Tests you own (`tests/test_platform.py`)

- Signature check: valid, invalid and missing headers.
- `parse_incoming` on real sample payloads for text, video and button replies. Save samples in `tests/fixtures/wa_*.json`.
- State machine with fakes: the happy path ends in `AGREED`; the shady clip ends in `REJECTED`; **no seller send without approval**.
- Duplicate webhook delivery is processed only once.

## 9. Your timeline

| When (ET) | Target |
|---|---|
| Sun Nov 1, evening | A1–A3 (webhook live, echo, `/dev/simulate`) |
| Mon Nov 2, 6 PM | A4–A6 on fakes, report page v1 (A7). **Integration 1 at 9 PM** |
| Tue Nov 3, 6 PM | A8 deployed, A9 copy, real-data polish. **Freeze at 9 PM** |
| Wed Nov 4, morning | On call during recording; fix only what breaks |
