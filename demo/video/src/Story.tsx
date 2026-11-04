import React from "react";
import { Audio } from "@remotion/media";
import { AbsoluteFill, Easing, Sequence, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { COLORS, LINE_AT, SCENES, SFX, TOTAL_S, lineEnd } from "./timeline";
import { DashboardScene, StreetScene, VinScene } from "./three/scenes";
import { Captions, CodeCard, Flag, Headline, Logo, Phone, Stat, TireMark, pop } from "./ui";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const SANS = '"Inter", "Segoe UI", Helvetica, Arial, sans-serif';

/** One scene on the timeline, with a short fade-in so cuts don't pop. */
const Scene: React.FC<{ name: keyof typeof SCENES; children: React.ReactNode; fade?: boolean }> = ({ name, children, fade = true }) => {
  const { fps } = useVideoConfig();
  const [a, b] = SCENES[name];
  return (
    <Sequence name={name} from={Math.round(a * fps)} durationInFrames={Math.round((b - a) * fps)} premountFor={fps}>
      {fade ? <FadeIn>{children}</FadeIn> : children}
    </Sequence>
  );
};
const FadeIn: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const frame = useCurrentFrame();
  return <AbsoluteFill style={{ opacity: interpolate(frame, [0, 6], [0, 1], clamp) }}>{children}</AbsoluteFill>;
};

const Backdrop: React.FC<{ tint?: string }> = ({ tint = "#10203A" }) => (
  <AbsoluteFill style={{ background: `radial-gradient(ellipse at 30% 40%, ${tint} 0%, #070B14 75%)` }} />
);

// ---------------------------------------------------------------- composite scenes

const Trap: React.FC = () => (
  <AbsoluteFill>
    <Backdrop tint="#3A1424" />
    <Phone title="Car seller" x={-380} msgs={[
      { at: 0.4, from: "bot", text: "Lots of people asking about the Accord. Send a *$500 deposit* and I'll hold it for you." },
      { at: 1.1, from: "bot", text: "I'm on a submarine right now (the Wi-Fi is amazing), so I can't meet. Zelle is fine." },
    ]} />
    <Flag at={1.4} top={330} text="Deposit before you've seen it" />
    <Flag at={1.9} top={470} right={220} text="Seller can't meet" />
  </AbsoluteFill>
);

const Steps: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const steps: [number, string][] = [
    [2.3, "One continuous take, no cuts"],
    [4.2, "One-time code next to the VIN"],
    [6.1, "Every warning light at key-on"],
    [8.0, "Then the engine start"],
  ];
  return (
    <AbsoluteFill style={{ padding: "110px 0 0 110px" }}>
      {steps.map(([at, text], i) => {
        const p = pop(frame, at * fps, fps);
        return (
          <div key={text} style={{
            display: "flex", alignItems: "center", gap: 22, marginBottom: 20, opacity: p, translate: `${interpolate(p, [0, 1], [-40, 0])}px 0`,
          }}>
            <div style={{ width: 64, height: 64, borderRadius: 32, background: COLORS.brand, color: "#fff", display: "grid", placeItems: "center", font: `800 34px ${SANS}` }}>{i + 1}</div>
            <div style={{ padding: "12px 26px", borderRadius: 16, background: "rgba(8,11,20,.72)", color: "#fff", font: `600 40px ${SANS}` }}>{text}</div>
          </div>
        );
      })}
    </AbsoluteFill>
  );
};

/** The challenge: the code card next to the VIN, then the dashboard bulb check, under one narration line. */
const Challenge: React.FC = () => {
  const { fps } = useVideoConfig();
  const split = Math.round(5.9 * fps);
  return (
    <AbsoluteFill>
      <Sequence durationInFrames={split}><VinScene /></Sequence>
      <Sequence from={split}><DashboardScene variant="sweep" /></Sequence>
      <Steps />
    </AbsoluteFill>
  );
};

