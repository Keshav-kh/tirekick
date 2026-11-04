"""C5 (simulated): AI-played sellers negotiate against a student buyer (H) and TireKick (T). Owner: C.

  python eval/sim_negotiation.py                     # 10 personas x 2 conditions, 1 repeat
  python eval/sim_negotiation.py --repeats 3         # 60 negotiations
  python eval/negotiation_study.py eval/out/sim_negotiation.csv

Results are SIMULATED and must be labelled that way ("AI-played sellers"), never as real people.

Fairness rules, enforced in code:
- Every seller has a secret floor (reservation). Code blocks any accept or counter below it,
  so the model playing the seller can't "give away" the car.
- Both buyers get the same budget (buyer_max) and the same number of seller replies.
- H only sees the listing. T sees TireKick's report (evidence + comps), which is the product's edge.
- The deal price comes from the seller's structured reply, not from TireKick's own parser.
  When TireKick's parser thinks a deal was agreed but the seller didn't agree, that's logged
  as parser_false_agree (a real bug to report to B).

With no META_API_KEY or TIREKICK_FAKE_AI=1, sellers and the H buyer are simple rule bots, so the
harness runs offline. Those numbers only test the plumbing; don't report them.
"""

from __future__ import annotations

import argparse
import json
import random
import re
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

from _common import OUT, ROOT, write_rows

from tirekick.config import env, fake_ai
from tirekick.models import (
    Evidence, EvidenceSource, EvidenceType, Listing, NegotiationStatus, PriceComps, ProofChallenge,
    Severity, VerificationReport, utcnow,
)
from tirekick.negotiate import (
    apply_seller_reply, draft_offer, final_offer, record_sent_offer, start_negotiation, walk_away_offer,
)

CARDS = ROOT / "eval" / "data" / "car_cards.json"
MAX_ROUNDS = 6
CLOSE_GAP = 150  # seller and buyer this close = the rule bots settle

PERSONAS = [
    ("stubborn", "Stubborn. You think the car is worth every dollar and you concede slowly, in small steps."),
    ("chill", "Laid-back and friendly. You want a fair deal and don't love haggling."),
    ("desperate", "You're moving cities in 4 days and really need the car gone, but you hide it."),
    ("suspicious", "Suspicious of lowballers and scammers. A rude or very low offer annoys you."),
    ("chatty", "Talkative and warm. You tell little stories about the car and like the buyer to like you."),
    ("defensive", "Defensive about the car's problems. You downplay issues, but you won't lie outright if asked directly."),
    ("short", "You reply in very short texts, often without punctuation. Busy and a bit impatient."),
    ("overvaluer", "You believe your car is worth more than market because you took good care of it."),
    ("honest", "Honest. If the buyer raises a real problem you admit it and adjust your price fairly."),
    ("haggler", "You love bargaining and always counter, even when the offer is close."),
]

FACT_WORDS = re.compile(r"recall|light|odometer|mileage|miles|leak|transmission|cvt|abs|oil|coolant|engine", re.I)


# --------------------------------------------------------------------------- data


def load_cards(path: Path = CARDS) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["cards"]


def listing_for(card: dict) -> Listing:
    li = card["listing"]
    return Listing(listing_id=card["card_id"], asking_price=li["asking"], year=li["year"], make=li["make"],
                   model=li["model"], trim=li.get("trim"), mileage=li.get("mileage"),
                   description=li.get("description", ""),
                   title=f'{li["year"]} {li["make"]} {li["model"]} {li.get("trim", "")}'.strip())


def listing_text(card: dict) -> str:
    li = card["listing"]
    return (f'{li["year"]} {li["make"]} {li["model"]} {li.get("trim", "")}, {li["mileage"]:,} miles. '
            f'{li.get("description", "")} Asking ${li["asking"]:,}.')


def report_for(card: dict) -> VerificationReport:
    """The report TireKick would have built for this car (evidence matches the seller's hidden facts)."""
    now = utcnow()
    ch = ProofChallenge(challenge_id="CH-sim", deal_id=card["card_id"], code="SIMSIM", issued_at=now,
                        expires_at=now + timedelta(hours=24), message_text="")
    evidence = [Evidence(id=f"EV-{i:02d}", type=EvidenceType(e["type"]), severity=Severity.YELLOW,
                         summary=e["summary"], source=EvidenceSource(e["source"]), price_impact=e["price_impact"])
                for i, e in enumerate(card["evidence"], 1)]
    c = card["comps"]
    return VerificationReport(deal_id=card["card_id"], listing=listing_for(card), challenge=ch,
                              comps=PriceComps(low=c["low"], median=c["median"], high=c["high"], n=c["n"]),
                              evidence=evidence, verdict=VerificationReport.compute_verdict(evidence))


