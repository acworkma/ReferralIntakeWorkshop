"""Provisioning for the custom Content Understanding analyzer.

The Content Understanding account has ``publicNetworkAccess: Disabled``, so
the analyzer cannot be created from a workstation or from CI. It has to be
created from inside the VNet, which in practice means from this container.
The API calls :func:`ensure_analyzer` once at startup; it is idempotent and
safe to run on every replica and every revision.
"""

from __future__ import annotations

import logging

import httpx

from .config import settings
from .schema import analyzer_field_schema

logger = logging.getLogger(__name__)

_ANALYZER_DESCRIPTION = "HomeCare referral intake extraction for the workshop."


def analyzer_definition() -> dict:
    return {
        "description": _ANALYZER_DESCRIPTION,
        "baseAnalyzerId": "prebuilt-document",
        # Content Understanding requires both a completion and an embedding
        # default before it will accept a custom analyzer, and both deployments
        # must use the GlobalStandard SKU.
        "models": {
            "completion": settings.content_understanding_completion_model,
            "embedding": settings.content_understanding_embedding_model,
        },
        "config": {
            "returnDetails": True,
            # Required for the per-field confidence the comparison table shows.
            "estimateFieldSourceAndConfidence": True,
            "tableFormat": "html",
        },
        "fieldSchema": analyzer_field_schema(),
    }


def _base_url() -> str:
    return settings.content_understanding_endpoint.rstrip("/") + "/contentunderstanding"


def _wait_for_operation(url: str, headers: dict[str, str]) -> None:
    for _ in range(60):
        response = httpx.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        payload = response.json()
        status = str(payload.get("status", "")).lower()
        if status == "succeeded":
            return
        if status == "failed":
            raise RuntimeError(f"Analyzer provisioning failed: {payload}")
        import time

        time.sleep(2)
    raise TimeoutError("Analyzer provisioning timed out.")


def ensure_defaults(headers: dict[str, str]) -> None:
    """Point the account at the model deployments the analyzer needs.

    Without this the service has no completion model to call and analyzer
    creation fails with a model-deployment error. The embedding default is
    attempted separately: not every account exposes an embedding deployment
    to Content Understanding, and extraction analyzers do not require one.
    """
    url = f"{_base_url()}/defaults?api-version={settings.content_understanding_api_version}"
    payload = {
        "modelDeployments": {
            settings.content_understanding_completion_model: (
                settings.content_understanding_completion_deployment
            ),
            settings.content_understanding_embedding_model: (
                settings.content_understanding_embedding_deployment
            ),
        }
    }
    response = httpx.patch(
        url,
        headers={**headers, "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    if response.status_code >= 400:
        logger.warning(
            "Could not set Content Understanding defaults (%s): %s",
            response.status_code,
            response.text[:300],
        )
        return
    logger.info("Content Understanding default model deployments configured.")


def ensure_analyzer(token_provider) -> bool:
    """Create or update the custom analyzer. Returns True when it is usable."""
    if not settings.content_understanding_endpoint:
        logger.info("No Content Understanding endpoint configured; skipping analyzer setup.")
        return False
    analyzer_id = settings.content_understanding_analyzer
    if analyzer_id.startswith("prebuilt-"):
        logger.info("Analyzer %s is prebuilt; nothing to provision.", analyzer_id)
        return True

    headers = {"Authorization": f"Bearer {token_provider()}"}
    version = settings.content_understanding_api_version
    url = f"{_base_url()}/analyzers/{analyzer_id}?api-version={version}"

    try:
        ensure_defaults(headers)
        definition = analyzer_definition()
        existing = httpx.get(url, headers=headers, timeout=30)
        if existing.status_code == 200:
            if existing.json().get("fieldSchema") == definition["fieldSchema"]:
                logger.info("Content Understanding analyzer %s is up to date.", analyzer_id)
                return True
            # Analyzers are immutable once created, so a changed field schema
            # means editing schema.py silently has no effect until the old one
            # is removed. Replace it instead of serving stale extraction.
            logger.info("Field schema changed; replacing analyzer %s.", analyzer_id)
            deleted = httpx.delete(url, headers=headers, timeout=60)
            if deleted.status_code >= 400 and deleted.status_code != 404:
                raise RuntimeError(
                    f"Analyzer DELETE failed ({deleted.status_code}): {deleted.text[:1200]}"
                )

        logger.info("Creating Content Understanding analyzer %s.", analyzer_id)
        response = httpx.put(
            url,
            headers={**headers, "Content-Type": "application/json"},
            json=definition,
            timeout=60,
        )
        if response.status_code >= 400:
            # The status line alone is useless here; the body names the field
            # or model that the service rejected.
            raise RuntimeError(
                f"Analyzer PUT failed ({response.status_code}): {response.text[:1200]}"
            )
        operation = response.headers.get("operation-location")
        if operation:
            _wait_for_operation(operation, headers)
        logger.info("Content Understanding analyzer %s is ready.", analyzer_id)
        return True
    except Exception:
        # A missing analyzer must not stop the API from serving traffic; the
        # extractor surfaces the failure per referral instead.
        logger.exception("Could not provision Content Understanding analyzer %s.", analyzer_id)
        return False
