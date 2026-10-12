"""PDF certificate generation using ReportLab (fixed landscape design)."""

import math
import os
import uuid
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CERT_DIR = os.path.join(BASE_DIR, "certificates")
DEFAULT_ORG_NAME = os.environ.get("CERTIBATCH_ORG", "CertiBatch Organization")

# Design colours inspired by the professional certificate template
GOLD = HexColor("#C9A227")
GOLD_DARK = HexColor("#A8841A")
GREY = HexColor("#6B6B6B")
GREY_LIGHT = HexColor("#B0B0B0")
GREY_DARK = HexColor("#4A4A4A")
BORDER_GREY = HexColor("#8A8A8A")

_cert_dir = DEFAULT_CERT_DIR
_org_name = DEFAULT_ORG_NAME


def set_certificate_dir(path):
    """Override certificate output directory (used by tests)."""
    global _cert_dir
    _cert_dir = path


def get_certificate_dir():
    return _cert_dir


def set_org_name(name):
    global _org_name
    _org_name = name


def get_org_name():
    return _org_name


def _ensure_cert_dir():
    os.makedirs(_cert_dir, exist_ok=True)


def _safe_filename(certificate_id):
    """Build a unique filename that does not use raw user input."""
    return f"cert_{certificate_id}_{uuid.uuid4().hex[:8]}.pdf"


def _draw_corner_waves(c, width, height):
    """Draw abstract wavy line patterns in top-left and bottom-right corners."""
    c.setStrokeColor(GREY_LIGHT)
    c.setLineWidth(0.6)

    # Top-left corner waves
    for i in range(12):
        offset = i * 4.5
        path = c.beginPath()
        path.moveTo(15 * mm + offset, height - 8 * mm)
        for x in range(0, 90, 2):
            px = 15 * mm + offset + x * mm * 0.35
            py = height - 8 * mm - offset * 0.4 - 12 * mm * math.sin(x / 12.0)
            path.lineTo(px, py)
        c.drawPath(path, stroke=1, fill=0)

    # Bottom-right corner waves
    for i in range(12):
        offset = i * 4.5
        path = c.beginPath()
        path.moveTo(width - 15 * mm - offset, 8 * mm)
        for x in range(0, 90, 2):
            px = width - 15 * mm - offset - x * mm * 0.35
            py = 8 * mm + offset * 0.4 + 12 * mm * math.sin(x / 12.0)
            path.lineTo(px, py)
        c.drawPath(path, stroke=1, fill=0)


def _draw_diamonds(c, cx, y):
    """Three small diamond outlines under the title."""
    c.setStrokeColor(GREY_LIGHT)
    c.setLineWidth(1)
    size = 4
    for dx in (-14, 0, 14):
        x = cx + dx
        path = c.beginPath()
        path.moveTo(x, y + size)
        path.lineTo(x + size, y)
        path.lineTo(x, y - size)
        path.lineTo(x - size, y)
        path.close()
        c.drawPath(path, stroke=1, fill=0)


def _draw_seal(c, cx, cy, radius=28):
    """Gold circular 'Best Award' style seal at the bottom centre."""
    # Outer ring
    c.setFillColor(GOLD)
    c.circle(cx, cy, radius, stroke=0, fill=1)
    c.setFillColor(GOLD_DARK)
    c.circle(cx, cy, radius - 3, stroke=0, fill=1)
    c.setFillColor(GOLD)
    c.circle(cx, cy, radius - 6, stroke=0, fill=1)

    # Inner highlight ring
    c.setStrokeColor(white)
    c.setLineWidth(1.2)
    c.circle(cx, cy, radius - 8, stroke=1, fill=0)

    # Crown-like mark
    c.setFillColor(GOLD_DARK)
    crown_y = cy + 8
    c.drawCentredString(cx, crown_y, "★")

    c.setFillColor(GREY_DARK)
    c.setFont("Helvetica-Bold", 7)
    c.drawCentredString(cx, cy - 2, "BEST")
    c.drawCentredString(cx, cy - 11, "AWARD")


