# TireKick: submission

**Track:** Indie · **Theme:** Build for Your World
**Name:** TireKick
**Tagline:** Meta's Muse agent finds a car and haggles. TireKick makes the car prove itself.

## Problem

Buying a used car from a private seller on Facebook Marketplace or dubizzle means trusting photos and a
stranger's word. Meta's Muse agent can now find a car and negotiate for you, but nothing checks the car.
Sellers hide faults with tricks as simple as tape over the check-engine light, about 1 in 5 US vehicles
has an open recall, and Marketplace car scams (fake listings, deposits for cars that don't exist) are
well documented. The people hit hardest are students and young people buying a cheap first car,
often international students with no credit history who can't afford a dealer.

## What it does

TireKick is a buyer's agent in WhatsApp.

1. **The buyer** pastes a listing and their max price. TireKick reads it, checks the VIN, pulls NHTSA
   recalls and comparable prices, and gives the buyer a link to forward to the seller.
2. **The seller** gets a one-time code and is asked for one continuous video (up to 60 seconds): the code
   next to the windshield VIN, the door-jamb sticker, every warning light at key-on, the odometer, and a
   cold start. It's liveness detection for a physical object: an old video, a different car or a
   spliced clip can't contain today's code next to the right VIN.
3. **Verification:** Muse Spark watches the take three times and reports only facts (code read, VINs,
   which lights lit, odometer, cuts, screen replay). Code makes every decision: VIN check digit, NHTSA
   decode, recalls, door VIN vs windshield VIN vs listing, odometer vs listing. The buyer gets a 🟢/🟡/🔴
   verdict with every reason and a report page with the evidence frames.
4. **Negotiation:** if the car isn't red, TireKick drafts offers that may only cite verified evidence
   (an open recall, higher real mileage, comps). The price ceiling is enforced in code, and nothing reaches
   the seller until the buyer taps Send. If the car is red, it drafts a polite walk-away instead.

## How we used Meta's tools

- **Muse Spark** (Meta Model API): reads the seller's proof video (code, both VINs, per-light status at
  key-on and after start, odometer, temperature needle, cuts, screen replay), parses listing text and
  screenshots, finds comparable prices with web search, flags scam signals in the chat, and writes the
  offer messages. Structured output, three runs merged by majority vote.
- **SAM 3.1:** highlights each piece of evidence (the VIN plate, a warning light) in the report frames.
- **WhatsApp Cloud API:** both chats (buyer and seller), media download, approve/edit/stop buttons.

## Results

Full method, data and caveats: `eval/RESULTS.md`. No real car was available during the hackathon, so the
video tests use AI-generated clips (Higgsfield), and the negotiation study uses AI-played sellers. Both are
labelled that way.

| Study | Result |
|---|---|
| 200 listings (public US Cars dataset, auction listings ~2020) | Every VIN valid; year matched 200/200, make 199/200. **96% are a model with at least one NHTSA recall.** |
| 3 current Craigslist private-seller listings | None mention a recall. The 2004 Honda Element ("runs and drives excellent, clean title") is a model with **11 recalls, including both front airbag inflators**. |
| Red team: 6 spoof attempts (AI-generated take, old video / wrong code, different car) | **6/6 caught** for the expected reason. False-alarm rate on real honest takes is untested. |
| Light check: does a dark check-engine light get flagged? | **0/3 caught.** Muse Spark reported the light as "can't tell" while clearly seeing others, and our report code treated "can't tell" as a pass. Fixed since; not yet re-measured (see limits). |
| Negotiation (60 simulated negotiations) | TireKick captured **84%** of the available discount vs **51%** for a student negotiating alone, and closed **30/30** deals vs **15/30**. |

Live run with real Muse Spark (web demo): an AI-generated proof video was rejected 🔴 for five independent
reasons: cuts at 5/10/15 s, an invalid windshield VIN, windshield vs door VIN mismatch, video VIN vs
listing mismatch, and an odometer reading of 98,412 mi against a listed 200,000.

## Honest limits

- Not a mechanical inspection. TireKick always recommends a pre-purchase inspection.
- Recalls are model-level (year/make/model), not proof that this exact car is unrepaired.
- **Hidden-light check:** at evaluation time a blurry or distant dashboard passed, because "couldn't tell"
  wasn't flagged. Fixed: an unconfirmed check-engine, airbag or ABS light is now yellow ("refilm the
  dashboard up close"). The 0/3 above was measured before the fix and hasn't been re-run.
- Tested on AI-generated clips and AI-played sellers, not real cars or real people. The false-alarm rate on
  honest sellers is our first next test.
- Our WhatsApp business account is restricted until Meta business verification, so the recorded demo runs
  the same bot through a web chat (buyer and seller side by side) instead of WhatsApp.
- Bugs our own evaluation found, all fixed with regression tests: the hidden-light gap above; a reply parser
  that read "okay, I can't go that low" as agreement (never triggered in 30 runs); a silent "saw nothing"
  result when ffmpeg is missing (now a red "couldn't be analyzed"); recall lookups failing for Scion VINs.

## What's next

- Re-run the light check with the fix, then measure false alarms on real honest proof takes.
- TireKick as a tool Meta's Muse agent can call (Muse Connector), so Muse checks the car before it haggles.
- dubizzle and Arabic support for the UAE market.

## Links

- Repo: https://github.com/Keshav-kh/tirekick
- Demo video: https://youtu.be/oZptKwqpeaw
