"""View definitions -> 2D geometry (HLR, sections, partial views, centre lines)."""
import math
from build123d import Vector
from .geom import hlr, basis, proj, cut, common, fuse, region, section_rings, faces_info, vol
from .spec import vec

STD = {  # first-angle standard views: view direction, up (for a main view)
    "front": ((0, 1, 0), (0, 0, 1)), "top": ((0, 0, -1), (0, 1, 0)), "left": ((1, 0, 0), (0, 0, 1)),
    "right": ((-1, 0, 0), (0, 0, 1)), "bottom": ((0, 0, 1), (0, -1, 0)), "rear": ((0, -1, 0), (0, 0, 1)),
}


def _plane(c, k):
    """cut/clip condition -> (unit normal, offset)."""
    n = vec(c["n"]).normalized() if "n" in c else None
    if "p" in c:
        off = Vector(*c["p"]).dot(n) * 1.0
        if k != 1:
            off = (Vector(*c["p"]) * k).dot(n)
    else:
        off = c.get("at", 0.0) * k
    off += c.get("off", 0.0) * k
    return n, off


def child_basis(parent, vd):
    """Basis of a view projected from `parent` (first-angle: placed on the side the view looks to)."""
    vd = vec(vd).normalized()
    sx, sy = vd.dot(parent.right), vd.dot(parent.up)
    L = math.hypot(sx, sy)
    if L < 1e-6:
        raise ValueError("view direction parallel to parent view direction")
    sx, sy = sx / L, sy / L
    c2 = (-sy, sx)
    c3 = parent.right * c2[0] + parent.up * c2[1]
    R = c3 * c2[0] + parent.vd * (-sx)
    U = c3 * c2[1] + parent.vd * (-sy)
    return vd, R.normalized(), U.normalized(), (sx, sy)


class View:
    def __init__(self, model, d, parent=None, idx=0):
        self.m = model
        self.d = d
        self.id = d.get("id", f"V{idx}")
        k = model.k
        dr = d.get("dir", "front")
        if isinstance(dr, str):
            vd, up = STD[dr]
        else:
            vd, up = dr, d.get("up")
        self.parent = parent
        if parent is None:
            if up is None:
                up = (0, 0, 1) if abs(Vector(*vd).normalized().Z) < 0.9 else (0, 1, 0)
            self.vd, self.right, self.up = basis(vd, up)
            self.sdir = None
        else:
            self.vd, self.right, self.up, self.sdir = child_basis(parent, vd)
        self.std = dr if isinstance(dr, str) else None
        self.is_section = bool(d.get("cut"))
        self.hidden = d.get("hid", not self.is_section)
        self.label = d.get("label")
        self.notes = []
        self._compute()

    # ---------------------------------------------------------------- geometry
    def _compute(self):
        m, k = self.m, self.m.k
        solid, norib = m.solid, m.norib
        self.clip_lines = []      # (n2, c2) lines (view coords) where partial views are cut
        self.drop_lines = []      # lines whose straight segments are cut artefacts
        clip = None
        for c in self.d.get("clip", []):
            n, off = _plane(c, k)
            r = region([(n, off, c.get("op", ">="))])
            clip = r if clip is None else common(clip, r)
            self._edge_line(n, off, "clip")
        if clip is not None:
            solid = common(solid, clip)
            norib = common(norib, clip)
        self.solid = solid
        self.rings = []
        if self.is_section:
            removed = None
            steps = self.d["cut"]
            for st in steps:
                n, off = _plane(dict(st, n=st.get("n", list(self.vd))), k)
                sgn = 1 if n.dot(self.vd) > 0 else -1
                n, off = n * sgn, off * sgn          # now n == vd
                conds = [(n, off, "<=")]
                regc = []
                for cond in st.get("if", []):
                    cn = vec(cond[0]).normalized() if not isinstance(cond[0], str) else vec(cond[0])
                    regc.append((cn, cond[2] * k, ">=" if cond[1].startswith(">") else "<="))
                    self._edge_line(cn, cond[2] * k, "step")
                rem = region(conds + regc)
                removed = rem if removed is None else fuse(removed, rem)
                keep = region(regc) if regc else None
                if clip is not None:
                    keep = clip if keep is None else common(keep, clip)
                base = norib if self._rib_longitudinal() else solid
                self.rings += section_rings(base, n, off, self.right, self.up, clip=keep)
            solid = cut(solid, removed)
        self.cut_solid = solid
        vis, hid = hlr(solid, self.vd, self.up)
        vis = self._drop_artefacts(vis)
        hid = self._drop_artefacts(hid) if self.hidden else []
        self.vis, self.hid = vis, _remove_overlaps(hid, vis)
        self._centres()
        pts = [p for pl in self.vis + self.hid for p in pl]
        self.bbox = (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))
        self.wavy = []
        for (n2, c2, kind) in self.drop_lines:
            if kind != "clip":
                continue
            # extent of the clip line over the (clipped) solid outline
            ts = []
            t2 = (-n2[1], n2[0])
            for pl in self.vis + self.hid:
                for a, b in zip(pl, pl[1:]):
                    for q in (a, b):
                        if abs(q[0] * n2[0] + q[1] * n2[1] - c2) < 1e-3:
                            ts.append(q[0] * t2[0] + q[1] * t2[1])
            if len(ts) >= 2:
                t0, t1 = min(ts), max(ts)
                P = lambda t: (n2[0] * c2 + t2[0] * t, n2[1] * c2 + t2[1] * t)
                self.wavy.append((P(t0), P(t1)))

    def _rib_longitudinal(self):
        for f in self.m.feats:
            if f["rib"]:
                bb = f["shape"].bounding_box()
                for s in f["shape"].solids():
                    b = s.bounding_box()
                    sz = [b.size.X, b.size.Y, b.size.Z]
                    i = sz.index(min(sz))
                    thin = Vector(*[1 if j == i else 0 for j in range(3)])
                    if abs(thin.dot(self.vd)) > 0.9:
                        return True
        return False

    def _edge_line(self, n, off, kind):
        n = Vector(*n)
        if abs(n.dot(self.vd)) > 1e-6:
            return
        n2 = (n.dot(self.right), n.dot(self.up))
        L = math.hypot(*n2)
        self.drop_lines.append(((n2[0] / L, n2[1] / L), off / L, kind))

    def _drop_artefacts(self, pls):
        out = []
        for pl in pls:
            bad = False
            if len(pl) == 2:
                for n2, c2, kind in self.drop_lines:
                    if all(abs(q[0] * n2[0] + q[1] * n2[1] - c2) < 1e-3 for q in pl):
                        bad = True
            if not bad:
                out.append(pl)
        return out

    def _centres(self):
        """Centre / axis lines of cylinders and holes visible in this view."""
        self.centres = []        # ("cross", c2, r) | ("axis", p0, p1)
        seen = []
        for f in faces_info(self.cut_solid):
            if f["kind"] != "cyl":
                continue
            ax, loc, r = f["ax"], f["loc"], f["r"]
            if abs(ax.dot(self.vd)) > 0.999:
                c2 = proj(loc, self.right, self.up)
                key = ("x", round(c2[0], 2), round(c2[1], 2))
                if key in [s[0] for s in seen]:
                    for s in seen:
                        if s[0] == key:
                            s[1]["r"] = max(s[1]["r"], r)
                    continue
                item = {"kind": "cross", "c": c2, "r": r, "ext": f["ext"]}
                seen.append((key, item))
            elif abs(ax.dot(self.vd)) < 1e-3:
                bb = f["face"].bounding_box()
                ts = [((Vector(x, y, z) - loc).dot(ax)) for x in (bb.min.X, bb.max.X)
                      for y in (bb.min.Y, bb.max.Y) for z in (bb.min.Z, bb.max.Z)]
                # axial extent of the face: project its vertices
                ts = [(Vector(vv.X, vv.Y, vv.Z) - loc).dot(ax) for vv in f["face"].vertices()] or ts
                t0, t1 = min(ts), max(ts)
                p0 = proj(loc + ax * t0, self.right, self.up)
                p1 = proj(loc + ax * t1, self.right, self.up)
                d2 = (ax.dot(self.right), ax.dot(self.up))
                key = ("a", round(p0[0] * d2[1] - p0[1] * d2[0], 2), round(d2[0], 3), round(d2[1], 3))
                hit = [s for s in seen if s[0] == key]
                if hit:
                    it = hit[0][1]
                    pts = [it["p0"], it["p1"], p0, p1]
                    tt = sorted(pts, key=lambda q: q[0] * d2[0] + q[1] * d2[1])
                    it["p0"], it["p1"] = tt[0], tt[-1]
                    continue
                seen.append((key, {"kind": "axis", "p0": p0, "p1": p1, "r": r}))
        self.centres = [s[1] for s in seen]


