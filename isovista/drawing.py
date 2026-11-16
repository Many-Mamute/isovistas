"""Orthographic drawing: dimension placement, view layout, sheet (ISO 5457/7200), lint, outputs."""
import json
import math
from build123d import Vector
from .canvas import Canvas
from .style import Style, SHEETS
from .views import build_views
from .dims import Dimensioner, fmt, _perp, _par
from .geom import proj

LETTERS = "ABCDEFGHJKLMNPRSTUVWXYZ"


def _d2(v, a):   # 3D direction -> paper direction (y down) in view v
    x, y = a.dot(v.right), a.dot(v.up)
    L = math.hypot(x, y)
    return (x / L, -y / L) if L > 1e-9 else (0.0, 0.0)


class VD:
    """A view placed on paper: geometry in paper mm relative to the view origin (y down)."""

    def __init__(self, v, sc):
        self.v, self.sc = v, sc
        P = self.P
        self.vis = [[P(q) for q in pl] for pl in v.vis]
        self.hid = [[P(q) for q in pl] for pl in v.hid]
        self.rings = [[[P(q) for q in r] for r in f] for f in v.rings]
        self.wavy = [(P(a), P(b)) for a, b in v.wavy]
        self.items = []              # drawing commands for annotations (relative)
        self.texts = []              # text boxes (relative) for collisions
        self.dimlines = []           # segments of dims
        pts = [q for pl in self.vis + self.hid for q in pl] + [q for f in self.rings for r in f for q in r]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        self.gb = (min(xs), min(ys), max(xs), max(ys))
        self.geo_segs = [(a, b) for pl in self.vis + self.hid for a, b in zip(pl, pl[1:])] + \
                        [(a, b) for f in self.rings for r in f for a, b in zip(r, r[1:] + r[:1])]
        self.tiers = {}
        self.origin = (0.0, 0.0)
        self.centres = []

    def P(self, q):
        return (q[0] * self.sc, -q[1] * self.sc)

    def pts_on(self, t2p, c, tol=0.05, vis_only=False):
        """Paper points of geometry lying on the line {q : q.t2p = c} (t2p paper unit vector)."""
        out = []
        groups = [(self.vis, True)] + ([] if vis_only else [(self.hid, False)])
        groups.append(([r for f in self.rings for r in f], True))
        for pls, vis in groups:
            for pl in pls:
                for q in pl:
                    if abs(q[0] * t2p[0] + q[1] * t2p[1] - c) < tol:
                        out.append((q, vis))
        return out

    def env(self):
        xs = [self.gb[0], self.gb[2]]
        ys = [self.gb[1], self.gb[3]]
        for b in self.texts:
            xs += [b[0], b[2]]
            ys += [b[1], b[3]]
        for a, b in self.dimlines:
            xs += [a[0], b[0]]
            ys += [a[1], b[1]]
        return (min(xs), min(ys), max(xs), max(ys))


def _seg_hits_box(a, b, box, pad=0.3):
    x0, y0, x1, y1 = box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad
    # Liang-Barsky
    dx, dy = b[0] - a[0], b[1] - a[1]
    p = [-dx, dx, -dy, dy]
    q = [a[0] - x0, x1 - a[0], a[1] - y0, y1 - a[1]]
    u0, u1 = 0.0, 1.0
    for pi, qi in zip(p, q):
        if abs(pi) < 1e-12:
            if qi < 0:
                return False
        else:
            t = qi / pi
            if pi < 0:
                u0 = max(u0, t)
            else:
                u1 = min(u1, t)
            if u0 > u1:
                return False
    return True


def _box_overlap(a, b, pad=0.4):
    return not (a[2] + pad < b[0] or b[2] + pad < a[0] or a[3] + pad < b[1] or b[3] + pad < a[1])


