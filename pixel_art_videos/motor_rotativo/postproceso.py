"""Postproceso del video "¿Cómo funciona un motor rotativo?".

Toma los cuadros de Blender (270x480, fondo transparente) y:
  1. pone el fondo negro y dibuja las partículas brillantes (aire, mezcla, fuego, gases, aceite);
  2. oscurece la franja de los textos;
  3. reduce todo a una paleta fija de ~40 colores (k-means) con tramado Bayer 4x4
     SOLO entre colores parecidos;
  4. escribe títulos letra por letra, frases y etiquetas en letra pixel;
  5. agranda x4 sin difuminar (1080x1920) y arma el MP4.

Uso:
  python postproceso.py --render CARPETA_RENDER --out video.mp4 [--audio audio.wav]
  python postproceso.py --render CARPETA_RENDER --preview 100,400 --preview-dir carpeta
"""
import argparse
import json
import math
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rotativo_comun as rc  # noqa: E402

F = rc.F
W, H = rc.RES_X, rc.RES_Y
NF = rc.N_FRAMES
FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "C:/Windows/Fonts/DejaVuSansMono-Bold.ttf",
    os.path.join(HERE, "DejaVuSansMono-Bold.ttf"),
]
FONT_FILE = next((p for p in FONT_PATHS if os.path.exists(p)), FONT_PATHS[0])

ORANGE = (255, 150, 40)
YELLOW = (255, 214, 60)
WHITE = (255, 255, 255)
CYAN = (90, 225, 255)


def srgb(c):
    c = np.asarray(c, float)
    return np.where(c <= 0.0031308, 12.92 * c, 1.055 * np.power(np.maximum(c, 0), 1 / 2.4) - 0.055)


# ------------------------------------------------------------------ textos
SCENES = [
    # (inicio, fin, título, color, frase)
    (160, 250, "1. MOTOR ROTATIVO", ORANGE,
     "No tiene pistones: un rotor con forma de triángulo hace todo el trabajo."),
    (256, 358, "2. ROTOR Y CARCASA", YELLOW,
     "El rotor gira dentro de una carcasa ovalada y forma 3 cámaras que cambian de tamaño."),
    (362, 442, "3. ADMISIÓN", CYAN,
     "La cámara crece y aspira aire con gasolina por la lumbrera."),
    (446, 526, "4. COMPRESIÓN", WHITE,
     "El rotor sigue girando: la cámara se achica y aprieta la mezcla."),
    (530, 610, "5. COMBUSTIÓN", ORANGE,
     "Dos bujías encienden la mezcla. La explosión empuja el rotor."),
    (614, 694, "6. ESCAPE", YELLOW,
     "La cámara se achica otra vez y saca los gases quemados."),
    (698, 802, "7. EJE EXCÉNTRICO", CYAN,
     "El rotor empuja la excéntrica: por cada vuelta del rotor, el eje da 3."),
]
INTRO = (4, 82, [("¿CÓMO FUNCIONA", WHITE), ("UN MOTOR ROTATIVO?", ORANGE)])
OUTRO = (880, NF, [("¡ASÍ FUNCIONA!", YELLOW)],
         "Cada cara del rotor hace los 4 tiempos: 3 explosiones por vuelta, sin pistones ni válvulas.")

Yc = rc.Y_CUT
YP = rc.Y_PART


def eng(u, y, v):
    return lambda f: ("engine", (u, y, v))


def eng_polar(deg, r, y):
    a = math.radians(deg)
    return eng(r * math.cos(a), y, r * math.sin(a))


def rotor_pt(ru, rv, y):
    def fn(f):
        uu, vv = rc.rotor_to_engine(f, [complex(ru, rv)])
        return ("engine", (float(uu[0]), y, float(vv[0])))
    return fn


def lobe_pt(r, y):
    def fn(f):
        (cu, cv), _ = rc.rotor_pose(f)
        a = rc.alpha(f) + math.pi / 2
        return ("engine", (cu + r * math.cos(a), y, cv + r * math.sin(a)))
    return fn


def chamber_c(y=YP):
    def fn(f):
        u, v = rc.chamber_centroid(f)
        return ("engine", (u, y, v))
    return fn


def path_frac(path, x, y):
    def fn(f):
        u, v = rc.path_point(path, x)
        return ("engine", (float(u), y, float(v)))
    return fn


