"""¿Cómo funciona un motor rotativo?  -  escena 3D para Blender 5.3

Arma TODO: carro cruzando un puente, motor rotativo con sus piezas, materiales,
luces, cámara y animación. Luego renderiza los cuadros a 270x480 con fondo
transparente, guarda el .blend, exporta las matrices de cámara (para que el
postproceso ponga partículas y etiquetas) y mete los cuadros en un .zip.

Uso:
  blender.exe --background --factory-startup --python motor_rotativo_blender.py -- [opciones]
Opciones:
  --out CARPETA        carpeta de salida (por defecto: ./render junto al script)
  --engine EEVEE|CYCLES
  --frames 0-947       rango o lista (ej. 0,100,300-310)
  --no-render          solo arma la escena, guarda el .blend y los datos
  --gpu                usa la tarjeta de video en Cycles (CUDA/OPTIX)
  --samples N          muestras de render (por defecto 16 en Eevee)
  --reanudar           no vuelve a exportar datos ni el .blend si ya existen
"""
import json
import math
import os
import sys
import time
import zipfile

import bpy  # noqa: I001  (bpy va primero: carga bmesh y mathutils)
import bmesh
import numpy as np
from bpy_extras import anim_utils
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import rotativo_comun as rc  # noqa: E402

# ------------------------------------------------------------------ opciones
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]


def _opt(name, default=None):
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv) and not argv[i + 1].startswith("--"):
            return argv[i + 1]
        return True
    return default


OUT = os.path.abspath(_opt("--out", os.path.join(HERE, "render")))
ENGINE = str(_opt("--engine", "EEVEE")).upper()
DO_RENDER = not _opt("--no-render", False)
USE_GPU = bool(_opt("--gpu", False))
FRAMES_ARG = _opt("--frames", None)
SAMPLES = int(_opt("--samples", 0) or 0)
FRAMES_DIR = os.path.join(OUT, "cuadros")
os.makedirs(FRAMES_DIR, exist_ok=True)

NF = rc.N_FRAMES
FR = np.arange(NF, dtype=float)
F = rc.F

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.name = "MotorRotativo"

COLLS = {}
for cname in ("Carro", "Motor", "Puente", "Luces"):
    c = bpy.data.collections.new(cname)
    scene.collection.children.link(c)
    COLLS[cname] = c

OUTLINE_GROUPS = {"car": [], "engine": [], "bridge": []}
HIDE_GROUPS = {"car": [], "bridge": []}

# ------------------------------------------------------------------ materiales
MATS = {}


def _bsdf(m):
    return m.node_tree.nodes["Principled BSDF"]


def pbr(name, color, metallic=0.0, rough=0.5, coat=0.0, bump=0.04, emit=None, estr=0.0, spec=0.5):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = _bsdf(m)
    b.inputs["Base Color"].default_value = (*color, 1.0)
    b.inputs["Metallic"].default_value = metallic
    b.inputs["Roughness"].default_value = rough
    b.inputs["Specular IOR Level"].default_value = spec
    if coat:
        b.inputs["Coat Weight"].default_value = coat
        b.inputs["Coat Roughness"].default_value = 0.05
    if emit is not None:
        b.inputs["Emission Color"].default_value = (*emit, 1.0)
        b.inputs["Emission Strength"].default_value = estr
    if bump > 0:
        tc = nt.nodes.new("ShaderNodeTexCoord")
        nz = nt.nodes.new("ShaderNodeTexNoise")
        nz.inputs["Scale"].default_value = 40.0
        nz.inputs["Detail"].default_value = 2.0
        bp = nt.nodes.new("ShaderNodeBump")
        bp.inputs["Strength"].default_value = bump
        bp.inputs["Distance"].default_value = 0.02
        nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
        nt.links.new(nz.outputs["Fac"], bp.inputs["Height"])
        nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    MATS[name] = m
    return m


def flat(name, color, strength=1.0):
    """Color liso (emisión): interiores en corte, luces, pintura de carril."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color, 1.0)
    em.inputs["Strength"].default_value = strength
    nt.links.new(em.outputs[0], out.inputs["Surface"])
    MATS[name] = m
    return m


def stripes(name, c1, c2, period=0.075):
    """Cara del corte: rayas diagonales rojo oscuro / naranja."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    add = nt.nodes.new("ShaderNodeMath")
    add.operation = "ADD"
    add2 = nt.nodes.new("ShaderNodeMath")
    add2.operation = "ADD"
    div = nt.nodes.new("ShaderNodeMath")
    div.operation = "DIVIDE"
    div.inputs[1].default_value = period
    fr = nt.nodes.new("ShaderNodeMath")
    fr.operation = "FRACT"
    gt = nt.nodes.new("ShaderNodeMath")
    gt.operation = "GREATER_THAN"
    gt.inputs[1].default_value = 0.5
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs[6].default_value = (*c1, 1.0)
    mix.inputs[7].default_value = (*c2, 1.0)
    L = nt.links.new
    L(tc.outputs["Object"], sep.inputs[0])
    L(sep.outputs[0], add.inputs[0])
    L(sep.outputs[2], add.inputs[1])
    L(add.outputs[0], add2.inputs[0])
    L(sep.outputs[1], add2.inputs[1])
    L(add2.outputs[0], div.inputs[0])
    L(div.outputs[0], fr.inputs[0])
    L(fr.outputs[0], gt.inputs[0])
    L(gt.outputs[0], mix.inputs[0])
    L(mix.outputs[2], em.inputs["Color"])
    L(em.outputs[0], out.inputs["Surface"])
    MATS[name] = m
    return m


