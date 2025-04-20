targetScope = 'subscription'

// === Core Parameters ===
@minLength(1)
@maxLength(64)
@description('Name of the environment that can be used as part of naming resource convention')
param environmentName string

@minLength(1)
@description('Primary location for all resources')
@allowed([
  'northcentralusstage'
  'westus2'
  'northeurope'
  'eastus'
  'eastasia'
  'northcentralus'
  'germanywestcentral'
  'polandcentral'
  'italynorth'
  'switzerlandnorth'
  'swedencentral'
  'norwayeast'
  'japaneast'
  'australiaeast'
  'westcentralus'
  'westeurope'
])
param location string

@description('Id of the user or app owner to assign administrative roles.')
param principalId string // User Principal ID

param srcExists bool = false // Assuming default for source code check
@secure()
param srcDefinition object = {} // Assuming default for source definition

// === Global Variables ===
var tags = {
  'azd-env-name': environmentName
}
var abbrs = loadJsonContent('./abbreviations.json')
var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))
var prefix = 'dreamv2' // Prefix for custom subdomain if needed

// === Resource Naming ===
var logAnalyticsName = '${abbrs.operationalInsightsWorkspaces}${resourceToken}'
var applicationInsightsName = '${abbrs.insightsComponents}${resourceToken}'
var containerRegistryName = '${abbrs.containerRegistryRegistries}${resourceToken}'
var keyVaultName = '${abbrs.keyVaultVaults}${resourceToken}'
var vnetName = '${abbrs.networkVirtualNetworks}${resourceToken}'
var appsEnvName = '${abbrs.appManagedEnvironments}${resourceToken}'
var storageAccountName = '${abbrs.storageStorageAccounts}${resourceToken}' // Storage for Hub & Backend
var cosmosDbName = '${abbrs.documentDBDatabaseAccounts}${resourceToken}'
var aiSearchName = '${abbrs.searchSearchServices}${resourceToken}'
var backendIdentityName = '${abbrs.managedIdentityUserAssignedIdentities}backend-${resourceToken}'
var aiServiceName = '${abbrs.cognitiveServicesAccounts}${resourceToken}' // Name for the AI Service (OpenAI)
var aiHubName = '${abbrs.aiHubs}${resourceToken}' // Name for the AI Hub
var aiProjectName = '${abbrs.aiProjects}${resourceToken}' // Name for the AI Project
var staticSiteName = '${abbrs.webStaticSites}${resourceToken}'
var dashboardName = '${abbrs.portalDashboards}${resourceToken}'
var sessionPoolName = 'sessionPool-${resourceToken}' // Unique name for session pool

// AI Service Deployment Names (used in ai-service module and backend env var)
var openAiDeploymentGpt4oName = 'gpt-4o'
var openAiDeploymentGpt4oMiniName = 'gpt-4o-mini'
var openAiDeploymentEmbeddingName = 'text-embedding-3-large'

// AI Hub Connection Names (used in hub module)
var hubOpenAiConnectionName = 'hub-conn-${aiServiceName}'
var hubContentSafetyConnectionName = 'hub-conn-${aiServiceName}-cs'
var hubSearchConnectionName = 'hub-conn-${aiSearchName}'

// === Resource Group ===
resource rg 'Microsoft.Resources/resourceGroups@2022-09-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

// === Shared Infrastructure Modules ===
module monitoring './shared/monitoring.bicep' = {
  name: 'monitoring'
  scope: rg
  params: {
    location: location
    tags: tags
    logAnalyticsName: logAnalyticsName
    applicationInsightsName: applicationInsightsName
  }
}

module registry './shared/registry.bicep' = {
  name: 'registry'
  scope: rg
  params: {
    location: location
    tags: tags
    name: containerRegistryName
  }
}

module keyVault './shared/keyvault.bicep' = {
  name: 'keyvault'
  scope: rg
  params: {
    location: location
    tags: tags
    name: keyVaultName
    principalId: principalId // Granting user access
  }
}

