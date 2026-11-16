"""OCP helpers: hidden-line removal, sections, robust (fuzzy) booleans, face analysis."""
import math
import numpy as np
from build123d import Vector, Plane, Solid, Shape, Edge, GeomType
from build123d.topology.shape_core import List_TopoDS_Shape
from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
from OCP.HLRAlgo import HLRAlgo_Projector
from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir
from OCP.BRepLib import BRepLib
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopoDS import TopoDS
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common, BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Plane, GeomAbs_Cylinder, GeomAbs_Cone


def basis(vd, up):
    vd = Vector(*vd).normalized()
    up = Vector(*up)
    up = (up - vd * up.dot(vd)).normalized()
    right = vd.cross(up).normalized()
    up = right.cross(vd).normalized()
    return vd, right, up


def _to_edge(e):
    try:
        return TopoDS.Edge(e)
    except Exception:
        return TopoDS.Edge_s(e)


def sample_edge(ed, n=48, tol=0.15):
    if ed.geom_type == GeomType.LINE:
        k = 2
    else:
        k = max(8, min(n * 4, int(ed.length / tol) + 2)) if ed.length > 0 else 2
        k = min(k, 160)
    return [ed.position_at(t) for t in np.linspace(0, 1, k)]


def hlr(shape, vd, up):
    """Hidden-line removal looking ALONG vd. Returns (visible, hidden) polylines in view
    coordinates (x = right = vd x up, y = up)."""
    vd, right, upv = basis(vd, up)
    ax = gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(*tuple(vd * -1)), gp_Dir(*tuple(right)))
    a = HLRBRep_Algo()
    a.Add(shape.wrapped)
    a.Projector(HLRAlgo_Projector(ax))
    a.Update()
    a.Hide()
    hs = HLRBRep_HLRToShape(a)

    def grab(cs):
        out = []
        for c in cs:
            if c.IsNull():
                continue
            ex = TopExp_Explorer(c, TopAbs_EDGE)
            while ex.More():
                e = _to_edge(ex.Current())
                BRepLib.BuildCurves3d_s(e, 1e-6)
                ed = Edge(e)
                pts = sample_edge(ed)
                pl = [(round(p.X, 4), round(p.Y, 4)) for p in pts]
                if len(pl) >= 2 and math.hypot(pl[-1][0] - pl[0][0], pl[-1][1] - pl[0][1]) + \
                        sum(math.hypot(b[0] - a_[0], b[1] - a_[1]) for a_, b in zip(pl, pl[1:])) > 1e-3:
                    out.append(pl)
                ex.Next()
        return out
    vis = grab([hs.VCompound(), hs.OutLineVCompound()])
    hid = grab([hs.HCompound(), hs.OutLineHCompound()])
    return vis, hid


def proj(p, right, up):
    p = Vector(*p) if not isinstance(p, Vector) else p
    return (p.dot(right), p.dot(up))


def vol(s):
    if s is None:
        return 0.0
    w = s.wrapped if hasattr(s, "wrapped") else s
    p = GProp_GProps()
    BRepGProp.VolumeProperties_s(w, p)
    return abs(p.Mass())


def _fz(cls, a, b, f=1e-3):
    op = cls()
    A = List_TopoDS_Shape()
    A.Append(a.wrapped)
    B = List_TopoDS_Shape()
    for x in (b if isinstance(b, (list, tuple)) else [b]):
        B.Append(x.wrapped)
    op.SetArguments(A)
    op.SetTools(B)
    op.SetFuzzyValue(f)
    op.SetRunParallel(True)
    op.Build()
    return Shape.cast(op.Shape())


def cut(a, b):
    return _fz(BRepAlgoAPI_Cut, a, b)


def common(a, b):
    return _fz(BRepAlgoAPI_Common, a, b)


def fuse(a, b):
    return _fz(BRepAlgoAPI_Fuse, a, b)


def halfspace(n, c, size=4000.0):
    """Solid box approximating {p : p.n >= c}."""
    n = Vector(*n).normalized()
    pl = Plane(origin=n * c, z_dir=n)
    return Solid.make_box(size, size, size / 2, Plane(origin=pl.from_local_coords((-size / 2, -size / 2, 0)),
                                                       x_dir=pl.x_dir, z_dir=n))


def region(conds):
    """Intersection of half-spaces; conds = [(n, c, '>='|'<=')]."""
    r = None
    for n, c, op in conds:
        n = Vector(*n)
        h = halfspace(n, c) if op == ">=" else halfspace(n * -1, -c)
        r = h if r is None else common(r, h)
    return r


