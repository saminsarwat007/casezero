"""Synthetic MYBank Berhad statement PDFs.

Feeds two things: the evidence attachments in the eval corpus, and the document
that the Gemini vision path reads during the demo. Everything here is fabricated —
no real customer data exists anywhere in this project (T&C originality clause).

Gemini accepts application/pdf directly, so a generated statement exercises the
real production OCR path rather than a mock of it.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

BANK_NAME = "MYBank Berhad"
BANK_REG = "Company No. 196801000752 (12345-X)"


@dataclass(frozen=True)
class StatementLine:
    posted: date
    description: str
    amount_rm: float
    is_credit: bool = False


@dataclass(frozen=True)
class StatementSpec:
    account_holder: str
    account_no: str
    nric_masked: str
    period_label: str
    opening_balance_rm: float
    lines: tuple[StatementLine, ...]

    @property
    def closing_balance_rm(self) -> float:
        balance = self.opening_balance_rm
        for line in self.lines:
            balance += line.amount_rm if line.is_credit else -line.amount_rm
        return balance


def render_statement(spec: StatementSpec) -> bytes:
    """Render to PDF bytes.

    Laid out like a real retail statement — right-aligned monospaced amounts, a
    running balance, ruled columns — because an extraction path that only works on
    tidy synthetic text is not evidence that it works at all.
    """
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    left = 18 * mm
    right = width - 18 * mm
    y = height - 22 * mm

    # ─── Masthead ───────────────────────────────────────────────────────────
    pdf.setFont("Helvetica-Bold", 15)
    pdf.drawString(left, y, BANK_NAME)
    pdf.setFont("Helvetica", 7)
    pdf.drawString(left, y - 11, BANK_REG)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawRightString(right, y, "STATEMENT OF ACCOUNT")
    pdf.setFont("Helvetica", 8)
    pdf.drawRightString(right, y - 11, spec.period_label)

    y -= 20
    pdf.setLineWidth(1.1)
    pdf.line(left, y, right, y)

    # ─── Account block ──────────────────────────────────────────────────────
    y -= 16
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(left, y, spec.account_holder)
    pdf.setFont("Helvetica", 8)
    y -= 11
    pdf.drawString(left, y, f"Account No: {spec.account_no}")
    y -= 10
    pdf.drawString(left, y, f"NRIC: {spec.nric_masked}")

    pdf.setFont("Helvetica", 8)
    pdf.drawRightString(right, y + 11, f"Opening Balance: RM {spec.opening_balance_rm:,.2f}")
    pdf.drawRightString(right, y, f"Closing Balance: RM {spec.closing_balance_rm:,.2f}")

    # ─── Column headers ─────────────────────────────────────────────────────
    y -= 20
    pdf.setFillColor(colors.HexColor("#E4EAE5"))
    pdf.rect(left, y - 4, right - left, 14, stroke=0, fill=1)
    pdf.setFillColor(colors.black)
    pdf.setFont("Helvetica-Bold", 7.5)
    pdf.drawString(left + 3, y, "DATE")
    pdf.drawString(left + 60, y, "TRANSACTION DESCRIPTION")
    pdf.drawRightString(right - 96, y, "DEBIT (RM)")
    pdf.drawRightString(right - 48, y, "CREDIT (RM)")
    pdf.drawRightString(right - 3, y, "BALANCE (RM)")

    # ─── Rows ───────────────────────────────────────────────────────────────
    y -= 8
    balance = spec.opening_balance_rm
    for line in spec.lines:
        y -= 13
        balance += line.amount_rm if line.is_credit else -line.amount_rm

        pdf.setFont("Helvetica", 7.5)
        pdf.drawString(left + 3, y, line.posted.strftime("%d/%m/%Y"))
        pdf.drawString(left + 60, y, line.description[:52])

        pdf.setFont("Courier", 7.5)
        if line.is_credit:
            pdf.drawRightString(right - 48, y, f"{line.amount_rm:,.2f}")
        else:
            pdf.drawRightString(right - 96, y, f"{line.amount_rm:,.2f}")
        pdf.drawRightString(right - 3, y, f"{balance:,.2f}")

        pdf.setStrokeColor(colors.HexColor("#C8D2CA"))
        pdf.setLineWidth(0.3)
        pdf.line(left, y - 3.5, right, y - 3.5)
        pdf.setStrokeColor(colors.black)

    # ─── Footer ─────────────────────────────────────────────────────────────
    y -= 24
    pdf.setFont("Helvetica-Oblique", 6.5)
    pdf.drawString(
        left,
        y,
        "This is a computer-generated statement. Report any discrepancy within 14 days "
        "to complaints@mybank.com.my",
    )
    y -= 9
    pdf.setFont("Helvetica-Bold", 6.5)
    pdf.setFillColor(colors.HexColor("#8B2333"))
    pdf.drawString(left, y, "SYNTHETIC TEST DOCUMENT - NOT A REAL BANK STATEMENT")

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def demo_statement() -> StatementSpec:
    """The statement used in the 90-Second Challenge.

    Contains the disputed RM2,450.00 TECHWORLD KL debit at 03:02, alongside
    ordinary spending so the extractor has to actually find the right row rather
    than pick the only one present.
    """
    return StatementSpec(
        account_holder="AHMAD BIN ISMAIL",
        account_no="7142556890",
        nric_masked="880412-14-****",
        period_label="01 JUL 2026 - 31 JUL 2026",
        opening_balance_rm=8_420.15,
        lines=(
            StatementLine(date(2026, 7, 3), "DUITNOW TRF - TNB BILL PAYMENT", 187.40),
            StatementLine(date(2026, 7, 5), "SALARY CREDIT - SIME DARBY BHD", 6_200.00, True),
            StatementLine(date(2026, 7, 9), "POS - LOTUS'S KOTA DAMANSARA", 243.85),
            StatementLine(date(2026, 7, 12), "FPX - SHOPEE MALAYSIA", 89.90),
            StatementLine(date(2026, 7, 15), "ATM WDL - CIMB SS2 PJ", 500.00),
            StatementLine(date(2026, 7, 18), "POS 03:02 - TECHWORLD KL", 2_450.00),
            StatementLine(date(2026, 7, 19), "POS - 99 SPEEDMART TTDI", 62.30),
            StatementLine(date(2026, 7, 24), "DUITNOW TRF - MAYBANK CARD PMT", 1_100.00),
            StatementLine(date(2026, 7, 28), "POS - SHELL SEKSYEN 14", 120.00),
        ),
    )


def demo_statement_pdf() -> bytes:
    return render_statement(demo_statement())
