"""Automatic nominal dimensioning (classic theory: size + situation dimensions, ISO 129-1).

For every frame axis (global X, Y, Z and the local frames of oblique features) the
coordinates that define the part ("nodes") are collected from the B-rep. A maximum
spanning tree over candidate dimensions gives a COMPLETE and NON-REDUNDANT set
(every node connected to the datum exactly once; symmetric pairs dimensioned as
one dimension; axes of symmetry not dimensioned). Cylinders give Ø/R, holes give notes.
"""
import math
from build123d import Vector
from .geom import faces_info, proj, vol, common, ang_coverage
from .spec import vec

TOL = 0.02


def fmt(v):
    v = round(v, 2)
    if abs(v - round(v)) < 0.01:
        return str(int(round(v)))
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return s.replace(".", ",")


class Node:
    def __init__(self, c, src, info=None):
        self.c, self.src, self.info = c, src, info or {}


class Frame:
    def __init__(self, name, axes, region=None, feat=None):
        self.name, self.axes, self.region, self.feat = name, axes, region, feat


class Intent:
    """A dimension to draw. kind: lin | dia | rad | note | ang"""

    def __init__(self, kind, **kw):
        self.kind = kind
        self.__dict__.update(kw)
        self.view = None


# ------------------------------------------------------------------ analysis
def _inside(shape, p):
    try:
        return shape.is_inside(Vector(*p))
    except Exception:
        return False


def _hole_tools(model):
    tools = []
    for f in model.feats:
        if f["t"] == "hole":
            tools.append(f)
    return tools


def _local_feats(model):
    out = []
    for f in model.feats:
        fd = f["f"]
        if f["t"] == "ext" and isinstance(fd.get("pl"), dict) and not f["cut"]:
            o, u, v, n = model.frame(fd)
            if all(max(abs(a.X), abs(a.Y), abs(a.Z)) > 0.999 for a in (u, v, n)):
                continue  # actually axis aligned
            out.append((f, (u, v, n), o))
    return out


def symmetric(model, axis_vec, c):
    from build123d import Plane
    s = model.solid
    try:
        m = s.mirror(Plane(origin=Vector(*axis_vec) * c, z_dir=Vector(*axis_vec)))
        return abs(vol(common(s, m)) - s.volume) < 1e-3 * s.volume
    except Exception:
        return False


