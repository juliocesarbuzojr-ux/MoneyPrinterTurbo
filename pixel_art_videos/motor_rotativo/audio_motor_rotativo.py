"""Audio del video "¿Cómo funciona un motor rotativo?".

- Efectos reales CC0 de wyzowl/sfx-kit (carpeta ./sfx).
- Música chiptune 8-bit generada con código (120 BPM).
- Sonidos generados con código: motor rotativo, aspiración, compresión,
  chispa + explosión, pulsos del escape y engranes.
- Todo sincronizado con los cuadros del video; mezcla con compresión suave.

Uso: python audio_motor_rotativo.py [--sfx carpeta] [--out audio.wav]
"""
import argparse
import math
import os
import sys

import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, resample_poly, sosfilt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rotativo_comun as rc  # noqa: E402

SR = 48000
FPS = rc.FPS
F = rc.F
DUR = rc.N_FRAMES / FPS
N = int(DUR * SR)
RNG = np.random.default_rng(11)


def fr(f):
    return int(round(f / FPS * SR))


def load(path):
    sr, x = wavfile.read(path)
    if x.dtype == np.int16:
        x = x.astype(np.float32) / 32768.0
    elif x.dtype == np.int32:
        x = x.astype(np.float32) / 2147483648.0
    elif x.dtype == np.uint8:
        x = (x.astype(np.float32) - 128) / 128.0
    else:
        x = x.astype(np.float32)
    if x.ndim == 1:
        x = np.stack([x, x], 1)
    if sr != SR:
        x = resample_poly(x, SR, sr, axis=0)
    return x


class Mix:
    def __init__(self):
        self.bus = {k: np.zeros((N, 2), np.float32) for k in ("sfx", "music", "synth")}

    def add(self, bus, x, f, gain=1.0, pan=0.0):
        if x.ndim == 1:
            x = np.stack([x, x], 1)
        i0 = fr(f)
        if i0 >= N:
            return
        if i0 < 0:
            x = x[-i0:]
            i0 = 0
        n = min(len(x), N - i0)
        lg = gain * math.cos((pan + 1) * math.pi / 4) * math.sqrt(2)
        rg = gain * math.sin((pan + 1) * math.pi / 4) * math.sqrt(2)
        self.bus[bus][i0:i0 + n, 0] += x[:n, 0] * lg
        self.bus[bus][i0:i0 + n, 1] += x[:n, 1] * rg


def lp(x, fc, order=2):
    return sosfilt(butter(order, fc, "low", fs=SR, output="sos"), x)


def hp(x, fc, order=2):
    return sosfilt(butter(order, fc, "high", fs=SR, output="sos"), x)


def bp(x, f1, f2, order=2):
    return sosfilt(butter(order, [f1, f2], "band", fs=SR, output="sos"), x)


def env_ad(n, a, d):
    t = np.arange(n) / SR
    return np.minimum(t / max(a, 1e-4), 1.0) * np.exp(-np.maximum(t - a, 0) / max(d, 1e-4))