module network './shared/netwk.bicep' = {
  name: 'network'
  scope: rg
  params: {
    name: vnetName
    location: location
    tags: tags
  }
}

module appsEnv './shared/apps-env.bicep' = {
  name: 'apps-env'
  scope: rg
  params: {
    name: appsEnvName
    location: location
    tags: tags
    applicationInsightsName: monitoring.outputs.applicationInsightsName
    logAnalyticsWorkspaceName: monitoring.outputs.logAnalyticsWorkspaceName
    infrastructureSubnetId: network.outputs.acaSubnetId
  }
  dependsOn: [
    network
    monitoring
  ]
}

// === Core Application Dependencies (Directly in main.bicep) ===

// Storage Account (Required by Hub and Backend)
resource storageAcct 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: storageAccountName
  location: location
  tags: tags
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    // Consider private endpoint if needed
  }
}

// Cosmos DB
resource cosmosDb 'Microsoft.DBforCosmosDB/databaseAccounts@2023-04-15' = {
  name: cosmosDbName
  location: location
  tags: tags
  kind: 'GlobalDocumentDB' // Or 'MongoDB' depending on API type needed
  properties: {
    databaseAccountOfferType: 'Standard'
    locations: [
      {
        locationName: location
        failoverPriority: 0
      }
    ]
    // Add consistency policy, capabilities etc. as needed
    // Consider private endpoint if needed
  }
}

// User Assigned Identity for Backend App
resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: backendIdentityName
  location: location
  tags: tags
}

// AI Search Service
resource aiSearch 'Microsoft.Search/searchServices@2024-06-01-preview' = {
  name: aiSearchName
  location: location
  tags: tags
  sku: {
    name: 'basic' // Or other SKU as needed
  }
  properties: {
    replicaCount: 1
    partitionCount: 1
    hostingMode: 'default'
    publicNetworkAccess: 'Enabled' // Change to Disabled if using private endpoint exclusively
    authOptions: {
      aadOrApiKey: { aadAuthFailureMode: 'http403' }
    }
  }
  identity: { // Assign backend identity for potential Azure RBAC access (alternative to API key)
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identity.id}': {}
    }
  }
}

// AI Search Private Endpoint Resources (Copied from original)
resource searchPrivateDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.search.windows.net'
  location: 'global'
  scope: rg // Deploy DNS Zone within the RG
}

resource searchDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: searchPrivateDnsZone
  name: '${searchPrivateDnsZone.name}-link'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: network.outputs.vnetId
    }
  }
  dependsOn: [
    network // Ensure VNet exists
  ]
}

resource peSearch 'Microsoft.Network/privateEndpoints@2023-05-01' = {
  name: 'pe-${aiSearchName}'
  location: location
  tags: tags
  scope: rg
  properties: {
    subnet: {
      id: network.outputs.defaultSubnetId // Assuming default subnet is suitable
    }
    privateLinkServiceConnections: [
      {
        name: '${aiSearchName}-plsconnection'
        properties: {
          privateLinkServiceId: aiSearch.id
          groupIds: [ 'searchService' ]
        }
      }
    ]
  }
  dependsOn: [
    network // Ensure subnet exists
  ]
}

resource searchZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-05-01' = {
  name: '${peSearch.name}-zonegroup'
  parent: peSearch
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'search-config'
        properties: {
          privateDnsZoneId: searchPrivateDnsZone.id
        }
      }
    ]
  }
  dependsOn: [
    searchDnsLink // Ensure DNS Zone and Link exist
  ]
}