class Dimensioner:
    def __init__(self, model, views, main):
        self.m = model
        self.views = views
        self.main = main
        self.faces = faces_info(model.solid)
        self.intents = []
        self.notes = []
        self.warn = []
        self._tag_faces()
        self._sizes()
        self._holes_in_sections()
        self._frames()

    # ---------------------------------------------------------------- tagging
    def _tag_faces(self):
        holes = _hole_tools(self.m)
        self.locals = _local_feats(self.m)
        for fi in self.faces:
            c = fi["ip"]
            fi["hole"] = None
            for h in holes:
                if _near_shape(h["shape"], c, 1e-3):
                    fi["hole"] = h["i"]
                    break
            fi["local"] = None
            for (f, axes, o) in self.locals:
                if _near_shape(f["shape"], c, 1e-3):
                    fi["local"] = f["i"]
                    break
        # natural frames of local (oblique) features: largest oblique face
        nl = []
        for (f, axes, o) in self.locals:
            fs = [x for x in self.faces if x["local"] == f["i"] and x["kind"] == "plane" and _oblique(x["n"])]
            if not fs:
                nl.append((f, axes, o))
                continue
            big = max(fs, key=lambda x: x["area"])
            n = big["n"]
            best, bs = None, -1
            for e in big["face"].edges():
                if e.geom_type.name != "LINE":
                    continue
                d = (e.position_at(1) - e.position_at(0)).normalized()
                score = max(abs(d.X), abs(d.Y), abs(d.Z)) + (1 if abs(d.Z) < 1e-6 else 0)
                if score > bs:
                    best, bs = d, score
            e1 = best
            e2 = n.cross(e1).normalized()
            nl.append((f, [e1, e2, n], o))
        self.locals = nl

    # ---------------------------------------------------------------- sizes
    def _sizes(self):
        groups = {}
        for fi in self.faces:
            if fi["kind"] != "cyl" or fi["hole"] is not None:
                continue
            ax = fi["ax"]
            if ax.dot(Vector(1, 1, 1)) < 0 and not (abs(ax.dot(Vector(1, 1, 1))) < 1e-9):
                ax = ax * -1
            loc = fi["loc"]
            base = loc - ax * loc.dot(ax)
            key = (round(base.X, 2), round(base.Y, 2), round(base.Z, 2), round(ax.X, 3), round(ax.Y, 3),
                   round(ax.Z, 3), round(fi["r"], 3), fi["inner"])
            g = groups.setdefault(key, dict(r=fi["r"], ax=ax, loc=base, bins=set(), inner=fi["inner"], faces=[]))
            g["bins"] |= ang_coverage(fi["face"], ax, base)
            g["faces"].append(fi)
        self.cyl_groups = list(groups.values())
        for g in self.cyl_groups:
            g["ext"] = len(g["bins"])
        # identical groups (same r, same kind, parallel axis) -> n x
        used = set()
        for i, g in enumerate(self.cyl_groups):
            if i in used:
                continue
            same = [j for j, h in enumerate(self.cyl_groups)
                    if j not in used and abs(h["r"] - g["r"]) < 1e-3 and h["inner"] == g["inner"]
                    and abs(abs(h["ax"].dot(g["ax"])) - 1) < 1e-6 and (h["ext"] > 180.5) == (g["ext"] > 180.5)]
            for j in same:
                used.add(j)
            full = g["ext"] > 180.5
            kind = "dia" if full else "rad"
            n = len(same)
            txt = ("Ø" if full else "R") + fmt(2 * g["r"] if full else g["r"])
            if n > 1:
                txt = f"{n}× " + txt
            self.intents.append(Intent(kind, group=g, groups=[self.cyl_groups[j] for j in same], text=txt,
                                       r=g["r"], ax=g["ax"], loc=g["loc"], inner=g["inner"]))
        # holes
        for h in _hole_tools(self.m):
            fd = h["f"]
            k = self.m.k
            n = 1 + len(fd.get("at", []))
            mir = fd.get("mir")
            if mir:
                n *= 2 ** (len(mir) if isinstance(mir, (str, dict)) else 1)
            txt = (f"{n}× " if n > 1 else "") + "Ø" + fmt(fd["d"] * k)
            sym = []
            if fd.get("depth") is not None:
                sym.append(("depth", fmt(fd["depth"] * k)))
            if fd.get("cb"):
                sym.append(("cb", "Ø" + fmt(fd["cb"][0] * k), fmt(fd["cb"][1] * k)))
            if fd.get("cs"):
                sym.append(("cs", "Ø" + fmt(fd["cs"][0] * k), fmt(fd["cs"][1]) + "°"))
            a = vec(fd.get("ax", "-z")).normalized()
            pts = [Vector(*fd["p"]) * k] + [Vector(*q) * k for q in fd.get("at", [])]
            self.intents.append(Intent("note", hole=h, text=txt, sym=sym, ax=a, pts=pts, r=fd["d"] * k / 2,
                                       count=n, fd=fd))

    def _holes_in_sections(self):
        """A single hole whose axis lies in a cutting plane is dimensioned in that section (Ø, ⌴Ø, depth)."""
        from .views import _plane
        k = self.m.k
        new = []
        for it in list(self.intents):
            if it.kind != "note" or it.count != 1 or any(sy[0] == "cs" for sy in it.sym):
                continue
            p = it.pts[0]
            hit = None
            for v in self.views.values():
                if not v.is_section or not _perp(it.ax, v.vd):
                    continue
                for st in v.d["cut"]:
                    n, off = _plane(dict(st, n=st.get("n", list(v.vd))), k)
                    if abs(p.dot(n) - off) > 0.01:
                        continue
                    ok = True
                    for cond in st.get("if", []):
                        cn = vec(cond[0]).normalized()
                        val = p.dot(cn)
                        ok &= (val <= cond[2] * k + 1e-6) if cond[1].startswith("<") else (val >= cond[2] * k - 1e-6)
                    if ok:
                        hit = v
                if hit:
                    break
            if hit is None:
                continue
            self.intents.remove(it)
            fd = it.fd
            new.append(Intent("dia", r=fd["d"] * k / 2, ax=it.ax, loc=p, inner=True, text="Ø" + fmt(fd["d"] * k),
                              force_view=hit))
            if fd.get("cb"):
                D, dd = fd["cb"]
                new.append(Intent("dia", r=D * k / 2, ax=it.ax, loc=p, inner=True, text="Ø" + fmt(D * k),
                                  force_view=hit))
                a = it.ax
                ca, cb = p.dot(a), (p + a * dd * k).dot(a)
                lo, hi = min(ca, cb), max(ca, cb)
                new.append(Intent("lin", t=a, a=Node(lo, "face", {"hole": it}), b=Node(hi, "face", {"hole": it}),
                                  ca=lo, cb=hi, why="hole", frame=Frame("H", [a]), text=fmt(dd * k), force_view=hit))
            if fd.get("depth") is not None:
                a = it.ax
                ca, cb = p.dot(a), (p + a * fd["depth"] * k).dot(a)
                lo, hi = min(ca, cb), max(ca, cb)
                new.append(Intent("lin", t=a, a=Node(lo, "face", {"hole": it}), b=Node(hi, "face", {"hole": it}),
                                  ca=lo, cb=hi, why="hole", frame=Frame("H", [a]), text=fmt(fd["depth"] * k),
                                  force_view=hit))
        self.intents += new

    # ---------------------------------------------------------------- frames / graphs
    def _frames(self):
        frames = [Frame("G", [Vector(1, 0, 0), Vector(0, 1, 0), Vector(0, 0, 1)])]
        for (f, axes, o) in self.locals:
            frames.append(Frame(f"L{f['i']}", list(axes), feat=f, region=f["shape"]))
        for fr in frames:
            for t in fr.axes:
                self._axis_graph(fr, t)
        self._angles()

    def _faces_of(self, fr):
        if fr.feat is None:
            return [f for f in self.faces if f["local"] is None]
        return [f for f in self.faces if f["local"] == fr.feat["i"] or
                (f["kind"] == "cyl" and _near_shape(fr.region, f["c"], 1.0))]

    def _axis_graph(self, fr, t):
        faces = self._faces_of(fr)
        nodes = {}

        def add(c, src, info=None):
            key = round(c, 2)
            info = info or {}
            if key not in nodes or (src == "face" and nodes[key].src != "face"):
                old = nodes.get(key)
                nodes[key] = Node(c, src, info)
                nodes[key].faces = old.faces if old else []
            if info.get("face") is not None:
                nodes[key].faces.append(info["face"])
            return key

        cyls = [f for f in self.faces if f["kind"] == "cyl"]
        for f in faces:
            if f["hole"] is not None and f["kind"] != "cyl":
                continue
            if f["kind"] == "plane":
                n = f["n"]
                if _par(n, t):
                    add(f["c"].dot(t), "face", dict(face=f))
                elif not _perp(n, t) and self._edge_on_somewhere(n) and \
                        not any(_par(n, a) for a in fr.axes):
                    for v in f["face"].vertices():
                        p = Vector(v.X, v.Y, v.Z)
                        if any(_on_cyl(c, p) for c in cyls if _perp(c["ax"], t)):
                            continue
                        add(p.dot(t), "vertex", dict(face=f, p=p))
            elif f["kind"] == "cyl":
                if _perp(f["ax"], t):
                    add(f["loc"].dot(t), "centre", dict(cyl=f, hole=f["hole"]))
        # hole centres (pattern copies) too
        for it in self.intents:
            if it.kind == "note" and _perp(it.ax, t):
                for p in it.pts:
                    if fr.feat is None or _near_shape(fr.region, p, 1.0):
                        add(p.dot(t), "centre", dict(hole=it))
        if fr.feat is not None:
            gverts = [Vector(v.X, v.Y, v.Z) for f in self.faces if f["local"] is None and f["kind"] == "plane"
                      for v in f["face"].vertices()]
            for f in faces:
                if f["kind"] != "plane":
                    continue
                for v in f["face"].vertices():
                    p = Vector(v.X, v.Y, v.Z)
                    if any((p - g).length < 1e-3 for g in gverts):
                        key = add(p.dot(t), "vertex", dict(p=p))
                        nodes[key].info["anchor"] = True
                        if f["local"] is not None and abs(abs(f["n"].dot(t)) - 1) < 1e-6:
                            pass
            for f in faces:
                if f["kind"] == "plane" and abs(abs(f["n"].dot(t)) - 1) < 1e-6:
                    key = round(f["c"].dot(t), 2)
                    if key in nodes and any((Vector(v.X, v.Y, v.Z) - g).length < 1e-3
                                            for v in f["face"].vertices() for g in gverts):
                        nodes[key].info["anchor"] = True
        if len(nodes) < 2:
            return
        keys = sorted(nodes)
        # symmetry of the whole part about the mid plane of this axis
        lo, hi = keys[0], keys[-1]
        mid = None
        if fr.feat is None:
            mm = (lo + hi) / 2
            cand = [k for k in keys if abs(k - mm) < 0.02]
            sym_nodes = all(any(abs((2 * mm - a) - b) < 0.02 for b in keys) for a in keys)
            if sym_nodes and symmetric(self.m, t, mm):
                mid = round(mm, 2)
                add(mm, "sym")
                keys = sorted(nodes)
        cand = []
        import os
        if os.environ.get("ISOVISTA_DEBUG"):
            print("NODES", fr.name, _axname(t), [(k, nodes[k].src, bool(nodes[k].info.get("anchor"))) for k in keys])

        def edge(a, b, w, why):
            if a == b:
                return
            a, b = min(a, b), max(a, b)
            cand.append((w, a, b, why))

        edge(lo, hi, 60 if fr.feat is None else 10, "overall")
        anch = [k for k in keys if nodes[k].info.get("anchor")]
        for a in anch[1:]:
            edge(anch[0], a, 2000, "implicit")
        # face extents (sizes of steps, thicknesses, lengths)
        for f in faces:
            if f["hole"] is not None:
                continue
            vs = [Vector(v.X, v.Y, v.Z).dot(t) for v in f["face"].vertices()
                  if not any(_on_cyl(c, Vector(v.X, v.Y, v.Z)) for c in cyls if c is not f and _perp(c["ax"], t))]
            if f["kind"] == "cyl" and _par(f["ax"], t):
                bb = f["bb"]
                vs = vs or [bb[0], bb[3]]
            if len(vs) >= 2 and all(round(x, 2) in nodes for x in vs):
                a, b = round(min(vs), 2), round(max(vs), 2)
                if b - a > TOL:
                    front = any(f["kind"] == "plane" and f["n"].dot(v.vd) < -1e-3 and _perp(t, v.vd)
                                for v in self.views.values())
                    edge(a, b, 12 + min(f["area"], 2000) / 400 + (3 if front else 0), "extent")
        # centres
        cents = [k for k in keys if nodes[k].src in ("centre", "sym")]
        for c in cents:
            for k2 in keys:
                if k2 == c:
                    continue
                if nodes[k2].src == "centre":
                    edge(c, k2, 7 - abs(k2 - c) / 500, "c-c")
                else:
                    edge(c, k2, (25 if (k2 in (lo, hi) and fr.feat is None) else 5) - abs(k2 - c) / 500, "c-f")
        # features centred on an axis (rib, slot, arm...): symmetric face pairs about a centre node
        for c in cents:
            for a in keys:
                b = round(2 * c - a, 2)
                if a < c and b in nodes and nodes[a].src != "centre" and nodes[b].src != "centre" \
                        and _mirror_pair(nodes[a], nodes[b], t, c):
                    edge(a, b, 35 - (b - a) / 1000, "csym")
                    edge(a, c, 900, "implicit")
                elif a < c and b in nodes and nodes[a].src == "centre" and nodes[b].src == "centre":
                    edge(a, b, 30 - (b - a) / 1000, "csym")
                    edge(a, c, 900, "implicit")
        # symmetric pairs & implicit symmetry plane
        if mid is not None:
            for a in keys:
                b = round(2 * mid - a, 2)
                if a < mid and b in nodes:
                    edge(a, b, 40 + (b - a) / 100, "sym")
                    edge(a, mid, 1000, "implicit")
        # Kruskal (maximum spanning tree)
        parent = {k: k for k in keys}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        cand.sort(key=lambda e: -e[0])
        chosen = []
        for w, a, b, why in cand:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb
                if why != "implicit":
                    chosen.append((a, b, why))
        comps = {find(k) for k in keys}
        if len(comps) > 1:
            self.warn.append(f"eixo {fr.name}{_axname(t)}: {len(comps)} grupos de coordenadas sem ligação")
        for a, b, why in chosen:
            self.intents.append(Intent("lin", t=t, a=nodes[a], b=nodes[b], ca=a, cb=b, why=why, frame=fr,
                                       text=fmt(b - a)))

    def _edge_on_somewhere(self, n):
        return any(_perp(n, v.vd) for v in self.views.values())

    def _angles(self):
        """Angles between a face of a local (oblique) feature and an adjacent global face."""
        from OCP.TopExp import TopExp
        loc_faces = [f for f in self.faces if f["local"] is not None and f["kind"] == "plane" and _oblique(f["n"])]
        glob = [f for f in self.faces if f["local"] is None and f["kind"] == "plane"]
        done = set()
        for lf in loc_faces:
            for gf in glob:
                common_edges = [e for e in lf["face"].edges() for e2 in gf["face"].edges() if e.is_same(e2)]
                if not common_edges:
                    continue
                e = common_edges[0]
                if e.geom_type.name != "LINE":
                    continue
                p0, p1 = e.position_at(0), e.position_at(1)
                ed = (p1 - p0).normalized()
                w1 = _in_face_dir(lf, ed, p0, p1)
                w2 = _in_face_dir(gf, ed, p0, p1)
                if w1 is None or w2 is None:
                    continue
                ang = math.degrees(math.acos(max(-1, min(1, w1.dot(w2)))))
                if min(abs(ang - 90), abs(ang - 180), abs(ang)) < 0.5:
                    continue
                key = round(ang, 1)
                if key in done:
                    continue
                done.add(key)
                self.intents.append(Intent("ang", v=(p0 + p1) * 0.5, ed=ed, w1=w1, w2=w2,
                                           text=fmt(ang) + "°", val=ang))


