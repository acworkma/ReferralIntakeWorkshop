targetScope = 'resourceGroup'

param location string = resourceGroup().location
param workloadName string = 'referralintake'
param environmentName string = 'dev'
param logAnalyticsWorkspaceId string
param tags object = { managedBy: 'bicep' }

module component '../modules/integration.bicep' = {
  name: 'integration'
  params: {
    location: location
    workloadName: workloadName
    environmentName: environmentName
    logAnalyticsWorkspaceId: logAnalyticsWorkspaceId
    tags: tags
  }
}

output logicAppId string = component.outputs.logicAppId
output logicAppName string = component.outputs.logicAppName
