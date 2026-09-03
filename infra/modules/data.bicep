param location string
@minLength(3)
param workloadName string
param environmentName string
param uniqueSuffix string
param sqlAdminGroupObjectId string
param tenantId string
param privateEndpointSubnetId string
param blobPrivateDnsZoneId string
param queuePrivateDnsZoneId string
param sqlPrivateDnsZoneId string
param functionPrincipalId string
param containerAppsPrincipalId string
param tags object

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: 'st${workloadName}${environmentName}${uniqueSuffix}'
  location: location
  tags: tags
  sku: { name: 'Standard_ZRS' }
  kind: 'StorageV2'
  properties: {
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    defaultToOAuthAuthentication: true
    minimumTlsVersion: 'TLS1_2'
    publicNetworkAccess: 'Disabled'
    networkAcls: { defaultAction: 'Deny', bypass: 'AzureServices' }
    supportsHttpsTrafficOnly: true
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
  properties: {
    deleteRetentionPolicy: { enabled: true, days: 7 }
    containerDeleteRetentionPolicy: { enabled: true, days: 7 }
  }
}

resource referralContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'referrals'
  properties: { publicAccess: 'None' }
}

resource queueService 'Microsoft.Storage/storageAccounts/queueServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource jobsQueue 'Microsoft.Storage/storageAccounts/queueServices/queues@2023-05-01' = {
  parent: queueService
  name: 'referral-jobs'
}

resource poisonQueue 'Microsoft.Storage/storageAccounts/queueServices/queues@2023-05-01' = {
  parent: queueService
  name: 'referral-jobs-poison'
}

var storageRoles = [
  'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
  '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
]

var workloadPrincipals = [functionPrincipalId, containerAppsPrincipalId]

resource storageAssignments 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for item in flatten(map(workloadPrincipals, principal => map(storageRoles, role => {
    principal: principal
    role: role
  }))): {
    name: guid(storage.id, item.principal, item.role)
    scope: storage
    properties: {
      principalId: item.principal
      principalType: 'ServicePrincipal'
      roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', item.role)
    }
  }
]

var storagePrivateLinks = [
  { group: 'blob', zone: blobPrivateDnsZoneId }
  { group: 'queue', zone: queuePrivateDnsZoneId }
]

resource storagePe 'Microsoft.Network/privateEndpoints@2024-03-01' = [
  for service in storagePrivateLinks: {
    name: 'pe-${storage.name}-${service.group}'
    location: location
    tags: tags
    properties: {
      subnet: { id: privateEndpointSubnetId }
      privateLinkServiceConnections: [
        {
          name: service.group
          properties: {
            privateLinkServiceId: storage.id
            groupIds: [service.group]
          }
        }
      ]
    }
  }
]

resource storageDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-03-01' = [
  for (service, i) in storagePrivateLinks: {
    parent: storagePe[i]
    name: 'default'
    properties: {
      privateDnsZoneConfigs: [
        { name: service.group, properties: { privateDnsZoneId: service.zone } }
      ]
    }
  }
]

resource sqlServer 'Microsoft.Sql/servers@2023-08-01-preview' = {
  name: 'sql-${workloadName}-${environmentName}-${uniqueSuffix}'
  location: location
  tags: tags
  properties: {
    administrators: {
      administratorType: 'ActiveDirectory'
      principalType: 'Group'
      login: 'Referral SQL Administrators'
      sid: sqlAdminGroupObjectId
      tenantId: tenantId
      azureADOnlyAuthentication: true
    }
    minimalTlsVersion: '1.2'
    publicNetworkAccess: 'Disabled'
    restrictOutboundNetworkAccess: 'Enabled'
    version: '12.0'
  }
}

resource database 'Microsoft.Sql/servers/databases@2023-08-01-preview' = {
  parent: sqlServer
  name: 'sqldb-${workloadName}'
  location: location
  tags: tags
  sku: { name: 'S0', tier: 'Standard' }
  properties: {
    zoneRedundant: false
    readScale: 'Disabled'
  }
}

resource sqlPe 'Microsoft.Network/privateEndpoints@2024-03-01' = {
  name: 'pe-${sqlServer.name}'
  location: location
  tags: tags
  properties: {
    subnet: { id: privateEndpointSubnetId }
    privateLinkServiceConnections: [
      {
        name: 'sql'
        properties: {
          privateLinkServiceId: sqlServer.id
          groupIds: ['sqlServer']
        }
      }
    ]
  }
}

resource sqlDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-03-01' = {
  parent: sqlPe
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      { name: 'sql', properties: { privateDnsZoneId: sqlPrivateDnsZoneId } }
    ]
  }
}

output storageAccountName string = storage.name
output storageAccountId string = storage.id
output sqlServerFqdn string = sqlServer.properties.fullyQualifiedDomainName
output sqlDatabaseName string = database.name
