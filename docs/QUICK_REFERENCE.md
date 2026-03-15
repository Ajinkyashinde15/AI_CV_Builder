# Quick Reference: Lambda Deployment

Fast reference for deployment commands and troubleshooting.

## One-Command Deployment

### Windows (PowerShell)
```powershell
.\scripts\deploy-lambda.ps1 -Environment dev
```

### Linux/macOS (Bash)
```bash
./scripts/deploy-lambda.sh dev
```

---

## Key AWS Resources

### S3 Bucket
```bash
# List CVs
aws s3 ls s3://ai-resume-cv-bucket/rawcvs/

# Upload sample CV
aws s3 cp sample_cv.docx s3://ai-resume-cv-bucket/rawcvs/

# List generated resumes
aws s3 ls s3://ai-resume-cv-bucket/processedresumes/
```

### DynamoDB
```bash
# Scan trace table
aws dynamodb scan --table-name drc-core-dyn

# Get specific trace
aws dynamodb get-item \
    --table-name drc-core-dyn \
    --key '{"pk":{"S":"REQUEST-ID"},"sk":{"S":"FILE-KEY"}}'
```

### Secrets Manager
```bash
# View secret
aws secretsmanager get-secret-value \
    --secret-id drc_secrets \
    --query SecretString --output text | jq

# Update secret
aws secretsmanager update-secret \
    --secret-id drc_secrets \
    --secret-string '{"HF_API_TOKEN":"new_token","GEMINI_API_KEY":"new_key"}'
```

### Lambda Function
```bash
# Get function config
aws lambda get-function-configuration \
    --function-name cv-builder-dev

# Invoke function
aws lambda invoke \
    --function-name cv-builder-dev \
    --payload '{"path":"/resume/list-cvs","httpMethod":"GET"}' \
    response.json

# View logs
aws logs tail /aws/lambda/cv-builder-dev --follow
```

### API Gateway
```bash
# Get endpoint URL
aws cloudformation describe-stacks \
    --stack-name cv-builder-dev \
    --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' \
    --output text

# Test endpoint
API_URL=$(aws cloudformation describe-stacks \
    --stack-name cv-builder-dev \
    --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' \
    --output text)

curl $API_URL/resume/list-cvs
```

---

## Environment Variables (for SAM deployment)

```
ENV=dev
AWS_REGION=us-east-1
S3_BUCKET=ai-resume-cv-bucket
S3_CV_PREFIX=rawcvs/
S3_RESUME_PREFIX=processedresumes/
TRACE_TABLE=drc-core-dyn
SECRETS_MANAGER_NAME=drc_secrets
LLM_PROVIDER=hf_endpoint  # or "gemini"
GEMINI_MODEL=gemini-1.5-flash
HF_MODEL=Qwen/Qwen2.5-14B-Instruct-1M
HF_MAX_NEW_TOKENS=1024
```

---

## Deployment Steps (Manual)

```bash
# 1. Build image
docker build -f backend/Dockerfile.lambda -t cv-builder:latest .

# 2. Tag for ECR
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
docker tag cv-builder:latest $ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/cv-builder:latest

# 3. Push to ECR
aws ecr get-login-password --region us-east-1 | \
    docker login --username AWS --password-stdin \
    $ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com

docker push $ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/cv-builder:latest

# 4. Deploy with SAM
IMAGE_URI=$ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com/cv-builder:latest

sam deploy \
    --template-file infra/sam-template.yaml \
    --stack-name cv-builder-dev \
    --parameter-overrides Environment=dev ECRImageUri=$IMAGE_URI \
    --capabilities CAPABILITY_IAM
```

---

## Troubleshooting

### Check Logs
```bash
# Real-time logs
aws logs tail /aws/lambda/cv-builder-dev --follow

# Errors only
aws logs tail /aws/lambda/cv-builder-dev --filter-pattern "ERROR"

# Last invocation
aws logs tail /aws/lambda/cv-builder-dev --max-items 50
```

### Invoke Function Directly
```bash
aws lambda invoke \
    --function-name cv-builder-dev \
    --payload '{"path":"/health","httpMethod":"GET"}' \
    response.json

cat response.json
```

### Check Role Permissions
```bash
# List attached policies
aws iam list-attached-role-policies \
    --role-name cv-builder-LambdaExecutionRole

# View inline policies
aws iam list-role-policies \
    --role-name cv-builder-LambdaExecutionRole

# Get policy details
aws iam get-role-policy \
    --role-name cv-builder-LambdaExecutionRole \
    --policy-name S3Access
```

### Verify Resources
```bash
# S3 bucket
aws s3api head-bucket --bucket ai-resume-cv-bucket

# DynamoDB table
aws dynamodb describe-table --table-name drc-core-dyn

# Secrets
aws secretsmanager describe-secret \
    --secret-id drc_secrets

# Lambda function
aws lambda get-function --function-name cv-builder-dev
```

