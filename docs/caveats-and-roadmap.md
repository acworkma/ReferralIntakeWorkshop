# Caveats and future integrations

## Regional, preview, and cost caveats

- Azure AI Content Understanding APIs and analyzer names evolve and may remain preview in some regions. The template deliberately separates `aiFallbackLocation` (default `westus3`) from the primary `eastus2`. Confirm availability, quota, responsible-AI terms, API version, and private-link support before deployment. The code currently calls `2025-05-01-preview`; pin a validated version before production. See [Content Understanding overview](https://learn.microsoft.com/azure/ai-services/content-understanding/overview).
- Document Intelligence uses REST `2024-11-30`; model output in this generic adapter is intentionally mapped to review-required fields. Build a versioned custom model/schema for a real implementation. See [Document Intelligence](https://learn.microsoft.com/azure/ai-services/document-intelligence/overview).
- Several Bicep resources use preview API versions where the stable API lacks the required control. Re-run `az bicep build` and what-if with the current CLI and validate provider support in the target subscription.
- Private endpoints are regional resources. A fallback-region AI endpoint connected to an east-US spoke introduces cross-region latency/egress and a regional dependency.
- Container Apps internal environments require adequate delegated subnet capacity. Functions Premium, Premium ACR, Azure SQL, private endpoints/DNS, Defender plans, AI transactions, Log Analytics ingestion, and an always-running VM/ACA replica incur charges even while idle. The jumpbox is optional (`deployJumpbox=false`) and should be deallocated or omitted when not needed.
- The Logic App is disabled and has no production connector. The dashboard is a baseline, not a service-level objective.

Review [Azure retail pricing](https://azure.microsoft.com/pricing/), [region availability](https://azure.microsoft.com/explore/global-infrastructure/products-by-region/), and [Azure service health](https://learn.microsoft.com/azure/service-health/overview) during planning.

## Explicitly future-only

The repository does **not** implement any of the following. Each needs an approved data contract, threat model, identity design, retention policy, and separate deployment:

- external referral, case-management, scheduling, or electronic-record systems;
- SharePoint document libraries or Microsoft Graph ingestion;
- Dataverse tables, model-driven apps, or Power Platform connectors;
- Azure AI Search indexes or enrichment pipelines;
- Cosmos DB, vector stores, grounding/RAG, agents, or Copilot experiences.

Relevant starting points: [Microsoft Graph SharePoint](https://learn.microsoft.com/graph/api/resources/sharepoint), [Dataverse](https://learn.microsoft.com/power-apps/maker/data-platform/data-platform-intro), [Azure AI Search security](https://learn.microsoft.com/azure/search/search-security-overview), [Cosmos DB security](https://learn.microsoft.com/azure/cosmos-db/security), and [RAG guidance](https://learn.microsoft.com/azure/search/retrieval-augmented-generation-overview).
