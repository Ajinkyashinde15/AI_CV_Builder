param(
    [string]$Environment = "dev",
    [string]$AwsRegion = "us-east-1"
)

$ErrorActionPreference = "Stop"
$WarningPreference = "SilentlyContinue"

# Colors for output
function Write-Step { param([string]$Message) Write-Host "==== $Message ==== " -ForegroundColor Magenta }
function Write-Info { param([string]$Message) Write-Host "INFO: $Message" -ForegroundColor Cyan }
function Write-Ok { param([string]$Message) Write-Host "OK: $Message" -ForegroundColor Green }
function Write-Warn { param([string]$Message) Write-Host "WARN: $Message" -ForegroundColor Yellow }
function Write-Err { param([string]$Message) Write-Host "ERROR: $Message" -ForegroundColor Red }

# Configuration
$ECR_REPO_NAME = "cv-builder"
$S3_BUCKET_NAME = "ai-resume-cv-bucket"
$DYNAMODB_TABLE = "CvBuilderDb"
$SECRETS_NAME = "CvBuilderSecretsManager"

Write-Host "`n" -ForegroundColor Green
Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║   AI CV Builder - AWS Lambda Deployment (PowerShell)       ║" -ForegroundColor Green
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Green

Write-Info "Environment: $Environment"
Write-Info "Region: $AwsRegion"

# ============================================================================
# 1. VERIFY AWS CREDENTIALS
# ============================================================================
Write-Step "STEP 1: VERIFYING AWS CREDENTIALS"
try {
    $AccountId = aws sts get-caller-identity --query Account --output text
    Write-Ok "AWS credentials verified (Account: $AccountId)"
} catch {
    Write-Err "AWS credentials not configured"
    exit 1
}

# ============================================================================
# 2. CREATE ECR REPOSITORY
# ============================================================================
Write-Step "STEP 2: SETTING UP ECR REPOSITORY"
$REGISTRY_URL = "$AccountId.dkr.ecr.$AwsRegion.amazonaws.com"
$IMAGE_URI = "$REGISTRY_URL/$ECR_REPO_NAME`:latest"
$IMAGE_URI_VERSIONED = "$REGISTRY_URL/$ECR_REPO_NAME`:$Environment-$(Get-Date -Format 'yyyyMMddHHmmss')"

try {
    aws ecr describe-repositories --repository-names $ECR_REPO_NAME --region $AwsRegion | Out-Null
    Write-Info "ECR repository already exists"
} catch {
    Write-Info "Creating ECR repository: $ECR_REPO_NAME"
    aws ecr create-repository `
        --repository-names $ECR_REPO_NAME `
        --region $AwsRegion `
        --image-scanning-configuration scanOnPush=true | Out-Null
}
Write-Ok "ECR repository ready"

# ============================================================================
# 3. AUTHENTICATE DOCKER WITH ECR
# ============================================================================
Write-Step "STEP 3: AUTHENTICATING DOCKER WITH ECR"
$LoginToken = aws ecr get-login-password --region $AwsRegion
$LoginToken | docker login --username AWS --password-stdin $REGISTRY_URL
Write-Ok "Docker authenticated with ECR"

# ============================================================================
# 4. BUILD AND PUSH IMAGE
# ============================================================================
Write-Step "STEP 4: BUILDING AND PUSHING DOCKER IMAGE"
Write-Info "Building Docker image..."
docker build `
    -f backend/Dockerfile.lambda `
    -t $IMAGE_URI `
    -t $IMAGE_URI_VERSIONED `
    .

if ($LASTEXITCODE -ne 0) {
    Write-Err "Docker build failed"
    exit 1
}

Write-Info "Pushing image to ECR..."
docker push $IMAGE_URI
docker push $IMAGE_URI_VERSIONED

if ($LASTEXITCODE -ne 0) {
    Write-Err "Docker push failed"
    exit 1
}

Write-Ok "Image built and pushed"
Write-Info "Image URI: $IMAGE_URI"

# ============================================================================
# 5. VERIFY S3 BUCKET
# ============================================================================
Write-Step "STEP 5: VERIFYING S3 BUCKET"
try {
    aws s3api head-bucket --bucket $S3_BUCKET_NAME --region $AwsRegion 2> $null
    Write-Info "S3 bucket exists: $S3_BUCKET_NAME"
} catch {
    Write-Info "Creating S3 bucket: $S3_BUCKET_NAME"
    
    if ($AwsRegion -eq "us-east-1") {
        aws s3api create-bucket `
            --bucket $S3_BUCKET_NAME `
            --region $AwsRegion
    } else {
        aws s3api create-bucket `
            --bucket $S3_BUCKET_NAME `
            --region $AwsRegion `
            --create-bucket-configuration LocationConstraint=$AwsRegion
    }
    
    # Block public access
    aws s3api put-public-access-block `
        --bucket $S3_BUCKET_NAME `
        --public-access-block-configuration `
        "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
}
Write-Ok "S3 bucket verified"

# ============================================================================
# 6. SETUP SECRETS MANAGER
# ============================================================================
Write-Step "STEP 6: SETTING UP SECRETS MANAGER"

$HFToken = Read-Host -AsSecureString "Enter Hugging Face API Token (or press Enter to skip)"
$HFToken = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto([System.Runtime.InteropServices.Marshal]::SecureStringToCoTaskMemUnicode($HFToken))

$GeminiKey = Read-Host -AsSecureString "Enter Gemini API Key (or press Enter to skip)"
$GeminiKey = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto([System.Runtime.InteropServices.Marshal]::SecureStringToCoTaskMemUnicode($GeminiKey))

$SecretJson = @{
    "HF_API_TOKEN" = $HFToken
    "GEMINI_API_KEY" = $GeminiKey
} | ConvertTo-Json -Compress

try {
    aws secretsmanager get-secret-value --secret-id $SECRETS_NAME --region $AwsRegion 2> $null | Out-Null
    Write-Info "Updating existing secret: $SECRETS_NAME"
    aws secretsmanager update-secret `
        --secret-id $SECRETS_NAME `
        --secret-string $SecretJson `
        --region $AwsRegion
} catch {
    Write-Info "Creating new secret: $SECRETS_NAME"
    aws secretsmanager create-secret `
        --name $SECRETS_NAME `
        --description "API keys for CV Builder (HF and Gemini)" `
        --secret-string $SecretJson `
        --region $AwsRegion
}
Write-Ok "Secrets configured"

