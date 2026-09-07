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


def _compare_rows(target: str) -> int:
    """Show a referral's extraction rows and which ones are flagged.

    The review UI highlights disagreements, and the first question anyone asks
    is why a given row is highlighted. This prints the same decision the UI
    renders, so it can be answered without a browser.
    """
    import json as _json

    from sqlalchemy import select

    from .database import Referral, SessionLocal

    with SessionLocal() as session:
        query = select(Referral).order_by(Referral.created_at.desc())
        row = (
            session.scalars(query).first()
            if target == "latest"
            else session.get(Referral, target)
        )
        if row is None:
            print(f"No referral matched {target!r}.")
            return 1
        if not row.comparison_json:
            print(f"{row.id} is {row.status}; no extraction recorded yet.")
            return 1
        comparison = _json.loads(row.comparison_json)
        print(f"{row.id}  {row.status}  {row.filename}")
        print(f"agreement: {comparison.get('agreementPercent')}%\n")
        for entry in comparison.get("rows", []):
            if entry.get("comparable") is False:
                flag = "prose "
            elif entry["matches"]:
                flag = "      "
            else:
                flag = "DIFFER"
            print(f"{flag}  {entry['field']}")
            print(f"          DI: {entry['documentIntelligence']}")
            print(f"          CU: {entry['contentUnderstanding']}")
    return 0


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


def _provision_analyzer() -> int:
    """Create the custom analyzer and show what it extracts."""
    from .analyzer import analyzer_definition, ensure_analyzer
    from .extractors import _token

    print(f"analyzer: {settings.content_understanding_analyzer}")
    print(f"completion: {settings.content_understanding_completion_deployment}")
    print(f"embedding: {settings.content_understanding_embedding_deployment}")
    print(f"fields: {', '.join(analyzer_definition()['fieldSchema']['fields'])}\n")
    ok = ensure_analyzer(_token)
    print("\nAnalyzer ready." if ok else "\nAnalyzer provisioning failed.")
    return 0 if ok else 1


def _score_samples() -> int:
    """Grade extraction against the known ground truth of the sample corpus.

    Pushes every sample through the real blob -> queue -> worker path, then
    reports how much of the ground truth each engine actually recovered. This
    only works from inside the VNet, which is where the AI endpoints live.
    """
    import hashlib
    import json
    import time
    from pathlib import Path

    from sqlalchemy import select

    from .database import Referral, SessionLocal
    from .extractors import _values_agree
    from .storage import delete_document, store_incoming

    corpus = Path(__file__).resolve().parent.parent / "samples"
    manifest_path = corpus / "manifest.json"
    if not manifest_path.exists():
        print(f"FAILED: no sample corpus at {manifest_path}.")
        return 1
    documents = json.loads(manifest_path.read_text(encoding="utf-8"))["documents"]

    totals = {"documentIntelligence": [0, 0], "contentUnderstanding": [0, 0]}
    for document in documents:
        filename = document["file"]
        print(f"\n=== {filename} ({document['channel']}, {document['difficulty']}) ===")
        content = (corpus / filename).read_bytes()
        digest = hashlib.sha256(content).hexdigest()

        # Clear any earlier run so the duplicate guard does not reject this one.
        with SessionLocal() as session:
            for stale in session.scalars(
                select(Referral).where(Referral.sha256 == digest)
            ).all():
                session.delete(stale)
            session.commit()

        # Drop the document into the landing zone and let the trigger do the rest.
        # Scoring runs through the same path a real upstream system takes.
        store_incoming(f"{int(time.time())}-{filename}", content)

        referral_id, status, comparison = None, "queued", None
        deadline = time.time() + 300
        while time.time() < deadline:
            time.sleep(5)
            with SessionLocal() as session:
                row = session.scalars(
                    select(Referral).where(Referral.sha256 == digest)
                ).first()
                if row is None:
                    continue
                referral_id, status, comparison = row.id, row.status, row.comparison_json
            if status not in {"queued", "processing"}:
                break

        if referral_id is None:
            print("FAILED: the document never reached the database.")
            continue

        with SessionLocal() as session:
            row = session.get(Referral, referral_id)
            if row:
                # Scoring is a test, so it cleans up after itself: the row and
                # the document it left in the processing container both go.
                if row.storage_uri:
                    try:
                        delete_document(row.storage_uri)
                    except Exception:  # noqa: BLE001 - cleanup is best effort
                        pass
                session.delete(row)
                session.commit()

        if status != "needs_review" or not comparison:
            print(f"FAILED: pipeline ended in '{status}'.")
            continue

        extracted = {entry["field"]: entry for entry in json.loads(comparison).get("rows", [])}
        for engine in ("documentIntelligence", "contentUnderstanding"):
            hits, scored, misses = 0, 0, []
            for field, expected in document["expected"].items():
                entry = extracted.get(field)
                if entry is None or not expected:
                    continue
                scored += 1
                actual = entry.get(engine, "")
                if _values_agree(actual, expected):
                    hits += 1
                else:
                    misses.append(f"{field}: expected {expected!r}, got {actual!r}")
            totals[engine][0] += hits
            totals[engine][1] += scored
            print(f"  {engine:>22}: {hits}/{scored} ({round(hits / scored * 100) if scored else 0}%)")
            for miss in misses:
                print(f"        - {miss}")
        if document["reviewerMustConfirm"]:
            print(f"  reviewer must confirm: {', '.join(document['reviewerMustConfirm'])}")

    print("\n=== Corpus totals ===")
    for engine, (hits, scored) in totals.items():
        print(f"  {engine:>22}: {hits}/{scored} ({round(hits / scored * 100) if scored else 0}%)")
    return 0


