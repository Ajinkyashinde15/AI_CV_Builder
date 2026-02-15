#!/bin/bash
# Deployment script for AWS Lambda

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
ENVIRONMENT="${1:-dev}"
AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-$(aws sts get-caller-identity --query Account --output text)}"
ECR_REPO_NAME="cv-builder"
S3_BUCKET_NAME="ai-resume-cv-bucket"
DYNAMODB_TABLE="CvBuilderDb"
SECRETS_NAME="CvBuilderSecretsManager"

echo -e "${YELLOW}=== AI CV Builder - AWS Lambda Deployment ===${NC}"
echo "Environment: $ENVIRONMENT"
echo "Region: $AWS_REGION"
echo "Account ID: $AWS_ACCOUNT_ID"

# ============================================================================
# 1. VERIFY AWS CREDENTIALS
# ============================================================================
echo -e "${YELLOW}\n[1/7] Verifying AWS credentials...${NC}"
if ! aws sts get-caller-identity &>/dev/null; then
    echo -e "${RED}ERROR: AWS credentials not configured${NC}"
    exit 1
fi
echo -e "${GREEN}✓ AWS credentials verified${NC}"

# ============================================================================
# 2. CREATE ECR REPOSITORY (if not exists)
# ============================================================================
echo -e "${YELLOW}\n[2/7] Setting up ECR repository...${NC}"
REGISTRY_URL="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
IMAGE_URI="${REGISTRY_URL}/${ECR_REPO_NAME}:latest"
IMAGE_URI_VERSIONED="${REGISTRY_URL}/${ECR_REPO_NAME}:${ENVIRONMENT}-$(date +%s)"

if ! aws ecr describe-repositories --repository-names $ECR_REPO_NAME --region $AWS_REGION &>/dev/null; then
    echo "Creating ECR repository: $ECR_REPO_NAME"
    aws ecr create-repository \
        --repository-name $ECR_REPO_NAME \
        --region $AWS_REGION \
        --image-scanning-configuration scanOnPush=true
else
    echo "ECR repository already exists"
fi
echo -e "${GREEN}✓ ECR repository ready${NC}"

# ============================================================================
# 3. AUTHENTICATE DOCKER WITH ECR
# ============================================================================
echo -e "${YELLOW}\n[3/7] Authenticating Docker with ECR...${NC}"
aws ecr get-login-password --region $AWS_REGION | \
    docker login --username AWS --password-stdin $REGISTRY_URL
echo -e "${GREEN}✓ Docker authenticated${NC}"

# ============================================================================
# 4. BUILD AND PUSH IMAGE
# ============================================================================
echo -e "${YELLOW}\n[4/7] Building and pushing Docker image...${NC}"
echo "Building from backend/Dockerfile.lambda..."
docker build \
    -f backend/Dockerfile.lambda \
    -t $IMAGE_URI \
    -t $IMAGE_URI_VERSIONED \
    .

echo "Pushing to ECR..."
docker push $IMAGE_URI
docker push $IMAGE_URI_VERSIONED

echo -e "${GREEN}✓ Image built and pushed${NC}"
echo "Image URI: $IMAGE_URI"

# ============================================================================
# 5. ENSURE S3 BUCKET EXISTS
# ============================================================================
echo -e "${YELLOW}\n[5/7] Verifying S3 bucket...${NC}"
if aws s3api head-bucket --bucket $S3_BUCKET_NAME --region $AWS_REGION 2>/dev/null; then
    echo "S3 bucket exists: $S3_BUCKET_NAME"
else
    echo "Creating S3 bucket: $S3_BUCKET_NAME"
    aws s3api create-bucket \
        --bucket $S3_BUCKET_NAME \
        --region $AWS_REGION \
        $([ "$AWS_REGION" != "us-east-1" ] && echo "--create-bucket-configuration LocationConstraint=$AWS_REGION")
    
    # Block public access
    aws s3api put-public-access-block \
        --bucket $S3_BUCKET_NAME \
        --public-access-block-configuration \
        "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
