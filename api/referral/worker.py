"""Background consumer for the referral-jobs queue.

The API container owns this worker so that a deployed environment can process
referrals without depending on a separately published Function App. Container
Apps runs at least one replica, and the queue guarantees a message is handed to
exactly one replica at a time, so running the worker alongside the API is safe
when the app scales out.
"""

import logging
import threading

from azure.identity import DefaultAzureCredential
from azure.storage.queue import QueueClient

from .config import settings
from .processing import mark_failed, process_referral

logger = logging.getLogger(__name__)


def _queue_client(name: str) -> QueueClient:
    return QueueClient(
        account_url=settings.queue_account_url,
        queue_name=name,
        credential=DefaultAzureCredential(),
    )


def _handle(message, jobs: QueueClient, poison: QueueClient) -> None:
    referral_id = message.content
    try:
        process_referral(referral_id)
    except Exception:
        # process_referral already marked the referral failed before re-raising.
        if message.dequeue_count >= settings.queue_max_dequeue:
            logger.exception(
                "Referral %s failed %s times; moving to the poison queue.",
                referral_id,
                message.dequeue_count,
            )
            mark_failed(referral_id)
            poison.send_message(referral_id)
            jobs.delete_message(message)
        else:
            # Leave the message invisible until the visibility timeout expires
            # so the next attempt happens automatically.
            logger.exception("Referral %s failed; will retry.", referral_id)
        return
    jobs.delete_message(message)
    logger.info("Referral %s processed.", referral_id)


def _run(stop: threading.Event) -> None:
    jobs = _queue_client(settings.queue_name)
    poison = _queue_client(f"{settings.queue_name}-poison")
    logger.info("Referral queue worker started on %s.", settings.queue_name)
    while not stop.is_set():
        try:
            batch = jobs.receive_messages(
                messages_per_page=settings.queue_batch_size,
                visibility_timeout=settings.queue_visibility_timeout,
            )
            received = False
            for message in batch:
                received = True
                _handle(message, jobs, poison)
                if stop.is_set():
                    break
            if received:
                continue
        except Exception:
            logger.exception("Referral queue poll failed; retrying.")
        stop.wait(settings.queue_poll_seconds)
    logger.info("Referral queue worker stopped.")


class QueueWorker:
    def __init__(self) -> None:
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not (settings.queue_worker_enabled and settings.queue_account_url):
            logger.info("Referral queue worker disabled.")
            return
        self._thread = threading.Thread(
            target=_run, args=(self._stop,), name="referral-queue-worker", daemon=True
        )
        self._thread.start()

    @property
    def alive(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=settings.queue_shutdown_seconds)
            self._thread = None
