param location string
@minLength(3)
param workloadName string
param environmentName string
param uniqueSuffix string
param publicNetworkAccess bool
param privateEndpointSubnetId string
param acrPrivateDnsZoneId string
param containerAppsPrincipalId string
param tags object

resource registry 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: 'cr${workloadName}${environmentName}${uniqueSuffix}'
  location: location
  tags: tags
  sku: { name: 'Premium' }
  properties: {
    adminUserEnabled: false
    anonymousPullEnabled: false
    dataEndpointEnabled: true
    publicNetworkAccess: publicNetworkAccess ? 'Enabled' : 'Disabled'
    networkRuleBypassOptions: 'AzureServices'
    policies: {
      quarantinePolicy: { status: 'disabled' }
      retentionPolicy: { days: 7, status: 'enabled' }
    }
  }
}

resource pullRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, containerAppsPrincipalId, 'AcrPull')
  scope: registry
  properties: {
    principalId: containerAppsPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '7f951dda-4ed3-4680-a7ca-43fe172d538d'
    )
  }
}

resource registryPe 'Microsoft.Network/privateEndpoints@2024-03-01' = {
  name: 'pe-${registry.name}'
  location: location
  tags: tags
  properties: {
    subnet: { id: privateEndpointSubnetId }
    privateLinkServiceConnections: [
      {
        name: 'registry'
        properties: {
          privateLinkServiceId: registry.id
          groupIds: ['registry']
        }
      }
    ]
  }
}

resource registryDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-03-01' = {
  parent: registryPe
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      { name: 'registry', properties: { privateDnsZoneId: acrPrivateDnsZoneId } }
    ]
  }
}

output registryId string = registry.id
output loginServer string = registry.properties.loginServer
