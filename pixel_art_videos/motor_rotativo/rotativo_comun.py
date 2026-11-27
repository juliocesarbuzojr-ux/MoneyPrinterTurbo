"""Datos compartidos del video "¿Cómo funciona un motor rotativo?".

Lo usan el script de Blender (modelos y animación) y el postproceso
(partículas y etiquetas), para que todo quede sincronizado.

Coordenadas del motor (locales): u = X (derecha), v = Z (arriba),
el eje excéntrico va a lo largo de Y y el frente del motor mira a -Y.
"""
import math

import numpy as np

FPS = 24
RES_X, RES_Y = 270, 480

# ---------------------------------------------------------------- tiempos
F = {
    "title": 0,        # puente + pregunta
    "hood": 84,        # zoom al capot
    "hood_open": 126,  # se abre el capot
    "motor": 156,      # 1. MOTOR ROTATIVO (por fuera)
    "rotor": 252,      # 2. ROTOR Y CARCASA
    "rotor_open": 292, # se abre la mitad de enfrente
    "adm": 360,        # 3. ADMISIÓN
    "comp": 444,       # 4. COMPRESIÓN
    "comb": 528,       # 5. COMBUSTIÓN
    "esc": 612,        # 6. ESCAPE
    "eje": 696,        # 7. EJE EXCÉNTRICO
    "eje_open": 736,   # se abre la cara del rotor
    "out": 804,        # la cámara sale
    "end": 876,        # cierre
    "last": 948,       # (exclusivo) 39.5 s
}
N_FRAMES = F["last"]

# ---------------------------------------------------------------- geometría
R = 1.0          # radio generador (centro del rotor -> punta)
E = 0.15         # excentricidad
ENGINE_SCALE = 1.25
ENGINE_POS = (12.5, 0.0, 4.3)   # en coordenadas del carro

# profundidades (Y local del motor, el frente es -Y)
Y_PULLEY = (-2.35, -2.05)
Y_COVER = (-1.95, -1.55)
Y_FIRON = (-1.55, -1.25)
Y_FHOUS = (-1.25, -0.45)
Y_CUT = -0.85                 # plano del corte de la carcasa
Y_MIRON = (-0.45, -0.15)
Y_RHOUS = (-0.15, 0.65)
Y_RIRON = (0.65, 0.95)
Y_RCOVER = (0.95, 1.35)
Y_RPLATE = (-1.22, -1.10)     # cara delantera del rotor (sale volando en la escena 7)
Y_RBODY = (-1.10, -0.48)
Y_GEAR = (-1.10, -1.00)
Y_LOBE = (-1.00, -0.55)
Y_PART = -0.80                # profundidad de las partículas

# superelipse exterior de la carcasa
OUT_A_U, OUT_A_V, OUT_N = 1.30, 1.55, 3.5

# lumbreras (ángulo polar en grados) y bujías
PORT_IN = 145.0
PORT_EX = 215.0
PORT_HALF = 10.0
PLUG_ANGLES = (10.0, -10.0)

GEAR_RING_R = 3 * E      # corona interna del rotor (radio primitivo)
GEAR_FIX_R = 2 * E       # piñón fijo
GEAR_RING_T = 24
GEAR_FIX_T = 16


def housing_curve(t):
    """Epitrocoide (eje mayor vertical). t en radianes -> (u, v)."""
    z = 1j * (E * np.exp(3j * t) + R * np.exp(1j * t))
    return np.real(z), np.imag(z)


def _polar_table(u, v, n=1440):
    ang = np.mod(np.arctan2(v, u), 2 * math.pi)
    rad = np.hypot(u, v)
    order = np.argsort(ang)
    ang, rad = ang[order], rad[order]
    grid = np.linspace(0, 2 * math.pi, n, endpoint=False)
    return np.interp(grid, ang, rad, period=2 * math.pi)


_TH = np.linspace(0, 2 * math.pi, 4000, endpoint=False)
_HU, _HV = housing_curve(_TH)
HOUSING_POLAR = _polar_table(_HU, _HV)


def housing_r(theta):
    """Radio de la superficie interior de la carcasa en el ángulo polar theta (rad)."""
    n = len(HOUSING_POLAR)
    x = np.mod(theta, 2 * math.pi) / (2 * math.pi) * n
    i0 = np.floor(x).astype(int) % n
    fr = x - np.floor(x)
    return HOUSING_POLAR[i0] * (1 - fr) + HOUSING_POLAR[(i0 + 1) % n] * fr