// === AI Service (OpenAI) Module ===
module aiService 'ai-service.bicep' = {
  name: 'aiServiceDeployment'
  scope: rg
  params: {
    name: aiServiceName
    location: location
    tags: tags
    customSubDomainName: '${prefix}-${resourceToken}' // Use prefix + token for uniqueness
    kind: 'OpenAI'
    sku: {
      name: 'S0'
    }
    publicNetworkAccess: 'Enabled' // Adjust if private endpoint needed for OpenAI
    deployments: [ // Define model deployments
      {
        name: openAiDeploymentGpt4oName
        sku: {
          name: 'GlobalStandard' // Check exact SKU name in Azure Portal/docs if needed
          capacity: 70 // Adjust capacity as needed
        }
        model: {
          format: 'OpenAI'
          name: 'gpt-4o'
          version: '2024-05-13' // Use a valid, available version
        }
        versionUpgradeOption: 'OnceCurrentVersionExpired'
      }
      {
        name: openAiDeploymentGpt4oMiniName
        sku: {
          name: 'GlobalStandard'
          capacity: 70
        }
        model: {
          format: 'OpenAI'
          name: 'gpt-4o-mini'
          version: '2024-07-18'
        }
        versionUpgradeOption: 'OnceCurrentVersionExpired'
      }
      {
        name: openAiDeploymentEmbeddingName
        sku: {
          name: 'Standard'
          capacity: 60
        }
        model: {
          format: 'OpenAI'
          name: 'text-embedding-3-large'
          version: '1' // Use a valid, available version
        }
        versionUpgradeOption: 'OnceCurrentVersionExpired'
      }
    ]
    logAnalyticsWorkspaceResourceId: monitoring.outputs.logAnalyticsWorkspaceId // Send logs
    roleAssignments: [ // Grant access to backend identity and user
      {
        roleDefinitionIdOrName: 'Cognitive Services OpenAI User'
        principalId: identity.properties.principalId // Backend App Identity
        principalType: 'ServicePrincipal'
      }
      {
        roleDefinitionIdOrName: 'Cognitive Services OpenAI User'
        principalId: principalId // Deploying User
        principalType: 'User'
      }
    ]
  }
  dependsOn: [
    monitoring,
    identity // Need identity principalId for role assignment
  ]
}

// === AI Hub Module ===
module hub 'hub.bicep' = {
  name: 'aiHubDeployment'
  scope: rg
  params: {
    name: aiHubName
    location: location
    tags: tags
    displayName: 'AI Hub (${environmentName})'
    storageAccountId: storageAcct.id
    keyVaultId: keyVault.outputs.id
    applicationInsightsId: monitoring.outputs.applicationInsightsId
    containerRegistryId: registry.outputs.id
    openAiName: aiService.outputs.name // Pass the name of the created AI Service
    openAiConnectionName: hubOpenAiConnectionName
    aiSearchName: aiSearch.name // Pass the name of the created AI Search
    aiSearchConnectionName: hubSearchConnectionName
    openAiContentSafetyConnectionName: hubContentSafetyConnectionName
    skuName: 'Free' // Or 'Standard', 'Basic' etc.
    skuTier: 'Free' // Match skuName tier
    publicNetworkAccess: 'Enabled' // Adjust as needed
  }
  dependsOn: [
    storageAcct,
    keyVault,
    monitoring,
    registry,
    aiService, // Hub needs AI Service details for connection
    aiSearch // Hub needs AI Search details for connection
  ]
}

// === AI Project Module ===
module project 'project.bicep' = {
  name: 'aiProjectDeployment'
  scope: rg
  params: {
    name: aiProjectName
    location: location
    tags: tags
    displayName: 'AI Project (${environmentName})'
    hubName: hub.outputs.name // Link to the created Hub
    skuName: 'Free' // Or 'Standard', 'Basic' etc.
    skuTier: 'Free' // Match skuName tier
    publicNetworkAccess: 'Enabled' // Adjust as needed
  }
  dependsOn: [
    hub // Project depends on Hub
  ]
}

// === Dynamic Session Pool ===
resource dynamicsession 'Microsoft.App/sessionPools@2024-02-02-preview' = {
  name: sessionPoolName
  location: location
  tags: tags
  scope: rg
  properties: {
    containerType: 'PythonLTS'
    dynamicPoolConfiguration: {
      cooldownPeriodInSeconds: 300
      executionType: 'Timed'
    }
    poolManagementType: 'Dynamic'
    scaleConfiguration: {
      maxConcurrentSessions: 20
      readySessionInstances: 2
    }
  }
}

