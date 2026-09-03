using './main.bicep'

param resourceGroupName = 'rg-referralintake'
param location = 'eastus2'
param sqlLocation = 'centralus'
param aiFallbackLocation = 'westus3'
param workloadName = 'referralintake'
param environmentName = 'dev'
param acrPublicNetworkAccess = true
param deployJumpbox = true

// Supply these at deployment time or copy this file outside source control.
param uniqueSuffix = readEnvironmentVariable('AZURE_UNIQUE_SUFFIX')
param entraClientId = readEnvironmentVariable('ENTRA_CLIENT_ID')
param sqlAdminGroupObjectId = readEnvironmentVariable('SQL_ADMIN_GROUP_OBJECT_ID')
param jumpboxAdminGroupObjectId = readEnvironmentVariable('JUMPBOX_ADMIN_GROUP_OBJECT_ID')
param jumpboxAdminPassword = readEnvironmentVariable('JUMPBOX_ADMIN_PASSWORD')
