targetScope = 'resourceGroup'

param location string = resourceGroup().location
param workloadName string = 'referralintake'
param environmentName string = 'dev'
param tags object = { managedBy: 'bicep', dataClassification: 'synthetic-only' }

module component '../modules/network.bicep' = {
  name: 'network'
  params: {
    location: location
    workloadName: workloadName
    environmentName: environmentName
    tags: tags
  }
}

output acaSubnetId string = component.outputs.acaSubnetId
output privateEndpointSubnetId string = component.outputs.privateEndpointSubnetId
