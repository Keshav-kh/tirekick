"""Generate every voice line, sound effect and the music bed for the TireKick story video.

Voices: Kokoro (open-source neural TTS, local CPU). Each line is lightly processed so it sits in a room
instead of sounding dry: high-pass, a short synthetic room reverb, and peak normalisation.
Run from the tts venv:  python tools/gen_audio.py <path-to-kokoro-dir>
"""

import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from kokoro_onnx import Kokoro

ROOT = Path(__file__).resolve().parents[1]
VO = ROOT / "public" / "vo"
SFXD = ROOT / "public" / "sfx"
VO.mkdir(parents=True, exist_ok=True)
SFXD.mkdir(parents=True, exist_ok=True)

# id, speaker, text. Order = story order. Punctuation is tuned for Kokoro's intonation.
SCRIPT = [
    ("A01", "jay", "Maya, look! A 2003 Accord... forty-eight hundred bucks. The seller says it runs great."),
    ("A02", "maya", "Oh, nice! Have you seen it in person?"),
    ("A03", "jay", "Not yet. He's out of state, so he wants a five hundred dollar deposit to hold it."),
    ("A04", "jay", "He's in the navy. On a submarine. But apparently, the Wi-Fi down there is amazing."),
    ("A05", "maya", "Jay."),
    ("B01", "maya", "That is exactly how my cousin lost his money."),
    ("C01", "maya", "And even when the car is real, one strip of tape can hide a check-engine light."),
    ("C02", "maya", "Send it through TireKick first."),
    ("D01", "narr", "TireKick. The car proves itself, before anyone haggles."),
    ("E01", "narr", "The seller gets a one-time code, and films one continuous take. The code, next to the VIN. Every warning light at key-on. Then, the engine start."),
    ("F01", "narr", "Meta's Muse Spark watches the video, and reports what it sees. Our code makes the call. The model never decides the verdict."),
    ("G01", "narr", "This seller's video had no code, a VIN that fails the check digit, and a deposit request."),
    ("H01", "jay", "Wow. Glad I didn't send that five hundred."),
    ("H02", "maya", "You almost sent five hundred bucks to a submarine."),
    ("H03", "jay", "The Wi-Fi was amazing, though."),
    ("I01", "narr", "An honest seller passes, with one flag: an airbag recall on this model. TireKick turns that into leverage."),
    ("J01", "narr", "Every price comes from code. Never above your max. Every ask cites real evidence, and you approve each message."),
    ("K01", "jay", "Forty-four hundred! That's four hundred under asking."),
    ("P01", "narr", "Find the car on Facebook Marketplace. TireKick checks it, right inside WhatsApp."),
    ("S01", "narr", "In our tests, TireKick caught all six spoof attempts. And it got eighty-four percent of the possible discount. A student on their own got fifty-one."),
    ("Z01", "narr", "Meta's Muse finds the car, and haggles. TireKick makes the car prove itself."),
]
VOICES = {"jay": ("am_michael", 1.0), "maya": ("af_heart", 0.98), "narr": ("bf_emma", 1.0)}
ROOM = {"jay": 0.13, "maya": 0.13, "narr": 0.05}  # reverb wet level: dialogue sits in the scene, narrator stays close

rng = np.random.default_rng(42)


def onepole_hp(x, sr, fc=80.0):
    a = np.exp(-2 * np.pi * fc / sr)
    y = np.empty_like(x)
    prev_x = prev_y = 0.0
    for i, v in enumerate(x):
        prev_y = a * (prev_y + v - prev_x)
        prev_x = v
        y[i] = prev_y
    return y


def room_ir(sr, decay=0.32):
    n = int(decay * sr)
    t = np.arange(n) / sr
    ir = rng.standard_normal(n) * np.exp(-t / (decay / 5.5))
    # a few early reflections
    for d, g in ((0.011, 0.6), (0.019, 0.45), (0.027, 0.35), (0.041, 0.25)):
        ir[int(d * sr)] += g
    # darken the tail (one-pole low-pass)
    out = np.empty_like(ir)
    acc = 0.0
    for i, v in enumerate(ir):
        acc += 0.25 * (v - acc)
        out[i] = acc
    return out / np.max(np.abs(out))


def convolve(x, ir):
    n = len(x) + len(ir) - 1
    size = 1 << (n - 1).bit_length()
    return np.fft.irfft(np.fft.rfft(x, size) * np.fft.rfft(ir, size), size)[:n]


