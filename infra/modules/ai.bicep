param location string
param aiFallbackLocation string
@minLength(3)
param workloadName string
param environmentName string
param uniqueSuffix string
param privateEndpointSubnetId string
param cognitivePrivateDnsZoneId string
param functionPrincipalId string
param containerAppsPrincipalId string
param tags object

resource documentIntelligence 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: 'doc-${workloadName}-${environmentName}-${uniqueSuffix}'
  location: location
  kind: 'FormRecognizer'
  sku: { name: 'S0' }
  tags: tags
  properties: {
    customSubDomainName: 'doc-${workloadName}-${environmentName}-${uniqueSuffix}'
    disableLocalAuth: true
    publicNetworkAccess: 'Disabled'
    networkAcls: { defaultAction: 'Deny' }
  }
}

resource contentUnderstanding 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: 'ai-${workloadName}-${environmentName}-${uniqueSuffix}'
  location: aiFallbackLocation
  kind: 'AIServices'
  sku: { name: 'S0' }
  tags: union(tags, { regionalPurpose: 'content-understanding-fallback' })
  properties: {
    customSubDomainName: 'ai-${workloadName}-${environmentName}-${uniqueSuffix}'
    disableLocalAuth: true
    publicNetworkAccess: 'Disabled'
    networkAcls: { defaultAction: 'Deny' }
  }
}

var principals = [functionPrincipalId, containerAppsPrincipalId]

resource documentRoles 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for principal in principals: {
    name: guid(documentIntelligence.id, principal, 'Cognitive Services User')
    scope: documentIntelligence
    properties: {
      principalId: principal
      principalType: 'ServicePrincipal'
      roleDefinitionId: subscriptionResourceId(
        'Microsoft.Authorization/roleDefinitions',
        'a97b65f3-24c7-4388-baec-2e87135dc908'
      )
    }
  }
]

resource contentUnderstandingRoles 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for principal in principals: {
    name: guid(contentUnderstanding.id, principal, 'Cognitive Services User')
    scope: contentUnderstanding
    properties: {
      principalId: principal
      principalType: 'ServicePrincipal'
      roleDefinitionId: subscriptionResourceId(
        'Microsoft.Authorization/roleDefinitions',
        'a97b65f3-24c7-4388-baec-2e87135dc908'
      )
    }
  }
]

resource documentPe 'Microsoft.Network/privateEndpoints@2024-03-01' = {
  name: 'pe-${documentIntelligence.name}'
  location: location
  tags: tags
  properties: {
    subnet: { id: privateEndpointSubnetId }
    privateLinkServiceConnections: [
      {
        name: 'account'
        properties: {
          privateLinkServiceId: documentIntelligence.id
          groupIds: ['account']
        }
      }
    ]
  }
}

resource contentUnderstandingPe 'Microsoft.Network/privateEndpoints@2024-03-01' = {
  name: 'pe-${contentUnderstanding.name}'
  location: location
  tags: tags
  properties: {
    subnet: { id: privateEndpointSubnetId }
    privateLinkServiceConnections: [
      {
        name: 'account'
        properties: {
          privateLinkServiceId: contentUnderstanding.id
          groupIds: ['account']
        }
      }
    ]
  }
}

resource documentDns 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-03-01' = {
  parent: documentPe
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      { name: 'cognitive', properties: { privateDnsZoneId: cognitivePrivateDnsZoneId } }
    ]
  }
}

resource contentUnderstandingDns 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-03-01' = {
  parent: contentUnderstandingPe
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      { name: 'cognitive', properties: { privateDnsZoneId: cognitivePrivateDnsZoneId } }
    ]
  }
}

output documentIntelligenceEndpoint string = documentIntelligence.properties.endpoint
output contentUnderstandingEndpoint string = contentUnderstanding.properties.endpoint
