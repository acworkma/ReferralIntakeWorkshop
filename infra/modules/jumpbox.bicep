param location string
param workloadName string
param environmentName string
param jumpboxSubnetId string
param adminUsername string = 'azureadmin'
@secure()
param adminPassword string
param tags object

resource nic 'Microsoft.Network/networkInterfaces@2024-03-01' = {
  name: 'nic-${workloadName}-jump-${environmentName}'
  location: location
  tags: tags
  properties: {
    ipConfigurations: [
      {
        name: 'ipconfig'
        properties: {
          privateIPAllocationMethod: 'Dynamic'
          subnet: { id: jumpboxSubnetId }
        }
      }
    ]
  }
}

resource vm 'Microsoft.Compute/virtualMachines@2024-03-01' = {
  name: 'vm-${workloadName}-jump-${environmentName}'
  location: location
  tags: union(tags, { purpose: 'private-administration' })
  identity: { type: 'SystemAssigned' }
  properties: {
    hardwareProfile: { vmSize: 'Standard_D2as_v5' }
    osProfile: {
      computerName: 'refjump'
      adminUsername: adminUsername
      adminPassword: adminPassword
      windowsConfiguration: {
        provisionVMAgent: true
        enableAutomaticUpdates: true
        patchSettings: {
          patchMode: 'AutomaticByOS'
          assessmentMode: 'ImageDefault'
        }
      }
    }
    storageProfile: {
      imageReference: {
        publisher: 'MicrosoftWindowsDesktop'
        offer: 'windows-11'
        sku: 'win11-25h2-pro'
        version: 'latest'
      }
      osDisk: {
        createOption: 'FromImage'
        managedDisk: { storageAccountType: 'Premium_LRS' }
        deleteOption: 'Delete'
      }
    }
    networkProfile: {
      networkInterfaces: [{ id: nic.id, properties: { deleteOption: 'Delete' } }]
    }
    securityProfile: { securityType: 'TrustedLaunch' }
  }
}

output virtualMachineId string = vm.id
