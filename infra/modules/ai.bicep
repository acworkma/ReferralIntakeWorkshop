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
param contentUnderstandingCompletionModel string = 'gpt-5.2'
param contentUnderstandingCompletionDeployment string = 'gpt-5.2'
param contentUnderstandingEmbeddingModel string = 'text-embedding-3-large'
param contentUnderstandingEmbeddingDeployment string = 'text-embedding-3-large'
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

// The custom Content Understanding analyzer requires BOTH a completion and an
// embedding default before the service will accept it, and both deployments
// must use the GlobalStandard SKU -- a regional 'Standard' embedding
// deployment is not visible to Content Understanding and analyzer creation
// fails with DefaultDeploymentModelNotFound.
resource completionModel 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: contentUnderstanding
  name: contentUnderstandingCompletionDeployment
  sku: { name: 'GlobalStandard', capacity: 50 }
  properties: {
    model: {
      format: 'OpenAI'
      name: contentUnderstandingCompletionModel
      version: '2025-12-11'
    }
  }
}

resource embeddingModel 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: contentUnderstanding
  name: contentUnderstandingEmbeddingDeployment
  sku: { name: 'GlobalStandard', capacity: 50 }
  properties: {
    model: {
      format: 'OpenAI'
      name: contentUnderstandingEmbeddingModel
      version: '1'
    }
  }
  // Serialised: the account rejects concurrent deployment writes.
  dependsOn: [completionModel]
}

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
