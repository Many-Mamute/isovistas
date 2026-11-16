"""Image side: ink extraction, isometric grid detection, labelled node overlays, perspective
rectification of photos, and numeric fit of a model against a picture (no LLM vision needed)."""
import json
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy import ndimage as ndi


# ----------------------------------------------------------------- basics
def load_gray(path):
    im = Image.open(path).convert("L")
    return np.asarray(im, dtype=np.float32)


def ink_mask(g, win=41, rel=0.16, floor=20.0):
    """Dark strokes on a light, possibly unevenly lit background (screenshots, scans, photos)."""
    bg = ndi.uniform_filter(ndi.maximum_filter(g, size=5), size=win)
    return (bg - g) > np.maximum(floor, rel * bg)


def rectify(path, quad, size_mm, out, px_per_mm=6.0):
    """Perspective-correct a photo. quad: 4 image points (TL, TR, BR, BL) of a rectangle of
    size_mm=(w,h) lying in the drawing plane (page corners, frame, grid square...)."""
    w, h = size_mm
    W, H = int(w * px_per_mm), int(h * px_per_mm)
    dst = [(0, 0), (W, 0), (W, H), (0, H)]
    A, B = [], []
    for (x, y), (u, v) in zip(dst, quad):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        B += [u, v]
    coeffs = np.linalg.solve(np.array(A, float), np.array(B, float))
    im = Image.open(path).convert("RGB")
    im.transform((W, H), Image.Transform.PERSPECTIVE, tuple(coeffs), Image.Resampling.BICUBIC).save(out)
    return dict(out=out, size_px=(W, H), px_per_mm=px_per_mm)


# ----------------------------------------------------------------- isometric grid
def _family(ys, xs, ang_deg, spmin=12, spmax=200):
    """Best periodic family of parallel lines at angle ang (degrees from +x, image y down)."""
    a = math.radians(ang_deg)
    # line direction (cos a, sin a); coordinate across lines: n = (-sin a, cos a)
    c = ys * math.cos(a) - xs * math.sin(a)
    lo = math.floor(c.min())
    h = np.bincount((c - lo).astype(np.int64)).astype(np.float64)
    if h.size < 3 * spmin:
        return None
    h = h - ndi.uniform_filter1d(h, size=spmax)
    f = np.abs(np.fft.rfft(h, n=4 * h.size))
    freqs = np.fft.rfftfreq(4 * h.size)
    ok = (freqs > 1.0 / spmax) & (freqs < 1.0 / spmin)
    if not ok.any():
        return None
    i = np.argmax(np.where(ok, f, 0))
    # prefer the fundamental: a harmonic peak has a strong partner at half the frequency
    j = int(round(i / 2))
    if freqs[j] > 1.0 / spmax and f[j] > 0.35 * f[i]:
        i = j - 2 + int(np.argmax(f[j - 2:j + 3]))
    sp = 1.0 / freqs[i]
    score = f[i] / (np.median(f[ok]) + 1e-9)
    # phase: offset of the lines
    k = np.arange(h.size)
    ph = np.angle(np.sum(h * np.exp(-2j * math.pi * k / sp)))
    off = lo + (-ph / (2 * math.pi)) * sp
    return dict(ang=ang_deg, sp=sp, off=off % sp, score=float(score))


def detect_grid(path, angles=(30.0, -30.0, 90.0)):
    """Detect an isometric (or square) grid. Returns families {ang, sp, off}. Lines satisfy
    y cos(a) - x sin(a) = off + k sp."""
    g = load_gray(path)
    m = ink_mask(g, rel=0.08, floor=10)
    ys, xs = np.nonzero(m)
    if len(xs) > 400000:
        sel = np.random.default_rng(0).choice(len(xs), 400000, replace=False)
        ys, xs = ys[sel], xs[sel]
    ys, xs = ys.astype(np.float64), xs.astype(np.float64)
    fams = []
    for a0 in angles:
        best = None
        for da in np.arange(-3, 3.01, 0.25):
            r = _family(ys, xs, a0 + da)
            if r and (best is None or r["score"] > best["score"]):
                best = r
        if best:
            for da in np.arange(-0.25, 0.26, 0.05):
                r = _family(ys, xs, best["ang"] + da)
                if r and r["score"] > best["score"]:
                    best = r
            fams.append(best)
    return dict(families=fams, size=list(g.shape[::-1]))


