# Referral Intake Reference

A public-workspace-safe reference implementation for receiving **synthetic** referral documents, comparing Azure AI Document Intelligence with Azure AI Content Understanding, and routing discrepancies through human approval.

## Quick start

Prerequisites: Docker Desktop with Compose.

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Open `http://localhost:5173`. Local development uses an intentionally obvious mock identity and synthetic extraction. The Azure Bicep deployment disables both modes, and the API refuses them when running under the Azure Functions environment.

## Repository map

| Path | Purpose |
|---|---|
| `web/` | React, Vite, and TypeScript operator experience |
| `api/` | FastAPI application, Azure Functions HTTP adapter, and queue worker |
| `infra/` | Modular Bicep and independently deployable entry points |
| `docs/` | Architecture, security, deployment, operations, and caveats |
| `.github/workflows/` | Validation and OIDC-based image/deployment delivery |

Start with [deployment instructions](docs/deployment.md), [architecture](docs/architecture.md), and [security](docs/security.md).

> **Safety:** This repository contains no real referral records. Uploads must be synthetic, carry the `X-Data-Classification: synthetic` header, and have a filename beginning with `synthetic-`. Never use production or personal data.

## Developer commands

```powershell
docker compose up --build
python -m pytest api\tests
cd web; npm install; npm run check
```

All Azure examples use `rg-referralintake` and `eastus2` by default. Names are parameterized and suffixed for global uniqueness.
