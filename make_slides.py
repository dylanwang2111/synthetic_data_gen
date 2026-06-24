"""
Generate slides.pptx — a focused presentation of the synthetic-data pipeline.

Run:  python make_slides.py
Concentrated on the key delivery points: pipeline, methods, the fidelity and
diagnostic metrics, and the headline SDV-vs-SmartNoise comparison (mean ± SD).
"""

from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from PIL import Image

REPORTS = Path("reports")

# ── palette ───────────────────────────────────────────────────────────────
INK    = RGBColor(0x1F, 0x2A, 0x37)   # near-black text
MUTED  = RGBColor(0x5B, 0x66, 0x70)
ACCENT = RGBColor(0x4E, 0x79, 0xA7)   # M1 blue / SDV
BG     = RGBColor(0xFF, 0xFF, 0xFF)
PANEL  = RGBColor(0xF3, 0xF5, 0xF7)
GOOD   = RGBColor(0x2E, 0x7D, 0x32)
WARN   = RGBColor(0xC6, 0x28, 0x28)
DPCLR  = RGBColor(0xB0, 0x7A, 0xA1)   # SmartNoise / DP purple
METHOD = {"M1": RGBColor(0x4E,0x79,0xA7), "M2": RGBColor(0xF2,0x8E,0x2B),
          "M3": RGBColor(0x59,0xA1,0x4F), "M4": RGBColor(0xE1,0x57,0x59),
          "M5": RGBColor(0xB0,0x7A,0xA1)}

prs = Presentation()
prs.slide_width  = Inches(13.333)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]
SW, SH = prs.slide_width, prs.slide_height


def slide():
    s = prs.slides.add_slide(BLANK)
    bg = s.background.fill
    bg.solid(); bg.fore_color.rgb = BG
    return s


def box(s, x, y, w, h):
    return s.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h)).text_frame


def _set(p, text, size, color=INK, bold=False, align=PP_ALIGN.LEFT, italic=False):
    p.alignment = align
    r = p.add_run(); r.text = text
    r.font.size = Pt(size); r.font.bold = bold; r.font.italic = italic
    r.font.color.rgb = color; r.font.name = "Calibri"


def accent_bar(s, color=ACCENT):
    bar = s.shapes.add_shape(1, Inches(0), Inches(0), Inches(0.22), SH)
    bar.fill.solid(); bar.fill.fore_color.rgb = color; bar.line.fill.background()


def header(s, title, kicker=None, color=ACCENT):
    accent_bar(s, color)
    tf = box(s, 0.6, 0.42, 12.2, 1.1)
    if kicker:
        _set(tf.paragraphs[0], kicker.upper(), 13, color, bold=True)
        p = tf.add_paragraph(); _set(p, title, 32, INK, bold=True)
    else:
        _set(tf.paragraphs[0], title, 32, INK, bold=True)


def bullets(s, items, x=0.85, y=1.9, w=11.6, h=5.0, size=18, gap=10):
    h = min(h, 7.2 - y)   # never run past the slide bottom
    tf = box(s, x, y, w, h); tf.word_wrap = True
    for i, it in enumerate(items):
        lvl = 0
        if isinstance(it, tuple):
            it, lvl = it
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        bullet = "•  " if lvl == 0 else "–  "
        _set(p, bullet + it, size - lvl*2, INK if lvl == 0 else MUTED, bold=(lvl == 0 and it.endswith(":")))
        p.space_after = Pt(gap)
        p.level = lvl


def fit_image(s, path, x, y, w, h):
    """Place an image fit (contain) within the box (x,y,w,h) in inches, centered."""
    iw, ih = Image.open(path).size
    box_ar = w / h; img_ar = iw / ih
    if img_ar > box_ar:
        dw = w; dh = w / img_ar
    else:
        dh = h; dw = h * img_ar
    px = x + (w - dw) / 2; py = y + (h - dh) / 2
    s.shapes.add_picture(str(path), Inches(px), Inches(py), Inches(dw), Inches(dh))


def caption(s, text, y=6.9):
    tf = box(s, 0.85, y, 11.6, 0.5)
    _set(tf.paragraphs[0], text, 13, MUTED, italic=True)