def make_voices(kdir: Path):
    k = Kokoro(str(kdir / "kokoro-v1.0.onnx"), str(kdir / "voices-v1.0.bin"))
    out = {}
    ir_cache = {}
    for lid, who, text in SCRIPT:
        voice, speed = VOICES[who]
        s, sr = k.create(text, voice=voice, speed=speed, lang="en-gb" if voice.startswith("b") else "en-us")
        s = np.asarray(s, dtype=np.float64)
        idx = np.where(np.abs(s) > 0.01)[0]
        s = s[max(0, idx[0] - int(0.04 * sr)): idx[-1] + int(0.12 * sr)]
        s = onepole_hp(s, sr)
        if sr not in ir_cache:
            ir_cache[sr] = room_ir(sr)
        wet = convolve(s, ir_cache[sr])[: len(s) + int(0.25 * sr)]
        dry = np.concatenate([s, np.zeros(len(wet) - len(s))])
        mix = dry + ROOM[who] * wet / (np.max(np.abs(wet)) + 1e-9) * np.max(np.abs(dry))
        mix = mix / (np.max(np.abs(mix)) + 1e-9) * 0.89
        sf.write(VO / f"{lid}.wav", mix.astype(np.float32), sr)
        out[lid] = {"who": who, "text": text, "sec": round(len(s) / sr, 3)}  # speech length (tail excluded)
        print(lid, who, out[lid]["sec"])
    (ROOT / "src" / "lines.json").write_text(json.dumps(out, indent=1))


# ---------------------------------------------------------------- sound effects (synthesised, no licensing issues)

SR = 44100


def t(sec):
    return np.arange(int(sec * SR)) / SR


def env(n, a=0.005, r=0.2):
    e = np.ones(n)
    ai, ri = int(a * SR), int(r * SR)
    if ai:
        e[:ai] = np.linspace(0, 1, ai)
    if ri:
        e[-ri:] *= np.linspace(1, 0, ri) ** 2
    return e


def lp(x, a):
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):
        acc += a * (v - acc)
        y[i] = acc
    return y


def save(name, x, peak=0.8):
    x = x / (np.max(np.abs(x)) + 1e-9) * peak
    sf.write(SFXD / name, x.astype(np.float32), SR)


