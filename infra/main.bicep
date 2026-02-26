targetScope = 'subscription'

param environmentName string
param location string
param resourceGroupName string = ''

resource rg 'Microsoft.Resources/resourceGroups@2021-04-01' = {
  name: !empty(resourceGroupName) ? resourceGroupName : 'rg-${environmentName}'
  location: location
  tags: {
    'azd-env-name': environmentName
  }
}

// 1. Azure AI Foundry Project
module aiFoundry './ai-foundry.bicep' = {
  name: 'ai-foundry'
  scope: rg
  params: {
    name: 'ai-${environmentName}'
    location: location
  }
}

// 2. Azure Database (PostgreSQL Flexible Server)
module db './db.bicep' = {
  name: 'database'
  scope: rg
  params: {
    name: 'db-${environmentName}'
    location: location
    adminUser: 'uzima_admin'
  }
}

// 3. App Service (Django Host)
module web './appservice.bicep' = {
  name: 'web'
  scope: rg
  params: {
    name: 'app-${environmentName}'
    location: location
    databaseUrl: db.outputs.connectionString
    aiFoundryEndpoint: aiFoundry.outputs.endpoint
  }
}