def section_rings(shape, n, c, right, up, clip=None):
    """Section of shape by plane p.n = c -> list of faces, each a list of 2D rings (view coords)."""
    from build123d import section as b3d_section
    n = Vector(*n).normalized()
    pl = Plane(origin=n * c, z_dir=n)
    try:
        sk = b3d_section(shape, section_by=pl)
    except Exception:
        return []
    faces = sk.faces() if sk is not None else []
    out = []
    for f in faces:
        if clip is not None:
            g = common(f, clip)
            fs = g.faces() if g is not None else []
        else:
            fs = [f]
        for ff in fs:
            rings = []
            for w in [ff.outer_wire()] + list(ff.inner_wires()):
                pts = []
                edges = w.order_edges() if hasattr(w, "order_edges") else w.edges()
                for e in edges:
                    seg = [proj(p, right, up) for p in sample_edge(e, tol=0.1)]
                    if pts and math.hypot(pts[-1][0] - seg[0][0], pts[-1][1] - seg[0][1]) > 1e-3:
                        if math.hypot(pts[-1][0] - seg[-1][0], pts[-1][1] - seg[-1][1]) < 1e-3:
                            seg = seg[::-1]
                    pts += seg
                if len(pts) >= 3:
                    rings.append(pts)
            if rings:
                out.append(rings)
    return out


# ------------------------------------------------------------- face analysis
def interior_point(face):
    """A point on the face, slightly inside its boundary (centroids can fall outside trimmed faces)."""
    for e in face.edges():
        try:
            p = e.position_at(0.5)
            t = e.tangent_at(0.5)
            n = face.normal_at(p)
            w = n.cross(t)
            if w.length < 1e-9:
                continue
            w = w.normalized()
            for s in (1, -1):
                q = p + w * (0.05 * s)
                if face.distance_to(q) < 1e-3:
                    return q
        except Exception:
            continue
    return face.center()


def ang_coverage(fi_face, ax, loc):
    """Angular coverage (set of 1-degree bins) of a cylindrical face around axis (ax, loc),
    from the face's parametric u-range (trimmed range of the surface)."""
    u0v, v0v = _ortho_pair(ax)
    ad = BRepAdaptor_Surface(fi_face.wrapped)
    u0, u1 = ad.FirstUParameter(), ad.LastUParameter()
    vm = (ad.FirstVParameter() + ad.LastVParameter()) / 2

    def ang(u):
        q = ad.Value(u, vm)
        d = Vector(q.X(), q.Y(), q.Z()) - loc
        return math.degrees(math.atan2(d.dot(v0v), d.dot(u0v)))
    a0 = ang(u0)
    step = math.radians(1)
    da = (ang(u0 + step) - a0 + 540) % 360 - 180
    sgn = 1 if da >= 0 else -1
    span = math.degrees(u1 - u0)
    return {int((a0 + sgn * k) % 360) for k in range(int(round(span)))}


def _ortho_pair(n):
    n = n.normalized()
    t = Vector(1, 0, 0) if abs(n.X) < 0.9 else Vector(0, 1, 0)
    u = (t - n * t.dot(n)).normalized()
    return u, n.cross(u)


def faces_info(shape):
    """Planar / cylindrical / conical face descriptors of a solid."""
    out = []
    for f in shape.faces():
        ad = BRepAdaptor_Surface(f.wrapped)
        t = ad.GetType()
        bb = f.bounding_box()
        d = dict(face=f, bb=(bb.min.X, bb.min.Y, bb.min.Z, bb.max.X, bb.max.Y, bb.max.Z), area=f.area,
                 ip=interior_point(f))
        if t == GeomAbs_Plane:
            pln = ad.Plane()
            nn = pln.Axis().Direction()
            n = Vector(nn.X(), nn.Y(), nn.Z())
            if f.wrapped.Orientation() == 1:   # reversed
                n = n * -1
            d.update(kind="plane", n=n, c=f.center())
        elif t == GeomAbs_Cylinder:
            cy = ad.Cylinder()
            a = cy.Axis()
            loc = Vector(a.Location().X(), a.Location().Y(), a.Location().Z())
            ax = Vector(a.Direction().X(), a.Direction().Y(), a.Direction().Z())
            u0, u1 = ad.FirstUParameter(), ad.LastUParameter()
            c = f.center()
            # inner (hole) if the surface normal points towards the axis
            nrm = f.normal_at(c)
            radial = c - (loc + ax * (c - loc).dot(ax))
            inner = nrm.dot(radial) < 0
            d.update(kind="cyl", r=cy.Radius(), ax=ax, loc=loc, ext=math.degrees(u1 - u0), inner=inner, c=c)
        elif t == GeomAbs_Cone:
            d.update(kind="cone", c=f.center())
        else:
            d.update(kind="other", c=f.center())
        out.append(d)
    return out
