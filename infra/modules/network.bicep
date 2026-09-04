param location string
param workloadName string
param environmentName string
param tags object

var hubName = 'vnet-${workloadName}-hub-${environmentName}'
var spokeName = 'vnet-${workloadName}-spoke-${environmentName}'
var bastionSubnetPrefix = '10.20.1.0/26'

resource hubNsg 'Microsoft.Network/networkSecurityGroups@2024-03-01' = {
  name: 'nsg-${workloadName}-hub-${environmentName}'
  location: location
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'AllowBastionRdpInbound'
        properties: {
          priority: 200
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '3389'
          sourceAddressPrefix: bastionSubnetPrefix
          destinationAddressPrefix: '*'
        }
      }
      {
        name: 'DenyInternetInbound'
        properties: {
          priority: 4096
          direction: 'Inbound'
          access: 'Deny'
          protocol: '*'
          sourcePortRange: '*'
          destinationPortRange: '*'
          sourceAddressPrefix: 'Internet'
          destinationAddressPrefix: '*'
        }
      }
    ]
  }
}

resource workloadNsg 'Microsoft.Network/networkSecurityGroups@2024-03-01' = {
  name: 'nsg-${workloadName}-workload-${environmentName}'
  location: location
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'AllowAzureLoadBalancer'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: '*'
          sourcePortRange: '*'
          destinationPortRange: '*'
          sourceAddressPrefix: 'AzureLoadBalancer'
          destinationAddressPrefix: '*'
        }
      }
      {
        name: 'DenyInternetInbound'
        properties: {
          priority: 4096
          direction: 'Inbound'
          access: 'Deny'
          protocol: '*'
          sourcePortRange: '*'
          destinationPortRange: '*'
          sourceAddressPrefix: 'Internet'
          destinationAddressPrefix: '*'
        }
      }
    ]
  }
}

resource hub 'Microsoft.Network/virtualNetworks@2024-03-01' = {
  name: hubName
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: ['10.20.0.0/16']
    }
    subnets: [
      {
        name: 'AzureBastionSubnet'
        properties: {
          addressPrefix: '10.20.1.0/26'
        }
      }
      {
        name: 'snet-jumpbox'
        properties: {
          addressPrefix: '10.20.2.0/24'
          networkSecurityGroup: { id: hubNsg.id }
        }
      }
    ]
  }
}

resource spoke 'Microsoft.Network/virtualNetworks@2024-03-01' = {
  name: spokeName
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: ['10.21.0.0/16']
    }
    subnets: [
      {
        name: 'snet-aca'
        properties: {
          addressPrefix: '10.21.0.0/23'
          networkSecurityGroup: { id: workloadNsg.id }
          delegations: [
            {
              name: 'aca'
              properties: { serviceName: 'Microsoft.App/environments' }
            }
          ]
        }
      }
      {
        name: 'snet-functions'
        properties: {
          addressPrefix: '10.21.2.0/24'
          networkSecurityGroup: { id: workloadNsg.id }
          delegations: [
            {
              name: 'functions'
              properties: { serviceName: 'Microsoft.Web/serverFarms' }
            }
          ]
        }
      }
      {
        name: 'snet-private-endpoints'
        properties: {
          addressPrefix: '10.21.3.0/24'
          privateEndpointNetworkPolicies: 'Disabled'
          networkSecurityGroup: { id: workloadNsg.id }
        }
      }
    ]
  }
}

resource hubToSpoke 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2024-03-01' = {
  parent: hub
  name: 'peer-to-spoke'
  properties: {
    remoteVirtualNetwork: { id: spoke.id }
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: true
  }
}

resource spokeToHub 'Microsoft.Network/virtualNetworks/virtualNetworkPeerings@2024-03-01' = {
  parent: spoke
  name: 'peer-to-hub'
  properties: {
    remoteVirtualNetwork: { id: hub.id }
    allowVirtualNetworkAccess: true
    allowForwardedTraffic: true
  }
}

var zones = [
  'privatelink.blob.${environment().suffixes.storage}'
  'privatelink.queue.${environment().suffixes.storage}'
  'privatelink.database.windows.net'
  'privatelink.vaultcore.azure.net'
  'privatelink.azurecr.io'
  'privatelink.cognitiveservices.azure.com'
  'privatelink.azurewebsites.net'
]

resource privateDnsZones 'Microsoft.Network/privateDnsZones@2024-06-01' = [
  for zone in zones: {
    name: zone
    location: 'global'
    tags: tags
  }
]

resource dnsLinks 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = [
  for (zone, i) in zones: {
    parent: privateDnsZones[i]
    name: 'link-${spokeName}'
    location: 'global'
    properties: {
      registrationEnabled: false
      virtualNetwork: { id: spoke.id }
    }
  }
]

output acaSubnetId string = resourceId('Microsoft.Network/virtualNetworks/subnets', spoke.name, 'snet-aca')
output functionSubnetId string = resourceId('Microsoft.Network/virtualNetworks/subnets', spoke.name, 'snet-functions')
output privateEndpointSubnetId string = resourceId('Microsoft.Network/virtualNetworks/subnets', spoke.name, 'snet-private-endpoints')
output jumpboxSubnetId string = resourceId('Microsoft.Network/virtualNetworks/subnets', hub.name, 'snet-jumpbox')
output blobPrivateDnsZoneId string = privateDnsZones[0].id
output queuePrivateDnsZoneId string = privateDnsZones[1].id
output sqlPrivateDnsZoneId string = privateDnsZones[2].id
output keyVaultPrivateDnsZoneId string = privateDnsZones[3].id
output acrPrivateDnsZoneId string = privateDnsZones[4].id
output cognitivePrivateDnsZoneId string = privateDnsZones[5].id
output sitesPrivateDnsZoneId string = privateDnsZones[6].id