fi
echo -e "${GREEN}✓ S3 bucket verified${NC}"

# ============================================================================
# 6. CREATE/UPDATE SECRETS IN SECRETS MANAGER
# ============================================================================
echo -e "${YELLOW}\n[6/7] Setting up Secrets Manager...${NC}"

# Read secrets from environment or prompt user
read -sp "Enter Hugging Face API Token (or leave blank for current value): " HF_TOKEN
echo
HF_TOKEN=${HF_TOKEN:-$HF_API_TOKEN}

read -sp "Enter Gemini API Key (or leave blank for current value): " GEMINI_KEY
echo
GEMINI_KEY=${GEMINI_KEY:-$GEMINI_API_KEY}

SECRET_JSON=$(cat <<EOF
{
  "HF_API_TOKEN": "$HF_TOKEN",
  "GEMINI_API_KEY": "$GEMINI_KEY"
}
EOF
)

# Check if secret exists
if aws secretsmanager get-secret-value --secret-id $SECRETS_NAME --region $AWS_REGION &>/dev/null; then
    echo "Updating existing secret: $SECRETS_NAME"
    aws secretsmanager update-secret \
        --secret-id $SECRETS_NAME \
        --secret-string "$SECRET_JSON" \
        --region $AWS_REGION
else
    echo "Creating new secret: $SECRETS_NAME"
    aws secretsmanager create-secret \
        --name $SECRETS_NAME \
        --description "API keys for CV Builder (HF and Gemini)" \
        --secret-string "$SECRET_JSON" \
        --region $AWS_REGION
fi
echo -e "${GREEN}✓ Secrets configured${NC}"

# ============================================================================
# 7. DEPLOY WITH SAM
# ============================================================================
echo -e "${YELLOW}\n[7/7] Deploying with SAM...${NC}"

# Get current secrets from Secrets Manager for validation
HF_TOKEN=$(echo $SECRET_JSON | grep -o '"HF_API_TOKEN": "[^"]*' | grep -o '[^"]*$')
GEMINI_KEY=$(echo $SECRET_JSON | grep -o '"GEMINI_API_KEY": "[^"]*' | grep -o '[^"]*$')

sam deploy \
    --template-file infra/sam-template.yaml \
    --stack-name "cv-builder-${ENVIRONMENT}" \
    --parameter-overrides \
        Environment=$ENVIRONMENT \
        S3BucketName=$S3_BUCKET_NAME \
        DynamoDBTableName=$DYNAMODB_TABLE \
        SecretsManagerName=$SECRETS_NAME \
        ECRImageUri=$IMAGE_URI \
        HFApiToken="$HF_TOKEN" \
        GeminiApiKey="$GEMINI_KEY" \
    --region $AWS_REGION \
    --capabilities CAPABILITY_IAM \
    --no-fail-on-empty-changeset

echo -e "${GREEN}✓ Deployment complete${NC}"

# ============================================================================
# OUTPUT
# ============================================================================
echo -e "${GREEN}\n=== Deployment Summary ===${NC}"
echo "Environment: $ENVIRONMENT"
echo "Region: $AWS_REGION"
echo "Account: $AWS_ACCOUNT_ID"
echo "ECR Image: $IMAGE_URI"
echo "Stack Name: cv-builder-${ENVIRONMENT}"

# Get stack outputs
echo -e "\n${YELLOW}Stack Outputs:${NC}"
aws cloudformation describe-stacks \
    --stack-name "cv-builder-${ENVIRONMENT}" \
    --region $AWS_REGION \
    --query 'Stacks[0].Outputs[*].[OutputKey,OutputValue]' \
    --output table

echo -e "\n${GREEN}Next steps:${NC}"
echo "1. Test API endpoint from outputs above"
echo "2. Upload sample CVs to S3: s3://$S3_BUCKET_NAME/rawcvs/"
echo "3. Monitor logs: aws logs tail /aws/lambda/cv-builder-${ENVIRONMENT} --follow"
echo "4. View metrics: aws cloudwatch get-metric-statistics..."
