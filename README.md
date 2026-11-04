# TireKick

**Meta's Muse agent finds a car and haggles. TireKick makes the car prove itself.**

TireKick is a WhatsApp buyer's agent for private used-car sales (Facebook Marketplace in the US, dubizzle in the UAE). Before any negotiation, the seller has to film one continuous **proof-of-car** take that answers a one-time challenge code. TireKick verifies that take with Muse Spark plus deterministic checks (VIN check digit, NHTSA decode, recalls). Then it negotiates on the buyer's behalf. Every concession it asks for must cite verified evidence, the price ceiling is enforced in code, and the buyer approves every message before it is sent.

Built for the **Meta Global AI Developer Hackathon** (Indie track, theme "Build for Your World").

## Results

Full method, data and caveats in [eval/RESULTS.md](eval/RESULTS.md). The video tests use AI-generated clips and the negotiation study uses AI-played sellers (no real car was available during the hackathon).

| Study | Result |
|---|---|
| Red team: 6 spoof attempts (AI-generated take, old video / wrong code, different car) | **6/6 caught** for the expected reason (false-alarm rate on real honest takes untested) |
| Negotiation: 60 simulated negotiations | TireKick **84%** of the available discount vs **51%** for a student alone; **30/30** deals vs **15/30** |
| 200 public listings (US Cars dataset) | **96%** are a model with at least one NHTSA recall |
| Light check: dark check-engine light | **0/3 caught**: "can't tell" was treated as a pass; fix identified |

Demo video: (link)

## Read these first

| Doc | What it's for | Who reads it |
|---|---|---|
| [docs/SPEC.md](docs/SPEC.md) | The full product spec: user flows, the proof-of-car challenge, every check, negotiation rules, the report, the demo, the evaluation | Everyone |
| [docs/CONTRACTS.md](docs/CONTRACTS.md) | Shared data models and function signatures between the three workstreams. **Integration depends on it.** | Everyone |
| [docs/WORKFLOW.md](docs/WORKFLOW.md) | Branches, PRs, merge order, integration checkpoints, the hour-by-hour timeline to the deadline | Everyone |
| [docs/workstream-A-platform.md](docs/workstream-A-platform.md) | Branch `platform-whatsapp`: WhatsApp bot, webhook, conversation state machine, approvals, report page, deployment | Person A |
| [docs/workstream-B-intelligence.md](docs/workstream-B-intelligence.md) | Branch `verification-negotiation`: Muse Spark proof-take analysis, VIN, recalls, price comparisons, scam signals, report builder, negotiation agent | Person B |
| [docs/workstream-C-eval-demo.md](docs/workstream-C-eval-demo.md) | Branch `eval-demo`: the 100-listing study, red team, light check, negotiation study, demo video, submission | Person C |

## The three branches

```
main ──────────────────────────────────────────────── (shared contracts, docs, tests)
  ├── platform-whatsapp         Person A: tirekick/app.py, orchestrator.py, store.py, whatsapp/, report/
  ├── verification-negotiation  Person B: tirekick/verify/, tirekick/negotiate/, scripts/
  └── eval-demo                 Person C: eval/, demo/, README numbers
```

Each person works only in their own folders, so the branches merge without conflicts. The interface between the branches is `tirekick/models.py` plus the function signatures in [docs/CONTRACTS.md](docs/CONTRACTS.md). **Change those only through a small PR to `main` that everyone sees.** The details are in [docs/WORKFLOW.md](docs/WORKFLOW.md).

## Quickstart

```bash
git clone https://github.com/Keshav-kh/tirekick.git
cd tirekick
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env        # fill in your keys (never commit .env)
pytest                      # contract + VIN + policy tests must pass
```

Run the bot locally with fake AI (A can build the whole flow before B's code lands):

```bash
TIREKICK_FAKE_AI=1 uvicorn tirekick.app:app --reload --port 8000
# expose it for the WhatsApp webhook, e.g.:  ngrok http 8000
```

Run the verifier on a local video (B and C use this constantly):

```bash
python scripts/verify_clip.py --video samples/coldstart.mp4 --code K7Q2XM --listing samples/listing.json
```

## Stack

- Python 3.11+, FastAPI, httpx, Pydantic v2, Jinja2, pytest
- **Meta Model API** (OpenAI-compatible) for **Muse Spark**: video/audio/image understanding, structured output, web search
- **SAM 3.1** (Meta Model API) for evidence crops and highlights in the report
- **WhatsApp Cloud API** for the buyer and seller chats
- NHTSA **vPIC** (VIN decode) and **Recalls** APIs, both free with no key

## Status

- [x] All three workstreams merged; tests pass
- [x] Evaluation complete ([eval/RESULTS.md](eval/RESULTS.md))
- [x] Demo video; WhatsApp delivery pending Meta business verification
- [ ] Submitted (Wed Nov 4, 2026)
