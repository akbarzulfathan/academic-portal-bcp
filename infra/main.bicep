param prefix string = 'kel2bcp2026'
param primaryRegion string = 'indonesiacentral'
param secondaryRegion string = 'eastasia'
param acrRegion string = 'koreacentral'
param cosmosSecondaryRegion string = 'koreacentral'
param appImage string = '://microsoft.com'
param probePath string = '/'
param targetPort int = 80

@secure()
param sqlAdminPassword string

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: 'acr${prefix}kr'
  location: acrRegion
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: true }
}

var acrPwd = first(acr.listCredentials().passwords).value

module stampRegionA './stamp.bicep' = {
  name: 'deploy-stamp-${primaryRegion}'
  params: {
    location: primaryRegion
    prefix: prefix
    acrLoginServer: acr.properties.loginServer
    acrUsername: acr.listCredentials().username
    acrPassword: acrPwd
    containerImage: appImage
    probePath: probePath
    targetPort: targetPort
  }
}

module stampRegionB './stamp.bicep' = {
  name: 'deploy-stamp-${secondaryRegion}'
  params: {
    location: secondaryRegion
    prefix: prefix
    acrLoginServer: acr.properties.loginServer
    acrUsername: acr.listCredentials().username
    acrPassword: acrPwd
    containerImage: appImage
    probePath: probePath
    targetPort: targetPort
  }
}

resource cosmosDb 'Microsoft.DocumentDB/databaseAccounts@2023-04-15' = {
  name: 'cosmos-${prefix}-v2'
  location: primaryRegion
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    enableMultipleWriteLocations: true
    consistencyPolicy: { defaultConsistencyLevel: 'Session' }
    locations: [
      { locationName: primaryRegion, failoverPriority: 0, isZoneRedundant: false }
      { locationName: cosmosSecondaryRegion, failoverPriority: 1, isZoneRedundant: false }
    ]
  }
}

resource sqlPrimary 'Microsoft.Sql/servers@2022-05-01-preview' = {
  name: 'sql-${prefix}-${primaryRegion}'
  location: primaryRegion
  properties: { administratorLogin: 'sqladmin', administratorLoginPassword: sqlAdminPassword }
}

resource sqlSecondary 'Microsoft.Sql/servers@2022-05-01-preview' = {
  name: 'sql-${prefix}-${secondaryRegion}'
  location: secondaryRegion
  properties: { administratorLogin: 'sqladmin', administratorLoginPassword: sqlAdminPassword }
}

resource sqlDb 'Microsoft.Sql/servers/databases@2022-05-01-preview' = {
  parent: sqlPrimary
  name: 'db-akademik'
  location: primaryRegion
  sku: { name: 'Basic', tier: 'Basic' }
}

resource failoverGroup 'Microsoft.Sql/servers/failoverGroups@2022-05-01-preview' = {
  parent: sqlPrimary
  name: 'fog-${prefix}'
  properties: {
    readWriteEndpoint: { failoverPolicy: 'Automatic', failoverWithDataLossGracePeriodMinutes: 60 }
    partnerServers: [ { id: sqlSecondary.id } ]
    databases: [ sqlDb.id ]
  }
}

resource trafficManager 'Microsoft.Network/trafficManagerProfiles@2022-04-01' = {
  name: 'tm-${prefix}'
  location: 'global'
  properties: {
    profileStatus: 'Enabled'
    trafficRoutingMethod: 'Weighted'
    dnsConfig: { relativeName: 'tm-${prefix}', ttl: 30 }
    monitorConfig: {
      protocol: 'HTTPS'
      port: 443
      path: probePath
      intervalInSeconds: 10
      timeoutInSeconds: 5
      toleratedNumberOfFailures: 2
    }
    endpoints: [
      {
        name: 'ep-${primaryRegion}'
        type: 'Microsoft.Network/trafficManagerProfiles/externalEndpoints'
        properties: { target: stampRegionA.outputs.appFqdn, endpointStatus: 'Enabled', weight: 50 }
      }
      {
        name: 'ep-${secondaryRegion}'
        type: 'Microsoft.Network/trafficManagerProfiles/externalEndpoints'
        properties: { target: stampRegionB.outputs.appFqdn, endpointStatus: 'Enabled', weight: 50 }
      }
    ]
  }
}

output trafficManagerDns string = 'http://${trafficManager.properties.dnsConfig.fqdn}'
output regionAUrl string = 'https://${stampRegionA.outputs.appFqdn}'
output regionBUrl string = 'https://${stampRegionB.outputs.appFqdn}'
