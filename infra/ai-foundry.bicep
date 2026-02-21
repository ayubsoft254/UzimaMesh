param name string
param location string

resource aiHub 'Microsoft.MachineLearningServices/workspaces@2024-04-01-preview' = {
  name: name
  location: location
  kind: 'Hub'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    description: 'Uzima Mesh AI Hub'
  }
}

resource aiProject 'Microsoft.MachineLearningServices/workspaces@2024-04-01-preview' = {
  name: '${name}-project'
  location: location
  kind: 'Project'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    hubResourceId: aiHub.id
  }
}

output endpoint string = aiProject.properties.discoveryUrl