# ------------------------------------------------------------------ música chiptune 120 BPM
def music():
    beat = 0.5
    t = np.arange(N) / SR
    out = np.zeros(N, np.float32)
    chords = [(57, [57, 60, 64]), (53, [53, 57, 60]), (48, [48, 52, 55]), (55, [55, 59, 62])]  # Am F C G

    def hz(m):
        return 440.0 * 2 ** ((m - 69) / 12)

    n_bars = int(DUR / (4 * beat)) + 1
    for b in range(n_bars):
        root, tones = chords[b % 4]
        t0 = b * 4 * beat
        # bajo triangular en corcheas
        for k in range(8):
            s0 = t0 + k * beat / 2
            i0, i1 = int(s0 * SR), int((s0 + beat / 2 * 0.9) * SR)
            if i0 >= N:
                break
            i1 = min(i1, N)
            tt = np.arange(i1 - i0) / SR
            ph = (tt * hz(root - 24 + (12 if k in (3, 7) else 0))) % 1.0
            tri = 4 * np.abs(ph - 0.5) - 1
            out[i0:i1] += 0.32 * tri * np.minimum(1, (i1 - i0 - np.arange(i1 - i0)) / 300)
        # arpegio de onda cuadrada en semicorcheas
        pattern = tones + [tones[0] + 12, tones[2], tones[1], tones[0] + 12, tones[1] + 12]
        for k in range(16):
            s0 = t0 + k * beat / 4
            i0, i1 = int(s0 * SR), int((s0 + beat / 4 * 0.8) * SR)
            if i0 >= N:
                break
            i1 = min(i1, N)
            tt = np.arange(i1 - i0) / SR
            m = pattern[k % len(pattern)] + 12
            sq = np.sign(np.sin(2 * np.pi * hz(m) * tt)) * 0.5
            out[i0:i1] += 0.13 * sq * np.exp(-tt * 9)
        # bombo y hi-hat de ruido
        for k in range(4):
            s0 = t0 + k * beat
            i0 = int(s0 * SR)
            if i0 >= N:
                break
            if k in (0, 2):
                n = min(int(0.18 * SR), N - i0)
                tt = np.arange(n) / SR
                f_sw = 120 * np.exp(-tt * 25) + 45
                out[i0:i0 + n] += 0.55 * np.sin(2 * np.pi * np.cumsum(f_sw) / SR) * np.exp(-tt * 18)
            for h in (0, 1):
                j0 = int((s0 + h * beat / 2) * SR)
                n = min(int(0.04 * SR), N - j0)
                if n > 0:
                    nz = RNG.uniform(-1, 1, n) * np.exp(-np.arange(n) / SR * 90)
                    out[j0:j0 + n] += 0.09 * nz
    out = hp(out, 35)
    fade = np.ones(N)
    k = int(2.5 * SR)
    fade[-k:] = np.linspace(1, 0, k)
    return out * fade


# ------------------------------------------------------------------ motor rotativo
def engine():
    t = np.arange(N) / SR
    f_of = np.arange(N) / SR * FPS
    f0 = np.zeros(N)
    amp = np.zeros(N)
    for i_, (a, b, fa, fb, ga, gb) in enumerate([
        (0, 84, 66, 66, 0.25, 0.35),
        (84, 130, 62, 64, 0.5, 0.6),
        (130, 252, 64, 64, 0.85, 0.8),
        (252, 292, 64, 62, 0.8, 0.7),
        (292, 318, 62, 16, 0.7, 0.3),
        (318, 736, 16, 16, 0.3, 0.3),
        (736, 762, 16, 26, 0.3, 0.32),
        (762, 804, 26, 26, 0.32, 0.32),
        (804, 830, 26, 64, 0.32, 0.75),
        (830, 860, 60, 60, 0.7, 0.7),
        (860, 948, 60, 120, 0.85, 0.15),
    ]):
        m = (f_of >= a) & (f_of < b)
        k = (f_of[m] - a) / (b - a)
        k = k * k * (3 - 2 * k)
        f0[m] = fa + (fb - fa) * k
        amp[m] = ga + (gb - ga) * k
    # el carro pasa frente a la cámara (doppler y volumen)
    m = f_of < 84
    amp[m] *= 0.35 + 0.65 * np.exp(-((f_of[m] - 46) / 24) ** 2)
    f0[m] *= 1 + 0.05 * np.tanh((46 - f_of[m]) / 10)
    phase = 2 * np.pi * np.cumsum(f0) / SR
    saw = np.zeros(N)
    for k in range(1, 14):
        saw += np.sin(k * phase + 0.3 * k) / k
    pulse = ((1 + np.cos(phase)) / 2) ** 6
    wob = 1 + 0.25 * np.sin(phase / 3.0) + 0.15 * np.sin(phase * 0.47)    # "brap" irregular
    nz = lp(RNG.standard_normal(N), 900)
    sig = lp(saw * 0.45 * wob, 700) + 0.9 * nz * pulse * wob
    sig = lp(sig, 1400) * amp
    return hp(sig, 28).astype(np.float32)


