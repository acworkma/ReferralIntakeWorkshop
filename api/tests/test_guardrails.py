from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from referral.guardrails import validate_synthetic_upload


@pytest.mark.asyncio
async def test_accepts_synthetic_pdf():
    upload = UploadFile(
        filename="synthetic-referral.pdf",
        file=BytesIO(b"%PDF synthetic"),
        headers=Headers({"content-type": "application/pdf"}),
    )
    name, content, digest = await validate_synthetic_upload(upload, "synthetic", 100)
    assert name == "synthetic-referral.pdf"
    assert content.startswith(b"%PDF")
    assert len(digest) == 64


@pytest.mark.asyncio
async def test_rejects_unmarked_filename():
    upload = UploadFile(filename="real-referral.pdf", file=BytesIO(b"%PDF"))
    with pytest.raises(HTTPException) as exc:
        await validate_synthetic_upload(upload, "synthetic", 100)
    assert exc.value.status_code == 400
