targetScope = 'resourceGroup'

param location string = resourceGroup().location
param aiFallbackLocation string = 'westus3'
param workloadName string = 'referralintake'
param environmentName string = 'dev'
param uniqueSuffix string
param privateEndpointSubnetId string
param cognitivePrivateDnsZoneId string
param functionPrincipalId string
param containerAppsPrincipalId string
param tags object = { managedBy: 'bicep', dataClassification: 'synthetic-only' }

module component '../modules/ai.bicep' = {
  name: 'ai'
  params: {
    location: location
    aiFallbackLocation: aiFallbackLocation
    workloadName: workloadName
    environmentName: environmentName
    uniqueSuffix: uniqueSuffix
    privateEndpointSubnetId: privateEndpointSubnetId
    cognitivePrivateDnsZoneId: cognitivePrivateDnsZoneId
    functionPrincipalId: functionPrincipalId
    containerAppsPrincipalId: containerAppsPrincipalId
    tags: tags
  }
}

output contentUnderstandingEndpoint string = component.outputs.contentUnderstandingEndpoint
