# TireKick story video (source)

A ~2-minute 3D animated skit, built as code with [Remotion](https://www.remotion.dev) (React + Three.js).
Two friends, a too-good deal, a scammer on a "submarine", and how TireKick makes the car prove itself.
Every product moment on screen is real TireKick output from our live runs, and every code card is real
code from this repo. The rendered MP4 is not committed (videos stay out of git).

## Story

| Scene | What happens |
|---|---|
| street | Jay found a 2003 Accord for $4,800. The seller wants a $500 deposit: he's "in the navy, on a submarine, but the Wi-Fi down there is amazing". Crickets. Snap zoom on Maya: "Jay." |
| trap | The seller's messages; red flags stamp on. |
| tape | A strip of tape ("nothing to see here :)") hides the check-engine light. |
| logo | TireKick. |
| challenge | One-time code card next to the windshield VIN, then every dashboard light sweeps on. |
| verdictCode | `compute_verdict` from `tirekick/models.py`: the model reports, the code decides. |
| scam | TireKick's real red verdict + the VIN check-digit code. The scammer replies "ok fine. $300 deposit?" (sad trombone). |
| relief | "You almost sent five hundred bucks to a submarine." / "The Wi-Fi was amazing, though." |
| honest / ceiling / deal | Yellow verdict (airbag recall), the real AI-drafted $4,100 offer, the buyer-ceiling check from `policy.py`, the deal at $4,400. |
| platforms | Find it on Facebook Marketplace, check it in WhatsApp. |
| stats / end | Eval results with their caveats, then the tagline. |

Timing is computed from the voice lines (`src/timeline.ts`), so editing a line and regenerating the
audio re-times the whole video.

## Rebuild

```bash
# 1. voices + sound effects + music (Kokoro TTS, runs locally on CPU)
python -m venv tts && . tts/bin/activate && pip install kokoro-onnx soundfile
curl -LO https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx
curl -LO https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin
python tools/gen_audio.py .        # writes public/vo, public/sfx and src/lines.json

# 2. preview and render
npm i
npx remotion studio                # live preview
npx remotion render TireKickStory out/tirekick-story.mp4 --crf=18
```

`remotion.config.ts` points Remotion at a local headless Chrome and software WebGL (`swangle`) for
the cloud container it was made in; delete those two lines on a normal laptop.
