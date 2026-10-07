from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

OUTPUT_DIR = Path("output")


def _fit_font_size(text: str, font: str, max_size: int, max_width: float) -> int:
    """Shrink the font until the text fits inside max_width."""
    size = max_size
    while size > 12 and stringWidth(text, font, size) > max_width:
        size -= 2
    return size


def generate_certificate_pdf(
    *,
    certificate_id: str,
    job_id: str,
    recipient_name: str,
    achievement: str,
    event_name: str,
    issued_by: str,
    issued_on: str,
) -> str:
    """Render ONE certificate from the single predefined template. Returns the file path."""
    folder = OUTPUT_DIR / job_id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{certificate_id}.pdf"

    width, height = landscape(A4)
    c = canvas.Canvas(str(path), pagesize=(width, height))
    cx = width / 2

    # Border (double line)
    c.setStrokeColor(HexColor("#1F3864"))
    c.setLineWidth(6)
    c.rect(25, 25, width - 50, height - 50)
    c.setLineWidth(1.5)
    c.rect(38, 38, width - 76, height - 76)

    # Title
    c.setFillColor(HexColor("#1F3864"))
    c.setFont("Helvetica-Bold", 38)
    c.drawCentredString(cx, height - 130, "CERTIFICATE")
    c.setFont("Helvetica", 16)
    c.drawCentredString(cx, height - 160, "OF ACHIEVEMENT")

    # Body
    c.setFillColor(HexColor("#333333"))
    c.setFont("Helvetica", 15)
    c.drawCentredString(cx, height - 215, "This is proudly presented to")

    name_size = _fit_font_size(recipient_name, "Helvetica-Bold", 34, width - 160)
    c.setFont("Helvetica-Bold", name_size)
    c.setFillColor(HexColor("#2E5597"))
    c.drawCentredString(cx, height - 265, recipient_name)

    c.setStrokeColor(HexColor("#999999"))
    c.setLineWidth(0.8)
    c.line(cx - 200, height - 278, cx + 200, height - 278)

    c.setFillColor(HexColor("#333333"))
    c.setFont("Helvetica", 15)
    c.drawCentredString(cx, height - 315, "for")
    ach_size = _fit_font_size(achievement, "Helvetica-Bold", 22, width - 160)
    c.setFont("Helvetica-Bold", ach_size)
    c.drawCentredString(cx, height - 345, achievement)

    ev_size = _fit_font_size(event_name, "Helvetica", 16, width - 160)
    c.setFont("Helvetica", ev_size)
    c.drawCentredString(cx, height - 380, f"at {event_name}")

    # Footer
    c.setFont("Helvetica", 12)
    c.drawString(80, 85, f"Issued by: {issued_by}")
    c.drawRightString(width - 80, 85, f"Date: {issued_on}")
    c.setFont("Helvetica", 9)
    c.setFillColor(HexColor("#888888"))
    c.drawCentredString(cx, 55, f"Certificate ID: {certificate_id}")

    c.save()
    return str(path)