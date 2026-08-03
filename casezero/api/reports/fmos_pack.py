"""Machine-assembled FMOS referral pack with an integrity verification page."""

from __future__ import annotations

from io import BytesIO
import math
from typing import Any, Iterable

from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from api.kernel.chain import ChainEvent, ChainVerdict

PAPER = HexColor("#E4EAE5")
PANEL = HexColor("#F2F5F2")
INK = HexColor("#131A15")
INK_2 = HexColor("#5A665D")
GUILLOCHE = HexColor("#A8BFB0")
ENDORSE = HexColor("#8B2333")


def _safe(value: Any) -> str:
    text = "-" if value in (None, "") else str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _masked_account(value: Any) -> str:
    text = str(value or "-")
    return f"******{text[-4:]}" if text.isdigit() and len(text) >= 8 else text


def _canvas(page, doc) -> None:
    width, height = A4
    page.saveState()
    page.setFillColor(PAPER)
    page.rect(0, 0, width, height, fill=1, stroke=0)
    page.setStrokeColor(INK)
    page.setLineWidth(0.7)
    page.rect(12 * mm, 12 * mm, width - 24 * mm, height - 24 * mm, fill=0, stroke=1)

    # Lightweight generated guilloche: two phase-shifted sine paths. Vector,
    # crisp at any zoom, and quiet enough that report content remains primary.
    page.setStrokeColor(GUILLOCHE)
    page.setLineWidth(0.25)
    for phase in (0.0, math.pi / 2):
        path = page.beginPath()
        for i in range(181):
            x = 20 * mm + i * (width - 40 * mm) / 180
            y = height - 22 * mm + math.sin(i / 7 + phase) * 2.2 * mm
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        page.drawPath(path)

    page.setFillColor(INK_2)
    page.setFont("Courier", 6.5)
    page.drawString(18 * mm, 16 * mm, "CASEZERO / MYBANK BERHAD / FMOS REFERRAL / SYNTHETIC")
    page.drawRightString(width - 18 * mm, 16 * mm, f"PAGE {doc.page}")
    page.restoreState()


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "kicker": ParagraphStyle(
            "kicker", parent=base["Normal"], fontName="Courier-Bold", fontSize=7.5,
            leading=10, textColor=INK_2, spaceAfter=6, uppercase=True,
        ),
        "title": ParagraphStyle(
            "title", parent=base["Title"], fontName="Helvetica-Bold", fontSize=27,
            leading=29, textColor=INK, alignment=TA_LEFT, spaceAfter=9,
        ),
        "h2": ParagraphStyle(
            "h2", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=15,
            leading=18, textColor=INK, spaceBefore=14, spaceAfter=8,
        ),
        "body": ParagraphStyle(
            "body", parent=base["BodyText"], fontName="Helvetica", fontSize=9.5,
            leading=14, textColor=INK, spaceAfter=7,
        ),
        "mono": ParagraphStyle(
            "mono", parent=base["BodyText"], fontName="Courier", fontSize=7.2,
            leading=10, textColor=INK_2,
        ),
        "stamp": ParagraphStyle(
            "stamp", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=13,
            leading=16, textColor=INK, alignment=TA_CENTER, borderColor=INK,
            borderWidth=1.1, borderPadding=7, spaceBefore=10, spaceAfter=10,
        ),
    }


