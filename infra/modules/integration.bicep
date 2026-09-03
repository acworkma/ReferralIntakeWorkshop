param location string
param workloadName string
param environmentName string
param storageAccountId string
param logAnalyticsWorkspaceId string
param tags object

resource logicApp 'Microsoft.Logic/workflows@2019-05-01' = {
  name: 'logic-${workloadName}-notification-${environmentName}'
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  properties: {
    state: 'Disabled'
    definition: {
      '$schema': 'https://schema.management.azure.com/schemas/2016-06-01/Microsoft.Logic.json#'
      contentVersion: '1.0.0.0'
      parameters: {}
      triggers: {
        manual: {
          type: 'Request'
          kind: 'Http'
          inputs: { schema: { type: 'object' } }
        }
      }
      actions: {
        Record_synthetic_event: {
          type: 'Compose'
          inputs: {
            message: 'Synthetic referral review notification received.'
            body: '@triggerBody()'
          }
          runAfter: {}
        }
      }
      outputs: {}
    }
    parameters: {}
  }
}

resource logicStorageReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccountId, logicApp.id, 'Storage Blob Data Reader')
  scope: resourceGroup()
  properties: {
    principalId: logicApp.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'
    )
  }
}

resource diagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'diag-${logicApp.name}'
  scope: logicApp
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [
      { categoryGroup: 'allLogs', enabled: true }
    ]
    metrics: [
      { category: 'AllMetrics', enabled: true }
    ]
  }
}

output logicAppId string = logicApp.id