# ------------------------------------------------------------------ explicación (sonidos generados)
def explain_sounds(mx):
    # admisión: aire que entra (ruido de banda con barrido)
    a, b = F["adm"] + 2, F["adm"] + 80
    n = fr(b) - fr(a)
    tt = np.arange(n) / n
    nz = RNG.standard_normal(n)
    sw = np.zeros(n)
    for j, (lo, hi) in enumerate([(500, 1200), (900, 2200), (1500, 3200)]):
        seg = slice(j * n // 3, (j + 1) * n // 3)
        sw[seg] = bp(nz, lo, hi)[seg]
    env = np.sin(np.pi * tt) ** 0.7 * (0.7 + 0.3 * np.sin(tt * 40))
    mx.add("synth", (sw * env * 0.5).astype(np.float32), a, 1.0, -0.4)
    # compresión: tono grave que sube (la presión aumenta)
    a, b = F["comp"] + 4, F["comb"] + 4
    n = fr(b) - fr(a)
    tt = np.arange(n) / SR
    k = tt / tt[-1]
    fsw = 70 + 110 * k ** 1.5
    tone = np.sin(2 * np.pi * np.cumsum(fsw) / SR) + 0.4 * np.sin(4 * np.pi * np.cumsum(fsw) / SR)
    tone *= (0.15 + 0.5 * k ** 2) * (1 + 0.3 * np.sin(2 * np.pi * (3 + 9 * k) * tt))
    mx.add("synth", lp(tone, 900).astype(np.float32) * 0.45, a, 1.0, 0.1)
    # chispa (bujías) y explosión
    f_ign = F["comb"] + 6
    for j in range(2):
        n = int(0.14 * SR)
        z = hp(RNG.standard_normal(n), 3000) * env_ad(n, 0.001, 0.03)
        cr = np.zeros(n)
        for _ in range(25):
            p = RNG.integers(0, n - 50)
            cr[p:p + 30] += RNG.uniform(-1, 1) * np.exp(-np.arange(30) / 6)
        mx.add("synth", ((z * 0.6 + cr * 0.5) * 0.7).astype(np.float32), f_ign - 2 + j, 1.0, 0.5)
    n = int(1.4 * SR)
    tt = np.arange(n) / SR
    fsw = 30 + 70 * np.exp(-tt * 9)
    thump = np.sin(2 * np.pi * np.cumsum(fsw) / SR) * np.exp(-tt * 3.2)
    rumble = lp(RNG.standard_normal(n), 1100) * np.exp(-tt * 4.5)
    crack = hp(RNG.standard_normal(n), 1500) * np.exp(-tt * 22)
    boom = 1.1 * thump + 0.8 * rumble + 0.35 * crack
    mx.add("synth", boom.astype(np.float32) * 0.9, f_ign, 1.0)
    # pulsos del escape
    for j in range(9):
        f = F["esc"] + 8 + j * 8
        n = int(0.22 * SR)
        tt = np.arange(n) / SR
        puff = lp(RNG.standard_normal(n), 520) * env_ad(n, 0.005, 0.07)
        puff += 0.6 * np.sin(2 * np.pi * 55 * tt) * env_ad(n, 0.003, 0.05)
        mx.add("synth", puff.astype(np.float32) * (1.1 - 0.07 * j), f, 1.0, -0.5)
    # engranes y excéntrica (escena 7)
    a, b = F["eje_open"], F["out"] + 8
    n = fr(b) - fr(a)
    tt = np.arange(n) / SR
    k = np.clip(tt / 1.0, 0, 1)
    fz = 60 + 150 * k
    ph = 2 * np.pi * np.cumsum(fz) / SR
    whir = lp(np.sign(np.sin(ph)) * 0.4 + np.sin(2 * ph) * 0.3, 1800)
    ticks = ((1 + np.cos(ph / 2)) / 2) ** 30
    sig = (whir * 0.35 + hp(RNG.standard_normal(n), 2500) * ticks * 0.6) * np.minimum(1, tt / 0.3)
    sig *= np.minimum(1, (tt[-1] - tt) / 0.4)
    mx.add("synth", sig.astype(np.float32) * 0.45, a, 1.0, 0.2)


# ------------------------------------------------------------------ efectos sincronizados
def sfx_events(mx, sfx_dir):
    S = {}

    def s(name):
        if name not in S:
            S[name] = load(os.path.join(sfx_dir, name + ".wav"))
        return S[name]

    def dur_frames(name):
        return len(s(name)) / SR * FPS

    # cambios de escena
    for f in (84, 156, 252, F["adm"], F["comp"], F["comb"], F["esc"], F["eje"], F["out"], F["end"]):
        mx.add("sfx", s("whoosh-medium-medium"), f - 3, 0.55)
    # antes de un zoom: whoosh al revés que termina justo al empezar el zoom; luego el zoom
    for fz in (92, 266, 704):
        mx.add("sfx", s("reverse-whoosh-medium-soft"), fz - dur_frames("reverse-whoosh-medium-soft"), 0.5)
        mx.add("sfx", s("move-zoom-in"), fz, 0.6)
    mx.add("sfx", s("move-zoom-in"), 160, 0.45)
    mx.add("sfx", s("move-zoom-in"), F["rotor_open"] + 8, 0.45)
    mx.add("sfx", s("move-zoom-out"), F["out"] + 2, 0.6)
    mx.add("sfx", s("move-zoom-out"), 840, 0.55)
    # se abre una carcasa: seguro + golpe metálico y luego sale volando
    for fo, fly in ((F["hood_open"], F["hood_open"] + 5), (F["rotor_open"], F["rotor_open"] + 5),
                    (F["eje_open"], F["eje_open"] + 4)):
        mx.add("sfx", s("mechanical-latch-heavy"), fo, 0.9)
        mx.add("sfx", s("cinematic-metal-big"), fo, 0.55)
        mx.add("sfx", s("whoosh-fast-medium"), fly, 0.8)
    # las piezas regresan
    for fl in (F["out"] + 12, F["out"] + 22, 856):
        mx.add("sfx", s("mechanical-latch-heavy"), fl, 0.6)
        mx.add("sfx", s("click-snap-soft"), fl + 1, 0.6)
    # título inicial y cierre
    mx.add("sfx", s("impact-deep-firm"), 6, 0.9)
    mx.add("sfx", s("boom-hit-medium"), 880, 0.85)
    mx.add("sfx", s("shimmer-medium-sparkle"), 882, 0.6)
    # teclas: una por letra del título
    import postproceso as pp
    key = s("keyboard-letter-soft")
    starts = [(pp.INTRO[0], sum(len(t) for t, _ in pp.INTRO[2]))]
    starts += [(a, len(title)) for (a, b, title, col, ph) in pp.SCENES]
    starts += [(pp.OUTRO[0], len(pp.OUTRO[2][0][0]))]
    for a, n in starts:
        for k in range(n):
            mx.add("sfx", key * RNG.uniform(0.7, 1.0), a + 2 * k, 0.5, RNG.uniform(-0.3, 0.3))
    # etiquetas
    for (txt, a, b, anchor, off) in pp.LABELS:
        mx.add("sfx", s("appear-poof"), a, 0.45)
        mx.add("sfx", s("click-snap-soft"), a + 4, 0.6)


def compress(x, thr_db=-16, ratio=3.0, win=0.012, rel=0.12):
    mono = np.sqrt((x ** 2).mean(1))
    k = max(1, int(win * SR))
    env = np.sqrt(np.convolve(mono ** 2, np.ones(k) / k, mode="same") + 1e-12)
    thr = 10 ** (thr_db / 20)
    gain = np.where(env > thr, (env / thr) ** (1 / ratio - 1), 1.0)
    a = math.exp(-1 / (rel * SR))
    sos = np.array([[1 - a, 0, 0, 1, -a, 0]])
    g = sosfilt(sos, gain)
    return x * g[:, None]


def limiter(x, ceiling=0.89):
    """Limitador de picos suave (ventana corta, sin distorsión audible)."""
    from scipy.ndimage import minimum_filter1d, uniform_filter1d
    peak = np.abs(x).max(1)
    g = np.minimum(1.0, ceiling / np.maximum(peak, 1e-9))
    g = minimum_filter1d(g, size=int(0.006 * SR))
    g = uniform_filter1d(g, size=int(0.003 * SR))
    y = x * g[:, None]
    return np.clip(y, -ceiling, ceiling)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sfx", default=os.path.join(HERE, "sfx"))
    ap.add_argument("--out", default=os.path.join(HERE, "audio_motor_rotativo.wav"))
    args = ap.parse_args()
    mx = Mix()
    m = music()
    mx.add("music", np.stack([m, m], 1).astype(np.float32), 0, 1.0)
    e = engine()
    mx.add("synth", np.stack([e, e], 1), 0, 0.42)
    explain_sounds(mx)
    sfx_events(mx, args.sfx)
    mix = mx.bus["music"] * 0.16 + mx.bus["synth"] * 0.5 + mx.bus["sfx"] * 0.75
    mix = compress(mix, thr_db=-22, ratio=3.0)
    rms = np.sqrt((mix ** 2).mean())
    mix = mix * (10 ** (-15.5 / 20) / rms)
    mix = limiter(mix, 0.89)         # picos a -1 dBFS, sin saturar
    wavfile.write(args.out, SR, (mix * 32767).astype(np.int16))
    print("Audio:", args.out, f"{len(mix) / SR:.2f}s")


if __name__ == "__main__":
    main()
