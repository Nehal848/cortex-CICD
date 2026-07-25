"""
Report Generator
~~~~~~~~~~~~~~~~~
Generates downloadable PDF reports using reportlab.
Falls back to JSON if reportlab is not installed.

Reports:
  - Pipeline Report: run stats, success rate, healed runs
  - AI Prediction Report: risk score, failure type, root cause, recommendations
  - Healing Report: healing timeline, strategy used, outcome
"""

import io
import json
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def _has_reportlab() -> bool:
    try:
        import reportlab  # noqa: F401
        return True
    except ImportError:
        return False


# ── Public API ─────────────────────────────────────────────────────

def generate_pipeline_report(runs: list[dict], stats: dict) -> tuple[bytes, str]:
    """
    Generate a pipeline summary report.

    Returns
    -------
    (bytes, mimetype)
    """
    if _has_reportlab():
        return _pipeline_pdf(runs, stats), "application/pdf"
    return _pipeline_json(runs, stats), "application/json"


def generate_ai_report(run_id: str, prediction: dict, rca: dict) -> tuple[bytes, str]:
    if _has_reportlab():
        return _ai_pdf(run_id, prediction, rca), "application/pdf"
    return _ai_json(run_id, prediction, rca), "application/json"


def generate_healing_report(healing_events: list[dict]) -> tuple[bytes, str]:
    if _has_reportlab():
        return _healing_pdf(healing_events), "application/pdf"
    return _healing_json(healing_events), "application/json"


# ── PDF generators ─────────────────────────────────────────────────

def _pipeline_pdf(runs: list[dict], stats: dict) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.enums import TA_CENTER

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story  = []

    # Title
    title_style = ParagraphStyle("title", parent=styles["Title"], textColor=colors.HexColor("#58a6ff"),
                                 fontSize=22, spaceAfter=6)
    sub_style   = ParagraphStyle("sub",   parent=styles["Normal"], textColor=colors.grey, fontSize=10)
    body_style  = ParagraphStyle("body",  parent=styles["Normal"], fontSize=10, leading=14)

    story.append(Paragraph("CortexCICD — Pipeline Report", title_style))
    story.append(Paragraph(f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", sub_style))
    story.append(Spacer(1, 0.5*cm))

    # Stats summary table
    stat_data = [
        ["Metric",         "Value"],
        ["Total Runs",     str(stats.get("total_runs", 0))],
        ["Success Rate",   f"{stats.get('success_rate', 0)}%"],
        ["Failed Builds",  str(stats.get("failed", 0))],
        ["Auto-Healed",    str(stats.get("healed", 0))],
        ["Active Alerts",  str(stats.get("active_alerts", 0))],
        ["Deployments",    str(stats.get("total_deps", 0))],
    ]
    tbl = Table(stat_data, colWidths=[10*cm, 6*cm])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#161b22")),
        ("TEXTCOLOR",  (0,0), (-1,0), colors.HexColor("#58a6ff")),
        ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",   (0,0), (-1,-1), 10),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.HexColor("#0d1117"), colors.HexColor("#161b22")]),
        ("TEXTCOLOR",  (0,1), (-1,-1), colors.HexColor("#c9d1d9")),
        ("GRID",       (0,0), (-1,-1), 0.5, colors.HexColor("#30363d")),
        ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 0.5*cm))

    # Recent runs table
    story.append(Paragraph("Recent Pipeline Runs", ParagraphStyle("h2", parent=styles["Heading2"],
                            textColor=colors.HexColor("#58a6ff"), fontSize=14)))
    story.append(Spacer(1, 0.3*cm))

    run_data = [["Run ID", "Branch", "Status", "Triggered By", "Duration", "Risk"]]
    for r in runs[:20]:
        run_data.append([
            r.get("run_id", ""),
            r.get("branch", "")[:20],
            r.get("status", ""),
            r.get("triggered_by", ""),
            f"{r.get('duration_secs', 0)}s",
            f"{r.get('risk_score', 0)}/100",
        ])

    run_tbl = Table(run_data, colWidths=[3*cm, 4*cm, 2.5*cm, 2.5*cm, 2*cm, 2*cm])
    run_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#161b22")),
        ("TEXTCOLOR",  (0,0), (-1,0), colors.HexColor("#58a6ff")),
        ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",   (0,0), (-1,-1), 8),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.HexColor("#0d1117"), colors.HexColor("#161b22")]),
        ("TEXTCOLOR",  (0,1), (-1,-1), colors.HexColor("#c9d1d9")),
        ("GRID",       (0,0), (-1,-1), 0.5, colors.HexColor("#30363d")),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    story.append(run_tbl)

    # Footer
    story.append(Spacer(1, 1*cm))
    story.append(Paragraph("This report was automatically generated by CortexCICD Self-Healing Platform.",
                            sub_style))

    doc.build(story)
    return buf.getvalue()