class Drawing:
    def __init__(self, model, style=None, sheet=None, scale=None, title=None):
        self.m = model
        self.s = style or Style()
        meta = model.spec.get("meta", {})
        self.meta = meta
        self.sheet_name = sheet or meta.get("sheet", "A3")
        sc = scale or meta.get("scale", "1:1")
        a, b = [float(x) for x in str(sc).split(":")]
        self.sc = a / b
        self.scale_txt = sc
        self.main, self.views = build_views(model)
        self.dimr = Dimensioner(model, self.views, self.main)
        self.lint = []
        self._letters()

    def _letters(self):
        used = {v.label for v in self.views.values() if v.label}
        it = iter(c for c in LETTERS if c not in used)
        for v in self.views.values():
            if v is self.main and not v.is_section:
                continue
            if v.label is None and (v.is_section or v.std not in ("top", "left", "right", "bottom", "rear", "front")):
                v.label = next(it)

    # ================================================================ assignment
    def assign(self):
        self.vd = {v.id: VD(v, self.sc) for v in self.views.values()}
        out = []
        for it in self.dimr.intents:
            best, bs = None, -1e9
            V = [it.force_view] if getattr(it, "force_view", None) is not None else list(self.views.values())
            if it.kind == "lin":
                for v in V:
                    if not _perp(it.t, v.vd):
                        continue
                    d = self.vd[v.id]
                    t2p = _d2(v, it.t)
                    ca = it.ca * t2p[0] * (it.t.dot(v.right) / max(1e-12, abs(it.t.dot(v.right)))) if False else None
                    # coordinate along t2p for node c: c_paper = c*sc * sign
                    sgn = (it.t.dot(v.right) * t2p[0] - it.t.dot(v.up) * t2p[1])
                    wa = d.pts_on(t2p, it.ca * self.sc * sgn)
                    wb = d.pts_on(t2p, it.cb * self.sc * sgn)
                    if it.a.src in ("centre", "sym"):
                        wa = wa + self._centre_pts(d, t2p, it.ca * self.sc * sgn)
                    if it.b.src in ("centre", "sym"):
                        wb = wb + self._centre_pts(d, t2p, it.cb * self.sc * sgn)
                    if not wa or not wb:
                        continue
                    sc_ = (5 if any(x[1] for x in wa) else 1) + (5 if any(x[1] for x in wb) else 1)
                    if v.is_section and (it.a.info.get("hole") is not None or it.b.info.get("hole") is not None):
                        sc_ += 3
                    if it.frame.feat is None and v.std is None:
                        sc_ -= 4
                    if it.frame.feat is not None and v.std is None:
                        sc_ += 4
                        if _par(it.frame.axes[2], v.vd):
                            sc_ += 3
                    if v is self.main:
                        sc_ += 1
                    if sc_ > bs:
                        bs, best = sc_, (v, dict(t2p=t2p, ua=it.ca * self.sc * sgn, ub=it.cb * self.sc * sgn,
                                                  wa=wa, wb=wb))
            elif it.kind == "dia":
                for v in V:
                    d = self.vd[v.id]
                    if _perp(it.ax, v.vd):
                        a2 = _d2(v, it.ax)
                        t2p = (-a2[1], a2[0])
                        c2 = d.P(proj(it.loc, v.right, v.up))
                        cc = c2[0] * t2p[0] + c2[1] * t2p[1]
                        r = it.r * self.sc
                        wa = [w for w in d.pts_on(t2p, cc - r) if w[1]]
                        wb = [w for w in d.pts_on(t2p, cc + r) if w[1]]
                        if wa and wb:
                            s_ = 8 + (3 if (v.is_section and it.inner) else 0) + (2 if v is self.main else 0) - \
                                 (4 if v.std is None else 0)
                            if s_ > bs:
                                bs, best = s_, (v, dict(t2p=t2p, ua=cc - r, ub=cc + r, wa=wa, wb=wb, dia=True))
                    elif _par(it.ax, v.vd):
                        arc = self._arc_angles(d, v, it)
                        if arc:
                            s_ = 2 + (1 if v.std else 0)
                            if s_ > bs:
                                bs, best = s_, (v, dict(circ=True, arc=arc))
            elif it.kind == "rad":
                for v in V:
                    if _par(it.ax, v.vd):
                        d = self.vd[v.id]
                        arc = self._arc_angles(d, v, it)
                        if arc:
                            s_ = len(arc) + (3 if v.std else 0) + (2 if not v.is_section else 0)
                            if s_ > bs:
                                bs, best = s_, (v, dict(arc=arc))
            elif it.kind == "note":
                for v in V:
                    if _par(it.ax, v.vd):
                        d = self.vd[v.id]
                        arc = self._arc_angles(d, v, it, loc=it.pts[0])
                        if arc:
                            s_ = len(arc) + (5 if not v.is_section else 0) + (2 if v.std else 0)
                            if s_ > bs:
                                bs, best = s_, (v, dict(arc=arc))
            elif it.kind == "ang":
                for v in V:
                    if _par(it.ed, v.vd):
                        s_ = 5 + (2 if v.std is None else 0)
                        if s_ > bs:
                            bs, best = s_, (v, {})
            if best is None:
                self.lint.append(f"sem vista para a cota {it.kind} {it.text}")
                continue
            it.view, it.geo = best
            out.append(it)
        self.placed = out

    def _centre_pts(self, d, t2p, c):
        out = []
        for ce in d.v.centres:
            if ce["kind"] == "cross":
                p = d.P(ce["c"])
                r = ce["r"] * self.sc
                if abs(p[0] * t2p[0] + p[1] * t2p[1] - c) < 0.05:
                    out += [((p[0] + t2p[1] * r, p[1] - t2p[0] * r), True), ((p[0] - t2p[1] * r, p[1] + t2p[0] * r), True)]
            else:
                a, b = d.P(ce["p0"]), d.P(ce["p1"])
                if abs(a[0] * t2p[0] + a[1] * t2p[1] - c) < 0.05 and abs(b[0] * t2p[0] + b[1] * t2p[1] - c) < 0.05:
                    out += [(a, True), (b, True)]
        return out

    def _arc_angles(self, d, v, it, loc=None):
        """Angles (deg, math sense on paper) where the circle of `it` is visible in view v."""
        c = d.P(proj(loc if loc is not None else it.loc, v.right, v.up))
        r = it.r * self.sc
        ok = []
        for k in range(0, 360, 15):
            a = math.radians(k)
            q = (c[0] + r * math.cos(a), c[1] - r * math.sin(a))
            hit = False
            for pl in d.vis:
                for p in pl:
                    if abs(p[0] - q[0]) < 0.6 and abs(p[1] - q[1]) < 0.6:
                        hit = True
                        break
                if hit:
                    break
            if not hit:   # arc points between samples
                for a_, b_ in d.geo_segs:
                    if _dist_seg(q, a_, b_) < 0.25:
                        hit = True
                        break
            if hit:
                ok.append(k)
        return ok

    # ================================================================ placement
    def place(self):
        for vd in self.vd.values():
            self._centre_lines(vd)
        seen, keep = set(), []
        order = sorted(self.placed, key=lambda it: 0 if it.kind == "dia" else 1)
        for it in order:
            if it.kind in ("lin", "dia") and "t2p" in it.geo and getattr(it, "why", "") != "hole":
                g = it.geo
                t2, ua, ub = g["t2p"], g["ua"], g["ub"]
                if t2[0] < -1e-6 or (abs(t2[0]) < 1e-6 and t2[1] < 0):
                    t2, ua, ub = (-t2[0], -t2[1]), -ua, -ub
                key = (it.view.id, round(t2[0], 3), round(t2[1], 3), round(min(ua, ub), 1), round(max(ua, ub), 1))
                if key in seen:
                    continue
                seen.add(key)
            keep.append(it)
        self.placed = keep
        lins = [it for it in self.placed if it.kind in ("lin",) or (it.kind == "dia" and "t2p" in it.geo)]
        lins.sort(key=lambda it: abs(it.geo["ub"] - it.geo["ua"]))
        for it in lins:
            self._place_lin(it)
        for it in self.placed:
            if it.kind == "rad" or (it.kind == "dia" and "circ" in it.geo):
                self._place_rad(it)
            elif it.kind == "note":
                self._place_note(it)
            elif it.kind == "ang":
                self._place_ang(it)

    def _centre_lines(self, d):
        S, sc = self.s, self.sc
        for ce in d.v.centres:
            if ce["kind"] == "cross":
                c = d.P(ce["c"])
                r = ce["r"] * sc
                for ang in (0, 90, 180, 270):
                    a = math.radians(ang)
                    q = (c[0] + r * math.cos(a), c[1] - r * math.sin(a))
                    on = any(_dist_seg(q, a_, b_) < 0.3 for a_, b_ in d.geo_segs)
                    L = r + S.centre_over if on else min(S.centre_over, r)
                    d.items.append(("line", c, (c[0] + L * math.cos(a), c[1] - L * math.sin(a)), "ctr"))
            else:
                a, b = d.P(ce["p0"]), d.P(ce["p1"])
                L = math.hypot(b[0] - a[0], b[1] - a[1])
                if L < 1e-6:
                    continue
                ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
                e = S.centre_over
                d.items.append(("line", (a[0] - ux * e, a[1] - uy * e), (b[0] + ux * e, b[1] + uy * e), "ctr"))

    def _place_lin(self, it):
        S = self.s
        d = self.vd[it.view.id]
        g = it.geo
        t = g["t2p"]
        n = (-t[1], t[0])
        ua, ub = g["ua"], g["ub"]
        text = ("Ø" + it.text) if it.kind == "dia" and not it.text.startswith(("Ø", "R")) and False else it.text
        if it.kind == "dia":
            text = it.text if it.text.startswith(("Ø",)) or "×" in it.text else "Ø" + it.text
        al = S.arrow_len
        span = abs(ub - ua)
        tw = S.text_w(text)
        allpts = [q for pl in d.vis + d.hid for q in pl] + [q for f in d.rings for r in f for q in r]
        best = None
        for side in (1, -1):
            s = (n[0] * side, n[1] * side)
            E = max(q[0] * s[0] + q[1] * s[1] for q in allpts)
            wa = max(g["wa"], key=lambda w: (w[1], w[0][0] * s[0] + w[0][1] * s[1]))[0]
            wb = max(g["wb"], key=lambda w: (w[1], w[0][0] * s[0] + w[0][1] * s[1]))[0]
            ext = (E - (wa[0] * s[0] + wa[1] * s[1])) + (E - (wb[0] * s[0] + wb[1] * s[1]))
            cross = 0
            for w in (wa, wb):
                tip = (w[0] + s[0] * (E - (w[0] * s[0] + w[1] * s[1]) + 1), w[1] + s[1] * (E - (w[0] * s[0] + w[1] * s[1]) + 1))
                st = (w[0] + s[0] * 0.3, w[1] + s[1] * 0.3)
                cross += sum(1 for g_ in d.geo_segs if _seg_cross(st, tip, g_[0], g_[1]))
            key_ = (round(s[0], 3), round(s[1], 3))
            sg_ = t[0] * (-s[1]) + t[1] * s[0]
            lo_, hi_ = min(ua * sg_, ub * sg_) - 1, max(ua * sg_, ub * sg_) + 1
            tiers_ = d.tiers.get(key_, [])
            kk = 0
            while kk < len(tiers_) and not all(hi_ < a or lo_ > b for a, b in tiers_[kk]):
                kk += 1
            cost = ext + 12 * cross + 2 * kk * S.dim_step
            if best is None or cost < best[0]:
                best = (cost, s, E, wa, wb)
        _, s, E, wa, wb = best
        key = (round(s[0], 3), round(s[1], 3))
        tiers = d.tiers.setdefault(key, [])
        sg = t[0] * (-s[1]) + t[1] * s[0]
        lo, hi = min(ua * sg, ub * sg), max(ua * sg, ub * sg)
        inside = span >= 2 * al + tw + 2
        need = (lo - 1, hi + 1) if inside else (lo - al - 3, hi + tw + al + 4)
        k = 0
        while True:
            if k >= len(tiers):
                tiers.append([])
            if all(need[1] < a or need[0] > b for a, b in tiers[k]):
                L = E + S.dim_first + k * S.dim_step
                pa = self._pt(t, s, ua, L)
                pb = self._pt(t, s, ub, L)
                tp, ang = self._lin_text_pos(pa, pb, inside, tw)
                box = Canvas(1, 1, S).text_bbox(tp, text, S.h, ang, "middle", "base")
                if not any(_box_overlap(box, b) for b in d.texts) or k > 6:
                    tiers[k].append(need)
                    break
            k += 1
        # extension lines
        ov = S.ext_over * S.thin
        for w, p in ((wa, pa), (wb, pb)):
            dx, dy = p[0] - w[0], p[1] - w[1]
            Lw = math.hypot(dx, dy)
            if Lw > 0.5:
                d.items.append(("line", w, (p[0] + s[0] * ov, p[1] + s[1] * ov), "thin"))
        # dimension line + arrows
        uxy = (pb[0] - pa[0], pb[1] - pa[1])
        Lab = math.hypot(*uxy)
        ux, uy = uxy[0] / Lab, uxy[1] / Lab
        if inside:
            d.items.append(("line", pa, pb, "thin"))
            d.items.append(("arrow", pa, (-ux, -uy)))
            d.items.append(("arrow", pb, (ux, uy)))
            d.dimlines.append((pa, pb))
        else:
            e1 = (pa[0] - ux * (al + 3), pa[1] - uy * (al + 3))
            e2 = (pb[0] + ux * (al + 3 + tw + 1), pb[1] + uy * (al + 3 + tw + 1))
            d.items.append(("line", e1, e2, "thin"))
            d.items.append(("arrow", pa, (ux, uy)))
            d.items.append(("arrow", pb, (-ux, -uy)))
            d.dimlines.append((e1, e2))
        d.items.append(("text", tp, text, ang))
        d.texts.append(box)
        it.drawn = dict(view=it.view.id, text=text, a=pa, b=pb)

    def _pt(self, t, s, u, L):
        # point with coordinate u along t and L along s (t, s orthonormal paper vectors)
        return (t[0] * u + s[0] * L, t[1] * u + s[1] * L)

    def _lin_text_pos(self, pa, pb, inside, tw):
        S = self.s
        dx, dy = pb[0] - pa[0], pb[1] - pa[1]
        mx, my = dx, -dy                     # math coords
        ang = math.degrees(math.atan2(my, mx))
        if ang > 90.01 or ang <= -89.99:
            ang = ang - 180 if ang > 0 else ang + 180
        a = math.radians(ang)
        ux, uy = math.cos(a), -math.sin(a)   # paper unit along text
        nx, ny = -math.sin(a), -math.cos(a)  # paper "up" of text
        if inside:
            cx, cy = (pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2
        else:
            # beyond the end that is further along the text direction
            far = pb if (pb[0] - pa[0]) * ux + (pb[1] - pa[1]) * uy > 0 else pa
            off = S.arrow_len + 3 + tw / 2
            cx, cy = far[0] + ux * off, far[1] + uy * off
        g = 0.9
        return (cx + nx * g, cy + ny * g), ang

    def _free_angle(self, d, c, cands, r, Lout, text):
        """Pick the candidate angle whose leader + text collide least."""
        S = self.s
        best, bs = None, 1e9
        pref = [45, 135, 315, 225, 30, 60, 120, 150, 300, 330, 210, 240, 0, 90, 180, 270, 15, 75, 105, 165,
                195, 255, 285, 345]
        for k in sorted(cands, key=lambda a: pref.index(a) if a in pref else 99):
            a = math.radians(k)
            tip = (c[0] + r * math.cos(a), c[1] - r * math.sin(a))
            out = (c[0] + (r + Lout) * math.cos(a), c[1] - (r + Lout) * math.sin(a))
            tw = S.text_w(text)
            right = math.cos(a) >= -1e-9
            tx = (out[0] + (tw / 2 + 1) * (1 if right else -1), out[1] - 0.9)
            box = Canvas(1, 1, S).text_bbox(tx, text, S.h, 0, "middle", "base")
            cost = sum(1 for g in d.geo_segs if _seg_hits_box(g[0], g[1], box)) * 3
            cost += sum(5 for b in d.texts if _box_overlap(box, b))
            cost += sum(1 for g in d.geo_segs if _seg_cross((tip[0] + 0.01 * (out[0] - tip[0]), tip[1] + 0.01 * (out[1] - tip[1])), out, g[0], g[1]))
            cost += (pref.index(k) if k in pref else 30) * 0.01
            if cost < bs:
                bs, best = cost, k
        return best

    def _rad_geom(self, c, r, k, text, kind, mode=None):
        S = self.s
        a = math.radians(k)
        u = (math.cos(a), -math.sin(a))
        tip = (c[0] + r * u[0], c[1] + r * u[1])
        tw = S.text_w(text)
        if (mode == "in" or (mode is None and r > tw + S.arrow_len + 4)) and kind == "rad":
            ang = math.degrees(math.atan2(-u[1], u[0]))
            if ang > 90.01 or ang <= -89.99:
                ang = ang - 180 if ang > 0 else ang + 180
            mid = (c[0] + u[0] * (r - tw / 2 - S.arrow_len - 1), c[1] + u[1] * (r - tw / 2 - S.arrow_len - 1))
            aa = math.radians(ang)
            tp = (mid[0] - math.sin(aa) * 0.9, mid[1] - math.cos(aa) * 0.9)
            box = Canvas(1, 1, S).text_bbox(tp, text, S.h, ang, "middle", "base")
            return dict(mode="in", tip=tip, u=u, tp=tp, ang=ang, box=box, segs=[(c, tip)])
        knee = (tip[0] + u[0] * 7, tip[1] + u[1] * 7)
        right = u[0] >= -1e-9
        end = (knee[0] + (tw + 2) * (1 if right else -1), knee[1])
        x0 = min(knee[0], end[0]) + 1
        tp = (x0 + tw / 2, knee[1] - 0.9)
        box = Canvas(1, 1, S).text_bbox(tp, text, S.h, 0, "middle", "base")
        return dict(mode="out", tip=tip, u=u, box=box, segs=[(tip, knee), (knee, end)])

    def _best_rad(self, d, c, r, cands, text, kind):
        pref = [45, 135, 315, 225, 30, 60, 120, 150, 300, 330, 210, 240, 0, 90, 180, 270]
        best, bs = None, 1e18
        S = self.s
        modes = ["out"] + (["in"] if (kind == "rad" and r > S.text_w(text) + S.arrow_len + 4) else [])
        for k, md in [(k, m) for k in cands for m in modes]:
            g = self._rad_geom(c, r, k, text, kind, md)
            cost = sum(4 for s_ in d.geo_segs if _seg_hits_box(s_[0], s_[1], g["box"], 0.2))
            cost += sum(20 for b in d.texts if _box_overlap(g["box"], b))
            for a, b in g["segs"]:
                a2 = (a[0] + (b[0] - a[0]) * 0.02, a[1] + (b[1] - a[1]) * 0.02)
                cost += sum(2 for s_ in d.geo_segs if _seg_cross(a2, b, s_[0], s_[1]))
                cost += sum(8 for b_ in d.texts if _seg_hits_box(a, b, b_, 0.2))
            cost += (pref.index(k) if k in pref else 20) * 0.05 + (0.5 if md == "out" else 0)
            if cost < bs:
                bs, best = cost, (k, md)
        return best

    def _place_rad(self, it):
        S = self.s
        d = self.vd[it.view.id]
        v = it.view
        c = d.P(proj(it.loc, v.right, v.up))
        r = it.r * self.sc
        text = it.text
        if it.kind == "dia" and "Ø" not in text:
            text = "Ø" + text
        k, md = self._best_rad(d, c, r, it.geo["arc"], text, it.kind)
        g = self._rad_geom(c, r, k, text, it.kind, md)
        if g["mode"] == "in":
            d.items.append(("line", c, g["tip"], "thin"))
            d.items.append(("arrow", g["tip"], g["u"]))
            d.items.append(("text", g["tp"], text, g["ang"]))
            d.texts.append(g["box"])
            d.dimlines.append((c, g["tip"]))
        else:
            self._leader(d, g["tip"], g["u"], text)
        it.drawn = dict(view=v.id, text=text, at=g["tip"])

    def _leader(self, d, tip, u, text, inward=True, tokens=None):
        """Leader from a point on a contour (arrow) going out along u, then a horizontal shoulder."""
        S = self.s
        knee = (tip[0] + u[0] * 7, tip[1] + u[1] * 7)
        right = u[0] >= -1e-9
        tw = self._tokens_w(tokens) if tokens else S.text_w(text)
        end = (knee[0] + (tw + 2) * (1 if right else -1), knee[1])
        d.items.append(("line", tip, knee, "thin"))
        d.items.append(("line", knee, end, "thin"))
        d.items.append(("arrow", tip, (-u[0], -u[1])))
        x0 = min(knee[0], end[0]) + 1
        if tokens:
            d.items.append(("tokens", (x0, knee[1] - 0.9), tokens))
            box = (x0, knee[1] - 0.9 - S.h, x0 + tw, knee[1] - 0.9 + 0.3 * S.h)
        else:
            tp = (x0 + tw / 2, knee[1] - 0.9)
            d.items.append(("text", tp, text, 0))
            box = Canvas(1, 1, S).text_bbox(tp, text, S.h, 0, "middle", "base")
        d.texts.append(box)
        d.dimlines += [(tip, knee), (knee, end)]

    def _tokens_w(self, tokens):
        S = self.s
        w = 0
        for t in tokens:
            w += S.text_w(t[1]) if t[0] == "t" else S.h * 1.0 + 0.6
        return w

    def _place_note(self, it):
        S = self.s
        d = self.vd[it.view.id]
        v = it.view
        c = d.P(proj(it.pts[0], v.right, v.up))
        r = it.r * self.sc
        # leader to the outer circle if a countersink/counterbore makes it bigger
        R = r
        for sy in it.sym:
            if sy[0] in ("cs", "cb"):
                R = max(R, float(sy[1][1:].replace(",", ".")) / 2 * self.sc)
        tokens = [("t", it.text)]
        for sy in it.sym:
            if sy[0] == "cs":
                tokens += [("t", " "), ("cs",), ("t", f"{sy[1]}×{sy[2]}")]
            elif sy[0] == "cb":
                tokens += [("t", " "), ("cb",), ("t", sy[1]), ("t", " ↧" + sy[2])]
            elif sy[0] == "depth":
                tokens += [("t", " ↧" + sy[1])]
        full = "".join(t[1] if t[0] == "t" else "  " for t in tokens)
        cand = it.geo["arc"]
        k, _ = self._best_rad(d, c, R, cand, full + "    ", "note")
        a = math.radians(k)
        u = (math.cos(a), -math.sin(a))
        tip = (c[0] + R * u[0], c[1] + R * u[1])
        self._leader(d, tip, u, full, tokens=[(t[0], t[1] if len(t) > 1 else "") for t in tokens])
        it.drawn = dict(view=v.id, text=full.strip(), at=tip)

    def _place_ang(self, it):
        S = self.s
        d = self.vd[it.view.id]
        v = it.view
        V = d.P(proj(it.v, v.right, v.up))
        w1 = _d2(v, it.w1)
        w2 = _d2(v, it.w2)
        R = 16.0
        a1 = math.degrees(math.atan2(-w1[1], w1[0]))
        a2 = math.degrees(math.atan2(-w2[1], w2[0]))
        sweep = (a2 - a1) % 360
        if sweep > 180:
            a1, a2 = a2, a1
            sweep = 360 - sweep
        pts = []
        n = max(10, int(sweep / 3))
        for i in range(n + 1):
            aa = math.radians(a1 + sweep * i / n)
            pts.append((V[0] + R * math.cos(aa), V[1] - R * math.sin(aa)))
        d.items.append(("path", pts, "thin"))
        for aa, sg in ((a1, 1), (a2, -1)):
            r_ = math.radians(aa)
            tip = (V[0] + R * math.cos(r_), V[1] - R * math.sin(r_))
            tang = (-math.sin(r_) * -sg, -math.cos(r_) * -sg)
            d.items.append(("arrow", tip, (tang[0], tang[1])))
            d.items.append(("line", V, (V[0] + (R + 2) * math.cos(r_), V[1] - (R + 2) * math.sin(r_)), "thin"))
        am = math.radians(a1 + sweep / 2)
        tp = (V[0] + (R + 4) * math.cos(am), V[1] - (R + 4) * math.sin(am) + S.h / 2)
        d.items.append(("text", tp, it.text, 0))
        d.texts.append(Canvas(1, 1, S).text_bbox(tp, it.text, S.h, 0, "middle", "base"))
        d.dimlines.append((pts[0], pts[-1]))
        it.drawn = dict(view=v.id, text=it.text, at=tp)

    # ================================================================ layout
    def layout(self):
        W, H = SHEETS[self.sheet_name]
        S = self.s
        area = (20 + 6, 10 + 6, W - 10 - 6, H - 10 - 6)
        tb = (W - 10 - 182, H - 10 - 40, W - 10, H - 10)      # title block + scale/symbol row
        lab = S.h_label + 4
        envs = {k: d.env() for k, d in self.vd.items()}
        envs = {k: (e[0], e[1] - lab, e[2], e[3]) for k, e in envs.items()}
        pos = {}
        main = self.main.id
        pos[main] = (0.0, 0.0)
        gap = 8.0

        def box(k, p=None):
            e, p = envs[k], (p or pos[k])
            return (e[0] + p[0], e[1] + p[1], e[2] + p[0], e[3] + p[1])

        std, aux = [], []
        for v in self.views.values():
            if v.id == main:
                continue
            sx, sy = v.sdir
            (std if (abs(sx) > 0.999 or abs(sy) > 0.999) else aux).append(v)
        for v in std:
            par = v.parent
            sx, sy = v.sdir
            sxp, syp = sx, -sy
            pe = box(par.id)
            e = envs[v.id]
            po = pos[par.id]
            if abs(syp) > 0.999:
                pos[v.id] = (po[0], (pe[3] + gap - e[1]) if syp > 0 else (pe[1] - gap - e[3]))
            else:
                pos[v.id] = ((pe[2] + gap - e[0]) if sxp > 0 else (pe[0] - gap - e[2]), po[1])
        allb = [box(k) for k in pos]
        gx0, gy0 = min(b[0] for b in allb), min(b[1] for b in allb)
        gx1, gy1 = max(b[2] for b in allb), max(b[3] for b in allb)
        aw, ah = area[2] - area[0], area[3] - area[1]
        # standard group: centred, or pushed left when auxiliary views need room
        dx = area[0] + (aw - (gx1 - gx0)) / 2 - gx0 if not aux else area[0] + 4 - gx0
        dy = area[1] + (ah - (gy1 - gy0)) / 2 - gy0
        for k in pos:
            pos[k] = (pos[k][0] + dx, pos[k][1] + dy)
        for _ in range(200):
            if not any(_box_overlap(box(k), tb, 2) for k in pos):
                break
            gy0 = min(box(k)[1] for k in pos)
            gx0 = min(box(k)[0] for k in pos)
            if gy0 > area[1] + 1:
                pos = {k: (p[0], p[1] - 1) for k, p in pos.items()}
            elif gx0 > area[0] + 1:
                pos = {k: (p[0] - 1, p[1]) for k, p in pos.items()}
            else:
                break

        def free(bb):
            if bb[0] < area[0] or bb[1] < area[1] or bb[2] > area[2] or bb[3] > area[3]:
                return False
            if _box_overlap(bb, tb, 2):
                return False
            return not any(_box_overlap(bb, box(k), gap / 2) for k in pos)
        for v in aux:
            par = v.parent
            sx, sy = v.sdir
            sxp, syp = sx, -sy
            po = pos[par.id]
            ideal = None
            for dist in range(10, 700, 3):
                cand = (po[0] + sxp * dist, po[1] + syp * dist)
                if not any(_box_overlap(box(v.id, cand), box(k), gap / 2) for k in pos):
                    ideal = cand
                    break
            if ideal is not None and free(box(v.id, ideal)):
                pos[v.id] = ideal
                continue
            best, bd = None, 1e18
            e = envs[v.id]
            for x in range(int(area[0] - e[0]), int(area[2] - e[2]) + 1, 3):
                for y in range(int(area[1] - e[1]), int(area[3] - e[3]) + 1, 3):
                    if free(box(v.id, (x, y))):
                        dd = (x - ideal[0]) ** 2 + (y - ideal[1]) ** 2 if ideal else 0
                        if dd < bd:
                            bd, best = dd, (x, y)
            if best is None:
                self.lint.append(f"vista {v.label or v.id}: sem espaço livre na folha {self.sheet_name}")
                best = ideal or (area[2], area[1])
            pos[v.id] = best
        allb = [box(k) for k in pos]
        cw = max(b[2] for b in allb) - min(b[0] for b in allb)
        ch = max(b[3] for b in allb) - min(b[1] for b in allb)
        bad = [k for k in pos if not free(box(k)) and False]
        for k in pos:
            bb = box(k)
            if bb[0] < area[0] - 0.5 or bb[1] < area[1] - 0.5 or bb[2] > area[2] + 0.5 or bb[3] > area[3] + 0.5 \
                    or _box_overlap(bb, tb, 0):
                self.lint.append(f"vista {self.views[k].label or k} sai da zona de desenho / toca na legenda "
                                 f"(composição {cw:.0f}×{ch:.0f} mm): usar escala menor ou folha maior")
        for k in pos:
            self.vd[k].origin = pos[k]
        self.env_abs = {k: box(k) for k in pos}

    # ================================================================ render
    def render(self):
        W, H = SHEETS[self.sheet_name]
        S = self.s
        cv = Canvas(W, H, S)
        self.cv = cv
        for k, d in self.vd.items():
            ox, oy = d.origin
            T = lambda p: (p[0] + ox, p[1] + oy)
            for f in d.rings:
                cv.hatch([[T(p) for p in r] for r in f])
            for f in d.rings:
                for r in f:
                    cv.path([T(p) for p in r], "vis", close=True)
            for pl in d.hid:
                cv.path([T(p) for p in pl], "hid")
            for pl in d.vis:
                cv.path([T(p) for p in pl], "vis")
            for a, b in d.wavy:
                cv.wavy(T(a), T(b))
            for itm in d.items:
                kd = itm[0]
                if kd == "line":
                    cv.line(T(itm[1]), T(itm[2]), itm[3])
                elif kd == "path":
                    cv.path([T(p) for p in itm[1]], itm[2])
                elif kd == "arrow":
                    cv.arrow(T(itm[1]), itm[2])
                elif kd == "text":
                    cv.text(T(itm[1]), itm[2], ang=itm[3])
                elif kd == "tokens":
                    self._draw_tokens(cv, T(itm[1]), itm[2])
            # labels
            v = d.v
            if v.label:
                e = self.env_abs[k]
                txt = f"{v.label}-{v.label}" if v.is_section else v.label
                gb = d.gb
                cv.text(((gb[0] + gb[2]) / 2 + ox, e[1] + S.h_label + 1), txt, h=S.h_label)
        self._section_marks()
        self._aux_arrows()
        self._sheet()
        return cv

    def _draw_tokens(self, cv, p, tokens):
        S = self.s
        x, y = p
        for t in tokens:
            if t[0] == "t":
                w = S.text_w(t[1])
                if t[1].strip():
                    cv.text((x + w / 2, y), t[1], track=False)
                x += w
            elif t[0] == "cs":
                h = S.h
                cv.path([(x + 0.3, y - h), (x + 0.3 + h / 2, y), (x + 0.3 + h, y - h)], "thin")
                x += h + 0.6
            elif t[0] == "cb":
                h = S.h
                cv.path([(x + 0.3, y - h), (x + 0.3, y), (x + 0.3 + h, y), (x + 0.3 + h, y - h)], "thin")
                x += h + 0.6

    def _section_marks(self):
        S = self.s
        for sv in self.views.values():
            if not sv.is_section:
                continue
            cands = [v for v in self.views.values() if v is not sv and _perp(sv.vd, v.vd)]
            cands.sort(key=lambda v: (v.is_section, v.std is None, v.parent is not sv))
            ind = cands[0] if cands else None
            if ind is None:
                self.lint.append(f"corte {sv.label}: nenhuma vista mostra o plano de corte de perfil")
                continue
            d = self.vd[ind.id]
            ox, oy = d.origin
            T = lambda p: (p[0] + ox, p[1] + oy)
            n2 = _d2(ind, sv.vd)               # paper unit: plane normal in indicator view
            t2 = (-n2[1], n2[0])
            gb = d.gb
            corners = [(gb[0], gb[1]), (gb[2], gb[1]), (gb[0], gb[3]), (gb[2], gb[3])]
            tmin = min(c[0] * t2[0] + c[1] * t2[1] for c in corners) - 6
            tmax = max(c[0] * t2[0] + c[1] * t2[1] for c in corners) + 6
            steps = []
            k = self.m.k
            from .views import _plane
            from .spec import vec as _vec
            for st in sv.d["cut"]:
                nn, off = _plane(dict(st, n=st.get("n", list(sv.vd))), k)
                if nn.dot(sv.vd) < 0:
                    nn, off = nn * -1, -off
                cpos = off * self.sc
                lo, hi = tmin, tmax
                for cond in st.get("if", []):
                    cn = _vec(cond[0]).normalized()
                    c2 = _d2(ind, cn)
                    a_ = t2[0] * c2[0] + t2[1] * c2[1]
                    b_ = n2[0] * c2[0] + n2[1] * c2[1]
                    if abs(a_) < 1e-6:
                        continue
                    tb = (cond[2] * k * self.sc - cpos * b_) / a_
                    le = cond[1].startswith("<")
                    if le == (a_ > 0):
                        hi = min(hi, tb)
                    else:
                        lo = max(lo, tb)
                steps.append((lo, hi, cpos))
            steps.sort()
            path = []
            for i, (lo, hi, c) in enumerate(steps):
                a = (t2[0] * lo + n2[0] * c, t2[1] * lo + n2[1] * c)
                b = (t2[0] * hi + n2[0] * c, t2[1] * hi + n2[1] * c)
                path += [a, b]
            P = [T(p) for p in path]
            self.cv.path(P, "cut")
            seg = 7.0
            # thick ends and corners
            def thick(a, b, L):
                Lab = math.hypot(b[0] - a[0], b[1] - a[1])
                if Lab < 1e-6:
                    return a
                u = ((b[0] - a[0]) / Lab, (b[1] - a[1]) / Lab)
                e = (a[0] + u[0] * min(L, Lab), a[1] + u[1] * min(L, Lab))
                self.cv.line(a, e, "cutthick")
                return e
            thick(P[0], P[1], seg)
            thick(P[-1], P[-2], seg)
            for i in range(1, len(P) - 1):
                thick(P[i], P[i - 1], 4)
                thick(P[i], P[i + 1], 4)
            vd2 = _d2(ind, sv.vd)
            for end in (P[0], P[-1]):
                inw = 2.5
                base = end
                tip = (base[0] + vd2[0] * (S.h_label * 2), base[1] + vd2[1] * (S.h_label * 2))
                self.cv.line(base, tip, "cutthick")
                self.cv.arrow(tip, vd2, L=S.h_label)
                # letter beside the arrow, upright
                lp = (tip[0] + (3 if vd2[1] != 0 else 0) + vd2[0] * 2, tip[1] + vd2[1] * 2 + (S.h_label if vd2[1] > 0 else -1))
                self._letter(d, lambda p: p, tip, vd2, sv.label, absolute=True, origin=(ox, oy))

    def _aux_arrows(self):
        S = self.s
        for v in self.views.values():
            if v.parent is None or v.std in ("top", "left", "right", "bottom", "rear", "front") or v.is_section:
                continue
            par = v.parent
            d = self.vd[par.id]
            ox, oy = d.origin
            bb = v.solid.bounding_box()
            cen = Vector((bb.min.X + bb.max.X) / 2, (bb.min.Y + bb.max.Y) / 2, (bb.min.Z + bb.max.Z) / 2)
            if v.d.get("at"):
                cen = Vector(*v.d["at"]) * self.m.k
            c = d.P(proj(cen, par.right, par.up))
            u = _d2(par, v.vd)
            far = (c[0] - u[0] * 1000, c[1] - u[1] * 1000)
            best_t = None
            for a, b in d.geo_segs:
                t_ = _ray_hit(c, far, a, b)
                if t_ is not None and t_ > 1e-4 and (best_t is None or t_ < best_t):
                    best_t = t_
            best_t = best_t or 0.0
            dist = best_t * 1000
            tip = (c[0] - u[0] * (dist + 1.5), c[1] - u[1] * (dist + 1.5))
            L = 12
            tail = (tip[0] - u[0] * L, tip[1] - u[1] * L)
            T = lambda p: (p[0] + ox, p[1] + oy)
            self.cv.line(T(tail), T(tip), "cutthick")
            self.cv.arrow(T(tip), u, L=S.h_label)
            self._letter(d, T, tail, u, v.label)

    def _letter(self, d, T, anchor, u, label, absolute=False, origin=(0, 0)):
        """Upright letter near an arrow, placed where it collides least with the drawing."""
        S = self.s
        h = S.h_label
        ox, oy = origin if absolute else (0, 0)
        best, bc = None, 1e9
        for ang in range(0, 360, 30):
            a = math.radians(ang)
            for r in (h * 0.9, h * 1.4):
                p = (anchor[0] + r * math.cos(a), anchor[1] + r * math.sin(a) + h / 2)
                P = T(p)
                box = self.cv.text_bbox(P, label, h, 0, "middle", "base")
                cost = sum(1 for g in self.cv.segments(("vis", "hid", "cutthick", "thin", "cut")) if _seg_hits_box(g[0], g[1], box, 0.3))
                cost += sum(5 for b in self.cv.text_boxes if _box_overlap(box, b[:4]))
                cost += r * 0.05
                if cost < bc:
                    bc, best = cost, P
        self.cv.text(best, label, h=h)

    def _sheet(self):
        W, H = SHEETS[self.sheet_name]
        S = self.s
        cv = self.cv
        # frame (esquadria) and centring marks (ISO 5457)
        cv.path([(20, 10), (W - 10, 10), (W - 10, H - 10), (20, H - 10)], "frame", close=True)
        for a, b in (((W / 2, 0), (W / 2, 15)), ((W / 2, H), (W / 2, H - 15)),
                     ((0, H / 2), (25, H / 2)), ((W, H / 2), (W - 15, H / 2))):
            cv.line(a, b, "frame")
        cv.text((W - 12, H - 5), self.sheet_name, h=2.5, anchor="end", track=False)
        # title block (ISO 7200 layout, 180 mm wide)
        x0, y1 = W - 10 - 180, H - 10
        y0 = y1 - 26
        m = self.meta
        cv.path([(x0, y0), (x0 + 180, y0), (x0 + 180, y1), (x0, y1)], "frame", close=True)
        rows = [y0, y0 + 8, y0 + 17, y1]
        cv.line((x0, rows[1]), (x0 + 180, rows[1]), "thin")
        for x in (30, 70, 130):
            cv.line((x0 + x, rows[0]), (x0 + x, y1), "thin")
        cv.line((x0 + 30, rows[2]), (x0 + 70, rows[2]), "thin")
        cv.line((x0 + 130, rows[2]), (x0 + 180, rows[2]), "thin")
        for x in (138, 160, 168):
            cv.line((x0 + x, rows[2]), (x0 + x, y1), "thin")

        def fld(x, y, label, value, h=2.5, w=None):
            cv.text((x0 + x + 1, y + 2.3), label, h=1.8, anchor="start", track=False)
            if value:
                cv.text((x0 + x + 1.5, y + 2.3 + h + 1.6), str(value), h=h, anchor="start", track=False)
        fld(0, rows[0], "Departamento resp.", m.get("dept", ""))
        fld(30, rows[0], "Referência técnica", m.get("ref", ""))
        fld(70, rows[0], "Tipo de documento", m.get("type", "Desenho de definição"))
        fld(130, rows[0], "Estado do documento", m.get("status", ""))
        fld(0, rows[1], "Proprietário legal", m.get("owner", ""))
        fld(30, rows[1], "Criado por", m.get("author", ""))
        fld(30, rows[2], "Aprovado por", m.get("approved", ""))
        cv.text((x0 + 71, rows[1] + 2.3), "Título", h=1.8, anchor="start", track=False)
        cv.text((x0 + 100, rows[1] + 12), m.get("title", self.m.spec.get("name", "")), h=5, track=False)
        fld(130, rows[1], "Nº de identificação", m.get("number", ""))
        fld(130, rows[2], "Rev.", m.get("rev", ""), h=2.5)
        fld(138, rows[2], "Data de edição", m.get("date", ""), h=2.5)
        fld(160, rows[2], "Líng.", m.get("lang", "pt"), h=2.5)
        fld(168, rows[2], "Folha", m.get("sheet_no", "1/1"), h=2.5)
        # scale + first-angle symbol, just above the title block (outside it, ISO 7200)
        yb = y0 - 3
        cv.text((x0 + 2, yb), f"ESCALA {self.scale_txt}", h=3.5, anchor="start", track=False)
        self._first_angle(x0 + 160, yb - 5)

    def _first_angle(self, x, ycen):
        cv = self.cv
        h, Hh = 5.0, 10.0
        # truncated cone (small end left) and its view from the left placed on the right
        xl = x - Hh - 1.5
        cv.path([(xl, ycen - h / 2), (xl + Hh, ycen - Hh / 2), (xl + Hh, ycen + Hh / 2), (xl, ycen + h / 2)],
                "vis", close=True)
        cx = x + 1.5 + Hh / 2
        cv.circle((cx, ycen), Hh / 2, "vis")
        cv.circle((cx, ycen), h / 2, "vis")
        cv.line((xl - 1.5, ycen), (cx + Hh / 2 + 1.5, ycen), "ctr")
        cv.line((cx, ycen - Hh / 2 - 1.5), (cx, ycen + Hh / 2 + 1.5), "ctr")

    # ================================================================ lint + outputs
    def check(self):
        cv = self.cv
        boxes = cv.text_boxes
        geo = cv.segments(("vis", "hid"))
        dims = cv.segments(("thin",))
        n_tt = n_tg = 0
        for i, a in enumerate(boxes):
            for b in boxes[i + 1:]:
                if _box_overlap(a[:4], b[:4], -0.2):
                    n_tt += 1
                    self.lint.append(f"texto sobreposto: '{a[4]}' / '{b[4]}'")
            hits = sum(1 for s in geo if _seg_hits_box(s[0], s[1], a[:4], -0.3))
            if hits:
                n_tg += 1
                self.lint.append(f"texto '{a[4]}' cruza {hits} linha(s) da peça")
        for w in self.dimr.warn:
            self.lint.append("cotagem: " + w)
        return dict(text_text=n_tt, text_geo=n_tg)

    def record(self):
        dims = []
        for it in self.placed:
            if getattr(it, "drawn", None):
                dims.append(dict(kind=it.kind, **{k: v for k, v in it.drawn.items() if k in ("view", "text")}))
        return dict(sheet=self.sheet_name, scale=self.scale_txt,
                    views=[dict(id=v.id, label=v.label, dir=[round(v.vd.X, 4), round(v.vd.Y, 4), round(v.vd.Z, 4)],
                                section=v.is_section, origin=self.vd[v.id].origin) for v in self.views.values()],
                    dims=dims, lint=self.lint)


def _dist_seg(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    if L2 < 1e-12:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = max(0, min(1, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


def _seg_cross(p1, p2, p3, p4):
    def o(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    return (o(p1, p2, p3) * o(p1, p2, p4) < 0) and (o(p3, p4, p1) * o(p3, p4, p2) < 0)


def _ray_hit(p, q, a, b):
    """Parameter t in [0,1] along p->q where it crosses segment a-b (None if no crossing)."""
    r = (q[0] - p[0], q[1] - p[1])
    s_ = (b[0] - a[0], b[1] - a[1])
    den = r[0] * s_[1] - r[1] * s_[0]
    if abs(den) < 1e-12:
        return None
    t = ((a[0] - p[0]) * s_[1] - (a[1] - p[1]) * s_[0]) / den
    u = ((a[0] - p[0]) * r[1] - (a[1] - p[1]) * r[0]) / den
    return t if (0 <= t <= 1 and 0 <= u <= 1) else None


def _point_in_bbox(q, b):
    return b[0] - 1 <= q[0] <= b[2] + 1 and b[1] - 1 <= q[1] <= b[3] + 1


def make_drawing(model, out_prefix, sheet=None, scale=None, png=True, pdf=True):
    dr = Drawing(model, sheet=sheet, scale=scale)
    dr.assign()
    dr.place()
    dr.layout()
    cv = dr.render()
    stats = dr.check()
    open(out_prefix + ".svg", "w").write(cv.to_svg())
    if png:
        cv.to_mpl(out_prefix + ".png", dpi=150)
    if pdf:
        cv.to_mpl(out_prefix + ".pdf")
    rec = dr.record()
    rec["stats"] = stats
    json.dump(rec, open(out_prefix + ".info.json", "w"), ensure_ascii=False, indent=1)
    return dr, rec
