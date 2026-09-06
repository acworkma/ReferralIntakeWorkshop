targetScope = 'resourceGroup'

param location string = resourceGroup().location
param workloadName string = 'referralintake'
param environmentName string = 'dev'
param uniqueSuffix string
param privateEndpointSubnetId string
param keyVaultPrivateDnsZoneId string
param tags object = { managedBy: 'bicep' }

module component '../modules/identity-security.bicep' = {
  name: 'identity-security'
  params: {
    location: location
    workloadName: workloadName
    environmentName: environmentName
    uniqueSuffix: uniqueSuffix
    privateEndpointSubnetId: privateEndpointSubnetId
    keyVaultPrivateDnsZoneId: keyVaultPrivateDnsZoneId
    tags: tags
  }
}

output functionIdentityId string = component.outputs.functionIdentityId
