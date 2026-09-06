from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from azure.storage.blob import BlobClient
from azure.storage.queue import QueueClient

from .config import settings


def store_document(referral_id: str, filename: str, content: bytes) -> str | None:
    if not settings.storage_account_url:
        return None
    client = BlobServiceClient(settings.storage_account_url, credential=DefaultAzureCredential())
    blob = client.get_blob_client("referrals", f"{referral_id}/{filename}")
    blob.upload_blob(content, overwrite=False)
    return blob.url


def load_document(storage_uri: str) -> bytes:
    return BlobClient.from_blob_url(
        storage_uri, credential=DefaultAzureCredential()
    ).download_blob(max_concurrency=2).readall()


def enqueue(referral_id: str) -> bool:
    if not settings.queue_account_url:
        return False
    queue = QueueClient(
        account_url=settings.queue_account_url,
        queue_name=settings.queue_name,
        credential=DefaultAzureCredential(),
    )
    queue.send_message(referral_id)
    return True