def _facts(rows: list[tuple[str, Any]], styles: dict[str, ParagraphStyle]) -> Table:
    data = [
        [Paragraph(_safe(label).upper(), styles["kicker"]), Paragraph(_safe(value), styles["body"])]
        for label, value in rows
    ]
    table = Table(data, colWidths=[48 * mm, 112 * mm], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PANEL),
                ("GRID", (0, 0), (-1, -1), 0.35, GUILLOCHE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table


def build_fmos_pack(
    *,
    case: dict[str, Any],
    events: Iterable[ChainEvent],
    journal: list[dict[str, Any]],
    verdict: ChainVerdict,
    contact_email: str,
) -> bytes:
    """Return an ombudsman-ready PDF. Ciphertext and raw account numbers are omitted."""
    event_rows = list(events)
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=25 * mm,
        rightMargin=25 * mm,
        topMargin=33 * mm,
        bottomMargin=25 * mm,
        title=f"FMOS Referral Pack - {case.get('case_ref', '')}",
        author="CaseZero / MYBank Berhad",
    )
    styles = _styles()
    story: list[Any] = [
        Paragraph("FMOS REFERRAL / MACHINE-ASSEMBLED CASE FILE", styles["kicker"]),
        Paragraph("Financial Markets<br/>Ombudsman Service", styles["title"]),
        Paragraph(
            "Complete complaint record, decision evidence, communications register and "
            "tamper-evidence verification for independent review.",
            styles["body"],
        ),
        Paragraph(
            "CHAIN VERIFIED" if verdict.ok else "VOID - INTEGRITY FAILURE",
            styles["stamp"],
        ),
        Spacer(1, 5 * mm),
        _facts(
            [
                ("Case reference", case.get("case_ref")),
                ("Status", case.get("status")),
                ("Outcome", case.get("outcome")),
                ("Category", case.get("category")),
                ("Urgency / SLA", f"{case.get('urgency', '-')} / {case.get('sla_due', '-')}") ,
                ("Claim amount", f"RM {float(case.get('amount_rm') or 0):,.2f}"),
                ("Account", f"******{case.get('account_last4', '')}"),
                ("Bank contact", contact_email),
            ],
            styles,
        ),
        PageBreak(),
        Paragraph("01 / CASE AND DECISION", styles["kicker"]),
        Paragraph("Complaint and outcome", styles["title"]),
        Paragraph(_safe(case.get("summary")), styles["body"]),
        _facts(
            [
                ("Verification result", case.get("verification_result")),
                ("Classification confidence", case.get("confidence")),
                ("Rule pack version", case.get("rule_pack_version")),
                ("Transaction references", ", ".join(case.get("txn_refs") or [])),
                ("Resolved at", case.get("resolved_at")),
            ],
            styles,
        ),
        Paragraph("Financial journal", styles["h2"]),
    ]
    if journal:
        for entry in journal:
            story.append(
                KeepTogether(
                    [
                        _facts(
                            [
                                ("Entry type", entry.get("entry_type")),
                                ("Debit", _masked_account(entry.get("debit_account"))),
                                ("Credit", _masked_account(entry.get("credit_account"))),
                                ("Amount", f"RM {float(entry.get('amount_rm') or 0):,.2f}"),
                                ("Narrative", entry.get("narrative")),
                                ("Posted by", entry.get("posted_by")),
                            ],
                            styles,
                        ),
                        Spacer(1, 3 * mm),
                    ]
                )
            )
    else:
        story.append(Paragraph("No financial journal was posted.", styles["body"]))

    story.extend(
        [
            PageBreak(),
            Paragraph("02 / COMPLETE TIMELINE", styles["kicker"]),
            Paragraph("Every governed action", styles["title"]),
        ]
    )
    timeline_data = [["SEQ", "EVENT", "ACTOR", "HASH"]]
    for event in event_rows:
        timeline_data.append(
            [
                f"{event.seq:02d}",
                event.event_type,
                event.actor,
                f"{event.hash[:16]}...",
            ]
        )
    timeline = Table(timeline_data, colWidths=[12 * mm, 55 * mm, 45 * mm, 48 * mm], repeatRows=1)
    timeline.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), "Courier-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "Courier"),
                ("FONTSIZE", (0, 0), (-1, -1), 6.8),
                ("TEXTCOLOR", (0, 0), (-1, -1), INK),
                ("BACKGROUND", (0, 0), (-1, 0), GUILLOCHE),
                ("GRID", (0, 0), (-1, -1), 0.3, GUILLOCHE),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(timeline)
    story.extend(
        [
            PageBreak(),
            Paragraph("03 / HASH-CHAIN VERIFICATION", styles["kicker"]),
            Paragraph("Record integrity", styles["title"]),
            Paragraph(
                "Each event hash is recomputed over its canonical payload and the previous "
                "event hash. Verification stops at the first mismatch, so alteration is "
                "located rather than merely suspected.",
                styles["body"],
            ),
            _facts(
                [
                    ("Verification", "PASS" if verdict.ok else "FAIL"),
                    ("Links checked", len(event_rows)),
                    ("First bad sequence", verdict.first_bad_seq),
                    ("Reason", verdict.reason or "All links match their recomputed hashes."),
                    ("Genesis", "0" * 64),
                    ("Terminal hash", event_rows[-1].hash if event_rows else "-"),
                ],
                styles,
            ),
            Spacer(1, 8 * mm),
            Paragraph(
                "This pack is generated from the same append-only record used by the CaseZero "
                "operator surface. It is not a substitute for FMOS intake review.",
                styles["body"],
            ),
        ]
    )
    doc.build(story, onFirstPage=_canvas, onLaterPages=_canvas)
    return buffer.getvalue()
