"""isovista command line.  Run `isovista -h`."""
import argparse
import json
import sys
import time


def _p(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=1))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="isovista", description="Desenho técnico: isométrico <-> vistas (normas ISO).")
    sp = ap.add_subparsers(dest="cmd", required=True)

    a = sp.add_parser("check", help="constrói o sólido da especificação e resume-o")
    a.add_argument("spec")

    a = sp.add_parser("draw", help="desenho ortográfico cotado (SVG+PNG+PDF+JSON)")
    a.add_argument("spec")
    a.add_argument("-o", "--out", default="desenho")
    a.add_argument("--sheet", default=None, help="A4 | A4L | A3 | A2 ...")
    a.add_argument("--scale", default=None, help="1:1, 1:2, 2:1 ...")
    a.add_argument("--no-pdf", action="store_true")

    a = sp.add_parser("iso", help="desenho isométrico sobre reticulado")
    a.add_argument("spec")
    a.add_argument("-o", "--out", default="isometrico")
    a.add_argument("--view", default="fr", help="fr | fl | br | bl | fr-low | fl-low")
    a.add_argument("--unit", type=float, default=10.0, help="mm por unidade do reticulado (0 = sem reticulado)")
    a.add_argument("--sheet", default="A4L")
    a.add_argument("--hidden", action="store_true")

    a = sp.add_parser("grid", help="deteta o reticulado isométrico e gera uma ampliação com nós rotulados")
    a.add_argument("image")
    a.add_argument("-o", "--out", default="nos.png")
    a.add_argument("--crop", default=None, help="x0,y0,x1,y1 em píxeis")
    a.add_argument("--step", type=float, default=1.0, help="1 = nós inteiros, 0.5 = meios")
    a.add_argument("--scale", type=int, default=3)

    a = sp.add_parser("rectify", help="corrige a perspetiva de uma fotografia")
    a.add_argument("image")
    a.add_argument("--quad", required=True, help="x1,y1,...,x4,y4 (TL,TR,BR,BL) de um retângulo conhecido")
    a.add_argument("--size", required=True, help="largura,altura do retângulo em mm")
    a.add_argument("-o", "--out", default="retificada.png")

    a = sp.add_parser("fit", help="compara o modelo com a figura isométrica/axonométrica original")
    a.add_argument("spec")
    a.add_argument("image")
    a.add_argument("--pts", required=True, help="JSON [[x,y,z,u,v],...] ou [[x,y,z,'m,n'],...] (com --grid)")
    a.add_argument("--grid", action="store_true", help="usar o reticulado detetado (permite pontos em nós m,n)")
    a.add_argument("--overlay", default=None)

    a = sp.add_parser("fitviews", help="compara o modelo com um desenho de vistas original")
    a.add_argument("spec")
    a.add_argument("image")
    a.add_argument("--views", required=True, help='JSON [{"dir":"front","pts":[[x,y,z,u,v],...]},...]')
    a.add_argument("--overlay", default=None)

    a = sp.add_parser("compare", help="verificação de ida-e-volta: compara duas leituras independentes")
    a.add_argument("a")
    a.add_argument("b")
    a.add_argument("--no-rotate", action="store_true")

    args = ap.parse_args(argv)
    t0 = time.time()
    if args.cmd in ("check", "draw", "iso", "fit", "fitviews", "compare"):
        from .spec import Model
    if args.cmd == "check":
        m = Model(args.spec)
        bb = m.bbox()
        _p(dict(ok=m.solid.is_valid, volume=round(m.solid.volume, 1),
                bbox=[round(c, 2) for c in bb], features=len(m.feats), s=round(time.time() - t0, 1)))
    elif args.cmd == "draw":
        from .drawing import make_drawing
        m = Model(args.spec)
        dr, rec = make_drawing(m, args.out, sheet=args.sheet, scale=args.scale, pdf=not args.no_pdf)
        _p(dict(files=[args.out + e for e in (".svg", ".png", ".pdf", ".info.json")], views=[v["label"] or v["id"] for v in rec["views"]],
                dims=len(rec["dims"]), lint=rec["lint"], s=round(time.time() - t0, 1)))
    elif args.cmd == "iso":
        from .iso import iso_drawing
        m = Model(args.spec)
        iso_drawing(m, args.out, view=args.view, unit=args.unit, sheet=args.sheet, hidden=args.hidden)
        _p(dict(files=[args.out + e for e in (".svg", ".png", ".pdf")], s=round(time.time() - t0, 1)))
    elif args.cmd == "grid":
        from .image import detect_grid, grid_overlay
        g = detect_grid(args.image)
        json.dump(g, open(args.image + ".grid.json", "w"), indent=1)
        crop = [int(v) for v in args.crop.split(",")] if args.crop else None
        grid_overlay(args.image, g, args.out, crop=crop, step=args.step, scale=args.scale)
        _p(dict(grid=g["families"], grid_file=args.image + ".grid.json", overlay=args.out))
    elif args.cmd == "rectify":
        from .image import rectify
        q = [float(v) for v in args.quad.split(",")]
        _p(rectify(args.image, list(zip(q[0::2], q[1::2])), [float(v) for v in args.size.split(",")], args.out))
    elif args.cmd == "fit":
        from .image import fit, detect_grid, node_px
        m = Model(args.spec)
        pts = json.loads(open(args.pts).read()) if not args.pts.strip().startswith("[") else json.loads(args.pts)
        g = detect_grid(args.image) if args.grid else None
        corr = []
        for p in pts:
            if isinstance(p[3], str):
                mm, nn = [float(v) for v in p[3].split(",")]
                corr.append([p[0], p[1], p[2], *node_px(g, mm, nn)])
            else:
                corr.append(p)
        r = fit(m, args.image, corr, grid=g, overlay=args.overlay)
        _p(r)
    elif args.cmd == "fitviews":
        from .image import fit_views
        m = Model(args.spec)
        v = json.loads(open(args.views).read()) if not args.views.strip().startswith("[") else json.loads(args.views)
        _p(fit_views(m, args.image, v, overlay=args.overlay))
    elif args.cmd == "compare":
        from .compare import compare
        r = compare(Model(args.a), Model(args.b), rotate=not args.no_rotate)
        _p(r)
        sys.exit(0 if r["ok"] else 1)


if __name__ == "__main__":
    main()
