"""Part specification (compact JSON) -> exact B-rep solid (build123d / OpenCascade).

See references/dsl.md for the language. Axes: X right, Y back (depth), Z up. Units mm
(or grid units if "u" is given: every length is multiplied by u).
"""
import json
import math
from build123d import (Vector, Plane, Location, Solid, Face, Wire, Edge, Axis)

AX = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1),
      "-x": (-1, 0, 0), "-y": (0, -1, 0), "-z": (0, 0, -1)}


def vec(a):
    if isinstance(a, str):
        return Vector(*AX[a])
    return Vector(*a)


def _ortho(n):
    n = n.normalized()
    t = Vector(1, 0, 0) if abs(n.X) < 0.9 else Vector(0, 1, 0)
    u = (t - n * t.dot(n)).normalized()
    return u, n.cross(u)


# ----------------------------------------------------------------- 2D profiles
def _hull_disks(el):
    """Exact convex hull of disks/points (gift wrapping). el: [(cx,cy,r)].
    Returns list of ('L',p0,p1) / ('A',p0,pm,p1) in CCW order."""
    el = [e for i, e in enumerate(el)
          if not any(j != i and math.hypot(e[0] - f[0], e[1] - f[1]) + e[2] <= f[2] - 1e-9 for j, f in enumerate(el))]
    if len(el) == 1:
        return None
    start = min(range(len(el)), key=lambda i: (el[i][1] - el[i][2], el[i][0]))

    def tang(i, j):
        (x1, y1, r1), (x2, y2, r2) = el[i], el[j]
        L = math.hypot(x2 - x1, y2 - y1)
        if L < 1e-12:
            return None
        return math.atan2(y2 - y1, x2 - x1) - math.asin(max(-1, min(1, (r2 - r1) / L)))

    seq = [start]
    th = 0.0
    cur = start
    for _ in range(4 * len(el) + 4):
        best, bt, bturn = None, None, 9
        for j in range(len(el)):
            if j == cur:
                continue
            t = tang(cur, j)
            if t is None:
                continue
            turn = (t - th) % (2 * math.pi)
            if turn > 2 * math.pi - 1e-9:
                turn = 0.0
            if turn < bturn - 1e-9:
                best, bt, bturn = j, t, turn
        th = bt
        cur = best
        if cur == start:
            seq.append((cur, th))
            break
        seq.append((cur, th))
    # seq: [start, (j1,t01), (j2,t12) ..., (start, t_last)]
    pts = []
    order = [seq[0]] + [s[0] for s in seq[1:]]
    tangs = [s[1] for s in seq[1:]]
    out = []
    n = len(tangs)
    for k in range(n):
        i, j = order[k], order[k + 1]
        t = tangs[k]
        nx, ny = math.sin(t), -math.cos(t)          # right normal (outward)
        a = (el[i][0] + el[i][2] * nx, el[i][1] + el[i][2] * ny)
        b = (el[j][0] + el[j][2] * nx, el[j][1] + el[j][2] * ny)
        out.append(("L", a, b))
    segs = []
    for k in range(n):
        segs.append(out[k])
        j = order[k + 1]
        cx, cy, r = el[j]
        if r > 1e-9:
            t_in, t_out = tangs[k], tangs[(k + 1) % n]
            a0 = t_in - math.pi / 2
            a1 = t_out - math.pi / 2
            sweep = (a1 - a0) % (2 * math.pi)
            if sweep > 1e-6:
                am = a0 + sweep / 2
                segs.append(("A", (cx + r * math.cos(a0), cy + r * math.sin(a0)),
                             (cx + r * math.cos(am), cy + r * math.sin(am)),
                             (cx + r * math.cos(a1), cy + r * math.sin(a1))))
    return segs


def _segs_poly(pts):
    segs = []
    P = [(p[0], p[1]) for p in pts]
    for k in range(len(pts)):
        a, b = P[k - 1], P[k]
        R = pts[k][2] if len(pts[k]) > 2 else None
        if R:
            mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
            dx, dy = b[0] - a[0], b[1] - a[1]
            c = math.hypot(dx, dy) / 2
            s = abs(R) - math.sqrt(max(R * R - c * c, 0))
            rx, ry = dy / (2 * c), -dx / (2 * c)    # right normal
            sg = 1 if R > 0 else -1
            segs.append(("A", a, (mx + sg * s * rx, my + sg * s * ry), b))
        else:
            segs.append(("L", a, b))
    return segs


