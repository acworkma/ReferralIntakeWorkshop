"""Verifies AI extraction wiring from inside the private network.

Run it inside the API container, where the managed identity and private
endpoints are available:

    az containerapp exec -g <rg> -n <app> --container api --command "python -m referral.diagnose"
"""

import struct
import sys
import zlib

import httpx

from .config import settings
from .extractors import _token, content_understanding, document_intelligence


def _sample_png(size: int = 200) -> bytes:
    """A valid white PNG. Document Intelligence rejects images under 50x50."""
    scanlines = b"".join(b"\x00" + b"\xff" * (size * 3) for _ in range(size))

    def chunk(kind: bytes, payload: bytes) -> bytes:
        body = kind + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(scanlines))
        + chunk(b"IEND", b"")
    )


def _list_analyzers() -> None:
    endpoint = settings.content_understanding_endpoint
    if not endpoint:
        return
    url = (
        f"{endpoint.rstrip('/')}/contentunderstanding/analyzers"
        f"?api-version={settings.content_understanding_api_version}"
    )
    print(f"\n=== Content Understanding analyzers ({settings.content_understanding_api_version}) ===")
    try:
        response = httpx.get(url, headers={"Authorization": f"Bearer {_token()}"}, timeout=30)
        response.raise_for_status()
        names = [item.get("analyzerId") for item in response.json().get("value", [])]
        print(f"available: {names or '(none)'}")
    except Exception as error:  # noqa: BLE001 - diagnostics report every failure
        print(f"FAILED: {type(error).__name__}: {error}")


def _end_to_end() -> int:
    """Drives the real blob -> queue -> worker -> SQL path against live Azure resources."""
    import hashlib
    import time
    import uuid

    from .database import Referral, SessionLocal
    from .storage import delete_document, enqueue, store_document
    from sqlalchemy import select

    content = _sample_png()
    digest = hashlib.sha256(content).hexdigest()
    filename = "diagnostic.png"
    referral_id = str(uuid.uuid4())

    print("\n=== End-to-end pipeline ===")
    with SessionLocal() as session:
        for stale in session.scalars(select(Referral).where(Referral.sha256 == digest)).all():
            session.delete(stale)
        session.commit()

    storage_uri = store_document(referral_id, filename, content)
    print(f"stored blob: {'yes' if storage_uri else 'no (storage unset)'}")
    with SessionLocal() as session:
        session.add(
            Referral(
                id=referral_id,
                filename=filename,
                sha256=digest,
                status="queued",
                progress=5,
                submitted_by="diagnostics",
                storage_uri=storage_uri,
            )
        )
        session.commit()

    if not enqueue(referral_id):
        print("FAILED: queue is not configured, so no worker can pick this up.")
        return 1
    print(f"enqueued {referral_id}; waiting for the worker to process it...")

    status, deadline = "queued", time.time() + 300
    while time.time() < deadline:
        time.sleep(5)
        with SessionLocal() as session:
            row = session.get(Referral, referral_id)
            status, progress = row.status, row.progress
        print(f"  status={status} progress={progress}")
        if status not in {"queued", "processing"}:
            break

    with SessionLocal() as session:
        row = session.get(Referral, referral_id)
        if row:
            session.delete(row)
            session.commit()
    if storage_uri:
        try:
            delete_document(storage_uri)
        except Exception:  # noqa: BLE001 - cleanup is best effort
            print("note: diagnostic blob could not be removed.")

    if status == "needs_review":
        print("End-to-end pipeline succeeded.")
        return 0
    print(f"FAILED: pipeline ended in '{status}' instead of 'needs_review'.")
    return 1


def _list_referrals() -> int:
    from sqlalchemy import select

    from .database import Referral, SessionLocal

    with SessionLocal() as session:
        rows = session.scalars(select(Referral).order_by(Referral.created_at.desc())).all()
        if not rows:
            print("No referrals.")
        for row in rows:
            print(f"{row.id}  {row.status:<12} {row.progress:>3}%  {row.filename}")
    return 0


def _delete_referrals(targets: list[str]) -> int:
    from sqlalchemy import select

    from .database import Referral, SessionLocal
    from .storage import delete_document

    wanted = set(targets)
    purge_failed = "failed" in wanted
    with SessionLocal() as session:
        rows = session.scalars(select(Referral)).all()
        doomed = [
            row for row in rows if row.id in wanted or (purge_failed and row.status == "failed")
        ]
        if not doomed:
            print("Nothing matched.")
            return 1
        for row in doomed:
            uri = row.storage_uri
            print(f"deleting {row.id} ({row.status}) {row.filename}")
            session.delete(row)
            session.commit()
            if uri:
                try:
                    delete_document(uri)
                except Exception:  # noqa: BLE001 - cleanup is best effort
                    print(f"  note: blob for {row.id} could not be removed.")
    return 0


def main() -> int:
    if "--list" in sys.argv:
        return _list_referrals()
    if "--delete" in sys.argv:
        targets = sys.argv[sys.argv.index("--delete") + 1 :]
        if not targets:
            print("Usage: python -m referral.diagnose --delete <referral-id|failed> ...")
            return 1
        return _delete_referrals(targets)
    if "--e2e" in sys.argv:
        return _end_to_end()
    content = _sample_png()
    digest = "0" * 64
    _list_analyzers()
    checks = (
        ("Document Intelligence", settings.document_intelligence_endpoint, document_intelligence),
        ("Content Understanding", settings.content_understanding_endpoint, content_understanding),
    )
    failures = 0
    for name, endpoint, call in checks:
        print(f"\n=== {name} ===")
        print(f"endpoint: {endpoint or '(unset)'}")
        try:
            result = call(content, digest)
        except Exception as error:  # noqa: BLE001 - diagnostics report every failure
            failures += 1
            print(f"FAILED: {type(error).__name__}: {error}")
        else:
            print(f"OK: engine={result.engine} fields={sorted(result.fields)}")
    print("\nAll extraction endpoints reachable." if not failures else f"\n{failures} check(s) failed.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