const VERDICT_CODE = `@staticmethod
def compute_verdict(evidence: list[Evidence]) -> Severity:
    """Overall verdict is computed in code, never by the model (SPEC §6.3)."""
    severities = {e.severity for e in evidence}
    if Severity.RED in severities:
        return Severity.RED
    if Severity.YELLOW in severities:
        return Severity.YELLOW
    return Severity.GREEN`;

const VIN_CODE = `total = sum(_TRANSLIT[c] * w for c, w in zip(v, _WEIGHTS))
remainder = total % 11
expected = "X" if remainder == 10 else str(remainder)
return v[8] == expected, v`;

const CEILING_CODE = `def check_offer(offer: Offer, state: NegotiationState, report: VerificationReport) -> None:
    """Raise PolicyViolation if the draft breaks any SPEC section 7 rule."""
    if FORBIDDEN.search(offer.message_text or ""):
        raise PolicyViolation("message mentions payment details, a deposit, or an address")
    ...
    if offer.amount > state.buyer_ceiling:
        raise PolicyViolation(f"amount {offer.amount} exceeds the buyer ceiling {state.buyer_ceiling}")`;

const VerdictCode: React.FC = () => (
  <AbsoluteFill>
    <Backdrop />
    <Headline text="The model reports. The code decides." top={110} />
    <CodeCard file="tirekick/models.py" code={VERDICT_CODE} mark={[2]} markAt={2.6} top={290} width={1740} size={31} />
  </AbsoluteFill>
);

const Chip: React.FC<{ at: number; top: number; left: number; text: string; color: string }> = ({ at, top, left, text, color }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = pop(frame, at * fps, fps);
  return (
    <div style={{ position: "absolute", top, left, padding: "16px 28px", borderRadius: 40, border: `3px solid ${color}`, color, font: `700 38px ${SANS}`, opacity: p, scale: String(interpolate(p, [0, 1], [0.8, 1])) }}>{text}</div>
  );
};

const Scam: React.FC = () => {
  const frame = useCurrentFrame();
  const flash = interpolate(frame, [0, 4, 14], [0.55, 0.55, 0], clamp);
  return (
    <AbsoluteFill>
      <Backdrop tint="#4A0F22" />
      <Phone x={-420} msgs={[
        { at: 0.8, from: "bot", tone: "red", text: "*Don't buy this one.*" },
        { at: 2.0, from: "bot", tone: "red", text: "The video doesn't show the requested code next to the VIN." },
        { at: 3.2, from: "bot", tone: "red", text: "The VIN read from the windshield fails the standard check digit." },
        { at: 4.4, from: "bot", tone: "red", text: "Asked for a deposit before showing the car on video." },
      ]} />
      <CodeCard file="tirekick/verify/vin.py" code={VIN_CODE} mark={[3]} markAt={3.3} x={470} width={1110} top={360} size={26} />
      <Headline text="Caught." at={0.5} top={170} size={120} color="#FF5C7C" align="left" left={930} />
      <Notification at={SCENES.scam[1] - SCENES.scam[0] - 3.1} from="Car seller" text="ok fine. $300 deposit?" />
      <AbsoluteFill style={{ background: COLORS.red, opacity: flash, mixBlendMode: "screen" }} />
    </AbsoluteFill>
  );
};

const Notification: React.FC<{ at: number; from: string; text: string }> = ({ at, from, text }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = pop(frame, at * fps, fps);
  const wobble = interpolate(frame - at * fps, [0, 6, 12, 18], [0, -3, 2, 0], clamp);
  return (
    <div style={{
      position: "absolute", left: 930, top: 660, width: 820, padding: "22px 28px", borderRadius: 26,
      background: "rgba(255,255,255,.96)", boxShadow: "0 24px 70px rgba(0,0,0,.5)", opacity: p,
      translate: `0 ${interpolate(p, [0, 1], [-60, 0])}px`, rotate: `${wobble}deg`,
      display: "flex", gap: 20, alignItems: "center",
    }}>
      <div style={{ width: 70, height: 70, borderRadius: 18, background: "#25D366", display: "grid", placeItems: "center", color: "#fff", font: `800 34px ${SANS}` }}>?</div>
      <div>
        <div style={{ color: "#667781", font: `600 28px ${SANS}` }}>{from}</div>
        <div style={{ color: "#111B21", font: `600 42px ${SANS}` }}>{text}</div>
      </div>
    </div>
  );
};