def node_px(grid, m, n):
    """Pixel of lattice node (m, n) = intersection of family0 line m and family1 line n."""
    f0, f1 = grid["families"][0], grid["families"][1]
    A = []
    B = []
    for f, k in ((f0, m), (f1, n)):
        a = math.radians(f["ang"])
        A.append([-math.sin(a), math.cos(a)])
        B.append(f["off"] + k * f["sp"])
    x, y = np.linalg.solve(np.array(A), np.array(B))
    return float(x), float(y)


def px_node(grid, x, y):
    f0, f1 = grid["families"][0], grid["families"][1]
    out = []
    for f in (f0, f1):
        a = math.radians(f["ang"])
        out.append((y * math.cos(a) - x * math.sin(a) - f["off"]) / f["sp"])
    return out


def grid_overlay(path, grid, out, crop=None, step=1.0, scale=3):
    """Crop of the image (enlarged) with labelled lattice nodes (m,n) - the one visual aid needed
    to read coordinates on the grid."""
    im = Image.open(path).convert("RGB")
    W, H = im.size
    x0, y0, x1, y1 = crop or (0, 0, W, H)
    c = im.crop((x0, y0, x1, y1)).resize(((x1 - x0) * scale, (y1 - y0) * scale), Image.Resampling.LANCZOS)
    dr = ImageDraw.Draw(c)
    try:
        f = ImageFont.truetype("DejaVuSans.ttf", 14)
    except Exception:
        f = ImageFont.load_default()
    corners = [px_node(grid, x, y) for x in (x0, x1) for y in (y0, y1)]
    m0, m1 = math.floor(min(q[0] for q in corners)), math.ceil(max(q[0] for q in corners))
    n0, n1 = math.floor(min(q[1] for q in corners)), math.ceil(max(q[1] for q in corners))
    k = int(round(1 / step))
    for mi in range(m0 * k, m1 * k + 1):
        for ni in range(n0 * k, n1 * k + 1):
            m, n = mi / k, ni / k
            x, y = node_px(grid, m, n)
            if x0 <= x <= x1 and y0 <= y <= y1:
                X, Y = (x - x0) * scale, (y - y0) * scale
                whole = mi % k == 0 and ni % k == 0
                r = 3 if whole else 2
                dr.ellipse((X - r, Y - r, X + r, Y + r), fill=(230, 0, 0) if whole else (0, 150, 0))
                if whole:
                    dr.text((X + 4, Y + 2), f"{m:g},{n:g}", fill=(0, 0, 230), font=f)
    c.save(out)
    return out


# ----------------------------------------------------------------- numeric fit
def solve_affine(pts3, px):
    """Parallel projection (any axonometric or oblique view): px = A p + b, least squares."""
    P = np.array([[*p, 1.0] for p in pts3])
    U = np.array(px, float)
    sol, res, rk, _ = np.linalg.lstsq(P, U, rcond=None)
    A, b = sol[:3].T, sol[3]
    err = np.sqrt(((P @ sol - U) ** 2).sum(1))
    return A, b, err


def _sample(pls, step=0.7):
    out = []
    for pl in pls:
        for a, b in zip(pl, pl[1:]):
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            n = max(1, int(L / step))
            for i in range(n):
                t = i / n
                out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return np.array(out) if out else np.zeros((0, 2))


