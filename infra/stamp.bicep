param location string
param prefix string
param containerImage string

@secure()
param acrPassword string
param acrLoginServer string
param acrUsername string
param probePath string = '/'
param targetPort int = 80

var suffix = '${prefix}-${location}'
var cleanPrefix = replace(prefix, '-', '')
var locShort = substring(location, 0, 6)

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: 'law-${suffix}'
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: take('kv${cleanPrefix}${locShort}', 24)
  location: location
  properties: {
    sku: { family: 'A', name: 'standard' }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: take('st${cleanPrefix}${locShort}', 24)
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
}

resource containerAppEnv 'Microsoft.App/managedEnvironments@2023-05-01' = {
  name: 'cae-${suffix}'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

resource containerApp 'Microsoft.App/containerApps@2023-05-01' = {
  name: 'app-${suffix}'
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {
    managedEnvironmentId: containerAppEnv.id
    configuration: {
      ingress: { external: true, targetPort: targetPort, transport: 'http' }
      registries: [
        { server: acrLoginServer, username: acrUsername, passwordSecretRef: 'acr-pwd' }
      ]
      secrets: [
        { name: 'acr-pwd', value: acrPassword }
      ]
    }
    template: {
      containers: [
        {
          name: 'academic-portal'
          image: containerImage
          resources: { cpu: json('0.5'), memory: '1.0Gi' }
          env: [
            { name: 'REGION_NAME', value: location }
            { name: 'USE_MOCK', value: 'true' }
          ]
          probes: [
            { type: 'Liveness', httpGet: { path: probePath, port: targetPort }, periodSeconds: 10 }
            { type: 'Readiness', httpGet: { path: probePath, port: targetPort }, periodSeconds: 10 }
          ]
        }
      ]
      scale: { minReplicas: 1, maxReplicas: 3 }
    }
  }
}

output appFqdn string = containerApp.properties.configuration.ingress.fqdn
