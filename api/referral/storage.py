"""The landing zone: blob and queue access behind one interface.

A referral's container is its workflow state. It lands in ``incoming``, moves to
``processing`` while the orchestration function works on it, and finishes in
``archive`` or ``failed``. Keeping that state in the blob path rather than only
in a database column is what makes the pipeline legible from the portal.

Two backends implement the same surface. Azure Blob Storage is the real one. A
filesystem backend stands in when no storage account is configured, so the same
``referral.intake`` code path can be exercised on a laptop and in tests rather
than having a second, untested implementation for local development.
"""

from functools import lru_cache
from pathlib import Path
import shutil
from urllib.parse import unquote, urlparse

from azure.identity import DefaultAzureCredential
from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import BlobClient, BlobServiceClient

from .config import settings

LOCAL_SCHEME = "file"


@lru_cache(maxsize=1)
def credential() -> DefaultAzureCredential:
    return DefaultAzureCredential()


def _service() -> BlobServiceClient:
    return BlobServiceClient(settings.storage_account_url, credential=credential())


def using_azure_storage() -> bool:
    return bool(settings.storage_account_url)


def _local_path(container: str, blob_name: str) -> Path:
    return Path(settings.local_landing_zone_root).resolve() / container / blob_name


def _local_uri(path: Path) -> str:
    return path.resolve().as_uri()


def _is_local(storage_uri: str) -> bool:
    return urlparse(storage_uri).scheme == LOCAL_SCHEME


def _local_target(storage_uri: str) -> Path:
    return Path(url2path(storage_uri))


def url2path(storage_uri: str) -> str:
    parsed = urlparse(storage_uri)
    path = unquote(parsed.path)
    # Windows file URIs carry the drive letter as a leading path segment.
    return path[1:] if len(path) > 2 and path[2] == ":" else path


def split_blob_uri(storage_uri: str) -> tuple[str, str]:
    """Returns the (container, blob name) a storage URI points at."""
    if _is_local(storage_uri):
        relative = Path(url2path(storage_uri)).relative_to(
            Path(settings.local_landing_zone_root).resolve()
        )
        return relative.parts[0], "/".join(relative.parts[1:])
    path = unquote(urlparse(storage_uri).path).lstrip("/")
    container, _, name = path.partition("/")
    return container, name


def store_incoming(
    filename: str, content: bytes, metadata: dict[str, str] | None = None
) -> str:
    """Drops a document into the landing zone exactly as an upstream system would.

    Nothing else happens here. The blob write is what starts the workflow.
    """
    if not using_azure_storage():
        target = _local_path(settings.incoming_container, filename)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        _write_local_metadata(target, metadata or {})
        return _local_uri(target)
    blob = _service().get_blob_client(settings.incoming_container, filename)
    blob.upload_blob(content, overwrite=True, metadata=metadata or {})
    return blob.url


def load_document(storage_uri: str) -> bytes:
    if _is_local(storage_uri):
        target = _local_target(storage_uri)
        if not target.exists():
            raise ResourceNotFoundError(f"{storage_uri} does not exist.")
        return target.read_bytes()
    return (
        BlobClient.from_blob_url(storage_uri, credential=credential())
        .download_blob(max_concurrency=2)
        .readall()
    )


def blob_metadata(storage_uri: str) -> dict[str, str]:
    if _is_local(storage_uri):
        sidecar = _metadata_path(_local_target(storage_uri))
        if not sidecar.exists():
            return {}
        return dict(
            line.split("=", 1)
            for line in sidecar.read_text(encoding="utf-8").splitlines()
            if "=" in line
        )
    properties = BlobClient.from_blob_url(
        storage_uri, credential=credential()
    ).get_blob_properties()
    return properties.metadata or {}


def delete_document(storage_uri: str) -> None:
    if _is_local(storage_uri):
        target = _local_target(storage_uri)
        _metadata_path(target).unlink(missing_ok=True)
        target.unlink(missing_ok=True)
        return
    BlobClient.from_blob_url(storage_uri, credential=credential()).delete_blob(
        delete_snapshots="include"
    )


def move_document(storage_uri: str, destination_container: str, blob_name: str) -> str:
    """Moves a document between landing zone containers, advancing its state.

    Copy then delete rather than a server side copy: uploads are capped well
    below the size where streaming the bytes through the caller matters, and
    this avoids needing a SAS to authorize the copy source.
    """
    if _is_local(storage_uri):
        source = _local_target(storage_uri)
        target = _local_path(destination_container, blob_name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(target))
        source_metadata = _metadata_path(source)
        if source_metadata.exists():
            shutil.move(str(source_metadata), str(_metadata_path(target)))
        return _local_uri(target)

    source_blob = BlobClient.from_blob_url(storage_uri, credential=credential())
    properties = source_blob.get_blob_properties()
    content = source_blob.download_blob(max_concurrency=2).readall()
    target_blob = _service().get_blob_client(destination_container, blob_name)
    target_blob.upload_blob(content, overwrite=True, metadata=properties.metadata or {})
    source_blob.delete_blob(delete_snapshots="include")
    return target_blob.url


def _metadata_path(target: Path) -> Path:
    return target.with_name(f"{target.name}.metadata")


def _write_local_metadata(target: Path, metadata: dict[str, str]) -> None:
    sidecar = _metadata_path(target)
    if not metadata:
        sidecar.unlink(missing_ok=True)
        return
    sidecar.write_text(
        "\n".join(f"{key}={value}" for key, value in metadata.items()), encoding="utf-8"
    )