IN_PATH = rc.intake_path()
EX_PATH = rc.exhaust_path()
hp = rc.housing_r(np.radians([rc.PORT_IN, rc.PORT_EX]))
PORT_IN_PT = (hp[0] * math.cos(math.radians(rc.PORT_IN)), hp[0] * math.sin(math.radians(rc.PORT_IN)))
PORT_EX_PT = (hp[1] * math.cos(math.radians(rc.PORT_EX)), hp[1] * math.sin(math.radians(rc.PORT_EX)))
PLUG_OUT = (rc.plug_tip(10)[0] + 0.75, rc.plug_tip(10)[1] + 0.12)

# (texto, inicio, fin, ancla, desplazamiento de la caja en pixeles de 270x480)
LABELS = [
    ("ADMISIÓN", 186, 250, eng(-0.4, 0.0, 3.36), (-30, -42)),
    ("ESCAPE", 194, 250, eng(-2.2, Yc + 0.6, -2.9), (-10, 46)),
    ("ALTERNADOR", 202, 250, eng(1.78, -1.9, 1.22), (34, -30)),
    ("ROTOR", 314, 358, rotor_pt(0.0, -0.45, -1.23), (-58, 64)),
    ("CARCASA", 318, 358, eng_polar(52, 1.15, Yc), (24, -34)),
    ("EJE EXCÉNTRICO", 322, 358, eng(0.0, -1.25, 0.0), (-80, -58)),
    ("BUJÍAS", 326, 358, eng(PLUG_OUT[0], Yc, PLUG_OUT[1]), (16, 44)),
    ("LUMBRERA DE ADMISIÓN", 374, 442, eng(PORT_IN_PT[0] - 0.12, Yc, PORT_IN_PT[1] + 0.08), (6, -46)),
    ("AIRE + GASOLINA", 394, 442, chamber_c(), (10, 66)),
    ("MEZCLA COMPRIMIDA", 470, 526, chamber_c(), (-60, 62)),
    ("BUJÍAS", 540, 610, eng(PLUG_OUT[0], Yc, PLUG_OUT[1]), (-20, -56)),
    ("LADO CALIENTE", 556, 610, eng(0.35, rc.Y_MIRON[0] - 0.01, -0.85), (-50, 56)),
    ("LUMBRERA DE ESCAPE", 626, 694, eng(PORT_EX_PT[0] - 0.1, Yc, PORT_EX_PT[1] - 0.06), (10, 52)),
    ("GASES QUEMADOS", 644, 694, path_frac(EX_PATH, 0.7, Yc + 0.1), (14, 36)),
    ("CORONA DEL ROTOR", 754, 802, rotor_pt(-0.29, -0.31, -1.10), (-70, 70)),
    ("PIÑÓN FIJO", 760, 802, eng(0.21, -1.10, 0.21), (36, -70)),
    ("EXCÉNTRICA", 766, 802, lobe_pt(0.3, -1.0), (30, 64)),
]