def _queue_depth() -> int:
    """Show what is sitting in the jobs queue, and in its poison queue.

    Between Event Grid and the function there is exactly one buffer. When a
    document does not appear in the review queue, this is the first place to
    look: a message here means the trigger fired and the function has not
    consumed it, an empty queue means the trigger never fired at all.
    """
    from azure.storage.queue import QueueClient

    from . import storage

    if not settings.queue_account_url:
        print("No queue account configured.")
        return 1
    for name in (settings.queue_name, f"{settings.queue_name}-poison"):
        client = QueueClient(
            account_url=settings.queue_account_url,
            queue_name=name,
            credential=storage.credential(),
        )
        try:
            depth = client.get_queue_properties().approximate_message_count
        except Exception as error:  # noqa: BLE001 - diagnostics report every failure
            print(f"{name}: unreachable ({type(error).__name__}: {error})")
            continue
        print(f"{name}: {depth} message(s)")
        for message in client.peek_messages(max_messages=5):
            body = (message.content or "")[:400]
            print(f"    inserted={message.inserted_on} dequeued={message.dequeue_count}")
            print(f"    {body}")
    return 0


def _drop(paths: list[str]) -> int:
    """Prove the pipeline is trigger-driven, not app-driven.

    Writes a document straight into the incoming container and waits. Nothing
    here calls the API or the function: if a referral appears, the blob write
    is what started it.
    """
    import time
    from pathlib import Path

    from sqlalchemy import select

    from . import storage
    from .database import Referral, SessionLocal, initialize_database

    initialize_database()

    def rows() -> list[Referral]:
        with SessionLocal() as session:
            return list(session.scalars(select(Referral).order_by(Referral.created_at.desc())).all())

    if not storage.using_azure_storage():
        print("No storage account configured. Set STORAGE_ACCOUNT_URL and try again.")
        return 1

    candidates = [Path(p) for p in paths] if paths else sorted(Path("samples").glob("*.pdf"))[:1]
    if not candidates:
        print("Nothing to drop. Pass a file path or run from a checkout with samples/.")
        return 1

    before = {row.id for row in rows()}
    dropped: list[str] = []
    for path in candidates:
        if not path.is_file():
            print(f"Not a file: {path}")
            return 1
        name = f"{int(time.time())}-{path.name}"
        storage.store_incoming(name, path.read_bytes(), {"droppedBy": "diagnose"})
        dropped.append(name)
        print(f"dropped  {name} -> {settings.incoming_container}/")

    print("\nWaiting for the workflow. No API call was made.")
    deadline = time.time() + 300
    seen: dict[str, str] = {}
    while time.time() < deadline:
        time.sleep(5)
        for row in rows():
            if row.id in before:
                continue
            if seen.get(row.id) != row.status:
                seen[row.id] = row.status
                print(f"  {row.filename}: {row.status}")
        settled = [s for s in seen.values() if s in {"needs_review", "failed"}]
        if len(settled) >= len(dropped):
            break

    if not seen:
        print("\nFAILED: nothing reached the database. The trigger did not fire.")
        print("Check the Event Grid subscription's delivery metrics and the queue depth.")
        return 1
    failed = [rid for rid, status in seen.items() if status == "failed"]
    if failed or len(seen) < len(dropped):
        print(f"\nFAILED: {len(seen)}/{len(dropped)} arrived, {len(failed)} failed.")
        return 1
    print(f"\nOK: {len(seen)} document(s) reached the review queue without an API call.")
    return 0