def _remove_overlaps(hid, vis, tol=0.05):
    """Drop hidden straight segments lying on visible straight segments (line priority)."""
    vs = [(a, b) for pl in vis if len(pl) == 2 for a, b in [pl]]
    out = []
    for pl in hid:
        if len(pl) != 2:
            out.append(pl)
            continue
        a, b = pl
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if L < 1e-6:
            continue
        ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        cover = []
        for p, q in vs:
            if abs((p[0] - a[0]) * uy - (p[1] - a[1]) * ux) < tol and abs((q[0] - a[0]) * uy - (q[1] - a[1]) * ux) < tol:
                t0 = (p[0] - a[0]) * ux + (p[1] - a[1]) * uy
                t1 = (q[0] - a[0]) * ux + (q[1] - a[1]) * uy
                cover.append((min(t0, t1), max(t0, t1)))
        cover.sort()
        t, segs = 0.0, []
        for c0, c1 in cover:
            if c0 > t + tol:
                segs.append((t, min(c0, L)))
            t = max(t, c1)
            if t >= L:
                break
        if t < L - tol:
            segs.append((t, L))
        for s0, s1 in segs:
            if s1 - s0 > 0.2:
                out.append([(a[0] + ux * s0, a[1] + uy * s0), (a[0] + ux * s1, a[1] + uy * s1)])
    return out


def build_views(model):
    specs = model.spec.get("views") or [{"id": "F", "dir": "front"}, {"id": "T", "dir": "top"},
                                        {"id": "L", "dir": "left"}]
    views = {}
    main = None
    for i, d in enumerate(specs):
        parent = None
        if i > 0:
            parent = views[d.get("of", specs[0].get("id", "V0"))]
        v = View(model, d, parent, i)
        views[v.id] = v
        if main is None:
            main = v
    return main, views
