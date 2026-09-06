param location string
param workloadName string
param environmentName string
param entraClientId string
param tenantId string
param acaSubnetId string
param hubVnetId string
param spokeVnetId string
@description('Container Apps environment default domain. Set after initial environment deployment to provision private ingress DNS.')
param containerAppsDefaultDomain string = ''
param functionSubnetId string
param privateEndpointSubnetId string
param sitesPrivateDnsZoneId string
param logAnalyticsCustomerId string
@secure()
param logAnalyticsSharedKey string
@secure()
param appInsightsConnectionString string
param containerAppsIdentityId string
param containerAppsIdentityClientId string
param functionIdentityId string
param functionIdentityClientId string
param storageAccountName string
param sqlServerFqdn string
param sqlDatabaseName string
param documentIntelligenceEndpoint string
param contentUnderstandingEndpoint string
param acrLoginServer string
param tags object

resource containerEnvironment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-${workloadName}-${environmentName}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalyticsCustomerId
        sharedKey: logAnalyticsSharedKey
      }
    }
    vnetConfiguration: {
      infrastructureSubnetId: acaSubnetId
      internal: true
    }
    zoneRedundant: false
  }
}

resource containerAppsPrivateDnsZone 'Microsoft.Network/privateDnsZones@2024-06-01' = if (!empty(containerAppsDefaultDomain)) {
  name: containerAppsDefaultDomain
  location: 'global'
  tags: tags
}

resource containerAppsWildcardRecord 'Microsoft.Network/privateDnsZones/A@2024-06-01' = if (!empty(containerAppsDefaultDomain)) {
  parent: containerAppsPrivateDnsZone
  name: '*'
  properties: {
    ttl: 300
    aRecords: [
      {
        ipv4Address: containerEnvironment.properties.staticIp
      }
    ]
  }
}

resource containerAppsHubDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = if (!empty(containerAppsDefaultDomain)) {
  parent: containerAppsPrivateDnsZone
  name: 'link-hub'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: { id: hubVnetId }
  }
}

resource containerAppsSpokeDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = if (!empty(containerAppsDefaultDomain)) {
  parent: containerAppsPrivateDnsZone
  name: 'link-spoke'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: { id: spokeVnetId }
  }
}

resource web 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-${workloadName}-web-${environmentName}'
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${containerAppsIdentityId}': {} }
  }
  properties: {
    managedEnvironmentId: containerEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8080
        transport: 'auto'
        allowInsecure: false
      }
      registries: [
        {
          server: acrLoginServer
          identity: containerAppsIdentityId
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'web'
          image: 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: [
            { name: 'API_BASE_URL', value: 'http://127.0.0.1:7071' }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: { path: '/', port: 8080 }
              initialDelaySeconds: 10
              periodSeconds: 30
            }
          ]
        }
        {
          name: 'api'
          image: 'mcr.microsoft.com/azuredocs/aci-helloworld:latest'
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: [
            { name: 'DATABASE_URL', value: 'mssql+pyodbc://@${sqlServerFqdn}/${sqlDatabaseName}?driver=ODBC+Driver+18+for+SQL+Server&authentication=ActiveDirectoryMsi&UID=${containerAppsIdentityClientId}' }
            { name: 'AZURE_CLIENT_ID', value: containerAppsIdentityClientId }
            { name: 'STORAGE_ACCOUNT_URL', value: 'https://${storageAccountName}.blob.${environment().suffixes.storage}' }
            { name: 'QUEUE_ACCOUNT_URL', value: 'https://${storageAccountName}.queue.${environment().suffixes.storage}' }
            { name: 'QUEUE_NAME', value: 'referral-jobs' }
            { name: 'DOCUMENT_INTELLIGENCE_ENDPOINT', value: documentIntelligenceEndpoint }
            { name: 'CONTENT_UNDERSTANDING_ENDPOINT', value: contentUnderstandingEndpoint }
            { name: 'LOCAL_MOCK_IDENTITY', value: 'false' }
            { name: 'ALLOW_LOCAL_MOCK_EXTRACTION', value: 'false' }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 3
        rules: [
          {
            name: 'http'
            http: { metadata: { concurrentRequests: '50' } }
          }
        ]
      }
    }
  }
}

