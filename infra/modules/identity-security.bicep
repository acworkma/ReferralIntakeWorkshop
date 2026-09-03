param location string
param workloadName string
param environmentName string
param uniqueSuffix string
param privateEndpointSubnetId string
param keyVaultPrivateDnsZoneId string
param tags object

resource functionIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${workloadName}-func-${environmentName}'
  location: location
  tags: tags
}

resource containerAppsIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${workloadName}-aca-${environmentName}'
  location: location
  tags: tags
}

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: 'kv-${workloadName}-${uniqueSuffix}'
  location: location
  tags: tags
  properties: {
    tenantId: tenant().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
    enablePurgeProtection: true
    publicNetworkAccess: 'Disabled'
  }
}

resource functionSecretsRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, functionIdentity.id, 'Key Vault Secrets User')
  scope: keyVault
  properties: {
    principalId: functionIdentity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '4633458b-17de-408a-b874-0445c86b69e6'
    )
  }
}

resource keyVaultPe 'Microsoft.Network/privateEndpoints@2024-03-01' = {
  name: 'pe-${keyVault.name}'
  location: location
  tags: tags
  properties: {
    subnet: { id: privateEndpointSubnetId }
    privateLinkServiceConnections: [
      {
        name: 'vault'
        properties: {
          privateLinkServiceId: keyVault.id
          groupIds: ['vault']
        }
      }
    ]
  }
}

resource keyVaultDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-03-01' = {
  parent: keyVaultPe
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      { name: 'vault', properties: { privateDnsZoneId: keyVaultPrivateDnsZoneId } }
    ]
  }
}

output functionIdentityId string = functionIdentity.id
output functionPrincipalId string = functionIdentity.properties.principalId
output functionClientId string = functionIdentity.properties.clientId
output containerAppsIdentityId string = containerAppsIdentity.id
output containerAppsPrincipalId string = containerAppsIdentity.properties.principalId
output containerAppsClientId string = containerAppsIdentity.properties.clientId
output keyVaultId string = keyVault.id
