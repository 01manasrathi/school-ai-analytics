from __future__ import annotations

from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, PageBreak


DEMO_PAGES = [
    ("Assessment and feedback", [
        "Fictional demonstration handbook. Not a real school's policy. Applies to all grades unless stated otherwise.",
        "Teachers must return marked assignments within 7 school days of submission. The Assessment Coordinator supports teachers with assessment questions.",
        "The Assessment Coordinator reports to the Principal. Teachers should use the published rubric and give written feedback on one strength and one next step.",
        "For Middle grades, teachers may offer one reassessment after a feedback conference. The Assessment Coordinator approves reassessment requests.",
    ]),
    ("Staff leave and communication", [
        "Fictional demonstration handbook. These procedures are examples only.",
        "Teachers submit planned leave requests to the HR Coordinator at least 5 school days before the requested date. The Principal approves planned leave after checking class coverage.",
        "The HR Coordinator reports to the Principal. Staff must notify the HR Coordinator before 7:30 AM when illness prevents attendance.",
        "Teachers acknowledge parent messages within 2 school days. Confidential student information must not be shared in public group chats.",
    ]),
    ("Clubs, trips and safeguarding", [
        "Fictional demonstration handbook. These procedures are examples only.",
        "The Activities Coordinator approves school clubs. Off-campus trips require written parent consent and approval from the Principal before travel.",
        "The Activities Coordinator reports to the Principal. Teachers submit trip risk assessments to the Activities Coordinator.",
        "Staff report safeguarding concerns to the Designated Safeguarding Lead immediately. Staff record the child's words accurately and do not investigate concerns themselves.",
        "The Designated Safeguarding Lead coordinates safeguarding referrals. This demonstration handbook does not specify emergency telephone numbers.",
    ]),
]


def demo_pdf():
    target = BytesIO()
    styles = getSampleStyleSheet()
    styles["Title"].textColor = colors.HexColor("#16324f")
    story = []
    for index, (heading, paragraphs) in enumerate(DEMO_PAGES):
        if index:
            story.append(PageBreak())
        story.extend([Paragraph("STAFFDESK / FICTIONAL DEMO", styles["Title"]), Spacer(1, 18), Paragraph(heading, styles["Heading1"])])
        for paragraph in paragraphs:
            story.extend([Paragraph(paragraph, styles["BodyText"]), Spacer(1, 15)])
    SimpleDocTemplate(target, pagesize=A4, title="StaffDesk Fictional Demo Handbook", author="StaffDesk demo").build(story)
    return target.getvalue()


def diagram_pdf():
    from reportlab.pdfgen import canvas
    target = BytesIO()
    page = canvas.Canvas(target, pagesize=A4)
    page.setFont("Helvetica-Bold", 18)
    page.drawString(50, 790, "FICTIONAL DEMO: Staff reporting chart")
    for x, y, label in [(205, 660, "Principal"), (65, 500, "HR Coordinator"), (330, 500, "Assessment Coordinator")]:
        page.roundRect(x - 10, y - 25, 210, 60, 8)
        page.setFont("Helvetica", 13)
        page.drawString(x, y, label)
    page.line(155, 535, 290, 635)
    page.line(420, 535, 300, 635)
    page.setFont("Helvetica", 11)
    page.drawString(85, 595, "reports to")
    page.drawString(390, 595, "reports to")
    page.drawString(50, 400, "Diagram for software verification only; not a real school policy.")
    page.save()
    return target.getvalue()