resource webAuth 'Microsoft.App/containerApps/authConfigs@2024-03-01' = {
  parent: web
  name: 'current'
  properties: {
    platform: { enabled: true }
    globalValidation: {
      unauthenticatedClientAction: 'RedirectToLoginPage'
      redirectToProvider: 'azureactivedirectory'
    }
    identityProviders: {
      azureActiveDirectory: {
        enabled: true
        registration: {
          clientId: entraClientId
          openIdIssuer: 'https://sts.windows.net/${tenantId}/v2.0'
        }
        validation: {
          allowedAudiences: ['api://${entraClientId}']
          defaultAuthorizationPolicy: { allowedPrincipals: {} }
        }
      }
    }
    login: {
      tokenStore: { enabled: false }
      preserveUrlFragmentsForLogins: false
    }
  }
}

resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: 'asp-${workloadName}-func-${environmentName}'
  location: location
  tags: tags
  kind: 'elastic'
  sku: { name: 'EP1', tier: 'ElasticPremium', size: 'EP1', capacity: 1 }
  properties: {
    reserved: true
    maximumElasticWorkerCount: 3
  }
}

resource functionApp 'Microsoft.Web/sites@2023-12-01' = {
  name: 'func-${workloadName}-${environmentName}'
  location: location
  tags: tags
  kind: 'functionapp,linux'
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${functionIdentityId}': {} }
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    publicNetworkAccess: 'Disabled'
    virtualNetworkSubnetId: functionSubnetId
    keyVaultReferenceIdentity: functionIdentityId
    siteConfig: {
      linuxFxVersion: 'Python|3.12'
      minTlsVersion: '1.2'
      ftpsState: 'Disabled'
      alwaysOn: true
      vnetRouteAllEnabled: true
      appSettings: [
        { name: 'FUNCTIONS_WORKER_RUNTIME', value: 'python' }
        { name: 'FUNCTIONS_EXTENSION_VERSION', value: '~4' }
        { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsightsConnectionString }
        { name: 'AzureWebJobsStorage__accountName', value: storageAccountName }
        { name: 'AzureWebJobsStorage__credential', value: 'managedidentity' }
        { name: 'AzureWebJobsStorage__clientId', value: functionIdentityClientId }
        { name: 'STORAGE_ACCOUNT_URL', value: 'https://${storageAccountName}.blob.${environment().suffixes.storage}' }
        { name: 'QUEUE_ACCOUNT_URL', value: 'https://${storageAccountName}.queue.${environment().suffixes.storage}' }
        { name: 'QUEUE_NAME', value: 'referral-jobs' }
        {
          name: 'DATABASE_URL'
          value: 'mssql+pyodbc://@${sqlServerFqdn}/${sqlDatabaseName}?driver=ODBC+Driver+18+for+SQL+Server&authentication=ActiveDirectoryMsi&UID=${functionIdentityClientId}'
        }
        { name: 'AZURE_CLIENT_ID', value: functionIdentityClientId }
        { name: 'DOCUMENT_INTELLIGENCE_ENDPOINT', value: documentIntelligenceEndpoint }
        { name: 'CONTENT_UNDERSTANDING_ENDPOINT', value: contentUnderstandingEndpoint }
        { name: 'LOCAL_MOCK_IDENTITY', value: 'false' }
        { name: 'ALLOW_LOCAL_MOCK_EXTRACTION', value: 'false' }
      ]
    }
  }
}

resource functionAuth 'Microsoft.Web/sites/config@2023-12-01' = {
  parent: functionApp
  name: 'authsettingsV2'
  properties: {
    platform: { enabled: true, runtimeVersion: '~1' }
    globalValidation: {
      requireAuthentication: true
      unauthenticatedClientAction: 'Return401'
    }
    identityProviders: {
      azureActiveDirectory: {
        enabled: true
        registration: {
          clientId: entraClientId
          openIdIssuer: 'https://sts.windows.net/${tenantId}/v2.0'
        }
        validation: { allowedAudiences: ['api://${entraClientId}'] }
      }
    }
    login: { tokenStore: { enabled: false } }
  }
}

resource functionPe 'Microsoft.Network/privateEndpoints@2024-03-01' = {
  name: 'pe-${functionApp.name}'
  location: location
  tags: tags
  properties: {
    subnet: { id: privateEndpointSubnetId }
    privateLinkServiceConnections: [
      {
        name: 'sites'
        properties: {
          privateLinkServiceId: functionApp.id
          groupIds: ['sites']
        }
      }
    ]
  }
}

resource functionDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-03-01' = {
  parent: functionPe
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      { name: 'sites', properties: { privateDnsZoneId: sitesPrivateDnsZoneId } }
    ]
  }
}

output webFqdn string = web.properties.configuration.ingress.fqdn
output containerAppsDefaultDomain string = containerEnvironment.properties.defaultDomain
output functionHostName string = functionApp.properties.defaultHostName
