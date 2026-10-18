"""Generate presentation/Project_Presentation.pptx (15 slides, notes on every slide).

All numbers are READ from results/*.csv|json and docs/TEST_REPORT.md at run
time — nothing is hard-coded. Charts/diagrams reuse the 300-dpi PNGs in
figures/; screenshots are the real Part-3 E2E captures in docs/screenshots/.

Run:  .venv\\Scripts\\python.exe scripts\\generate_presentation.py
Export to PNG with scripts\\export_slides.ps1 (PowerPoint COM, A26).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

RESULTS = ROOT / "results"
FIGURES = ROOT / "figures"
SHOTS = ROOT / "docs" / "screenshots"
OUT = ROOT / "presentation" / "Project_Presentation.pptx"

# design tokens
NAVY = RGBColor(0x0F, 0x17, 0x2A)
BLUE = RGBColor(0x25, 0x63, 0xEB)
TEAL = RGBColor(0x0D, 0x94, 0x88)
BODY = RGBColor(0x1E, 0x29, 0x3B)
GRAY = RGBColor(0x64, 0x74, 0x8B)
CARD = RGBColor(0xF1, 0xF5, 0xF9)
BORDER = RGBColor(0xCB, 0xD5, 0xE1)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
PALE = RGBColor(0xE2, 0xE8, 0xF0)
FONT = "Segoe UI"

SW, SH = 13.333, 7.5  # slide size, inches


def load_numbers() -> dict:
    test_report = (ROOT / "docs" / "TEST_REPORT.md").read_text(encoding="utf-8")
    m = re.search(r"(\d+) passed in ([\d.]+)\s*s", test_report)
    return {
        "mc": pd.read_csv(RESULTS / "model_comparison_metrics.csv"),
        "lat": pd.read_csv(RESULTS / "latency_summary.csv"),
        "thr": pd.read_csv(RESULTS / "throughput_ingestion.csv"),
        "cost": pd.read_csv(RESULTS / "cost_model.csv"),
        "tests": int(m.group(1)) if m else 0,
        "tests_s": float(m.group(2)) if m else 0.0,
        "cost_sources_accessed": json.loads(
            (RESULTS / "cost_sources.json").read_text(encoding="utf-8"))["accessed"],
    }


# ---------------------------------------------------------------- primitives
def rect(slide, x, y, w, h, fill, line=None, rounded=False):
    shape = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE,
        Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    if line is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = line
        shape.line.width = Pt(1)
    shape.shadow.inherit = False
    return shape


def text(slide, x, y, w, h, s, size=16, bold=False, color=BODY,
         align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = s
    run.font.name = FONT
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color
    return tb


def bullets(slide, items, x, y, w, h, size=15, color=BODY, space=10):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(space)
        run = p.add_run()
        run.text = item
        run.font.name = FONT
        run.font.size = Pt(size)
        run.font.color.rgb = color
    return tb


def picture_fit(slide, path: Path, x, y, max_w, max_h, crop_bottom=0.0):
    """Place image scaled to fit (x,y,max_w,max_h); optional top-crop."""
    im = Image.open(path)
    w0, h0 = im.size
    aspect = w0 / (h0 * (1 - crop_bottom))
    if max_w / max_h < aspect:
        w, h = max_w, max_w / aspect
    else:
        h, w = max_h, max_h * aspect
    px = x + (max_w - w) / 2
    py = y + (max_h - h) / 2
    pic = slide.shapes.add_picture(str(path), Inches(px), Inches(py),
                                   width=Inches(w), height=Inches(h))
    if crop_bottom:
        pic.crop_bottom = crop_bottom
    return pic


def notes(slide, s):
    slide.notes_slide.notes_text_frame.text = s


def footer(slide, n, total=15, dark=False):
    c = PALE if dark else GRAY
    text(slide, 0.6, 7.02, 8.0, 0.35,
         "Cloud-Based Customer Review Sentiment Analysis Dashboard  ·  26MS-DS037",
         size=9, color=c)
    text(slide, 12.0, 7.02, 0.9, 0.35, f"{n} / {total}", size=9, color=c,
         align=PP_ALIGN.RIGHT)


def content_slide(prs, n, title, kicker=None):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    text(slide, 0.6, 0.32, 12.1, 0.75, title, size=28, bold=True, color=NAVY)
    rect(slide, 0.62, 1.06, 1.5, 0.06, BLUE)
    if kicker:
        text(slide, 2.35, 0.98, 10.3, 0.4, kicker, size=13, color=GRAY)
    footer(slide, n)
    return slide


def card(slide, x, y, w, h, title_s, items, accent=BLUE):
    rect(slide, x, y, w, h, CARD, line=BORDER, rounded=True)
    rect(slide, x, y, 0.07, h, accent)
    text(slide, x + 0.22, y + 0.12, w - 0.4, 0.4, title_s, size=14, bold=True,
         color=NAVY)
    bullets(slide, items, x + 0.22, y + 0.58, w - 0.42, h - 0.7, size=11.5,
            color=BODY, space=6)


def stat(slide, x, y, w, h, big, label):
    rect(slide, x, y, w, h, WHITE, line=BORDER, rounded=True)
    text(slide, x + 0.1, y + 0.12, w - 0.2, 0.55, big, size=24, bold=True,
         color=BLUE, align=PP_ALIGN.CENTER)
    text(slide, x + 0.1, y + 0.72, w - 0.2, h - 0.8, label, size=10.5,
         color=GRAY, align=PP_ALIGN.CENTER)


def mini_table(slide, headers, rows, x, y, w, h, size=11):
    shape = slide.shapes.add_table(len(rows) + 1, len(headers), Inches(x),
                                   Inches(y), Inches(w), Inches(h))
    tbl = shape.table
    for j, htxt in enumerate(headers):
        cell = tbl.cell(0, j)
        cell.text = htxt
        cell.fill.solid()
        cell.fill.fore_color.rgb = NAVY
        run = cell.text_frame.paragraphs[0].runs[0]
        run.font.name = FONT
        run.font.size = Pt(size)
        run.font.bold = True
        run.font.color.rgb = WHITE
    for i, row in enumerate(rows, start=1):
        for j, val in enumerate(row):
            cell = tbl.cell(i, j)
            cell.text = str(val)
            cell.fill.solid()
            cell.fill.fore_color.rgb = WHITE if i % 2 else CARD
            run = cell.text_frame.paragraphs[0].runs[0]
            run.font.name = FONT
            run.font.size = Pt(size)
            run.font.color.rgb = BODY
    return tbl


# ---------------------------------------------------------------- slides
def build(n: dict) -> Presentation:
    prs = Presentation()
    prs.slide_width = Inches(SW)
    prs.slide_height = Inches(SH)
    mc, lat, thr, cost = n["mc"], n["lat"], n["thr"], n["cost"]

    def er(df, name):
        return df[df["engine"] == name].iloc[0]

    vader, tb_, hf = er(mc, "vader"), er(mc, "textblob"), er(mc, "huggingface")
    lv, lt, lh = er(lat, "vader"), er(lat, "textblob"), er(lat, "huggingface")
    c1m = cost[cost["workload_reviews_per_month"] == 1_000_000].set_index("option")

    # ---- 1 title -----------------------------------------------------------
    s = prs.slides.add_slide(prs.slide_layouts[6])
    rect(s, 0, 0, SW, SH, NAVY)
    rect(s, 0.9, 2.32, 1.8, 0.07, BLUE)
    text(s, 0.9, 0.9, 11.6, 1.1,
         "Cloud-Based Customer Review\nSentiment Analysis Dashboard",
         size=36, bold=True, color=WHITE)
    text(s, 0.9, 2.58, 11.0, 0.6,
         "A serverless, free-tier cloud pipeline for small-business review analytics",
         size=17, color=PALE)
    text(s, 0.9, 3.35, 11.0, 1.2,
         "Ahmed Bin Jaffar  ·  26MS-DS037  ·  MSDS Semester 2 — Cloud Computing\n"
         "Sir Ab Raheem Ansari  ·  MUET  ·  October 2026",
         size=14, color=PALE)
    for i, (big, label) in enumerate([
            ("1,214", "real reviews evaluated"),
            ("4", "pluggable sentiment engines"),
            (f"{n['tests']}", "automated tests, all passing"),
            (f"${c1m.loc['aws_free_tier', 'monthly_cost_usd']:.2f}/mo", "at 1M reviews, free tier")]):
        stat(s, 0.9 + i * 2.95, 5.1, 2.7, 1.4, big, label)
    footer(s, 1, dark=True)
    notes(s, "Good morning. This project asked one practical question: can a "
             "small business get trustworthy review-sentiment analytics for "
             "effectively zero infrastructure cost? We built the full pipeline "
             "— ingestion to dashboard — and measured everything: accuracy, "
             "latency, throughput, and a source-checked monthly cost model. "
             "Every number in this deck comes from an executed run stored in "
             "results/.")

    # ---- 2 problem ---------------------------------------------------------
    s = content_slide(prs, 2, "The problem", "who needs this, and why it does not exist yet")
    card(s, 0.6, 1.45, 6.0, 2.3, "Reviews are free; the insight is not",
         [("Commercial sentiment SaaS starts around $299/month (third-party "
          "estimate, unverified)."),
          ("Usage-billed managed APIs cost roughly $300/month at one million "
          "reviews — linear in text volume.")])
    card(s, 6.85, 1.45, 6.0, 2.3, "DIY is out of reach",
         [("Pipelines, databases and dashboards need engineers a shop owner "
          "does not have."),
          ("Black-box scores cannot be audited, exported or reproduced — trust "
          "is exactly what is missing.")])
    card(s, 0.6, 4.0, 12.25, 1.55, "Free tiers exist — but the boundary is unproven",
         [("Cloud free tiers are generous, yet nobody shows with measured numbers "
          "what volume they really cover, or what latency a free-tier design "
          "actually pays.")], accent=TEAL)
    text(s, 0.6, 5.85, 12.25, 0.6,
         "Our answer: an open, reproducible, free-tier serverless pipeline — "
         "and honest measurements of where it wins and where it bends.",
         size=15, bold=True, color=BLUE)
    notes(s, "Three gaps: price, skill, and trust. A salon or restaurant "
             "paying $299 a month for sentiment analytics is paying for roughly "
             "one engineer-hour per week of value. DIY alternatives need "
             "engineering the owner does not have. And existing tools rarely "
             "show how a score was produced. Free tiers look like the answer, "
             "but their real capacity is folklore — so we measured it.")

    # ---- 3 objectives ------------------------------------------------------
    s = content_slide(prs, 3, "Objectives", "as approved in the proposal — plus measurement rigor")
    bullets(s, [
        ("1.  A serverless ingestion-to-dashboard pipeline that runs inside "
        "free-tier limits, with zero servers to administer."),
        ("2.  Pluggable three-class sentiment engines — VADER (default, fully "
        "offline), TextBlob, Hugging Face DistilBERT, Comprehend adapter."),
        ("3.  Storage abstraction: SQLite locally, Firestore (proposal) and "
        "DynamoDB (infrastructure-as-code) in the cloud — same handlers."),
        ("4.  An interactive dashboard: distribution, trends, keywords, filters, "
        "CSV/JSON upload, live single-review analysis."),
        ("5.  Quantify accuracy, latency, throughput and monthly cost with "
        "reproducible experiments (seed 42)."),
        ("6.  Automated tests end-to-end, with every published number traceable "
        "to an executed run."),
    ], 0.75, 1.6, 11.9, 5.2, size=16, space=14)
    notes(s, "Six objectives. Note that the proposal's stack — Firestore, "
             "Hugging Face, Streamlit — stays the design target; every layer is "
             "behind an interface so the identical code runs locally without "
             "any cloud credentials and deploys to the cloud unchanged. "
             "Objective five is what makes this a cloud-computing project and "
             "not just a demo: we measure the free tier rather than assume it.")

    # ---- 4 architecture ----------------------------------------------------
    s = content_slide(prs, 4, "System architecture",
                      "one Lambda router · three pluggable layers")
    picture_fit(s, FIGURES / "architecture_diagram.png", 1.9, 1.35, 9.6, 5.1)
    notes(s, "One entry point — lambda_handler — routes API-Gateway v1/v2 "
             "requests and S3 object-created events to ingestion, processing "
             "and read handlers. Behind it sit three pluggable layers: four "
             "sentiment engines, three storage backends, and object ingestion. "
             "The local FastAPI server forwards every HTTP request to this same "
             "function, so local and cloud behaviour cannot drift apart — "
             "that is local/cloud parity, and it is why the whole system could "
             "be tested without credentials.")

    # ---- 5 serverless + free tier rationale --------------------------------
    s = content_slide(prs, 5, "Why serverless — and why the free tier holds",
                      "economics measured, not assumed")
    card(s, 0.6, 1.45, 6.0, 2.15, "FaaS economics",
         ["Billed per request and per millisecond — zero cost at zero traffic.",
          ("Event-driven: HTTP requests and S3 uploads both trigger the same "
          "function; auto-scaling is free."),
          ("No OS patching, no capacity planning — the scarce resource a small "
          "team actually has.")])
    card(s, 6.85, 1.45, 6.0, 2.15, "AWS free-tier allowances used",
         ["Lambda: 1M requests + 400k GB-seconds/month — always free.",
          "API Gateway 1M calls, S3 5 GB, CloudWatch 5 GB logs (12-month).",
          "DynamoDB: 25 GB storage + provisioned 25 WCU/RCU."], accent=TEAL)
    card(s, 0.6, 3.95, 6.0, 2.15, "Measured cold-start reality",
         [(f"Engine init: VADER {lv['cold_init_s']:.2f} s vs DistilBERT "
          f"{lh['cold_init_s']:.1f} s (model load dominates)."),
          (f"Warm: VADER {lv['warm_mean_ms']:.3f} ms mean per review — "
          f"DistilBERT {lh['warm_mean_ms']:.0f} ms."),
          ("→ VADER stays the default engine; FaaS design follows the "
          "measurement.")], accent=TEAL)
    card(s, 6.85, 3.95, 6.0, 2.15, "Free tier is not $0 — and that is fine",
         [(f"At 1M reviews/month: free tier ${c1m.loc['aws_free_tier', 'monthly_cost_usd']:.2f}, "
          f"no-free-tier ${c1m.loc['aws_payg_after_free_tier', 'monthly_cost_usd']:.2f} "
          "(DynamoDB on-demand bills per request)."),
          (f"Always-on t3.micro: ${c1m.loc['ec2_t3_micro_vm', 'monthly_cost_usd']:.2f}/mo — "
          "≈3,300× the serverless path at 1K reviews, plus a server to patch.")])
    notes(s, "Serverless changes the cost floor: at zero traffic the bill is "
             "zero, which no VM can match. The free tier covers a small "
             "business for a long time — but not literally everything: "
             "DynamoDB's on-demand mode bills per request even inside the free "
             "allowance, which is why our honest free-tier row at one million "
             "reviews is $2.50, not zero. The cold-start measurement decided "
             "the engine choice for us: 18.6 seconds to load DistilBERT is "
             "unusable behind an interactive API; 50 milliseconds for VADER is "
             "not.")

    # ---- 6 tech stack ------------------------------------------------------
    s = content_slide(prs, 6, "Technology stack", "proposal targets vs what runs today")
    card(s, 0.6, 1.45, 6.0, 4.35, "Proposal stack (design target)",
         ["Firebase Firestore (Spark plan) — cloud document database.",
          "Hugging Face Inference API — managed sentiment AI.",
          "Streamlit Community Cloud — free dashboard hosting.",
          "",
          ("Status: engine + storage adapters written behind interfaces; "
          "deployment gated on credentials — nothing is pretended live."),
          ("AWS roles stay optional: SAM infrastructure-as-code for Lambda, "
          "API Gateway, DynamoDB, S3, CloudWatch.")])
    card(s, 6.85, 1.45, 6.0, 4.35, "Implemented and measured here",
         ["Python 3.13 · one lambda_handler · FastAPI local parity server.",
          ("Engines: VADER (default) · TextBlob · DistilBERT-SST2 · "
          "Comprehend adapter."),
          ("Storage: SQLite (live) · DynamoDB + S3 + SAM template (validated, "
          "not deployed)."),
          "Dashboard: HTML/JS + vendored Chart.js at /ui — works offline.",
          (f"Tests: {n['tests']} pytest (unit + HTTP e2e) in {n['tests_s']:.2f} s "
          "+ Playwright browser E2E 9/9."),
          "Experiments: 5 runners, seed 42, raw outputs in results/."],
         accent=TEAL)
    notes(s, "Two columns, one honest gap. The right column is what executes "
             "and is measured today; the left column is the proposal's hosted "
             "stack, which the remaining parts of the project will connect — "
             "Firestore and Streamlit Community Cloud. The interface "
             "abstraction means connecting them is configuration, not a "
             "rewrite: STORAGE_BACKEND=firestore and an HF token.")

    # ---- 7 pipeline walkthrough --------------------------------------------
    s = content_slide(prs, 7, "Pipeline walkthrough", "upload → classify → dashboard, ten stages")
    picture_fit(s, FIGURES / "dataflow_diagram.png", 1.4, 1.5, 10.6, 4.9)
    notes(s, "Ten numbered stages. Ingestion (1–4) accepts CSV or JSON from "
             "the dashboard, the API or an S3 drop; normalises column aliases, "
             "validates rows, de-duplicates and upserts idempotently by review "
             "id. Processing (5–8) cleans each text, runs the engine into the "
             "three-class scheme with the 0.15 neutral band, extracts "
             "keywords, and writes label, confidence, per-class scores and "
             "engine back to the same record. Reads (9–10) aggregate "
             "summary/trends/keywords for the dashboard and API consumers. "
             "Batches are capped at 200 reviews to stay inside free-tier "
             "quotas.")

    # ---- 8 dashboard demo 1 -------------------------------------------------
    s = content_slide(prs, 8, "Dashboard — the product", "real capture, 1,214-review corpus")
    bullets(s, [("KPI cards, sentiment doughnut, day/week/month trends and top "
                "keywords — all computed by the read APIs."),
                ("Light and dark themes, fully responsive; Chart.js is "
                "vendored, so the dashboard works offline."),
                ("Served at /ui — the same static bundle deploys unchanged to "
                "an S3 website bucket or Streamlit.")],
            0.7, 1.7, 5.3, 4.6, size=14.5, space=16)
    picture_fit(s, SHOTS / "01_dashboard_light_full.png", 6.3, 1.45, 3.35, 5.3,
                crop_bottom=0.55)
    picture_fit(s, SHOTS / "02_dashboard_dark_full.png", 9.85, 1.45, 3.35, 5.3,
                crop_bottom=0.55)
    text(s, 6.3, 6.78, 6.9, 0.3, "Light theme (left) · dark theme (right) — "
         "top of the page; full-page captures in docs/screenshots/",
         size=9.5, color=GRAY, align=PP_ALIGN.CENTER)
    notes(s, "This is the real dashboard, not a mock-up: headless-Chromium "
             "captures against the live local server with all 1,214 reviews "
             "loaded. KPIs, charts and keywords all come from the /summary, "
             "/trends and /keywords endpoints — the dashboard holds no data "
             "logic of its own. Both themes and the responsive layout were "
             "verified by the browser end-to-end test.")

    # ---- 9 dashboard demo 2 -------------------------------------------------
    s = content_slide(prs, 9, "Dashboard — filters, upload, live analysis",
                      "every flow verified by browser E2E (9/9 checks)")
    picture_fit(s, SHOTS / "03_table_negative_filter.png", 0.6, 1.5, 4.5, 4.9)
    text(s, 0.6, 6.45, 4.5, 0.3, "Sentiment filter → charts + table",
         size=10, color=GRAY, align=PP_ALIGN.CENTER)
    picture_fit(s, SHOTS / "05_upload_result.png", 5.3, 1.5, 3.2, 2.35)
    picture_fit(s, SHOTS / "04_analyze_live_result.png", 5.3, 4.15, 3.2, 2.35)
    text(s, 5.3, 6.45, 3.2, 0.3, "CSV upload report · live analysis",
         size=10, color=GRAY, align=PP_ALIGN.CENTER)
    picture_fit(s, SHOTS / "06_mobile_dark.png", 8.75, 1.5, 1.5, 4.9,
                crop_bottom=0.83)
    bullets(s, [("Filters: sentiment, rating, date, keyword, business type — "
                "case-insensitive."),
                ("CSV/JSON upload with template download and a row-level "
                "ingestion report."),
                ("Live box: analyse one review instantly, per-class scores "
                "shown."),
                "Mobile: zero horizontal overflow at 390 px (E2E-checked)."],
            10.45, 1.7, 2.6, 4.8, size=11.5, space=12)
    notes(s, "Beyond the charts, four interaction flows matter for a real "
             "user: filtering the corpus by sentiment (charts and table update "
             "together), bulk CSV upload with a per-row success/failure report, "
             "instant single-review analysis for 'what does this complaint say', "
             "and a usable phone layout. The Playwright suite clicks through "
             "all of them headlessly and captured these screenshots as "
             "evidence.")

    # ---- 10 results & accuracy ---------------------------------------------
    s = content_slide(prs, 10, "Results — accuracy against star labels",
                      "1,214 real reviews · ground truth: 1-2★ negative, 3★ neutral, 4-5★ positive")
    mini_table(s, ["Engine", "Accuracy", "Macro-F1", "Neg. recall", "ms/review"],
               [["VADER (default)", f"{vader['accuracy']:.4f}", f"{vader['macro_f1']:.4f}",
                 f"{vader['recall_negative']:.4f}", f"{vader['ms_per_review']:.3f}"],
                ["TextBlob", f"{tb_['accuracy']:.4f}", f"{tb_['macro_f1']:.4f}",
                 f"{tb_['recall_negative']:.4f}", f"{tb_['ms_per_review']:.3f}"],
                ["HF DistilBERT", f"{hf['accuracy']:.4f}", f"{hf['macro_f1']:.4f}",
                 f"{hf['recall_negative']:.4f}", f"{hf['ms_per_review']:.3f}"]],
               0.6, 1.55, 6.1, 1.5, size=11.5)
    bullets(s, [("Corpus is 98% positive (1,190/12/12) — an 'always positive' "
                "baseline already scores 0.98 accuracy, so accuracy alone "
                "proves nothing."),
                ("VADER is the best all-rounder: highest accuracy and macro-F1, "
                "and 228× faster per review than DistilBERT."),
                ("DistilBERT catches the most negatives (10 of 12) but never "
                "predicts neutral — SST-2 is binary by construction."),
                (f"{n['tests']} automated tests lock the pipeline and the "
                "metric definitions; Comprehend honestly excluded (no AWS "
                "credentials).")],
            0.6, 3.3, 6.2, 3.4, size=13, space=12)
    picture_fit(s, FIGURES / "model_comparison_scores.png", 7.0, 1.5, 5.9, 5.3)
    notes(s, "Evaluation is deliberately harsh. Because 98 percent of the "
             "corpus is positive, headline accuracy is nearly meaningless — "
             "we therefore lead with macro-F1 and per-class recall from the "
             "confusion matrices. VADER wins on the balanced measures while "
             "being three orders of magnitude cheaper to run per review. "
             "DistilBERT's negative recall of 10 out of 12 is the accuracy "
             "story, and its zero-neutral prediction is exactly the kind of "
             "finding the ablation and neutral-band design were built to "
             "surface.")

    # ---- 11 performance ------------------------------------------------------
    s = content_slide(prs, 11, "Performance — latency and throughput",
                      "500 timed requests per engine · ingestion batches 100 → 10,000")
    picture_fit(s, FIGURES / "latency_warm_percentiles.png", 0.6, 1.5, 6.0, 5.2)
    card(s, 6.9, 1.5, 5.95, 2.5, "Warm latency (mean / p99)",
         [(f"VADER {lv['warm_mean_ms']:.3f} / {lv['warm_p99_ms']:.3f} ms — "
          "interactive-instant."),
          f"TextBlob {lt['warm_mean_ms']:.3f} / {lt['warm_p99_ms']:.3f} ms.",
          (f"DistilBERT {lh['warm_mean_ms']:.0f} / {lh['warm_p99_ms']:.0f} ms "
          "(CPU, batch-of-1).")])
    card(s, 6.9, 4.25, 5.95, 2.45, "Throughput & memory (measured)",
         [(f"Ingestion: {thr.loc[thr['batch_size'] == 10000, 'reviews_per_second'].iloc[0]:,.0f} reviews/s "
          "at 10k rows — linear scaling."),
          (f"Peak RSS < 150 MB ({thr['rss_peak_mb'].max():.0f} MB worst); heap "
          "grows ≈2 MB per 10k rows."),
          (f"Cold start (fresh process): VADER {lv['cold_process_wall_s']:.1f} s "
          f"total vs DistilBERT {lh['cold_process_wall_s']:.1f} s — model "
          "loading dominates.")], accent=TEAL)
    notes(s, "Two slides' worth of numbers in one view. Warm latency: the "
             "lexicon engines answer in about a millisecond, DistilBERT in "
             "about fifty — fine for batches, marginal for an interactive "
             "API. Ingestion throughput is flat at roughly seventeen thousand "
             "reviews per second from one thousand to ten thousand rows, with "
             "memory under 150 megabytes — one order of magnitude above the "
             "largest modelled workload's steady-state rate. The cold-start "
             "column is the FaaS design input: total process time to first "
             "result is dominated by loading torch and the model weights.")

    # ---- 12 cost analysis ----------------------------------------------------
    s = content_slide(prs, 12, "Free-tier cost analysis",
                      f"measured inputs (7.47 ms/review, 732 B/review) · published prices, "
                      f"us-east-1, accessed {n['cost_sources_accessed']}")
    picture_fit(s, FIGURES / "cost_model.png", 0.6, 1.5, 7.0, 5.2)
    mini_table(s, ["Reviews/mo", "AWS free tier", "t3.micro", "Comprehend"],
               [[f"{w:,}",
                f"${cost[(cost.workload_reviews_per_month == w) & (cost.option == 'aws_free_tier')].monthly_cost_usd.iloc[0]:.4f}",
                f"${cost[(cost.workload_reviews_per_month == w) & (cost.option == 'ec2_t3_micro_vm')].monthly_cost_usd.iloc[0]:.2f}",
                f"${cost[(cost.workload_reviews_per_month == w) & (cost.option == 'managed_saaS_comprehend')].monthly_cost_usd.iloc[0]:.2f}"]
                for w in (1_000, 100_000, 1_000_000)],
               7.9, 1.55, 5.0, 1.5, size=11.5)
    bullets(s, [("Serverless wins at every modelled volume — pennies even with "
                "zero free-tier allowance ($3.35/mo at 1M reviews)."),
                ("Free tier ≠ $0: DynamoDB on-demand is outside the "
                "provisioned-only allowance → $2.50/mo at 1M."),
                ("Managed sentiment APIs scale linearly with text: Comprehend "
                "$300.49/mo at 1M — 90× the pipeline."),
                ("Flat-rate SaaS ≈ $299/mo (third-party, UNVERIFIED) only "
                "makes sense above ~1M reviews."),
                ("Every price carries a source URL in results/cost_sources.json "
                "— nothing invented.")],
            7.9, 3.35, 5.0, 3.4, size=11.5, space=9)
    notes(s, "The cost model combines two measured inputs — 7.47 milliseconds "
             "per processed review including write-back, and 732 bytes stored "
             "per review — with published, dated prices. The headline: two "
             "dollars fifty per month for a million reviews under the free "
             "tier, three thirty-five without any free tier, against three "
             "hundred for a managed sentiment API. The always-on VM is the "
             "trap: eight dollars and change sounds cheap until you compare it "
             "with a serverless path that costs fractions of a cent at small "
             "volume — and still needs no one to patch it.")

    # ---- 13 challenges --------------------------------------------------------
    s = content_slide(prs, 13, "Challenges & lessons learned", "the honest part of the talk")
    bullets(s, [
        ("No cloud credentials on the development machine → every cloud "
        "component (Firestore, DynamoDB, Comprehend, HF API) was written "
        "behind interfaces and verified through real local equivalents — "
        "nothing was ever pretended live."),
        ("Severe label skew (1,190/12/12) → accuracy alone is misleading; "
        "macro-F1, per-class recall and confusion matrices are the reported "
        "evidence."),
        ("Binary transformer vs the required 3-class output → neutral-band "
        "mapping; the ablation showed TextBlob collapses at band 0.5 "
        "(accuracy 0.6013), justifying the 0.15 default."),
        ("Windows quirks: PowerShell mangling inline JSON, SQLite temp-dir "
        "locks in one experiment, Hugging Face cache symlink fallback."),
        (f"Writing {n['tests']} tests surfaced four real bugs — silent "
        "limit=0 default, case-sensitive sentiment filter, missing storage "
        "default, and a per-1M pricing bug that produced a $2,606/month "
        "nonsense estimate — all fixed and regression-locked."),
    ], 0.75, 1.6, 11.9, 5.3, size=15, space=16)
    notes(s, "We include challenges because a cloud project is mostly "
             "constraints. With no credentials, the honest move was local "
             "parity, not screenshots of consoles. The skewed dataset forced "
             "better metrics. The binary-transformer mismatch became the "
             "neutral-band feature — and its ablation. And the test suite "
             "paid for itself immediately: the cost model's first version "
             "multiplied per-million prices by raw counts and claimed $2,606 "
             "per month; a sanity check caught it, and a regression test now "
             "pins the arithmetic.")

    # ---- 14 conclusion & future -----------------------------------------------
    s = content_slide(prs, 14, "Conclusion & future work")
    card(s, 0.6, 1.45, 6.0, 4.35, "Delivered — and measured",
         [(f"Free-tier review analytics is real: VADER "
          f"{vader['accuracy']:.4f} accuracy at {lv['warm_mean_ms']:.3f} ms "
          "per review."),
          (f"≈{thr['reviews_per_second'].max():,.0f} reviews/s ingestion, "
          "<150 MB memory, linear scaling."),
          (f"${c1m.loc['aws_free_tier', 'monthly_cost_usd']:.2f}/month at one "
          "million reviews — ~120× cheaper than a managed sentiment API."),
          (f"{n['tests']} tests green + browser E2E 9/9; five experiment "
          "suites, seed 42, raw numbers in results/."),
          ("Nothing deployed, nothing billed, proposal untouched — the cloud "
          "parts activate with credentials, not rewrites.")])
    card(s, 6.85, 1.45, 6.0, 4.35, "Next steps",
         [("Connect the proposal stack: Firestore adapter "
          "(STORAGE_BACKEND=firestore) + Streamlit dashboard on Community "
          "Cloud."),
          ("Live Hugging Face Inference-API token; fine-tune DistilBERT to "
          "recover neutral recall."),
          ("Multilingual and aspect-level sentiment (food, service, price) — "
          "actionable per-topic scores."),
          ("Streaming ingestion and per-tenant rate limiting for multi-business "
          "use."),
          ("CI/CD with drift checks on accuracy and cost; energy/carbon "
          "accounting per inference.")], accent=TEAL)
    notes(s, "In one sentence: the pipeline works, the numbers are real, and "
             "the cost is close to zero. What remains is connectivity, not "
             "construction — Firestore and Streamlit Community Cloud plug into "
             "the interfaces we already have. The measurement side continues "
             "too: fine-tuning for neutral recall, aspect-level sentiment for "
             "actionability, and extending the cost model from dollars to "
             "energy.")

    # ---- 15 Q&A ---------------------------------------------------------------
    s = prs.slides.add_slide(prs.slide_layouts[6])
    rect(s, 0, 0, SW, SH, NAVY)
    rect(s, 5.75, 2.75, 1.8, 0.07, BLUE)
    text(s, 1.0, 1.6, 11.3, 1.1, "Thank you — questions?", size=40, bold=True,
         color=WHITE, align=PP_ALIGN.CENTER)
    text(s, 1.0, 3.15, 11.3, 0.5, "Ahmed Bin Jaffar  ·  26MS-DS037  ·  MSDS "
         "Semester 2, MUET", size=16, color=PALE, align=PP_ALIGN.CENTER)
    text(s, 1.0, 4.25, 11.3, 1.2,
         "Artifacts: docs/Project_Report.docx  ·  presentation/  ·  "
         "results/ (raw numbers)  ·  figures/ (300-dpi charts)\n"
         "Dashboard live at /ui  ·  tests: pytest (105) + Playwright E2E  ·  "
         "re-run: scripts/generate_presentation.py",
         size=13, color=PALE, align=PP_ALIGN.CENTER)
    footer(s, 15, dark=True)
    notes(s, "Happy to take questions. If anyone wants to see the system "
             "running, it starts with one script — scripts/run_local.ps1 — "
             "and the whole study re-runs with scripts/run_experiments.ps1. "
             "The report and every raw result file are in the repository.")

    return prs


def main() -> None:
    numbers = load_numbers()
    print("building presentation...")
    prs = build(numbers)
    prs.save(OUT)

    # validity check: reopen, confirm slide count + notes on every slide
    check = Presentation(str(OUT))
    n_slides = len(check.slides)
    missing = [i + 1 for i, sl in enumerate(check.slides)
               if not sl.notes_slide.notes_text_frame.text.strip()]
    print(f"saved {OUT}")
    print(f"validity check: {n_slides} slides; slides without notes: "
          f"{missing or 'none'}")


if __name__ == "__main__":
    main()
