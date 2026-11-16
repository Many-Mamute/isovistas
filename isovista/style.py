"""Drawing style constants (ISO 128-2, ISO 129-1, ISO 3098, ISO 5457, ISO 7200),
as taught in FEUP's 'Desenho Técnico' course (J. S. Almacinha).

All sizes in mm on paper. One line group is used per drawing (thick:thin = 2:1).
"""
from dataclasses import dataclass, field


@dataclass
class Style:
    thick: float = 0.7          # 01.2 visible edges/outlines (A3 preferred group 0.7/0.35)
    thin: float = 0.35          # 01.1 dims, extension, hatch, centre; 02.1 hidden
    h: float = 3.5              # lettering type B vertical, h = 10 d(thin)
    # ISO 128-2 Annex A element lengths are multiples of d (thin line width)
    dash: float = 12.0          # x d : dash of hidden line (02)
    gap: float = 3.0            # x d : gap
    long_dash: float = 24.0     # x d : long dash of chain line (04)
    dot: float = 0.5            # x d : "dot" of chain line
    arrow_len_k: float = 1.0    # arrow length = h  (closed, filled, 30 deg)
    ext_over: float = 8.0       # extension line passes dim line by ~8 d
    dim_first: float = 10.0     # first dim line distance from outline (mm)
    dim_step: float = 7.0       # distance between parallel dim lines (>= 6 mm)
    hatch_step: float = 2.5     # hatch spacing (45 deg)
    centre_over: float = 3.0    # centre lines pass outlines by ~3 mm
    font: str = "DejaVu Sans"
    font_svg: str = "osifont, 'ISOCPEUR', 'DejaVu Sans', Arial, sans-serif"
    cap_ratio: float = 0.73     # cap height / em for DejaVu Sans
    char_w: float = 0.62        # average glyph advance / em

    @property
    def h_label(self):          # view / section letters: h' = sqrt(2) h
        return round(self.h * 1.4142, 1)

    @property
    def fs(self):               # SVG font-size (em) giving cap height h
        return self.h / self.cap_ratio

    def text_w(self, s, h=None):
        h = h or self.h
        n = sum(0.55 if c in "1.,()" else 1.0 for c in s)
        return n * self.char_w * h / self.cap_ratio

    @property
    def arrow_len(self):
        return self.h * self.arrow_len_k


SHEETS = {  # ISO 5457 trimmed sizes (landscape for A0-A3; A4 portrait)
    "A4": (210, 297), "A4L": (297, 210), "A3": (420, 297), "A2": (594, 420),
    "A1": (841, 594), "A0": (1189, 841),
}
SCALES = [(1, 1), (1, 2), (2, 1), (1, 5), (5, 1), (1, 10), (10, 1), (1, 20), (20, 1)]