# ------------------------------------------------------------------ partículas
def make_particles():
    """Devuelve una función f -> lista de (u, y, v, color(0..1), core_px, glow_px, intensidad)."""
    rng = np.random.default_rng(7)
    N = 70
    s = rng.uniform(0.1, 0.9, N)
    r = rng.uniform(0.12, 0.88, N)
    te = np.sort(rng.uniform(F["adm"] + 6, F["adm"] + 72, N))
    gas = rng.random(N) < 0.25
    ph = rng.uniform(0, 2 * math.pi, N)
    lat = rng.uniform(-0.12, 0.12, N)
    # ruta de admisión: dentro del plenum -> tubo -> lumbrera
    plen = np.array([[0.6, 2.95], [-0.2, 2.93], [-0.95, 2.9]])
    route_in = np.vstack([plen, IN_PATH[::-1][1:], [PORT_IN_PT]])
    T_IN = 26.0
    # combustión: partículas extra
    NX = 60
    sx = rng.uniform(0.08, 0.92, NX)
    rx = rng.uniform(0.1, 0.92, NX)
    phx = rng.uniform(0, 2 * math.pi, NX)
    f_ign = F["comb"] + 6
    s_all = np.concatenate([s, sx])
    r_all = np.concatenate([r, rx])
    d_all = 0.6 * np.abs(s_all - 0.5) * 2 + 0.4 * (1 - r_all)
    t_ign = f_ign + 2 + d_all * 12
    # escape: salen en orden (las de la punta delantera primero)
    order = np.argsort(s_all + rng.uniform(0, 0.15, len(s_all)))
    tx = np.empty(len(s_all))
    tx[order] = np.linspace(F["esc"] + 6, F["esc"] + 74, len(s_all))
    route_ex = np.vstack([[PORT_EX_PT], EX_PATH, [[-2.34, -3.15], [-2.36, -3.55]]])
    T_EX = 24.0
    latx = rng.uniform(-0.12, 0.12, len(s_all))
    # aceite (escena 7)
    NO = 40
    oa = rng.uniform(0, 2 * math.pi, NO)
    orr = rng.uniform(0.385, 0.40, NO)
    ospd = rng.uniform(0.8, 1.2, NO)
    o_on = F["eje_open"] + 10

    cyan = np.array([0.35, 0.95, 1.0])
    gasc = np.array([0.95, 1.0, 0.45])

    def route_point(route, x):
        return rc.path_point(route, x)

    def fire_color(age):
        k = np.clip(age / 40.0, 0, 1)
        c0 = np.array([1.0, 1.0, 0.75])
        c1 = np.array([1.0, 0.58, 0.12])
        c2 = np.array([0.85, 0.22, 0.05])
        return c0 * (1 - k) ** 2 + c1 * 2 * k * (1 - k) + c2 * k * k

    def at(f):
        out = []
        f = float(f)
        # ---- mezcla y fuego (cámara que seguimos)
        if F["adm"] - 30 <= f < F["esc"] + 110:
            for i in range(N + NX):
                is_main = i < N
                if not is_main and f < t_ign[i]:
                    continue
                # posición en la cámara con un vaivén suave
                si = s_all[i] + 0.015 * math.sin(f * 0.21 + (ph[i] if is_main else phx[i - N]))
                ri = np.clip(r_all[i] + 0.04 * math.sin(f * 0.17 + 1.3 * i), 0.05, 0.95)
                if f >= t_ign[i]:
                    si += 0.012 * math.sin(f * 1.3 + i)
                    ri = np.clip(ri + 0.03 * math.sin(f * 1.1 + 2 * i), 0.05, 0.95)
                cu, cv = rc.chamber_points(f, si, ri)
                cu, cv = float(cu), float(cv)
                y = YP
                vis = 1.0
                if is_main and f < te[i]:
                    x = 1.0 - (te[i] - f) / T_IN
                    if x < 0:
                        continue
                    pu, pv = route_point(route_in, x)
                    # desplazamiento lateral dentro del tubo
                    pu, pv = float(pu), float(pv)
                    cu, cv, y = pu + lat[i] * 0.6, pv + lat[i] * 0.6, Yc + 0.1
                elif is_main and f < te[i] + 10:
                    k = (f - te[i]) / 10.0
                    k = k * k * (3 - 2 * k)
                    cu = PORT_IN_PT[0] * (1 - k) + cu * k
                    cv = PORT_IN_PT[1] * (1 - k) + cv * k
                # escape
                if f >= tx[i]:
                    dt = f - tx[i]
                    if dt < 8:
                        k = dt / 8.0
                        cu = cu * (1 - k) + PORT_EX_PT[0] * k
                        cv = cv * (1 - k) + PORT_EX_PT[1] * k
                    else:
                        x = (dt - 8) / T_EX
                        if x > 1.0:
                            continue
                        x = x ** 1.3
                        pu, pv = route_point(route_ex, x)
                        cu, cv, y = float(pu) + latx[i] * 0.5, float(pv) + latx[i] * 0.5, Yc + 0.1
                        vis = 1.0 - max(0.0, (x - 0.75) / 0.25)
                # color
                if f >= t_ign[i]:
                    age = f - t_ign[i]
                    col = fire_color(age)
                    if f >= tx[i]:
                        k = min(1.0, (f - tx[i]) / 30.0)
                        col = col * (1 - k) + np.array([0.5, 0.42, 0.38]) * k
                    flick = 0.8 + 0.2 * math.sin(f * 2.3 + i * 1.7)
                    core = 3 if (age < 14 and i % 3 == 0) else 2
                    glow = 4 if age < 30 else 3
                    out.append((cu, y, cv, col, core, glow, vis * flick))
                else:
                    base = gasc if (is_main and gas[i]) else cyan
                    if f > F["comp"]:
                        k = min(1.0, (f - F["comp"]) / 84.0)
                        base = base * (1 - 0.35 * k) + np.array([1.0, 1.0, 1.0]) * 0.35 * k
                    out.append((cu, y, cv, base, 2, 3, vis * 0.95))
        # ---- chispa de las bujías
        for j, pa in enumerate(rc.PLUG_ANGLES):
            t0 = f_ign - 2 + j
            if t0 <= f < t0 + 6:
                tu, tv = rc.plug_tip(pa)
                a = math.radians(pa)
                k = 1.0 if int(f) % 2 == 0 else 0.6
                out.append((tu - 0.05 * math.cos(a), Yc - 0.02, tv - 0.05 * math.sin(a),
                            np.array([0.85, 0.95, 1.0]), 3, 7, k))
        # ---- aceite alrededor de la excéntrica
        if o_on <= f < F["out"]:
            (cu, cv), _ = rc.rotor_pose(f)
            a_now = rc.alpha(f)
            fade = min(1.0, (f - o_on) / 8.0)
            for i in range(NO):
                ang = oa[i] + a_now * ospd[i] + 0.3 * math.sin(f * 0.2 + i)
                out.append((cu + orr[i] * math.cos(ang), -1.03, cv + orr[i] * math.sin(ang),
                            np.array([1.0, 0.82, 0.12]), 2, 3, fade))
        return out
    return at


