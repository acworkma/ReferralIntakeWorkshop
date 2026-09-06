targetScope = 'resourceGroup'

param location string = resourceGroup().location
param workloadName string = 'referralintake'
param environmentName string = 'dev'
param bastionSubnetId string
param bastionPublicIpId string
param tags object = { managedBy: 'bicep' }

module component '../modules/bastion.bicep' = {
  name: 'bastion'
  params: {
    location: location
    workloadName: workloadName
    environmentName: environmentName
    bastionSubnetId: bastionSubnetId
    bastionPublicIpId: bastionPublicIpId
    tags: tags
  }
}

output bastionHostName string = component.outputs.bastionHostName
