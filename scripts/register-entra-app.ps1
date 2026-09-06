#Requires -Version 7.0
<#
.SYNOPSIS
    Idempotently finds or creates the Microsoft Entra app registration used by
    Container Apps and Azure Functions "Easy Auth" (see infra/modules/compute.bicep).

.DESCRIPTION
    App registrations are Microsoft Graph objects, not ARM resources, so Bicep
    cannot create them directly. This script uses the caller's own `az cli`
    session (the same identity already deploying the subscription) to
    find-or-create a stable app registration by display name, set its
    identifier URI, and ensure a service principal exists.

    Redirect URIs depend on the Container Apps/Function hostnames, which are
    only known after the first deployment, so they are NOT set here. Run
    scripts/set-entra-redirect-uris.ps1 after `az deployment sub create`
    completes.

    PREREQUISITE: the identity running this script (a human via `az login`,
    or a CI OIDC service principal) must hold a directory-level role capable
    of managing app registrations, e.g. the "Application Administrator" or
    "Cloud Application Administrator" Entra role, or the Microsoft Graph
    `Application.ReadWrite.All` permission. This is a directory permission,
    separate from Azure RBAC, and cannot be granted through Bicep/ARM.

.PARAMETER WorkloadName
    Matches infra/main.bicepparam's workloadName. Default: referralintake.

.PARAMETER EnvironmentName
    Matches infra/main.bicepparam's environmentName. Default: dev.

.OUTPUTS
    Writes the app's client (application) ID to the pipeline as the last
    output so callers can capture it directly, e.g.:

        $env:ENTRA_CLIENT_ID = .\scripts\register-entra-app.ps1

    All human-readable status is written with Write-Host so it does not
    pollute the captured pipeline output.
#>
[CmdletBinding()]
param(
    [string]$WorkloadName = 'referralintake',
    [string]$EnvironmentName = 'dev'
)

$ErrorActionPreference = 'Stop'

function Assert-AzCliLoggedIn {
    $account = az account show 2>$null | ConvertFrom-Json
    if (-not $account) {
        throw "Not logged in to Azure CLI. Run 'az login' (or federate the CI identity) before running this script."
    }
    return $account
}

$account = Assert-AzCliLoggedIn
Write-Host "Using Azure CLI identity: $($account.user.name) (tenant $($account.tenantId))"

$displayName = "app-$WorkloadName-$EnvironmentName"
Write-Host "Looking for existing app registration '$displayName'..."

$existing = az ad app list --display-name $displayName --query '[0]' -o json | ConvertFrom-Json

if ($existing) {
    Write-Host "Found existing app registration: appId=$($existing.appId)"
    $appId = $existing.appId
}
else {
    Write-Host "No existing app registration found. Creating '$displayName'..."
    $created = az ad app create `
        --display-name $displayName `
        --sign-in-audience AzureADMyOrg `
        -o json | ConvertFrom-Json
    $appId = $created.appId
    Write-Host "Created app registration: appId=$appId"
}

# Idempotent: safe to (re)apply every run.
Write-Host "Setting identifier URI to api://$appId..."
az ad app update --id $appId --identifier-uris "api://$appId" | Out-Null

Write-Host "Ensuring a service principal exists for the app..."
$sp = az ad sp list --filter "appId eq '$appId'" --query '[0]' -o json | ConvertFrom-Json
if (-not $sp) {
    az ad sp create --id $appId | Out-Null
    Write-Host "Created service principal for appId=$appId"
}
else {
    Write-Host "Service principal already exists for appId=$appId"
}

Write-Host ""
Write-Host "Set this before deploying infra (infra/main.bicepparam reads it via readEnvironmentVariable):"
Write-Host "  `$env:ENTRA_CLIENT_ID = '$appId'"
Write-Host ""
Write-Host "After 'az deployment sub create' finishes, run scripts/set-entra-redirect-uris.ps1 to patch redirect URIs."

# Last pipeline output: the client ID, for `$env:ENTRA_CLIENT_ID = .\scripts\register-entra-app.ps1`.
$appId
