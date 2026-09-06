targetScope = 'resourceGroup'

param location string = resourceGroup().location
param workloadName string = 'referralintake'
param environmentName string = 'dev'
param uniqueSuffix string
param privateEndpointSubnetId string
param keyVaultPrivateDnsZoneId string
@secure()
param jumpboxAdminPassword string = ''
param jumpboxAdminGroupObjectId string = ''
param storeJumpboxPassword bool = false
param tags object = { managedBy: 'bicep', dataClassification: 'synthetic-only' }

module component '../modules/identity-security.bicep' = {
  name: 'identity-security'
  params: {
    location: location
    workloadName: workloadName
    environmentName: environmentName
    uniqueSuffix: uniqueSuffix
    privateEndpointSubnetId: privateEndpointSubnetId
    keyVaultPrivateDnsZoneId: keyVaultPrivateDnsZoneId
    jumpboxAdminPassword: jumpboxAdminPassword
    jumpboxAdminGroupObjectId: jumpboxAdminGroupObjectId
    storeJumpboxPassword: storeJumpboxPassword
    tags: tags
  }
}

output functionIdentityId string = component.outputs.functionIdentityId
output keyVaultName string = component.outputs.keyVaultName
