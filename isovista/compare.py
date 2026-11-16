"""Round-trip check: compare two independent readings of the same part (exact solids)."""
import itertools
import math
from build123d import Vector, Location, Axis
from .geom import common, cut, vol


def _rotations():
    """The 24 proper rotations of the cube as (axis-permutation, signs)."""
    out = []
    for perm in itertools.permutations(range(3)):
        for sg in itertools.product((1, -1), repeat=3):
            M = [[0] * 3 for _ in range(3)]
            for i in range(3):
                M[i][perm[i]] = sg[i]
            det = (M[0][0] * (M[1][1] * M[2][2] - M[1][2] * M[2][1]) - M[0][1] * (M[1][0] * M[2][2] - M[1][2] * M[2][0])
                   + M[0][2] * (M[1][0] * M[2][1] - M[1][1] * M[2][0]))
            if det == 1:
                out.append(M)
    return out


def _apply(shape, M):
    from OCP.gp import gp_Trsf, gp_Mat, gp_XYZ
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from build123d import Shape
    t = gp_Trsf()
    t.SetValues(M[0][0], M[0][1], M[0][2], 0, M[1][0], M[1][1], M[1][2], 0, M[2][0], M[2][1], M[2][2], 0)
    return Shape.cast(BRepBuilderAPI_Transform(shape.wrapped, t, True).Shape())


def align(a, b, rotate=True):
    """Move b onto a: try the 24 axis-aligned rotations (readers may choose different axes),
    then align bounding-box centres; keep the best overlap."""
    va = vol(a)
    ba = a.bounding_box()
    best = None
    rots = _rotations() if rotate else [[[1, 0, 0], [0, 1, 0], [0, 0, 1]]]
    for M in rots:
        bb_ = _apply(b, M)
        bbb = bb_.bounding_box()
        if any(abs(x - y) > 0.15 * max(x, y) + 1 for x, y in
               zip(sorted([ba.size.X, ba.size.Y, ba.size.Z]), sorted([bbb.size.X, bbb.size.Y, bbb.size.Z]))):
            pass
        if abs(ba.size.X - bbb.size.X) + abs(ba.size.Y - bbb.size.Y) + abs(ba.size.Z - bbb.size.Z) > \
                0.3 * (ba.size.X + ba.size.Y + ba.size.Z):
            continue
        d = Vector((ba.min.X + ba.max.X) / 2 - (bbb.min.X + bbb.max.X) / 2,
                   (ba.min.Y + ba.max.Y) / 2 - (bbb.min.Y + bbb.max.Y) / 2,
                   (ba.min.Z + ba.max.Z) / 2 - (bbb.min.Z + bbb.max.Z) / 2)
        cand = [d, Vector(ba.min.X - bbb.min.X, ba.min.Y - bbb.min.Y, ba.min.Z - bbb.min.Z)]
        for dv in cand:
            m = bb_.moved(Location(dv))
            inter = vol(common(a, m))
            iou = inter / (va + vol(m) - inter)
            if best is None or iou > best[0]:
                best = (iou, m, M, dv)
    return best


def compare(model_a, model_b, rotate=True, tol=0.995):
    a, b = model_a.solid, model_b.solid
    best = align(a, b, rotate)
    if best is None:
        return dict(ok=False, iou=0.0, msg="tamanhos globais muito diferentes")
    iou, bm, M, dv = best
    regions = []
    for name, x, y in (("só na leitura A (falta em B)", a, bm), ("só na leitura B (a mais em B)", bm, a)):
        d = cut(x, y)
        sols = d.solids() if d is not None else []
        for s in sols:
            v = vol(s)
            if v < 1.0:
                continue
            bb = s.bounding_box()
            regions.append(dict(kind=name, vol=round(v, 1),
                                bbox=[round(c, 1) for c in (bb.min.X, bb.min.Y, bb.min.Z, bb.max.X, bb.max.Y, bb.max.Z)],
                                feats=_feats_near(model_a, s)))
    regions.sort(key=lambda r: -r["vol"])
    va, vb = vol(a), vol(b)
    return dict(ok=iou >= tol and not any(r["vol"] > 0.002 * va for r in regions), iou=round(iou, 5),
                vol_a=round(va, 1), vol_b=round(vb, 1), rotation=M, shift=[round(dv.X, 2), round(dv.Y, 2), round(dv.Z, 2)],
                regions=regions[:10])


def _feats_near(model, s):
    c = s.center()
    out = []
    for f in model.feats:
        try:
            d = f["shape"].distance_to(c)
        except Exception:
            continue
        out.append((d, f["f"].get("id", f"#{f['i']}")))
    out.sort()
    return [n for d, n in out[:3] if d < max(2.0, out[0][0] + 1.0)]


def _feats_in(model, bb):
    out = []
    for f in model.feats:
        b = f["shape"].bounding_box()
        if b.min.X <= bb.max.X and b.max.X >= bb.min.X and b.min.Y <= bb.max.Y and b.max.Y >= bb.min.Y \
                and b.min.Z <= bb.max.Z and b.max.Z >= bb.min.Z:
            out.append(f["f"].get("id", f"#{f['i']}"))
    return out
