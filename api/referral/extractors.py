from dataclasses import dataclass
import hashlib
import time

import httpx
from azure.identity import DefaultAzureCredential

from .config import settings


@dataclass
class Extraction:
    engine: str
    fields: dict[str, str]
    confidence: dict[str, float]


FIELDS = ("referralType", "priority", "service", "requestedDate", "summary")


def _synthetic(engine: str, digest: str) -> Extraction:
    seed = int(digest[:8], 16)
    is_cu = engine == "Content Understanding"
    return Extraction(
        engine=engine,
        fields={
            "referralType": "Synthetic specialist consultation",
            "priority": "Routine" if (seed + int(is_cu)) % 3 else "Expedited",
            "service": "Synthetic care navigation",
            "requestedDate": "2030-01-15",
            "summary": "Generated demonstration referral; contains no personal data.",
        },
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
        if settings.allow_local_synthetic_extraction:
            return _synthetic("Document Intelligence", digest)
        raise RuntimeError("DOCUMENT_INTELLIGENCE_ENDPOINT is required.")
    url = (
        f"{settings.document_intelligence_endpoint.rstrip('/')}/documentintelligence/"
        "documentModels/prebuilt-layout:analyze?api-version=2024-11-30"
    )
    headers = {"Authorization": f"Bearer {_token()}", "Content-Type": "application/octet-stream"}
    response = httpx.post(url, headers=headers, content=content, timeout=30)
    response.raise_for_status()
    result = _poll(response.headers["operation-location"], headers)
    text = result["analyzeResult"].get("content", "")
    return Extraction(
        "Document Intelligence",
        {"summary": text[:500], **{field: "Review required" for field in FIELDS[:-1]}},
        {field: 0.0 for field in FIELDS},
    )


def content_understanding(content: bytes, digest: str) -> Extraction:
    if not settings.content_understanding_endpoint:
        if settings.allow_local_synthetic_extraction:
            return _synthetic("Content Understanding", digest)
        raise RuntimeError("CONTENT_UNDERSTANDING_ENDPOINT is required.")
    url = (
        f"{settings.content_understanding_endpoint.rstrip('/')}/contentunderstanding/"
        "analyzers/prebuilt-document:analyze?api-version=2025-05-01-preview"
    )
    headers = {"Authorization": f"Bearer {_token()}", "Content-Type": "application/octet-stream"}
    response = httpx.post(url, headers=headers, content=content, timeout=30)
    response.raise_for_status()
    result = _poll(response.headers["operation-location"], headers)
    content_result = result.get("result", {}).get("contents", [{}])[0]
    fields = content_result.get("fields", {})
    return Extraction(
        "Content Understanding",
        {
            field: str(fields.get(field, {}).get("valueString", "Review required"))
            for field in FIELDS
        },
        {field: float(fields.get(field, {}).get("confidence", 0)) for field in FIELDS},
    )


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
                "matches": left.casefold().strip() == right.casefold().strip(),
            }
        )
    return {
        "rows": rows,
        "agreementPercent": round(sum(row["matches"] for row in rows) / len(rows) * 100),
        "contentSha256": hashlib.sha256(content).hexdigest(),
    }
