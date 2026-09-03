import base64
import json

from fastapi import Header, HTTPException

from .config import settings


def current_user(x_ms_client_principal: str | None = Header(default=None)) -> str:
    if x_ms_client_principal:
        try:
            principal = json.loads(base64.b64decode(x_ms_client_principal))
            claims = {claim["typ"]: claim["val"] for claim in principal.get("claims", [])}
            return claims.get("preferred_username") or claims.get("name") or "entra-user"
        except (ValueError, KeyError, TypeError):
            raise HTTPException(401, "Invalid App Service authentication principal.") from None
    if settings.local_mock_identity:
        return "local.synthetic.reviewer@example.invalid"
    raise HTTPException(401, "Microsoft Entra ID authentication is required.")
