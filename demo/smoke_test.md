# End-to-end smoke test (no phones needed)

Run this at every integration checkpoint. It drives the full flow through `/dev/simulate`.

```bash
# terminal 1: fake AI first; later drop TIREKICK_FAKE_AI to test the real B code
TIREKICK_FAKE_AI=1 TIREKICK_DEV=1 uvicorn tirekick.app:app --port 8000
```

```bash
# terminal 2
S=http://localhost:8000/dev/simulate
BUYER=15550000001; SELLER=15550000002

# 1. buyer pastes a listing + max
curl -s $S -H 'content-type: application/json' -d "{\"from\":\"$BUYER\",\"text\":\"2003 Honda Accord EX, 128k miles, \$4,800, runs great, VIN 1HGCM82633A004352. max 5000\"}"
# -> outbox shows the summary + a wa.me link containing DEAL-xxxx; copy that code

# 2. seller joins with the code
curl -s $S -H 'content-type: application/json' -d "{\"from\":\"$SELLER\",\"text\":\"DEAL-xxxx\"}"

# 3. seller sends the proof video (fake mode: any path; "shady" in the name gives a RED report)
curl -s $S -H 'content-type: application/json' -d "{\"from\":\"$SELLER\",\"media_path\":\"clips/honest_accord_01.mp4\"}"

# 4. buyer approves the opening offer
curl -s $S -H 'content-type: application/json' -d "{\"from\":\"$BUYER\",\"text\":\"1\"}"

# 5. seller counters, then the buyer approves again
curl -s $S -H 'content-type: application/json' -d "{\"from\":\"$SELLER\",\"text\":\"I can do 4600\"}"
curl -s $S -H 'content-type: application/json' -d "{\"from\":\"$BUYER\",\"text\":\"1\"}"

# 6. open the report
open http://localhost:8000/r/DEAL-xxxx    # Windows: start http://localhost:8000/r/DEAL-xxxx
```

**Pass when:**
- the outbox shows exactly one challenge and one "got it" to the seller before the first approval
- every other seller message was approved first
- the report page renders.
