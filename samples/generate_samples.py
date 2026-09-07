"""Render the sample referral documents from :mod:`scenarios`.

    python -m pip install reportlab pillow
    python samples/generate_samples.py

Each Box 1 intake channel is rendered differently on purpose, because the
point of the corpus is to exercise different parts of the pipeline:

===========================  ==========================  =======================
Channel                      Output                      Exercises
===========================  ==========================  =======================
Referral Portals             clean digital PDF           baseline extraction
Fax Systems                  200 dpi bitonal PNG         OCR under degradation
Email Attachments            digital PDF + header block  transport vs. content
Scanned Patient Documents    300 dpi PNG, handwritten    handwriting recognition
Provider Referral Packets    multi-page PDF              classification/splitting
External Healthcare Partners digital PDF, table layout   layout generalisation
===========================  ==========================  =======================

Writing ``manifest.json`` alongside the documents lets the diagnostics tool
score extraction accuracy against known ground truth.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

from scenarios import SCENARIOS, Scenario, expected_fields

OUT_DIR = Path(__file__).parent
FONT_DIR = OUT_DIR / "fonts"
HANDWRITING = FONT_DIR / "Caveat.ttf"

# Deterministic output: regenerating must not produce a noisy git diff.
SEED = 20300101

_SANS_CANDIDATES = (
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
)
_SANS_BOLD_CANDIDATES = (
    "C:/Windows/Fonts/arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
)


def _pil_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for path in _SANS_BOLD_CANDIDATES if bold else _SANS_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    raise RuntimeError(
        "No scalable sans-serif font found. Install DejaVu or Liberation fonts."
    )


def _hand_font(size: int) -> ImageFont.FreeTypeFont:
    if not HANDWRITING.exists():
        raise RuntimeError(f"Missing handwriting font at {HANDWRITING}.")
    return ImageFont.truetype(str(HANDWRITING), size)


# --------------------------------------------------------------------------
# PDF helpers
# --------------------------------------------------------------------------


def _labelled(c: canvas.Canvas, x: float, y: float, label: str, value: str,
              gap: float = 1.75 * inch, size: int = 10) -> float:
    c.setFont("Helvetica-Bold", size)
    c.drawString(x, y, label)
    c.setFont("Helvetica", size)
    c.drawString(x + gap, y, value)
    return y - 0.23 * inch


def _wrapped(c: canvas.Canvas, x: float, y: float, text: str, width: float,
             size: int = 10, leading: float = 0.19 * inch) -> float:
    c.setFont("Helvetica", size)
    line = ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if c.stringWidth(trial, "Helvetica", size) > width and line:
            c.drawString(x, y, line)
            y -= leading
            line = word
        else:
            line = trial
    if line:
        c.drawString(x, y, line)
        y -= leading
    return y


def _rule(c: canvas.Canvas, x1: float, y: float, x2: float, weight: float = 0.6) -> None:
    c.setStrokeColor(colors.HexColor("#9aa2b1"))
    c.setLineWidth(weight)
    c.line(x1, y, x2, y)
    c.setStrokeColor(colors.black)


def _footer(c: canvas.Canvas, text: str) -> None:
    c.setFont("Helvetica-Oblique", 7.5)
    c.setFillColor(colors.HexColor("#6b7280"))
    c.drawString(1 * inch, 0.6 * inch, text)
    c.setFillColor(colors.black)


# --------------------------------------------------------------------------
# Channel 1: Referral Portals - clean, machine generated, easy baseline
# --------------------------------------------------------------------------


def render_portal_pdf(scenario: Scenario, path: Path) -> None:
    c = canvas.Canvas(str(path), pagesize=LETTER)
    width, height = LETTER

    c.setFillColor(colors.HexColor("#1f3a93"))
    c.rect(0, height - 0.9 * inch, width, 0.9 * inch, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 17)
    c.drawString(1 * inch, height - 0.55 * inch, "HomeCare Connect Referral Portal")
    c.setFont("Helvetica", 9.5)
    c.drawString(1 * inch, height - 0.75 * inch, "Electronic referral submission receipt")
    c.setFillColor(colors.black)

    y = height - 1.35 * inch
    c.setFont("Helvetica-Bold", 11)
    c.drawString(1 * inch, y, f"Confirmation {scenario.authorization_number}")
    c.setFont("Helvetica", 9)
    c.drawRightString(width - 1 * inch, y, f"Submitted {scenario.requested_date}")
    y -= 0.15 * inch
    _rule(c, 1 * inch, y, width - 1 * inch)
    y -= 0.3 * inch

    c.setFont("Helvetica-Bold", 11)
    c.drawString(1 * inch, y, "Patient")
    y -= 0.26 * inch
    y = _labelled(c, 1 * inch, y, "Patient name", scenario.patient_name)
    y = _labelled(c, 1 * inch, y, "Date of birth", scenario.date_of_birth)
    y = _labelled(c, 1 * inch, y, "Medical record number", scenario.mrn)
    y = _labelled(c, 1 * inch, y, "Home address", scenario.address)
    y = _labelled(c, 1 * inch, y, "Contact phone", scenario.phone)

    y -= 0.16 * inch
    c.setFont("Helvetica-Bold", 11)
    c.drawString(1 * inch, y, "Referring provider")
    y -= 0.26 * inch
    y = _labelled(c, 1 * inch, y, "Provider", scenario.referring_provider)
    y = _labelled(c, 1 * inch, y, "Organization", scenario.provider_org)
    y = _labelled(c, 1 * inch, y, "NPI", scenario.provider_npi)
    y = _labelled(c, 1 * inch, y, "Phone", scenario.provider_phone)

    y -= 0.16 * inch
    c.setFont("Helvetica-Bold", 11)
    c.drawString(1 * inch, y, "Referral")
    y -= 0.26 * inch
    y = _labelled(c, 1 * inch, y, "Requested service", scenario.requested_service)
    y = _labelled(c, 1 * inch, y, "Priority", scenario.priority)
    y = _labelled(c, 1 * inch, y, "Primary diagnosis", scenario.primary_diagnosis)
    y = _labelled(c, 1 * inch, y, "ICD-10 code", scenario.diagnosis_code)
    y = _labelled(c, 1 * inch, y, "Requested start of care", scenario.requested_date)
    y = _labelled(c, 1 * inch, y, "Payer", scenario.payer)
    y = _labelled(c, 1 * inch, y, "Member ID", scenario.member_id)
    y = _labelled(c, 1 * inch, y, "Authorization", scenario.authorization_number)

    y -= 0.16 * inch
    c.setFont("Helvetica-Bold", 11)
    c.drawString(1 * inch, y, "Clinical summary")
    y -= 0.24 * inch
    _wrapped(c, 1 * inch, y, scenario.clinical_note, width - 2 * inch)

    _footer(c, "HomeCare Connect portal submission receipt. Fabricated record for workshop use.")
    c.save()


# --------------------------------------------------------------------------
# Channel 3: Email Attachments - content wrapped in transport metadata
# --------------------------------------------------------------------------


def render_email_pdf(scenario: Scenario, path: Path) -> None:
    c = canvas.Canvas(str(path), pagesize=LETTER)
    width, height = LETTER

    y = height - 0.9 * inch
    c.setFont("Helvetica-Bold", 13)
    c.drawString(1 * inch, y, "Fwd: Home health referral")
    y -= 0.3 * inch

    c.setFillColor(colors.HexColor("#f1f3f7"))
    c.rect(1 * inch, y - 1.02 * inch, width - 2 * inch, 1.14 * inch, fill=1, stroke=0)
    c.setFillColor(colors.black)
    y -= 0.06 * inch
    domain = scenario.provider_org.split()[0].lower()
    for label, value in (
        ("From", f"referrals@{domain}.example.org"),
        ("To", "intake@homecare.example.com"),
        ("Cc", "care.coordination@homecare.example.com"),
        ("Subject", f"Referral - {scenario.patient_name} - {scenario.requested_service}"),
        ("Attachments", "referral.pdf, face-sheet.pdf"),
    ):
        c.setFont("Helvetica-Bold", 8.5)
        c.drawString(1.12 * inch, y, f"{label}:")
        c.setFont("Helvetica", 8.5)
        c.drawString(1.85 * inch, y, value)
        y -= 0.19 * inch

    y -= 0.22 * inch
    y = _wrapped(
        c, 1 * inch, y,
        f"Hi team, please see the attached referral for {scenario.patient_name}. "
        f"{scenario.provider_org} is requesting {scenario.requested_service.lower()}. "
        "Let me know if anything else is needed. Thanks.",
        width - 2 * inch, size=9.5,
    )
    y -= 0.18 * inch
    _rule(c, 1 * inch, y, width - 1 * inch)
    y -= 0.34 * inch

    c.setFont("Helvetica-Bold", 12)
    c.drawString(1 * inch, y, "HOME HEALTH REFERRAL")
    y -= 0.3 * inch
    y = _labelled(c, 1 * inch, y, "Patient name", scenario.patient_name)
    y = _labelled(c, 1 * inch, y, "Date of birth", scenario.date_of_birth)
    y = _labelled(c, 1 * inch, y, "MRN", scenario.mrn)
    y = _labelled(c, 1 * inch, y, "Referring provider", scenario.referring_provider)
    y = _labelled(c, 1 * inch, y, "NPI", scenario.provider_npi)
    y = _labelled(c, 1 * inch, y, "Requested service", scenario.requested_service)
    y = _labelled(c, 1 * inch, y, "Priority", scenario.priority)
    y = _labelled(c, 1 * inch, y, "Primary diagnosis", scenario.primary_diagnosis)
    y = _labelled(c, 1 * inch, y, "ICD-10", scenario.diagnosis_code)
    y = _labelled(c, 1 * inch, y, "Payer", scenario.payer)
    y = _labelled(c, 1 * inch, y, "Authorization", scenario.authorization_number)
    y = _labelled(c, 1 * inch, y, "Requested start of care", scenario.requested_date)

    y -= 0.16 * inch
    c.setFont("Helvetica-Bold", 10)
    c.drawString(1 * inch, y, "Clinical notes")
    y -= 0.22 * inch
    _wrapped(c, 1 * inch, y, scenario.clinical_note, width - 2 * inch, size=9.5)

    _footer(c, "Referral received as an email attachment. Fabricated record for workshop use.")
    c.save()


# --------------------------------------------------------------------------
# Channel 5: Provider Referral Packets - multi page, mixed document types
# --------------------------------------------------------------------------


def render_packet_pdf(scenario: Scenario, path: Path) -> None:
    c = canvas.Canvas(str(path), pagesize=LETTER)
    width, height = LETTER

    def header(title: str, page_label: str) -> float:
        c.setFont("Helvetica-Bold", 12)
        c.drawString(1 * inch, height - 0.85 * inch, scenario.provider_org.upper())
        c.setFont("Helvetica", 9)
        c.drawRightString(width - 1 * inch, height - 0.85 * inch, page_label)
        _rule(c, 1 * inch, height - 0.95 * inch, width - 1 * inch, weight=1.1)
        c.setFont("Helvetica-Bold", 13)
        c.drawString(1 * inch, height - 1.28 * inch, title)
        return height - 1.62 * inch

    # Page 1 - face sheet
    y = header("PATIENT FACE SHEET", "Page 1 of 4")
    y = _labelled(c, 1 * inch, y, "Patient name", scenario.patient_name)
    y = _labelled(c, 1 * inch, y, "Date of birth", scenario.date_of_birth)
    y = _labelled(c, 1 * inch, y, "Medical record number", scenario.mrn)
    y = _labelled(c, 1 * inch, y, "Address", scenario.address)
    y = _labelled(c, 1 * inch, y, "Phone", scenario.phone)
    y -= 0.2 * inch
    y = _labelled(c, 1 * inch, y, "Payer", scenario.payer)
    y = _labelled(c, 1 * inch, y, "Member ID", scenario.member_id)
    y = _labelled(c, 1 * inch, y, "Authorization", scenario.authorization_number)
    y -= 0.2 * inch
    y = _labelled(c, 1 * inch, y, "Referring provider", scenario.referring_provider)
    y = _labelled(c, 1 * inch, y, "NPI", scenario.provider_npi)
    y = _labelled(c, 1 * inch, y, "Provider phone", scenario.provider_phone)
    y = _labelled(c, 1 * inch, y, "Provider fax", scenario.provider_fax)
    _footer(c, "Face sheet. Fabricated record for workshop use.")
    c.showPage()

    # Page 2 - history and physical
    y = header("HISTORY AND PHYSICAL", "Page 2 of 4")
    y = _labelled(c, 1 * inch, y, "Primary diagnosis", scenario.primary_diagnosis)
    y = _labelled(c, 1 * inch, y, "ICD-10 code", scenario.diagnosis_code)
    y -= 0.12 * inch
    c.setFont("Helvetica-Bold", 10)
    c.drawString(1 * inch, y, "Secondary diagnoses")
    y -= 0.22 * inch
    c.setFont("Helvetica", 10)
    for item in scenario.secondary_diagnoses:
        c.drawString(1.2 * inch, y, f"- {item}")
        y -= 0.2 * inch
    y -= 0.12 * inch
    c.setFont("Helvetica-Bold", 10)
    c.drawString(1 * inch, y, "Narrative")
    y -= 0.22 * inch
    _wrapped(c, 1 * inch, y, scenario.clinical_note, width - 2 * inch)
    _footer(c, "History and physical. Fabricated record for workshop use.")
    c.showPage()

    # Page 3 - medication list
    y = header("MEDICATION LIST", "Page 3 of 4")
    c.setFont("Helvetica-Bold", 9.5)
    c.drawString(1 * inch, y, "Medication")
    c.drawString(4.6 * inch, y, "Route / frequency")
    y -= 0.08 * inch
    _rule(c, 1 * inch, y, width - 1 * inch)
    y -= 0.24 * inch
    for medication in scenario.medications:
        name, _, rest = medication.partition(" PO ")
        c.setFont("Helvetica", 9.5)
        c.drawString(1 * inch, y, name)
        c.drawString(4.6 * inch, y, f"PO {rest}" if rest else "See order")
        y -= 0.22 * inch
    _footer(c, "Medication list. Fabricated record for workshop use.")
    c.showPage()

    # Page 4 - signed order
    y = header("HOME HEALTH ORDER", "Page 4 of 4")
    y = _labelled(c, 1 * inch, y, "Requested service", scenario.requested_service)
    y = _labelled(c, 1 * inch, y, "Priority", scenario.priority)
    y = _labelled(c, 1 * inch, y, "Requested start of care", scenario.requested_date)
    y -= 0.2 * inch
    y = _wrapped(
        c, 1 * inch, y,
        f"I certify that {scenario.patient_name} is under my care and requires "
        f"{scenario.requested_service.lower()} in the home setting for "
        f"{scenario.primary_diagnosis.lower()}.",
        width - 2 * inch,
    )
    y -= 0.6 * inch
    _rule(c, 1 * inch, y, 4 * inch)
    c.setFont("Helvetica-Oblique", 13)
    c.drawString(1.1 * inch, y + 0.1 * inch, scenario.referring_provider)
    c.setFont("Helvetica", 8.5)
    c.drawString(1 * inch, y - 0.18 * inch,
                 f"{scenario.referring_provider}  NPI {scenario.provider_npi}")
    c.drawString(1 * inch, y - 0.36 * inch, f"Signed {scenario.requested_date}")
    _footer(c, "Signed order. Fabricated record for workshop use.")
    c.save()


# --------------------------------------------------------------------------
# Channel 6: External Healthcare Partners - a partner EMR export
# --------------------------------------------------------------------------


def render_partner_pdf(scenario: Scenario, path: Path) -> None:
    c = canvas.Canvas(str(path), pagesize=LETTER)
    width, height = LETTER

    c.setFont("Courier-Bold", 12)
    c.drawString(1 * inch, height - 0.9 * inch, scenario.provider_org.upper())
    c.setFont("Courier", 8.5)
    c.drawString(1 * inch, height - 1.08 * inch,
                 "INTEROPERABILITY EXPORT / REFERRAL TRANSACTION")
    c.drawRightString(width - 1 * inch, height - 1.08 * inch, f"EXPORT {scenario.requested_date}")
    _rule(c, 1 * inch, height - 1.2 * inch, width - 1 * inch, weight=1.2)

    rows = (
        ("PID.5", "PATIENT NAME", scenario.patient_name),
        ("PID.7", "DATE OF BIRTH", scenario.date_of_birth),
        ("PID.3", "MEDICAL RECORD NUMBER", scenario.mrn),
        ("PID.11", "ADDRESS", scenario.address),
        ("PID.13", "HOME PHONE", scenario.phone),
        ("PRD.1", "REFERRING PROVIDER", scenario.referring_provider),
        ("PRD.7", "PROVIDER NPI", scenario.provider_npi),
        ("PRD.3", "PROVIDER ORGANIZATION", scenario.provider_org),
        ("RF1.1", "REFERRAL PRIORITY", scenario.priority.upper()),
        ("RF1.3", "REQUESTED SERVICE", scenario.requested_service),
        ("DG1.3", "PRIMARY DIAGNOSIS", scenario.primary_diagnosis),
        ("DG1.1", "DIAGNOSIS CODE (ICD-10)", scenario.diagnosis_code),
        ("IN1.4", "PAYER", scenario.payer),
        ("IN1.49", "MEMBER ID", scenario.member_id),
        ("RF1.6", "AUTHORIZATION NUMBER", scenario.authorization_number),
        ("RF1.7", "REQUESTED START OF CARE", scenario.requested_date),
    )

    y = height - 1.5 * inch
    c.setFont("Courier-Bold", 8)
    c.drawString(1 * inch, y, "SEGMENT")
    c.drawString(1.85 * inch, y, "ELEMENT")
    c.drawString(4.15 * inch, y, "VALUE")
    y -= 0.1 * inch
    _rule(c, 1 * inch, y, width - 1 * inch)
    y -= 0.22 * inch

    for index, (segment, label, value) in enumerate(rows):
        if index % 2 == 0:
            c.setFillColor(colors.HexColor("#f4f5f8"))
            c.rect(1 * inch, y - 0.06 * inch, width - 2 * inch, 0.2 * inch, fill=1, stroke=0)
            c.setFillColor(colors.black)
        c.setFont("Courier", 8)
        c.drawString(1 * inch, y, segment)
        c.drawString(1.85 * inch, y, label)
        c.setFont("Courier-Bold", 8)
        c.drawString(4.15 * inch, y, value if len(value) <= 48 else value[:45] + "...")
        y -= 0.21 * inch

    y -= 0.18 * inch
    c.setFont("Courier-Bold", 8)
    c.drawString(1 * inch, y, "NTE.3  CLINICAL NARRATIVE")
    y -= 0.2 * inch
    c.setFont("Courier", 8)
    line = ""
    for word in scenario.clinical_note.split():
        trial = f"{line} {word}".strip()
        if c.stringWidth(trial, "Courier", 8) > width - 2.2 * inch and line:
            c.drawString(1.1 * inch, y, line)
            y -= 0.17 * inch
            line = word
        else:
            line = trial
    if line:
        c.drawString(1.1 * inch, y, line)

    _footer(c, "Partner network export. Fabricated record for workshop use.")
    c.save()


# --------------------------------------------------------------------------
# Image degradation shared by the fax and scan channels
# --------------------------------------------------------------------------


def _degrade(image: Image.Image, *, rotation: float, noise: float,
             blur: float, bitonal: bool, rng: random.Random,
             final_width: int) -> Image.Image:
    """Make a crisp render look like it went through real hardware."""
    image = image.rotate(rotation, resample=Image.BICUBIC, expand=False, fillcolor="white")
    if blur:
        image = image.filter(ImageFilter.GaussianBlur(blur))

    ratio = final_width / image.width
    image = image.resize((final_width, int(image.height * ratio)), Image.LANCZOS)
    image = image.convert("L")

    pixels = image.load()
    width, height = image.size
    for _ in range(int(width * height * noise)):
        x, y = rng.randrange(width), rng.randrange(height)
        pixels[x, y] = rng.choice((0, 255))

    if bitonal:
        # Horizontal scanner streaks, then a hard threshold like a fax machine.
        for _ in range(rng.randint(2, 5)):
            row = rng.randrange(height)
            shade = rng.randint(140, 210)
            for x in range(width):
                if pixels[x, row] > shade:
                    pixels[x, row] = shade
        image = image.point(lambda value: 0 if value < 138 else 255, mode="1")
    return image


def _draw_rows(draw: ImageDraw.ImageDraw, x: int, y: int, rows, label_font,
               value_font, gap: int, step: int) -> int:
    for label, value in rows:
        draw.text((x, y), label, font=label_font, fill="black")
        draw.text((x + gap, y), value, font=value_font, fill="black")
        y += step
    return y


def _wrap_image_text(draw: ImageDraw.ImageDraw, x: int, y: int, text: str,
                     font, max_width: int, step: int) -> int:
    line = ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) > max_width and line:
            draw.text((x, y), line, font=font, fill="black")
            y += step
            line = word
        else:
            line = trial
    if line:
        draw.text((x, y), line, font=font, fill="black")
        y += step
    return y


# --------------------------------------------------------------------------
# Channel 2: Fax Systems - degraded bitonal transmission
# --------------------------------------------------------------------------


def render_fax_png(scenario: Scenario, path: Path) -> None:
    rng = random.Random(SEED + 2)
    # Render large, then degrade down to a 200 dpi bitonal page.
    width, height = 2550, 3300
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)

    title = _pil_font(64, bold=True)
    head = _pil_font(40, bold=True)
    label = _pil_font(34, bold=True)
    value = _pil_font(34)
    small = _pil_font(26)

    draw.text((170, 150), "FAX TRANSMISSION", font=title, fill="black")
    draw.line([(170, 240), (width - 170, 240)], fill="black", width=5)

    y = _draw_rows(draw, 170, 290, (
        ("TO:", "HomeCare Intake  (555) 555-0100"),
        ("FROM:", f"{scenario.provider_org}  {scenario.provider_fax}"),
        ("DATE:", scenario.requested_date),
        ("PAGES:", "1"),
        ("RE:", f"Home health referral - {scenario.requested_service}"),
    ), label, value, 380, 62)

    y += 30
    draw.line([(170, y), (width - 170, y)], fill="black", width=3)
    y += 60

    draw.text((170, y), "HOME HEALTH REFERRAL", font=head, fill="black")
    y += 80

    y = _draw_rows(draw, 170, y, (
        ("Patient:", scenario.patient_name),
        ("DOB:", scenario.date_of_birth),
        ("MRN:", scenario.mrn),
        ("Phone:", scenario.phone),
        ("Provider:", scenario.referring_provider),
        ("NPI:", scenario.provider_npi),
        ("Priority:", scenario.priority.upper()),
        ("Service:", scenario.requested_service),
        ("Diagnosis:", scenario.primary_diagnosis),
        ("ICD-10:", scenario.diagnosis_code),
        ("Payer:", scenario.payer),
        ("Member ID:", scenario.member_id),
        ("Auth #:", scenario.authorization_number),
        ("Start of care:", scenario.requested_date),
    ), label, value, 480, 62)

    y += 40
    draw.text((170, y), "CLINICAL NOTES", font=label, fill="black")
    y += 55
    _wrap_image_text(draw, 170, y, scenario.clinical_note, small, width - 400, 44)

    draw.text((170, height - 220), "Confidential fax. Fabricated record for workshop use.",
              font=small, fill="black")

    # 8.5in at 200 dpi = 1700 px.
    _degrade(image, rotation=0.8, noise=0.0016, blur=0.9, bitonal=True,
             rng=rng, final_width=1700).save(path, optimize=True)


# --------------------------------------------------------------------------
# Channel 4: Scanned Patient Documents - handwritten intake form
# --------------------------------------------------------------------------


def render_scanned_png(scenario: Scenario, path: Path) -> None:
    rng = random.Random(SEED + 4)
    width, height = 2550, 3300
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)

    title = _pil_font(58, bold=True)
    label = _pil_font(32, bold=True)
    small = _pil_font(24)
    hand = _hand_font(52)
    ink = (18, 22, 74)

    draw.text((170, 150), "HOME HEALTH INTAKE FORM", font=title, fill="black")
    draw.text((170, 225), f"{scenario.provider_org}   Fax {scenario.provider_fax}",
              font=small, fill="black")
    draw.rectangle([(150, 300), (width - 150, height - 260)], outline="black", width=4)

    def handwritten(x: int, y: int, text: str) -> None:
        """Ink wanders: jitter each word so it does not look typeset."""
        cursor = x
        for word in text.split():
            draw.text((cursor, y + rng.randint(-7, 7)), word, font=hand, fill=ink)
            cursor += int(draw.textlength(word + " ", font=hand))

    y = 380
    for field_label, written in (
        ("Patient name", scenario.patient_name),
        ("Date of birth", scenario.date_of_birth),
        ("MRN", scenario.mrn),
        ("Home phone", scenario.phone),
        ("Referring provider", scenario.referring_provider),
        ("Provider NPI", scenario.provider_npi),
        ("Requested service", scenario.requested_service),
        ("Primary diagnosis", scenario.primary_diagnosis),
        ("ICD-10 code", scenario.diagnosis_code),
        ("Payer", scenario.payer),
        ("Authorization #", scenario.authorization_number),
        ("Start of care", scenario.requested_date),
    ):
        draw.text((210, y), f"{field_label}:", font=label, fill="black")
        draw.line([(760, y + 52), (width - 220, y + 52)], fill="black", width=3)
        handwritten(790, y - 8, written)
        y += 100

    y += 20
    draw.text((210, y), "Priority (check one):", font=label, fill="black")
    box_x = 830
    for option in ("Routine", "Urgent", "STAT"):
        draw.rectangle([(box_x, y), (box_x + 40, y + 40)], outline="black", width=4)
        if option == scenario.priority:
            # A hand-drawn check, not a glyph.
            draw.line([(box_x + 8, y + 22), (box_x + 18, y + 33)], fill=ink, width=6)
            draw.line([(box_x + 18, y + 33), (box_x + 34, y + 6)], fill=ink, width=6)
        draw.text((box_x + 55, y + 2), option, font=label, fill="black")
        box_x += 330

    y += 110
    draw.text((210, y), "Notes:", font=label, fill="black")
    y += 60
    y = _wrap_image_text(draw, 250, y, scenario.clinical_note, small, width - 500, 40)

    y += 70
    draw.text((210, y), "Signature:", font=label, fill="black")
    draw.line([(560, y + 60), (1700, y + 60)], fill="black", width=3)
    draw.text((600, y - 10), scenario.referring_provider, font=_hand_font(64), fill=ink)

    draw.text((210, height - 200), "Fabricated record for workshop use.", font=small, fill="black")

    # Keep 300 dpi width so handwriting stays legible, but add scan artefacts.
    _degrade(image, rotation=-0.5, noise=0.0009, blur=0.6, bitonal=False,
             rng=rng, final_width=2550).save(path, optimize=True)


# --------------------------------------------------------------------------
# Manifest
# --------------------------------------------------------------------------

RENDERERS = {
    "portal-chf": ("referral-portal-submission.pdf", render_portal_pdf),
    "fax-wound": ("fax-referral-transmission.png", render_fax_png),
    "email-ortho": ("email-attachment-referral.pdf", render_email_pdf),
    "scan-copd": ("scanned-intake-form.png", render_scanned_png),
    "packet-stroke": ("provider-referral-packet.pdf", render_packet_pdf),
    "partner-hospice": ("partner-network-referral.pdf", render_partner_pdf),
}


def main() -> None:
    documents = []
    for scenario in SCENARIOS:
        filename, renderer = RENDERERS[scenario.key]
        target = OUT_DIR / filename
        renderer(scenario, target)
        documents.append(
            {
                "file": filename,
                "channel": scenario.channel,
                "scenario": scenario.key,
                "difficulty": (
                    "hard" if scenario.ambiguous_fields
                    else "medium" if target.suffix == ".png"
                    else "easy"
                ),
                "expected": expected_fields(scenario),
                "reviewerMustConfirm": list(scenario.ambiguous_fields),
                "notes": scenario.notes,
            }
        )
        print(f"wrote {filename} ({target.stat().st_size // 1024} KB)")

    payload = json.dumps(
        {
            "description": (
                "Ground truth for the sample referral corpus. Every record is "
                "fabricated; identifiers use ranges reserved for fiction."
            ),
            "documents": documents,
        },
        indent=2,
    ) + "\n"

    (OUT_DIR / "manifest.json").write_text(payload, encoding="utf-8")
    print(f"wrote manifest.json ({len(documents)} documents)")


if __name__ == "__main__":
    main()
