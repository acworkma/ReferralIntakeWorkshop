import hashlib
from pathlib import PurePath
import re

from fastapi import HTTPException, UploadFile

ALLOWED_TYPES = {"application/pdf", "image/png", "image/jpeg"}
SIGNATURES = {
    "application/pdf": (b"%PDF",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
}


async def validate_upload(upload: UploadFile, max_bytes: int) -> tuple[str, bytes, str]:
    filename = PurePath(upload.filename or "").name
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,200}", filename):
        raise HTTPException(400, "Use a safe filename.")
    if upload.content_type not in ALLOWED_TYPES:
        raise HTTPException(415, "Only PDF, PNG, and JPEG files are accepted.")

    content = await upload.read(max_bytes + 1)
    if not content or len(content) > max_bytes:
        raise HTTPException(413, f"File must be between 1 byte and {max_bytes} bytes.")
    if not any(content.startswith(sig) for sig in SIGNATURES[upload.content_type]):
        raise HTTPException(400, "File signature does not match its declared media type.")
    return filename, content, hashlib.sha256(content).hexdigest()