def fit(model, img_path, corr, grid=None, overlay=None, tol_px=2.5):
    """Compare the model's visible edges with the picture. corr: [[x,y,z,u,v], ...] (mm, pixels),
    >= 4 points not all coplanar. Returns precision (model edges found in the image), recall
    (image strokes explained by the model) and the worst regions."""
    from build123d import Vector
    from .geom import hlr, basis
    corr = [c for c in corr]
    k = model.k
    pts3 = [[c[0] * k, c[1] * k, c[2] * k] for c in corr]
    px = [[c[3], c[4]] for c in corr]
    A, b, err = solve_affine(pts3, px)
    kv = np.cross(A[0], A[1])
    kv = kv / np.linalg.norm(kv)
    g = load_gray(img_path)
    ink = ink_mask(g)
    gridmask = np.zeros_like(ink)
    if grid:
        H, W = ink.shape
        yy, xx = np.mgrid[0:H, 0:W]
        for f in grid["families"]:
            a = math.radians(f["ang"])
            c = yy * math.cos(a) - xx * math.sin(a) - f["off"]
            d = np.abs(((c + f["sp"] / 2) % f["sp"]) - f["sp"] / 2)
            gridmask |= d < 1.6
    strokes = ink & ~gridmask
    thick = ndi.binary_opening(ink, structure=np.ones((3, 3), bool))
    if thick.sum() > 0.25 * strokes.sum():
        strokes = strokes & ndi.binary_dilation(thick, iterations=1)   # drop thin annotation strokes
    near_ink = ndi.binary_dilation(ink, iterations=int(math.ceil(tol_px)))
    best = None
    for sgn in (1, -1):
        vd = Vector(*(kv * sgn))
        up = (0, 0, 1) if abs(vd.Z) < 0.95 else (0, 1, 0)
        vdv, R, U = basis(vd, up)
        vis, hid = hlr(model.solid, vdv, U)
        M = A @ np.array([[R.X, U.X], [R.Y, U.Y], [R.Z, U.Z]])
        pls = [[tuple(M @ np.array(q) + b) for q in pl] for pl in vis]
        S = _sample(pls)
        if len(S) == 0:
            continue
        H, W = ink.shape
        inb = (S[:, 0] >= 0) & (S[:, 0] < W) & (S[:, 1] >= 0) & (S[:, 1] < H)
        Si = S[inb].astype(int)
        hit = near_ink[Si[:, 1], Si[:, 0]]
        prec = float(hit.mean()) if len(hit) else 0.0
        if best is None or prec > best["precision"]:
            best = dict(precision=prec, sgn=sgn, pls=pls, S=S, inb=inb, hit=hit, M=M)
    # recall over strokes inside the model's footprint
    H, W = ink.shape
    edge = np.zeros_like(ink)
    Si = best["S"][best["inb"]].astype(int)
    edge[Si[:, 1], Si[:, 0]] = True
    near_model = ndi.binary_dilation(edge, iterations=4)
    footprint = ndi.binary_dilation(edge, iterations=25)
    cand = strokes & footprint
    covered = cand & near_model
    recall = float(covered.sum() / max(1, cand.sum()))
    miss = cand & ~ndi.binary_dilation(edge, iterations=6)
    lab, n = ndi.label(ndi.binary_dilation(miss, iterations=2))
    regions = []
    for i, sl in enumerate(ndi.find_objects(lab)):
        if sl is None:
            continue
        area = int((lab[sl] == i + 1).sum())
        if area < 60:
            continue
        x0, x1, y0, y1 = sl[1].start, sl[1].stop, sl[0].start, sl[0].stop
        r = dict(kind="tinta sem modelo", px=[x0, y0, x1, y1], area=area)
        if grid:
            r["node"] = [round(v, 1) for v in px_node(grid, (x0 + x1) / 2, (y0 + y1) / 2)]
        regions.append(r)
    # model edges without ink
    off = best["S"][best["inb"]][~best["hit"]]
    if len(off):
        lab2, n2 = ndi.label(ndi.binary_dilation(_raster(off, ink.shape), iterations=3))
        for i, sl in enumerate(ndi.find_objects(lab2)):
            if sl is None:
                continue
            area = int((lab2[sl] == i + 1).sum())
            if area < 80:
                continue
            x0, x1, y0, y1 = sl[1].start, sl[1].stop, sl[0].start, sl[0].stop
            r = dict(kind="aresta do modelo sem tinta", px=[x0, y0, x1, y1], area=area)
            if grid:
                r["node"] = [round(v, 1) for v in px_node(grid, (x0 + x1) / 2, (y0 + y1) / 2)]
            regions.append(r)
    regions.sort(key=lambda r: -r["area"])
    res = dict(precision=round(best["precision"], 3), recall=round(recall, 3),
               corr_err_px=[round(float(e), 2) for e in err], worst=regions[:6],
               view_dir=[round(float(v), 4) for v in kv * best["sgn"]])
    res["ok"] = res["precision"] >= 0.95 and res["recall"] >= 0.90 and max(res["corr_err_px"]) < 6
    if overlay:
        im = Image.open(img_path).convert("RGB")
        dr = ImageDraw.Draw(im)
        for pl in best["pls"]:
            dr.line([tuple(map(float, q)) for q in pl], fill=(230, 0, 0), width=2)
        for r in regions[:6]:
            dr.rectangle(r["px"], outline=(0, 90, 255), width=2)
        if isinstance(overlay, (list, tuple)):
            path, crop = overlay
            im = im.crop(crop)
        else:
            path = overlay
        im.save(path)
        res["overlay"] = path
    return res


