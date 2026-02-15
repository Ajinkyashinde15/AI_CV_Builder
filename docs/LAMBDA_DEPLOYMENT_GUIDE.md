# AWS Lambda Deployment Guide

Complete guide for deploying the AI CV Builder application to AWS Lambda with automatic secret management and environment-aware configuration.

## Table of Contents
1. [Quick Start](#quick-start)
2. [Pre-Deployment Checklist](#pre-deployment-checklist)
3. [Architecture Overview](#architecture-overview)
4. [Manual Deployment Steps](#manual-deployment-steps)
5. [Automated Deployment](#automated-deployment)
6. [Secrets Management](#secrets-management)
7. [Environment Configuration](#environment-configuration)
8. [Monitoring and Logging](#monitoring-and-logging)
9. [Cost Estimation](#cost-estimation)
10. [Troubleshooting](#troubleshooting)

---

## Quick Start

### 1. One-Command Deployment (Linux/macOS)
```bash
./scripts/deploy-lambda.sh dev
```

### 2. One-Command Deployment (Windows PowerShell)
```powershell
.\scripts\deploy-lambda.ps1 -Environment dev
```

The scripts handle:
- AWS credential verification
- ECR repository creation
- Docker image building and pushing
- Secrets Manager configuration
- SAM template deployment
- CloudFormation stack creation

---

## Pre-Deployment Checklist

### AWS Account Setup
- [ ] AWS Account with billing enabled
- [ ] IAM user with appropriate permissions
- [ ] AWS CLI v2 installed and configured
- [ ] AWS credentials in `~/.aws/credentials` or environment variables

### Local Development Tools
- [ ] Docker installed and running
- [ ] AWS SAM CLI installed
- [ ] Git installed
- [ ] Python 3.11+ (for local development)

### Required Permissions (IAM Policy)
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ecr:*",
        "lambda:*",
        "apigateway:*",
        "dynamodb:*",
        "s3:*",
        "secretsmanager:*",
        "cloudformation:*",
        "iam:*",
        "logs:*",
        "cloudwatch:*"
      ],
      "Resource": "*"
    }
  ]
}
```

---

## Architecture Overview

### Deployment Topology

```
┌─────────────────────────────────────────────────────────────┐
│                     AWS Account                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐   ┌─────────────────┐  ┌──────────────┐ │
│  │ API Gateway  │───│    Lambda       │──│  Secrets     │ │
│  │              │   │ (FastAPI App)   │  │  Manager     │ │
│  └──────────────┘   └─────────────────┘  └──────────────┘ │
│                            │                                │
│                     ┌──────┴──────┬──────────────┐          │
│                     │             │              │          │
│              ┌──────▼──┐   ┌──────▼──┐   ┌──────▼──┐       │
│              │    S3   │   │ DynamoDB│   │CloudWatch     │  │
│              │ (CVs)   │   │ (Traces)│   │ (Logs)   │  │
│              └─────────┘   └─────────┘   └──────────┘       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Environment Detection Flow

```
Application Startup
        │
        ├─ Read ENV variable
        │
        └─ ENV=="dev" ? ─────────────────┐
           │                              │
         "local"                        "dev"
           │                              │
    ┌──────▼──────┐              ┌───────▼─────────┐
    │  LocalStack  │              │   AWS Services  │
    │  Endpoints   │              │   (Real AWS)    │
    │http://4566  │              │                 │
    │  localhost  │              │ CloudFormation  │
    ├──────┬──────┤              └────────┬────────┘
    │      │      │                       │
    │ SM DS3 DDB  │               SM S3 DDB
    │ Local Test │               Prod Running
    └──────┴──────┘               
```

---

## Manual Deployment Steps

### Step 1: Create AWS Infrastructure

#### a) Create ECR Repository
```bash
AWS_REGION=us-east-1
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

aws ecr create-repository \
    --repository-name cv-builder \
    --region $AWS_REGION \
    --image-scanning-configuration scanOnPush=true
```

#### b) Create S3 Bucket
```bash
aws s3api create-bucket \
    --bucket ai-resume-cv-bucket \
    --region $AWS_REGION
    
# Block public access
aws s3api put-public-access-block \
    --bucket ai-resume-cv-bucket \
    --public-access-block-configuration \
    "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
```

#### c) Create DynamoDB Table
```bash
aws dynamodb create-table \
    --table-name CvBuilderDb \
    --attribute-definitions \
        AttributeName=pk,AttributeType=S \
        AttributeName=sk,AttributeType=S \
    --key-schema \
        AttributeName=pk,KeyType=HASH \
        AttributeName=sk,KeyType=RANGE \
    --billing-mode PAY_PER_REQUEST \
    --region $AWS_REGION
```

#### d) Create Secrets Manager Secret
```bash
aws secretsmanager create-secret \
    --name CvBuilderSecretsManager \
    --description "API keys for CV Builder" \
    --secret-string '{
        "HF_API_TOKEN": "hf_xxxxxxxxxxxxxxxxxxx",
        "GEMINI_API_KEY": "AIzaSyxxxxxxxxxxxxxxxxxx"
    }' \
    --region $AWS_REGION
```

### Step 2: Build and Push Docker Image

#### a) Authenticate Docker
```bash
aws ecr get-login-password --region $AWS_REGION | \
    docker login --username AWS --password-stdin \
    $ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com
```

#### b) Build Image
```bash
docker build \
    -f backend/Dockerfile.lambda \
    -t $ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/cv-builder:latest \
    .
```

#### c) Push to ECR
```bash
docker push $ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/cv-builder:latest
```

### Step 3: Deploy with SAM

```bash
IMAGE_URI=$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/cv-builder:latest

sam deploy \
    --template-file infra/sam-template.yaml \
    --stack-name cv-builder-dev \
    --parameter-overrides \
        Environment=dev \
        S3BucketName=ai-resume-cv-bucket \
        ECRImageUri=$IMAGE_URI \
        HFApiToken="hf_xxxxxxxxxxxxxxxxxxx" \
        GeminiApiKey="AIzaSyxxxxxxxxxxxxxxxxxx" \
    --region $AWS_REGION \
    --capabilities CAPABILITY_IAM \
    --no-fail-on-empty-changeset
```

### Step 4: Verify Deployment

```bash
# Get API endpoint
aws cloudformation describe-stacks \
    --stack-name cv-builder-dev \
    --region $AWS_REGION \
    --query 'Stacks[0].Outputs' \
    --output table

# Test health endpoint
API_ENDPOINT=$(aws cloudformation describe-stacks \
    --stack-name cv-builder-dev \
    --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' \
    --output text \
    --region $AWS_REGION)

curl $API_ENDPOINT/health
```

---

## Automated Deployment

### Linux/macOS

```bash
cd scripts
chmod +x deploy-lambda.sh
./deploy-lambda.sh dev
```

**Parameters:**
```bash
./deploy-lambda.sh [environment] [region]
# Example:
./deploy-lambda.sh dev us-east-1
./deploy-lambda.sh staging eu-west-1
```

### Windows (PowerShell)

```powershell
cd .\scripts
.\deploy-lambda.ps1 -Environment dev -AwsRegion us-east-1
```

**Parameters:**
- `-Environment`: `dev`, `staging`, or `prod` (default: dev)
- `-AwsRegion`: AWS region (default: us-east-1)

**Script Flow:**
1. Verifies AWS credentials
2. Creates/gets ECR repository
3. Authenticates Docker
4. Builds Docker image
5. Pushes to ECR
6. Verifies S3 bucket
7. Creates/updates Secrets Manager secret
8. Runs SAM deployment

---

## Secrets Management

### Secrets Architecture

```
┌──────────────────────────────────────────┐
│     Lambda Execution                      │
├──────────────────────────────────────────┤
│                                           │
│  Application Startup                      │
│         │                                 │
│         ├─ Is _secrets_cache empty?       │
│         │                                 │
│    YES  │    NO                           │
│         ▼     ▼                           │
│    🔄Fetch   ✓Return                      │
│   Secrets   Cached                        │
│   Manager    Secrets                      │
│         │                                 │
│         └─ Store in _secrets_cache        │
│              (Global Memory)              │
│                                           │
│  Subsequent Invocations (Warm Start)      │
│         │                                 │
│         ├─ _secrets_cache exists? ─YES─▶ ✓Use Cache
│         │                                 │No Secrets Manager Call!
│         └─ Use immediately                │
│              (~1-2ms vs ~100-200ms)       │
│                                           │
└──────────────────────────────────────────┘
```

### Updating Secrets

```bash
# Update secret value
aws secretsmanager update-secret \
    --secret-id CvBuilderSecretsManager \
    --secret-string '{
        "HF_API_TOKEN": "new_token_here",
        "GEMINI_API_KEY": "new_key_here"
    }' \
    --region us-east-1

# Views current secret
aws secretsmanager get-secret-value \
    --secret-id CvBuilderSecretsManager \
    --region us-east-1 \
    --query SecretString \
    --output text | jq '.'
```

### Secrets Rotation (Future Enhancement)

```bash
# Automatic rotation can be configured
aws secretsmanager rotate-secret \
    --secret-id CvBuilderSecretsManager \
    --rotation-rules AutomaticallyAfterDays=30
```

---

## Environment Configuration

### Environment Variables by Deployment Type

#### Local Development (LocalStack)
```env
ENV=local
AWS_ENDPOINT_URL=http://localhost:4566
S3_BUCKET=ai-resume-cv-bucket
LLM_PROVIDER=hf_endpoint
```

#### AWS Lambda (Dev)
```env
ENV=dev
AWS_REGION=us-east-1
S3_BUCKET=ai-resume-cv-bucket
SECRETS_MANAGER_NAME=CvBuilderSecretsManager
LLM_PROVIDER=hf_endpoint
```

#### AWS Lambda (Production)
```env
ENV=dev
AWS_REGION=us-east-1
S3_BUCKET=ai-resume-cv-bucket-prod
SECRETS_MANAGER_NAME=CvBuilderSecretsManager
LLM_PROVIDER=gemini  # or hf_endpoint
TRACE_TABLE=CvBuilderDb-prod
```

### Configuration Files

**config.py** reads from:
1. Lambda environment variables (highest priority)
2. Secrets Manager (for API keys)
3. LocalStack (if ENV=local)
4. Default values (lowest priority)

---

## Monitoring and Logging

### CloudWatch Logs

```bash
# View Lambda logs (real-time)
aws logs tail /aws/lambda/cv-builder-dev --follow

# View logs from last hour
aws logs tail /aws/lambda/cv-builder-dev --since 1h

# Search for errors
aws logs filter-log-events \
    --log-group-name /aws/lambda/cv-builder-dev \
    --filter-pattern "ERROR"
```

### CloudWatch Metrics

```bash
# Lambda invocations
aws cloudwatch get-metric-statistics \
    --namespace AWS/Lambda \
    --metric-name Invocations \
    --dimensions Name=FunctionName,Value=cv-builder-dev \
    --start-time 2024-02-14T00:00:00Z \
    --end-time 2024-02-15T00:00:00Z \
    --period 3600 \
    --statistics Sum

# Lambda errors
aws cloudwatch get-metric-statistics \
    --namespace AWS/Lambda \
    --metric-name Errors \
    --dimensions Name=FunctionName,Value=cv-builder-dev \
    --start-time 2024-02-14T00:00:00Z \
    --end-time 2024-02-15T00:00:00Z \
    --period 3600 \
    --statistics Sum

# Lambda duration
aws cloudwatch get-metric-statistics \
    --namespace AWS/Lambda \
    --metric-name Duration \
    --dimensions Name=FunctionName,Value=cv-builder-dev \
    --start-time 2024-02-14T00:00:00Z \
    --end-time 2024-02-15T00:00:00Z \
    --period 3600 \
    --statistics Average,Maximum
```

### CloudWatch Alarms (Auto-created)

- `cv-builder-lambda-errors-dev`: Triggers on > 5 errors in 5 minutes
- `cv-builder-lambda-duration-dev`: Triggers on avg duration > 250 seconds
- `cv-builder-dynamodb-throttle-dev`: Triggers on DynamoDB throttling

---

## Cost Estimation

### Monthly Costs (Typical Dev Environment)

| Service | Usage | Cost |
|---------|-------|------|
| Lambda | 10K invocations, 512MB, 30s avg | $0.35 |
| S3 | 50 CVs + 50 resumes (5GB) | $0.12 |
| DynamoDB | 10K writes, 30K reads | $1.50 |
| Secrets Manager | 1 secret | $0.40 |
| CloudWatch | Logs (~100MB/month) | $0.05 |
| API Gateway | 10K requests | $0.35 |
| **Total** | | **~$2.77** |

### Cost Optimization Tips

1. **Reduce Lambda Memory**: Lower memory reduces cost (adjust SAM parameter)
2. **DynamoDB Batch:**: Process multiple CVs in parallel
3. **S3 Lifecycle**: Archive old resumes to Glacier
4. **Lambda Concurrency**: Set reserved concurrency limit
5. **VPC Endpoint**: Use for private S3 access (no NAT gateway charges)

### Comparison with ECS Fargate

| Metric | Lambda | ECS Fargate |
|--------|--------|----------|
| Monthly Cost (Dev) | $2-5 | $30-50 |
| Cold Start | 2-5 seconds | ~30 seconds |
| Scaling | Automatic | Manual (tasks) |
| Best For | Bursty workloads | Always-on services |

---

## Troubleshooting

### Common Issues

#### 1. "Lambda execution role does not have permissions"
**Error:** `AccessDenied` when accessing S3/DynamoDB/Secrets Manager

**Solution:**
```bash
# Check role policies
aws iam list-attached-role-policies \
    --role-name cv-builder-LambdaExecutionRole

# Attach missing policy
aws iam attach-role-policy \
    --role-name cv-builder-LambdaExecutionRole \
    --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess
```

#### 2. "ImageNotFound" during deployment
**Error:** ECR image URI not found

**Solution:**
```bash
# Verify image exists in ECR
aws ecr describe-images --repository-name cv-builder

# Re-push image
docker push $IMAGE_URI
```

#### 3. "Secrets Manager secret not found"
**Error:** `ResourceNotFoundException` for CvBuilderSecretsManager

**Solution:**
```bash
# Verify secret exists
aws secretsmanager describe-secret \
    --secret-id CvBuilderSecretsManager

# Create if missing
aws secretsmanager create-secret \
    --name CvBuilderSecretsManager \
    --secret-string '{...}'
```

#### 4. "DynamoDB throttling"
**Error:** Too many requests to DynamoDB

**Solution:**
```bash
# Check table status
aws dynamodb describe-table --table-name CvBuilderDb

# Increase capacity (if using provisioned billing)
aws dynamodb update-table \
    --table-name CvBuilderDb \
    --provisioned-throughput ReadCapacityUnits=100,WriteCapacityUnits=100
```

#### 5. "Lambda timeout"
**Error:** Task took longer than 300 seconds

**Solution:**
```bash
# Increase timeout in SAM template or console
aws lambda update-function-configuration \
    --function-name cv-builder-dev \
    --timeout 600

# Or re-deploy with increased timeout:
sam deploy --parameter-overrides LambdaTimeout=600
```

#### 6. "Out of memory"
**Error:** `OutOfMemory` Lambda exception

**Solution:**
```bash
# Increase memory allocation
aws lambda update-function-configuration \
    --function-name cv-builder-dev \
    --memory-size 1024

# Or re-deploy with increased memory:
sam deploy --parameter-overrides LambdaMemory=1024
```

### Debug Checklist

- [ ] Lambda cold start vs warm start (check logs)
- [ ] Secrets Manager configuration (verify API keys)
- [ ] S3 bucket permissions (check IAM policy)
- [ ] DynamoDB table exists and is ACTIVE
- [ ] ECR image is correct and up-to-date
- [ ] API Gateway endpoint is publicly accessible
- [ ] CloudWatch logs show detailed error messages

---

## Next Steps

1. **Test the Deployment**
   ```bash
   API_ENDPOINT=$(aws cloudformation describe-stacks \
       --stack-name cv-builder-dev \
       --query 'Stacks[0].Outputs[?OutputKey==`ApiEndpoint`].OutputValue' \
       --output text)
   
   curl $API_ENDPOINT/resume/list-cvs
   ```

2. **Upload Sample CVs**
   ```bash
   aws s3 cp sample_cv_1.docx s3://ai-resume-cv-bucket/rawcvs/
   ```

3. **Test Generation**
   ```bash
   curl -X POST $API_ENDPOINT/resume/generate \
       -H 'Content-Type: application/json' \
       -d '{"job_description": "..."}'
   ```

4. **Monitor in CloudWatch**
   ```bash
   aws logs tail /aws/lambda/cv-builder-dev --follow
   ```

5. **Setup Continuous Deployment (CI/CD)**
   - GitHub Actions or similar
   - Auto-rebuild image on code changes
   - Auto-deploy new image version

---

## References

- [AWS Lambda Documentation](https://docs.aws.amazon.com/lambda/)
- [AWS SAM Developer Guide](https://docs.aws.amazon.com/serverless-application-model/)
- [Mangum Documentation](https://mangum.io/)
- [FastAPI Deployment](https://fastapi.tiangolo.com/deployment/)
- [AWS Secrets Manager](https://docs.aws.amazon.com/secretsmanager/)
