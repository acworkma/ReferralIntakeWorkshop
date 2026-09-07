targetScope = 'resourceGroup'

param location string = resourceGroup().location
param workloadName string = 'referralintake'
param environmentName string = 'dev'
param uniqueSuffix string
param publicNetworkAccess bool = true
param privateEndpointSubnetId string
param acrPrivateDnsZoneId string
param containerAppsPrincipalId string
param functionPrincipalId string
param tags object = { managedBy: 'bicep' }

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
    functionPrincipalId: functionPrincipalId
    tags: tags
  }
}

output loginServer string = component.outputs.loginServer