def _raster(pts, shape):
    m = np.zeros(shape, bool)
    p = pts.astype(int)
    m[p[:, 1], p[:, 0]] = True
    return m


def fit_views(model, img_path, views, overlay=None, tol_px=2.5):
    """Fit against a multi-view drawing. views: [{"dir": "front"|[x,y,z], "pts": [[x,y,z,u,v],...]}]
    (>= 3 correspondences per view; a 2D affine maps view coordinates to pixels)."""
    from build123d import Vector
    from .geom import hlr, basis
    from .views import STD
    g = load_gray(img_path)
    ink = ink_mask(g)
    near_ink = ndi.binary_dilation(ink, iterations=int(math.ceil(tol_px)))
    H, W = ink.shape
    out = []
    edge_all = np.zeros_like(ink)
    draw = []
    k = model.k
    for v in views:
        d = v["dir"]
        vd, up = (STD[d] if isinstance(d, str) else (d, v.get("up", (0, 0, 1))))
        vdv, R, U = basis(vd, up)
        P = np.array([[c[0] * k * R.X + c[1] * k * R.Y + c[2] * k * R.Z,
                       c[0] * k * U.X + c[1] * k * U.Y + c[2] * k * U.Z, 1.0] for c in v["pts"]])
        Px = np.array([[c[3], c[4]] for c in v["pts"]], float)
        sol, *_ = np.linalg.lstsq(P, Px, rcond=None)
        err = np.sqrt(((P @ sol - Px) ** 2).sum(1))
        vis, hid = hlr(model.solid, vdv, U)
        if v.get("cut"):
            pass
        pls = [[tuple(np.array([q[0], q[1], 1.0]) @ sol) for q in pl] for pl in vis]
        S = _sample(pls)
        inb = (S[:, 0] >= 0) & (S[:, 0] < W) & (S[:, 1] >= 0) & (S[:, 1] < H)
        Si = S[inb].astype(int)
        hit = near_ink[Si[:, 1], Si[:, 0]]
        edge = np.zeros_like(ink)
        edge[Si[:, 1], Si[:, 0]] = True
        edge_all |= edge
        fp = np.zeros_like(ink)
        x0, y0 = Si.min(0)
        x1, y1 = Si.max(0)
        fp[max(0, y0 - 3):y1 + 4, max(0, x0 - 3):x1 + 4] = True
        cand = ink & fp
        rec = float((cand & ndi.binary_dilation(edge, iterations=4)).sum() / max(1, cand.sum()))
        out.append(dict(dir=d, precision=round(float(hit.mean()), 3), recall_in_box=round(rec, 3),
                        corr_err_px=[round(float(e), 2) for e in err]))
        draw.append(pls)
    if overlay:
        im = Image.open(img_path).convert("RGB")
        dr = ImageDraw.Draw(im)
        for pls in draw:
            for pl in pls:
                dr.line([tuple(map(float, q)) for q in pl], fill=(230, 0, 0), width=2)
        im.save(overlay)
    ok = all(o["precision"] >= 0.93 for o in out)
    return dict(views=out, ok=ok, overlay=overlay)
