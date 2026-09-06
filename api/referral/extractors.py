from dataclasses import dataclass
import base64
import hashlib
import time

import httpx
from azure.identity import DefaultAzureCredential

from .config import settings
from .guardrails import sniff_media_type
from .schema import COMPARABLE_FIELDS, FIELDS, QUERY_FIELDS


@dataclass
class Extraction:
    engine: str
    fields: dict[str, str]
    confidence: dict[str, float]


_DEMO_VALUES = {
    "patientName": "Rowan Alvarez",
    "patientDateOfBirth": "1948-03-22",
    "medicalRecordNumber": "MRN-441703",
    "referringProvider": "Dr. Priya Raman, Lakeview Family Medicine",
    "referringProviderNpi": "1000000012",
    "priority": "Routine",
    "requestedService": "Skilled nursing",
    "primaryDiagnosis": "Congestive heart failure exacerbation",
    "diagnosisCode": "I50.9",
    "payer": "Example Health Plan",
    "authorizationNumber": "AUTH-55012",
    "requestedDate": "2030-01-15",
    "summary": "Demonstration referral generated locally; no service call was made.",
}


def _demo_extraction(engine: str, digest: str) -> Extraction:
    seed = int(digest[:8], 16)
    is_cu = engine == "Content Understanding"
    fields = dict(_DEMO_VALUES)
    # Make the two engines disagree on one row so the comparison view has
    # something to show when running without Azure.
    if is_cu and seed % 2:
        fields["priority"] = "Urgent"
    return Extraction(
        engine=engine,
        fields=fields,
        confidence={
            field: round(0.80 + ((seed >> index) % 17) / 100, 2)
            for index, field in enumerate(FIELDS)
        },
    )


def _token() -> str:
    return DefaultAzureCredential().get_token(
        "https://cognitiveservices.azure.com/.default"
    ).token


def _poll(url: str, headers: dict[str, str]) -> dict:
    for _ in range(60):
        response = httpx.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        payload = response.json()
        if payload.get("status", "").lower() in {"succeeded", "failed"}:
            if payload["status"].lower() == "failed":
                raise RuntimeError("Azure extraction operation failed.")
            return payload
        time.sleep(2)
    raise TimeoutError("Azure extraction operation timed out.")


def document_intelligence(content: bytes, digest: str) -> Extraction:
    if not settings.document_intelligence_endpoint:
        if settings.allow_local_mock_extraction:
            return _demo_extraction("Document Intelligence", digest)
        raise RuntimeError("DOCUMENT_INTELLIGENCE_ENDPOINT is required.")
    url = (
        f"{settings.document_intelligence_endpoint.rstrip('/')}/documentintelligence/"
        "documentModels/prebuilt-layout:analyze?api-version=2024-11-30"
        f"&features=queryFields&queryFields={','.join(QUERY_FIELDS)}"
    )
    headers = {"Authorization": f"Bearer {_token()}", "Content-Type": "application/octet-stream"}
    response = httpx.post(url, headers=headers, content=content, timeout=30)
    response.raise_for_status()
    result = _poll(response.headers["operation-location"], headers)
    analyze = result.get("analyzeResult", {})
    documents = analyze.get("documents") or [{}]
    extracted = documents[0].get("fields", {})

    fields: dict[str, str] = {}
    confidence: dict[str, float] = {}
    for field in FIELDS:
        found = extracted.get(field) or {}
        value = found.get("valueString") or found.get("content") or ""
        fields[field] = value.strip() or "Not found"
        confidence[field] = float(found.get("confidence", 0.0))

    # Layout does not generate prose, so summarise from the recognised text.
    if not extracted.get("summary"):
        text = " ".join(analyze.get("content", "").split())
        fields["summary"] = text[:400] or "Not found"
        confidence["summary"] = 0.0
    return Extraction("Document Intelligence", fields, confidence)


def content_understanding(content: bytes, digest: str) -> Extraction:
    if not settings.content_understanding_endpoint:
        if settings.allow_local_mock_extraction:
            return _demo_extraction("Content Understanding", digest)
        raise RuntimeError("CONTENT_UNDERSTANDING_ENDPOINT is required.")
    url = (
        f"{settings.content_understanding_endpoint.rstrip('/')}/contentunderstanding/"
        f"analyzers/{settings.content_understanding_analyzer}:analyze"
        f"?api-version={settings.content_understanding_api_version}"
    )
    auth = {"Authorization": f"Bearer {_token()}"}
    # Content Understanding takes JSON with base64 inputs, not a raw binary body.
    payload = {
        "inputs": [
            {
                "name": "referral",
                "data": base64.b64encode(content).decode("ascii"),
                "mimeType": sniff_media_type(content),
            }
        ]
    }
    response = httpx.post(url, headers=auth, json=payload, timeout=60)
    response.raise_for_status()
    result = _poll(response.headers["operation-location"], auth)
    content_result = result.get("result", {}).get("contents", [{}])[0]
    extracted = content_result.get("fields", {})

    fields: dict[str, str] = {}
    confidence: dict[str, float] = {}
    for field in FIELDS:
        found = extracted.get(field) or {}
        fields[field] = _field_value(found)
        confidence[field] = float(found.get("confidence", 0.0))
    return Extraction("Content Understanding", fields, confidence)


def _field_value(found: dict) -> str:
    """Read whichever typed value slot Content Understanding populated."""
    for key in ("valueString", "valueDate", "valueTime", "valueNumber", "valueInteger"):
        if found.get(key) not in (None, ""):
            return str(found[key])
    if found.get("valueBoolean") is not None:
        return "Yes" if found["valueBoolean"] else "No"
    return "Not found"


def compare(content: bytes, digest: str) -> dict:
    first = document_intelligence(content, digest)
    second = content_understanding(content, digest)
    rows = []
    for field in FIELDS:
        left, right = first.fields.get(field, ""), second.fields.get(field, "")
        rows.append(
            {
                "field": field,
                "documentIntelligence": left,
                "contentUnderstanding": right,
                "documentIntelligenceConfidence": first.confidence.get(field, 0),
                "contentUnderstandingConfidence": second.confidence.get(field, 0),
                "matches": _values_agree(left, right),
            }
        )
    # Generated prose is expected to differ, so agreement is scored on the
    # fields that have a single correct answer.
    scored = [row for row in rows if row["field"] in COMPARABLE_FIELDS]
    agreement = round(sum(row["matches"] for row in scored) / len(scored) * 100)
    return {
        "rows": rows,
        "agreementPercent": agreement,
        "contentSha256": hashlib.sha256(content).hexdigest(),
    }


def _values_agree(left: str, right: str) -> bool:
    def normalise(value: str) -> str:
        return " ".join(value.casefold().replace(",", " ").split()).strip(" .")

    return normalise(left) == normalise(right)