// === Role Assignments (Centralized for clarity) ===

// Backend Identity Roles
resource backendIdentityAiSearchContrib 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(aiSearch.id, identity.id, 'SearchServiceContributor')
  scope: aiSearch // Scope to AI Search resource
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7ca78c08-252a-4471-8644-bb5ff32d4ba0') // Search Service Contributor
  }
}
resource backendIdentityAiSearchDataContrib 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(aiSearch.id, identity.id, 'SearchIndexDataContributor')
  scope: aiSearch // Scope to AI Search resource
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '8ebe5a00-799e-43f5-93ac-243d3dce84a7') // Search Index Data Contributor
  }
}
resource backendIdentityStorageBlobContrib 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAcct.id, identity.id, 'StorageBlobDataContributor')
  scope: storageAcct // Scope to Storage Account
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe') // Storage Blob Data Contributor
  }
}
resource backendIdentityCosmosDbContrib 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  // NOTE: Role Definition ID for Cosmos DB Data Plane access depends on the API (SQL vs Mongo)
  // Using a common one - verify this ID '00000000-0000-0000-0000-000000000002' (Cosmos DB Built-in Data Contributor - may need adjustment)
  // Or consider using connection strings / keys managed via Key Vault for Cosmos DB access from the app
  name: guid(cosmosDb.id, identity.id, 'CosmosDBDataContributor')
  scope: cosmosDb // Scope to Cosmos DB Account
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: resourceId('Microsoft.DocumentDB/databaseAccounts/sqlRoleDefinitions', '00000000-0000-0000-0000-000000000002') // Example: Cosmos DB Built-in Data Contributor - VERIFY/ADJUST
  }
}
resource backendIdentityAcrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.outputs.id, identity.id, 'AcrPull')
  scope: registry // Scope to Container Registry resource
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d') // AcrPull
  }
}
resource backendIdentitySessionPoolExecutor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(dynamicsession.id, identity.id, 'SessionPoolExecutor')
  scope: dynamicsession // Scope to Session Pool resource
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '0fb8eba5-a2bb-4abe-b1c1-49dfad359bb0') // Azure Container Apps Session Executor
  }
}

// User Roles
resource userSessionPoolExecutor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(dynamicsession.id, principalId, 'SessionPoolExecutorUser')
  scope: dynamicsession // Scope to Session Pool resource
  properties: {
    principalId: principalId
    principalType: 'User'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '0fb8eba5-a2bb-4abe-b1c1-49dfad359bb0') // Azure Container Apps Session Executor
  }
}

// === Backend Application Module ===
module backend './app/backend.bicep' = {
  name: 'backend'
  scope: rg
  params: {
    // --- Core App Params ---
    name: 'backend-${resourceToken}' // Unique name for the container app
    location: location
    tags: union(tags, {'azd-service-name': 'backend'}) // Add azd tag
    identityName: identity.name // Pass the name of the UAMI resource
    applicationInsightsName: applicationInsightsName // Pass AppInsights name
    containerAppsEnvironmentName: appsEnv.outputs.name
    containerRegistryName: containerRegistryName
    exists: srcExists
    appDefinition: srcDefinition
    userPrincipalId: principalId // Needed for some internal logic/roles in original backend?

    // --- Service Endpoints & Config ---
    customSubDomainName: '${prefix}-${resourceToken}' // Pass if needed by backend logic (though AI Service endpoint is primary)
    cosmosdbName: cosmosDb.name
    aiSearchName: aiSearch.name
    storageName: storageAcct.name
    vnetId: network.outputs.vnetId
    acaSubnetId: network.outputs.acaSubnetId // Pass ACA subnet
    defaultSubnetId: network.outputs.defaultSubnetId // Pass default subnet

    // --- AI & Session Pool Params (Crucial Updates) ---
    azureOpenaiEndpoint: aiService.outputs.endpoint // Use endpoint from ai-service module
    azureOpenaiEmbeddingDeploymentName: openAiDeploymentEmbeddingName // Pass the specific deployment name
    poolManagementEndpoint: dynamicsession.properties.poolManagementEndpoint // Use endpoint from dynamicsession resource
  }
  dependsOn: [
    // Ensure all dependencies are created before backend
    network,
    appsEnv,
    monitoring,
    registry,
    keyVault,
    storageAcct,
    cosmosDb,
    aiSearch,
    identity,
    aiService, // Depends on AI Service for endpoint/deployment info
    dynamicsession, // Depends on Session Pool for endpoint
    // Explicitly depend on role assignments needed by the backend identity
    backendIdentityAiSearchContrib,
    backendIdentityAiSearchDataContrib,
    backendIdentityStorageBlobContrib,
    backendIdentityCosmosDbContrib,
    backendIdentityAcrPull,
    backendIdentitySessionPoolExecutor
  ]
}