PARTICLES = make_particles()


# ------------------------------------------------------------------ proyección
class Cam:
    def __init__(self, path):
        with open(path) as fh:
            d = json.load(fh)
        self.fr = d["frames"]

    def project(self, f, space, p):
        M = np.array(self.fr[f]["P_" + space])
        c = M @ np.array([p[0], p[1], p[2], 1.0])
        if c[3] <= 1e-6:
            return None
        x = (c[0] / c[3] + 1) * 0.5 * W
        y = (1 - c[1] / c[3]) * 0.5 * H
        return x, y, c[3]


def draw_particles(img, f, cam):
    """img: float32 HxWx3 (sRGB 0..1). Brillo aditivo con un pequeño resplandor."""
    parts = PARTICLES(f)
    if not parts:
        return img
    glow = np.zeros_like(img)
    cores = []
    for (u, y, v, col, core, g, inten) in parts:
        pr = cam.project(f, "engine", (u, y, v))
        if pr is None:
            continue
        x, yy, _ = pr
        if not (-6 <= x < W + 6 and -6 <= yy < H + 6):
            continue
        xi, yi = int(round(x)), int(round(yy))
        col = np.asarray(col, float)
        for dy in range(-g, g + 1):
            for dx in range(-g, g + 1):
                d2 = dx * dx + dy * dy
                if d2 > g * g + 0.5:
                    continue
                px, py = xi + dx, yi + dy
                if 0 <= px < W and 0 <= py < H:
                    glow[py, px] += col * inten * 0.75 * math.exp(-d2 / (0.45 * g * g + 0.3))
        cores.append((xi, yi, core, col, inten))
    img = 1 - (1 - img) * (1 - np.clip(glow, 0, 1))      # mezcla "pantalla"
    for xi, yi, core, col, inten in cores:
        c = np.clip(col * (0.6 + 0.6 * inten), 0, 1)
        x0, y0 = xi - (core - 1) // 2, yi - (core - 1) // 2
        img[max(y0, 0):max(min(y0 + core, H), 0), max(x0, 0):max(min(x0 + core, W), 0)] = c
        if core >= 2 and inten > 0.7 and 0 <= yi < H and 0 <= xi < W:
            img[yi, xi] = np.clip(c * 0.5 + 0.5, 0, 1)      # centro casi blanco
    return img


def chamber_glow(img, f, cam):
    """Relleno brillante de la cámara durante la explosión."""
    f_ign = F["comb"] + 6
    if not (f_ign <= f < F["esc"] + 30):
        return img
    t = f - f_ign
    if f < F["esc"]:
        a = 0.75 * math.exp(-t / 14.0) + 0.5 * (1 - t / (F["esc"] - f_ign)) + 0.05 * math.sin(f * 2.1)
    else:
        a = 0.2 * (1 - (f - F["esc"]) / 30.0)
    a = max(0.0, min(0.9, a))
    k = min(1.0, t / 30.0)
    col = np.array([1.0, 0.95, 0.55]) * (1 - k) + np.array([1.0, 0.48, 0.08]) * k
    ss = np.linspace(0, 1, 40)
    fu, fv = rc.chamber_points(f, ss, np.zeros_like(ss))
    hu, hv = rc.chamber_points(f, ss[::-1], np.ones_like(ss))
    pts = []
    for u, v in list(zip(fu, fv)) + list(zip(hu, hv)):
        pr = cam.project(f, "engine", (float(u), YP, float(v)))
        if pr is None:
            return img
        pts.append((pr[0], pr[1]))
    m = Image.new("L", (W, H), 0)
    ImageDraw.Draw(m).polygon(pts, fill=255)
    mask = np.asarray(m, np.float32)[..., None] / 255.0 * a
    return img * (1 - mask) + col * mask