def table(s, rows, x, y, w, h, header_fill=ACCENT, font=13, col_widths=None,
          cell_colors=None):
    nr, nc = len(rows), len(rows[0])
    gt = s.shapes.add_table(nr, nc, Inches(x), Inches(y), Inches(w), Inches(h)).table
    if col_widths:
        for j, cw in enumerate(col_widths):
            gt.columns[j].width = Inches(cw)
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            c = gt.cell(i, j)
            c.margin_top = Pt(2); c.margin_bottom = Pt(2)
            c.margin_left = Pt(6); c.margin_right = Pt(6)
            c.vertical_anchor = MSO_ANCHOR.MIDDLE
            p = c.text_frame.paragraphs[0]
            _set(p, str(val), font, RGBColor(0xFF,0xFF,0xFF) if i == 0 else INK,
                 bold=(i == 0 or j == 0), align=PP_ALIGN.LEFT if j == 0 else PP_ALIGN.CENTER)
            if i == 0:
                c.fill.solid(); c.fill.fore_color.rgb = header_fill
            else:
                c.fill.solid(); c.fill.fore_color.rgb = BG if i % 2 else PANEL
            if cell_colors and (i, j) in cell_colors:
                c.text_frame.paragraphs[0].runs[0].font.color.rgb = cell_colors[(i, j)]
                c.text_frame.paragraphs[0].runs[0].font.bold = True
    return gt


# ════════════════════════════════════════════════════════════════════════════
# 1 — Title
# ════════════════════════════════════════════════════════════════════════════
s = slide()
panel = s.shapes.add_shape(1, Inches(0), Inches(0), SW, SH)
panel.fill.solid(); panel.fill.fore_color.rgb = INK; panel.line.fill.background()
tf = box(s, 0.9, 2.3, 11.5, 2.8)
_set(tf.paragraphs[0], "SYNTHETIC BANKING DATA", 15, RGBColor(0x9F,0xC0,0xE0), bold=True)
p = tf.add_paragraph(); _set(p, "SDV vs Differential Privacy", 42, BG, bold=True)
p = tf.add_paragraph()
_set(p, "Which synthesizer for customer + transaction data — and why", 20,
     RGBColor(0xC9,0xD3,0xDD))
tf = box(s, 0.9, 6.4, 11.5, 0.6)
_set(tf.paragraphs[0], "Pipeline · 5 methods · fidelity / diagnostic / privacy · bootstrapped comparison", 14,
     RGBColor(0x8A,0x97,0xA3))

# ════════════════════════════════════════════════════════════════════════════
# 2 — Pipeline
# ════════════════════════════════════════════════════════════════════════════
s = slide(); header(s, "The pipeline", "How it works")

def stage(x, y, w, h, title, sub, color):
    sh = s.shapes.add_shape(5, Inches(x), Inches(y), Inches(w), Inches(h))
    sh.fill.solid(); sh.fill.fore_color.rgb = color; sh.line.color.rgb = color
    tf = sh.text_frame; tf.word_wrap = True
    _set(tf.paragraphs[0], title, 16, BG, bold=True, align=PP_ALIGN.CENTER)
    p = tf.add_paragraph(); _set(p, sub, 11, RGBColor(0xEE,0xF2,0xF6), align=PP_ALIGN.CENTER)

def arrow(x, y):
    a = s.shapes.add_shape(13, Inches(x), Inches(y), Inches(0.5), Inches(0.5))
    a.fill.solid(); a.fill.fore_color.rgb = MUTED; a.line.fill.background()

yy, hh = 2.55, 1.7
stage(0.85, yy, 2.6, hh, "1 · Seed data", "2,000 customers\n~24k transactions\nrule-driven", INK)
arrow(3.55, yy+0.6)
stage(4.15, yy, 3.0, hh, "2 · Synthesize", "5 models\nSDV (4) + DP (1)\n+ constraints", ACCENT)
arrow(7.25, yy+0.6)
stage(7.85, yy, 2.7, hh, "3 · Evaluate", "fidelity · diagnostic\nprivacy\n(bootstrapped)", METHOD["M3"])
arrow(10.65, yy+0.6)
stage(11.25, yy, 1.75, hh, "4 · Use", "LLM product\nrecommender", METHOD["M4"])
bullets(s, [
    "One rule-driven ground truth (income↔occupation, credit eligibility, age→channel) feeds every method.",
    "Constraints (SDV CAG) attach before fitting → valid output at generation, not patched afterward.",
    "Same seed + metadata for all 5 → only the synthesizer changes, so the comparison is clean.",
], y=4.65, size=16, gap=10)

