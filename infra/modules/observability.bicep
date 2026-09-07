param location string
param workloadName string
param environmentName string
param tags object

resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${workloadName}-${environmentName}'
  location: location
  tags: tags
  properties: {
    retentionInDays: 30
    features: { enableLogAccessUsingOnlyResourcePermissions: true }
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

resource insights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${workloadName}-${environmentName}'
  location: location
  kind: 'web'
  tags: tags
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: workspace.id
    DisableLocalAuth: true
    IngestionMode: 'LogAnalytics'
  }
}

resource failedJobs 'Microsoft.Insights/scheduledQueryRules@2023-12-01' = {
  name: 'alert-${workloadName}-failed-jobs-${environmentName}'
  location: location
  tags: tags
  properties: {
    displayName: 'Referral processing failures'
    description: 'More than zero failed referral-processing traces in fifteen minutes.'
    severity: 2
    enabled: true
    evaluationFrequency: 'PT5M'
    windowSize: 'PT15M'
    scopes: [workspace.id]
    criteria: {
      allOf: [
        {
          query: 'AppTraces | where Message has "referral" and SeverityLevel >= 3'
          timeAggregation: 'Count'
          operator: 'GreaterThan'
          threshold: 0
          failingPeriods: {
            numberOfEvaluationPeriods: 1
            minFailingPeriodsToAlert: 1
          }
        }
      ]
    }
    autoMitigate: true
  }
}

resource dashboard 'Microsoft.Portal/dashboards@2020-09-01-preview' = {
  name: guid(resourceGroup().id, workloadName, environmentName, 'dashboard')
  location: location
  tags: union(tags, { 'hidden-title': 'Referral intake operations' })
  properties: {
    lenses: [
      {
        order: 0
        parts: [
          {
            position: {
              x: 0
              y: 0
              colSpan: 12
              rowSpan: 4
            }
            metadata: {
              type: 'Extension/HubsExtension/PartType/MarkdownPart'
              settings: {
                content: {
                  settings: {
                    title: 'Referral intake operations'
                    content: 'Workshop reference environment. Monitor failed jobs, authentication failures, queue age, and extraction latency.'
                  }
                }
              }
            }
          }
        ]
      }
    ]
    metadata: {
      description: 'Referral intake operations dashboard. Add environment-specific Azure Monitor tiles after deployment.'
    }
  }
}

output logAnalyticsWorkspaceId string = workspace.id
output logAnalyticsCustomerId string = workspace.properties.customerId
@secure()
output logAnalyticsSharedKey string = workspace.listKeys().primarySharedKey
output appInsightsConnectionString string = insights.properties.ConnectionString
