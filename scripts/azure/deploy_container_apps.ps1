# Railo Cloud Azure Container Apps deployment
# Fill in values, then run with PowerShell.

$subscription = "02453eb5-bdac-41d5-943f-c281dfaa310b"
$rg = "railo-cloud"
$loc = "eastasia"
$acr = "railoregistry"
$cae = "railo-env"
$storage = "railostore"
$kv = "railo-kv"
$pg = "railo-postgres"
$pgAdmin = "railo_admin"
$pgPass = $env:RAILO_PG_PASS
$pgSku = "standard_b1ms"
$redis = "railo-redis"
$redisSku = "Basic"
$apiApp = "railo-api"
$workerApp = "railo-worker"
$webApp = "railo-web"
$fixpointMode = "warn"
$githubAppId = "2914293"
$githubWebhookSecret = $env:RAILO_GITHUB_WEBHOOK_SECRET
$githubPrivateKeyPath = $env:RAILO_GITHUB_PRIVATE_KEY_PATH

if (-not $pgPass) {
  $pgPass = Read-Host "Enter Postgres admin password"
}
if (-not $githubWebhookSecret) {
  $githubWebhookSecret = Read-Host "Enter GitHub webhook secret"
}
if (-not $githubPrivateKeyPath) {
  $githubPrivateKeyPath = "E:\\fixpoint-cloud\\secrets\\railo-cloud-github-app.pem"
}

# Ensure Azure CLI is available in this session
$azPath = "C:\\Program Files\\Microsoft SDKs\\Azure\\CLI2\\wbin"
if ($env:Path -notlike "*${azPath}*") {
  $env:Path += ";$azPath"
}
if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
  Write-Error "Azure CLI (az) not found. Install it or add it to PATH."
  exit 1
}

# Ensure we are logged in
try {
  az account show -o none | Out-Null
} catch {
  Write-Error "Please run 'az login' in this terminal before running the script."
  exit 1
}

az account set --subscription $subscription

az group create -n $rg -l $loc

# Register resource providers up front
az extension add --name containerapp --upgrade --allow-preview true
az provider register --namespace Microsoft.App --wait
az provider register --namespace Microsoft.OperationalInsights --wait
az provider register --namespace Microsoft.ContainerRegistry --wait
az provider register --namespace Microsoft.Storage --wait
az provider register --namespace Microsoft.DBforPostgreSQL --wait
az provider register --namespace Microsoft.Cache --wait
az provider register --namespace Microsoft.KeyVault --wait
az provider register --namespace Microsoft.ManagedIdentity --wait

az acr create -n $acr -g $rg --sku Basic
$acrLoginServer = (az acr show -n $acr -g $rg --query loginServer -o tsv)
if (-not $acrLoginServer) {
  Write-Error "ACR login server not found. Check policy/region restrictions for Container Registry."
  exit 1
}
az acr login -n $acr

az storage account create -n $storage -g $rg -l $loc --sku Standard_LRS
$storageKey = (az storage account keys list -n $storage -g $rg --query "[0].value" -o tsv)
az storage container create --account-name $storage --name artifacts --public-access off --account-key $storageKey

az postgres flexible-server create -g $rg -n $pg -l $loc --tier Burstable --sku-name $pgSku --admin-user $pgAdmin --admin-password $pgPass --public-access none
$pgHost = (az postgres flexible-server show -g $rg -n $pg --query "fullyQualifiedDomainName" -o tsv)
$pgConn = "postgresql+psycopg://$pgAdmin`:$pgPass@$pgHost`:5432/railo"

az redis create -g $rg -n $redis --location $loc --sku $redisSku --vm-size c0
$redisHost = (az redis show -g $rg -n $redis --query "hostName" -o tsv)
$redisKey = (az redis list-keys -g $rg -n $redis --query "primaryKey" -o tsv)
$redisUrl = "redis://`:$redisKey@$redisHost`:6379/0"

# Managed identity for Key Vault access
$miName = "railo-mi"
az identity create -g $rg -n $miName -l $loc
$miId = (az identity show -g $rg -n $miName --query id -o tsv)
$miPrincipalId = (az identity show -g $rg -n $miName --query principalId -o tsv)

az keyvault create -n $kv -g $rg -l $loc
$kvId = (az keyvault show -n $kv -g $rg --query id -o tsv)

# Grant current user permissions to set secrets (RBAC vault)
$currentUserId = (az ad signed-in-user show --query id -o tsv)
az role assignment create --assignee $currentUserId --role "Key Vault Secrets Officer" --scope $kvId

# Grant managed identity permissions to read secrets
az role assignment create --assignee $miPrincipalId --role "Key Vault Secrets User" --scope $kvId

