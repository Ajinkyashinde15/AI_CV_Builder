param(
  [string]$LocalStackEndpoint = "http://localhost:4566",
  [string]$BucketName = "ai-resume-cv-bucket",
  [string]$Region = "us-east-1",
  [string]$CvPrefix = "rawcvs/",
  [string]$ResumePrefix = "processedresumes/",
  [string]$TableName = "drc-core-dyn",
  [string]$SecretName = "drc_secrets",
  [string]$HFApiToken = "",
  [string]$GeminiApiKey = "",
  [bool]$UploadSampleCvs = $true
)

$ErrorActionPreference = "Stop"
$WarningPreference = "SilentlyContinue"

function Write-Step { param([string]$Message) Write-Host "==== $Message ==== " -ForegroundColor Magenta }
function Write-Info { param([string]$Message) Write-Host "INFO: $Message" -ForegroundColor Cyan }
function Write-Ok { param([string]$Message) Write-Host "OK: $Message" -ForegroundColor Green }
function Write-Warn { param([string]$Message) Write-Host "WARN: $Message" -ForegroundColor Yellow }
function Write-Err { param([string]$Message) Write-Host "ERROR: $Message" -ForegroundColor Red }

function Test-Prerequisites {
  Write-Step "CHECKING PREREQUISITES"
  $allOk = $true

  try { docker --version | Out-Null; Write-Info "Docker found" } catch { Write-Err "Docker not found"; $allOk = $false }
  try { docker info | Out-Null; Write-Info "Docker daemon is running" } catch { Write-Err "Docker daemon not running"; $allOk = $false }
  try { docker compose version | Out-Null; Write-Info "Docker Compose found" } catch { Write-Err "Docker Compose not found"; $allOk = $false }
  try { aws --version | Out-Null; Write-Info "AWS CLI found" } catch { Write-Err "AWS CLI not found"; $allOk = $false }

  if (-not $allOk) { throw "Prerequisite check failed." }
}

function Invoke-AwsLocalStack {
  param([Parameter(Mandatory=$true)][string[]]$Args)
  $fullArgs = @($Args + @("--endpoint-url=$LocalStackEndpoint", "--region=$Region"))
  & aws @fullArgs 2>&1
}

function Docker-Compose-Up {
  Write-Step "DOCKER COMPOSE UP"
  Push-Location (Join-Path $PSScriptRoot "..")
  try {
    docker compose down --remove-orphans | Out-Null
    docker compose build --no-cache
    docker compose up -d
    Write-Ok "Containers started"
    Start-Sleep -Seconds 3
  } finally { Pop-Location }
}

# Main
Write-Step "LOCAL ENV SETUP"
Test-Prerequisites
#Docker-Compose-Up #Launch Backend and Frontend containers in docker desktop 

# Set AWS env for local shell usage (LocalStack)
$env:AWS_ACCESS_KEY_ID = "test"
$env:AWS_SECRET_ACCESS_KEY = "test"
$env:AWS_DEFAULT_REGION = $Region

# --- Ensure AWS S3 module is loaded ---
Import-Module AWS.Tools.S3 -ErrorAction Stop

# -------- S3 Helpers --------
function Test-S3BucketExists {
    param(
        [Parameter(Mandatory)] [string] $BucketName,
        [Parameter(Mandatory)] [string] $LocalStackEndpoint
    )
    try {
        # List all and check by name
        $buckets = Get-S3Bucket -EndpointUrl $LocalStackEndpoint
        $names = $buckets | Select-Object -ExpandProperty BucketName
        return $names -contains $BucketName
    } catch {
        Write-Verbose "Failed to list buckets: $_"
        return $false
    }
}

# -------- Ensure bucket --------
if (-not (Test-S3BucketExists -BucketName $BucketName -LocalStackEndpoint $LocalStackEndpoint)) {
    Write-Host "Creating bucket '$BucketName' in region '$Region' on LocalStack..." -ForegroundColor Cyan
    New-S3Bucket -BucketName $BucketName -Region $Region -EndpointUrl $LocalStackEndpoint | Out-Null
} else {
    Write-Host "Bucket '$BucketName' already exists." -ForegroundColor Yellow
}

