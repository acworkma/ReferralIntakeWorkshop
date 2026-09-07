"""Business-event notifications, handed off to the Logic App.

Everything here is deliberately thin. The decisions a non-developer would want
to change - who hears about a failure, where an approved referral is routed -
belong in the Logic App designer, not in this file. The code's only job is to
say what happened and let the workflow decide what to do about it.
"""

import logging

import httpx

from .config import settings

logger = logging.getLogger(__name__)

TIMEOUT = httpx.Timeout(10.0, connect=5.0)


def notify(event: str, payload: dict) -> bool:
    """Posts a business event to the Logic App. Never raises.

    A notification failing must not fail the referral it describes, so this
    reports success as a boolean and logs rather than propagating.
    """
    if not settings.logic_app_url:
        logger.info("No Logic App configured; skipping '%s' notification.", event)
        return False
    try:
        response = httpx.post(
            settings.logic_app_url,
            json={"event": event, **payload},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
    except httpx.HTTPError:
        logger.warning("Logic App rejected the '%s' notification.", event, exc_info=True)
        return False
    return True
