targetScope = 'resourceGroup'

param location string = resourceGroup().location
param workloadName string = 'referralintake'
param environmentName string = 'dev'
param hubVnetName string = 'vnet-${workloadName}-hub-${environmentName}'
param tags object = { managedBy: 'bicep', dataClassification: 'synthetic-only' }

module component '../modules/bastion.bicep' = {
  name: 'bastion'
  params: {
    location: location
    workloadName: workloadName
    environmentName: environmentName
    hubVnetName: hubVnetName
    tags: tags
  }
}

output bastionHostName string = component.outputs.bastionHostName
