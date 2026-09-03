param location string
param workloadName string
param environmentName string
param hubVnetName string
param tags object

resource bastion 'Microsoft.Network/bastionHosts@2023-09-01' = {
  name: 'bas-${workloadName}-${environmentName}'
  location: location
  tags: tags
  sku: {
    name: 'Developer'
  }
  properties: {
    ipConfigurations: []
    virtualNetwork: {
      id: resourceId('Microsoft.Network/virtualNetworks', hubVnetName)
    }
  }
}

output bastionHostName string = bastion.name
