from __future__ import annotations

import argparse
import json
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

FILENAME = "Maple_Grove_School_Sample_Policies_10_Pages.pdf"
PAGES = [
    ("Governance, scope and school day", [
        ("POL-01 / Scope", "Maple Grove Demonstration School is fictional. This handbook is a software test fixture, not legal advice or an approved real-school policy. Version 1.0 applies to Primary, Middle and Secondary grades. All dates, procedures and roles are invented for testing."),
        ("School hours", "The school day starts at 8:15 AM and ends at 3:10 PM. The main office opens at 7:45 AM. Students must remain with a supervising adult until collection; they must not leave campus during the school day without office authorization."),
        ("Policy ownership", "The Principal approves school policies. The School Office maintains the current handbook and records policy revisions. Staff consult the named policy owner when a procedure is unclear rather than inventing exceptions."),
        ("Reporting structure", "The HR Coordinator reports to the Principal. The Assessment Coordinator reports to the Principal. The Activities Coordinator reports to the Principal. The IT Coordinator reports to the Principal. The School Nurse reports to the Principal."),
        ("Document boundaries", "The handbook does not specify salary amounts, tuition fees, a cafeteria menu, emergency telephone numbers or statutory retention periods. Questions on those subjects cannot be answered from this PDF. Policy review takes place each January."),
    ]),
    ("Student attendance, punctuality and collection", [
        ("POL-02 / Attendance owner", "The Attendance Officer manages student attendance records and reports to the Principal. The School Office records authorized changes to collection arrangements."),
        ("Morning register", "Teachers submit the morning attendance register by 8:30 AM each school day. A student arriving after 8:30 AM signs in at the School Office before going to class. The office records the arrival time; teachers must not alter it to hide lateness."),
        ("Reporting student absence", "Parents report a student's absence to the Attendance Officer by 8:45 AM. The report includes the student's name, class and reason for absence. The Attendance Officer follows up on unexplained absences by 9:15 AM."),
        ("Repeated absence", "After 3 unexplained absences within 20 school days, the Attendance Officer arranges a meeting with the family and class teacher. The meeting identifies support needs and documents an attendance improvement plan; it is not an automatic punishment."),
        ("Early collection", "Only an adult named in the authorized collection record may collect a student early. The School Office checks identification and records the departure time. A change in collection adult must be confirmed with the registered parent before release."),
    ]),
    ("Assessment, marking and homework", [
        ("POL-03 / Assessment owner", "The Assessment Coordinator oversees assessment procedures and reports to the Principal. Teachers explain success criteria before issuing assessed work and use the published rubric consistently."),
        ("Marking turnaround", "Teachers return marked assignments within 7 school days of submission. Written feedback identifies one strength and one improvement step. A delayed return must be explained to the Assessment Coordinator, with a revised date shared with the class."),
        ("Homework planning", "Primary homework should take no more than 20 minutes per school day. Middle homework should take no more than 40 minutes per school day. Secondary homework should take no more than 60 minutes per school day. Teachers coordinate deadlines to avoid unnecessary clustering."),
        ("Reassessment", "Middle and Secondary students may request one reassessment within 5 school days of receiving feedback. The Assessment Coordinator approves reassessment after a feedback conference. Primary students receive a supported practice task instead of a formal reassessment."),
        ("Academic integrity", "Teachers discuss suspected plagiarism privately with the student and retain the relevant work. The Assessment Coordinator reviews evidence before deciding a proportionate response. An allegation alone must not be recorded as a confirmed finding."),
    ]),
    ("Staff leave, absence and cover", [
        ("POL-04 / HR owner", "The HR Coordinator manages staff leave records and reports to the Principal. This policy covers staff absence, not student absence; student absence is addressed on page 2."),
        ("Planned leave", "Staff submit planned leave requests to the HR Coordinator at least 5 school days before the requested date. The Principal approves planned leave after checking class coverage. Submission of a request does not by itself authorize leave."),
        ("Illness notification", "Staff who cannot attend because of illness notify the HR Coordinator before 7:30 AM on the day of absence. Staff provide the expected duration if known. Medical details are shared only with authorized personnel who need them."),
        ("Cover arrangements", "The HR Coordinator assigns cover and informs affected teachers. Teachers upload lesson materials and class routines to the approved staff workspace before planned leave begins. Cover staff receive necessary learning and safety information, not unrelated personal records."),
        ("Return to work", "After 3 consecutive school days of sickness absence, the HR Coordinator schedules a return-to-work conversation on the first day back. The conversation checks support needs and updates the absence record. This handbook does not define pay rates or sick-pay entitlement."),
    ]),
    ("Safeguarding and visitor access", [
        ("POL-05 / Safeguarding owner", "The Designated Safeguarding Lead coordinates safeguarding procedures and reports to the Principal. This fictional handbook is not an emergency service and does not supply emergency telephone numbers."),
        ("Reporting a concern", "Staff report safeguarding concerns to the Designated Safeguarding Lead immediately. Staff record the student's own words accurately, including the date and time, and do not investigate the concern themselves. They do not promise absolute confidentiality."),
        ("Unavailable lead", "If the Designated Safeguarding Lead is unavailable, staff contact the Deputy Safeguarding Lead. If both leads are unavailable, staff contact the Principal without delaying the report. The Deputy Safeguarding Lead reports to the Designated Safeguarding Lead."),
        ("Visitor sign-in", "All visitors sign in at the School Office, show identification and wear a visitor badge. Visitors remain accompanied by an authorized member of staff unless the Principal has approved unsupervised access. Visitors sign out and return the badge when leaving."),
        ("Record access", "Safeguarding records are accessible only to the safeguarding team and specifically authorized leadership. Staff must not copy safeguarding records into public chat groups or personal accounts. Questions about disclosure are referred to the Designated Safeguarding Lead."),
    ]),
    ("Behaviour, bullying and inclusive support", [
        ("POL-06 / Behaviour owner", "The Pastoral Lead oversees behaviour support and reports to the Principal. Staff use calm, respectful language and explain expectations without humiliation or collective punishment."),
        ("Classroom response", "For minor disruption, the teacher gives a calm reminder, offers a short reset and records repeated incidents. The Pastoral Lead reviews repeated behaviour concerns with the student and teacher to agree a support plan."),
        ("Bullying reports", "Staff pass bullying reports to the Pastoral Lead on the same school day. The Pastoral Lead acknowledges the report within 1 school day and starts a fact-finding review within 2 school days. The review considers the safety and support needs of all students involved."),
        ("Learning adjustments", "The Inclusion Coordinator agrees reasonable classroom adjustments with teachers and families. The Inclusion Coordinator reports to the Principal. An adjustment may include accessible materials, a quiet work space or additional processing time; it must not depend on a student publicly disclosing private information."),
        ("Review cycle", "A documented behaviour or inclusion support plan is reviewed after 10 school days. The review records what helped and any agreed changes. Safeguarding concerns identified during a behaviour review follow the immediate reporting procedure on page 5."),
    ]),
    ("Health, medication and emergency drills", [
        ("POL-07 / Health owner", "The School Nurse manages health arrangements and reports to the Principal. The Facilities Lead coordinates evacuation drills and reports to the Principal. Staff check the current care plan before supporting a student with a known medical need."),
        ("Medication", "Medication is administered only by the School Nurse or a trained authorized delegate after written parent consent. Medicine must arrive in its original labelled container. Every administered dose is recorded with the student's name, dose, time and administering adult."),
        ("Accident records", "Staff notify the School Nurse of injuries promptly and complete an accident record before the end of the same school day. The School Nurse decides whether further medical attention is needed and contacts the registered parent as appropriate."),
        ("Evacuation", "The primary evacuation assembly point is the north sports field. Teachers bring the class register, account for students and report missing persons to the Facilities Lead. Nobody re-enters the building until the Facilities Lead communicates authorization."),
        ("Drill schedule", "The Facilities Lead arranges one evacuation drill each term and records issues for review. This test handbook does not replace trained emergency judgment or specify local emergency service numbers. Food-allergy information is shared only with staff responsible for the student's care."),
    ]),
    ("Digital safety, privacy and school devices", [
        ("POL-08 / Technology owner", "The IT Coordinator manages approved school systems and reports to the Principal. The Data Protection Lead oversees privacy incidents and reports to the Principal. School information is stored in approved school-managed systems."),
        ("Account security", "Staff use a unique passphrase of at least 14 characters and enable multi-factor authentication on school accounts. Staff must not share passwords, leave devices unlocked or upload identifiable student records to unapproved AI tools."),
        ("Lost device", "Staff report a lost school device to the IT Coordinator within 1 hour of discovery. The IT Coordinator records the incident and secures affected accounts. Staff must not attempt to hide a device loss by deleting related records."),
        ("Privacy incident", "Suspected unauthorized disclosure of personal data is reported to the Data Protection Lead immediately. The Data Protection Lead coordinates the response and records decisions. This handbook does not set statutory retention periods or authorize public disclosure of student information."),
        ("Student devices", "Students keep personal phones switched off and stored during lessons unless the teacher authorizes an accessibility or learning use. School devices are returned to the charging cabinet at the end of the lesson. The teacher reports damage to the IT Coordinator."),
    ]),
    ("Parent communication, complaints and records", [
        ("POL-09 / Communication owner", "The School Office manages formal parent correspondence and reports to the Principal. Teachers use school-approved communication channels and verify the recipient before discussing a student."),
        ("Routine messages", "Teachers acknowledge routine parent messages within 2 school days. If a complete reply needs more time, the acknowledgement states when the parent can expect an update. Private student information must not appear in public parent groups."),
        ("Complaints", "Parents submit formal complaints to the School Office. The Principal acknowledges a formal complaint within 3 school days and provides an initial written response within 10 school days. If a review is delayed, the Principal explains the reason and gives a revised date."),
        ("Meetings", "Staff arrange parent meetings in advance and keep a factual record of agreed actions. A parent may request an interpreter through the School Office. Disagreements are recorded respectfully without treating an unverified allegation as a fact."),
        ("Corrections", "Parents request corrections to contact or collection details through the School Office. The office verifies identity before changing records and informs relevant staff. Safeguarding disclosures follow page 5 rather than the routine complaints timetable."),
    ]),
    ("Clubs, trips, transport and policy review", [
        ("POL-10 / Activities owner", "The Activities Coordinator oversees clubs and trips and reports to the Principal. A named teacher supervises each club and maintains a register. Clubs must use accessible participation arrangements agreed with the Inclusion Coordinator."),
        ("Trip approval", "Teachers submit trip risk assessments to the Activities Coordinator at least 15 school days before departure. The Principal approves off-campus trips only after reviewing the risk assessment, staffing and written parent consent. No student travels without written parent consent."),
        ("Supervision", "The minimum trip supervision ratio is one adult for every 10 students, with at least 2 adults on every off-campus trip. The risk assessment may require additional adults. A group of 8 students still requires at least 2 adults."),
        ("Transport", "The trip leader checks the student register before departure, on arrival and before the return journey. Only approved transport is used. A change to pickup arrangements must be confirmed through the School Office, not through an unverified message to a student."),
        ("Post-event review", "The trip leader submits a short trip review to the Activities Coordinator within 3 school days of return. The Principal reviews this handbook each January with policy owners. The document contains no cafeteria menu, salary schedule or tuition price list."),
    ]),
]
CASES = [
    {"question": "What time does the school day start and end?", "page": 1, "expected": ["8:15 AM", "3:10 PM"]},
    {"question": "By what time must parents report a student's absence?", "page": 2, "expected": ["8:45 AM", "Attendance Officer"]},
    {"question": "How soon must teachers return marked assignments?", "page": 3, "expected": ["7 school days"]},
    {"question": "Who approves planned leave and how early must staff request it?", "page": 4, "expected": ["Principal", "5 school days"]},
    {"question": "Who should staff contact if the Designated Safeguarding Lead is unavailable?", "page": 5, "expected": ["Deputy Safeguarding Lead"]},
    {"question": "How quickly does the Pastoral Lead acknowledge a bullying report?", "page": 6, "expected": ["1 school day"]},
    {"question": "Where is the primary evacuation assembly point?", "page": 7, "expected": ["north sports field"]},
    {"question": "How quickly must staff report a lost school device?", "page": 8, "expected": ["1 hour", "IT Coordinator"]},
    {"question": "What is the deadline for an initial written response to a formal complaint?", "page": 9, "expected": ["10 school days"]},
    {"question": "How early must teachers submit trip risk assessments?", "page": 10, "expected": ["15 school days"]},
    {"question": "What is tomorrow's cafeteria menu?", "page": None, "expected": []},
    {"question": "How much is the Principal paid each month?", "page": None, "expected": []},
]