# --------------------------------------------------------------------------- model helper


def use_llm() -> bool:
    return not fake_ai() and bool(env("META_API_KEY"))


def chat_json(system: str, messages: list[dict], model: str, temperature: float) -> dict | None:
    """One chat call that must return a JSON object. Returns None on any failure."""
    from tirekick.verify.muse import client

    for _ in range(2):
        try:
            resp = client().chat.completions.create(
                model=model, temperature=temperature,
                messages=[{"role": "system", "content": system}, *messages])
            text = resp.choices[0].message.content or ""
            m = re.search(r"\{.*\}", text, re.S)
            if m:
                return json.loads(m.group(0))
        except Exception:  # noqa: BLE001 - retry once, then the caller falls back to the rule bot
            continue
    return None


def as_int(v) -> int | None:
    try:
        return int(round(float(str(v).replace(",", "").replace("$", "")))) if v not in (None, "") else None
    except ValueError:
        return None


# --------------------------------------------------------------------------- seller


@dataclass
class SellerMove:
    text: str
    action: str           # counter | accept | walk | talk
    price: int | None     # seller's current ask (for counter)


SELLER_SYSTEM = """You are role-playing a private seller of a used car, chatting with a buyer on WhatsApp.
Personality: {persona}
Your car: {listing}
Things only you know (never volunteer them; if the buyer raises one, react in character):
{facts}
Your secret lowest price is ${floor:,}. Never accept or ask for less than that. Never ask for more than ${asking:,}.
Write like a real person texting: short, casual. Never mention that you are an AI or that this is a study.
After every buyer message, reply with ONLY a JSON object:
{{"message": "<your WhatsApp reply>", "action": "counter" | "accept" | "walk" | "talk", "price": <your current asking price as an integer, or null>}}
"accept" means you accept the buyer's latest offer. "walk" means you end the conversation."""