const PriceTag: React.FC<{ at: number; top: number; label: string; value: string; color: string; strike?: boolean; note?: string }> = ({ at, top, label, value, color, strike, note }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = pop(frame, at * fps, fps);
  return (
    <div style={{ position: "absolute", top, left: 1080, opacity: p, translate: `${interpolate(p, [0, 1], [60, 0])}px 0` }}>
      <div style={{ color: "#93A1B5", font: `600 34px ${SANS}` }}>{label}</div>
      <div style={{ color, font: `800 140px/1 "Inter Display", sans-serif`, letterSpacing: "-0.04em", textDecoration: strike ? "line-through" : undefined, textDecorationThickness: 8 }}>{value}</div>
      {note && <div style={{ marginTop: 10, color: "#CFE9E2", font: `500 32px ${SANS}` }}>{note}</div>}
    </div>
  );
};

const Honest: React.FC = () => (
  <AbsoluteFill>
    <Backdrop tint="#2E2A12" />
    <Phone x={-420} msgs={[
      { at: 0.6, from: "bot", tone: "yellow", text: "*2003 Honda Accord: OK to negotiate, a few flags*\nThere's an NHTSA recall for this model: Air Bags." },
      { at: 2.8, from: "bot", text: "Opening offer, draft to seller:\n\"Hi! I'm interested in your 2003 Honda Accord. I noticed there's an air bag recall for this model. Would you consider *$4,100*? Thanks so much!\"", chips: ["Send", "Edit", "Stop"], tapAt: SCENES.honest[1] - SCENES.honest[0] - 0.9 },
    ]} />
    <PriceTag at={1.0} top={230} label="Asking" value="$4,800" color="#93A1B5" strike />
    <PriceTag at={3.2} top={520} label="Opening offer" value="$4,100" color={COLORS.yellow} note="Cites: airbag recall (NHTSA)" />
  </AbsoluteFill>
);

const Ceiling: React.FC = () => (
  <AbsoluteFill>
    <Backdrop />
    <Headline text="Never above your max." top={120} />
    <CodeCard file="tirekick/negotiate/policy.py" code={CEILING_CODE} mark={[5, 6]} markAt={1.6} top={330} width={1720} size={27} />
    <Chip at={2.4} top={770} left={190} text="Prices come from code" color={COLORS.brand} />
    <Chip at={3.4} top={770} left={720} text="No deposits, no addresses" color={COLORS.brand} />
    <Chip at={4.4} top={770} left={1330} text="You approve every message" color={COLORS.brand} />
  </AbsoluteFill>
);

const Deal: React.FC = () => (
  <AbsoluteFill>
    <Backdrop tint="#0F3A2E" />
    <Phone x={-420} msgs={[
      { at: 0.2, from: "bot", text: "Seller replied ($4,600). Counter-offer draft:\n\"Would you take *$4,400*?\"" },
      { at: 1.1, from: "me", text: "Send" },
      { at: 1.9, from: "bot", tone: "green", text: "*Seller agreed at $4,400.*\nMeet at a police station safe exchange zone, and get a pre-purchase inspection first." },
    ]} />
    <PriceTag at={2.3} top={300} label="Deal" value="$4,400" color="#3BE0A8" note="$400 under asking" />
  </AbsoluteFill>
);

const Stats: React.FC = () => (
  <AbsoluteFill>
    <Backdrop tint="#14213D" />
    <Headline text="In our tests" top={120} size={84} />
    <Stat at={0.8} x={110} value={6} suffix="/6" label="spoof attempts caught" sub="AI-generated test clips" color="#3BE0A8" />
    <Stat at={3.4} x={700} value={84} suffix="%" label="of the possible discount, vs 51% for a student alone" sub="60 negotiations with AI-played sellers" color="#FFC46B" />
    <Stat at={6.4} x={1290} value={96} suffix="%" label="of 200 listings are a model with an NHTSA recall" sub="Public US Cars dataset" color="#7FB0FF" />
  </AbsoluteFill>
);

