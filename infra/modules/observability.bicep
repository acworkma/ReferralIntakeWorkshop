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
          // The orchestration function is where a referral fails, so this reads
          // the function's own logs rather than App Insights traces. isfuzzy
          // keeps the rule valid on a fresh deployment, before either table
          // has received its first row.
          query: 'union isfuzzy=true (FunctionAppLogs | where Level == "Error" | project TimeGenerated), (ContainerAppConsoleLogs_CL | where Log_s has "failed during processing" | project TimeGenerated)'
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

output logAnalyticsWorkspaceId string = workspace.id
output logAnalyticsCustomerId string = workspace.properties.customerId
@secure()
output logAnalyticsSharedKey string = workspace.listKeys().primarySharedKey
output appInsightsConnectionString string = insights.properties.ConnectionString
