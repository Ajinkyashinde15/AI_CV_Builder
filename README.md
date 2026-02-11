
# AI CV Builder (LangGraph + Gemini/HuggingFace)

A production-ready, cost-effective resume tailoring system. It ingests CVs from **AWS S3**, takes a **Job Description (JD)**, and generates tailored resumes. The pipeline is orchestrated with **LangGraph**, runs **Gemini** or **Hugging Face** LLMs, exposes a **FastAPI** backend, a **Streamlit** UI, and ships with **Docker** and **AWS CloudFormation** for deployment.

> ✅ Design choice: *Option A (LangGraph + Gemini/HuggingFace only)* — no external OCR or third‑party text extraction services. DOCX/PDF CVs are read locally; the LLM focuses on generation. Output can be **DOCX** (default) or **PDF**.

---

## Table of Contents
- [Architecture](#architecture)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [AWS S3 Layout](#aws-s3-layout)
- [Model Backends (Gemini / Hugging Face)](#model-backends-gemini--hugging-face)
- [Environment Variables](#environment-variables)
- [Local Development](#local-development)
- [Docker (Backend + UI) & Compose](#docker-backend--ui--compose)
- [CloudFormation Deployment (ECR/ECS/ALB)](#cloudformation-deployment-ecrecsalb)
- [FastAPI Endpoints](#fastapi-endpoints)
- [Streamlit App](#streamlit-app)
- [LangGraph Pipeline](#langgraph-pipeline)
- [Security, Logging, and Cost Controls](#security-logging-and-cost-controls)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Roadmap](#roadmap)
- [License](#license)

---

## Architecture

```mermaid
flowchart LR
    A[Streamlit UI] -- POST /generate --> B(FastAPI Backend)
    B -->|List Keys| S3[(S3 Bucket)]
    B -->|for each CV| G[LangGraph Pipeline]
    G --> E1[Extract (local)]
    E1 --> E2[Generate (LLM)]
    E2 --> E3[Write DOCX]
    E3 -->|optional| E4[Convert to PDF]
    E4 --> E5[Upload S3]
    E3 --> E5
    E5 --> S3
    B -->|Response| A
```

**High-level flow**
1. UI accepts a Job Description (JD) and triggers generation.
2. Backend lists CVs under a configured S3 prefix and runs the **LangGraph** pipeline per CV.
3. Pipeline reads each CV (DOCX/PDF) locally, generates tailored resume text with **Gemini or a Hugging Face model**, writes a **DOCX**, optionally converts to **PDF**, and uploads to the output prefix.
4. UI displays the processed files and S3 keys.

---

## Features
- **LangGraph**: deterministic, debuggable pipeline (extract → generate → write → upload).
- **Models**: Plug-and-play **Gemini** (e.g., `gemini-1.5-flash` for cost-efficiency) or **Hugging Face** (e.g., `mistral-7b-instruct`, `Llama-3` via Inference API or endpoints).
- **S3-native**: Input and output folders; supports batch processing.
- **Output formats**: DOCX (default). Optional PDF via **LibreOffice headless** in Docker.
- **Production-ready**: FastAPI with pydantic schemas, robust logging, retries, health endpoints, Docker images, and CloudFormation for ECS Fargate + ALB.
- **Security**: Minimal IAM, private environment variables, no resume content in logs.

---

## Tech Stack
- **Backend**: FastAPI, Uvicorn/Gunicorn, LangGraph
- **UI**: Streamlit
- **LLMs**: Gemini (Google Generative AI) **or** Hugging Face (Inference API / Inference Endpoints)
- **Storage**: AWS S3
- **Container/Deploy**: Docker, AWS CloudFormation (ECR/ECS/ALB/CloudWatch)

---

## AWS S3 Layout
- **Bucket**: `S3_BUCKET`
- **Input prefix**: `S3_CV_PREFIX` (e.g., `input/cv/`)
- **Output prefix**: `S3_RESUME_PREFIX` (e.g., `output/resume/`)

Recommended structure:
```
s3://<your-bucket>/
  input/
    cv/
      john_doe.docx
      jane_smith.pdf
  output/
    resume/
      john_doe_resume.docx
      john_doe_resume.pdf   # if PDF enabled
```

---

## Model Backends (Gemini / Hugging Face)
Choose **one** at runtime using `LLM_PROVIDER`:

- `LLM_PROVIDER=gemini`
  - `GEMINI_API_KEY` – API key
  - `GEMINI_MODEL=gemini-1.5-flash` (default: cost-effective) or `gemini-1.5-pro`

- `LLM_PROVIDER=huggingface`
  - `HF_API_TOKEN` – token for Inference API
  - `HF_MODEL_ID=mistralai/Mistral-7B-Instruct-v0.3` (example) or any chat-instruct model

> Tip: Keep prompts short and structured; truncate CV and JD to safe limits (the pipeline already does this) to avoid context overruns.

---

## Environment Variables
Create a `.env` (or use SSM/Secrets Manager in prod):

```env
# --- AWS ---
AWS_REGION=ap-south-1
S3_BUCKET=your-cv-bucket
S3_CV_PREFIX=input/cv/
S3_RESUME_PREFIX=output/resume/

# --- LLM Provider (choose one) ---
LLM_PROVIDER=gemini            # or: huggingface
GEMINI_API_KEY=
GEMINI_MODEL=gemini-1.5-flash
HF_API_TOKEN=
HF_MODEL_ID=mistralai/Mistral-7B-Instruct-v0.3

# --- App ---
APP_LOG_LEVEL=INFO
MAX_CV_CHARS=12000
MAX_JD_CHARS=8000
OUTPUT_FORMAT=docx             # or: pdf
ENABLE_PDF_CONVERSION=false    # set true to enable LibreOffice conversion

# --- Server ---
API_HOST=0.0.0.0
API_PORT=8080
UI_PORT=8501
WORKERS=2
TIMEOUT=120
```

**Minimal IAM policy** for the task role (replace bucket name):
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket"
      ],
      "Resource": "arn:aws:s3:::your-cv-bucket"
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject"
      ],
      "Resource": "arn:aws:s3:::your-cv-bucket/*"
    }
  ]
}
```

---

## Local Development

### 1) Python environment
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # then edit values
```

### 2) Run backend
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080 --workers 2 --timeout-keep-alive 120
# Or with Gunicorn:
# gunicorn -k uvicorn.workers.UvicornWorker app.main:app -w 2 -b 0.0.0.0:8080 --timeout 120
```

### 3) Run Streamlit UI
```bash
streamlit run ui/Home.py --server.address 0.0.0.0 --server.port 8501
```

---

## Docker (Backend + UI) & Compose

### `docker/backend.Dockerfile`
```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.11-slim as base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    libreoffice \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Non-root
RUN useradd -ms /bin/bash appuser
USER appuser

EXPOSE 8080
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "app.main:app", "-w", "2", "-b", "0.0.0.0:8080", "--timeout", "120"]
```

### `docker/ui.Dockerfile`
```dockerfile
FROM python:3.11-slim
WORKDIR /ui
COPY ui/requirements-ui.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY ui ./
EXPOSE 8501
CMD ["streamlit", "run", "Home.py", "--server.address=0.0.0.0", "--server.port=8501"]
```

### `docker-compose.yml`
```yaml
version: "3.9"
services:
  backend:
    build:
      context: .
      dockerfile: docker/backend.Dockerfile
    env_file: .env
    ports:
      - "8080:8080"
    restart: unless-stopped

  ui:
    build:
      context: .
      dockerfile: docker/ui.Dockerfile
    environment:
      API_BASE_URL: http://backend:8080
    ports:
      - "8501:8501"
    depends_on:
      - backend
    restart: unless-stopped
```

---

## CloudFormation Deployment (ECR/ECS/ALB)
A minimal stack that provisions:
- ECR repos for backend & ui images
- ECS Fargate cluster, task definitions, and services
- Application Load Balancer (HTTP 80 → backend, optional → UI)
- SSM Parameters for sensitive values (or use Secrets Manager)
- CloudWatch log groups

> Build and push images to ECR, then pass image URIs as parameters.

`infra/cloudformation/stack.yaml` (trimmed for brevity):
```yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: AI CV Builder - ECS Fargate with ALB
Parameters:
  VpcId:
    Type: AWS::EC2::VPC::Id
  Subnets:
    Type: List<AWS::EC2::Subnet::Id>
  BackendImageUri:
    Type: String
  UiImageUri:
    Type: String
  S3BucketName:
    Type: String
  S3CvPrefix:
    Type: String
    Default: input/cv/
  S3ResumePrefix:
    Type: String
    Default: output/resume/
  LlmProvider:
    Type: String
    Default: gemini
  GeminiApiKeyParam:
    Type: String
    Default: /aicv/gemini_api_key
  HfApiTokenParam:
    Type: String
    Default: /aicv/hf_api_token
Resources:
  LogGroupBackend:
    Type: AWS::Logs::LogGroup
    Properties: {LogGroupName: "/ecs/aicv-backend", RetentionInDays: 14}

  LogGroupUi:
    Type: AWS::Logs::LogGroup
    Properties: {LogGroupName: "/ecs/aicv-ui", RetentionInDays: 14}

  Cluster:
    Type: AWS::ECS::Cluster
    Properties: {ClusterName: aicv-cluster}

  TaskRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal: {Service: ecs-tasks.amazonaws.com}
            Action: sts:AssumeRole
      Policies:
        - PolicyName: s3-access
          PolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Action: [s3:ListBucket]
                Resource: !Sub arn:aws:s3:::${S3BucketName}
              - Effect: Allow
                Action: [s3:GetObject, s3:PutObject]
                Resource: !Sub arn:aws:s3:::${S3BucketName}/*
        - PolicyName: ssm-access
          PolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Effect: Allow
                Action: [ssm:GetParameter]
                Resource: "*"

  ExecutionRole:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal: {Service: ecs-tasks.amazonaws.com}
            Action: sts:AssumeRole
      ManagedPolicyArns:
        - arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy

  BackendTask:
    Type: AWS::ECS::TaskDefinition
    Properties:
      RequiresCompatibilities: [FARGATE]
      Cpu: '512'
      Memory: '1024'
      NetworkMode: awsvpc
      TaskRoleArn: !GetAtt TaskRole.Arn
      ExecutionRoleArn: !GetAtt ExecutionRole.Arn
      ContainerDefinitions:
        - Name: backend
          Image: !Ref BackendImageUri
          PortMappings: [{ContainerPort: 8080}]
          LogConfiguration:
            LogDriver: awslogs
            Options:
              awslogs-group: !Ref LogGroupBackend
              awslogs-region: !Ref AWS::Region
              awslogs-stream-prefix: ecs
          Environment:
            - {Name: AWS_REGION, Value: !Ref AWS::Region}
            - {Name: S3_BUCKET, Value: !Ref S3BucketName}
            - {Name: S3_CV_PREFIX, Value: !Ref S3CvPrefix}
            - {Name: S3_RESUME_PREFIX, Value: !Ref S3ResumePrefix}
            - {Name: LLM_PROVIDER, Value: !Ref LlmProvider}
          Secrets:
            - Name: GEMINI_API_KEY
              ValueFrom: !Ref GeminiApiKeyParam
            - Name: HF_API_TOKEN
              ValueFrom: !Ref HfApiTokenParam

  UiTask:
    Type: AWS::ECS::TaskDefinition
    Properties:
      RequiresCompatibilities: [FARGATE]
      Cpu: '256'
      Memory: '512'
      NetworkMode: awsvpc
      ExecutionRoleArn: !GetAtt ExecutionRole.Arn
      ContainerDefinitions:
        - Name: ui
          Image: !Ref UiImageUri
          PortMappings: [{ContainerPort: 8501}]
          LogConfiguration:
            LogDriver: awslogs
            Options:
              awslogs-group: !Ref LogGroupUi
              awslogs-region: !Ref AWS::Region
              awslogs-stream-prefix: ecs
          Environment:
            - {Name: API_BASE_URL, Value: "http://backend.local"}

  VpcSG:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: aicv-sg
      VpcId: !Ref VpcId
      SecurityGroupIngress:
        - IpProtocol: tcp
          FromPort: 80
          ToPort: 80
          CidrIp: 0.0.0.0/0

  ALB:
    Type: AWS::ElasticLoadBalancingV2::LoadBalancer
    Properties:
      Subnets: !Ref Subnets
      SecurityGroups: [!Ref VpcSG]

  TGBackend:
    Type: AWS::ElasticLoadBalancingV2::TargetGroup
    Properties:
      VpcId: !Ref VpcId
      Protocol: HTTP
      Port: 80
      TargetType: ip
      HealthCheckPath: /health

  Listener:
    Type: AWS::ElasticLoadBalancingV2::Listener
    Properties:
      LoadBalancerArn: !Ref ALB
      Port: 80
      Protocol: HTTP
      DefaultActions:
        - Type: forward
          TargetGroupArn: !Ref TGBackend

  BackendService:
    Type: AWS::ECS::Service
    DependsOn: Listener
    Properties:
      Cluster: !Ref Cluster
      LaunchType: FARGATE
      DesiredCount: 1
      NetworkConfiguration:
        AwsvpcConfiguration:
          AssignPublicIp: ENABLED
          Subnets: !Ref Subnets
          SecurityGroups: [!Ref VpcSG]
      TaskDefinition: !Ref BackendTask
      LoadBalancers:
        - ContainerName: backend
          ContainerPort: 8080
          TargetGroupArn: !Ref TGBackend
Outputs:
  AlbDNS:
    Value: !GetAtt ALB.DNSName
```

**Deploy**
```bash
aws cloudformation deploy \
  --template-file infra/cloudformation/stack.yaml \
  --stack-name aicv-prod \
  --capabilities CAPABILITY_NAMED_IAM \
  --parameter-overrides \
      VpcId=vpc-xxxx \
      Subnets=subnet-aaa,subnet-bbb \
      BackendImageUri=<acct>.dkr.ecr.<region>.amazonaws.com/aicv-backend:latest \
      UiImageUri=<acct>.dkr.ecr.<region>.amazonaws.com/aicv-ui:latest \
      S3BucketName=your-cv-bucket
```

---

## FastAPI Endpoints

### `GET /list-cvs`
Lists available CV object keys under `S3_CV_PREFIX`.

**Response**
```json
{
  "bucket": "your-cv-bucket",
  "prefix": "input/cv/",
  "keys": ["input/cv/john_doe.docx", "input/cv/jane_smith.pdf"]
}
```

### `POST /generate`
Triggers the unified pipeline across all CVs.

**Request**
```json
{
  "job_description": "We are seeking a Python backend developer..."
}
```

**Response**
```json
{
  "processed_keys": ["input/cv/john_doe.docx"],
  "output_keys": ["output/resume/john_doe_resume.docx"]
}
```

> The backend logs include a visual representation of the graph and a per-file status. No PII or resume content is logged; only character counts and keys.

---

## Streamlit App
- Text area to paste the **Job Description**
- **Generate Resume** button calls `POST /generate`
- Shows progress and S3 output keys
- (Optional) A list of input CVs from `GET /list-cvs`

**Environment**: set `API_BASE_URL` to the FastAPI service URL.

---

## LangGraph Pipeline
Your code defines a typed `State` and four nodes invoked in sequence:

1. **extract**
   - Downloads a CV from S3 to `/tmp` and extracts text.
   - For `.docx`: `llm_extract_text_from_docx(local_in)` (you can swap for `python-docx` if you prefer strict non-LLM extraction).
   - For `.pdf`: implement a similar local extractor (e.g., `pypdf`).
   - Truncates content to avoid model context limits.

2. **generate**
   - Validates `cv_text` and `job_description`.
   - Builds a concise prompt (`resume_prompt(cv_text, jd_text)`).
   - Invokes the selected model via `get_model()`.
   - Stores `resume_text` in state.

3. **write**
   - Writes `resume_text` to a local DOCX via `write_resume_docx()`.

4. **upload**
   - Uploads generated DOCX (and optionally PDF) to S3 under `S3_RESUME_PREFIX`.

### Optional: DOCX → PDF conversion
If `ENABLE_PDF_CONVERSION=true` or `OUTPUT_FORMAT=pdf`, add a conversion step using **LibreOffice headless**:

```python
import subprocess, shlex, os

def docx_to_pdf(docx_path: str) -> str:
    out_dir = os.path.dirname(docx_path)
    cmd = f"libreoffice --headless --convert-to pdf --outdir {shlex.quote(out_dir)} {shlex.quote(docx_path)}"
    subprocess.check_call(cmd, shell=True)
    return os.path.splitext(docx_path)[0] + ".pdf"
```
Upload the resulting PDF with `content_type="application/pdf"`.

---

## Security, Logging, and Cost Controls
- **IAM least privilege**: only allow `s3:ListBucket`, `s3:GetObject`, `s3:PutObject` on your bucket.
- **Secrets**: use **AWS SSM Parameter Store** or **Secrets Manager** for API keys.
- **PII safety**: never log raw CV or resume content; log counts and keys only.
- **Retries/Backoff**: wrap S3 and model calls with exponential backoff for transient errors.
- **Timeouts**: set worker timeouts and model timeouts to fail fast (`TIMEOUT=120`).
- **Costs**: prefer `gemini-1.5-flash` or small HF models for dev; batch calls, and truncate inputs (`MAX_CV_CHARS`, `MAX_JD_CHARS`).
- **Observability**: ship logs to CloudWatch; optionally add metrics and tracing later (e.g., OpenTelemetry).

---

## Testing
- **Unit tests** for: prompt builder, truncation, S3 helper functions, DOCX writer
- **Integration tests**: spin localstack or test S3 bucket; mock LLMs with fixed responses
- **Load tests**: small batch of CVs to validate timeouts and concurrency

Example test matrix:
- DOCX → resume DOCX
- PDF → resume DOCX
- JD empty → 400/validation error
- Missing S3 object → graceful skip with warning

---

## Troubleshooting
- **`AccessDenied` on S3**: verify task role policy and bucket name.
- **Large PDFs**: ensure truncation; consider pre-filtering sections before LLM.
- **`libreoffice` not found**: install in Docker image or disable PDF conversion.
- **Model 4xx/5xx**: rotate API key, reduce prompt size, add retries.

---

## Roadmap
- Optional RAG from CV sections (skills/experience) without external vector DB
- Caching to avoid reprocessing unchanged CVs (ETag-based)
- Parallelism (async/batch) for faster throughput
- Per-candidate configuration (e.g., role preferences)

---

## License
MIT (or your company’s standard license)

---

## Appendix

### Example `requirements.txt`
```txt
fastapi==0.115.0
uvicorn[standard]==0.30.6
gunicorn==22.0.0
pydantic==2.8.2
boto3==1.35.0
python-dotenv==1.0.1
langgraph==0.2.34
# If you use LangChain wrappers for models
langchain==0.2.16
langchain-community==0.2.16
pypdf2==3.0.1
python-docx==1.1.2
pillow==10.4.0
# Optional PDF conversion
# libreoffice installed at OS level in Docker
```

### Example `ui/requirements-ui.txt`
```txt
streamlit==1.39.0
requests==2.32.3
python-dotenv==1.0.1
```

### Example `curl` usage
```bash
# List CVs
curl http://localhost:8080/list-cvs | jq

# Generate resumes
curl -X POST http://localhost:8080/generate \
  -H 'Content-Type: application/json' \
  -d '{"job_description": "We are hiring a Python backend engineer with AWS experience..."}' | jq
```

### Notes on Extraction
- The current sample uses an LLM helper like `llm_extract_text_from_docx`. If you prefer **strictly no LLM in extraction**, switch to local readers:
  - DOCX → `python-docx`
  - PDF → `pypdf`
This retains the Option A spirit (no paid OCR/extract services) while keeping generation LLM-only.

---

Happy shipping! If you want, I can also generate a skeleton folder structure with these files pre-populated.
