param location string
param sqlLocation string
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

var storageAccountName = take('st${take(workloadName, 10)}${take(environmentName, 3)}${uniqueSuffix}', 24)
var systemTopicName = 'evgt-${workloadName}-${environmentName}'
var jobsQueueName = 'referral-jobs'

// Box 3 of the reference architecture: the blob's container is the workflow
// state. A document is in exactly one of these at any moment, which makes the
// pipeline legible from the portal without reading a database.
var landingContainers = [
  'incoming'
  'processing'
  'failed'
  'archive'
]

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
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
    networkAcls: {
      defaultAction: 'Deny'
      bypass: 'AzureServices'
      // Event Grid delivers blob events from outside the VNet. Trusted-service
      // access takes precedence over the disabled public endpoint, and the
      // resource instance rule narrows that trust to this one system topic.
      resourceAccessRules: [
        {
          tenantId: tenantId
          resourceId: resourceId('Microsoft.EventGrid/systemTopics', systemTopicName)
        }
      ]
    }
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

resource landingZone 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = [
  for name in landingContainers: {
    parent: blobService
    name: name
    properties: { publicAccess: 'None' }
  }
]

resource queueService 'Microsoft.Storage/storageAccounts/queueServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource jobsQueue 'Microsoft.Storage/storageAccounts/queueServices/queues@2023-05-01' = {
  parent: queueService
  name: jobsQueueName
}

resource poisonQueue 'Microsoft.Storage/storageAccounts/queueServices/queues@2023-05-01' = {
  parent: queueService
  name: '${jobsQueueName}-poison'
}

// Box 5 starts here. A blob landing in incoming/ is what fires the workflow,
// whether it arrived from the web app, azcopy, or a real upstream system.
resource systemTopic 'Microsoft.EventGrid/systemTopics@2024-06-01-preview' = {
  name: systemTopicName
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  properties: {
    source: storage.id
    topicType: 'Microsoft.Storage.StorageAccounts'
  }
}

// Storage Queue Data Message Sender, scoped so the topic can only enqueue.
resource topicQueueRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, systemTopic.id, 'queue-sender')
  scope: storage
  properties: {
    principalId: systemTopic.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      'c6a89b2d-59bc-44d0-9896-0f6e12d7b80a'
    )
  }
}

// Delivery lands in a storage queue rather than calling the function directly:
// the Function App has no inbound public path, so every hop has to be outbound.
// The subscription itself lives in eventing.bicep, deployed last. Event Grid
// validates the identity's queue permission the moment the subscription is
// created, and a role assignment made in this module is not always visible to
// that check yet. Putting the subscription at the end of the graph gives the
// assignment the minutes it needs rather than relying on a lucky race.

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
  name: 'sql-${workloadName}-${environmentName}-${take(replace(sqlLocation, '-', ''), 6)}-${uniqueSuffix}'
  location: sqlLocation
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
  location: sqlLocation
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
output eventGridSystemTopicName string = systemTopic.name
output jobsQueueName string = jobsQueueName
output incomingContainer string = landingContainers[0]
output sqlServerFqdn string = sqlServer.properties.fullyQualifiedDomainName
output sqlDatabaseName string = database.name
