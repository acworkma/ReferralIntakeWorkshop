targetScope = 'resourceGroup'

param systemTopicName string
param storageAccountId string
param incomingContainer string = 'incoming'
param jobsQueueName string = 'referral-jobs'

module component '../modules/eventing.bicep' = {
  name: 'eventing'
  params: {
    systemTopicName: systemTopicName
    storageAccountId: storageAccountId
    incomingContainer: incomingContainer
    jobsQueueName: jobsQueueName
  }
}

output eventSubscriptionId string = component.outputs.eventSubscriptionId