const MarketplacePhone: React.FC<{ at: number }> = ({ at }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = pop(frame, at * fps, fps);
  return (
    <div style={{
      position: "absolute", left: 250, top: 150, width: 540, height: 720, borderRadius: 60, background: "#0B0D12", padding: 15,
      boxShadow: "0 40px 120px rgba(0,0,0,.55)", opacity: p, translate: `0 ${interpolate(p, [0, 1], [180, 0])}px`,
    }}>
      <div style={{ width: "100%", height: "100%", borderRadius: 46, overflow: "hidden", background: "#fff", display: "flex", flexDirection: "column", font: `400 28px ${SANS}`, color: "#050505" }}>
        <div style={{ padding: "40px 26px 14px", font: `800 38px ${SANS}`, color: "#050505", borderBottom: "1px solid #E4E6EB" }}>Marketplace</div>
        <div style={{ height: 270, background: "#DADDE1", display: "grid", placeItems: "center" }}>
          <svg width="200" height="108" viewBox="0 0 120 64" fill="#BCC0C4"><path d="M18 40l8-15c2-4 6-6 10-6h40c5 0 9 2 12 6l10 13 10 2c4 1 6 4 6 7v6c0 2-2 3-4 3h-8a11 11 0 01-22 0H40a11 11 0 01-22 0h-8c-2 0-4-1-4-3v-7c0-4 4-6 12-6zm14-1h24V24H40c-2 0-4 1-5 3zm30 0h28l-8-11c-2-3-4-4-7-4H62z"/><circle cx="29" cy="53" r="7"/><circle cx="91" cy="53" r="7"/></svg>
        </div>
        <div style={{ padding: "18px 26px" }}>
          <div style={{ font: `800 46px ${SANS}` }}>$4,800</div>
          <div style={{ font: `600 32px ${SANS}`, marginTop: 4 }}>2003 Honda Accord EX</div>
          <div style={{ color: "#65676B", font: `400 26px ${SANS}`, marginTop: 6 }}>State College, PA. 128K miles.</div>
          <div style={{ marginTop: 22, padding: "14px 0", borderRadius: 10, background: COLORS.fb, color: "#fff", textAlign: "center", font: `700 28px ${SANS}` }}>Copy link</div>
        </div>
      </div>
    </div>
  );
};

