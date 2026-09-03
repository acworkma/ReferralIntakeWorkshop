targetScope = 'resourceGroup'

param location string = resourceGroup().location
param workloadName string = 'referralintake'
param environmentName string = 'dev'
param tags object = { managedBy: 'bicep', dataClassification: 'synthetic-only' }

module component '../modules/observability.bicep' = {
  name: 'observability'
  params: {
    location: location
    workloadName: workloadName
    environmentName: environmentName
    tags: tags
  }
}

output workspaceId string = component.outputs.logAnalyticsWorkspaceId
