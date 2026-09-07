"""The HTTP adapter over :mod:`referral.guardrails`.

Kept separate from the rules themselves so the orchestration function can apply
the same validation without importing a web framework it never serves.
"""

from fastapi import HTTPException, UploadFile

from .guardrails import (
    ALLOWED_TYPES,
    SIGNATURES,
    DocumentRejected,
    validate_document,
)


async def validate_upload(upload: UploadFile, max_bytes: int) -> tuple[str, bytes, str]:
    """Validates a browser upload and returns (filename, content, sha256).

    The browser also declares a content type, so this additionally checks the
    declaration against the bytes rather than trusting either on its own.
    """
    content = await upload.read(max_bytes + 1)
    try:
        name, content, digest = validate_document(upload.filename or "", content, max_bytes)
    except DocumentRejected as rejected:
        raise HTTPException(rejected.status_code, rejected.reason) from rejected
    if upload.content_type in ALLOWED_TYPES and not any(
        content.startswith(signature) for signature in SIGNATURES[upload.content_type]
    ):
        raise HTTPException(400, "File signature does not match its declared media type.")
    return name, content, digest