def _par(a, b):
    return abs(abs(a.normalized().dot(b.normalized())) - 1) < 1e-5


def _perp(a, b):
    return abs(a.normalized().dot(b.normalized())) < 1e-3


def _mirror_pair(na, nb, t, c):
    """True if the faces behind nodes a and b are mirror images about the plane p.t = c."""
    ax = [abs(t.X), abs(t.Y), abs(t.Z)]
    k = ax.index(max(ax))
    for fa in getattr(na, "faces", []):
        for fb in getattr(nb, "faces", []):
            if abs(fa["area"] - fb["area"]) > 0.01 * max(fa["area"], fb["area"]):
                continue
            ba, bb = fa["bb"], fb["bb"]
            if all(abs(ba[i] - bb[i]) <= 0.05 and abs(ba[i + 3] - bb[i + 3]) <= 0.05 for i in range(3) if i != k):
                return True
    return False


def _oblique(n):
    return all(abs(c) > 1e-3 for c in (n.X, n.Y, n.Z))


def _axname(t):
    for nm, a in (("X", (1, 0, 0)), ("Y", (0, 1, 0)), ("Z", (0, 0, 1))):
        if abs(abs(t.dot(Vector(*a))) - 1) < 1e-6:
            return nm
    return f"({t.X:.2f},{t.Y:.2f},{t.Z:.2f})"


def _near_shape(shape, p, tol=0.05):
    try:
        if shape.is_inside(Vector(*p)):
            return True
        return shape.distance_to(Vector(*p)) < tol
    except Exception:
        return False


def _on_cyl(cf, p):
    ax, loc, r = cf["ax"], cf["loc"], cf["r"]
    d = p - loc
    rad = (d - ax * d.dot(ax)).length
    if abs(rad - r) > 1e-3:
        return False
    try:
        return cf["face"].distance_to(p) < 1e-3
    except Exception:
        return True


def _in_face_dir(fi, ed, p0, p1):
    n = fi["n"]
    w = n.cross(ed).normalized()
    mid = (p0 + p1) * 0.5
    for s in (1, -1):
        q = mid + w * (0.5 * s)
        try:
            if fi["face"].distance_to(q) < 1e-3:
                return w * s
        except Exception:
            pass
    return None
