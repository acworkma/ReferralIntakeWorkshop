"""The referral field schema.

This module is the single source of truth for what the platform extracts.
It drives four things that must never drift apart:

* the Content Understanding custom analyzer definition (``analyzer.py``)
* the Document Intelligence ``queryFields`` request (``extractors.py``)
* the side-by-side comparison table rendered by the web app
* the ground truth recorded in ``samples/manifest.json``

Document Intelligence caps ``queryFields`` at 20 entries, so keep the
extracted set at or below that limit.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Field:
    name: str
    description: str
    type: str = "string"
    method: str = "extract"
    enum: tuple[str, ...] | None = None


#: Ordered so the comparison table reads top-to-bottom like a referral form:
#: who the patient is, who sent it, what is being asked for, and why.
SCHEMA: tuple[Field, ...] = (
    Field("patientName", "Full name of the patient being referred."),
    Field(
        "patientDateOfBirth",
        "Patient date of birth in YYYY-MM-DD format.",
        type="date",
    ),
    Field("medicalRecordNumber", "Patient medical record number (MRN) or chart number."),
    Field("referringProvider", "Name of the clinician or organization making the referral."),
    Field(
        "referringProviderNpi",
        "Ten digit National Provider Identifier of the referring provider.",
    ),
    Field(
        "priority",
        "Urgency of the referral as stated on the document.",
        method="classify",
        enum=("Routine", "Urgent", "STAT"),
    ),
    Field("requestedService", "The home health service or discipline being requested."),
    Field("primaryDiagnosis", "Primary diagnosis or clinical reason for the referral."),
    Field("diagnosisCode", "ICD-10 code for the primary diagnosis."),
    Field("payer", "Insurance plan or payer responsible for the episode of care."),
    Field("authorizationNumber", "Prior authorization or reference number, if present."),
    Field(
        "requestedDate",
        "Requested start of care date in YYYY-MM-DD format.",
        type="date",
    ),
    Field(
        "summary",
        "One or two sentence clinical summary of what is being requested and why.",
        method="generate",
    ),
)

FIELDS: tuple[str, ...] = tuple(field.name for field in SCHEMA)

#: ``summary`` is generated prose, so the two engines will legitimately word it
#: differently. Excluding it keeps the agreement metric meaningful.
COMPARABLE_FIELDS: tuple[str, ...] = tuple(
    field.name for field in SCHEMA if field.method != "generate"
)

#: Document Intelligence query fields cannot request generated prose.
QUERY_FIELDS: tuple[str, ...] = COMPARABLE_FIELDS


def analyzer_field_schema() -> dict:
    """Build the ``fieldSchema.fields`` block for a Content Understanding analyzer."""
    fields: dict[str, dict] = {}
    for field in SCHEMA:
        definition: dict = {
            "type": field.type,
            "method": field.method,
            "description": field.description,
        }
        if field.enum:
            definition["enum"] = list(field.enum)
        fields[field.name] = definition
    return {"fields": fields}