def zone_mat(name, cold, hot, deg=20.0):
    """Cara del fondo de la cámara: lado frío (cian oscuro) y lado caliente (naranja), lisos."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    a = nt.nodes.new("ShaderNodeMath")
    a.operation = "MULTIPLY"
    a.inputs[1].default_value = math.cos(math.radians(deg))
    b = nt.nodes.new("ShaderNodeMath")
    b.operation = "MULTIPLY"
    b.inputs[1].default_value = -math.sin(math.radians(deg))
    s = nt.nodes.new("ShaderNodeMath")
    s.operation = "ADD"
    gt = nt.nodes.new("ShaderNodeMath")
    gt.operation = "GREATER_THAN"
    gt.inputs[1].default_value = 0.0
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs[6].default_value = (*hot, 1.0)
    mix.inputs[7].default_value = (*cold, 1.0)
    L = nt.links.new
    L(tc.outputs["Object"], sep.inputs[0])
    L(sep.outputs[2], a.inputs[0])
    L(sep.outputs[0], b.inputs[0])
    L(a.outputs[0], s.inputs[0])
    L(b.outputs[0], s.inputs[1])
    L(s.outputs[0], gt.inputs[0])
    L(gt.outputs[0], mix.inputs[0])
    L(mix.outputs[2], em.inputs["Color"])
    L(em.outputs[0], out.inputs["Surface"])
    MATS[name] = m
    return m


def outline_material():
    m = bpy.data.materials.new("Contorno")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (0, 0, 0, 1)
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    tr2 = nt.nodes.new("ShaderNodeBsdfTransparent")
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    lp = nt.nodes.new("ShaderNodeLightPath")
    mix1 = nt.nodes.new("ShaderNodeMixShader")
    mix2 = nt.nodes.new("ShaderNodeMixShader")
    L = nt.links.new
    L(geo.outputs["Backfacing"], mix1.inputs[0])
    L(em.outputs[0], mix1.inputs[1])
    L(tr.outputs[0], mix1.inputs[2])
    L(lp.outputs["Is Shadow Ray"], mix2.inputs[0])   # Is Shadow Ray -> Transparent
    L(mix1.outputs[0], mix2.inputs[1])
    L(tr2.outputs[0], mix2.inputs[2])
    L(mix2.outputs[0], out.inputs["Surface"])
    m.use_backface_culling = True
    m.use_backface_culling_shadow = True
    MATS["Contorno"] = m
    return m


M_OUT = outline_material()
M_CHROME = pbr("Cromo", (0.92, 0.93, 0.95), metallic=1.0, rough=0.12, bump=0.03)
M_ALU = pbr("Aluminio", (0.72, 0.74, 0.78), metallic=1.0, rough=0.33, bump=0.05)
M_STEEL = pbr("AceroOscuro", (0.32, 0.34, 0.38), metallic=1.0, rough=0.38, bump=0.05)
M_ROTOR = pbr("AceroRotor", (0.74, 0.75, 0.79), metallic=0.8, rough=0.3, bump=0.04)
M_BLOCK = pbr("BloqueGrisAzul", (0.12, 0.15, 0.21), metallic=0.45, rough=0.42, bump=0.06)
M_RED = pbr("PinturaRoja", (0.78, 0.10, 0.03), rough=0.22, coat=0.6, bump=0.03)
M_ORANGE = pbr("PinturaNaranja", (0.95, 0.36, 0.04), rough=0.25, coat=0.5, bump=0.03)
M_RUBBER = pbr("Goma", (0.025, 0.025, 0.03), rough=0.75, bump=0.06)
M_YELLOW = pbr("MangoAmarillo", (1.0, 0.72, 0.04), rough=0.35, bump=0.03)
M_CERAMIC = pbr("Ceramica", (0.92, 0.91, 0.86), rough=0.3, bump=0.03)
M_BRASS = pbr("Laton", (0.92, 0.66, 0.26), metallic=1.0, rough=0.22, bump=0.03)
M_BLUE = pbr("FiltroAzul", (0.04, 0.14, 0.52), rough=0.3, coat=0.4, bump=0.03)
M_WIRE_RED = pbr("CableRojo", (0.6, 0.05, 0.04), rough=0.5, bump=0.03)
M_CAR = pbr("PinturaCarro", (0.62, 0.025, 0.02), metallic=0.25, rough=0.2, coat=1.0, bump=0.03)
M_GLASS = pbr("Vidrio", (0.015, 0.02, 0.03), rough=0.05, spec=1.0, bump=0.0)
M_HEAD = flat("Faro", (1.0, 0.93, 0.75), 3.0)
M_TAIL = flat("Calavera", (1.0, 0.05, 0.03), 2.5)
M_BAY = flat("NegroVano", (0.0, 0.0, 0.0), 1.0)
M_ASPH = pbr("Asfalto", (0.045, 0.045, 0.05), rough=0.85, bump=0.06)
M_LANE_Y = flat("RayaAmarilla", (0.9, 0.62, 0.08), 0.9)
M_LANE_W = flat("RayaBlanca", (0.8, 0.8, 0.8), 0.7)
M_CONC = pbr("Concreto", (0.28, 0.28, 0.30), rough=0.9, bump=0.06)
M_BRSTEEL = pbr("AceroPuente", (0.22, 0.26, 0.33), metallic=0.6, rough=0.45, bump=0.05)
M_LAMP = flat("Lampara", (1.0, 0.78, 0.42), 4.0)
M_STRIPE = stripes("CorteRayas", (0.36, 0.035, 0.02), (0.95, 0.42, 0.06))
M_HOT = flat("InteriorCaliente", (0.92, 0.36, 0.04), 1.0)
M_COLD = flat("InteriorFrio", (0.0, 0.20, 0.25), 1.0)
M_ZONE = zone_mat("FondoCamara", (0.0, 0.16, 0.21), (0.55, 0.16, 0.025))
M_DARK = pbr("NegroMate", (0.01, 0.01, 0.012), rough=0.6, bump=0.0)


# ------------------------------------------------------------------ mallas
def make_obj(name, verts, faces, mats, fmat=None, coll="Motor", parent=None, smooth=True,
             sharp=35.0, recalc=True, outline="engine"):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(map(float, v)) for v in verts], [], [list(map(int, f)) for f in faces])
    me.validate(clean_customdata=False)
    if recalc:
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bm.to_mesh(me)
        bm.free()
    for m in mats:
        me.materials.append(m)
    if fmat is not None:
        fm = list(fmat)
        if len(fm) == len(me.polygons):
            me.polygons.foreach_set("material_index", fm)
        else:
            print("AVISO: caras cambiaron en", name, len(fm), len(me.polygons))
    if smooth:
        me.shade_smooth()
        me.set_sharp_from_angle(angle=math.radians(sharp))
    ob = bpy.data.objects.new(name, me)
    COLLS[coll].objects.link(ob)
    if parent is not None:
        ob.parent = parent
    if outline:
        OUTLINE_GROUPS[outline].append(ob)
    return ob


def empty(name, coll, parent=None, loc=(0, 0, 0)):
    e = bpy.data.objects.new(name, None)
    COLLS[coll].objects.link(e)
    e.parent = parent
    e.location = loc
    e.empty_display_size = 0.5
    return e


def merge(parts):
    """Junta listas (verts, faces, fmat)."""
    V, Fc, M = [], [], []
    for v, f, m in parts:
        o = len(V)
        V.extend(v)
        Fc.extend([[i + o for i in face] for face in f])
        M.extend(m)
    return V, Fc, M


def xform(verts, mat):
    return [tuple(mat @ Vector(v)) for v in verts]


def axis_matrix(origin, direction, roll=0.0):
    d = Vector(direction).normalized()
    q = Vector((0, 0, 1)).rotation_difference(d)
    return Matrix.Translation(Vector(origin)) @ q.to_matrix().to_4x4() @ Matrix.Rotation(roll, 4, "Z")


def lathe(profile, n=24, mat=Matrix(), mi=0, phase=0.0):
    """Revoluciona un perfil [(r, z), ...] alrededor de Z local."""
    V, Fc = [], []
    rings = []
    for r, z in profile:
        if r < 1e-7:
            idx = len(V)
            V.append((0.0, 0.0, z))
            rings.append([idx] * n)
        else:
            ring = []
            for k in range(n):
                a = phase + 2 * math.pi * k / n
                ring.append(len(V))
                V.append((r * math.cos(a), r * math.sin(a), z))
            rings.append(ring)
    for a, b in zip(rings[:-1], rings[1:]):
        for k in range(n):
            k1 = (k + 1) % n
            face = [a[k], a[k1], b[k1], b[k]]
            uniq = []
            for i in face:
                if i not in uniq:
                    uniq.append(i)
            if len(uniq) >= 3:
                Fc.append(uniq)
    # tapas si el perfil no cierra en el eje
    if profile[0][0] > 1e-7:
        Fc.append(list(reversed(rings[0])))
    if profile[-1][0] > 1e-7:
        Fc.append(list(rings[-1]))
    return xform(V, mat), Fc, [mi] * len(Fc)


def box_data(x0, x1, y0, y1, z0, z1, mi=(0, 0, 0, 0, 0, 0)):
    """Caja; orden de caras: -X, +X, -Y, +Y, -Z, +Z."""
    V = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    Fc = [[0, 3, 7, 4], [1, 5, 6, 2], [0, 4, 5, 1], [3, 2, 6, 7], [0, 1, 2, 3], [4, 7, 6, 5]]
    if isinstance(mi, int):
        mi = (mi,) * 6
    return V, Fc, list(mi)


def box(name, x0, x1, y0, y1, z0, z1, mats, coll, parent=None, bevel=0.0, seg=2, fmi=0,
        outline="engine"):
    V, Fc, M = box_data(x0, x1, y0, y1, z0, z1, fmi)
    ob = make_obj(name, V, Fc, mats, M, coll=coll, parent=parent, smooth=bevel > 0, outline=outline)
    if bevel > 0:
        bv = ob.modifiers.new("Bisel", "BEVEL")
        bv.width = bevel
        bv.segments = seg
        bv.limit_method = "ANGLE"
        bv.harden_normals = False
    return ob


def ring_data(r_in, r_out, y0, y1, n=192, gaps=(), wall_mi=(), mi=(0, 1, 2, 3), cx=0.0, cz=0.0):
    """Anillo/disco extruido en Y entre dos curvas polares (en el plano XZ).
    mi: (frente y0, atrás y1, pared interior, pared exterior). gaps: [(deg_a, deg_b)] huecos (lumbreras)."""
    th = np.linspace(0, 2 * math.pi, n, endpoint=False)
    ro = r_out(th) if callable(r_out) else np.full(n, float(r_out))
    solid = r_in is None
    if not solid:
        ri = r_in(th) if callable(r_in) else np.full(n, float(r_in))
    V = []
    for k in range(n):
        c, s = math.cos(th[k]), math.sin(th[k])
        V.append((cx + ro[k] * c, y0, cz + ro[k] * s))   # 4k+0 outer front
        V.append((cx + ro[k] * c, y1, cz + ro[k] * s))   # 4k+1 outer back
        if not solid:
            V.append((cx + ri[k] * c, y0, cz + ri[k] * s))  # 4k+2 inner front
            V.append((cx + ri[k] * c, y1, cz + ri[k] * s))  # 4k+3 inner back
    st = 2 if solid else 4
    if solid:
        cf = len(V)
        V.append((cx, y0, cz))
        cb = len(V)
        V.append((cx, y1, cz))

    def gap_of(k):
        a = math.degrees(th[k] + math.pi / n) % 360
        for gi, (ga, gb) in enumerate(gaps):
            if (ga % 360) <= a <= (gb % 360):
                return gi
        return -1

    Fc, M = [], []
    for k in range(n):
        k1 = (k + 1) % n
        g = gap_of(k)
        if g >= 0:
            if gap_of(k - 1) < 0 and not solid:
                Fc.append([st * k + 2, st * k + 0, st * k + 1, st * k + 3])
                M.append(wall_mi[g])
            if gap_of(k1) < 0 and not solid:
                Fc.append([st * k1 + 0, st * k1 + 2, st * k1 + 3, st * k1 + 1])
                M.append(wall_mi[g])
            continue
        o0, o1 = st * k, st * k1
        if solid:
            Fc.append([cf, o1 + 0, o0 + 0]); M.append(mi[0])
            Fc.append([cb, o0 + 1, o1 + 1]); M.append(mi[1])
        else:
            Fc.append([o0 + 2, o1 + 2, o1 + 0, o0 + 0]); M.append(mi[0])
            Fc.append([o0 + 3, o0 + 1, o1 + 1, o1 + 3]); M.append(mi[1])
            Fc.append([o0 + 2, o0 + 3, o1 + 3, o1 + 2]); M.append(mi[2])
        Fc.append([o0 + 0, o1 + 0, o1 + 1, o0 + 1]); M.append(mi[3])
    return V, Fc, M


def tube_data(pts, r, n=12, mi=0, caps=True):
    """Tubo a lo largo de una polilínea 3D (marcos de transporte paralelo)."""
    P = [Vector(p) for p in pts]
    T = []
    for i in range(len(P)):
        a = P[max(i - 1, 0)]
        b = P[min(i + 1, len(P) - 1)]
        T.append((b - a).normalized())
    ref = Vector((0, 0, 1)) if abs(T[0].z) < 0.9 else Vector((1, 0, 0))
    N = (ref - T[0] * ref.dot(T[0])).normalized()
    V, Fc = [], []
    for i in range(len(P)):
        if i > 0:
            N = (N - T[i] * N.dot(T[i])).normalized()
        B = T[i].cross(N)
        rr = r[i] if isinstance(r, (list, tuple, np.ndarray)) else r
        for k in range(n):
            a = 2 * math.pi * k / n
            V.append(tuple(P[i] + rr * (math.cos(a) * N + math.sin(a) * B)))
    for i in range(len(P) - 1):
        for k in range(n):
            k1 = (k + 1) % n
            Fc.append([i * n + k, i * n + k1, (i + 1) * n + k1, (i + 1) * n + k])
    if caps:
        Fc.append([k for k in reversed(range(n))])
        Fc.append([(len(P) - 1) * n + k for k in range(n)])
    return V, Fc, [mi] * len(Fc)


def half_pipe_data(path, y, r, side, n_arc=8, mi=0, rim_mi=None, r_in=None, rim_only=False):
    """Medio tubo en el plano y (eje del tubo dentro del plano).
    side=+1: la mitad de atrás (+Y). side=-1: la de enfrente."""
    path = np.asarray(path)
    npt = len(path)
    V, Fc, M = [], [], []
    T = np.gradient(path, axis=0)
    T /= np.linalg.norm(T, axis=1, keepdims=True)
    Nn = np.stack([-T[:, 1], T[:, 0]], 1)
    betas = np.linspace(0, math.pi, n_arc + 1)
    for i in range(npt):
        for b in betas:
            d = (math.cos(b) * Nn[i, 0], side * math.sin(b), math.cos(b) * Nn[i, 1])
            V.append((path[i, 0] + r * d[0], y + r * d[1], path[i, 1] + r * d[2]))
    na = n_arc + 1
    if not rim_only:
        for i in range(npt - 1):
            for j in range(n_arc):
                f = [i * na + j, (i + 1) * na + j, (i + 1) * na + j + 1, i * na + j + 1]
                Fc.append(f if side > 0 else f[::-1])
                M.append(mi)
    if r_in is not None and rim_mi is not None:
        o = len(V)
        for i in range(npt):
            for b in (0.0, math.pi):
                d = (math.cos(b) * Nn[i, 0], 0.0, math.cos(b) * Nn[i, 1])
                V.append((path[i, 0] + r * d[0], y, path[i, 1] + r * d[2]))
                V.append((path[i, 0] + r_in * d[0], y, path[i, 1] + r_in * d[2]))
        for i in range(npt - 1):
            for s in range(2):
                a0 = o + i * 4 + s * 2
                a1 = o + (i + 1) * 4 + s * 2
                Fc.append([a0, a1, a1 + 1, a0 + 1])
                M.append(rim_mi)
    return V, Fc, M


def path3(path2d, y):
    return [(p[0], y, p[1]) for p in path2d]


def gear_polar(n_teeth, r_root, r_tip, phase_deg, top=0.15, base=0.30):
    ph = math.radians(phase_deg)
    period = 2 * math.pi / n_teeth

    def f(theta):
        x = np.mod((theta - ph) / period, 1.0)
        d = np.minimum(x, 1 - x)
        t = np.clip((base - d) / (base - top), 0, 1)
        return r_root + (r_tip - r_root) * t
    return f


def text_mesh(name, body, size, mats, coll, parent, mat_world, extrude=0.03, outline="engine"):
    cu = bpy.data.curves.new(name + "_c", "FONT")
    cu.body = body
    cu.size = size
    cu.extrude = extrude
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    tmp = bpy.data.objects.new(name + "_tmp", cu)
    scene.collection.objects.link(tmp)
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(tmp.evaluated_get(dg))
    bpy.data.objects.remove(tmp)
    me.transform(mat_world)
    for m in mats:
        me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    COLLS[coll].objects.link(ob)
    ob.parent = parent
    if outline:
        OUTLINE_GROUPS[outline].append(ob)
    return ob


def apply_boolean_holes(ob, cutters):
    mod = ob.modifiers.new("Agujeros", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.solver = "EXACT"
    col = bpy.data.collections.new(ob.name + "_cut")
    scene.collection.children.link(col)
    for c in cutters:
        col.objects.link(c)
    mod.operand_type = "COLLECTION"
    mod.collection = col
    bpy.context.view_layer.update()
    for c in cutters:
        c.matrix_world = ob.matrix_world.copy()
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    old = ob.data
    ob.modifiers.remove(mod)
    ob.data = me
    bpy.data.meshes.remove(old)
    for c in cutters:
        m = c.data
        bpy.data.objects.remove(c)
        bpy.data.meshes.remove(m)
    bpy.data.collections.remove(col)
    me.shade_smooth()
    me.set_sharp_from_angle(angle=math.radians(35))


def cutter_cyl(r, y0, y1, u, v, n=20):
    V, Fc, M = lathe([(0, 0), (r, 0), (r, 1), (0, 1)], n,
                     Matrix.Translation((u, y0, v)) @ Matrix.Rotation(-math.pi / 2, 4, "X")
                     @ Matrix.Diagonal((1, 1, y1 - y0, 1)))
    me = bpy.data.meshes.new("cut")
    me.from_pydata(V, [], Fc)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    return bpy.data.objects.new("cut", me)


# ====================================================================== MOTOR
CAR = empty("CARRO", "Carro")
ENGINE = empty("MOTOR", "Motor", parent=CAR, loc=rc.ENGINE_POS)
ENGINE.rotation_euler = (0, 0, math.radians(90))
ENGINE.scale = (rc.ENGINE_SCALE,) * 3
FRONT = empty("Frente_que_sale_volando", "Motor", parent=ENGINE)

Yc = rc.Y_CUT
ROT_Y = Matrix.Rotation(math.pi / 2, 4, "X")   # Z local del torno -> -Y (mira al frente)


def at(u, y, v):
    return Matrix.Translation((u, y, v))


def along_y(u, y, v):
    """Torno con eje hacia -Y empezando en y (z del perfil crece hacia el frente)."""
    return at(u, y, v) @ ROT_Y


outer = rc.outer_r
hous = rc.housing_r
GAPS = [(rc.PORT_IN - rc.PORT_HALF, rc.PORT_IN + rc.PORT_HALF),
        (rc.PORT_EX - rc.PORT_HALF, rc.PORT_EX + rc.PORT_HALF)]

# --- carcasa del rotor delantera: mitad de enfrente (sale volando) y mitad de atrás (queda en corte)
V, Fc, M = ring_data(hous, outer, rc.Y_FHOUS[0], Yc, 240, GAPS, (4, 5), mi=(1, 0, 2, 1))
make_obj("Carcasa_mitad_frente", V, Fc, [M_STRIPE, M_ALU, M_CHROME, M_ALU, M_COLD, M_HOT], M, parent=FRONT)
V, Fc, M = ring_data(hous, outer, Yc, rc.Y_FHOUS[1], 240, GAPS, (4, 5), mi=(0, 1, 2, 1))
make_obj("Carcasa_mitad_atras", V, Fc, [M_STRIPE, M_ALU, M_CHROME, M_ALU, M_COLD, M_HOT], M, parent=ENGINE)
# pernos cortados que se ven en la cara del corte
parts = []
for a in (35, 75, 105, 180, 255, 285, 325):
    ar = math.radians(a)
    rr = 0.5 * (float(hous(np.array([ar]))[0]) + float(outer(np.array([ar]))[0]))
    parts.append(lathe([(0, 0), (0.055, 0), (0.055, 0.004), (0, 0.004)], 12,
                       along_y(rr * math.cos(ar), Yc + 0.001, rr * math.sin(ar)), 0))
V, Fc, M = merge(parts)
make_obj("Pernos_cortados", V, Fc, [M_STEEL], M, parent=ENGINE, outline=None)

# --- placa intermedia: su cara de enfrente es el fondo de la cámara (lado frío / lado caliente)
V, Fc, M = ring_data(0.13, lambda t: outer(t) * 1.04, rc.Y_MIRON[0], rc.Y_MIRON[1], 192, mi=(0, 1, 1, 1))
make_obj("Placa_intermedia", V, Fc, [M_ZONE, M_BLOCK], M, parent=ENGINE)
# carcasa trasera, placa trasera y tapa trasera
V, Fc, M = ring_data(hous, outer, rc.Y_RHOUS[0], rc.Y_RHOUS[1], 192, GAPS, (0, 0), mi=(0, 0, 0, 0))
make_obj("Carcasa_trasera", V, Fc, [M_ALU], M, parent=ENGINE)
V, Fc, M = ring_data(0.13, lambda t: outer(t) * 1.04, rc.Y_RIRON[0], rc.Y_RIRON[1], 160)
make_obj("Placa_trasera", V, Fc, [M_BLOCK], [0] * len(Fc), parent=ENGINE)
V, Fc, M = ring_data(None, lambda t: outer(t) * 0.9, rc.Y_RCOVER[0], rc.Y_RCOVER[1], 128)
make_obj("Tapa_trasera", V, Fc, [M_BLOCK], [0] * len(Fc), parent=ENGINE)
# campana de la caja de cambios con nervaduras
prof = [(1.35, 0.0)]
for i in range(8):
    z = 0.12 + i * 0.24
    r = 1.35 - i * 0.09
    prof += [(r, z), (r + 0.06, z + 0.04), (r + 0.06, z + 0.1), (r, z + 0.14)]
prof += [(0.62, 2.1), (0.55, 2.4), (0.0, 2.45)]
V, Fc, M = lathe(prof, 36, at(0, rc.Y_RCOVER[1], -0.2) @ Matrix.Rotation(-math.pi / 2, 4, "X"))
make_obj("Caja_de_cambios", V, Fc, [M_BLOCK], M, parent=ENGINE)

# --- placa delantera y tapa delantera (salen volando), con pernos
V, Fc, M = ring_data(0.13, lambda t: outer(t) * 1.04, rc.Y_FIRON[0], rc.Y_FIRON[1], 192)
make_obj("Placa_delantera", V, Fc, [M_BLOCK], [0] * len(Fc), parent=FRONT)
parts = []
for k in range(12):
    a = math.radians(k * 30 + 15)
    rr = float(outer(np.array([a]))[0]) * 0.975
    parts.append(lathe([(0.065, 0), (0.065, 0.05), (0.05, 0.07), (0, 0.07)], 6,
                       along_y(rr * math.cos(a), rc.Y_FIRON[0], rr * math.sin(a)), 0))
V, Fc, M = merge(parts)
make_obj("Pernos_placa_delantera", V, Fc, [M_STEEL], M, parent=FRONT)

V, Fc, M = ring_data(0.2, lambda t: outer(t) * 0.9, rc.Y_COVER[0], rc.Y_COVER[1], 160)
make_obj("Tapa_delantera", V, Fc, [M_RED], [0] * len(Fc), parent=FRONT)
parts = []
# nervaduras radiales y pernos en la tapa
for k in range(8):
    a = math.radians(k * 45 + 22.5)
    c, s = math.cos(a), math.sin(a)
    r0, r1 = 0.5, float(outer(np.array([a]))[0]) * 0.8
    V0, F0, M0 = box_data(r0, r1, -0.045, 0.045, -0.03, 0.03, 0)
    m = at(0, rc.Y_COVER[0], 0) @ Matrix.Rotation(-a, 4, "Y")
    parts.append((xform([(x, z, y) for x, y, z in V0], m), F0, M0))
for k in range(10):
    a = math.radians(k * 36)
    rr = float(outer(np.array([a]))[0]) * 0.82
    parts.append(lathe([(0.05, 0), (0.05, 0.05), (0.035, 0.065), (0, 0.065)], 6,
                       along_y(rr * math.cos(a), rc.Y_COVER[0], rr * math.sin(a)), 0))
V, Fc, M = merge(parts)
make_obj("Nervaduras_tapa", V, Fc, [M_RED], M, parent=FRONT)
V, Fc, M = lathe([(0.2, 0.0), (0.45, 0.0), (0.45, 0.08), (0.4, 0.12), (0.2, 0.12)], 40,
                 along_y(0, rc.Y_COVER[0], 0))
make_obj("Tapa_centro", V, Fc, [M_RED], M, parent=FRONT)

# --- eje excéntrico (gira), con raya amarilla para ver las vueltas
SHAFT = empty("Eje_giratorio", "Motor", parent=ENGINE)
V, Fc, M = lathe([(0, 0), (0.12, 0), (0.12, 2.85), (0, 2.85)], 24,
                 along_y(0, rc.Y_RCOVER[1] + 0.25, 0))
make_obj("Eje_excentrico", V, Fc, [M_CHROME], M, parent=SHAFT)
V, Fc, M = box_data(-0.022, 0.022, -0.008, 0.0, 0.0, 0.115, 0)
V = [(x, y + rc.Y_FIRON[1], z) for x, y, z in V]
make_obj("Marca_eje", V, Fc, [M_YELLOW], M, parent=SHAFT, outline=None)
# --- lóbulo excéntrico (gira con el eje, su centro es el centro del rotor)
LOBE = empty("Lobulo_giratorio", "Motor", parent=ENGINE)
V, Fc, M = ring_data(None, 0.375, rc.Y_LOBE[0], rc.Y_LOBE[1], 64)
make_obj("Lobulo_excentrico", V, Fc, [M_ORANGE], [0] * len(Fc), parent=LOBE)
V, Fc, M = lathe([(0, 0), (0.06, 0), (0.06, 0.006), (0, 0.006)], 16, along_y(0.0, rc.Y_LOBE[0] - 0.0, 0.26))
make_obj("Marca_lobulo", V, Fc, [M_YELLOW], M, parent=LOBE, outline=None)

# --- piñón fijo
V, Fc, M = ring_data(0.125, gear_polar(rc.GEAR_FIX_T, 0.27, 0.33, -90.0), rc.Y_GEAR[0], rc.Y_GEAR[1],
                     rc.GEAR_FIX_T * 16)
make_obj("Pinon_fijo", V, Fc, [M_STEEL], [0] * len(Fc), parent=ENGINE)

# --- rotor: cuerpo (queda), cara delantera (sale volando en la escena 7), corona, sellos
ROTOR = empty("Rotor_giratorio", "Motor", parent=ENGINE)
ROTOR_PLATE = empty("Rotor_cara_que_sale", "Motor", parent=ENGINE)
rr_fn = rc.rotor_r
V1, F1, M1 = ring_data(0.47, rr_fn, rc.Y_RBODY[0], rc.Y_GEAR[1], 360, mi=(0, 1, 2, 3))
V2, F2, M2 = ring_data(0.395, rr_fn, rc.Y_GEAR[1], rc.Y_RBODY[1], 360, mi=(1, 1, 2, 3))
V, Fc, M = merge([(V1, F1, M1), (V2, F2, M2)])
make_obj("Rotor_cuerpo", V, Fc, [M_STRIPE, M_ROTOR, M_CHROME, M_ROTOR], M, parent=ROTOR)
ring_t = gear_polar(rc.GEAR_RING_T, 0.47, 0.405, -90.0 + 7.5)
V, Fc, M = ring_data(ring_t, 0.472, rc.Y_GEAR[0] + 0.002, rc.Y_GEAR[1], rc.GEAR_RING_T * 16)
make_obj("Corona_interna", V, Fc, [M_BRASS], [0] * len(Fc), parent=ROTOR)
parts = []
for k in range(3):
    a = math.radians(90 + 120 * k)
    tip = 0.993
    V0, F0, M0 = box_data(-0.035, 0.035, rc.Y_RPLATE[0] + 0.01, rc.Y_RBODY[1] - 0.01, tip - 0.07, tip + 0.004, 0)
    m = Matrix.Rotation(-(a - math.pi / 2), 4, "Y")
    parts.append((xform(V0, m), F0, M0))
V, Fc, M = merge(parts)
make_obj("Sellos_de_punta", V, Fc, [M_ORANGE], M, parent=ROTOR)
# cara delantera del rotor con línea de sellos y sellos de esquina
V, Fc, M = ring_data(0.30, rr_fn, rc.Y_RPLATE[0], rc.Y_RPLATE[1], 360)
make_obj("Rotor_cara", V, Fc, [M_ROTOR], [0] * len(Fc), parent=ROTOR_PLATE)
V, Fc, M = ring_data(lambda t: rr_fn(t) - 0.075, lambda t: rr_fn(t) - 0.055, rc.Y_RPLATE[0] - 0.004,
                     rc.Y_RPLATE[0] + 0.01, 360)
make_obj("Rotor_sello_lateral", V, Fc, [M_STEEL], [0] * len(Fc), parent=ROTOR_PLATE, outline=None)
parts = []
for k in range(3):
    a = math.radians(90 + 120 * k)
    parts.append(lathe([(0, 0), (0.04, 0), (0.04, 0.008), (0, 0.008)], 16,
                       along_y(0.86 * math.cos(a), rc.Y_RPLATE[0] + 0.004, 0.86 * math.sin(a)), 0))
V, Fc, M = merge(parts)
make_obj("Rotor_sellos_esquina", V, Fc, [M_STEEL], M, parent=ROTOR_PLATE, outline=None)

# --- tensores de bujía, bujías, cables y bobinas
for i, pa in enumerate(rc.PLUG_ANGLES):
    a = math.radians(pa)
    tu, tv = rc.plug_tip(pa)
    m = axis_matrix((tu, Yc, tv), (math.cos(a), 0, math.sin(a)))
    parts = [
        lathe([(0, -0.02), (0.018, -0.02), (0.018, 0.05), (0.0, 0.05)], 10, m, 1),
        lathe([(0.0, 0.04), (0.07, 0.04), (0.07, 0.47), (0.0, 0.47)], 14, m, 1),
        lathe([(0.0, 0.47), (0.115, 0.47), (0.115, 0.57), (0.0, 0.57)], 6, m, 1),
        lathe([(0.0, 0.57), (0.068, 0.57), (0.072, 0.66), (0.062, 0.7), (0.068, 0.75), (0.058, 0.79),
               (0.062, 0.85), (0.0, 0.9)], 14, m, 2),
        lathe([(0.0, 0.84), (0.095, 0.86), (0.1, 1.12), (0.07, 1.18), (0.0, 1.18)], 14, m, 0),
    ]
    V, Fc, M = merge(parts)
    make_obj(f"Bujia_{i + 1}", V, Fc, [M_RUBBER, M_STEEL, M_CERAMIC], M, parent=ENGINE)
    end = Vector((tu, Yc, tv)) + 1.16 * Vector((math.cos(a), 0, math.sin(a)))
    pts = [end, end + Vector((0.25, 0.0, 0.03 * (1 if pa > 0 else -1))),
           end + Vector((0.45, 0.35, 0.05 * (1 if pa > 0 else -1))),
           Vector((2.15, 0.6, 0.18 if pa > 0 else -0.18))]
    from_pts = []
    for j in range(len(pts) - 1):
        for t in np.linspace(0, 1, 6, endpoint=False):
            from_pts.append(pts[j].lerp(pts[j + 1], t))
    from_pts.append(pts[-1])
    V, Fc, M = tube_data(from_pts, 0.035, 8)
    make_obj(f"Cable_bujia_{i + 1}", V, Fc, [M_RUBBER], M, parent=ENGINE)
parts = [box_data(1.95, 2.35, 0.3, 1.1, -0.45, 0.45, 0)]
for k in range(5):
    parts.append(box_data(2.35, 2.4, 0.38 + k * 0.15, 0.45 + k * 0.15, -0.4, 0.4, 0))
parts.append(box_data(2.05, 2.25, 1.1, 1.25, -0.1, 0.1, 1))
V, Fc, M = merge(parts)
make_obj("Bobina_y_conector", V, Fc, [M_RUBBER, M_STEEL], M, parent=ENGINE)

# --- polea principal (con agujeros), banda, bomba de agua, alternador
V, Fc, M = lathe([(0.0, 0.0), (0.2, 0.0), (0.2, 0.75), (0.62, 0.78), (0.62, 0.82), (0.7, 0.85), (0.66, 0.9),
                  (0.7, 0.95), (0.66, 1.0), (0.7, 1.05), (0.7, 1.1), (0.62, 1.12), (0.25, 1.12),
                  (0.25, 1.17), (0.0, 1.17)], 48, along_y(0, rc.Y_FIRON[1] - 0.02, 0))
pul = make_obj("Polea_principal", V, Fc, [M_CHROME], M, parent=FRONT)
cut = [cutter_cyl(0.11, -2.6, -1.9, 0.42 * math.cos(math.radians(90 + 72 * k)),
                  0.42 * math.sin(math.radians(90 + 72 * k))) for k in range(5)]
for c in cut:
    scene.collection.objects.link(c)
apply_boolean_holes(pul, cut)
PULLEY = pul

WP = (0.0, 1.85)
ALT = (1.78, 1.22)
PUL_R = {"main": 0.7, "wp": 0.38, "alt": 0.26}
V, Fc, M = lathe([(0.0, 0.0), (0.28, 0.0), (0.3, 0.3), (0.2, 0.45), (0.0, 0.45)], 24,
                 along_y(WP[0], -1.55, WP[1]))
make_obj("Bomba_de_agua", V, Fc, [M_ALU], M, parent=FRONT)
V, Fc, M = lathe([(0.0, 0.0), (0.12, 0.0), (0.12, 0.2), (0.34, 0.22), (0.38, 0.26), (0.34, 0.3), (0.38, 0.34),
                  (0.38, 0.42), (0.12, 0.44), (0.0, 0.44)], 32, along_y(WP[0], -1.98, WP[1]))
WP_PULLEY = make_obj("Polea_bomba", V, Fc, [M_STEEL], M, parent=FRONT)
hose = [(0.2, -1.8, 2.05), (0.45, -2.25, 2.2), (0.55, -2.75, 2.15), (0.58, -3.2, 2.0)]
pts = []
for j in range(len(hose) - 1):
    for t in np.linspace(0, 1, 6, endpoint=False):
        pts.append(Vector(hose[j]).lerp(Vector(hose[j + 1]), t))
pts.append(Vector(hose[-1]))
V, Fc, M = tube_data(pts, 0.12, 12)
make_obj("Manguera", V, Fc, [M_RUBBER], M, parent=FRONT)
parts = []
for t in (0.25, 0.8):
    p = pts[int(t * (len(pts) - 1))]
    q = pts[int(t * (len(pts) - 1)) + 1]
    parts.append(tube_data([p, q], 0.135, 12)[:3])
V, Fc, M = merge(parts)
make_obj("Abrazaderas_manguera", V, Fc, [M_CHROME], M, parent=FRONT)

# banda: envolvente convexa de las tres poleas
circ = [((0.0, 0.0), 0.7), (WP, 0.38), (ALT, 0.26)]
P = []
for (cu_, cv_), r in circ:
    for k in range(96):
        a = 2 * math.pi * k / 96
        P.append((cu_ + r * math.cos(a), cv_ + r * math.sin(a)))
P = sorted(set(P))


def _cross(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


lower, upper = [], []
for p in P:
    while len(lower) >= 2 and _cross(lower[-2], lower[-1], p) <= 0:
        lower.pop()
    lower.append(p)
for p in reversed(P):
    while len(upper) >= 2 and _cross(upper[-2], upper[-1], p) <= 0:
        upper.pop()
    upper.append(p)
hull = np.array(lower[:-1] + upper[:-1])
# re-muestreo uniforme y banda con grosor
hull_c = np.vstack([hull, hull[:1]])
seg = np.linalg.norm(np.diff(hull_c, axis=0), axis=1)
s = np.concatenate([[0], np.cumsum(seg)])
ss = np.linspace(0, s[-1], 220, endpoint=False)
hu = np.interp(ss, s, hull_c[:, 0])
hv = np.interp(ss, s, hull_c[:, 1])
cen = np.array([hu.mean(), hv.mean()])
V, Fc = [], []
nb = len(hu)
for k in range(nb):
    d = np.array([hu[(k + 1) % nb] - hu[k - 1], hv[(k + 1) % nb] - hv[k - 1]])
    nrm = np.array([d[1], -d[0]]) / np.linalg.norm(d)
    if np.dot(nrm, np.array([hu[k], hv[k]]) - cen) < 0:
        nrm = -nrm
    for (dd, yy) in ((0.0, -2.30), (0.0, -2.10), (0.05, -2.10), (0.05, -2.30)):
        V.append((hu[k] + dd * nrm[0], yy, hv[k] + dd * nrm[1]))
for k in range(nb):
    k1 = (k + 1) % nb
    for j in range(4):
        j1 = (j + 1) % 4
        Fc.append([4 * k + j, 4 * k1 + j, 4 * k1 + j1, 4 * k + j1])
make_obj("Banda", V, Fc, [M_RUBBER], [0] * len(Fc), parent=FRONT)

# alternador con aletas, ventilador, polea, cable con conector y soporte
prof = [(0.0, 0.0), (0.42, 0.0), (0.46, 0.04)]
for i in range(9):
    z = 0.08 + i * 0.1
    prof += [(0.5, z), (0.55, z + 0.02), (0.55, z + 0.06), (0.5, z + 0.08)]
prof += [(0.48, 1.0), (0.4, 1.05), (0.0, 1.05)]
V, Fc, M = lathe(prof, 40, at(ALT[0], -0.85, ALT[1]) @ Matrix.Rotation(math.pi / 2, 4, "X"))
V = [(x, y - 0.0, z) for x, y, z in V]
make_obj("Alternador", V, Fc, [M_ALU], M, parent=ENGINE)
parts = []
for k in range(10):
    a = math.radians(k * 36 + 18)
    V0, F0, M0 = box_data(0.18, 0.42, -0.02, 0.02, -0.012, 0.012, 0)
    m = at(ALT[0], -1.905, ALT[1]) @ Matrix.Rotation(-a, 4, "Y")
    parts.append((xform([(x, z, y) for x, y, z in V0], m), F0, M0))
V, Fc, M = merge(parts)
make_obj("Ranuras_alternador", V, Fc, [M_DARK], M, parent=ENGINE, outline=None)
ALT_ROT = empty("Alternador_giro", "Motor", parent=ENGINE, loc=(ALT[0], 0, ALT[1]))
V, Fc, M = lathe([(0.0, 0.0), (0.1, 0.0), (0.1, 0.12), (0.22, 0.14), (0.26, 0.17), (0.22, 0.2), (0.26, 0.23),
                  (0.26, 0.28), (0.1, 0.3), (0.0, 0.3)], 28, along_y(0, -2.0, 0))
make_obj("Polea_alternador", V, Fc, [M_STEEL], M, parent=ALT_ROT)
parts = []
for k in range(8):
    a = math.radians(k * 45)
    V0, F0, M0 = box_data(0.08, 0.4, -0.03, 0.03, -0.04, 0.0, 0)
    m = at(0, -1.95, 0) @ Matrix.Rotation(-a, 4, "Y") @ Matrix.Rotation(math.radians(25), 4, "X")
    parts.append((xform([(x, z, y) for x, y, z in V0], m), F0, M0))
V, Fc, M = merge(parts)
make_obj("Ventilador_alternador", V, Fc, [M_STEEL], M, parent=ALT_ROT)
wire = [Vector((ALT[0] + 0.3, -0.8, ALT[1] + 0.25)), Vector((ALT[0] + 0.55, -0.55, ALT[1] + 0.35)),
        Vector((ALT[0] + 0.7, -0.1, ALT[1] + 0.2)), Vector((ALT[0] + 0.65, 0.5, ALT[1] - 0.1))]
pts = []
for j in range(len(wire) - 1):
    for t in np.linspace(0, 1, 6, endpoint=False):
        pts.append(wire[j].lerp(wire[j + 1], t))
pts.append(wire[-1])
V, Fc, M = tube_data(pts, 0.035, 8)
make_obj("Cable_alternador", V, Fc, [M_WIRE_RED], M, parent=ENGINE)
V, Fc, M = box_data(ALT[0] + 0.22, ALT[0] + 0.42, -0.9, -0.72, ALT[1] + 0.15, ALT[1] + 0.35, 0)
make_obj("Conector_alternador", V, Fc, [M_RUBBER], M, parent=ENGINE)
V, Fc, M = box_data(1.05, ALT[0] - 0.2, -1.3, -1.1, ALT[1] - 0.12, ALT[1] + 0.02, 0)
make_obj("Soporte_alternador", V, Fc, [M_STEEL], M, parent=ENGINE)

# --- cárter con nervaduras y tapón, filtro de aceite, varilla de aceite
box("Carter", -1.15, 1.15, -1.5, 0.95, -2.35, -1.42, [M_BLOCK], "Motor", ENGINE, bevel=0.08)
parts = []
for k in range(7):
    y = -1.3 + k * 0.33
    parts.append(box_data(-1.2, -1.15, y, y + 0.07, -2.25, -1.55, 0))
    parts.append(box_data(1.15, 1.2, y, y + 0.07, -2.25, -1.55, 0))
for k in range(5):
    u = -0.9 + k * 0.45
    parts.append(box_data(u, u + 0.07, -1.55, -1.5, -2.25, -1.55, 0))
parts.append(box_data(-1.22, 1.22, -1.56, 0.98, -1.47, -1.40, 0))
V, Fc, M = merge(parts)
make_obj("Nervaduras_carter", V, Fc, [M_BLOCK], M, parent=ENGINE)
V, Fc, M = lathe([(0.0, 0.0), (0.12, 0.0), (0.12, 0.1), (0.0, 0.1)], 6,
                 at(0.3, 0.3, -2.35) @ Matrix.Rotation(math.pi, 4, "X"))
make_obj("Tapon_carter", V, Fc, [M_STEEL], M, parent=ENGINE)
fdir = Vector((1.0, 0.0, -0.75)).normalized()
m = axis_matrix((1.0, -1.15, -1.2), fdir)
prof = [(0.0, 0.0), (0.3, 0.0), (0.3, 0.06), (0.33, 0.08), (0.33, 0.38)]
for i in range(5):
    z = 0.4 + i * 0.05
    prof += [(0.35, z), (0.35, z + 0.025), (0.33, z + 0.03)]
prof += [(0.33, 0.66), (0.28, 0.7), (0.0, 0.7)]
V, Fc, M = lathe(prof, 32, m)
make_obj("Filtro_de_aceite", V, Fc, [M_BLUE], M, parent=ENGINE)
V, Fc, M = lathe([(0.334, 0.2), (0.334, 0.3)], 32, m)
make_obj("Filtro_banda", V, Fc, [M_CERAMIC], M, parent=ENGINE, outline=None)
dip = [(-0.95, -1.5, -1.45), (-1.25, -1.62, -0.4), (-1.38, -1.72, 0.8), (-1.33, -1.8, 1.9), (-1.28, -1.82, 2.2)]
pts = []
for j in range(len(dip) - 1):
    for t in np.linspace(0, 1, 6, endpoint=False):
        pts.append(Vector(dip[j]).lerp(Vector(dip[j + 1]), t))
pts.append(Vector(dip[-1]))
V, Fc, M = tube_data(pts, 0.04, 8)
make_obj("Tubo_varilla", V, Fc, [M_CHROME], M, parent=FRONT)
top = Vector(dip[-1])
V, Fc, M = lathe([(0.0, 0.0), (0.06, 0.0), (0.06, 0.16), (0.0, 0.16)], 12, axis_matrix(top, (0, 0, 1)))
V2, F2, M2 = tube_data([top + Vector((0.13 * math.cos(a), 0, 0.16 + 0.13 + 0.13 * math.sin(a)))
                        for a in np.linspace(-math.pi / 2, 1.5 * math.pi, 25)], 0.035, 8, caps=False)
V, Fc, M = merge([(V, Fc, M), (V2, F2, M2)])
make_obj("Varilla_mango_amarillo", V, Fc, [M_YELLOW], M, parent=FRONT)

# --- admisión: plenum (rojo con letras), tubos en corte, cuerpo de aceleración y filtro de aire
PL = (-1.45, 0.95, 2.55, 3.35)
pu0, pu1, pv0, pv1 = PL
w = 0.07
# mitad de atrás (queda): cascarón exterior, interior frío y canto rayado
V = [(pu0, Yc, pv0), (pu1, Yc, pv0), (pu1, Yc, pv1), (pu0, Yc, pv1),
     (pu0, 0.85, pv0), (pu1, 0.85, pv0), (pu1, 0.85, pv1), (pu0, 0.85, pv1)]
Fc = [[0, 4, 7, 3], [1, 2, 6, 5], [3, 7, 6, 2], [0, 1, 5, 4], [4, 5, 6, 7]]
ob = make_obj("Plenum_atras", V, Fc, [M_RED], [0] * 5, parent=ENGINE, recalc=True)
bv = ob.modifiers.new("Bisel", "BEVEL")
bv.width = 0.06
bv.segments = 2
bv.limit_method = "ANGLE"
a0, a1, b0, b1 = pu0 + w, pu1 - w, pv0 + w, pv1 - w
Vi = [(a0, Yc, b0), (a1, Yc, b0), (a1, Yc, b1), (a0, Yc, b1),
      (a0, 0.85 - w, b0), (a1, 0.85 - w, b0), (a1, 0.85 - w, b1), (a0, 0.85 - w, b1)]
Fi = [[3, 7, 4, 0], [5, 6, 2, 1], [2, 6, 7, 3], [4, 5, 1, 0], [7, 6, 5, 4]]
Vr = [(pu0, Yc, pv0), (pu1, Yc, pv0), (pu1, Yc, pv1), (pu0, Yc, pv1), (a0, Yc, b0), (a1, Yc, b0),
      (a1, Yc, b1), (a0, Yc, b1)]
Fr = [[0, 1, 5, 4], [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
V, Fc, M = merge([(Vi, Fi, [0] * 5), (Vr, Fr, [1] * 4)])
make_obj("Plenum_interior", V, Fc, [M_COLD, M_STRIPE], M, parent=ENGINE, recalc=False, smooth=False,
         outline=None)
box("Plenum_frente", pu0, pu1, -1.6, Yc, pv0, pv1, [M_RED, M_STRIPE], "Motor", FRONT, bevel=0.06,
    fmi=(0, 0, 0, 1, 0, 0))
text_mesh("Letras_ROTATIVO", "ROTATIVO", 0.3, [M_CHROME], "Motor", ENGINE,
          Matrix.Translation((-0.25, 0.0, pv1 + 0.02)) @ Matrix.Rotation(-math.pi / 2, 4, "Z"), 0.03)
parts = []
for (u, y) in ((pu0 + 0.12, -0.7), (pu1 - 0.12, -0.7), (pu0 + 0.12, 0.7), (pu1 - 0.12, 0.7)):
    parts.append(lathe([(0.0, 0.0), (0.05, 0.0), (0.05, 0.05), (0.0, 0.05)], 6, at(u, y, pv1), 0))
V, Fc, M = merge(parts)
make_obj("Pernos_plenum", V, Fc, [M_CHROME], M, parent=ENGINE)
# cuerpo de aceleración y filtro de aire (salen con el frente)
V, Fc, M = lathe([(0.0, 0.0), (0.24, 0.0), (0.24, 0.5), (0.27, 0.52), (0.27, 0.6), (0.0, 0.6)], 28,
                 along_y(-0.55, -1.6, 2.95))
make_obj("Cuerpo_aceleracion", V, Fc, [M_CHROME], M, parent=FRONT)
prof = [(0.0, 0.0), (0.3, 0.0), (0.32, 0.03)]
for i in range(10):
    z = 0.05 + i * 0.065
    prof += [(0.4, z), (0.44, z + 0.03)]
prof += [(0.44, 0.72), (0.34, 0.76), (0.0, 0.78)]
V, Fc, M = lathe(prof, 36, along_y(-0.55, -2.18, 2.95))
make_obj("Filtro_de_aire", V, Fc, [M_RUBBER], M, parent=FRONT)
V, Fc, M = lathe([(0.0, 0.0), (0.3, 0.0), (0.3, 0.04), (0.0, 0.06)], 36, along_y(-0.55, -2.94, 2.95))
make_obj("Tapa_filtro", V, Fc, [M_CHROME], M, parent=FRONT)

IN_PATH = rc.intake_path()
EX_PATH = rc.exhaust_path()
for nm, path, inner in (("Admision", IN_PATH, M_COLD), ("Escape", EX_PATH, M_HOT)):
    rr_o, rr_i = 0.24, 0.19
    V, Fc, M = half_pipe_data(path, Yc, rr_o, +1, 8, 0)
    make_obj(f"Tubo_{nm}_atras", V, Fc, [M_CHROME], M, parent=ENGINE, recalc=False)
    V, Fc, M = half_pipe_data(path, Yc, rr_i, +1, 8, 0, rim_mi=1, r_in=rr_o)
    make_obj(f"Tubo_{nm}_interior", V, Fc, [inner, M_STRIPE], [m_ for m_ in M], parent=ENGINE,
             recalc=False, smooth=False, outline=None)
    V, Fc, M = half_pipe_data(path, Yc, rr_o, -1, 8, 0)
    make_obj(f"Tubo_{nm}_frente", V, Fc, [M_CHROME], M, parent=FRONT, recalc=False)
    # abrazaderas (mitad y mitad)
    nP = len(path)
    for frac in (0.12, 0.62):
        i0 = int(frac * (nP - 1))
        seg2 = path[i0:i0 + 2]
        for side, par in ((+1, ENGINE), (-1, FRONT)):
            V, Fc, M = half_pipe_data(seg2, Yc, 0.265, side, 8, 0)
            make_obj(f"Abrazadera_{nm}_{frac}_{side}", V, Fc, [M_STEEL], M, parent=par, recalc=False,
                     outline=None)

# acople de goma en la admisión, junto al plenum
seg3 = IN_PATH[-8:-3]
for side, par in ((+1, ENGINE), (-1, FRONT)):
    V, Fc, M = half_pipe_data(seg3, Yc, 0.255, side, 8, 0)
    make_obj(f"Acople_goma_{side}", V, Fc, [M_RUBBER], M, parent=par, recalc=False, outline=None)

# tubos completos: corredor trasero, escape que sigue hacia atrás y escape del rotor trasero
yR = 0.25
V, Fc, M = tube_data(path3(IN_PATH, yR), 0.24, 14)
make_obj("Tubo_admision_trasero", V, Fc, [M_CHROME], M, parent=ENGINE)
ex_end = EX_PATH[-1]
cont = [(ex_end[0], Yc, ex_end[1]), (ex_end[0] - 0.01, Yc + 0.12, ex_end[1] - 0.25),
        (ex_end[0] + 0.02, Yc + 0.45, ex_end[1] - 0.38), (ex_end[0] + 0.05, Yc + 1.2, ex_end[1] - 0.42),
        (ex_end[0] + 0.1, 2.5, ex_end[1] - 0.42), (ex_end[0] + 0.25, 4.2, ex_end[1] - 0.42)]
pts = []
for j in range(len(cont) - 1):
    for t in np.linspace(0, 1, 5, endpoint=False):
        pts.append(Vector(cont[j]).lerp(Vector(cont[j + 1]), t))
pts.append(Vector(cont[-1]))
V, Fc, M = tube_data(pts, 0.24, 14)
make_obj("Escape_hacia_atras", V, Fc, [M_CHROME], M, parent=ENGINE)
V, Fc, M = tube_data(path3(EX_PATH, yR) + [(ex_end[0] + 0.03, yR + 0.3, ex_end[1] - 0.38),
                                         (ex_end[0] + 0.05, yR + 0.95, ex_end[1] - 0.42)], 0.24, 14)
make_obj("Escape_trasero", V, Fc, [M_CHROME], M, parent=ENGINE)
parts = []
for yy in (Yc + 1.6, 2.3, 3.2):
    parts.append(tube_data([(ex_end[0] + 0.07, yy, ex_end[1] - 0.42),
                            (ex_end[0] + 0.07, yy + 0.08, ex_end[1] - 0.42)], 0.27, 14)[:3])
V, Fc, M = merge(parts)
make_obj("Abrazaderas_escape", V, Fc, [M_STEEL], M, parent=ENGINE)

# soportes del motor
for sgn in (-1, 1):
    V1_, F1_, M1_ = box_data(sgn * 1.3 if sgn > 0 else -2.4, 2.4 if sgn > 0 else -1.3, 0.1, 0.5, -0.75, -0.45, 0)
    V2_, F2_, M2_ = box_data(sgn * 2.4 if sgn > 0 else -2.75, 2.75 if sgn > 0 else -2.4, 0.05, 0.55, -0.85, -0.35, 1)
    V, Fc, M = merge([(V1_, F1_, M1_), (V2_, F2_, M2_)])
    make_obj(f"Soporte_motor_{sgn}", V, Fc, [M_STEEL, M_RUBBER], M, parent=ENGINE)

# ====================================================================== CARRO
CB = dict(coll="Carro", parent=CAR, outline="car")


def cbox(name, x0, x1, y0, y1, z0, z1, mat, bevel=0.0, seg=2, parent=CAR, outline="car"):
    ob = box(name, x0, x1, y0, y1, z0, z1, [mat], "Carro", parent, bevel=bevel, seg=seg, outline=outline)
    HIDE_GROUPS["car"].append(ob)
    return ob


cbox("Cuerpo_bajo", -9.5, 7.0, -9.0, 9.0, 1.6, 9.2, M_CAR, 0.8, 3)
for sg in (-1, 1):
    y0, y1 = (6.6, 9.0) if sg > 0 else (-9.0, -6.6)
    cbox(f"Falda_{sg}", 7.0, 9.6, y0, y1, 1.6, 6.9, M_CAR, 0.4)
    cbox(f"Salpicadera_{sg}", 7.0, 20.6, y0, y1, 6.9, 8.95, M_CAR, 0.5, 3)
    cbox(f"Falda_frente_{sg}", 17.4, 20.6, y0, y1, 1.8, 6.9, M_CAR, 0.4)
    cbox(f"Salpicadera_tras_{sg}", -17.5, -9.5, y0, y1, 6.9, 9.0, M_CAR, 0.5, 3)
cbox("Nariz", 20.4, 23.6, -8.8, 8.8, 1.7, 8.2, M_CAR, 1.4, 3)
cbox("Parrilla", 23.4, 23.75, -4.5, 4.5, 2.6, 4.4, M_DARK, 0.1, outline=None)
for k in range(3):
    cbox(f"Parrilla_barra_{k}", 23.6, 23.85, -4.3, 4.3, 2.9 + k * 0.5, 3.05 + k * 0.5, M_CHROME, 0.0,
         outline=None)
for sg in (-1, 1):
    y0, y1 = (5.0, 7.6) if sg > 0 else (-7.6, -5.0)
    cbox(f"Faro_{sg}", 23.2, 23.78, y0, y1, 5.6, 6.7, M_HEAD, 0.2, outline=None)
    cbox(f"Bisel_faro_{sg}", 23.1, 23.7, y0 - 0.2, y1 + 0.2, 5.4, 6.9, M_CHROME, 0.15, outline=None)
    cbox(f"Antiniebla_{sg}", 23.4, 23.8, (6.2 if sg > 0 else -7.0), (7.0 if sg > 0 else -6.2), 2.4, 3.0,
         M_HEAD, 0.1, outline=None)
cbox("Labio", 21.5, 24.0, -8.5, 8.5, 1.35, 1.8, M_DARK, 0.15)
cbox("Cofre_base", 3.5, 7.3, -8.8, 8.8, 8.2, 9.3, M_CAR, 0.4)
# cabina de vidrio con techo y pilares
V = [(-11.0, -8.4, 9.25), (4.6, -8.4, 9.25), (4.6, 8.4, 9.25), (-11.0, 8.4, 9.25),
     (-7.5, -7.0, 13.0), (-0.5, -7.0, 13.0), (-0.5, 7.0, 13.0), (-7.5, 7.0, 13.0)]
Fc = [[0, 3, 7, 4], [1, 5, 6, 2], [0, 4, 5, 1], [3, 2, 6, 7], [0, 1, 2, 3], [4, 7, 6, 5]]
ob = make_obj("Cabina_vidrio", V, Fc, [M_GLASS], [0] * 6, coll="Carro", parent=CAR, smooth=False,
              outline="car")
HIDE_GROUPS["car"].append(ob)
cbox("Techo", -7.7, -0.3, -7.15, 7.15, 12.85, 13.3, M_CAR, 0.4, 3)
for sg in (-1, 1):
    for nm, a, b in (("A", (4.5, 8.35, 9.3), (-0.5, 7.0, 13.0)), ("B", (-3.2, 8.4, 9.3), (-3.6, 7.05, 13.0)),
                     ("C", (-10.9, 8.35, 9.3), (-7.4, 7.0, 13.0))):
        pa = Vector((a[0], sg * a[1], a[2]))
        pb = Vector((b[0], sg * b[1], b[2]))
        V, Fc, M = tube_data([pa, pa.lerp(pb, 0.5), pb], 0.32, 8)
        ob = make_obj(f"Pilar_{nm}_{sg}", V, Fc, [M_CAR], M, coll="Carro", parent=CAR, outline="car")
        HIDE_GROUPS["car"].append(ob)
    cbox(f"Espejo_{sg}", 3.0, 4.4, (9.0 if sg > 0 else -10.3), (10.3 if sg > 0 else -9.0), 9.4, 10.3, M_CAR, 0.3)
    cbox(f"Linea_puerta_{sg}", -1.1, -0.95, (9.0 if sg > 0 else -9.06), (9.06 if sg > 0 else -9.0), 2.5, 9.0,
         M_DARK, 0.0, outline=None)
    cbox(f"Manija_{sg}", -3.0, -1.8, (9.0 if sg > 0 else -9.12), (9.12 if sg > 0 else -9.0), 7.3, 7.6,
         M_CHROME, 0.0, outline=None)
    cbox(f"Moldura_{sg}", -10.5, 4.0, (8.95 if sg > 0 else -9.08), (9.08 if sg > 0 else -8.95), 9.0, 9.25,
         M_CHROME, 0.0, outline=None)
cbox("Cajuela", -22.6, -9.5, -9.0, 9.0, 6.9, 9.0, M_CAR, 0.7, 3)
cbox("Defensa_tras", -22.6, -17.3, -9.0, 9.0, 1.7, 6.9, M_CAR, 1.0, 3)
cbox("Centro_tras", -17.3, -9.5, -6.6, 6.6, 1.7, 6.9, M_CAR, 0.3)
cbox("Aleron", -22.4, -19.6, -8.4, 8.4, 10.0, 10.4, M_CAR, 0.15)
for sg in (-1, 1):
    cbox(f"Pata_aleron_{sg}", -21.2, -20.6, (5.5 if sg > 0 else -6.1), (6.1 if sg > 0 else -5.5), 9.0, 10.0,
         M_DARK, 0.0)
    cbox(f"Calavera_{sg}", -22.8, -22.4, (4.0 if sg > 0 else -8.0), (8.0 if sg > 0 else -4.0), 7.2, 8.2,
         M_TAIL, 0.15, outline=None)
    V, Fc, M = lathe([(0.0, 0.0), (0.45, 0.0), (0.45, 1.2), (0.35, 1.2), (0.35, 0.2), (0.0, 0.2)], 16,
                     axis_matrix((-22.0, sg * 3.0, 2.4), (-1, 0, 0)))
    ob = make_obj(f"Salida_escape_{sg}", V, Fc, [M_CHROME], M, coll="Carro", parent=CAR, outline="car")
    HIDE_GROUPS["car"].append(ob)
# vano del motor (negro)
for args in ((7.0, 20.4, -6.6, 6.6, 1.0, 1.6), (7.0, 20.4, -6.7, -6.5, 1.6, 8.8), (7.0, 20.4, 6.5, 6.7, 1.6, 8.8),
             (6.8, 7.0, -6.6, 6.6, 1.6, 8.8), (20.3, 20.5, -6.6, 6.6, 1.6, 8.2)):
    cbox("Vano", *args, M_BAY, 0.0, outline=None)
# capó (bisagra atrás)
HOOD = empty("Capo_bisagra", "Carro", parent=CAR, loc=(7.3, 0.0, 9.05))
cbox("Capo", 0.0, 13.6, -8.5, 8.5, -0.3, 0.3, M_CAR, 0.4, 3, parent=HOOD)
cbox("Capo_joroba", 1.7, 10.7, -3.2, 3.2, 0.25, 0.6, M_CAR, 0.3, 3, parent=HOOD)
for sg in (-1, 1):
    cbox(f"Capo_ventila_{sg}", 4.0, 8.0, (1.0 if sg > 0 else -2.4), (2.4 if sg > 0 else -1.0), 0.58, 0.63,
         M_DARK, 0.0, parent=HOOD, outline=None)
# llantas
WHEELS = []
for wx in (13.5, -13.5):
    for sg in (-1, 1):
        wl = empty(f"Rueda_{wx}_{sg}", "Carro", parent=CAR, loc=(wx, sg * 8.0, 3.3))
        WHEELS.append(wl)
        HIDE_GROUPS["car"].append(wl)
        # dirección del exterior de la rueda
        mo = Matrix.Rotation(-sg * math.pi / 2, 4, "X")   # Z del torno -> hacia afuera (±Y)
        V, Fc, M = lathe([(2.25, -1.3), (3.0, -1.35), (3.25, -1.1), (3.32, -0.6), (3.32, 0.6), (3.25, 1.1),
                          (3.0, 1.35), (2.25, 1.3)], 40, mo)
        Fc = Fc[:-2] if len(Fc) > 40 * 7 else Fc
        ob = make_obj(f"Llanta_{wx}_{sg}", V, Fc, [M_RUBBER], [0] * len(Fc), coll="Carro", parent=wl,
                      outline="car", recalc=False)
        HIDE_GROUPS["car"].append(ob)
        V, Fc, M = lathe([(0.0, 0.9), (0.45, 0.95), (0.5, 1.05), (2.1, 1.0), (2.3, 1.18), (2.32, 1.3),
                          (2.3, -1.1), (2.0, -1.0), (1.6, 0.6), (0.0, 0.6)], 40, mo)
        rim = make_obj(f"Rin_{wx}_{sg}", V, Fc, [M_CHROME], M, coll="Carro", parent=wl, outline="car")
        cutters = []
        for k in range(5):
            a = 2 * math.pi * k / 5
            c = cutter_cyl(0.55, -2.0, 2.0, 1.4 * math.cos(a), 1.4 * math.sin(a), 20)
            scene.collection.objects.link(c)
            cutters.append(c)
        apply_boolean_holes(rim, cutters)
        HIDE_GROUPS["car"].append(rim)
        V, Fc, M = lathe([(0.0, 0.0), (2.0, 0.0), (2.0, 0.25), (0.0, 0.25)], 40, mo @ Matrix.Translation((0, 0, 0.1)))
        ob = make_obj(f"Disco_{wx}_{sg}", V, Fc, [M_STEEL], M, coll="Carro", parent=wl, outline=None)
        HIDE_GROUPS["car"].append(ob)
        parts = []
        for k in range(5):
            a = 2 * math.pi * k / 5 + 0.6
            parts.append(lathe([(0.0, 0.0), (0.12, 0.0), (0.12, 0.2), (0.0, 0.2)], 6,
                               mo @ Matrix.Translation((0.55 * math.cos(a), 0.55 * math.sin(a), 1.0)), 0))
        V, Fc, M = merge(parts)
        ob = make_obj(f"Birlos_{wx}_{sg}", V, Fc, [M_CHROME], M, coll="Carro", parent=wl, outline=None)
        HIDE_GROUPS["car"].append(ob)
        # caliper (no gira)
        ob = cbox(f"Caliper_{wx}_{sg}", wx - 0.9, wx + 0.9, sg * 7.2 - 0.25, sg * 7.2 + 0.25, 4.9, 5.6, M_YELLOW,
                  0.15, outline=None)
        V, Fc, M = lathe([(0.0, 0.0), (3.95, 0.0), (3.95, 0.6), (0.0, 0.6)], 40,
                         axis_matrix((wx, sg * 6.0, 3.3), (0, sg, 0)))
        ob = make_obj(f"Paso_rueda_{wx}_{sg}", V, Fc, [M_BAY], M, coll="Carro", parent=CAR, outline=None)
        HIDE_GROUPS["car"].append(ob)
# luces de los faros (iluminan el camino)
for sg in (-1, 1):
    ld = bpy.data.lights.new(f"FaroLuz_{sg}", "SPOT")
    ld.energy = 9000
    ld.color = (1.0, 0.9, 0.75)
    ld.spot_size = math.radians(55)
    ld.spot_blend = 0.6
    ob = bpy.data.objects.new(f"FaroLuz_{sg}", ld)
    COLLS["Carro"].objects.link(ob)
    ob.parent = CAR
    ob.location = (24.0, sg * 6.3, 6.1)
    ob.rotation_euler = (0, math.radians(-80), 0)
    HIDE_GROUPS["car"].append(ob)

# ====================================================================== PUENTE
BX0, BX1 = -420.0, 900.0
TOWERS = (-170.0, 330.0)


def pbox(name, *a, mat=M_BRSTEEL, bevel=0.0, outline="bridge"):
    ob = box(name, *a, [mat], "Puente", None, bevel=bevel, outline=outline)
    HIDE_GROUPS["bridge"].append(ob)
    return ob


def arr(ob, count, dx):
    m = ob.modifiers.new("Arreglo", "ARRAY")
    m.count = count
    m.use_relative_offset = False
    m.use_constant_offset = True
    m.constant_offset_displace = (dx, 0, 0)
    ob.modifiers.move(len(ob.modifiers) - 1, 0)
    return m


def mirror_y(ob):
    m = ob.modifiers.new("Espejo", "MIRROR")
    m.use_axis = (False, True, False)
    ob.modifiers.move(len(ob.modifiers) - 1, 0)


pbox("Calzada", BX0, BX1, -20.5, 20.5, -1.2, 0.0, mat=M_ASPH, outline=None)
d = pbox("Raya_central", 0, 6, -0.25, 0.25, 0.0, 0.05, mat=M_LANE_Y, outline=None)
d.location.x = BX0
arr(d, 110, 12.0)
for sg in (-1, 1):
    pbox(f"Raya_orilla_{sg}", BX0, BX1, sg * 18.6 - 0.2, sg * 18.6 + 0.2, 0.0, 0.05, mat=M_LANE_W, outline=None)
    pbox(f"Banqueta_{sg}", BX0, BX1, *(sorted((sg * 20.5, sg * 25.6))), -1.2, 0.9, mat=M_CONC)
    pbox(f"Larguero_sup_{sg}", BX0, BX1, *(sorted((sg * 25.5, sg * 26.6))), -1.8, -0.8)
    pbox(f"Larguero_inf_{sg}", BX0, BX1, *(sorted((sg * 25.5, sg * 26.6))), -10.0, -9.0)
for zr in (6.2, 3.6):
    ob = pbox(f"Barandal_{zr}", BX0, BX1, 24.6, 25.2, zr - 0.3, zr + 0.2, mat=M_CHROME)
    mirror_y(ob)
post = pbox("Poste_barandal", 0, 0.5, 24.65, 25.15, 0.9, 6.0, mat=M_BRSTEEL)
post.location.x = BX0
arr(post, 264, 5.0)
mirror_y(post)
# armadura en X bajo el tablero
V, Fc, M = merge([tube_data([(0, 26.05, -1.6), (5, 26.05, -9.2)], 0.28, 6)[:3],
                  tube_data([(5, 26.05, -9.2), (10, 26.05, -1.6)], 0.28, 6)[:3],
                  tube_data([(0, 26.05, -9.2), (0, 26.05, -1.6)], 0.32, 6)[:3]])
tr = make_obj("Armadura", V, Fc, [M_BRSTEEL], M, coll="Puente", smooth=False, outline=None)
tr.location.x = BX0
arr(tr, 132, 10.0)
mirror_y(tr)
HIDE_GROUPS["bridge"].append(tr)
# postes de luz
parts = [lathe([(0.0, 0.0), (0.5, 0.0), (0.4, 1.0), (0.32, 1.2), (0.28, 30.0), (0.0, 30.2)], 10,
               Matrix.Translation((0, -23.2, 0.9)), 0),
         box_data(-0.25, 0.25, -23.4, -17.0, 29.6, 30.2, 0),
         box_data(-0.9, 0.9, -18.4, -15.4, 29.0, 29.8, 0),
         box_data(-0.75, 0.75, -18.25, -15.55, 28.85, 29.0, 1)]
V, Fc, M = merge(parts)
lamp = make_obj("Postes_luz", V, Fc, [M_BRSTEEL, M_LAMP], M, coll="Puente", outline=None)
lamp.location.x = BX0 + 20
arr(lamp, 33, 40.0)
mirror_y(lamp)
HIDE_GROUPS["bridge"].append(lamp)


# torres y cables
def cable_z(x):
    t0, t1 = TOWERS
    mid = 0.5 * (t0 + t1)
    if t0 <= x <= t1:
        return 14.0 + 115.0 * ((x - mid) / (0.5 * (t1 - t0))) ** 2
    if x < t0:
        return 129.0 - (t0 - x) / (t0 - BX0) * 124.0
    return 129.0 - (x - t1) / (BX1 - t1) * 124.0


for tx in TOWERS:
    for sg in (-1, 1):
        pbox(f"Torre_{tx}_{sg}", tx - 3.5, tx + 3.5, *(sorted((sg * 26.8, sg * 33.0))), -80.0, 128.0, bevel=0.6)
    for zb in (48.0, 95.0, 124.0):
        pbox(f"Viga_{tx}_{zb}", tx - 2.5, tx + 2.5, -33.0, 33.0, zb - 2.0, zb + 2.0, bevel=0.4)
for sg in (-1, 1):
    xs = np.linspace(BX0, BX1, 400)
    pts = [(x, sg * 29.8, cable_z(x)) for x in xs]
    V, Fc, M = tube_data(pts, 0.9, 8)
    ob = make_obj(f"Cable_principal_{sg}", V, Fc, [M_BRSTEEL], M, coll="Puente", outline="bridge")
    HIDE_GROUPS["bridge"].append(ob)
    parts = []
    for x in np.arange(TOWERS[0] + 10, TOWERS[1] - 5, 10.0):
        z = cable_z(x)
        parts.append(tube_data([(x, sg * 29.8, 0.9), (x, sg * 29.8, z)], 0.17, 5)[:3])
    V, Fc, M = merge(parts)
    ob = make_obj(f"Tirantes_{sg}", V, Fc, [M_BRSTEEL], M, coll="Puente", smooth=False, outline=None)
    HIDE_GROUPS["bridge"].append(ob)

# ====================================================================== ANIMACIÓN
INTERP = {"CONSTANT": 0, "LINEAR": 1, "BEZIER": 2}


def bake(idblock, path, index, values, interp="LINEAR", scalar=False):
    values = np.asarray(values, float)
    if path in ("hide_render", "lens", "energy") or path.endswith(".thickness"):
        scalar = True
    idblock.keyframe_insert(path, index=-1 if scalar else index, frame=0)
    ad = idblock.animation_data
    cb = anim_utils.action_get_channelbag_for_slot(ad.action, ad.action_slot)
    fc = cb.fcurves.find(path, index=index)
    kp = fc.keyframe_points
    n = len(values)
    if len(kp) < n:
        kp.add(n - len(kp))
    co = np.empty(2 * n)
    co[0::2] = FR[:n]
    co[1::2] = values
    kp.foreach_set("co", co)
    kp.foreach_set("interpolation", [INTERP[interp]] * n)
    fc.update()


def bake_vec(ob, path, arr3, interp="LINEAR"):
    arr3 = np.asarray(arr3)
    for i in range(arr3.shape[1]):
        bake(ob, path, i, arr3[:, i], interp)


def smooth(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def ease_in(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x


# --- carro
car_loc = np.array([[rc.car_x(f), rc.CAR_Y, 0.0] for f in FR])
bake_vec(CAR, "location", car_loc)
dist = car_loc[:, 0] - car_loc[0, 0]
for wl in WHEELS:
    bake(wl, "rotation_euler", 1, dist / 3.32)

# --- motor: eje, lóbulo, rotor, poleas
alpha = np.array([rc.alpha(f) for f in FR])
bake(SHAFT, "rotation_euler", 1, -alpha)
bake(PULLEY, "rotation_euler", 1, -alpha)
PULLEY.location = (0, 0, 0)
WP_PULLEY.location = (WP[0], 0, WP[1])
for v in WP_PULLEY.data.vertices:
    v.co.x -= WP[0]
    v.co.z -= WP[1]
bake(WP_PULLEY, "rotation_euler", 1, -alpha * PUL_R["main"] / PUL_R["wp"])
bake(ALT_ROT, "rotation_euler", 1, -alpha * PUL_R["main"] / PUL_R["alt"])
centers = np.array([rc.rotor_pose(f)[0] for f in FR])
phis = np.array([rc.rotor_pose(f)[1] for f in FR])
loc_c = np.stack([centers[:, 0], np.zeros(NF), centers[:, 1]], 1)
bake_vec(LOBE, "location", loc_c)
bake(LOBE, "rotation_euler", 1, -alpha)
bake_vec(ROTOR, "location", loc_c)
bake(ROTOR, "rotation_euler", 1, -phis)


def fly(f0, f_jolt, f_gone, f_back0, f_back1, jolt, vec, rot):
    """Trayectoria de una pieza que se abre, sale volando y luego regresa."""
    loc = np.zeros((NF, 3))
    eul = np.zeros((NF, 3))
    for i, f in enumerate(FR):
        if f < f0:
            k_j, k_f = 0.0, 0.0
        elif f < f_jolt:
            k_j, k_f = smooth((f - f0) / (f_jolt - f0)), 0.0
        elif f < f_back0:
            k_j, k_f = 1.0, float(ease_in((f - f_jolt) / (f_gone - f_jolt)) * 1.0)
            k_f = min(k_f, 1.0)
        elif f < f_back1:
            t = float(smooth((f - f_back0) / (f_back1 - f_back0)))
            k_j, k_f = 1.0 - t, 1.0 - t
        else:
            k_j, k_f = 0.0, 0.0
        loc[i] = np.array(jolt) * k_j + np.array(vec) * k_f
        eul[i] = np.array(rot) * k_f
    return loc, eul


# frente del motor: se abre en rotor_open, regresa al salir
fl, fe = fly(F["rotor_open"], F["rotor_open"] + 5, F["rotor_open"] + 24, F["out"] + 2, F["out"] + 22,
             (0, -0.25, 0.0), (-7.0, -4.0, 6.0), (math.radians(-75), math.radians(30), math.radians(40)))
bake_vec(FRONT, "location", fl)
bake_vec(FRONT, "rotation_euler", fe)
vis_front = np.array([0.0 if (F["rotor_open"] + 24 <= f < F["out"] + 2) else 1.0 for f in FR])
for ob in [FRONT] + [o for o in FRONT.children_recursive]:
    bake(ob, "hide_render", 0, 1.0 - vis_front, "CONSTANT")

# cara del rotor: sigue al rotor y en eje_open sale volando
rl = np.zeros((NF, 3))
re_ = np.zeros((NF, 3))
f_lock = F["eje_open"]
fl2, fe2 = fly(F["eje_open"], F["eje_open"] + 4, F["eje_open"] + 22, F["out"] - 2, F["out"] + 12,
               (0, -0.12, 0), (4.0, -2.5, 3.5), (math.radians(-60), math.radians(-45), math.radians(-30)))
for i, f in enumerate(FR):
    if F["eje_open"] <= f < F["out"] + 12:
        # durante el vuelo se queda con la pose del rotor del momento en que se abrió (o la actual al regresar)
        ref = f_lock if f < F["out"] - 2 else f
        c, ph = rc.rotor_pose(ref)
    else:
        c, ph = rc.rotor_pose(f)
    rl[i] = (c[0] + fl2[i, 0], fl2[i, 1], c[1] + fl2[i, 2])
    re_[i] = (fe2[i, 0], -ph + fe2[i, 1], fe2[i, 2])
bake_vec(ROTOR_PLATE, "location", rl)
bake_vec(ROTOR_PLATE, "rotation_euler", re_)
vis_plate = np.array([0.0 if (F["eje_open"] + 22 <= f < F["out"] - 2) else 1.0 for f in FR])
for ob in [ROTOR_PLATE] + list(ROTOR_PLATE.children_recursive):
    bake(ob, "hide_render", 0, 1.0 - vis_plate, "CONSTANT")

# capó: se suelta, se levanta y sale volando; al final regresa
hl = np.zeros((NF, 3))
he = np.zeros((NF, 3))
HO, HB0, HB1 = F["hood_open"], 838, 856
for i, f in enumerate(FR):
    if HO <= f < HO + 5:          # clac: el seguro se suelta
        t = float(smooth((f - HO) / 5))
        he[i] = (0, math.radians(-6) * t, 0)
    elif HO + 5 <= f < HB0:       # se levanta y sale volando hacia atrás
        t = (f - HO - 5) / 20.0
        k = float(ease_in(min(t, 1.2)))
        he[i] = (math.radians(25) * k, math.radians(-6) - math.radians(170) * k, math.radians(20) * k)
        hl[i] = (-30.0 * k, -6.0 * k, 26.0 * k + 4.0 * float(smooth(t * 3)))
    elif HB0 <= f < HB1:          # regresa
        t = 1.0 - float(smooth((f - HB0) / (HB1 - HB0)))
        he[i] = (math.radians(25) * t, -math.radians(176) * t, math.radians(20) * t)
        hl[i] = (-30.0 * t, -6.0 * t, 30.0 * t)
hl += np.array([7.3, 0.0, 9.05])
bake_vec(HOOD, "location", hl)
bake_vec(HOOD, "rotation_euler", he)
vis_hood = np.array([0.0 if (HO + 30 <= f < HB0) else 1.0 for f in FR])
for ob in [HOOD] + list(HOOD.children_recursive):
    bake(ob, "hide_render", 0, 1.0 - vis_hood, "CONSTANT")

# carro y puente se ocultan mientras estamos dentro del motor
SHOW_AGAIN = 836
vis_world = np.array([0.0 if (F["rotor"] + 2 <= f < SHOW_AGAIN) else 1.0 for f in FR])
for ob in HIDE_GROUPS["car"] + HIDE_GROUPS["bridge"]:
    if ob.name.startswith("Capo") or ob in HOOD.children_recursive:
        continue
    bake(ob, "hide_render", 0, 1.0 - vis_world, "CONSTANT")
    for ch in ob.children_recursive:
        if ch.type in ("MESH", "LIGHT"):
            bake(ch, "hide_render", 0, 1.0 - vis_world, "CONSTANT")

# ====================================================================== CÁMARA
E2C = rc.engine_to_car


def EC(u, y, v):
    return E2C((u, y, v))


W0 = np.array([-10.0, -95.0, 26.0])
W0T = np.array([-10.0, -9.0, 13.0])
# (cuadro, posición, objetivo, ángulo vertical, se detiene)
KEYS = [
    (84, (0.0, -86.0, 26.0), (0.0, 0.0, 13.0), 62, True),
    (104, (46.0, -13.0, 30.0), (14.0, 0.0, 9.0), 54, False),
    (124, (30.0, -12.0, 23.0), (14.0, 0.0, 8.4), 47, True),
    (140, (29.0, -11.5, 22.5), (14.0, 0.0, 8.2), 47, True),
    (162, (22.5, -9.5, 16.5), (12.4, 0.3, 4.9), 43, False),
    (244, (20.5, -10.5, 15.0), (12.2, 0.3, 4.7), 43, True),
    (276, EC(0.35, -1.0 - 13.0, 1.3), EC(0.0, -1.0, 0.15), 45, False),
    (292, EC(0.25, -1.0 - 9.0, 0.8), EC(0.0, -1.0, 0.1), 45, False),
    (322, EC(0.2, -1.0 - 5.6, 0.5), EC(0.0, -1.0, 0.05), 45, False),
    (358, EC(0.3, -1.0 - 5.3, 0.55), EC(0.0, -1.0, 0.05), 45, True),
    (382, EC(-0.15, -1.0 - 6.0, 0.75), EC(-0.35, -1.0, 0.45), 45, False),
    (440, EC(-0.10, -1.0 - 5.8, 0.80), EC(-0.30, -1.0, 0.45), 45, True),
    (468, EC(0.10, -1.0 - 5.7, 0.95), EC(0.0, -1.0, 0.6), 45, False),
    (524, EC(0.12, -1.0 - 5.6, 0.92), EC(0.02, -1.0, 0.55), 45, True),
    (552, EC(0.30, -1.0 - 5.4, 0.30), EC(0.35, -1.0, 0.05), 45, False),
    (608, EC(0.32, -1.0 - 5.3, 0.25), EC(0.35, -1.0, 0.0), 45, True),
    (636, EC(-0.20, -1.0 - 5.9, -0.15), EC(-0.40, -1.0, -0.40), 45, False),
    (692, EC(-0.18, -1.0 - 5.8, -0.12), EC(-0.38, -1.0, -0.38), 45, True),
    (728, EC(0.95, -1.1 - 3.4, 0.85), EC(0.0, -1.05, 0.0), 45, False),
    (738, EC(0.92, -1.1 - 3.3, 0.82), EC(0.0, -1.05, 0.0), 45, False),
    (762, EC(0.75, -1.1 - 2.8, 0.70), EC(0.0, -1.0, 0.0), 45, False),
    (802, EC(0.70, -1.1 - 2.7, 0.65), EC(0.0, -1.0, 0.0), 45, True),
    (830, EC(0.3, -1.0 - 14.0, 1.2), EC(0.0, -1.0, 0.3), 45, False),
    (846, (16.0, -13.0, 19.0), (8.0, 0.0, 6.0), 50, False),
    (858, (-52.0, -6.0, 14.5), (60.0, 0.0, 8.0), 50, True),
]


def hermite(keys, f, idx):
    ts = [k[0] for k in keys]
    if f <= ts[0]:
        return np.array(keys[0][idx], float)
    if f >= ts[-1]:
        return np.array(keys[-1][idx], float)
    i = max(j for j in range(len(ts) - 1) if ts[j] <= f)
    t0, t1 = ts[i], ts[i + 1]
    p0, p1 = np.array(keys[i][idx], float), np.array(keys[i + 1][idx], float)

    def tangent(j):
        if keys[j][4] or j == 0 or j == len(keys) - 1:
            return np.zeros_like(p0)
        return (np.array(keys[j + 1][idx], float) - np.array(keys[j - 1][idx], float)) / (ts[j + 1] - ts[j - 1])

    m0, m1 = tangent(i) * (t1 - t0), tangent(i + 1) * (t1 - t0)
    t = (f - t0) / (t1 - t0)
    h00 = 2 * t ** 3 - 3 * t ** 2 + 1
    h10 = t ** 3 - 2 * t ** 2 + t
    h01 = -2 * t ** 3 + 3 * t ** 2
    h11 = t ** 3 - t ** 2
    return h00 * p0 + h10 * m0 + h01 * p1 + h11 * m1


cam_loc = np.zeros((NF, 3))
cam_tgt = np.zeros((NF, 3))
cam_fov = np.zeros(NF)
END_W = None
for i, f in enumerate(FR):
    carp = np.array([rc.car_x(f), rc.CAR_Y, 0.0])
    if f < 84:
        k = float(smooth((f - 30) / 40.0))
        lw = (1 - k) * W0 + k * (carp + np.array(KEYS[0][1]))
        tw = (1 - k) * W0T + k * (carp + np.array(KEYS[0][2]))
        cam_loc[i], cam_tgt[i], cam_fov[i] = lw, tw, 62.0
    elif f < KEYS[-1][0]:
        cam_loc[i] = carp + hermite(KEYS, f, 1)
        cam_tgt[i] = carp + hermite(KEYS, f, 2)
        cam_fov[i] = float(hermite(KEYS, f, 3))
    else:
        if END_W is None:
            c0 = np.array([rc.car_x(KEYS[-1][0]), rc.CAR_Y, 0.0])
            END_W = (c0 + np.array(KEYS[-1][1]), c0 + np.array(KEYS[-1][2]))
        cam_loc[i], cam_tgt[i], cam_fov[i] = END_W[0], END_W[1], 50.0

cam_data = bpy.data.cameras.new("Camara")
cam_data.sensor_fit = "VERTICAL"
cam_data.sensor_height = 24.0
cam_data.clip_start = 0.05
cam_data.clip_end = 3000.0
cam_data.shift_y = 0.05
CAM = bpy.data.objects.new("Camara", cam_data)
scene.collection.objects.link(CAM)
scene.camera = CAM
CAM.rotation_mode = "QUATERNION"
quats = []
for i in range(NF):
    fwd = Vector(cam_tgt[i] - cam_loc[i]).normalized()
    x = fwd.cross(Vector((0, 0, 1)))
    if x.length < 1e-6:
        x = Vector((1, 0, 0))
    x.normalize()
    y = x.cross(fwd)
    m = Matrix((x, y, -fwd)).transposed()
    quats.append(tuple(m.to_quaternion()))
quats = np.array(quats)
for i in range(1, NF):
    if np.dot(quats[i], quats[i - 1]) < 0:
        quats[i] = -quats[i]
bake_vec(CAM, "location", cam_loc)
bake_vec(CAM, "rotation_quaternion", quats)
lens = 0.5 * 24.0 / np.tan(np.radians(cam_fov) / 2)
bake(cam_data, "lens", 0, lens)

# --- grosor del contorno según la distancia a la cámara (siempre ~1 pixel)
eng_center = np.array([np.array(rc.engine_to_car((0, -0.6, 0.4))) + np.array([rc.car_x(f), rc.CAR_Y, 0]) for f in FR])
car_center = car_loc + np.array([0, 0, 6.0])


def px_size(dist_):
    return 2 * dist_ * np.tan(np.radians(cam_fov) / 2) / rc.RES_Y


th_eng = 1.15 * px_size(np.linalg.norm(cam_loc - eng_center, axis=1)) / rc.ENGINE_SCALE
th_car = 1.15 * px_size(np.linalg.norm(cam_loc - car_center, axis=1))
th_br = np.maximum(th_car, 0.12)
for grp, th in (("engine", np.clip(th_eng, 0.004, 0.05)), ("car", np.clip(th_car, 0.03, 0.6)),
                ("bridge", np.clip(th_br, 0.1, 1.2))):
    for ob in OUTLINE_GROUPS[grp]:
        if ob.type != "MESH":
            continue
        ob.data.materials.append(M_OUT)
        mod = ob.modifiers.new("Contorno", "SOLIDIFY")
        mod.thickness = float(th[0])
        mod.offset = 1.0
        mod.use_flip_normals = True
        mod.use_rim = False
        mod.use_even_offset = False
        mod.material_offset = len(ob.data.materials) - 1
        mod.material_offset_rim = len(ob.data.materials) - 1
        bake(ob, 'modifiers["Contorno"].thickness', 0, th)

# ====================================================================== LUCES Y MUNDO
world = bpy.data.worlds.new("Estudio")
scene.world = world
world.use_nodes = True
nt = world.node_tree
nt.nodes.clear()
wo = nt.nodes.new("ShaderNodeOutputWorld")
bg = nt.nodes.new("ShaderNodeBackground")
bg.inputs["Strength"].default_value = 0.7
tc = nt.nodes.new("ShaderNodeTexCoord")
sep = nt.nodes.new("ShaderNodeSeparateXYZ")
ramp = nt.nodes.new("ShaderNodeValToRGB")
cr = ramp.color_ramp
cr.interpolation = "LINEAR"
cr.elements[0].position = 0.0
cr.elements[0].color = (0.012, 0.012, 0.016, 1)     # suelo oscuro
cr.elements[1].position = 0.485
cr.elements[1].color = (0.04, 0.04, 0.05, 1)
for pos, col in ((0.50, (0.45, 0.46, 0.5, 1)),      # horizonte gris
                 (0.525, (0.5, 0.5, 0.54, 1)),
                 (0.545, (2.6, 2.5, 2.35, 1)),        # banda de luz
                 (0.60, (2.6, 2.5, 2.35, 1)),
                 (0.64, (0.22, 0.23, 0.27, 1)),
                 (1.0, (0.07, 0.08, 0.1, 1))):
    e = cr.elements.new(pos)
    e.color = col
mapr = nt.nodes.new("ShaderNodeMapRange")
mapr.inputs["From Min"].default_value = -1.0
mapr.inputs["From Max"].default_value = 1.0
nt.links.new(tc.outputs["Generated"], sep.inputs[0])
nt.links.new(sep.outputs[2], mapr.inputs["Value"])
nt.links.new(mapr.outputs["Result"], ramp.inputs["Fac"])
nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
nt.links.new(bg.outputs[0], wo.inputs["Surface"])


def sun(name, energy, color, d_cam, angle=2.0):
    ld = bpy.data.lights.new(name, "SUN")
    ld.energy = energy
    ld.color = color
    ld.angle = math.radians(angle)
    ob = bpy.data.objects.new(name, ld)
    COLLS["Luces"].objects.link(ob)
    ob.parent = CAM
    ob.rotation_mode = "QUATERNION"
    ob.rotation_quaternion = Vector((0, 0, -1)).rotation_difference(Vector(d_cam).normalized())
    return ob


sun("Luz_principal_calida", 3.2, (1.0, 0.86, 0.7), (0.45, -0.5, -1.0))
sun("Luz_contorno_azul", 4.5, (0.5, 0.68, 1.0), (-0.35, -0.55, 1.0))

# luz del fuego dentro de la cámara de combustión y chispa de las bujías
fire = bpy.data.lights.new("Fuego", "POINT")
fire.color = (1.0, 0.45, 0.1)
fire.shadow_soft_size = 0.2
FIRE = bpy.data.objects.new("Fuego", fire)
COLLS["Luces"].objects.link(FIRE)
FIRE.parent = ENGINE
spark = bpy.data.lights.new("Chispa", "POINT")
spark.color = (0.7, 0.85, 1.0)
spark.shadow_soft_size = 0.05
SPARK = bpy.data.objects.new("Chispa", spark)
COLLS["Luces"].objects.link(SPARK)
SPARK.parent = ENGINE
tip = rc.plug_tip(0.0)
SPARK.location = (tip[0] - 0.15, Yc - 0.25, tip[1])
f_ign = F["comb"] + 6
fire_loc = np.zeros((NF, 3))
fire_e = np.zeros(NF)
spark_e = np.zeros(NF)
for i, f in enumerate(FR):
    cu_, cv_ = rc.chamber_centroid(f)
    fire_loc[i] = (cu_, Yc - 0.35, cv_)
    if f_ign <= f < F["esc"]:
        t = (f - f_ign) / (F["esc"] - f_ign)
        fire_e[i] = 6.0 * (1 - math.exp(-(f - f_ign) / 3.0)) * (1 - 0.65 * t) * (0.85 + 0.15 * math.sin(f * 1.7))
    elif F["esc"] <= f < F["esc"] + 60:
        fire_e[i] = 2.1 * (1 - (f - F["esc"]) / 60.0)
    if f_ign - 2 <= f < f_ign + 5:
        spark_e[i] = 3.0 * (1 if int(f) % 2 == 0 else 0.6)
bake_vec(FIRE, "location", fire_loc)
bake(fire, "energy", 0, fire_e)
bake(spark, "energy", 0, spark_e)

# ====================================================================== RENDER
scene.render.resolution_x = rc.RES_X
scene.render.resolution_y = rc.RES_Y
scene.render.resolution_percentage = 100
scene.render.fps = rc.FPS
scene.frame_start = 0
scene.frame_end = NF - 1
scene.render.film_transparent = True
scene.render.filter_size = 0.0
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.render.image_settings.color_depth = "8"
scene.view_settings.view_transform = "Standard"
scene.view_settings.look = "None"
scene.render.use_overwrite = False
scene.render.use_placeholder = True
if ENGINE == "CYCLES":
    scene.render.engine = "CYCLES"
    scene.cycles.samples = SAMPLES or 48
    scene.cycles.use_denoising = True
    scene.cycles.pixel_filter_type = "BOX"
    scene.cycles.filter_width = 0.01
    scene.cycles.max_bounces = 6
    scene.cycles.transparent_max_bounces = 16
    if USE_GPU:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        for dev_type in ("OPTIX", "CUDA"):
            try:
                prefs.compute_device_type = dev_type
                prefs.get_devices()
                for dvc in prefs.devices:
                    dvc.use = True
                scene.cycles.device = "GPU"
                break
            except Exception:
                continue
else:
    scene.render.engine = "BLENDER_EEVEE"
    scene.eevee.taa_render_samples = SAMPLES or 16
    scene.eevee.use_shadows = True
    scene.eevee.use_raytracing = False
    scene.eevee.shadow_ray_count = 2
    scene.eevee.shadow_step_count = 6

# ====================================================================== DATOS PARA EL POSTPROCESO
CAM_JSON = os.path.join(OUT, "camara_por_cuadro.json")
SKIP_EXPORT = bool(_opt("--reanudar", False)) and os.path.exists(CAM_JSON)
print("Exportando matrices de cámara..." if not SKIP_EXPORT else "Reanudando: se usan los datos ya exportados")
data = {"frames": [], "res": [rc.RES_X, rc.RES_Y]}
for f in ([] if SKIP_EXPORT else range(NF)):
    scene.frame_set(f)
    dg = bpy.context.evaluated_depsgraph_get()
    proj = CAM.calc_matrix_camera(dg, x=rc.RES_X, y=rc.RES_Y)
    view = CAM.matrix_world.inverted()
    P = proj @ view
    data["frames"].append({
        "P_engine": [list(r) for r in (P @ ENGINE.matrix_world)],
        "P_car": [list(r) for r in (P @ CAR.matrix_world)],
        "P_world": [list(r) for r in P],
    })
scene.frame_set(0)
if not SKIP_EXPORT:
    with open(CAM_JSON, "w") as fh:
        json.dump(data, fh)
    blend_path = os.path.join(OUT, "motor_rotativo.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print("Guardado:", blend_path)


def parse_frames(arg):
    if not arg or arg is True:
        return list(range(NF))
    out = []
    for part in str(arg).split(","):
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return [f for f in out if 0 <= f < NF]


if DO_RENDER:
    frames = parse_frames(FRAMES_ARG)
    t0 = time.time()
    for n, f in enumerate(frames):
        path = os.path.join(FRAMES_DIR, f"c_{f:04d}.png")
        if os.path.exists(path) and os.path.getsize(path) > 0:
            continue
        scene.frame_set(f)
        scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        el = time.time() - t0
        print(f"[{n + 1}/{len(frames)}] cuadro {f}  {el:.0f}s", flush=True)
    if len(frames) == NF:
        zpath = os.path.join(OUT, "cuadros_motor_rotativo.zip")
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_STORED) as z:
            for f in range(NF):
                p = os.path.join(FRAMES_DIR, f"c_{f:04d}.png")
                if os.path.exists(p):
                    z.write(p, arcname=f"cuadros/c_{f:04d}.png")
            z.write(os.path.join(OUT, "camara_por_cuadro.json"), arcname="camara_por_cuadro.json")
        print("ZIP listo:", zpath)
print("TERMINADO")
