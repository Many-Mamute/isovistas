"""Isometric drawing of a part on an isometric grid (the format of the course exercises)."""
import json
import math
from build123d import Vector
from .canvas import Canvas
from .style import Style, SHEETS
from .geom import hlr, basis, faces_info

ISO_DIRS = {  # observer position -> viewing direction
    "fr": (-1, 1, -1), "fl": (1, 1, -1), "br": (-1, -1, -1), "bl": (1, -1, -1),
    "fr-low": (-1, 1, 1), "fl-low": (1, 1, 1),
}
K_ISO = math.sqrt(1.5)   # isometric drawing: axes in true length


def iso_drawing(model, out_prefix, view="fr", unit=10.0, sheet="A4", hidden=False, title=None, marks=True,
                png=True, pdf=True):
    S = Style()
    vd = ISO_DIRS.get(view, view)
    up = (0, 0, -1) if (isinstance(vd, tuple) and vd[2] > 0) else (0, 0, 1)
    vd, right, upv = basis(vd, (0, 0, 1))
    vis, hid = hlr(model.solid, vd, upv)
    k = K_ISO
    pts = [q for pl in vis for q in pl]
    x0, x1 = min(p[0] for p in pts) * k, max(p[0] for p in pts) * k
    y0, y1 = min(p[1] for p in pts) * k, max(p[1] for p in pts) * k
    W, H = SHEETS[sheet]
    cv = Canvas(W, H, S)
    fx0, fy0, fx1, fy1 = 20, 10, W - 10, H - 10
    # place the part centre in the drawing area, origin snapped to a grid node
    ax = [(Vector(*a).dot(right) * k, -Vector(*a).dot(upv) * k) for a in ((1, 0, 0), (0, 1, 0), (0, 0, 1))]
    cx = (fx0 + fx1) / 2 - (x0 + x1) / 2
    cy = (fy0 + fy1 + 12) / 2 + (y0 + y1) / 2
    # snap: origin must be a lattice node -> any point; the lattice is generated from the origin
    O = (cx, cy)
    T = lambda q: (O[0] + q[0] * k, O[1] - q[1] * k)
    # isometric grid: three families of lines through the lattice O + i*u*ax0 + j*u*ax1 (+ z)
    if unit:
        _iso_grid(cv, O, ax, unit, (fx0, fy0, fx1, fy1))
    if hidden:
        for pl in hid:
            cv.path([T(q) for q in pl], "hid")
    for pl in vis:
        cv.path([T(q) for q in pl], "vis")
    if marks:   # small crosses on the centres of circular edges seen in the drawing (hole/arc centres)
        seen = set()
        for f in faces_info(model.solid):
            if f["kind"] != "cyl" or not f["inner"] or f["ext"] < 359:
                continue
            for e in f["face"].edges():
                if e.geom_type.name != "CIRCLE":
                    continue
                c = e.arc_center
                key = (round(c.X, 2), round(c.Y, 2), round(c.Z, 2))
                if key in seen:
                    continue
                seen.add(key)
                q = T((c.dot(right), c.dot(upv)))
                if _near_vis(q, vis, T, e.radius * k):
                    s = 1.0
                    cv.line((q[0] - s, q[1] - s), (q[0] + s, q[1] + s), "thin")
                    cv.line((q[0] - s, q[1] + s), (q[0] + s, q[1] - s), "thin")
    cv.path([(fx0, fy0), (fx1, fy0), (fx1, fy1), (fx0, fy1)], "frame", close=True)
    name = title or model.spec.get("meta", {}).get("title") or model.spec.get("name", "")
    if unit:
        cv.text((fx0 + 3, fy0 + 7), f"{name} — 1 unidade do reticulado = {unit:g} mm".strip(" —"), h=3.5,
                anchor="start", track=False)
    open(out_prefix + ".svg", "w").write(cv.to_svg())
    if png:
        cv.to_mpl(out_prefix + ".png", dpi=150)
    if pdf:
        cv.to_mpl(out_prefix + ".pdf")
    rec = dict(view=view, dir=[vd.X, vd.Y, vd.Z], unit=unit, origin_paper=O, k=k, sheet=sheet,
               axes_paper=ax)
    json.dump(rec, open(out_prefix + ".info.json", "w"), indent=1)
    return rec


def _near_vis(q, vis, T, r):
    for pl in vis:
        for p in pl[:: max(1, len(pl) // 12)]:
            P = T(p)
            if abs(math.hypot(P[0] - q[0], P[1] - q[1]) - r) < r * 0.6 + 0.5:
                return True
    return False


def _iso_grid(cv, O, ax, unit, box):
    x0, y0, x1, y1 = box
    dirs = [ax[0], ax[1], ax[2]]
    for i, d in enumerate(dirs):
        L = math.hypot(*d)
        u = (d[0] / L, d[1] / L)
        o1, o2 = [dirs[j] for j in range(3) if j != i]
        # lattice step perpendicular to the family = one unit along another axis
        s = (o1[0] / math.hypot(*o1) * unit, o1[1] / math.hypot(*o1) * unit)
        n = (-u[1], u[0])
        step = abs(s[0] * n[0] + s[1] * n[1])
        c0 = O[0] * n[0] + O[1] * n[1]
        cs = [x * n[0] + y * n[1] for x in (x0, x1) for y in (y0, y1)]
        kmin = math.floor((min(cs) - c0) / step)
        kmax = math.ceil((max(cs) - c0) / step)
        for kk in range(kmin, kmax + 1):
            c = c0 + kk * step
            seg = _clip_line((n[0] * c, n[1] * c), u, box)
            if seg:
                cv.items.append(("path", (list(seg), "grid", False)))


def _clip_line(p, u, box):
    x0, y0, x1, y1 = box
    ts = []
    for t in ([(x0 - p[0]) / u[0], (x1 - p[0]) / u[0]] if abs(u[0]) > 1e-9 else []) + \
             ([(y0 - p[1]) / u[1], (y1 - p[1]) / u[1]] if abs(u[1]) > 1e-9 else []):
        q = (p[0] + u[0] * t, p[1] + u[1] * t)
        if x0 - 1e-6 <= q[0] <= x1 + 1e-6 and y0 - 1e-6 <= q[1] <= y1 + 1e-6:
            ts.append(t)
    if len(ts) < 2:
        return None
    a, b = min(ts), max(ts)
    return [(p[0] + u[0] * a, p[1] + u[1] * a), (p[0] + u[0] * b, p[1] + u[1] * b)]