def outer_r(theta):
    c, s = np.abs(np.cos(theta)), np.abs(np.sin(theta))
    return 1.0 / ((c / OUT_A_U) ** OUT_N + (s / OUT_A_V) ** OUT_N) ** (1.0 / OUT_N)


def _rotor_envelope(n=720):
    """Perfil del rotor: envolvente interior de la carcasa vista desde el rotor."""
    ts = np.linspace(0, 2 * math.pi, 1500, endpoint=False)
    H = 1j * (E * np.exp(3j * ts) + R * np.exp(1j * ts))
    best = np.full(n, 10.0)
    for a in np.linspace(0, 6 * math.pi, 2400, endpoint=False):
        C = 1j * E * np.exp(1j * a)
        w = (H - C) * np.exp(-1j * a / 3)
        ang = np.mod(np.angle(w), 2 * math.pi)
        idx = (ang / (2 * math.pi) * n).astype(int) % n
        np.minimum.at(best, idx, np.abs(w))
    # suavizado leve
    k = np.array([1, 2, 3, 2, 1], float)
    k /= k.sum()
    pad = np.concatenate([best[-2:], best, best[:2]])
    sm = np.convolve(pad, k, mode="valid")
    return np.minimum(best, sm)


ROTOR_POLAR = _rotor_envelope()


def rotor_r(psi, clearance=0.012):
    n = len(ROTOR_POLAR)
    x = np.mod(psi, 2 * math.pi) / (2 * math.pi) * n
    i0 = np.floor(x).astype(int) % n
    fr = x - np.floor(x)
    r = ROTOR_POLAR[i0] * (1 - fr) + ROTOR_POLAR[(i0 + 1) % n] * fr
    return r - clearance