def _format_display_date(issue_date):
    """Convert YYYY-MM-DD to a readable display string when possible."""
    try:
        parts = issue_date.split("-")
        if len(parts) == 3:
            year, month, day = parts
            months = [
                "",
                "JANUARY",
                "FEBRUARY",
                "MARCH",
                "APRIL",
                "MAY",
                "JUNE",
                "JULY",
                "AUGUST",
                "SEPTEMBER",
                "OCTOBER",
                "NOVEMBER",
                "DECEMBER",
            ]
            m = int(month)
            d = int(day)
            if 1 <= m <= 12:
                return f"{months[m]}, {d} {year}"
    except (ValueError, AttributeError):
        pass
    return str(issue_date).upper()


def generate_certificate(
    recipient_name,
    event_name,
    issue_date,
    certificate_id,
    organization_name=None,
):
    """
    Generate a landscape PDF certificate and return the absolute file path.

    Raises an exception if PDF creation fails.
    """
    _ensure_cert_dir()
    org = organization_name or _org_name
    filename = _safe_filename(certificate_id)
    filepath = os.path.join(_cert_dir, filename)

    page_size = landscape(A4)
    width, height = page_size
    c = canvas.Canvas(filepath, pagesize=page_size)

    # Background
    c.setFillColor(white)
    c.rect(0, 0, width, height, stroke=0, fill=1)

    # Outer grey border band
    margin = 10 * mm
    c.setStrokeColor(BORDER_GREY)
    c.setLineWidth(8)
    c.rect(margin / 2, margin / 2, width - margin, height - margin, stroke=1, fill=0)

    # Inner thin border
    inner = 14 * mm
    c.setStrokeColor(GREY)
    c.setLineWidth(1)
    c.rect(inner, inner, width - 2 * inner, height - 2 * inner, stroke=1, fill=0)

    _draw_corner_waves(c, width, height)

    cx = width / 2

    # Title
    c.setFillColor(GOLD)
    c.setFont("Times-Bold", 36)
    c.drawCentredString(cx, height - 42 * mm, "CERTIFICATE")
    c.setFont("Times-Bold", 18)
    c.drawCentredString(cx, height - 52 * mm, "OF PARTICIPATION")

    _draw_diamonds(c, cx, height - 58 * mm)

    # Presented to
    c.setFillColor(GREY_DARK)
    c.setFont("Helvetica", 10)
    c.drawCentredString(cx, height - 70 * mm, "THIS CERTIFICATE IS PRESENTED TO")

    # Recipient name (script-like via italic serif — ReportLab built-ins only)
    c.setFillColor(GOLD)
    c.setFont("Times-Italic", 32)
    # Shrink font slightly for very long names
    name = recipient_name.strip()
    font_size = 32
    while c.stringWidth(name, "Times-Italic", font_size) > width - 60 * mm and font_size > 16:
        font_size -= 1
    c.setFont("Times-Italic", font_size)
    c.drawCentredString(cx, height - 88 * mm, name)

    # Body text
    c.setFillColor(GREY_DARK)
    c.setFont("Helvetica", 11)
    body_y = height - 105 * mm
    c.drawCentredString(
        cx,
        body_y,
        f"for successfully participating in {event_name}",
    )
    c.drawCentredString(
        cx,
        body_y - 6 * mm,
        f"organized by {org}. Certificate ID: {certificate_id}",
    )

    display_date = _format_display_date(issue_date)

    # Date (bottom left)
    left_x = 55 * mm
    line_y = 38 * mm
    c.setStrokeColor(GREY)
    c.setLineWidth(0.8)
    c.line(left_x - 25 * mm, line_y, left_x + 25 * mm, line_y)
    c.setFillColor(GREY_DARK)
    c.setFont("Helvetica", 9)
    c.drawCentredString(left_x, line_y + 4 * mm, display_date)
    c.setFont("Helvetica", 8)
    c.drawCentredString(left_x, line_y - 5 * mm, "DATE")

    # Signature (bottom right)
    right_x = width - 55 * mm
    c.line(right_x - 25 * mm, line_y, right_x + 25 * mm, line_y)
    c.setFont("Helvetica-Oblique", 11)
    c.setFillColor(GREY)
    c.drawCentredString(right_x, line_y + 4 * mm, org[:28])
    c.setFillColor(GREY_DARK)
    c.setFont("Helvetica", 8)
    c.drawCentredString(right_x, line_y - 5 * mm, "SIGNATURE")

    # Gold seal (centre bottom)
    _draw_seal(c, cx, 40 * mm, radius=22)

    c.save()
    return os.path.abspath(filepath)