# ════════════════════════════════════════════════════════════════════════════
# 3 — The five methods
# ════════════════════════════════════════════════════════════════════════════
s = slide(); header(s, "Five synthesis methods", "What we compare")
rows = [
    ["", "Synthesizer", "Paradigm", "What it does"],
    ["M1", "HMA + Gaussian Copula", "SDV", "Models customer→txn FK jointly (multi-table)"],
    ["M2", "CTGAN (per table)", "SDV", "GAN — sharp marginals & transaction timing"],
    ["M3", "CTGAN + PAR", "SDV", "Adds a sequence model for transactions"],
    ["M4", "TVAE (per table)", "SDV", "Variational autoencoder — smooth, correlated"],
    ["M5", "SmartNoise MST", "OpenDP (DP)", "Noisy marginals → (ε≈6, δ) differential privacy"],
]
cc = {(i+1, 0): METHOD[m] for i, m in enumerate(["M1","M2","M3","M4","M5"])}
cc[(5,2)] = DPCLR
table(s, rows, 0.85, 2.0, 11.6, 3.2, font=14,
      col_widths=[0.8, 3.7, 2.1, 5.0], cell_colors=cc)
bullets(s, [
    "M1–M4 (SDV) optimise statistical fidelity; M5 (SmartNoise) trades fidelity for a formal privacy guarantee.",
    "M1 is the only one that models the customer→transaction relationship directly (native referential integrity).",
], y=5.45, size=15, gap=8)

# ════════════════════════════════════════════════════════════════════════════
# 4 — Fidelity metrics
# ════════════════════════════════════════════════════════════════════════════
s = slide(); header(s, "Fidelity metrics — does it look like the real data?", "Metric 1")
fit_image(s, REPORTS/"quality_report.png", 0.55, 1.7, 8.5, 4.6)
tf = box(s, 9.25, 1.85, 3.75, 4.8); tf.word_wrap = True
_set(tf.paragraphs[0], "Two components", 15, ACCENT, bold=True)
for t in ["Column Shapes — each column's distribution (marginals). Scored by KSComplement (numeric) / TVComplement (categorical): 1.0 = identical.",
          "Column Pair Trends — relationships between columns (correlation / contingency similarity).",
          "Overall Quality = average of the two — the headline fidelity score."]:
    p = tf.add_paragraph(); _set(p, "• " + t, 12.5, INK); p.space_after = Pt(9)
caption(s, "SDMetrics QualityReport — overall fidelity decomposed into Column Shapes and Column Pair Trends, per method.")

# ════════════════════════════════════════════════════════════════════════════
# 5 — Diagnostic metric
# ════════════════════════════════════════════════════════════════════════════
s = slide(); header(s, "Diagnostic metric — is it structurally valid?", "Metric 2")
bullets(s, [
    "Diagnostic ≠ fidelity. It does not ask 'is it realistic?' — it asks 'is it well-formed?'",
    "Data validity — values stay within valid ranges and known categories (credit∈[300,850], real product ids).",
    "Data structure — primary keys unique, no missing required fields.",
    "Referential integrity — every transaction references a real customer AND a real product (no orphan foreign keys).",
], y=1.95, size=17, gap=11)
rows = [
    ["Diagnostic / referential integrity", "M1", "M2", "M3", "M4", "M5"],
    ["Score (1.0 = perfect)", "1.00", "1.00", "0.74", "1.00", "1.00"],
]
cc = {(1,3): WARN, (1,1): GOOD, (1,2): GOOD, (1,4): GOOD, (1,5): GOOD}
table(s, rows, 0.85, 5.35, 11.6, 1.0, font=14,
      col_widths=[5.1, 1.3, 1.3, 1.3, 1.3, 1.3], cell_colors=cc)
caption(s, "Only M3 (PAR) breaks integrity — it merges product_id/category and rejects the FixedCombinations constraint.", y=6.55)

