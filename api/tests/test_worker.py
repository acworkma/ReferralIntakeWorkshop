from dataclasses import dataclass, field

import pytest

from referral import worker


@dataclass
class FakeMessage:
    content: str
    dequeue_count: int = 1


@dataclass
class FakeQueue:
    sent: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)

    def send_message(self, content: str) -> None:
        self.sent.append(content)

    def delete_message(self, message: FakeMessage) -> None:
        self.deleted.append(message.content)


def test_successful_message_is_deleted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(worker, "process_referral", lambda referral_id: None)
    jobs, poison = FakeQueue(), FakeQueue()

    worker._handle(FakeMessage("abc"), jobs, poison)

    assert jobs.deleted == ["abc"]
    assert poison.sent == []


def test_failure_below_threshold_is_left_for_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(referral_id: str) -> None:
        raise RuntimeError("extraction failed")

    monkeypatch.setattr(worker, "process_referral", boom)
    jobs, poison = FakeQueue(), FakeQueue()

    worker._handle(FakeMessage("abc", dequeue_count=1), jobs, poison)

    # Not deleted, so the visibility timeout returns it for another attempt.
    assert jobs.deleted == []
    assert poison.sent == []


def test_failure_at_threshold_moves_to_poison(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(referral_id: str) -> None:
        raise RuntimeError("extraction failed")

    marked: list[str] = []
    monkeypatch.setattr(worker, "process_referral", boom)
    monkeypatch.setattr(worker, "mark_failed", marked.append)
    jobs, poison = FakeQueue(), FakeQueue()

    worker._handle(
        FakeMessage("abc", dequeue_count=worker.settings.queue_max_dequeue), jobs, poison
    )

    assert marked == ["abc"]
    assert poison.sent == ["abc"]
    assert jobs.deleted == ["abc"]


def test_retryable_failure_leaves_the_referral_processable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed attempt must not mark the referral failed, or retries become pointless."""
    from referral.database import Referral, SessionLocal
    from referral.processing import process_referral

    referral_id = "retry-me"
    with SessionLocal() as session:
        session.add(
            Referral(
                id=referral_id,
                filename="retry.pdf",
                sha256="f" * 64,
                status="queued",
                progress=5,
                submitted_by="tester",
                storage_uri=None,
            )
        )
        session.commit()

    monkeypatch.setattr(
        "referral.processing.compare", lambda *_: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    monkeypatch.setattr("referral.processing._local_payloads", {referral_id: b"%PDF x"})

    with pytest.raises(RuntimeError):
        process_referral(referral_id)

    with SessionLocal() as session:
        assert session.get(Referral, referral_id).status == "processing"

    # A later successful attempt can still complete it.
    monkeypatch.setattr("referral.processing.compare", lambda *_: {"rows": []})
    monkeypatch.setattr("referral.processing._local_payloads", {referral_id: b"%PDF x"})
    process_referral(referral_id)

    with SessionLocal() as session:
        assert session.get(Referral, referral_id).status == "needs_review"


def test_worker_is_disabled_without_a_queue_account() -> None:
    instance = worker.QueueWorker()
    instance.start()
    assert instance._thread is None
    instance.stop()
