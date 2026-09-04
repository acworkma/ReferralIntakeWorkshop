param location string
param workloadName string
param environmentName string
param bastionSubnetId string
param bastionPublicIpId string
param tags object

// Basic SKU deploys into AzureBastionSubnet with a dedicated Standard public IP. Unlike the
// free Developer SKU (which proxies RDP/SSH through the shared platform address
// 168.63.129.16 and gets its required NSG rule flagged/reverted by tenant governance
// automation), Basic SKU uses the officially documented NSG pattern (RDP from
// AzureBastionSubnet to target subnets), which tenant compliance scanners recognize as
// expected Bastion traffic.
resource bastion 'Microsoft.Network/bastionHosts@2023-09-01' = {
  name: 'bas-${workloadName}-${environmentName}'
  location: location
  tags: tags
  sku: {
    name: 'Basic'
  }
  properties: {
    ipConfigurations: [
      {
        name: 'ipconfig'
        properties: {
          subnet: { id: bastionSubnetId }
          publicIPAddress: { id: bastionPublicIpId }
        }
      }
    ]
  }
}

output bastionHostName string = bastion.name
