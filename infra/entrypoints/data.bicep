targetScope = 'resourceGroup'

param location string = resourceGroup().location
param workloadName string = 'referralintake'
param environmentName string = 'dev'
param uniqueSuffix string
param sqlAdminGroupObjectId string
param tenantId string = tenant().tenantId
param privateEndpointSubnetId string
param blobPrivateDnsZoneId string
param queuePrivateDnsZoneId string
param sqlPrivateDnsZoneId string
param functionPrincipalId string
param containerAppsPrincipalId string
param tags object = { managedBy: 'bicep', dataClassification: 'synthetic-only' }

module component '../modules/data.bicep' = {
  name: 'data'
  params: {
    location: location
    workloadName: workloadName
    environmentName: environmentName
    uniqueSuffix: uniqueSuffix
    sqlAdminGroupObjectId: sqlAdminGroupObjectId
    tenantId: tenantId
    privateEndpointSubnetId: privateEndpointSubnetId
    blobPrivateDnsZoneId: blobPrivateDnsZoneId
    queuePrivateDnsZoneId: queuePrivateDnsZoneId
    sqlPrivateDnsZoneId: sqlPrivateDnsZoneId
    functionPrincipalId: functionPrincipalId
    containerAppsPrincipalId: containerAppsPrincipalId
    tags: tags
  }
}

output storageAccountId string = component.outputs.storageAccountId
