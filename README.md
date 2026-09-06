# Referral Intake Reference

A public-workspace-safe reference implementation for receiving **synthetic** referral documents, comparing Azure AI Document Intelligence with Azure AI Content Understanding, and routing discrepancies through human approval.

This is an Azure workshop: every component runs as an Azure resource (Container Apps, Functions, SQL, Storage, Document Intelligence, Content Understanding) behind a private VNet, and the only supported way to run it is to deploy it to Azure.

## Quick start

Prerequisites: Azure CLI with current Bicep CLI, and Owner/User Access Administrator plus Contributor on the target subscription.

```powershell
az bicep upgrade
.\scripts\register-entra-app.ps1
az deployment sub create --name referral-deploy --location eastus2 `
  --template-file infra\main.bicep --parameters infra\main.bicepparam
.\scripts\set-entra-redirect-uris.ps1
```

See [deployment instructions](docs/deployment.md) for full prerequisites, the what-if step, and independent component deployment.

## Repository map

| Path | Purpose |
|---|---|
| `web/` | React, Vite, and TypeScript operator experience |
| `api/` | FastAPI application, Azure Functions HTTP adapter, and queue worker |
| `infra/` | Modular Bicep and independently deployable entry points |
| `docs/` | Architecture, security, deployment, operations, and caveats |
| `samples/` | Synthetic sample referral documents for exercising the upload flow |
| `.github/workflows/` | Validation and OIDC-based image/deployment delivery |

Start with [deployment instructions](docs/deployment.md), [architecture](docs/architecture.md), and [security](docs/security.md).

> **Safety:** This repository contains no real referral records. Uploads must be synthetic, carry the `X-Data-Classification: synthetic` header, and have a filename beginning with `synthetic-`. Never use production or personal data. See [`samples/`](samples/README.md) for ready-to-use synthetic documents covering every intake channel.

All Azure examples use `rg-referralintake` and `eastus2` by default. Names are parameterized and suffixed for global uniqueness.