class Seller:
    def __init__(self, card: dict, persona: tuple[str, str], model: str, rng: random.Random):
        self.card, self.persona, self.model, self.rng = card, persona, model, rng
        self.asking, self.floor = card["listing"]["asking"], card["reservation"]
        self.ask = self.asking
        self.history: list[dict] = []
        self.floor_blocks = 0
        self.system = SELLER_SYSTEM.format(persona=persona[1], listing=listing_text(card),
                                           facts="\n".join(f"- {f}" for f in card["hidden_facts"]),
                                           floor=self.floor, asking=self.asking)

    def reply(self, buyer_text: str, buyer_offer: int | None) -> SellerMove:
        self.history.append({"role": "user", "content": buyer_text})
        move = self._llm(buyer_offer) if use_llm() else None
        move = move or self._rule(buyer_text, buyer_offer)
        move = self._enforce(move, buyer_offer)
        self.history.append({"role": "assistant", "content": move.text})
        if move.price is not None:
            self.ask = move.price
        return move

    def _llm(self, buyer_offer: int | None) -> SellerMove | None:
        hint = f"\n(Buyer's latest offer: ${buyer_offer:,}.)" if buyer_offer else ""
        msgs = self.history[:-1] + [{"role": "user", "content": self.history[-1]["content"] + hint}]
        out = chat_json(self.system, msgs, self.model, temperature=0.8)
        if not out or "message" not in out:
            return None
        action = str(out.get("action", "talk")).lower()
        return SellerMove(str(out["message"]), action if action in {"counter", "accept", "walk", "talk"} else "talk",
                          as_int(out.get("price")))

    def _rule(self, buyer_text: str, buyer_offer: int | None) -> SellerMove:
        name = self.persona[0]
        concede = {"stubborn": 0.2, "haggler": 0.3, "overvaluer": 0.2, "desperate": 0.55, "honest": 0.45}.get(name, 0.35)
        if FACT_WORDS.search(buyer_text or ""):
            concede += 0.15
        if buyer_offer is None:
            return SellerMove(f"yeah still available. asking {self.ask}", "talk", self.ask)
        if buyer_offer >= max(self.floor, self.ask - CLOSE_GAP):
            return SellerMove("ok deal", "accept", None)
        new = max(self.floor, int(self.ask - (self.ask - buyer_offer) * concede) // 50 * 50)
        return SellerMove(f"cant do that. {new} and its yours", "counter", new)

    def _enforce(self, move: SellerMove, buyer_offer: int | None) -> SellerMove:
        """The secret floor is enforced in code, whatever the model says."""
        if move.action == "accept" and (buyer_offer is None or buyer_offer < self.floor):
            self.floor_blocks += 1
            return SellerMove(f"nah i cant go that low. {self.floor} is the lowest", "counter", self.floor)
        if move.price is not None:
            move.price = min(max(move.price, self.floor), self.asking)
            if buyer_offer is not None and move.price <= buyer_offer:   # countered at/under the offer = accept
                return SellerMove(move.text, "accept", None)
        return move


# --------------------------------------------------------------------------- buyers


@dataclass
class BuyerMove:
    text: str
    offer: int | None
    action: str = "offer"   # offer | walk


HUMAN_SYSTEM = """You are a college student buying your first used car from a private seller on WhatsApp.
You only know what the listing says: {listing}
Your absolute maximum is ${maximum:,}. Never offer more than that. Try to pay as little as you reasonably can,
the way a normal student would negotiate by text. Don't invent problems with the car.
Reply with ONLY a JSON object:
{{"message": "<your WhatsApp message>", "action": "offer" | "walk", "offer": <your current offer as an integer, or null>}}"""


class HumanBuyer:
    """Condition H: a student negotiating alone, with only the listing."""

    def __init__(self, card: dict, model: str):
        self.card, self.model = card, model
        self.maximum, self.asking = card["buyer_max"], card["listing"]["asking"]
        self.offer: int | None = None
        self.history: list[dict] = []
        self.system = HUMAN_SYSTEM.format(listing=listing_text(card), maximum=self.maximum)

    def _llm(self, seller_text: str | None) -> BuyerMove | None:
        if seller_text is not None:
            self.history.append({"role": "user", "content": seller_text})
        msgs = self.history or [{"role": "user", "content": "(Start the conversation with the seller.)"}]
        out = chat_json(self.system, msgs, self.model, temperature=0.7)
        if not out or "message" not in out:
            return None
        action = "walk" if str(out.get("action", "")).lower() == "walk" else "offer"
        offer = as_int(out.get("offer"))
        offer = min(offer, self.maximum) if offer is not None else self.offer
        self.history.append({"role": "assistant", "content": str(out["message"])})
        return BuyerMove(str(out["message"]), offer, action)

    def _rule(self, seller_price: int | None) -> BuyerMove:
        if self.offer is None:
            self.offer = int(self.asking * 0.85) // 50 * 50
            return BuyerMove(f"hey is the car still available? would u take {self.offer}?", self.offer)
        ask = seller_price or self.asking
        if ask <= self.maximum and ask - self.offer <= CLOSE_GAP:
            self.offer = ask
            return BuyerMove(f"ok {ask} works for me", ask)
        self.offer = min(self.maximum, max(self.offer, int(self.offer + (ask - self.offer) / 3) // 50 * 50))
        return BuyerMove(f"i can do {self.offer}", self.offer)

    def open(self) -> BuyerMove:
        return self.respond(None, None)

    def respond(self, seller_text: str | None, seller_price: int | None) -> BuyerMove:
        move = self._llm(seller_text) if use_llm() else None
        if move is None:
            move = self._rule(seller_price)
        self.offer = move.offer
        return move


class TireKickBuyer:
    """Condition T: B's real negotiation agent, buyer approves every draft unedited."""

    def __init__(self, card: dict, max_rounds: int):
        self.report = report_for(card)
        self.state = start_negotiation(card["card_id"], self.report, buyer_ceiling=card["buyer_max"])
        self.state.max_rounds = max_rounds
        self.false_agrees = 0

    def _send(self, offer) -> BuyerMove:
        self.state = record_sent_offer(self.state, offer)
        return BuyerMove(offer.message_text, offer.amount, "walk" if offer.is_walk_away else "offer")

    def open(self) -> BuyerMove:
        return self._send(draft_offer(self.state, self.report))

    def respond(self, seller_text: str, seller_price: int | None, seller_action: str) -> BuyerMove:
        self.state = apply_seller_reply(self.state, seller_text)
        if self.state.status == NegotiationStatus.AGREED:
            if seller_action != "accept" and (seller_price is None or seller_price != self.state.last_seller_ask):
                self.false_agrees += 1   # TireKick's parser heard a deal the seller didn't make
            return self._send(final_offer(self.state))
        if self.state.status == NegotiationStatus.WALKED_AWAY:
            return self._send(walk_away_offer(self.state))
        return self._send(draft_offer(self.state, self.report, seller_message=seller_text))


# --------------------------------------------------------------------------- one negotiation


@dataclass
class Result:
    final_price: int | None
    walked_away: bool
    rounds: int
    transcript: list[dict] = field(default_factory=list)
    floor_blocks: int = 0
    false_agrees: int = 0


def negotiate(card: dict, persona: tuple[str, str], condition: str, model: str, rng: random.Random,
              max_rounds: int = MAX_ROUNDS) -> Result:
    seller = Seller(card, persona, model, rng)
    buyer = TireKickBuyer(card, max_rounds) if condition == "T" else HumanBuyer(card, model)
    transcript: list[dict] = []
    move = buyer.open()
    for rnd in range(1, max_rounds + 1):
        transcript.append({"role": "buyer", "text": move.text, "offer": move.offer})
        if move.action == "walk":
            return Result(None, True, rnd - 1, transcript, seller.floor_blocks, getattr(buyer, "false_agrees", 0))
        s = seller.reply(move.text, move.offer)
        transcript.append({"role": "seller", "text": s.text, "action": s.action, "price": s.price})
        if s.action == "accept" and move.offer is not None:
            return Result(move.offer, False, rnd, transcript, seller.floor_blocks, getattr(buyer, "false_agrees", 0))
        if s.action == "walk":
            return Result(None, True, rnd, transcript, seller.floor_blocks, getattr(buyer, "false_agrees", 0))
        move = (buyer.respond(s.text, s.price, s.action) if condition == "T"
                else buyer.respond(s.text, s.price))
    return Result(None, True, max_rounds, transcript, seller.floor_blocks, getattr(buyer, "false_agrees", 0))


# --------------------------------------------------------------------------- study design


def schedule(cards: list[dict]) -> list[tuple[int, str, dict, str]]:
    """10 personas x 2 rounds, different car each round. Odd participants do H first.
    Card offsets are chosen so every card is used once under H and once under T."""
    n, rows = len(cards), []
    for i in range(n):
        first, second = ("H", "T") if i % 2 == 0 else ("T", "H")
        a, b = cards[i], cards[(i + 4) % n]
        h_card, t_card = (a, b) if i % 2 == 0 else (b, a)
        order = first + second
        for cond in (first, second):
            rows.append((i, order, h_card if cond == "H" else t_card, cond))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--rounds", type=int, default=MAX_ROUNDS)
    ap.add_argument("--model", default=env("SIM_MODEL") or env("MUSE_MODEL", "muse-spark-1.3"))
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=str(OUT / "sim_negotiation.csv"))
    args = ap.parse_args()

    cards = load_cards()
    source = "simulated-llm" if use_llm() else "simulated-rules"
    if source == "simulated-rules":
        print("NOTE: TIREKICK_FAKE_AI=1 or no META_API_KEY, so sellers are rule bots. Plumbing test only; don't report.")
    tdir = OUT / "transcripts"
    tdir.mkdir(parents=True, exist_ok=True)
    rows, floor_blocks, false_agrees = [], 0, 0
    for rep in range(args.repeats):
        for i, order, card, cond in schedule(cards):
            persona = PERSONAS[i % len(PERSONAS)]
            rng = random.Random(args.seed * 1000 + rep * 100 + i)
            r = negotiate(card, persona, cond, args.model, rng, args.rounds)
            pid = f"S{i + 1:02d}" + (f"r{rep + 1}" if args.repeats > 1 else "")
            tpath = tdir / f"{pid}_{cond}_{card['card_id']}.json"
            tpath.write_text(json.dumps({"persona": persona[0], "card": card["card_id"], "condition": cond,
                                         "transcript": r.transcript}, indent=2), encoding="utf-8")
            floor_blocks += r.floor_blocks
            false_agrees += r.false_agrees
            rows.append({"participant": pid, "order": order, "card_id": card["card_id"], "condition": cond,
                         "asking": card["listing"]["asking"], "reservation": card["reservation"],
                         "final_price": r.final_price or "", "rounds": r.rounds, "minutes": "",
                         "walked_away": "yes" if r.walked_away else "no", "source": source,
                         "persona": persona[0], "model": args.model if source == "simulated-llm" else "rules",
                         "parser_false_agree": r.false_agrees, "transcript": str(tpath.relative_to(ROOT))})
    write_rows(Path(args.out), rows)
    print(f"Wrote {len(rows)} negotiations to {args.out}")
    print(f"Seller floor blocks (model tried to go under its secret price): {floor_blocks}")
    print(f"TireKick parser false agreements (reported to B): {false_agrees}")
    print(f"Next: python eval/negotiation_study.py {args.out}")


if __name__ == "__main__":
    main()
