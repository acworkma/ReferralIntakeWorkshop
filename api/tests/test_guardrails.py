from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from referral.guardrails import DocumentRejected, safe_filename, validate_document
from referral.uploads import validate_upload


def _upload(filename: str, body: bytes, content_type: str = "application/pdf") -> UploadFile:
    return UploadFile(
        filename=filename,
        file=BytesIO(body),
        headers=Headers({"content-type": content_type}),
    )


@pytest.mark.asyncio
async def test_accepts_valid_pdf():
    name, content, digest = await validate_upload(_upload("referral.pdf", b"%PDF demo"), 100)
    assert name == "referral.pdf"
    assert content.startswith(b"%PDF")
    assert len(digest) == 64


@pytest.mark.asyncio
async def test_rejects_signature_mismatch():
    """PNG bytes are extractable, but not as the PDF the browser claimed to send."""
    with pytest.raises(HTTPException) as exc:
        await validate_upload(_upload("referral.pdf", b"\x89PNG\r\n\x1a\nbody"), 100)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_rejects_bytes_we_cannot_identify_at_all():
    with pytest.raises(HTTPException) as exc:
        await validate_upload(_upload("referral.pdf", b"not-a-pdf"), 100)
    assert exc.value.status_code == 415


@pytest.mark.asyncio
async def test_rejects_a_type_we_cannot_extract():
    with pytest.raises(HTTPException) as exc:
        await validate_upload(_upload("notes.txt", b"just some text", "text/plain"), 100)
    assert exc.value.status_code == 415


@pytest.mark.asyncio
async def test_rejects_a_document_over_the_size_limit():
    with pytest.raises(HTTPException) as exc:
        await validate_upload(_upload("big.pdf", b"%PDF" + b"x" * 200), 100)
    assert exc.value.status_code == 413


def test_awkward_upstream_names_are_normalised_not_rejected():
    """A real upstream system will send names with spaces and punctuation."""
    assert safe_filename("Referral - Smith, John (2031).pdf") == "Referral-Smith-John-2031-.pdf"


def test_path_traversal_is_stripped_to_a_basename():
    assert safe_filename("../../etc/passwd") == "passwd"
    assert safe_filename(r"..\..\windows\system32\config") == "config"


def test_a_name_with_nothing_usable_left_is_rejected():
    with pytest.raises(DocumentRejected):
        safe_filename("///")


def test_validation_is_identical_whatever_the_document_arrived_through():
    name, _, digest = validate_document("scan.png", b"\x89PNG\r\n\x1a\nbody", 100)
    assert name == "scan.png"
    assert len(digest) == 64