// === Frontend Application Module ===
module frontend './app/frontend.bicep' = {
  name: 'frontend'
  scope: rg
  params: {
    name: staticSiteName
    location: location // SWA location often differs, adjust if needed e.g., 'westeurope'
    tags: union(tags, {'azd-service-name': 'frontend'}) // Add azd tag
    repositoryUrl: srcDefinition.?repositoryUrl ?? '' // Use optional chaining
    branch: srcDefinition.?branch ?? '' // Use optional chaining
    appArtifactLocation: srcDefinition.?frontendArtifactLocation ?? '' // Use optional chaining
  }
}

// === Dashboard Module ===
module dashboard './shared/dashboard-web.bicep' = {
  name: 'dashboard'
  scope: rg
  params: {
    name: dashboardName
    applicationInsightsName: monitoring.outputs.applicationInsightsName
    location: location
    tags: tags
  }
  dependsOn: [
    monitoring // Dashboard depends on App Insights
  ]
}

// === Outputs ===
output AZURE_RESOURCE_GROUP string = rg.name
output AZURE_LOCATION string = location

// Service Endpoints & Connection Info
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = registry.outputs.loginServer
output AZURE_KEY_VAULT_NAME string = keyVault.outputs.name
output AZURE_KEY_VAULT_ENDPOINT string = keyVault.outputs.endpoint
output AZURE_OPENAI_ENDPOINT string = aiService.outputs.endpoint // Updated source
output POOL_MANAGEMENT_ENDPOINT string = dynamicsession.properties.poolManagementEndpoint
output SERVICE_BACKEND_URI string = backend.outputs.uri // Assuming backend module outputs 'uri'
output STATIC_SITE_ENDPOINT string = frontend.outputs.staticSiteEndpoint // Assuming frontend module outputs 'staticSiteEndpoint'
output COSMOS_DB_URI string = cosmosDb.properties.documentEndpoint
output COSMOS_DB_DATABASE string = 'ag_demo' // Hardcoded in original backend env vars
output CONTAINER_NAME string = 'ag_demo' // Hardcoded in original backend env vars
output AZURE_SEARCH_SERVICE_ENDPOINT string = 'https://${aiSearch.name}.search.windows.net'
output AZURE_STORAGE_ACCOUNT_ENDPOINT string = storageAcct.properties.primaryEndpoints.blob
output AZURE_STORAGE_ACCOUNT_ID string = storageAcct.id

// AI Model/Deployment Info
output AZURE_OPENAI_EMBEDDING_MODEL string = openAiDeploymentEmbeddingName // Output the deployment name variable

// Identity Info
output UAMI_RESOURCE_ID string = identity.id
output UAMI_CLIENT_ID string = identity.properties.clientId

// AI Foundry Info (Optional)
output AZURE_AI_HUB_NAME string = hub.outputs.name
output AZURE_AI_HUB_ID string = hub.outputs.id
output AZURE_AI_PROJECT_NAME string = project.outputs.name
output AZURE_AI_PROJECT_ID string = project.outputs.resourceId