# -------- Optional: upload sample CVs --------
if ($UploadSampleCvs) {
    Write-Host "Uploading sample CVs..." -ForegroundColor Cyan
    $sampleFiles = @(
        # Add your local files here (update paths)
        "sample_cv_1.docx", "sample_cv_2.docx"
    ) | Where-Object { Test-Path $_ }

    foreach ($file in $sampleFiles) {
        $key = ($CvPrefix.TrimEnd('/')) + "/" + (Split-Path $file -Leaf)
        Write-S3Object -BucketName $BucketName -File $file -Key $key -EndpointUrl $LocalStackEndpoint | Out-Null
        Write-Host "Uploaded $file -> s3://$BucketName/$key" -ForegroundColor Green
    }
}

# -------- Ensure DynamoDB table (pk/sk, PAY_PER_REQUEST) --------
Add-Type -AssemblyName "AWSSDK.Core"
Add-Type -AssemblyName "AWSSDK.DynamoDBv2"

$ddbCfg = New-Object Amazon.DynamoDBv2.AmazonDynamoDBConfig
$ddbCfg.RegionEndpoint = [Amazon.RegionEndpoint]::GetBySystemName($Region)
if ($LocalStackEndpoint) { $ddbCfg.ServiceURL = $LocalStackEndpoint }
$ddbClient = New-Object Amazon.DynamoDBv2.AmazonDynamoDBClient($ddbCfg)

# Exists?
$ddbExists = $false
try {
    $null = $ddbClient.DescribeTableAsync($TableName).GetAwaiter().GetResult()
    $ddbExists = $true
} catch { }

if (-not $ddbExists) {
    Write-Host "Creating DynamoDB table '$TableName' in region '$Region' on LocalStack..." -ForegroundColor Cyan

    $req = [Amazon.DynamoDBv2.Model.CreateTableRequest]::new()
    $req.TableName   = $TableName
    $req.BillingMode = [Amazon.DynamoDBv2.BillingMode]::PAY_PER_REQUEST

    # Initialize lists BEFORE calling .Add()
    $req.AttributeDefinitions = New-Object 'System.Collections.Generic.List[Amazon.DynamoDBv2.Model.AttributeDefinition]'
    $req.KeySchema            = New-Object 'System.Collections.Generic.List[Amazon.DynamoDBv2.Model.KeySchemaElement]'

    $req.AttributeDefinitions.Add([Amazon.DynamoDBv2.Model.AttributeDefinition]::new("pk","S"))
    $req.AttributeDefinitions.Add([Amazon.DynamoDBv2.Model.AttributeDefinition]::new("sk","S"))
    $req.KeySchema.Add([Amazon.DynamoDBv2.Model.KeySchemaElement]::new("pk","HASH"))
    $req.KeySchema.Add([Amazon.DynamoDBv2.Model.KeySchemaElement]::new("sk","RANGE"))

    $null = $ddbClient.CreateTableAsync($req).GetAwaiter().GetResult()
    Write-Host "Table '$TableName' created." -ForegroundColor Green

    # Wait until ACTIVE (≤ ~60s)
    $deadline = [DateTime]::UtcNow.AddSeconds(60)
    do {
        Start-Sleep -Seconds 2
        $desc = $ddbClient.DescribeTableAsync($TableName).GetAwaiter().GetResult()
    } while ($desc.Table.TableStatus -ne 'ACTIVE' -and [DateTime]::UtcNow -lt $deadline)

    if ($desc.Table.TableStatus -eq 'ACTIVE') {
        Write-Host "Table '$TableName' is ACTIVE." -ForegroundColor Green
    } else {
        Write-Warning "Timed out waiting for table '$TableName' to become ACTIVE."
    }
} else {
    Write-Host "DynamoDB table '$TableName' already exists." -ForegroundColor Yellow
}

# -------- AWS Secrets Manager Setup --------
Write-Step "SETTING UP AWS SECRETS MANAGER"

# Create or update the secret
$secretValue = @{
    "HF_API_TOKEN" = "test"
    "GEMINI_API_KEY" = "test"
} | ConvertTo-Json -Compress

$secretJson = $secretValue | ConvertTo-Json -Compress

aws secretsmanager create-secret `
  --name $SecretName `
  --secret-string $secretJson `
  --endpoint-url $LocalStackEndpoint `
| Out-Null

Write-Host "Created new secret '$SecretName' in LocalStack..." -ForegroundColor Cyan

Write-Host "DONE" -ForegroundColor Green
Write-Host "Open Streamlit: http://localhost:8501" -ForegroundColor Green
Write-Host "API docs:    http://localhost:8000/docs" -ForegroundColor Green
Write-Host "LocalStack: http://localhost:4566" -ForegroundColor Green