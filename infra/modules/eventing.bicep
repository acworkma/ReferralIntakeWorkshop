@description('Name of the Event Grid system topic that watches the storage account.')
param systemTopicName string
param storageAccountId string
param incomingContainer string
param jobsQueueName string

// This is the join between Box 3 and Box 5. It is a separate module, deployed
// after everything else, for one reason: Event Grid checks the system topic's
// queue permission at the moment the subscription is created, and a role
// assignment made earlier in the same deployment is not reliably visible to
// that check yet. Deploying it last gives the assignment time to propagate.
resource systemTopic 'Microsoft.EventGrid/systemTopics@2024-06-01-preview' existing = {
  name: systemTopicName
}

resource incomingSubscription 'Microsoft.EventGrid/systemTopics/eventSubscriptions@2024-06-01-preview' = {
  parent: systemTopic
  name: 'referral-incoming'
  properties: {
    // The storage account has shared key access turned off, so delivery has to
    // be identity-based. The topic's own identity holds Storage Queue Data
    // Message Sender and nothing else.
    deliveryWithResourceIdentity: {
      identity: { type: 'SystemAssigned' }
      destination: {
        endpointType: 'StorageQueue'
        properties: {
          resourceId: storageAccountId
          queueName: jobsQueueName
          queueMessageTimeToLiveInSeconds: 604800
        }
      }
    }
    filter: {
      includedEventTypes: ['Microsoft.Storage.BlobCreated']
      subjectBeginsWith: '/blobServices/default/containers/${incomingContainer}/blobs/'
    }
    eventDeliverySchema: 'EventGridSchema'
    // Ten attempts over a day. A transient failure downstream should not lose a
    // referral, and anything still failing after that is not transient.
    retryPolicy: {
      maxDeliveryAttempts: 10
      eventTimeToLiveInMinutes: 1440
    }
    deadLetterDestination: null
  }
}

output eventSubscriptionId string = incomingSubscription.id