# RBAC can take a moment to propagate
Start-Sleep -Seconds 20

az keyvault secret set --vault-name $kv -n pg-conn --value $pgConn
az keyvault secret set --vault-name $kv -n redis-url --value $redisUrl
az keyvault secret set --vault-name $kv -n github-app-id --value $githubAppId
az keyvault secret set --vault-name $kv -n github-webhook-secret --value $githubWebhookSecret
az keyvault secret set --vault-name $kv -n github-private-key --file $githubPrivateKeyPath

az containerapp env create -g $rg -n $cae -l $loc

# Build and push images
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Push-Location $root

docker build -t $acrLoginServer/railo-api:latest -f fixpoint-cloud/docker/Dockerfile .
docker push $acrLoginServer/railo-api:latest

docker build -t $acrLoginServer/railo-worker:latest -f fixpoint-cloud/docker/Dockerfile .
docker push $acrLoginServer/railo-worker:latest

docker build -t $acrLoginServer/railo-web:latest -f fixpoint-cloud/web/Dockerfile fixpoint-cloud/web
docker push $acrLoginServer/railo-web:latest

Pop-Location

# API container app
az containerapp create -g $rg -n $apiApp --environment $cae `
  --image $acrLoginServer/railo-api:latest `
  --target-port 8000 --ingress external `
  --registry-server $acrLoginServer `
  --registry-identity $miId `
  --user-assigned $miId `
  --env-vars `
    DATABASE_URL=secretref:pg-conn `
    REDIS_URL=secretref:redis-url `
    GITHUB_APP_ID=secretref:github-app-id `
    GITHUB_WEBHOOK_SECRET=secretref:github-webhook-secret `
    GITHUB_APP_PRIVATE_KEY=secretref:github-private-key `
    ENGINE_MODE=live `
    FIXPOINT_MODE=$fixpointMode `
  --secrets `
    pg-conn=keyvaultref:https://$kv.vault.azure.net/secrets/pg-conn,identityref:$miId `
    redis-url=keyvaultref:https://$kv.vault.azure.net/secrets/redis-url,identityref:$miId `
    github-app-id=keyvaultref:https://$kv.vault.azure.net/secrets/github-app-id,identityref:$miId `
    github-webhook-secret=keyvaultref:https://$kv.vault.azure.net/secrets/github-webhook-secret,identityref:$miId `
    github-private-key=keyvaultref:https://$kv.vault.azure.net/secrets/github-private-key,identityref:$miId

# Worker container app
az containerapp create -g $rg -n $workerApp --environment $cae `
  --image $acrLoginServer/railo-worker:latest `
  --ingress internal `
  --registry-server $acrLoginServer `
  --registry-identity $miId `
  --user-assigned $miId `
  --env-vars `
    DATABASE_URL=secretref:pg-conn `
    REDIS_URL=secretref:redis-url `
    GITHUB_APP_ID=secretref:github-app-id `
    GITHUB_WEBHOOK_SECRET=secretref:github-webhook-secret `
    GITHUB_APP_PRIVATE_KEY=secretref:github-private-key `
    ENGINE_MODE=live `
    FIXPOINT_MODE=$fixpointMode `
  --secrets `
    pg-conn=keyvaultref:https://$kv.vault.azure.net/secrets/pg-conn,identityref:$miId `
    redis-url=keyvaultref:https://$kv.vault.azure.net/secrets/redis-url,identityref:$miId `
    github-app-id=keyvaultref:https://$kv.vault.azure.net/secrets/github-app-id,identityref:$miId `
    github-webhook-secret=keyvaultref:https://$kv.vault.azure.net/secrets/github-webhook-secret,identityref:$miId `
    github-private-key=keyvaultref:https://$kv.vault.azure.net/secrets/github-private-key,identityref:$miId

$apiHost = (az containerapp show -g $rg -n $apiApp --query "properties.configuration.ingress.fqdn" -o tsv)
Write-Host "API hostname: https://$apiHost"
if (-not $apiHost) {
  Write-Error "API hostname not found. Fix API container app creation before deploying the web app."
  exit 1
}

# Web container app
az containerapp create -g $rg -n $webApp --environment $cae `
  --image $acrLoginServer/railo-web:latest `
  --target-port 3000 --ingress external `
  --registry-server $acrLoginServer `
  --registry-identity $miId `
  --user-assigned $miId `
  --env-vars `
    NEXT_PUBLIC_API_BASE_URL=https://$apiHost

$webHost = (az containerapp show -g $rg -n $webApp --query "properties.configuration.ingress.fqdn" -o tsv)
Write-Host "Web hostname: https://$webHost"
