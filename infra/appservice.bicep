param name string
param location string
param databaseUrl string
param aiFoundryEndpoint string
param instanceCount int = 2

resource appPlan 'Microsoft.Web/serverfarms@2022-03-01' = {
  name: '${name}-plan'
  location: location
  sku: {
    name: 'S1'
    capacity: instanceCount
  }
  kind: 'linux'
  properties: { reserved: true }
}

resource webApp 'Microsoft.Web/sites@2022-03-01' = {
  name: name
  location: location
  tags: {
    'azd-service-name': 'web'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: appPlan.id
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.11'
      appCommandLine: './startup.sh'
      // Enable HTTP logging so app logs are visible in Log Stream
      httpLoggingEnabled: true
      logsDirectorySizeLimit: 35
      detailedErrorLoggingEnabled: true
      appSettings: [
        { name: 'DJANGO_DEBUG', value: 'False' }
        { name: 'ALLOWED_HOSTS', value: 'localhost,127.0.0.1,${name}.azurewebsites.net' }
        { name: 'CSRF_TRUSTED_ORIGINS', value: 'https://${name}.azurewebsites.net' }
        { name: 'DATABASE_URL', value: databaseUrl }
        { name: 'AZURE_AI_FOUNDRY_ENDPOINT', value: aiFoundryEndpoint }
        { name: 'SCM_DO_BUILD_DURING_DEPLOYMENT', value: 'true' }
        // Set to 'true' only on first deploy or when you want to reset seed data
        { name: 'SEED_ON_STARTUP', value: 'false' }
      ]
    }
  }
}

// Enable App Service diagnostic logs (application + web server logs)
resource diagnosticLogs 'Microsoft.Web/sites/config@2022-03-01' = {
  name: 'logs'
  parent: webApp
  properties: {
    applicationLogs: {
      fileSystem: {
        level: 'Information'
      }
    }
    httpLogs: {
      fileSystem: {
        enabled: true
        retentionInDays: 3
        retentionInMb: 35
      }
    }
    detailedErrorMessages: {
      enabled: true
    }
    failedRequestsTracing: {
      enabled: true
    }
  }
}

output webAppName string = webApp.name
output webAppUrl string = 'https://${webApp.properties.defaultHostName}'