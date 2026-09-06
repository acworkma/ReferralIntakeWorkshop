#Requires -Version 7.0
<#
.SYNOPSIS
    Patches the Entra app registration's redirect URIs after the Container
    Apps web app and Function App have been deployed (their hostnames aren't
    known until after `az deployment sub create` completes).

.DESCRIPTION
    Run this after infra/main.bicep has been deployed (and after
    scripts/register-entra-app.ps1 has already created the app). It
    auto-discovers the ACA web app and Function App hostnames by the naming
    convention used in infra/modules/compute.bicep
    (ca-<workload>-web-<env>, func-<workload>-<env>), finds the app
    registration created by register-entra-app.ps1, and adds the two
    Easy Auth callback redirect URIs:

        https://<web fqdn>/.auth/login/aad/callback
        https://<function hostname>/.auth/login/aad/callback

    Existing redirect URIs on the app are preserved; this only adds the two
    above if missing (safe to re-run after every deployment).

    Same directory-level permission prerequisite as
    scripts/register-entra-app.ps1 applies here.

.PARAMETER ResourceGroupName
    Resource group containing the deployed workload. Default: rg-referralintake.

.PARAMETER WorkloadName
    Matches infra/main.bicepparam's workloadName. Default: referralintake.

.PARAMETER EnvironmentName
    Matches infra/main.bicepparam's environmentName. Default: dev.

.PARAMETER WebFqdn
    Override the auto-discovered Container Apps web hostname.

.PARAMETER FunctionHostName
    Override the auto-discovered Function App hostname.
#>
[CmdletBinding()]
param(
    [string]$ResourceGroupName = 'rg-referralintake',
    [string]$WorkloadName = 'referralintake',
    [string]$EnvironmentName = 'dev',
    [string]$WebFqdn,
    [string]$FunctionHostName
)

$ErrorActionPreference = 'Stop'

$account = az account show 2>$null | ConvertFrom-Json
if (-not $account) {
    throw "Not logged in to Azure CLI. Run 'az login' (or federate the CI identity) before running this script."
}

$displayName = "app-$WorkloadName-$EnvironmentName"
$app = az ad app list --display-name $displayName --query '[0]' -o json | ConvertFrom-Json
if (-not $app) {
    throw "No app registration named '$displayName' found. Run scripts/register-entra-app.ps1 first."
}
Write-Host "Found app registration: appId=$($app.appId)"

if (-not $WebFqdn) {
    $webAppName = "ca-$WorkloadName-web-$EnvironmentName"
    Write-Host "Discovering Container Apps hostname for '$webAppName'..."
    $WebFqdn = az containerapp show -g $ResourceGroupName -n $webAppName `
        --query 'properties.configuration.ingress.fqdn' -o tsv
}

if (-not $FunctionHostName) {
    $functionAppName = "func-$WorkloadName-$EnvironmentName"
    Write-Host "Discovering Function App hostname for '$functionAppName'..."
    $FunctionHostName = az functionapp show -g $ResourceGroupName -n $functionAppName `
        --query 'defaultHostName' -o tsv
}

if (-not $WebFqdn -or -not $FunctionHostName) {
    throw "Could not resolve web/function hostnames. Confirm the workload is deployed to '$ResourceGroupName', or pass -WebFqdn/-FunctionHostName explicitly."
}

$desiredRedirectUris = @(
    "https://$WebFqdn/.auth/login/aad/callback"
    "https://$FunctionHostName/.auth/login/aad/callback"
)

$existingRedirectUris = @()
if ($app.web -and $app.web.redirectUris) {
    $existingRedirectUris = @($app.web.redirectUris)
}

$mergedRedirectUris = @($existingRedirectUris + $desiredRedirectUris | Select-Object -Unique)

$added = $desiredRedirectUris | Where-Object { $_ -notin $existingRedirectUris }
if ($added.Count -eq 0) {
    Write-Host "Redirect URIs already up to date on '$displayName'."
}
else {
    Write-Host "Adding redirect URI(s):"
    $added | ForEach-Object { Write-Host "  $_" }
    az ad app update --id $app.appId --web-redirect-uris $mergedRedirectUris | Out-Null
    Write-Host "Updated app registration '$displayName' redirect URIs."
}
