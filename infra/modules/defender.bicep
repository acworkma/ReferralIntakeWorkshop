targetScope = 'subscription'

param plans array = [
  'AppServices'
  'Containers'
  'KeyVaults'
  'SqlServers'
  'StorageAccounts'
  'VirtualMachines'
]

resource defenderPlans 'Microsoft.Security/pricings@2024-01-01' = [
  for plan in plans: {
    name: plan
    properties: {
      pricingTier: 'Standard'
    }
  }
]
