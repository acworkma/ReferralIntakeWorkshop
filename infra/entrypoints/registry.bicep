targetScope = 'resourceGroup'

param location string = resourceGroup().location
param workloadName string = 'referralintake'
param environmentName string = 'dev'
param uniqueSuffix string
param publicNetworkAccess bool = true
param privateEndpointSubnetId string
param acrPrivateDnsZoneId string
param containerAppsPrincipalId string
param tags object = { managedBy: 'bicep', dataClassification: 'synthetic-only' }

module component '../modules/registry.bicep' = {
  name: 'registry'
  params: {
    location: location
    workloadName: workloadName
    environmentName: environmentName
    uniqueSuffix: uniqueSuffix
    publicNetworkAccess: publicNetworkAccess
    privateEndpointSubnetId: privateEndpointSubnetId
    acrPrivateDnsZoneId: acrPrivateDnsZoneId
    containerAppsPrincipalId: containerAppsPrincipalId
    tags: tags
  }
}

output loginServer string = component.outputs.loginServer
