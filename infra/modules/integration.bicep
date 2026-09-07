param location string
param workloadName string
param environmentName string
param logAnalyticsWorkspaceId string
param tags object

// Box 7. The business half of the workflow: the orchestration function handles the
// document, this handles what the organisation does about it. It is HTTP triggered
// so both the function (on failure) and the API (on a reviewer decision) can call it
// over the same contract, and so a workshop attendee can add a connector action --
// Teams, Outlook, ServiceNow -- without touching any application code.
resource logicApp 'Microsoft.Logic/workflows@2019-05-01' = {
  name: 'logic-${workloadName}-notification-${environmentName}'
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  properties: {
    state: 'Enabled'
    definition: {
      '$schema': 'https://schema.management.azure.com/schemas/2016-06-01/Microsoft.Logic.json#'
      contentVersion: '1.0.0.0'
      parameters: {}
      triggers: {
        manual: {
          type: 'Request'
          kind: 'Http'
          inputs: {
            method: 'POST'
            schema: {
              type: 'object'
              required: ['event']
              properties: {
                event: {
                  type: 'string'
                  description: 'referral.failed, referral.approved, or referral.rejected'
                }
                referralId: { type: 'string' }
                filename: { type: 'string' }
                patientName: { type: 'string' }
                reviewedBy: { type: 'string' }
                reason: { type: 'string' }
                occurredAt: { type: 'string' }
              }
            }
          }
        }
      }
      actions: {
        // Every branch ends in a Compose so the run history shows the decision that
        // was taken. Replace either Compose with a connector action to make it real.
        Route_event: {
          type: 'Switch'
          expression: '@triggerBody()?[\'event\']'
          runAfter: {}
          cases: {
            Intake_failed: {
              case: 'referral.failed'
              actions: {
                Raise_intake_failure: {
                  type: 'Compose'
                  inputs: {
                    severity: 'error'
                    summary: 'Referral intake failed for @{triggerBody()?[\'filename\']}'
                    reason: '@triggerBody()?[\'reason\']'
                    detail: 'The document is in the failed container and did not reach the review queue. Add a Teams, Outlook, or ticketing action here to page whoever owns intake.'
                    payload: '@triggerBody()'
                  }
                  runAfter: {}
                }
              }
            }
          }
          default: {
            actions: {
              Record_review_decision: {
                type: 'Compose'
                inputs: {
                  severity: 'information'
                  summary: '@{triggerBody()?[\'event\']} for @{triggerBody()?[\'filename\']}'
                  reviewedBy: '@triggerBody()?[\'reviewedBy\']'
                  detail: 'A reviewer reached a decision. Add a downstream action here to hand the referral to the system of record.'
                  payload: '@triggerBody()'
                }
                runAfter: {}
              }
            }
          }
        }
        Acknowledge: {
          type: 'Response'
          kind: 'Http'
          inputs: {
            statusCode: 202
            body: { accepted: true, event: '@triggerBody()?[\'event\']' }
          }
          runAfter: {
            Route_event: ['Succeeded']
          }
        }
      }
      outputs: {}
    }
    parameters: {}
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
output logicAppName string = logicApp.name
