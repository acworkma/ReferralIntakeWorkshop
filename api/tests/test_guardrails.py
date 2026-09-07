from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from referral.guardrails import validate_upload


@pytest.mark.asyncio
async def test_accepts_valid_pdf():
    upload = UploadFile(
        filename="referral.pdf",
        file=BytesIO(b"%PDF demo"),
        headers=Headers({"content-type": "application/pdf"}),
    )
    name, content, digest = await validate_upload(upload, 100)
    assert name == "referral.pdf"
    assert content.startswith(b"%PDF")
    assert len(digest) == 64


@pytest.mark.asyncio
async def test_rejects_unsafe_filename():
    upload = UploadFile(
        filename="not a valid name!.pdf",
        file=BytesIO(b"%PDF"),
        headers=Headers({"content-type": "application/pdf"}),
    )
    with pytest.raises(HTTPException) as exc:
        await validate_upload(upload, 100)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_rejects_signature_mismatch():
    upload = UploadFile(
        filename="referral.pdf",
        file=BytesIO(b"not-a-pdf"),
        headers=Headers({"content-type": "application/pdf"}),
    )
    with pytest.raises(HTTPException) as exc:
        await validate_upload(upload, 100)
    assert exc.value.status_code == 400