def sample_policy_pdf():
    output = BytesIO()
    styles = getSampleStyleSheet()
    styles["Heading1"].textColor = colors.HexColor("#153b50")
    styles["BodyText"].fontSize = 10
    styles["BodyText"].leading = 15
    story = []
    for index, (title, sections) in enumerate(PAGES):
        if index:
            story.append(PageBreak())
        story.extend([Paragraph(title, styles["Heading1"]), Spacer(1, 14)])
        for heading, text in sections:
            story.extend([Paragraph(heading, styles["Heading3"]), Paragraph(text, styles["BodyText"]), Spacer(1, 10)])
    def decorate(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 9)
        canvas.setFillColor(colors.HexColor("#496578"))
        canvas.drawString(48, A4[1] - 30, "MAPLE GROVE DEMONSTRATION SCHOOL | FICTIONAL TEST POLICIES | v1.0")
        canvas.drawString(48, 27, "For StaffDesk testing only. Not a real school's approved policy.")
        canvas.drawRightString(A4[0] - 48, 27, f"Page {document.page} of 10")
        canvas.restoreState()
    SimpleDocTemplate(output, pagesize=A4, leftMargin=48, rightMargin=48, topMargin=58,
                      bottomMargin=48, title="Maple Grove School - Fictional Sample Policies", invariant=1).build(
                          story, onFirstPage=decorate, onLaterPages=decorate)
    data = output.getvalue()
    if len(PdfReader(BytesIO(data)).pages) != 10:
        raise RuntimeError("Sample handbook must contain exactly 10 pages.")
    return data


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent / FILENAME)
    args = parser.parse_args()
    with args.output.open("xb") as target:
        target.write(sample_policy_pdf())
    cases_path = args.output.with_suffix(".questions.json")
    with cases_path.open("x", encoding="utf-8") as target:
        json.dump(CASES, target, ensure_ascii=False, indent=2)
    print(f"Created: {args.output}\nExpected-answer cases: {cases_path}")
