param name string
param location string
param databaseUrl string
param aiFoundryEndpoint string

resource appPlan 'Microsoft.Web/serverfarms@2022-03-01' = {
  name: '${name}-plan'
  location: location
  sku: { name: 'B1' }
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
      appSettings: [
        { name: 'DJANGO_DEBUG', value: 'False' }
        { name: 'ALLOWED_HOSTS', value: 'localhost,127.0.0.1,${name}.azurewebsites.net' }
        { name: 'CSRF_TRUSTED_ORIGINS', value: 'https://${name}.azurewebsites.net' }
        { name: 'DATABASE_URL', value: databaseUrl }
        { name: 'AZURE_AI_FOUNDRY_ENDPOINT', value: aiFoundryEndpoint }
        { name: 'SCM_DO_BUILD_DURING_DEPLOYMENT', value: 'true' }
      ]
    }
  }
}