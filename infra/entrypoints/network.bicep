targetScope = 'resourceGroup'

param location string = resourceGroup().location
param workloadName string = 'referralintake'
param environmentName string = 'dev'
param tags object = { managedBy: 'bicep' }

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
output hubVnetId string = component.outputs.hubVnetId
output spokeVnetId string = component.outputs.spokeVnetId
