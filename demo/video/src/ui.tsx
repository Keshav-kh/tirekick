import React from "react";
import { AbsoluteFill, Easing, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { COLORS, LINES, LINE_AT, Who, lineEnd } from "./timeline";

const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const SANS = '"Inter", "Segoe UI", Helvetica, Arial, sans-serif';
const DISPLAY = '"Inter Display", "Inter", sans-serif';
const MONO = '"DejaVu Sans Mono", monospace';

export const pop = (frame: number, at: number, fps: number) =>
  spring({ frame: frame - at, fps, config: { damping: 14, stiffness: 180, mass: 0.6 } });

// ---------------------------------------------------------------- captions (who is speaking, what they say)

const WHO_LABEL: Record<Who, [string, string]> = { jay: ["Jay", "#7FB0FF"], maya: ["Maya", "#FFC46B"], narr: ["", "#FFFFFF"] };

const ON_SCREEN = new Set(["D01", "Z01"]);

export const Captions: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const id = Object.keys(LINE_AT).find((k) => !ON_SCREEN.has(k) && t >= LINE_AT[k] && t <= lineEnd(k) + 0.15);
  if (!id) return null;
  const { who, text } = LINES[id];
  const local = (t - LINE_AT[id]) * fps;
  const appear = interpolate(local, [0, 5], [0, 1], clamp);
  const [name, color] = WHO_LABEL[who];
  return (
    <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "center", paddingBottom: 70, pointerEvents: "none" }}>
      <div style={{
        maxWidth: 1400, padding: "18px 30px", borderRadius: 18, background: "rgba(8, 11, 20, 0.72)",
        color: "#fff", font: `500 40px/1.3 ${SANS}`, textAlign: "center", opacity: appear,
        translate: `0 ${interpolate(appear, [0, 1], [12, 0])}px`,
      }}>
        {name ? <span style={{ color, fontWeight: 800, marginRight: 14 }}>{name}</span> : null}
        {text}
      </div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- big headline