def _ai_pdf(run_id: str, prediction: dict, rca: dict) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story  = []

    title_style = ParagraphStyle("title", parent=styles["Title"],
                                 textColor=colors.HexColor("#58a6ff"), fontSize=20)
    sub_style   = ParagraphStyle("sub", parent=styles["Normal"], textColor=colors.grey, fontSize=10)
    body_style  = ParagraphStyle("body", parent=styles["Normal"], fontSize=10, leading=14,
                                 textColor=colors.HexColor("#c9d1d9"))

    story.append(Paragraph(f"AI Prediction Report — {run_id}", title_style))
    story.append(Paragraph(f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}", sub_style))
    story.append(Spacer(1, 0.5*cm))

    # Prediction block
    pred_data = [
        ["Field",           "Value"],
        ["Risk Score",      f"{prediction.get('risk_score', 0)}/100"],
        ["Predicted Type",  prediction.get("failure_type", "N/A")],
        ["Confidence",      f"{round(prediction.get('confidence', 0) * 100, 1)}%"],
        ["Model",           prediction.get("model", "unknown")],
    ]
    _add_table(story, pred_data)
    story.append(Spacer(1, 0.5*cm))

    # Root cause block
    story.append(Paragraph("Root Cause Analysis", ParagraphStyle("h2", parent=styles["Heading2"],
                            textColor=colors.HexColor("#58a6ff"), fontSize=14)))
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph(f"<b>Root Cause:</b> {rca.get('root_cause', 'N/A')}", body_style))
    story.append(Spacer(1, 0.3*cm))

    for i, rec in enumerate(rca.get("recommendations", []), 1):
        story.append(Paragraph(f"{i}. {rec}", body_style))

    doc.build(story)
    return buf.getvalue()


def _healing_pdf(events: list[dict]) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    story  = []

    title_style = ParagraphStyle("title", parent=styles["Title"],
                                 textColor=colors.HexColor("#58a6ff"), fontSize=20)
    story.append(Paragraph("Self-Healing Report", title_style))
    story.append(Paragraph(f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
                            ParagraphStyle("sub", parent=styles["Normal"], textColor=colors.grey, fontSize=10)))
    story.append(Spacer(1, 0.5*cm))

    event_data = [["Run ID", "Failure Type", "Strategy", "Outcome", "Timestamp"]]
    for e in events[:30]:
        event_data.append([
            e.get("run_id", ""), e.get("failure_type", "")[:25],
            e.get("strategy", ""), e.get("outcome", ""),
            str(e.get("created_at", ""))[:16],
        ])
    _add_table(story, event_data, col_widths=[2.5*cm, 5*cm, 3*cm, 2.5*cm, 4*cm])

    doc.build(story)
    return buf.getvalue()


# ── Helpers ────────────────────────────────────────────────────────

def _add_table(story, data, col_widths=None):
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle

    tbl = Table(data, colWidths=col_widths)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#161b22")),
        ("TEXTCOLOR",  (0,0), (-1,0), colors.HexColor("#58a6ff")),
        ("FONTNAME",   (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE",   (0,0), (-1,-1), 9),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.HexColor("#0d1117"), colors.HexColor("#161b22")]),
        ("TEXTCOLOR",  (0,1), (-1,-1), colors.HexColor("#c9d1d9")),
        ("GRID",       (0,0), (-1,-1), 0.5, colors.HexColor("#30363d")),
        ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]))
    story.append(tbl)


# ── JSON fallbacks ─────────────────────────────────────────────────

def _pipeline_json(runs, stats) -> bytes:
    return json.dumps({"type": "pipeline_report", "stats": stats, "runs": runs,
                       "generated": datetime.utcnow().isoformat()}, indent=2).encode()


def _ai_json(run_id, prediction, rca) -> bytes:
    return json.dumps({"type": "ai_report", "run_id": run_id, "prediction": prediction, "rca": rca,
                       "generated": datetime.utcnow().isoformat()}, indent=2).encode()


def _healing_json(events) -> bytes:
    return json.dumps({"type": "healing_report", "events": events,
                       "generated": datetime.utcnow().isoformat()}, indent=2).encode()
