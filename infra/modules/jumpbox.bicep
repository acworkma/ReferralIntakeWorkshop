param location string
param workloadName string
param environmentName string
param jumpboxSubnetId string
param adminUsername string = 'azureadmin'
@secure()
param adminPassword string
param allowedJitPrincipalId string
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
  tags: union(tags, { purpose: 'jit-administration' })
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
          patchMode: 'AutomaticByPlatform'
          assessmentMode: 'AutomaticByPlatform'
          enableHotpatching: false
        }
      }
    }
    storageProfile: {
      imageReference: {
        publisher: 'MicrosoftWindowsServer'
        offer: 'WindowsServer'
        sku: '2022-datacenter-azure-edition'
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

resource jitPolicy 'Microsoft.Security/locations/jitNetworkAccessPolicies@2020-01-01' = {
  name: '${location}/jit-${workloadName}-${environmentName}'
  properties: {
    virtualMachines: [
      {
        id: vm.id
        ports: [
          {
            number: 3389
            protocol: 'TCP'
            allowedSourceAddressPrefix: '*'
            maxRequestAccessDuration: 'PT3H'
            allowedSourceAddressPrefixes: []
          }
        ]
      }
    ]
    requests: []
  }
}

resource jitRequester 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(vm.id, allowedJitPrincipalId, 'JIT requester')
  scope: vm
  properties: {
    principalId: allowedJitPrincipalId
    principalType: 'Group'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '9980e02c-c2be-4d73-94e8-173b1dc7cf3c'
    )
  }
}

resource vmAdministratorLogin 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(vm.id, allowedJitPrincipalId, 'VM administrator login')
  scope: vm
  properties: {
    principalId: allowedJitPrincipalId
    principalType: 'Group'
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '1c0163c0-47e6-4577-8991-ea5c82e286e4'
    )
  }
}

output virtualMachineId string = vm.id