# ------------------------------------------------------------------ paleta y tramado
BAYER = (np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) + 0.5) / 16.0

FIXED = [
    (0, 0, 0), (255, 255, 255), ORANGE, YELLOW, CYAN,
    tuple((srgb([0.36, 0.035, 0.02]) * 255).round()), tuple((srgb([0.95, 0.42, 0.06]) * 255).round()),
    tuple((srgb([0.92, 0.36, 0.04]) * 255).round()), tuple((srgb([0.0, 0.20, 0.25]) * 255).round()),
    tuple((srgb([0.0, 0.16, 0.21]) * 255).round()), tuple((srgb([0.55, 0.16, 0.025]) * 255).round()),
]


def kmeans_palette(samples, k_total=40, iters=25, seed=3):
    rng = np.random.default_rng(seed)
    fixed = np.array(FIXED, float) / 255.0
    k = k_total - len(fixed)
    X = samples
    # k-means++
    cent = [X[rng.integers(len(X))]]
    dmin = np.min(((X[:, None, :] - fixed[None]) ** 2).sum(-1), axis=1)
    dmin = np.minimum(dmin, ((X - cent[0]) ** 2).sum(-1))
    for _ in range(k - 1):
        p = dmin / dmin.sum()
        c = X[rng.choice(len(X), p=p)]
        cent.append(c)
        dmin = np.minimum(dmin, ((X - c) ** 2).sum(-1))
    cent = np.array(cent)
    for _ in range(iters):
        allc = np.vstack([fixed, cent])
        d = ((X[:, None, :] - allc[None]) ** 2).sum(-1)
        lab = d.argmin(1)
        for j in range(k):
            m = lab == j + len(fixed)
            if m.any():
                cent[j] = X[m].mean(0)
    return np.vstack([fixed, cent])


def denoise(img, thr=0.06, passes=2):
    """Quita el grano fino sin tocar los bordes (promedia solo con vecinos parecidos)."""
    for _ in range(passes):
        acc = img.copy()
        cnt = np.ones(img.shape[:2], np.float32)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (-1, -1), (1, -1), (-1, 1)):
            sh = np.roll(np.roll(img, dy, 0), dx, 1)
            m = np.abs(sh - img).max(-1) < thr
            acc += sh * m[..., None]
            cnt += m
        img = acc / cnt[..., None]
    return img


def quantize(img, pal, sim=0.20, perp=0.07, dead=0.18):
    """Color más cercano; tramado Bayer solo entre dos colores parecidos."""
    h, w, _ = img.shape
    X = img.reshape(-1, 3)
    d = ((X[:, None, :] - pal[None]) ** 2).sum(-1)
    idx = np.argsort(d, axis=1)[:, :2]
    c1 = pal[idx[:, 0]]
    c2 = pal[idx[:, 1]]
    seg = c2 - c1
    L2 = (seg ** 2).sum(-1) + 1e-9
    t = ((X - c1) * seg).sum(-1) / L2
    proj = c1 + seg * t[:, None]
    pd = np.sqrt(((X - proj) ** 2).sum(-1))
    similar = (np.sqrt(L2) < sim) & (pd < perp)
    tt = np.clip((t - dead) / (0.5 - dead) * 0.5, 0, 0.5)
    yy, xx = np.mgrid[0:h, 0:w]
    thr = BAYER[yy % 4, xx % 4].reshape(-1)
    use2 = similar & (tt > thr)
    out = np.where(use2[:, None], c2, c1)
    return out.reshape(h, w, 3)


# ------------------------------------------------------------------ textos
_FONTS = {}


def font(sz):
    if sz not in _FONTS:
        _FONTS[sz] = ImageFont.truetype(FONT_FILE, sz)
    return _FONTS[sz]


