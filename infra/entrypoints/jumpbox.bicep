targetScope = 'resourceGroup'

param location string = resourceGroup().location
param workloadName string = 'referralintake'
param environmentName string = 'dev'
param jumpboxSubnetId string
@secure()
param adminPassword string
param allowedJitPrincipalId string
param tags object = { managedBy: 'bicep', dataClassification: 'synthetic-only' }

module component '../modules/jumpbox.bicep' = {
  name: 'jumpbox'
  params: {
    location: location
    workloadName: workloadName
    environmentName: environmentName
    jumpboxSubnetId: jumpboxSubnetId
    adminPassword: adminPassword
    allowedJitPrincipalId: allowedJitPrincipalId
    tags: tags
  }
}