class Prof:
    """2D profile -> Face on a plane frame (o,u,v)."""

    def __init__(self, scale):
        self.k = scale

    def face(self, P, frame):
        o, u, v = frame
        k = self.k

        def to3(p):
            return o + u * (p[0] * k) + v * (p[1] * k)

        def segs_face(segs):
            edges = []
            for s in segs:
                if s[0] == "L":
                    if math.hypot(s[2][0] - s[1][0], s[2][1] - s[1][1]) > 1e-9:
                        edges.append(Edge.make_line(to3(s[1]), to3(s[2])))
                else:
                    edges.append(Edge.make_three_point_arc(to3(s[1]), to3(s[2]), to3(s[3])))
            return Face(Wire(edges))

        if "poly" in P:
            return segs_face(_segs_poly(P["poly"]))
        if "rect" in P:
            x, y, w, h = P["rect"]
            return segs_face(_segs_poly([[x, y], [x + w, y], [x + w, y + h], [x, y + h]]))
        if "circ" in P:
            cx, cy, r = P["circ"]
            c = to3((cx, cy))
            n = u.cross(v)
            return Face(Wire([Edge.make_circle(r * k, Plane(origin=c, x_dir=u, z_dir=n))]))
        if "slot" in P:
            x1, y1, x2, y2, r = P["slot"]
            return segs_face(_hull_disks([(x1, y1, r), (x2, y2, r)]))
        if "hull" in P:
            el = []
            for e in P["hull"]:
                if "circ" in e:
                    el.append(tuple(e["circ"]))
                elif "pt" in e:
                    el.append((e["pt"][0], e["pt"][1], 0.0))
                elif "poly" in e:
                    el += [(p[0], p[1], 0.0) for p in e["poly"]]
                elif "rect" in e:
                    x, y, w, h = e["rect"]
                    el += [(x, y, 0), (x + w, y, 0), (x + w, y + h, 0), (x, y + h, 0)]
            segs = _hull_disks(el)
            if segs is None:
                return self.face({"circ": list(el[0])}, frame)
            return segs_face(segs)
        if "u" in P:
            f = self.face(P["u"][0], frame)
            for q in P["u"][1:]:
                f = f.fuse(self.face(q, frame)).clean()
            return _one_face(f)
        if "d" in P:
            f = self.face(P["d"][0], frame)
            for q in P["d"][1:]:
                f = f.cut(self.face(q, frame)).clean()
            return _one_face(f)
        raise ValueError(f"unknown profile {list(P)}")


def _one_face(shape):
    fs = shape.faces() if hasattr(shape, "faces") else [shape]
    if len(fs) == 1:
        return fs[0]
    from build123d import Compound
    return Compound(children=list(fs))