# ============================================================================
# 7. DEPLOY WITH SAM
# ============================================================================
Write-Step "STEP 7: DEPLOYING WITH SAM"
Write-Info "Running SAM deployment..."

sam deploy `
    --template-file infra\sam-template.yaml `
    --stack-name "cv-builder-$Environment" `
    --parameter-overrides `
        Environment=$Environment `
        S3BucketName=$S3_BUCKET_NAME `
        DynamoDBTableName=$DYNAMODB_TABLE `
        SecretsManagerName=$SECRETS_NAME `
        ECRImageUri=$IMAGE_URI `
        HFApiToken="$HFToken" `
        GeminiApiKey="$GeminiKey" `
    --region $AwsRegion `
    --capabilities CAPABILITY_IAM `
    --no-fail-on-empty-changeset

if ($LASTEXITCODE -ne 0) {
    Write-Err "SAM deployment failed"
    exit 1
}

Write-Ok "Deployment complete"

# ============================================================================
# OUTPUT SUMMARY
# ============================================================================
Write-Host "`n" -ForegroundColor Green
Write-Host "╔════════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║          DEPLOYMENT SUMMARY                               ║" -ForegroundColor Green
Write-Host "╚════════════════════════════════════════════════════════════╝" -ForegroundColor Green

Write-Info "Environment: $Environment"
Write-Info "Region: $AwsRegion"
Write-Info "Account ID: $AccountId"
Write-Info "ECR Image: $IMAGE_URI"
Write-Info "Stack Name: cv-builder-$Environment"

Write-Host "`n${YELLOW}Stack Outputs:${NC}" -ForegroundColor Yellow
aws cloudformation describe-stacks `
    --stack-name "cv-builder-$Environment" `
    --region $AwsRegion `
    --query 'Stacks[0].Outputs[*].[OutputKey,OutputValue]' `
    --output table

Write-Host "`nNext steps:" -ForegroundColor Green
Write-Host "1. Test API endpoint from outputs above" -ForegroundColor Cyan
Write-Host "2. Upload sample CVs to S3: s3://$S3_BUCKET_NAME/rawcvs/" -ForegroundColor Cyan
Write-Host "3. Monitor logs: aws logs tail /aws/lambda/cv-builder-$Environment --follow" -ForegroundColor Cyan
Write-Host "4. Troubleshoot with: aws lambda invoke --function-name cv-builder-$Environment --payload '{...}' response.json" -ForegroundColor Cyan