export const Headline: React.FC<{ text: string; at?: number; color?: string; top?: number; size?: number; align?: "left" | "center"; left?: number }> = ({
  text, at = 0, color = "#fff", top = 90, size = 92, align = "center", left = 110,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = pop(frame, at * fps, fps);
  return (
    <div style={{
      position: "absolute", top, left, right: 110, textAlign: align, color,
      font: `800 ${size}px/1.05 ${DISPLAY}`, letterSpacing: "-0.02em", opacity: p,
      translate: `0 ${interpolate(p, [0, 1], [30, 0])}px`, textShadow: "0 6px 30px rgba(0,0,0,.45)",
    }}>{text}</div>
  );
};

// ---------------------------------------------------------------- logo

export const TireMark: React.FC<{ size: number; color?: string; stroke?: string }> = ({ size, color = COLORS.brand, stroke = "#fff" }) => (
  <div style={{ width: size, height: size, borderRadius: "50%", background: color, display: "grid", placeItems: "center" }}>
    <svg width={size * 0.62} height={size * 0.62} viewBox="0 0 24 24" fill="none" stroke={stroke} strokeWidth={2.2}>
      <circle cx="12" cy="12" r="9" /><circle cx="12" cy="12" r="3.2" /><path d="M12 3v5.8M12 15.2V21M3 12h5.8M15.2 12H21" />
    </svg>
  </div>
);

export const Logo: React.FC<{ tagline?: string; sub?: string }> = ({ tagline, sub }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = pop(frame, 0, fps);
  const t = pop(frame, 0.35 * fps, fps);
  const spin = interpolate(frame, [0, 1.2 * fps], [-180, 0], { ...clamp, easing: Easing.out(Easing.cubic) });
  return (
    <AbsoluteFill style={{ background: "radial-gradient(ellipse at 50% 45%, #10302B 0%, #070B14 70%)", justifyContent: "center", alignItems: "center" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 36, scale: String(interpolate(p, [0, 1], [0.7, 1])), opacity: p }}>
        <div style={{ rotate: `${spin}deg` }}><TireMark size={170} /></div>
        <div style={{ color: "#fff", font: `800 170px/1 ${DISPLAY}`, letterSpacing: "-0.035em" }}>TireKick</div>
      </div>
      {tagline && <div style={{ marginTop: 40, color: "#CFE9E2", font: `500 52px/1.2 ${SANS}`, opacity: t, translate: `0 ${interpolate(t, [0, 1], [20, 0])}px` }}>{tagline}</div>}
      {sub && <div style={{ marginTop: 28, color: "#7F8EA3", font: `500 34px/1.2 ${SANS}`, opacity: t }}>{sub}</div>}
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------- WhatsApp-style phone

export type Msg = { at: number; from: "bot" | "me"; text: string; tone?: "red" | "yellow" | "green"; chips?: string[]; tapAt?: number };

export const Phone: React.FC<{ msgs: Msg[]; title?: string; x?: number; scale?: number; enterAt?: number }> = ({
  msgs, title = "TireKick", x = 0, scale = 1, enterAt = 0,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = pop(frame, enterAt * fps, fps);
  return (
    <div style={{
      position: "absolute", left: "50%", top: "45%", width: 640, height: 850,
      translate: `calc(-50% + ${x}px) calc(-50% + ${interpolate(enter, [0, 1], [220, 0])}px)`, scale: String(scale), opacity: enter,
      borderRadius: 64, background: "#0B0D12", padding: 16, boxShadow: "0 40px 120px rgba(0,0,0,.55)",
    }}>
      <div style={{ width: "100%", height: "100%", borderRadius: 50, overflow: "hidden", background: "#EFEAE2", display: "flex", flexDirection: "column" }}>
        <div style={{ background: "#008069", color: "#fff", padding: "40px 24px 16px", display: "flex", alignItems: "center", gap: 16 }}>
          <TireMark size={56} color="#fff" stroke="#00A884" />
          <div style={{ font: `700 32px/1.1 ${SANS}` }}>{title}<div style={{ font: `400 22px ${SANS}`, opacity: .85 }}>Business account</div></div>
        </div>
        <div style={{ flex: 1, padding: "22px 20px", display: "flex", flexDirection: "column", justifyContent: "flex-end", gap: 12, overflow: "hidden" }}>
          {msgs.filter((m) => frame >= m.at * fps).map((m, i) => {
            const p = pop(frame, m.at * fps, fps);
            const bar = m.tone ? { red: COLORS.red, yellow: COLORS.yellow, green: COLORS.brand }[m.tone] : null;
            const tapped = m.tapAt !== undefined && frame >= m.tapAt * fps;
            return (
              <div key={i} style={{
                alignSelf: m.from === "me" ? "flex-end" : "flex-start", maxWidth: "86%",
                background: m.from === "me" ? "#D9FDD3" : "#fff", borderRadius: 16, padding: "14px 18px",
                borderLeft: bar ? `8px solid ${bar}` : undefined, boxShadow: "0 1px 1px rgba(11,20,26,.13)",
                font: `400 31px/1.32 ${SANS}`, color: "#111B21", whiteSpace: "pre-wrap",
                scale: String(interpolate(p, [0, 1], [0.85, 1])), opacity: p, transformOrigin: m.from === "me" ? "right bottom" : "left bottom",
              }}>
                {m.text.split(/(\*[^*]+\*)/g).map((part, k) => part.startsWith("*") ? <b key={k}>{part.slice(1, -1)}</b> : <span key={k}>{part}</span>)}
                {m.chips && (
                  <div style={{ display: "flex", marginTop: 12, borderTop: "1px solid #E9EDEF" }}>
                    {m.chips.map((c, k) => (
                      <div key={c} style={{
                        flex: 1, textAlign: "center", padding: "12px 0 2px", font: `600 26px ${SANS}`, color: "#027EB5",
                        background: tapped && k === 0 ? "rgba(0,168,132,.18)" : "transparent", borderRadius: 10,
                      }}>{c}</div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------- code card (real code from the repo)

const KW = /\b(def|return|if|raise|for|in|not|and|or|else|class|import|from|True|False|None)\b/;
function highlight(line: string) {
  const parts: React.ReactNode[] = [];
  const re = /("""[^"]*"""|"[^"]*"|f"[^"]*"|#.*$|\b\d+\b|\b[A-Za-z_][A-Za-z0-9_]*\b(?=\()|\b(?:def|return|if|raise|for|in|not|and|or|else|class|True|False|None)\b|@\w+)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(line))) {
    if (m.index > last) parts.push(line.slice(last, m.index));
    const tok = m[0];
    let color = "#E6EDF3";
    if (tok.startsWith('"') || tok.startsWith('f"')) color = "#A5D6FF";
    else if (tok.startsWith("#")) color = "#8B949E";
    else if (tok.startsWith("@")) color = "#FFA657";
    else if (/^\d+$/.test(tok)) color = "#79C0FF";
    else if (KW.test(tok)) color = "#FF7B72";
    else color = "#D2A8FF";
    parts.push(<span key={m.index} style={{ color }}>{tok}</span>);
    last = m.index + tok.length;
  }
  if (last < line.length) parts.push(line.slice(last));
  return parts;
}

export const CodeCard: React.FC<{ file: string; code: string; mark?: number[]; markAt?: number; x?: number; width?: number; top?: number; size?: number }> = ({
  file, code, mark = [], markAt = 1.5, x = 0, width = 1240, top = 300, size = 34,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = pop(frame, 0.1 * fps, fps);
  const lines = code.split("\n");
  const hl = interpolate(frame, [markAt * fps, (markAt + 0.5) * fps], [0, 1], clamp);
  return (
    <div style={{
      position: "absolute", left: `calc(50% + ${x}px)`, top, width, translate: `-50% ${interpolate(enter, [0, 1], [60, 0])}px`, opacity: enter,
      background: "#0D1117", borderRadius: 22, boxShadow: "0 30px 90px rgba(0,0,0,.5)", overflow: "hidden", border: "1px solid #30363D",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "16px 24px", background: "#161B22", borderBottom: "1px solid #30363D" }}>
        {["#FF5F57", "#FEBC2E", "#28C840"].map((c) => <div key={c} style={{ width: 16, height: 16, borderRadius: 8, background: c }} />)}
        <div style={{ marginLeft: 14, color: "#8B949E", font: `500 26px ${MONO}` }}>{file}</div>
      </div>
      <div style={{ padding: "22px 0" }}>
        {lines.map((ln, i) => {
          const typed = interpolate(frame, [(0.25 + i * 0.12) * fps, (0.4 + i * 0.12) * fps], [0, 1], clamp);
          const on = mark.includes(i);
          return (
            <div key={i} style={{
              display: "flex", font: `400 ${size}px/1.55 ${MONO}`, whiteSpace: "pre", opacity: typed,
              background: on ? `rgba(0,168,132,${0.28 * hl})` : "transparent", boxShadow: on ? `inset 6px 0 0 rgba(0,168,132,${hl})` : undefined,
            }}>
              <span style={{ width: 70, textAlign: "right", paddingRight: 26, color: "#6E7681" }}>{i + 1}</span>
              <span style={{ color: "#E6EDF3" }}>{highlight(ln)}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------- stats

export const Stat: React.FC<{ at: number; value: number; suffix?: string; prefix?: string; label: string; sub?: string; color: string; x: number }> = ({
  at, value, suffix = "", prefix = "", label, sub, color, x,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = pop(frame, at * fps, fps);
  const n = Math.round(interpolate(frame, [at * fps, (at + 1.1) * fps], [0, value], { ...clamp, easing: Easing.out(Easing.cubic) }));
  return (
    <div style={{
      position: "absolute", top: 300, left: x, width: 520, padding: "44px 40px", borderRadius: 28, background: "rgba(255,255,255,.06)",
      border: `2px solid ${color}55`, opacity: p, translate: `0 ${interpolate(p, [0, 1], [50, 0])}px`,
    }}>
      <div style={{ color, font: `800 150px/1 ${DISPLAY}`, letterSpacing: "-0.04em" }}>{prefix}{n}{suffix}</div>
      <div style={{ marginTop: 22, color: "#fff", font: `600 38px/1.25 ${SANS}` }}>{label}</div>
      {sub && <div style={{ marginTop: 14, color: "#93A1B5", font: `500 28px/1.3 ${SANS}` }}>{sub}</div>}
    </div>
  );
};

export const Flag: React.FC<{ at: number; text: string; top: number; right?: number }> = ({ at, text, top, right = 140 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = pop(frame, at * fps, fps);
  return (
    <div style={{
      position: "absolute", top, right, display: "flex", alignItems: "center", gap: 18, padding: "20px 30px", borderRadius: 18,
      background: COLORS.red, color: "#fff", font: `700 40px/1.2 ${SANS}`, opacity: p, rotate: `${interpolate(p, [0, 1], [-8, -2])}deg`,
      scale: String(interpolate(p, [0, 1], [1.4, 1])), boxShadow: "0 18px 50px rgba(234,0,56,.45)",
    }}>
      <svg width="40" height="40" viewBox="0 0 24 24" fill="#fff"><path d="M5 21V4h10l1 2h4v10h-7l-1-2H7v7z" /></svg>
      {text}
    </div>
  );
};
