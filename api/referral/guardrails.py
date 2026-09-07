"""Document validation, shared by the web upload path and the orchestration function.

The rules live here rather than in the API because the API is not the only way a
document arrives. Anything an upstream system drops straight into the landing
zone has to face exactly the same checks, so the checks cannot depend on the
HTTP transport.
"""

import hashlib
from pathlib import PurePath
import re

ALLOWED_TYPES = {"application/pdf", "image/png", "image/jpeg"}
SIGNATURES = {
    "application/pdf": (b"%PDF",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
}

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
_RUNS = re.compile(r"-{2,}")


class DocumentRejected(Exception):
    """A document failed validation and must not enter the pipeline."""

    def __init__(self, reason: str, status_code: int = 400) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status_code = status_code


def sniff_media_type(content: bytes) -> str:
    for media_type, signatures in SIGNATURES.items():
        if any(content.startswith(signature) for signature in signatures):
            return media_type
    return "application/octet-stream"


def safe_filename(candidate: str) -> str:
    """Reduces any inbound name to a path-safe basename.

    Upstream systems name files whatever they like, so this normalises rather
    than rejects. Taking the ``PurePath`` basename first is what blocks
    traversal; the substitution only tidies what is left.
    """
    name = _UNSAFE.sub("-", PurePath(candidate.replace("\\", "/")).name)
    # A hyphen is itself legal, so runs have to be collapsed in a second pass or
    # " - " becomes "---".
    name = _RUNS.sub("-", name).strip("-")
    if not name or set(name) <= {"."}:
        raise DocumentRejected("The document has no usable filename.")
    return name[:200]


def validate_document(filename: str, content: bytes, max_bytes: int) -> tuple[str, bytes, str]:
    """Validates a document from any source and returns (name, content, sha256)."""
    name = safe_filename(filename)
    if not content:
        raise DocumentRejected("The document is empty.", 413)
    if len(content) > max_bytes:
        raise DocumentRejected(f"The document exceeds the {max_bytes} byte limit.", 413)
    media_type = sniff_media_type(content)
    if media_type not in ALLOWED_TYPES:
        raise DocumentRejected("Only PDF, PNG, and JPEG documents are accepted.", 415)
    return name, content, hashlib.sha256(content).hexdigest()