def wrap(text, fnt, maxw):
    words = text.split()
    lines, cur = [], ""
    for w_ in words:
        t = (cur + " " + w_).strip()
        if fnt.getlength(t) <= maxw:
            cur = t
        else:
            lines.append(cur)
            cur = w_
    if cur:
        lines.append(cur)
    return lines


def text_layout(f):
    """Qué textos van en este cuadro. Devuelve (alto_de_la_franja, dibujar(draw))."""
    items = []
    if INTRO[0] <= f < INTRO[1]:
        y = 30
        n_typed = (f - INTRO[0]) // 2 + 1
        total = 0
        for line, col in INTRO[2]:
            fn = font(16)
            vis = line[:max(0, min(len(line), n_typed - total))]
            total += len(line)
            items.append(("text", (W - fn.getlength(line)) / 2, y, vis, fn, col))
            y += 22
        items.append(("bar", W / 2 - 50, y + 2, 100 * min(1.0, n_typed / total), ORANGE))
        return y + 12, items, 22
    if OUTRO[0] <= f < OUTRO[1]:
        y = 22
        n_typed = (f - OUTRO[0]) // 2 + 1
        fn = font(16)
        line, col = OUTRO[2][0]
        items.append(("text", (W - fn.getlength(line)) / 2, y, line[:n_typed], fn, col))
        y += 22
        items.append(("bar", W / 2 - 50, y, 100 * min(1.0, n_typed / len(line)), col))
        y += 8
        if n_typed > len(line):
            fn2 = font(10)
            for ln in wrap(OUTRO[3], fn2, W - 20):
                items.append(("text", (W - fn2.getlength(ln)) / 2, y, ln, fn2, WHITE))
                y += 13
        return y + 4, items, 12
    for (a, b, title, col, phrase) in SCENES:
        if a <= f < b:
            y = 10
            fn = font(12)
            n_typed = (f - a) // 2 + 1
            items.append(("text", 8, y, title[:n_typed], fn, col))
            y += 16
            items.append(("bar", 8, y, fn.getlength(title[:n_typed]), col))
            y += 6
            fn2 = font(10)
            done = n_typed >= len(title)
            n_ph = 0 if not done else (f - a - 2 * len(title)) * 4
            for ln in wrap(phrase, fn2, W - 16):
                vis = ln[:max(0, min(len(ln), n_ph))]
                n_ph -= len(ln)
                items.append(("text", 8, y, vis, fn2, WHITE))
                y += 13
            return y + 3, items, 4
    return 0, [], 0


def draw_texts(img_u8, items):
    im = Image.fromarray(img_u8)
    dr = ImageDraw.Draw(im)
    dr.fontmode = "1"
    for it in items:
        if it[0] == "text":
            _, x, y, s, fn, col = it
            if s:
                dr.text((int(x), int(y)), s, font=fn, fill=col)
        elif it[0] == "bar":
            _, x, y, wbar, col = it
            if wbar >= 1:
                dr.rectangle([int(x), int(y), int(x + wbar - 1), int(y + 1)], fill=col)
    return np.array(im)


def draw_labels(img2, f, cam, band_bottom):
    """Etiquetas en la rejilla de 540x960 (caja negra, borde blanco, línea y punto)."""
    im = Image.fromarray(img2)
    dr = ImageDraw.Draw(im)
    dr.fontmode = "1"
    fn = font(12)
    S = 2
    for (txt, a, b, anchor, off) in LABELS:
        if not (a <= f < b):
            continue
        space, p = anchor(f)
        pr = cam.project(f, space, p)
        if pr is None:
            continue
        ax, ay = pr[0] * S, pr[1] * S
        if not (0 <= ax < W * S and 0 <= ay < H * S):
            continue
        age = f - a
        tw = fn.getlength(txt)
        bw, bh = int(tw) + 8, 17
        bx = ax + off[0] * S - bw / 2
        by = ay + off[1] * S - bh / 2
        bx = min(max(bx, 4), W * S - bw - 4)
        by = min(max(by, band_bottom * S + 6), H * S - bh - 6)
        bx, by = int(bx), int(by)
        # punto
        dr.rectangle([int(ax) - 3, int(ay) - 3, int(ax) + 3, int(ay) + 3], fill=(0, 0, 0))
        dr.rectangle([int(ax) - 2, int(ay) - 2, int(ax) + 2, int(ay) + 2], fill=WHITE)
        if age < 2:
            continue
        # línea hasta el borde más cercano de la caja
        cx = min(max(ax, bx), bx + bw)
        cy = min(max(ay, by), by + bh)
        k = min(1.0, (age - 1) / 3.0)
        ex, ey = ax + (cx - ax) * k, ay + (cy - ay) * k
        dr.line([(ax, ay), (ex, ey)], fill=(0, 0, 0), width=4)
        dr.line([(ax, ay), (ex, ey)], fill=WHITE, width=2)
        if age < 4:
            continue
        dr.rectangle([bx, by, bx + bw, by + bh], fill=(0, 0, 0), outline=WHITE, width=2)
        dr.text((bx + 4, by + 2), txt, font=fn, fill=WHITE)
    return np.array(im)