def _containers() -> int:
    """Show what is sitting in each container of the landing zone.

    The container a document sits in *is* its state: ``incoming`` means nobody
    has claimed it, ``processing`` means the function owns it, and ``archive``
    or ``failed`` is where it ended up. Storage is firewalled to the VNet, so
    this is the supported way to look.
    """
    from . import storage

    if not storage.using_azure_storage():
        print("Local filesystem backend; nothing to list in Azure.")
        return 1
    service = storage._service()
    for container in (
        settings.incoming_container,
        settings.processing_container,
        settings.archive_container,
        settings.failed_container,
    ):
        client = service.get_container_client(container)
        names = [blob.name for blob in client.list_blobs()]
        print(f"\n{container}: {len(names)} blob(s)")
        for name in names[:20]:
            print(f"  {name}")
        if len(names) > 20:
            print(f"  ... and {len(names) - 20} more")
    return 0


def _review(args: list[str]) -> int:
    """Approve or return a referral through the same path the reviewer's click takes.

    Boxes 6 and 7: the decision moves the document to its final container and
    posts a business event to the Logic App. Running it here proves the handoff
    works without needing a browser session against Easy Auth.
    """
    from .database import Referral, SessionLocal
    from .review import ReviewRejected, decide

    if not args:
        print("Usage: python -m referral.diagnose --review <referral-id> [approve|return]")
        return 1
    referral_id = args[0]
    approved = (args[1] if len(args) > 1 else "approve").lower() != "return"
    try:
        decided = decide(referral_id, approved, "Reviewed from the diagnostics CLI.", "diagnostics")
    except ReviewRejected as rejected:
        print(f"FAILED ({rejected.status}): {rejected.message}")
        return 1
    print(f"status: {decided['status']}")
    # The API response deliberately withholds the storage location, so read the
    # row directly to prove the document actually moved to its final container.
    with SessionLocal() as session:
        print(f"document: {session.get(Referral, referral_id).storage_uri}")
    if not settings.logic_app_url:
        print("WARNING: no Logic App configured, so Box 7 was not notified.")
        return 1
    print("Logic App notified. Check its run history for the matching run.")
    return 0


def main() -> int:
    if "--list" in sys.argv:
        return _list_referrals()
    if "--compare" in sys.argv:
        rest = sys.argv[sys.argv.index("--compare") + 1 :]
        return _compare_rows(rest[0] if rest else "latest")
    if "--drop" in sys.argv:
        return _drop(sys.argv[sys.argv.index("--drop") + 1 :])
    if "--review" in sys.argv:
        return _review(sys.argv[sys.argv.index("--review") + 1 :])
    if "--containers" in sys.argv:
        return _containers()
    if "--queue" in sys.argv:
        return _queue_depth()
    if "--score" in sys.argv:
        return _score_samples()
    if "--analyzer" in sys.argv:
        return _provision_analyzer()
    if "--delete" in sys.argv:
        targets = sys.argv[sys.argv.index("--delete") + 1 :]
        if not targets:
            print("Usage: python -m referral.diagnose --delete <referral-id|failed> ...")
            return 1
        return _delete_referrals(targets)
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
            print(f"OK: engine={result.engine}")
            for field, value in result.fields.items():
                score = result.confidence.get(field, 0.0)
                print(f"    {field:>22}: {value[:60]!r} ({score:.0%})")
    print("\nAll extraction endpoints reachable." if not failures else f"\n{failures} check(s) failed.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