def make_sfx():
    n = int(0.7 * SR)
    noise = rng.standard_normal(n)
    cut = np.linspace(0.02, 0.35, n) ** 1.5
    y = np.empty(n)
    acc = 0.0
    for i in range(n):
        acc += cut[i] * (noise[i] - acc)
        y[i] = acc
    save("whoosh.wav", y * np.sin(np.linspace(0, np.pi, n)) ** 2, 0.6)
    tt = t(0.09)
    f = np.linspace(1400, 700, len(tt))
    save("pop.wav", np.sin(2 * np.pi * np.cumsum(f) / SR) * env(len(tt), 0.002, 0.06), 0.5)
    tt = t(0.04)
    save("tap.wav", rng.standard_normal(len(tt)) * np.exp(-tt * 120) + 0.6 * np.sin(2 * np.pi * 2200 * tt) * np.exp(-tt * 90), 0.45)
    seg = []
    for _ in range(3):
        for fq in (880, 660):
            tt = t(0.16)
            seg.append(np.sign(np.sin(2 * np.pi * fq * tt)) * 0.5 * env(len(tt), 0.004, 0.03))
    save("alarm.wav", lp(np.concatenate(seg), 0.35), 0.55)
    tt = t(1.4)
    f = np.linspace(110, 45, len(tt))
    save("sting.wav", np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * 2.2) + 0.4 * lp(rng.standard_normal(len(tt)), 0.08) * np.exp(-tt * 6), 0.85)
    tt = t(0.45)
    b = np.sign(np.sin(2 * np.pi * 110 * tt)) + 0.5 * np.sign(np.sin(2 * np.pi * 116 * tt))
    save("buzz.wav", lp(b, 0.2) * env(len(tt), 0.005, 0.1), 0.5)
    out = np.zeros(int(1.4 * SR))
    for i, fq in enumerate((1046.5, 1318.5, 1568.0, 2093.0)):
        s = int(i * 0.09 * SR)
        tt = t(1.4)[: len(out) - s]
        out[s:] += (np.sin(2 * np.pi * fq * tt) + 0.3 * np.sin(2 * np.pi * 2 * fq * tt)) * np.exp(-tt * 3.5)
    save("chime.wav", out, 0.5)
    tt = t(1.0)
    c = sum(a * np.sin(2 * np.pi * fq * tt) * np.exp(-tt * d) for fq, a, d in ((2489, 1, 5), (3729, 0.7, 7), (5274, 0.5, 9), (1661, 0.4, 4)))
    save("cash.wav", c * env(len(tt), 0.001, 0.05), 0.5)
    tt = t(0.35)
    rip = rng.standard_normal(len(tt)) * (0.5 + 0.5 * np.sign(np.sin(2 * np.pi * 38 * tt))) * np.exp(-tt * 4)
    save("tape.wav", lp(rip, 0.5), 0.5)

    # crickets: the awkward-silence gag (3 chirp pairs)
    out = np.zeros(int(1.6 * SR))
    for k in range(3):
        for j in range(2):
            s = int((k * 0.5 + j * 0.09) * SR)
            tt = t(0.06)
            chirp = np.sin(2 * np.pi * 4300 * tt) * np.sin(np.pi * tt / 0.06) * (0.5 + 0.5 * np.sign(np.sin(2 * np.pi * 120 * tt)))
            out[s: s + len(chirp)] += chirp
    save("crickets.wav", out, 0.35)

    # sad trombone: "wah wah wah waaah" (descending, with vibrato on the last note)
    notes = [(311.1, 0.38), (293.7, 0.38), (277.2, 0.38), (261.6, 1.1)]
    parts = []
    for i, (fq, d) in enumerate(notes):
        tt = t(d)
        vib = 1 + (0.012 * np.sin(2 * np.pi * 5.5 * tt) if i == 3 else 0)
        ph = 2 * np.pi * np.cumsum(fq * vib) / SR
        tone = sum((1 / h) * np.sin(h * ph) for h in range(1, 8))
        wah = 0.35 + 0.65 * np.clip(np.sin(np.pi * tt / d) * 1.6, 0, 1)
        parts.append(lp(tone * wah * env(len(tt), 0.03, 0.08), 0.18))
    save("trombone.wav", np.concatenate(parts), 0.6)

    # street ambience: distant traffic rumble + occasional passing car, loops for outdoor scenes
    dur = 24
    tt = t(dur)
    brown = np.cumsum(rng.standard_normal(len(tt)))
    brown = brown - lp(brown, 0.0005)
    amb = lp(brown, 0.02) * 0.6
    for start in (3.0, 11.5, 18.0):
        s = int(start * SR)
        n = int(4.0 * SR)
        swell = np.sin(np.linspace(0, np.pi, n)) ** 3
        car = lp(rng.standard_normal(n), 0.06) * swell
        amb[s: s + n] += car * 2.2
    save("street.wav", amb, 0.4)

    # music bed: soft pad progression + gentle pulse, 120 s, 100 bpm
    dur = 120
    tt = t(dur)
    bed = np.zeros(len(tt))
    chords = [(57, 60, 64), (53, 57, 60), (48, 52, 55, 60), (55, 59, 62)]
    bar = 60 / 100 * 4
    for ci in range(int(dur / bar) + 1):
        s = int(ci * bar * SR)
        e = min(len(tt), int((ci + 1) * bar * SR))
        if s >= len(tt):
            break
        st = np.arange(e - s) / SR
        for m in chords[ci % 4]:
            fq = 440 * 2 ** ((m - 69) / 12)
            bed[s:e] += (np.sin(2 * np.pi * fq * st) + 0.25 * np.sin(2 * np.pi * fq * 2.003 * st)) * np.minimum(1, st / 0.6) * np.minimum(1, (len(st) / SR - st) / 0.4)
    beat = 60 / 100
    for k in range(int(dur / beat)):
        s = int(k * beat * SR)
        n = int(0.25 * SR)
        if s + n > len(tt):
            break
        kt = np.arange(n) / SR
        bed[s: s + n] += 1.2 * np.sin(2 * np.pi * np.linspace(90, 45, n).cumsum() / SR) * np.exp(-kt * 14)
    bed = lp(bed, 0.25)
    fade = np.ones(len(tt))
    fade[: 2 * SR] = np.linspace(0, 1, 2 * SR)
    save("music.wav", bed * fade, 0.5)


if __name__ == "__main__":
    make_voices(Path(sys.argv[1]))
    make_sfx()
    print("audio done")
