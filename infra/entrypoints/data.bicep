targetScope = 'resourceGroup'

param location string = resourceGroup().location
param sqlLocation string = location
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
param tags object = { managedBy: 'bicep' }

module component '../modules/data.bicep' = {
  name: 'data'
  params: {
    location: location
    sqlLocation: sqlLocation
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
