"""Referral scenarios used to render the sample documents.

Each scenario is the ground truth for one referral. The renderers in
``generate_samples.py`` lay these values out differently per intake channel,
and ``manifest.json`` records them so extraction accuracy can be scored.

On realism and safety
---------------------
These records are fabricated, but they are deliberately *structurally*
realistic so the extraction demo is meaningful. Safety comes from using
identifier ranges that are reserved for fiction rather than from stamping a
banner across the page:

* Phone/fax numbers use the 555-01xx block reserved for fictional use.
* Domains use ``example.com`` / ``example.org`` (RFC 2606).
* NPIs are ten digits that deliberately fail the required Luhn check digit,
  so they can never collide with a real registered provider.
* MRNs, authorization numbers, and member IDs follow plausible formats but
  belong to organizations that do not exist.

No real patient, provider, payer, or facility is represented.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Scenario:
    key: str
    channel: str
    patient_name: str
    date_of_birth: str
    mrn: str
    referring_provider: str
    provider_npi: str
    provider_org: str
    provider_phone: str
    provider_fax: str
    priority: str
    requested_service: str
    primary_diagnosis: str
    diagnosis_code: str
    payer: str
    member_id: str
    authorization_number: str
    requested_date: str
    summary: str
    clinical_note: str
    address: str
    phone: str
    secondary_diagnoses: tuple[str, ...] = ()
    medications: tuple[str, ...] = ()
    #: Fields a reviewer is expected to have to correct or confirm by hand.
    ambiguous_fields: tuple[str, ...] = field(default_factory=tuple)
    notes: str = ""


SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        key="portal-chf",
        channel="Referral Portals",
        patient_name="Rowan Alvarez",
        date_of_birth="1948-03-22",
        mrn="MRN-441703",
        referring_provider="Priya Raman, MD",
        provider_npi="1000000012",
        provider_org="Lakeview Family Medicine",
        provider_phone="(555) 555-0142",
        provider_fax="(555) 555-0143",
        priority="Routine",
        requested_service="Skilled nursing",
        primary_diagnosis="Congestive heart failure exacerbation",
        diagnosis_code="I50.9",
        payer="Example Health Plan",
        member_id="EHP-88213004",
        authorization_number="AUTH-55012",
        requested_date="2030-01-15",
        summary=(
            "Skilled nursing requested for post-discharge heart failure management "
            "including daily weights, diuretic titration support, and education."
        ),
        clinical_note=(
            "Patient discharged 2030-01-12 following a four day admission for acute "
            "decompensated heart failure. Discharge weight 84.2 kg, up 3.1 kg from "
            "baseline. Requires daily weight monitoring, low sodium diet reinforcement, "
            "and assessment of diuretic response. Spouse available to assist."
        ),
        address="418 Merrivale Road, Apt 2B, Springfield, IL 62704",
        phone="(555) 555-0177",
        secondary_diagnoses=("Type 2 diabetes mellitus (E11.9)", "Chronic kidney disease stage 3 (N18.30)"),
        medications=("Furosemide 40 mg PO daily", "Carvedilol 6.25 mg PO BID", "Lisinopril 10 mg PO daily"),
    ),
    Scenario(
        key="fax-wound",
        channel="Fax Systems",
        patient_name="Dolores Whitfield",
        date_of_birth="1939-11-04",
        mrn="MRN-207755",
        referring_provider="Aaron Beckett, DO",
        provider_npi="1000000038",
        provider_org="Riverside Surgical Associates",
        provider_phone="(555) 555-0119",
        provider_fax="(555) 555-0120",
        priority="Urgent",
        requested_service="Wound care",
        primary_diagnosis="Stage 3 pressure ulcer of sacral region",
        diagnosis_code="L89.153",
        payer="Statewide Care Advantage",
        member_id="SCA-40027719",
        authorization_number="AUTH-61884",
        requested_date="2030-02-03",
        summary=(
            "Urgent wound care requested for a stage 3 sacral pressure ulcer with "
            "moderate serosanguineous drainage; twice weekly dressing changes."
        ),
        clinical_note=(
            "Sacral wound measures 4.2 cm x 3.0 cm x 1.1 cm with moderate "
            "serosanguineous drainage and no odor. Peri-wound intact. Requires "
            "twice weekly dressing changes with alginate and offloading education. "
            "Daughter is primary caregiver."
        ),
        address="77 Old Chapel Lane, Danvers, MA 01923",
        phone="(555) 555-0188",
        secondary_diagnoses=("Vascular dementia (F01.50)", "Protein-calorie malnutrition (E44.0)"),
        medications=("Acetaminophen 650 mg PO q6h PRN", "Multivitamin PO daily"),
        # A fax is degraded on purpose; these are the fields that realistically
        # come back wrong and give the human reviewer something to actually do.
        ambiguous_fields=("referringProviderNpi", "authorizationNumber"),
        notes="Rendered as a degraded 200 dpi bitonal fax with skew and scan noise.",
    ),
    Scenario(
        key="email-ortho",
        channel="Email Attachments",
        patient_name="Marcus Oyelaran",
        date_of_birth="1972-07-30",
        mrn="MRN-663120",
        referring_provider="Helen Zhao, MD",
        provider_npi="1000000053",
        provider_org="Cedar Ridge Orthopaedics",
        provider_phone="(555) 555-0164",
        provider_fax="(555) 555-0165",
        priority="Routine",
        requested_service="Physical therapy",
        primary_diagnosis="Status post right total knee arthroplasty",
        diagnosis_code="Z96.651",
        payer="Northbridge Mutual",
        member_id="NBM-5521884",
        authorization_number="AUTH-70233",
        requested_date="2030-03-11",
        summary=(
            "Home physical therapy requested following right total knee arthroplasty "
            "to restore range of motion, strength, and safe stair negotiation."
        ),
        clinical_note=(
            "Right TKA performed 2030-03-04. Current ROM 5 to 85 degrees. Ambulates "
            "with a front wheeled walker, 50 percent weight bearing tolerance. Goals "
            "are independent ambulation, 0 to 110 degrees ROM, and stair negotiation. "
            "Two flights of stairs at home entry."
        ),
        address="1290 Kestrel Avenue, Unit 5, Portland, OR 97214",
        phone="(555) 555-0106",
        secondary_diagnoses=("Essential hypertension (I10)", "Obesity (E66.9)"),
        medications=("Oxycodone 5 mg PO q6h PRN", "Aspirin 81 mg PO daily", "Docusate 100 mg PO BID"),
    ),
    Scenario(
        key="scan-copd",
        channel="Scanned Patient Documents",
        patient_name="Etta Brannigan",
        date_of_birth="1945-05-17",
        mrn="MRN-118902",
        referring_provider="Samuel Ncube, MD",
        provider_npi="1000000079",
        provider_org="Grandview Pulmonary Clinic",
        provider_phone="(555) 555-0133",
        provider_fax="(555) 555-0134",
        priority="Routine",
        requested_service="Skilled nursing",
        primary_diagnosis="Chronic obstructive pulmonary disease with acute exacerbation",
        diagnosis_code="J44.1",
        payer="Example Health Plan",
        member_id="EHP-77340192",
        authorization_number="AUTH-58471",
        requested_date="2030-04-02",
        summary=(
            "Skilled nursing requested for COPD exacerbation follow-up, inhaler "
            "technique teaching, and home oxygen safety assessment."
        ),
        clinical_note=(
            "Home oxygen at 2 L/min via nasal cannula. Reports increased dyspnea on "
            "exertion over the past week. Requires inhaler technique review, oxygen "
            "safety assessment, and pulse oximetry monitoring. Lives alone."
        ),
        address="9 Bramble Court, Asheville, NC 28801",
        phone="(555) 555-0155",
        secondary_diagnoses=("Anxiety disorder (F41.9)", "Osteoporosis (M81.0)"),
        medications=("Tiotropium 18 mcg inhaled daily", "Albuterol 90 mcg inhaled q4h PRN", "Prednisone 20 mg PO daily"),
        # Handwritten form values are the hardest realistic case.
        ambiguous_fields=("patientDateOfBirth", "medicalRecordNumber", "authorizationNumber"),
        notes="Handwritten intake form values, rendered at 300 dpi with scan artifacts.",
    ),
    Scenario(
        key="packet-stroke",
        channel="Provider Referral Packets",
        patient_name="Theodore Kaminski",
        date_of_birth="1953-09-08",
        mrn="MRN-550418",
        referring_provider="Nadia Farouk, MD",
        provider_npi="1000000095",
        provider_org="Saint Aubrey Regional Medical Center",
        provider_phone="(555) 555-0171",
        provider_fax="(555) 555-0172",
        priority="Urgent",
        requested_service="Occupational therapy",
        primary_diagnosis="Cerebral infarction with right sided hemiparesis",
        diagnosis_code="I63.9",
        payer="Statewide Care Advantage",
        member_id="SCA-40118325",
        authorization_number="AUTH-64907",
        requested_date="2030-05-20",
        summary=(
            "Multi-discipline home referral after ischemic stroke; occupational "
            "therapy leads on activities of daily living and home safety."
        ),
        clinical_note=(
            "Ischemic stroke 2030-05-11 with residual right sided hemiparesis and mild "
            "expressive aphasia. Modified barium swallow cleared for dysphagia 2 diet. "
            "Requires ADL retraining, home safety evaluation, and caregiver training. "
            "Wife present in the home full time."
        ),
        address="3455 Harrowgate Street, Cleveland, OH 44113",
        phone="(555) 555-0122",
        secondary_diagnoses=("Atrial fibrillation (I48.91)", "Dysphagia (R13.10)", "Expressive aphasia (R47.01)"),
        medications=("Apixaban 5 mg PO BID", "Atorvastatin 40 mg PO daily", "Metoprolol succinate 50 mg PO daily"),
        notes="Multi-page packet: face sheet, history and physical, medication list, signed order.",
    ),
    Scenario(
        key="partner-hospice",
        channel="External Healthcare Partners",
        patient_name="Junko Halvorsen",
        date_of_birth="1936-12-19",
        mrn="MRN-903277",
        referring_provider="Elliot Sandoval, MD",
        provider_npi="1000000110",
        provider_org="Meridian Partner Health Network",
        provider_phone="(555) 555-0148",
        provider_fax="(555) 555-0149",
        priority="STAT",
        requested_service="Skilled nursing",
        primary_diagnosis="Metastatic pancreatic carcinoma",
        diagnosis_code="C25.9",
        payer="Northbridge Mutual",
        member_id="NBM-5590471",
        authorization_number="AUTH-72550",
        requested_date="2030-06-08",
        summary=(
            "STAT skilled nursing requested for symptom management and pain control "
            "in advanced pancreatic carcinoma, transitioning toward comfort care."
        ),
        clinical_note=(
            "Progressive metastatic disease with hepatic involvement. Pain currently "
            "7 of 10 despite current regimen. Requires pain reassessment, bowel regimen "
            "management, and goals of care discussion. Family requests same day contact."
        ),
        address="12 Foxglove Terrace, Tacoma, WA 98402",
        phone="(555) 555-0193",
        secondary_diagnoses=("Cancer related pain (G89.3)", "Cachexia (R64)"),
        medications=("Morphine sulfate ER 30 mg PO q12h", "Ondansetron 4 mg PO q8h PRN", "Senna-docusate PO BID"),
        notes="Partner EMR export layout with a code-first table rather than a form.",
    ),
)


def by_key(key: str) -> Scenario:
    for scenario in SCENARIOS:
        if scenario.key == key:
            return scenario
    raise KeyError(key)


def expected_fields(scenario: Scenario) -> dict[str, str]:
    """The ground truth an extraction engine should return for this referral."""
    return {
        "patientName": scenario.patient_name,
        "patientDateOfBirth": scenario.date_of_birth,
        "medicalRecordNumber": scenario.mrn,
        "referringProvider": scenario.referring_provider,
        "referringProviderNpi": scenario.provider_npi,
        "priority": scenario.priority,
        "requestedService": scenario.requested_service,
        "primaryDiagnosis": scenario.primary_diagnosis,
        "diagnosisCode": scenario.diagnosis_code,
        "payer": scenario.payer,
        "authorizationNumber": scenario.authorization_number,
        "requestedDate": scenario.requested_date,
    }