const Platforms: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const arrow = interpolate(frame, [1.5 * fps, 2.2 * fps], [0, 1], { ...clamp, easing: Easing.out(Easing.cubic) });
  return (
    <AbsoluteFill>
      <Backdrop tint="#13244A" />
      <MarketplacePhone at={0.3} />
      <div style={{ position: "absolute", left: 845, top: 470, width: 230 * arrow, height: 10, borderRadius: 5, background: "#fff" }} />
      <div style={{ position: "absolute", left: 1050, top: 455, opacity: arrow, width: 0, height: 0, borderTop: "20px solid transparent", borderBottom: "20px solid transparent", borderLeft: "34px solid #fff" }} />
      <div style={{ position: "absolute", left: 840, top: 380, width: 260, textAlign: "center", color: "#C9D6EA", font: `600 30px ${SANS}`, opacity: arrow }}>paste it</div>
      <Phone x={480} scale={0.86} enterAt={1.9} msgs={[
        { at: 2.5, from: "me", text: "2003 Honda Accord EX, 128k miles, $4,800. max 5000" },
        { at: 3.3, from: "bot", text: "*2003 Honda Accord EX*\nAsking $4,800, your max $5,000\nSimilar cars: $3,200-$4,245 (4 found)\nForward this link to the seller and I'll send them the proof challenge." },
      ]} />
      <Headline text="Find it on Marketplace. Check it in WhatsApp." top={36} size={58} />
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- audio

const Music: React.FC = () => {
  const { fps } = useVideoConfig();
  return (
    <Audio src={staticFile("sfx/music.wav")} volume={(f: number) => {
      const t = f / fps;
      const tense = (t > SCENES.trap[0] - 0.2 && t < SCENES.trap[1]) || (t > SCENES.scam[0] - 0.1 && t < SCENES.scam[1]);
      const awkward = t > lineEnd("A04") && t < lineEnd("A05") + 0.3;
      const base = awkward ? 0.0 : tense ? 0.035 : 0.11;
      return base * interpolate(t, [0, 1.5, TOTAL_S - 2, TOTAL_S], [0, 1, 1, 0], clamp);
    }} />
  );
};

const Ambience: React.FC = () => {
  const { fps } = useVideoConfig();
  return (
    <>
      {(["street", "relief"] as const).map((name) => {
        const [a, b] = SCENES[name];
        const len = Math.round((b - a) * fps);
        return (
          <Sequence key={name} name={`ambience ${name}`} from={Math.round(a * fps)} durationInFrames={len} layout="none">
            <Audio src={staticFile("sfx/street.wav")} volume={(f: number) => 0.55 * interpolate(f, [0, 8, len - 10, len], [0, 1, 1, 0], clamp)} />
          </Sequence>
        );
      })}
    </>
  );
};

const Voices: React.FC = () => {
  const { fps } = useVideoConfig();
  return (
    <>
      {Object.entries(LINE_AT).map(([id, at]) => (
        <Sequence key={id} name={`vo ${id}`} from={Math.round(at * fps)} layout="none">
          <Audio src={staticFile(`vo/${id}.wav`)} volume={1} />
        </Sequence>
      ))}
      {SFX.map(([file, at, vol], i) => (
        <Sequence key={`sfx${i}`} name={`sfx ${file}`} from={Math.round(at * fps)} layout="none">
          <Audio src={staticFile(`sfx/${file}`)} volume={vol} />
        </Sequence>
      ))}
    </>
  );
};

// ---------------------------------------------------------------- the whole story

export const Story: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps, durationInFrames } = useVideoConfig();
  const fadeOut = interpolate(frame, [durationInFrames - 0.8 * fps, durationInFrames - 1], [0, 1], { ...clamp, easing: Easing.in(Easing.quad) });
  return (
    <AbsoluteFill style={{ background: "#070B14" }}>
      <Scene name="street" fade={false}><StreetScene t0={0} variant="intro" /></Scene>
      <Scene name="trap"><Trap /></Scene>
      <Scene name="tape">
        <DashboardScene variant="tape" />
        <Headline text="Tape hides the check-engine light." at={1.4} top={90} />
      </Scene>
      <Scene name="logo"><Logo tagline="The car proves itself before anyone haggles." /></Scene>
      <Scene name="challenge"><Challenge /></Scene>
      <Scene name="verdictCode"><VerdictCode /></Scene>
      <Scene name="scam"><Scam /></Scene>
      <Scene name="relief"><StreetScene t0={SCENES.relief[0]} variant="relief" /></Scene>
      <Scene name="honest"><Honest /></Scene>
      <Scene name="ceiling"><Ceiling /></Scene>
      <Scene name="deal"><Deal /></Scene>
      <Scene name="platforms"><Platforms /></Scene>
      <Scene name="stats"><Stats /></Scene>
      <Scene name="end">
        <Logo tagline="Meta's Muse finds the car and haggles. TireKick makes the car prove itself."
          sub="Built with Meta Muse Spark, SAM 3.1 and the WhatsApp Cloud API" />
      </Scene>
      <Captions />
      <AbsoluteFill style={{ background: "#000", opacity: fadeOut, pointerEvents: "none" }} />
      <Music />
      <Ambience />
      <Voices />
    </AbsoluteFill>
  );
};

export const _unused = { TireMark, LINE_AT };
