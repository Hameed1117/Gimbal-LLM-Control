"""
Procedural 3-D model generator — writes CC0 OBJ files for scene entities.

Generated files live in  assets/models/  relative to the project root.
The generator runs once at startup and skips files that already exist,
so models can be replaced by any OBJ file downloaded from the web.
"""

import math
import os
import logging

logger = logging.getLogger(__name__)


# ── Math helpers ──────────────────────────────────────────────────────────────

def _v_sub(a, b):   return (a[0]-b[0], a[1]-b[1], a[2]-b[2])
def _v_cross(a, b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
def _v_len(v):      return math.sqrt(v[0]**2+v[1]**2+v[2]**2)
def _v_norm(v):
    l = _v_len(v)
    return (v[0]/l, v[1]/l, v[2]/l) if l > 1e-9 else (0.0, 1.0, 0.0)
def _face_normal(p0, p1, p2):
    return _v_norm(_v_cross(_v_sub(p1,p0), _v_sub(p2,p0)))


# ── Mesh builder ──────────────────────────────────────────────────────────────

class _MB:
    """Accumulates verts / faces, computes smooth per-vertex normals, exports OBJ."""

    def __init__(self):
        self.verts = []   # (x,y,z)
        self.tris  = []   # (i,j,k)  0-based
        self._vn_accum = {}   # vi -> [normal, …]

    # -- vertex ---------
    def v(self, x, y, z):
        self.verts.append((x, y, z))
        return len(self.verts) - 1

    # -- faces ----------
    def tri(self, a, b, c):
        fn = _face_normal(self.verts[a], self.verts[b], self.verts[c])
        self.tris.append((a, b, c))
        for vi in (a, b, c):
            self._vn_accum.setdefault(vi, []).append(fn)

    def quad(self, a, b, c, d):
        """Quad → two triangles (consistent winding)."""
        self.tri(a, b, c)
        self.tri(a, c, d)

    # -- smooth normals --
    def _smooth_normals(self):
        ns = []
        for vi in range(len(self.verts)):
            fl = self._vn_accum.get(vi, [(0,1,0)])
            avg = [sum(n[i] for n in fl)/len(fl) for i in range(3)]
            ns.append(_v_norm(tuple(avg)))
        return ns

    # -- export ----------
    def to_obj(self, name="model") -> str:
        normals = self._smooth_normals()
        lines = [f"# Generated model: {name}", "o " + name, ""]
        for x,y,z in self.verts:
            lines.append(f"v {x:.5f} {y:.5f} {z:.5f}")
        lines.append("")
        for nx,ny,nz in normals:
            lines.append(f"vn {nx:.4f} {ny:.4f} {nz:.4f}")
        lines.append("")
        lines.append(f"g {name}")
        for a,b,c in self.tris:
            lines.append(f"f {a+1}//{a+1} {b+1}//{b+1} {c+1}//{c+1}")
        return "\n".join(lines) + "\n"


# ── Sedan cross-section ────────────────────────────────────────────────────────

def _sedan_ring(x: float):
    """
    Return 12 (y, z) points for one sedan cross-section at longitudinal pos x.
    x: -0.36 (rear bumper) → +0.36 (front bumper)
    y: height above ground, z: half-width (positive = right)

    Ring goes clockwise when viewed from the +X direction:
      idx 0..5  = right half (z > 0) from bottom to roof-shoulder
      idx 6     = roof centre (z = 0, top)
      idx 7..11 = left half  (z < 0) from roof-shoulder to bottom
    """
    HW  = 0.186    # max half-width of body
    HWC = 0.145    # half-width of cabin

    # Smooth cabin blend: 1 in centre, 0 at bumpers
    t_raw = max(0.0, 1.0 - max(abs(x) - 0.16, 0.0) / 0.20)
    t = t_raw * t_raw * (3.0 - 2.0 * t_raw)   # smoothstep

    # Roof / cabin floor heights
    y_roof = 0.408 * t
    y_cf   = 0.195 * max(0.05, t)   # cabin floor (only meaningful when t > 0)

    # Body top (hood/trunk slope)
    span = abs(x) - 0.20
    if span > 0.0:
        slope = span / 0.16
        y_bt = 0.195 - 0.110 * min(1.0, slope)
    else:
        y_bt = 0.195

    # Half-widths
    hw_lo = HW * (0.78 + 0.22 * min(1.0, abs(x) * 0.6 + 0.55))   # narrow at bumpers
    hw_lo = min(hw_lo, HW)
    hw_hi = HWC + (HW * 0.95 - HWC) * (1.0 - t)   # cabin width → body width at edges

    # Build 12-point ring (6 right + centre + 5 left mirrored)
    if t > 0.05:
        # Full cabin zone
        pts_r = [
            (0.000,                             hw_lo * 0.78),   # 0  ground
            (y_bt * 0.40,                       hw_lo),          # 1  lower body
            (y_bt,                              hw_lo * 0.96),   # 2  body top / sill
            (y_cf,                              hw_hi),          # 3  cabin floor
            (y_cf + (y_roof - y_cf) * 0.55,    hw_hi * 0.94),   # 4  cabin mid
            (y_roof,                            hw_hi * 0.60),   # 5  roof shoulder
        ]
    else:
        # Bumper / hood / trunk — no cabin, tapered top
        y_top = y_bt
        pts_r = [
            (0.000,         hw_lo * 0.78),
            (y_top * 0.38,  hw_lo),
            (y_top * 0.72,  hw_lo * 0.95),
            (y_top * 0.90,  hw_lo * 0.78),
            (y_top,         hw_lo * 0.48),
            (y_top,         hw_lo * 0.20),
        ]
    y_top_actual = pts_r[5][0]

    ring = pts_r + [(y_top_actual, 0.0)]           # idx 6  roof/top centre
    ring += [(y, -z) for y, z in reversed(pts_r)]  # idx 7..11 left half
    return ring   # 12 points


def _gen_sedan(mb: _MB):
    """Sweep sedan cross-sections and add geometry to mb."""
    X = [-0.36, -0.28, -0.18, -0.08, 0.00, 0.10, 0.20, 0.28, 0.36]

    # Generate ring vertex indices
    rings = []
    for x in X:
        pts = _sedan_ring(x)
        N = len(pts)           # determined by _sedan_ring (currently 13)
        base = len(mb.verts)
        for (y, z) in pts:
            mb.v(x, y, z)
        rings.append((base, N))

    # Lateral quads between adjacent rings
    for ri in range(len(rings) - 1):
        a, Na = rings[ri]
        b, _  = rings[ri + 1]
        for j in range(Na):
            j1 = (j + 1) % Na
            mb.quad(a+j, a+j1, b+j1, b+j)

    # Front cap (triangle fan from centroid)
    fr, Nf = rings[-1]
    cx = X[-1]
    cy = sum(mb.verts[fr+j][1] for j in range(Nf)) / Nf
    fc = mb.v(cx, cy, 0.0)
    for j in range(Nf):
        mb.tri(fc, fr+j, fr+(j+1)%Nf)

    # Rear cap
    rr, Nr = rings[0]
    cy = sum(mb.verts[rr+j][1] for j in range(Nr)) / Nr
    rc = mb.v(X[0], cy, 0.0)
    for j in range(Nr - 1, -1, -1):
        mb.tri(rc, rr+j, rr+(j+1)%Nr)

    # Wheels  (4x cylinder approximations)
    _add_wheel(mb, x= 0.22, z= 0.20)
    _add_wheel(mb, x=-0.22, z= 0.20)
    _add_wheel(mb, x= 0.22, z=-0.20)
    _add_wheel(mb, x=-0.22, z=-0.20)


def _add_wheel(mb: _MB, x: float, z: float):
    """Add a tyre-shaped torus ring to the mesh."""
    segs = 16
    R_tyre = 0.098     # outer radius
    W_half = 0.032     # half-width along Z
    y = 0.0            # wheel centre height

    for i in range(segs):
        a0 = 2 * math.pi * i       / segs
        a1 = 2 * math.pi * (i + 1) / segs
        y0, r0 = R_tyre * math.sin(a0), R_tyre * math.cos(a0)
        y1, r1 = R_tyre * math.sin(a1), R_tyre * math.cos(a1)
        # Four verts of this quad strip section
        v0 = mb.v(x + W_half, y + y0, z + r0)
        v1 = mb.v(x + W_half, y + y1, z + r1)
        v2 = mb.v(x - W_half, y + y1, z + r1)
        v3 = mb.v(x - W_half, y + y0, z + r0)
        mb.quad(v0, v1, v2, v3)


# ── Mini-UAV ──────────────────────────────────────────────────────────────────

def _add_box(mb: _MB, cx, cy, cz, w, h, d):
    """Add an axis-aligned box centred at (cx,cy,cz)."""
    hw, hh, hd = w/2, h/2, d/2
    x0,x1 = cx-hw, cx+hw
    y0,y1 = cy-hh, cy+hh
    z0,z1 = cz-hd, cz+hd

    def _(x,y,z): return mb.v(x,y,z)

    # Each face = 4 new verts (no vertex sharing → flat normals per face)
    # +Y
    a,b,c,d_ = _(x0,y1,z0),_(x1,y1,z0),_(x1,y1,z1),_(x0,y1,z1)
    mb.quad(a,b,c,d_)
    # -Y
    a,b,c,d_ = _(x0,y0,z1),_(x1,y0,z1),_(x1,y0,z0),_(x0,y0,z0)
    mb.quad(a,b,c,d_)
    # +X
    a,b,c,d_ = _(x1,y0,z0),_(x1,y0,z1),_(x1,y1,z1),_(x1,y1,z0)
    mb.quad(a,b,c,d_)
    # -X
    a,b,c,d_ = _(x0,y0,z1),_(x0,y0,z0),_(x0,y1,z0),_(x0,y1,z1)
    mb.quad(a,b,c,d_)
    # +Z
    a,b,c,d_ = _(x0,y0,z1),_(x1,y0,z1),_(x1,y1,z1),_(x0,y1,z1)
    mb.quad(a,b,c,d_)
    # -Z
    a,b,c,d_ = _(x1,y0,z0),_(x0,y0,z0),_(x0,y1,z0),_(x1,y1,z0)
    mb.quad(a,b,c,d_)


def _add_cylinder(mb: _MB, cx, cy, cz, radius, height, segs=14, axis='y'):
    """Add a cylinder. axis: 'x','y','z'."""
    step = 2 * math.pi / segs
    top = []
    bot = []
    for i in range(segs):
        a = i * step
        c_, s_ = math.cos(a), math.sin(a)
        if axis == 'y':
            bot.append(mb.v(cx + radius*c_, cy,          cz + radius*s_))
            top.append(mb.v(cx + radius*c_, cy + height, cz + radius*s_))
        elif axis == 'z':
            bot.append(mb.v(cx + radius*c_, cy + radius*s_, cz))
            top.append(mb.v(cx + radius*c_, cy + radius*s_, cz + height))
        else:  # x
            bot.append(mb.v(cx,          cy + radius*c_, cz + radius*s_))
            top.append(mb.v(cx + height, cy + radius*c_, cz + radius*s_))
    # Side quads
    for i in range(segs):
        i1 = (i+1) % segs
        mb.quad(bot[i], bot[i1], top[i1], top[i])
    # Top cap
    tc = mb.v(cx, cy+height, cz) if axis == 'y' else mb.v(cx+(height if axis=='x' else 0), cy, cz+height)
    for i in range(segs):
        mb.tri(tc, top[i], top[(i+1)%segs])
    # Bottom cap
    bc = mb.v(cx, cy, cz)
    for i in range(segs-1, -1, -1):
        mb.tri(bc, bot[i], bot[(i-1)%segs])


def _gen_uav(mb: _MB):
    """Generate a DJI-Mini-style quadcopter mesh."""
    # Main body
    _add_box(mb, 0, 0.025, 0,  0.22, 0.052, 0.14)
    # Battery hump on top
    _add_box(mb, 0, 0.072, 0,  0.11, 0.034, 0.076)
    # Camera pod under front
    _add_cylinder(mb, 0.075, -0.036, 0, 0.026, 0.048, segs=10, axis='z')
    # 4 arms + motor pods
    for ax, az in ((0.26, 0.18), (-0.26, 0.18), (0.26, -0.18), (-0.26, -0.18)):
        # Arm (thin box)
        _add_box(mb, ax*0.5, 0, az*0.5,  abs(ax)*0.6+0.02, 0.012, abs(az)*0.4+0.02)
        # Motor pod
        _add_cylinder(mb, ax, -0.020, az, 0.028, 0.038, segs=10)
        # Prop disc (thin cylinder = disc)
        _add_cylinder(mb, ax,  0.022, az, 0.17,  0.008, segs=18)


# ── Seagull / bird ────────────────────────────────────────────────────────────

def _add_ellipsoid(mb: _MB, cx, cy, cz, rx, ry, rz, slices=14, stacks=8):
    """Scaled sphere = ellipsoid."""
    vbase = len(mb.verts)
    rings = []
    for j in range(stacks + 1):
        lat = math.pi * (-0.5 + j / stacks)
        yl = ry * math.sin(lat)
        rl = math.cos(lat)
        ring = []
        for i in range(slices):
            lng = 2 * math.pi * i / slices
            xv = cx + rx * rl * math.cos(lng)
            zv = cz + rz * rl * math.sin(lng)
            ring.append(mb.v(xv, cy + yl, zv))
        rings.append(ring)
    for j in range(stacks):
        for i in range(slices):
            i1 = (i+1) % slices
            mb.quad(rings[j][i], rings[j][i1], rings[j+1][i1], rings[j+1][i])


def _add_wing_mesh(mb: _MB, cx, cy, cz, sign, wing_span, chord, taper):
    """Add a single tapered wing panel (flat quad with slight dihedral)."""
    # Wing root and tip positions
    tip_z = cz + sign * wing_span
    tip_x_back  = cx - chord * taper
    tip_y = cy + wing_span * 0.08   # slight dihedral
    # 4 verts
    v0 = mb.v(cx + chord * 0.30, cy, cz)           # root leading edge
    v1 = mb.v(cx - chord * 0.70, cy, cz)           # root trailing edge
    v2 = mb.v(tip_x_back,        tip_y, tip_z)     # tip trailing
    v3 = mb.v(cx + chord * 0.30 * (1-taper*0.6),  tip_y, tip_z)  # tip leading
    if sign > 0:
        mb.quad(v0, v1, v2, v3)
    else:
        mb.quad(v0, v3, v2, v1)


def _gen_bird(mb: _MB):
    """Generate a seagull-like bird mesh with swept wings."""
    # Body
    _add_ellipsoid(mb, 0, 0, 0, 0.058, 0.042, 0.130, slices=12, stacks=7)
    # Head
    _add_ellipsoid(mb, 0, 0.048, 0.140, 0.040, 0.038, 0.040, slices=10, stacks=6)
    # Tail fan (flat box)
    _add_box(mb, 0, -0.010, -0.155,  0.058, 0.016, 0.080)
    # Wing panels (left and right)
    for sign in (+1, -1):
        # Inner wing
        _add_wing_mesh(mb, 0, 0.0, sign * 0.020, sign, 0.180, 0.095, 0.55)
        # Outer wing
        _add_wing_mesh(mb, -0.015, 0.012, sign * 0.200, sign, 0.130, 0.068, 0.70)


# ── Public API ────────────────────────────────────────────────────────────────

_MODELS = {
    "sedan.obj":    _gen_sedan,
    "quad_uav.obj": _gen_uav,
    "seagull.obj":  _gen_bird,
}


def ensure_models(assets_dir: str) -> dict:
    """
    Generate OBJ files in *assets_dir* if they don't already exist.
    Returns a dict  ``{stem: ObjMesh}`` for all successfully loaded models.

    Usage::

        meshes = ensure_models(os.path.join(base_dir, "assets", "models"))
        car_mesh = meshes.get("sedan")
    """
    os.makedirs(assets_dir, exist_ok=True)
    loaded = {}

    # Lazy import to avoid circular dependency
    from graphics.obj_loader import load_obj  # noqa: PLC0415

    for filename, gen_fn in _MODELS.items():
        path = os.path.join(assets_dir, filename)
        stem = filename.replace(".obj", "")

        if not os.path.exists(path):
            try:
                mb = _MB()
                gen_fn(mb)
                obj_text = mb.to_obj(name=stem)
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(obj_text)
                logger.info("Generated model: %s (%d verts, %d tris)",
                            filename, len(mb.verts), len(mb.tris))
            except Exception as exc:
                logger.error("Model generation failed for %s: %s", filename, exc)
                continue

        mesh = load_obj(path)
        if mesh is not None:
            loaded[stem] = mesh

    return loaded