# ---------------------------------------------------------------- movimiento
def _smooth(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


FAST = -18.75                 # grados del eje por cuadro (motor en marcha)
SLOW = -270.0 / 84.0          # cámara lenta: un tiempo = 270° de eje = 90° de rotor
EJE_SPEED = -9.0


def shaft_speed(f):
    """Velocidad del eje excéntrico (grados por cuadro, negativo = horario)."""
    if f < F["rotor_open"]:
        return FAST
    if f < F["rotor_open"] + 24:
        k = _smooth((f - F["rotor_open"]) / 24)
        return FAST + (SLOW - FAST) * k
    if f < F["eje_open"] + 4:
        return SLOW
    if f < F["eje_open"] + 24:
        k = _smooth((f - F["eje_open"] - 4) / 20)
        return SLOW + (EJE_SPEED - SLOW) * k
    if f < F["out"]:
        return EJE_SPEED
    if f < F["out"] + 26:
        k = _smooth((f - F["out"]) / 26)
        return EJE_SPEED + (FAST - EJE_SPEED) * k
    return FAST


def _alpha_table():
    n = N_FRAMES + 2
    a = np.zeros(n)
    for f in range(1, n):
        a[f] = a[f - 1] + 0.5 * (shaft_speed(f - 1) + shaft_speed(f))
    a += 90.0 - a[F["adm"]]   # al empezar la admisión la cámara está al mínimo, a la izquierda
    return a


ALPHA_DEG = _alpha_table()


def alpha(f):
    """Ángulo del eje excéntrico (rad) en el cuadro f (admite fracciones)."""
    f = min(max(f, 0.0), N_FRAMES)
    i = int(math.floor(f))
    fr = f - i
    return math.radians(ALPHA_DEG[i] * (1 - fr) + ALPHA_DEG[i + 1] * fr)


def rotor_pose(f):
    """Centro del rotor (u, v) y giro del rotor phi (rad, antihorario)."""
    a = alpha(f)
    c = 1j * E * complex(math.cos(a), math.sin(a))
    return (c.real, c.imag), a / 3.0


def rotor_to_engine(f, pts):
    """Puntos en coordenadas del rotor (complejos) -> (u, v) del motor."""
    (cu, cv), phi = rotor_pose(f)
    w = np.asarray(pts) * np.exp(1j * phi) + complex(cu, cv)
    return np.real(w), np.imag(w)


# La cámara que seguimos es la de la cara entre la punta 0 (90°) y la punta 1 (210°).
def chamber_points(f, s, r):
    """Punto dentro de la cámara seguida. s: 0..1 de la punta 0 a la 1; r: 0 rotor -> 1 carcasa."""
    s = np.asarray(s, float)
    r = np.asarray(r, float)
    (cu, cv), phi = rotor_pose(f)
    psi = math.radians(90) + s * math.radians(120)
    fl = rotor_r(psi) * np.exp(1j * psi)
    flank = fl * np.exp(1j * phi) + complex(cu, cv)
    t = phi + s * (2 * math.pi / 3)
    hu, hv = housing_curve(t)
    hous = hu + 1j * hv
    p = flank + r * (hous - flank)
    return np.real(p), np.imag(p)


def chamber_centroid(f):
    s = np.linspace(0.15, 0.85, 9)
    u, v = chamber_points(f, s, np.full_like(s, 0.5))
    return float(u.mean()), float(v.mean())


def polar_pt(deg, r):
    a = math.radians(deg)
    return r * math.cos(a), r * math.sin(a)


def port_outer(deg):
    a = math.radians(deg)
    ro = float(outer_r(np.array([a]))[0])
    return ro * math.cos(a), ro * math.sin(a)


def _catmull(points, n_per=12):
    P = [np.array(p, float) for p in points]
    P = [P[0] + (P[0] - P[1])] + P + [P[-1] + (P[-1] - P[-2])]
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for k in range(n_per):
            t = k / n_per
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    out.append(P[-2])
    return np.array(out)


def intake_path():
    """Tubo de admisión en el plano del corte: de la lumbrera al plenum (u, v)."""
    pu, pv = port_outer(PORT_IN)
    d = np.array(polar_pt(PORT_IN, 1.0))
    p1 = np.array([pu, pv]) + 0.45 * d
    pts = [(pu - 0.06 * d[0], pv - 0.06 * d[1]), tuple(p1), (-2.05, 1.95), (-1.75, 2.62), (-1.15, 2.86)]
    return _catmull(pts, 10)


def exhaust_path():
    pu, pv = port_outer(PORT_EX)
    d = np.array(polar_pt(PORT_EX, 1.0))
    p1 = np.array([pu, pv]) + 0.45 * d
    pts = [(pu - 0.06 * d[0], pv - 0.06 * d[1]), tuple(p1), (-2.15, -1.55), (-2.3, -2.35), (-2.32, -2.75)]
    return _catmull(pts, 10)


def resample_path(path, n):
    seg = np.linalg.norm(np.diff(path, axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    t = np.linspace(0, s[-1], n)
    return np.stack([np.interp(t, s, path[:, 0]), np.interp(t, s, path[:, 1])], 1), s[-1]


def path_point(path, x):
    """Punto a la fracción x (0..1) de la longitud del camino."""
    seg = np.linalg.norm(np.diff(path, axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    t = np.clip(np.asarray(x, float), 0, 1) * s[-1]
    return np.interp(t, s, path[:, 0]), np.interp(t, s, path[:, 1])


def plug_tip(deg):
    a = math.radians(deg)
    r = float(housing_r(np.array([a]))[0])
    return r * math.cos(a), r * math.sin(a)


def engine_to_car(p):
    """(u, y, v) del motor -> coordenadas del carro (x adelante, z arriba)."""
    u, y, v = p
    s = ENGINE_SCALE
    return (ENGINE_POS[0] - s * y, ENGINE_POS[1] + s * u, ENGINE_POS[2] + s * v)


# ---------------------------------------------------------------- carro
CAR_SPEED = 26.0     # unidades por segundo
CAR_X0 = -60.0
CAR_Y = -9.0
CAR_GO = 860         # vuelve a arrancar al final


def car_x(f):
    stop = F["rotor"]
    if f <= stop:
        return CAR_X0 + CAR_SPEED * f / FPS
    x = CAR_X0 + CAR_SPEED * stop / FPS
    if f <= CAR_GO:
        return x
    t = (f - CAR_GO) / FPS
    # acelera de 0 a ~45 u/s
    return x + 0.5 * 28.0 * t * t if t < 1.6 else x + 0.5 * 28.0 * 1.6 ** 2 + 44.8 * (t - 1.6)