# ════════════════════════════════════════════════════════════════════════════
# 6 — SDV vs SmartNoise: the comparison
# ════════════════════════════════════════════════════════════════════════════
s = slide(); header(s, "SDV vs SmartNoise — the comparison", "The key result")
fit_image(s, REPORTS/"sdv_vs_smartnoise.png", 0.55, 1.65, 9.1, 5.0)
tf = box(s, 9.8, 1.8, 3.3, 4.9); tf.word_wrap = True
_set(tf.paragraphs[0], "Mean ± SD (bootstrap)", 14, ACCENT, bold=True)
for t in ["Fidelity: means are close — SDV wins shapes, SmartNoise wins pair trends.",
          "Variance is the story: SmartNoise's DP noise gives ~6× the quality SD (±0.037 vs ±0.006).",
          "Diagnostic / referential integrity: both perfect (1.00).",
          "Privacy (MIA AUC): both ≈ 0.50 — no measurable membership leakage either way.",
          "Only real difference: M5 adds a formal (ε≈6, δ)-DP guarantee."]:
    p = tf.add_paragraph(); _set(p, "• " + t, 11.5, INK); p.space_after = Pt(8)
caption(s, "SDV = M1 (HMA-GC, recommended); SmartNoise = M5 (MST, DP). Error bars = ±1 SD over bootstrap resamples.")

# ════════════════════════════════════════════════════════════════════════════
# 7 — Mean ± variance table
# ════════════════════════════════════════════════════════════════════════════
s = slide(); header(s, "Per-metric: mean ± variance", "The numbers")
rows = [
    ["Metric (category)", "SDV  (M1)", "SmartNoise  (M5)", "Read"],
    ["Quality — fidelity", "0.88 ± 0.006", "0.88 ± 0.037", "tie mean · SDV 6× stabler"],
    ["Cust. column shapes — fidelity", "0.94 ± 0.003", "0.92 ± 0.003", "SDV"],
    ["Cust. pair trends — fidelity", "0.73 ± 0.009", "0.83 ± 0.014", "SmartNoise"],
    ["Txn. column shapes — fidelity", "0.86 ± 0.002", "0.85 ± 0.003", "SDV"],
    ["Diagnostic — ref. integrity", "1.00 ± 0.001", "1.00 ± 0.000", "tie (perfect)"],
    ["Privacy — MIA AUC (↓)", "0.50 ± 0.009", "0.49 ± 0.009", "tie (no leakage)"],
    ["Formal DP guarantee", "✗", "✓  ε ≈ 6", "SmartNoise"],
]
cc = {(2,3): ACCENT, (4,3): ACCENT, (3,3): DPCLR, (8,2): DPCLR,
      (1,3): MUTED, (5,3): MUTED, (6,3): MUTED, (7,3): MUTED}
table(s, rows, 0.7, 2.0, 12.0, 4.0, font=13.5,
      col_widths=[4.3, 2.5, 2.7, 2.5], cell_colors=cc)
caption(s, "Mean ± SD over the bootstrap (fidelity/diagnostic B=200; privacy B=300). Lower MIA AUC = more private; 0.5 = none.")

# ════════════════════════════════════════════════════════════════════════════
# 8 — Conclusion
# ════════════════════════════════════════════════════════════════════════════
s = slide(); header(s, "Verdict: use SDV for this data", "Conclusion")
bullets(s, [
    "Equal-or-better mean fidelity — SDV (M1) wins column shapes & txn shapes, ties on quality, loses only pair trends.",
    "Far more stable — DP noise gives SmartNoise ~6× the quality variance; SDV is reproducible run-to-run.",
    "Native referential integrity — HMA models the customer→transaction FK, so every row is structurally valid (1.00).",
    "Keeps structure DP drops — cross-table (income→product) and transaction timing survive; M5's sequence signal collapses.",
    "Privacy is empirically equal here — at n=2,000 no method leaks membership (MIA AUC ≈ 0.50, ε = 0).",
    "So the DP guarantee buys nothing measurable for this data type/scale — and costs fidelity + stability.",
], y=1.85, size=16.5, gap=10)
tf = box(s, 0.85, 6.35, 11.8, 0.7); tf.word_wrap = True
_set(tf.paragraphs[0], "Choose SmartNoise (DP) only when: data is small / high-dimensional, records are outlier-heavy, "
     "or a worst-case ε guarantee is a hard requirement.", 13.5, DPCLR, italic=True)

out = Path("slides.pptx")
prs.save(out)
print(f"wrote {out}  ({len(prs.slides.__iter__.__self__._sldIdLst)} slides)")
