// The whole story's timing is computed from the voice lines, so re-generating audio re-times the video.
import lines from "./lines.json";

export const FPS = 30;
export type Who = "jay" | "maya" | "narr";
export const LINES = lines as Record<string, { who: Who; text: string; sec: number }>;

type Beat = { line: string; gap?: number };            // gap = silence before this line (s)
type ScenePlan = { name: string; lead: number; beats: Beat[]; tail: number; min?: number };

// lead = seconds of picture before the first line; tail = seconds after the last line.
const PLAN: ScenePlan[] = [
  { name: "street", lead: 0.8, beats: [{ line: "A01" }, { line: "A02", gap: 0.3 }, { line: "A03", gap: 0.3 }, { line: "A04", gap: 0.35 }, { line: "A05", gap: 1.25 }], tail: 0.45 },
  { name: "trap", lead: 1.7, beats: [{ line: "B01" }], tail: 0.6 },
  { name: "tape", lead: 0.3, beats: [{ line: "C01" }, { line: "C02", gap: 0.45 }], tail: 0.35 },
  { name: "logo", lead: 0.5, beats: [{ line: "D01" }], tail: 0.6 },
  { name: "challenge", lead: 0.3, beats: [{ line: "E01" }], tail: 0.5, min: 9.6 },
  { name: "verdictCode", lead: 0.2, beats: [{ line: "F01" }], tail: 0.5 },
  { name: "scam", lead: 0.3, beats: [{ line: "G01" }], tail: 3.7 },
  { name: "relief", lead: 0.25, beats: [{ line: "H01" }, { line: "H02", gap: 0.3 }, { line: "H03", gap: 0.5 }], tail: 0.6 },
  { name: "honest", lead: 0.3, beats: [{ line: "I01" }], tail: 0.4 },
  { name: "ceiling", lead: 0.2, beats: [{ line: "J01" }], tail: 0.3 },
  { name: "deal", lead: 2.4, beats: [{ line: "K01" }], tail: 0.5 },
  { name: "platforms", lead: 0.4, beats: [{ line: "P01" }], tail: 0.9 },
  { name: "stats", lead: 0.2, beats: [{ line: "S01" }], tail: 0.6 },
  { name: "end", lead: 0.3, beats: [{ line: "Z01" }], tail: 2.4 },
];

export const LINE_AT: Record<string, number> = {};
export const SCENES: Record<string, [number, number]> = {};
let cursor = 0;
for (const sc of PLAN) {
  const start = cursor;
  let t = start + sc.lead;
  sc.beats.forEach((b, i) => {
    if (i > 0) t += b.gap ?? 0.3;
    LINE_AT[b.line] = t;
    t += LINES[b.line].sec;
  });
  const end = Math.max(t + sc.tail, start + (sc.min ?? 0));
  SCENES[sc.name] = [start, end];
  cursor = end;
}
export const TOTAL_S = Math.ceil(cursor * 10) / 10;

// Sound effects, scene-relative: [scene, seconds into scene, file, volume]
const SFX_REL: [string, number, string, number][] = [
  ["street", -1, "crickets.wav", 0.55],           // -1: placed right after A04 (see below)
  ["trap", 0, "sting.wav", 0.9], ["trap", 0.4, "pop.wav", 0.7], ["trap", 1.0, "pop.wav", 0.6], ["trap", 1.4, "buzz.wav", 0.5], ["trap", 1.9, "buzz.wav", 0.5],
  ["tape", 1.2, "tape.wav", 0.8],
  ["logo", -0.1, "whoosh.wav", 0.7],
  ["challenge", 0, "whoosh.wav", 0.5], ["challenge", 0.9, "pop.wav", 0.5], ["challenge", 5.8, "whoosh.wav", 0.4],
  ["verdictCode", 0, "whoosh.wav", 0.4],
  ["scam", 0.2, "alarm.wav", 0.55], ["scam", 0.8, "pop.wav", 0.5], ["scam", 2.0, "pop.wav", 0.5], ["scam", 3.2, "pop.wav", 0.5], ["scam", 4.4, "pop.wav", 0.5],
  ["scam", -3.1, "pop.wav", 0.7], ["scam", -2.6, "trombone.wav", 0.6],   // negative = seconds before the scene ends
  ["honest", 0.6, "pop.wav", 0.5], ["honest", 2.8, "pop.wav", 0.5], ["honest", -0.9, "tap.wav", 0.8],
  ["ceiling", 0, "whoosh.wav", 0.4],
  ["deal", 0.2, "pop.wav", 0.6], ["deal", 1.1, "pop.wav", 0.6], ["deal", 1.9, "pop.wav", 0.6], ["deal", 2.3, "cash.wav", 0.8],
  ["platforms", 0, "whoosh.wav", 0.45], ["platforms", 2.5, "pop.wav", 0.5], ["platforms", 3.3, "pop.wav", 0.5],
  ["stats", 0, "whoosh.wav", 0.4], ["stats", 0.8, "pop.wav", 0.5], ["stats", 3.4, "pop.wav", 0.5], ["stats", 6.4, "pop.wav", 0.5],
  ["end", 0, "chime.wav", 0.6],
];
export const SFX: [string, number, number][] = SFX_REL.map(([scene, off, file, vol]) => {
  const [a, b] = SCENES[scene];
  let at = off >= 0 ? a + off : b + off;
  if (file === "crickets.wav") at = LINE_AT.A04 + LINES.A04.sec + 0.1;
  if (scene === "logo") at = a + off;
  return [file, Math.max(0, at), vol];
});

export const COLORS = {
  brand: "#00A884",
  red: "#EA0038",
  yellow: "#F5A623",
  fb: "#0866FF",
};

export const lineEnd = (id: string) => LINE_AT[id] + LINES[id].sec;
/** Seconds into `scene` at which `line` starts. */
export const rel = (scene: string, line: string) => LINE_AT[line] - SCENES[scene][0];
