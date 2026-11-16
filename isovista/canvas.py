"""Display list in sheet millimetres (y grows DOWN) with SVG and matplotlib (PNG/PDF) back-ends."""
import math
from .style import Style


class Canvas:
    def __init__(self, w, h, style=None):
        self.w, self.h = w, h
        self.s = style or Style()
        self.items = []        # (kind, data)
        self.text_boxes = []   # (x0,y0,x1,y1,label) for lint

    # ---------------- primitives
    def path(self, pts, cls="vis", close=False):
        if len(pts) >= 2:
            self.items.append(("path", (list(pts), cls, close)))

    def line(self, a, b, cls="thin"):
        self.path([a, b], cls)

    def circle(self, c, r, cls="vis", n=72):
        self.path([(c[0] + r * math.cos(2 * math.pi * i / n), c[1] + r * math.sin(2 * math.pi * i / n))
                   for i in range(n + 1)], cls)

    def poly_fill(self, pts):
        self.items.append(("fill", list(pts)))

    def hatch(self, rings, angle=45.0, step=None):
        self.items.append(("hatch", ([list(r) for r in rings], angle, step or self.s.hatch_step)))

    def text(self, p, s, h=None, ang=0.0, anchor="middle", valign="base", bold=False, track=True):
        """Text with cap height h at p; ang in degrees, counter-clockwise on paper.
        anchor: start|middle|end ; valign: base (p on baseline) | center."""
        h = h or self.s.h
        self.items.append(("text", (p, s, h, ang, anchor, valign, bold)))
        if track:
            self.text_boxes.append(self.text_bbox(p, s, h, ang, anchor, valign) + (s,))

    def text_bbox(self, p, s, h, ang, anchor, valign):
        w = self.s.text_w(s, h)
        x0 = {"start": 0, "middle": -w / 2, "end": -w}[anchor]
        y0 = 0 if valign == "base" else -h / 2      # local y up
        corners = [(x0, y0 - 0.25 * h), (x0 + w, y0 - 0.25 * h), (x0 + w, y0 + h), (x0, y0 + h)]
        a = math.radians(ang)
        pts = [(p[0] + x * math.cos(a) - y * math.sin(a), p[1] - (x * math.sin(a) + y * math.cos(a)))
               for x, y in corners]
        xs, ys = [q[0] for q in pts], [q[1] for q in pts]
        return (min(xs), min(ys), max(xs), max(ys))

    def arrow(self, tip, d, L=None, angle=30.0):
        """Closed filled arrow head, included angle `angle`, pointing along d (sheet coords)."""
        L = L or self.s.arrow_len
        n = math.hypot(*d)
        ux, uy = d[0] / n, d[1] / n
        hw = L * math.tan(math.radians(angle / 2))
        bx, by = tip[0] - ux * L, tip[1] - uy * L
        self.poly_fill([tip, (bx - uy * hw, by + ux * hw), (bx + uy * hw, by - ux * hw)])

    def wavy(self, a, b, amp=None, wl=None):
        amp = amp or 1.2
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if L < 1e-6:
            return
        wl = wl or 12.0
        ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        n = max(8, int(L / 0.6))
        waves = max(1.0, round(L / wl))
        pts = [(a[0] + ux * L * t - uy * amp * math.sin(t * waves * 2 * math.pi),
                a[1] + uy * L * t + ux * amp * math.sin(t * waves * 2 * math.pi))
               for t in (i / n for i in range(n + 1))]
        self.path(pts, "thin")

    # ---------------- segments of everything drawn (for collision lint)
    def segments(self, classes=("vis", "hid", "thin", "ctr", "cut")):
        out = []
        for k, d in self.items:
            if k == "path" and d[1] in classes:
                pts = d[0]
                out += list(zip(pts[:-1], pts[1:]))
        return out

    # ---------------- SVG
    def _dash(self, cls):
        d = self.s.thin
        if cls == "hid":
            return f"{self.s.dash * d:.2f} {self.s.gap * d:.2f}"
        if cls in ("ctr", "cut", "phantom"):
            base = f"{self.s.long_dash * d:.2f} {self.s.gap * d:.2f} {self.s.dot * d:.2f} {self.s.gap * d:.2f}"
            if cls == "phantom":
                base += f" {self.s.dot * d:.2f} {self.s.gap * d:.2f}"
            return base
        return None

    def _lw(self, cls):
        return {"vis": self.s.thick, "cutthick": self.s.thick, "frame": self.s.thick, "grid": 0.18}.get(cls, self.s.thin)

    @staticmethod
    def _col(cls):
        return "#a0a0a0" if cls == "grid" else "#000"

    def to_svg(self):
        S = self.s
        out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" '
               f'width="{self.w}mm" height="{self.h}mm">',
               f'<rect width="{self.w}" height="{self.h}" fill="#fff"/>']
        defs = []
        for i, (k, d) in enumerate(self.items):
            if k == "path":
                pts, cls, close = d
                dd = "M" + " L".join(f"{x:.3f},{y:.3f}" for x, y in pts) + ("Z" if close else "")
                dash = self._dash(cls)
                da = f' stroke-dasharray="{dash}"' if dash else ""
                out.append(f'<path d="{dd}" fill="none" stroke="{self._col(cls)}" stroke-width="{self._lw(cls)}" '
                           f'stroke-linecap="round" stroke-linejoin="round"{da}/>')
            elif k == "fill":
                dd = "M" + " L".join(f"{x:.3f},{y:.3f}" for x, y in d) + "Z"
                out.append(f'<path d="{dd}" fill="#000"/>')
            elif k == "hatch":
                rings, ang, step = d
                pid = f"h{i}"
                defs.append(f'<pattern id="{pid}" width="{step}" height="{step}" patternUnits="userSpaceOnUse" '
                            f'patternTransform="rotate({-ang})"><line x1="0" y1="0" x2="{step}" y2="0" '
                            f'stroke="#000" stroke-width="{S.thin}"/></pattern>')
                dd = " ".join("M" + " L".join(f"{x:.3f},{y:.3f}" for x, y in r) + "Z" for r in rings)
                out.append(f'<path d="{dd}" fill="url(#{pid})" fill-rule="evenodd" stroke="none"/>')
            elif k == "text":
                p, s, h, ang, anchor, valign, bold = d
                fs = h / S.cap_ratio
                dy = f' dy="{h / 2:.3f}"' if valign == "center" else ""
                tr = f' transform="rotate({-ang:.2f} {p[0]:.3f} {p[1]:.3f})"' if ang else ""
                fw = ' font-weight="bold"' if bold else ""
                s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                out.append(f'<text x="{p[0]:.3f}" y="{p[1]:.3f}"{dy} font-size="{fs:.3f}" '
                           f'font-family="{S.font_svg}" text-anchor="{anchor}"{fw}{tr}>{s}</text>')
        if defs:
            out.insert(2, "<defs>" + "".join(defs) + "</defs>")
        out.append("</svg>")
        return "\n".join(out)

    # ---------------- matplotlib (PNG / PDF), no system libraries needed
    def to_mpl(self, path, dpi=150):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Polygon, PathPatch
        from matplotlib.path import Path
        S = self.s
        pt = 72 / 25.4
        fig = plt.figure(figsize=(self.w / 25.4, self.h / 25.4))
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_xlim(0, self.w)
        ax.set_ylim(self.h, 0)
        ax.set_aspect("equal")
        ax.axis("off")
        for k, d in self.items:
            if k == "path":
                pts, cls, close = d
                if close:
                    pts = pts + [pts[0]]
                lw = self._lw(cls)
                kw = dict(color=self._col(cls), lw=lw * pt, solid_capstyle="round", solid_joinstyle="round")
                dash = self._dash(cls)
                if dash:
                    seq = [float(v) / lw for v in dash.split()]
                    kw["dashes"] = seq
                ax.plot([p[0] for p in pts], [p[1] for p in pts], **kw)
            elif k == "fill":
                ax.add_patch(Polygon(d, closed=True, color="k", lw=0))
            elif k == "hatch":
                rings, ang, step = d
                verts, codes = [], []
                for r in rings:
                    verts += list(r) + [r[0]]
                    codes += [Path.MOVETO] + [Path.LINETO] * (len(r) - 1) + [Path.CLOSEPOLY]
                clip = PathPatch(Path(verts, codes), facecolor="none", edgecolor="none")
                ax.add_patch(clip)
                xs = [p[0] for r in rings for p in r]
                ys = [p[1] for r in rings for p in r]
                cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
                R = math.hypot(max(xs) - min(xs), max(ys) - min(ys)) / 2 + step
                a = math.radians(ang)
                ux, uy = math.cos(a), -math.sin(a)
                nx, ny = -uy, ux
                k0 = int(R / step) + 1
                for i in range(-k0, k0 + 1):
                    ox, oy = cx + nx * i * step, cy + ny * i * step
                    ln, = ax.plot([ox - ux * R, ox + ux * R], [oy - uy * R, oy + uy * R], color="k", lw=S.thin * pt)
                    ln.set_clip_path(clip)
            elif k == "text":
                p, s, h, ang, anchor, valign, bold = d
                fs = h / S.cap_ratio * pt
                ha = {"start": "left", "middle": "center", "end": "right"}[anchor]
                va = "baseline" if valign == "base" else "center"
                ax.text(p[0], p[1], s, fontsize=fs, rotation=ang, ha=ha, va=va, family=S.font,
                        fontweight="bold" if bold else "normal", rotation_mode="anchor")
        fig.savefig(path, dpi=dpi, facecolor="white")
        plt.close(fig)