# ------------------------------------------------------------------ cuadro completo
def load_frame(render_dir, f):
    p = os.path.join(render_dir, "cuadros", f"c_{f:04d}.png")
    im = Image.open(p).convert("RGBA")
    a = np.asarray(im, np.float32) / 255.0
    return a[..., :3] * a[..., 3:4]      # fondo negro puro


def prepared(render_dir, f, cam):
    img = denoise(load_frame(render_dir, f))
    img = chamber_glow(img, f, cam)
    img = draw_particles(img, f, cam)
    band, items, _ = text_layout(f)
    if band > 0:
        img[:band] *= 0.38                # franja negra semitransparente
    return img, band, items


def build_palette(render_dir, cam, path):
    if os.path.exists(path):
        return np.array(json.load(open(path)), float) / 255.0
    rng = np.random.default_rng(0)
    frames = list(range(0, NF, 18)) + [F["comb"] + 10, F["comb"] + 30, F["esc"] + 30, F["adm"] + 50,
                                       F["eje"] + 70]
    S = []
    for f in frames:
        if not os.path.exists(os.path.join(render_dir, "cuadros", f"c_{f:04d}.png")):
            continue
        img, _, _ = prepared(render_dir, f, cam)
        X = img.reshape(-1, 3)
        bright = X.max(1) > 0.02
        X = X[bright]
        if len(X) > 6000:
            X = X[rng.choice(len(X), 6000, replace=False)]
        S.append(X)
    S = np.vstack(S)
    pal = kmeans_palette(S)
    with open(path, "w") as fh:
        json.dump((pal * 255).round().astype(int).tolist(), fh)
    print("Paleta:", len(pal), "colores")
    return pal


def final_frame(render_dir, f, cam, pal):
    img, band, items = prepared(render_dir, f, cam)
    q = quantize(img, pal)
    q8 = (q * 255 + 0.5).astype(np.uint8)
    q8 = draw_texts(q8, items)
    big = np.repeat(np.repeat(q8, 2, 0), 2, 1)
    big = draw_labels(big, f, cam, band)
    return np.repeat(np.repeat(big, 2, 0), 2, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--render", required=True)
    ap.add_argument("--out", default=os.path.join(HERE, "motor_rotativo.mp4"))
    ap.add_argument("--audio", default=None)
    ap.add_argument("--preview", default=None)
    ap.add_argument("--preview-dir", default=None)
    ap.add_argument("--hasta", type=int, default=NF, help="solo los primeros N cuadros (avance)")
    args = ap.parse_args()
    cam = Cam(os.path.join(args.render, "camara_por_cuadro.json"))
    pal = build_palette(args.render, cam, os.path.join(args.render, "paleta.json"))
    if args.preview:
        os.makedirs(args.preview_dir, exist_ok=True)
        for tok in args.preview.split(","):
            f = int(tok)
            Image.fromarray(final_frame(args.render, f, cam, pal)).save(
                os.path.join(args.preview_dir, f"p_{f:04d}.png"))
        return
    tmp = args.out + ".sin_audio.mp4"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "1080x1920",
           "-r", str(rc.FPS), "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "16",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", tmp]
    pr = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for f in range(min(args.hasta, NF)):
        pr.stdin.write(final_frame(args.render, f, cam, pal).tobytes())
        if f % 48 == 0:
            print("cuadro", f, flush=True)
    pr.stdin.close()
    pr.wait()
    if args.audio:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", tmp, "-i", args.audio, "-c:v", "copy",
                        "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", args.out],
                       check=True)
        os.remove(tmp)
    else:
        os.replace(tmp, args.out)
    print("Video:", args.out)


if __name__ == "__main__":
    main()