# ----------------------------------------------------------------- 3D model
class Model:
    def __init__(self, spec):
        if isinstance(spec, str):
            spec = json.load(open(spec))
        self.spec = spec
        self.k = float(spec.get("u", 1.0))
        self.solid = None        # complete part
        self.norib = None        # part without ribs (for section hatching)
        self.feats = []          # dicts with geometry info
        self._build()

    def L(self, x):
        return None if x is None else x * self.k

    def P(self, p):
        return Vector(*[c * self.k for c in p])

    def frame(self, f):
        pl = f.get("pl", "xy")
        o = self.L(f.get("o", 0))
        if pl == "xy":
            return Vector(0, 0, o), Vector(1, 0, 0), Vector(0, 1, 0), Vector(0, 0, 1)
        if pl == "xz":
            return Vector(0, o, 0), Vector(1, 0, 0), Vector(0, 0, 1), Vector(0, 1, 0)
        if pl == "yz":
            return Vector(o, 0, 0), Vector(0, 1, 0), Vector(0, 0, 1), Vector(1, 0, 0)
        o3 = self.P(pl["o"])
        u = vec(pl["u"]).normalized()
        v = vec(pl["v"])
        v = (v - u * v.dot(u)).normalized()
        n = vec(pl["n"]).normalized() if "n" in pl else u.cross(v)
        return o3, u, v, n

    def _shape(self, f):
        t = f["t"]
        if t == "box":
            p, s = self.P(f["p"]), [self.L(c) for c in f["s"]]
            return Solid.make_box(s[0], s[1], s[2], Plane(origin=p))
        if t in ("cyl", "cone"):
            p = self.P(f["p"])
            a = vec(f.get("ax", "z")).normalized()
            h = self.L(f["h"])
            pl = Plane(origin=p, x_dir=_ortho(a)[0], z_dir=a)
            if t == "cyl":
                r = self.L(f["d"]) / 2 if "d" in f else self.L(f["r"])
                return Solid.make_cylinder(r, h, pl)
            return Solid.make_cone(self.L(f["d1"]) / 2, self.L(f["d2"]) / 2, h, pl)
        if t == "sph":
            return Solid.make_sphere(self.L(f["d"]) / 2, Plane(origin=self.P(f["p"])))
        if t == "ext":
            o, u, v, n = self.frame(f)
            face = Prof(self.k).face(f["prof"], (o, u, v))
            h = self.L(f["h"])
            if f.get("mid"):
                face = face.moved(Location(n * (-h / 2)))
            faces = face.faces() if hasattr(face, "faces") else [face]
            sol = None
            for fc in faces:
                s = Solid.extrude(fc, n * h)
                sol = s if sol is None else sol + s
            return sol
        if t == "rev":
            p = self.P(f.get("p", [0, 0, 0]))
            a = vec(f.get("ax", "z")).normalized()
            u, _ = _ortho(a)
            face = Prof(self.k).face(f["prof"], (p, u, a))   # profile coords (r, h)
            return Solid.revolve(face, f.get("ang", 360), Axis(p, a))
        if t == "hole":
            return self._hole(f, self.P(f["p"]))
        raise ValueError(f"unknown feature type {t}")

    def _hole(self, f, p):
        a = vec(f.get("ax", "-z")).normalized()
        r = self.L(f["d"]) / 2
        u = _ortho(a)[0]
        depth = self.L(f.get("depth"))
        if depth is None:
            tool = Solid.make_cylinder(r, 2000, Plane(origin=p - a * 1000, x_dir=u, z_dir=a))
        else:
            tool = Solid.make_cylinder(r, depth + 0.02, Plane(origin=p - a * 0.02, x_dir=u, z_dir=a))
            tip = f.get("tip")
            if tip:
                hc = r / math.tan(math.radians(tip / 2))
                tool = tool + Solid.make_cone(r, 0, hc, Plane(origin=p + a * depth, x_dir=u, z_dir=a))
        if f.get("cb"):
            D, dd = f["cb"]
            tool = tool + Solid.make_cylinder(self.L(D) / 2, self.L(dd) + 1,
                                              Plane(origin=p - a * 1, x_dir=u, z_dir=a))
        if f.get("cs"):
            D, ang = f["cs"]
            R = self.L(D) / 2
            hc = (R - r) / math.tan(math.radians(ang / 2))
            tool = tool + Solid.make_cone(R + math.tan(math.radians(ang / 2)), r, hc + 1,
                                          Plane(origin=p - a * 1, x_dir=u, z_dir=a))
        return tool

    def _mirror(self, shape, mir):
        out = [shape]
        if isinstance(mir, str):
            mir = {c: 0 for c in mir}
        for axis, c in mir.items():
            n = Vector(*AX[axis])
            pl = Plane(origin=n * self.L(c), z_dir=n)
            out += [s.mirror(pl) for s in out]
        res = out[0]
        for s in out[1:]:
            res = res + s
        return res

    def _build(self):
        sol = nor = None
        for i, f in enumerate(self.spec["f"]):
            shp = self._shape(f)
            extra = [self.P(q) for q in f.get("at", [])]
            for q in extra:
                shp = shp + (self._hole(f, q) if f["t"] == "hole" else
                             self._shape(dict(f, p=[c / self.k for c in q])))
            if f.get("mir"):
                shp = self._mirror(shp, f["mir"])
            cut = f.get("cut", f["t"] == "hole")
            info = dict(i=i, t=f["t"], f=f, shape=shp, cut=cut, rib=bool(f.get("rib")))
            self.feats.append(info)
            if cut:
                if sol is not None:
                    sol = sol - shp
                    nor = nor - shp
            else:
                sol = shp if sol is None else sol + shp
                if not f.get("rib"):
                    nor = shp if nor is None else nor + shp
        self.solid = _clean(sol)
        self.norib = _clean(nor)

    def bbox(self):
        bb = self.solid.bounding_box()
        return (bb.min.X, bb.min.Y, bb.min.Z, bb.max.X, bb.max.Y, bb.max.Z)


def _clean(s):
    try:
        s = s.clean()
    except Exception:
        pass
    sols = s.solids() if hasattr(s, "solids") else [s]
    if len(sols) == 1:
        return sols[0]
    from build123d import Compound
    return Compound(children=list(sols))


def load(path_or_dict):
    return Model(path_or_dict)