---

## Cleanup

```bash
# Delete stack (removes Lambda, IAM role, CloudWatch logs)
aws cloudformation delete-stack --stack-name cv-builder-dev

# Wait for completion
aws cloudformation wait stack-delete-complete \
    --stack-name cv-builder-dev

# Delete ECR image
aws ecr delete-repository \
    --repository-name cv-builder \
    --force

# Delete secret
aws secretsmanager delete-secret \
    --secret-id drc_secrets \
    --force-delete-without-recovery
```

---

## File Structure

```
ai_cv_builder/
├── backend/
│   ├── Dockerfile              # Docker image for local/ECS
│   ├── Dockerfile.lambda       # Docker image for Lambda (uses public.ecr.aws/lambda/python)
│   ├── requirements.txt        # Python dependencies
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py          # ⭐ Handles Secrets Manager + environment detection
│   │   ├── lambda_handler.py  # ⭐ Mangum adapter for Lambda
│   │   └── ...
│   └── test_unified_graph.py
├── infra/
│   └── sam-template.yaml      # ⭐ CloudFormation/SAM template for Lambda
├── scripts/
│   ├── deploy-lambda.ps1      # ⭐ Windows deployment script
│   ├── deploy-lambda.sh       # ⭐ Linux/macOS deployment script
│   ├── setup-local.ps1        # LocalStack setup (Secrets Manager support)
│   └── ...
├── docs/
│   └── LAMBDA_DEPLOYMENT_GUIDE.md  # ⭐ Full deployment guide
├── docker-compose.yml         # Updated with Secrets Manager
├── README.md                  # Updated with Lambda section
└── ...
```

---

## Secrets Caching Behavior

### Cold Start (First Invocation)
```
1. Lambda container starts
2. Application loads config.py
3. _secrets_cache is empty
4. Application fetches from Secrets Manager (~100-200ms)
5. Stores in _secrets_cache (global variable)
6. Request processed
```

### Warm Start (Subsequent Invocation)
```
1. Lambda container reused
2. Application loads config.py
3. _secrets_cache already populated
4. Application uses cached secrets (~1-2ms)
5. No Secrets Manager call needed!
6. Request processed
```

### Cost Benefit
- **Cold Start Overhead**: ~100-200ms (once per container lifecycle)
- **Warm Start Savings**: ~99ms per request (no Secrets Manager call)
- **Monthly Savings**: ~5-10 fewer API calls to Secrets Manager

---

## Common Environment Setups

### Development (LocalStack)
```bash
cd scripts
.\setup-local.ps1 -HFApiToken "your_token" -GeminiApiKey "your_key"

# Start containers
docker compose up -d

# Run backend (inside container or locally)
uvicorn app.main:app --reload
```

### Staging (AWS Lambda)
```bash
.\scripts\deploy-lambda.ps1 -Environment staging -AwsRegion us-east-1
```

### Production (AWS Lambda)
```bash
# Ensure production secrets are configured
aws secretsmanager update-secret \
    --secret-id drc_secrets \
    --secret-string '{...PROD_KEYS...}'

# Deploy
.\scripts\deploy-lambda.ps1 -Environment prod -AwsRegion us-east-1
```

---

## Monitoring Queries

```bash
# Total invocations today
aws cloudwatch get-metric-statistics \
    --namespace AWS/Lambda \
    --metric-name Invocations \
    --dimensions Name=FunctionName,Value=cv-builder-dev \
    --start-time $(date -u -d '1 day ago' +%Y-%m-%dT%H:%M:%S) \
    --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
    --period 86400 \
    --statistics Sum

# Average Lambda duration
aws cloudwatch get-metric-statistics \
    --namespace AWS/Lambda \
    --metric-name Duration \
    --dimensions Name=FunctionName,Value=cv-builder-dev \
    --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
    --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
    --period 3600 \
    --statistics Average Maximum

# Errors in last 24 hours
aws cloudwatch get-metric-statistics \
    --namespace AWS/Lambda \
    --metric-name Errors \
    --dimensions Name=FunctionName,Value=cv-builder-dev \
    --start-time $(date -u -d '1 day ago' +%Y-%m-%dT%H:%M:%S) \
    --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
    --period 3600 \
    --statistics Sum
```

---

## Support & Documentation

- Full guide: `docs/LAMBDA_DEPLOYMENT_GUIDE.md`
- Main README: `README.md` (Lambda section)
- Config details: `backend/app/config.py`
- Handler setup: `backend/app/lambda_handler.py`
- SAM template: `infra/sam-template.yaml`
