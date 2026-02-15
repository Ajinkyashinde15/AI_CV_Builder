# config.py
import os
import json
import logging
from functools import lru_cache
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

# ============================================================================
# ENVIRONMENT DETECTION & BOTO3 CLIENT FACTORY
# ============================================================================

def get_env() -> str:
    """
    Detect environment: 'dev' (AWS Lambda), 'local' (localhost/localstack).
    Defaults to 'local' if ENV not set.
    """
    return os.getenv("ENV", "local").lower()


def get_aws_clients(region: str, endpoint_url: str | None = None):
    """
    Create boto3 clients (S3, DynamoDB, Secrets Manager).
    
    - For 'local'/localstack: uses endpoint_url pointing to http://localhost:4566
    - For 'dev'/AWS: uses AWS endpoints directly (no endpoint_url)
    """
    s3 = boto3.client(
        "s3",
        region_name=region,
        endpoint_url=endpoint_url,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "test"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "test"),
    )
    
    dynamodb = boto3.client(
        "dynamodb",
        region_name=region,
        endpoint_url=endpoint_url,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "test"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "test"),
    )
    
    secrets_manager = boto3.client(
        "secretsmanager",
        region_name=region,
        endpoint_url=endpoint_url,
    )
    
    return {
        "s3": s3,
        "dynamodb": dynamodb,
        "secretsmanager": secrets_manager,
    }


# ============================================================================
# SECRETS MANAGER CACHING (Lambda Global Scope)
# ============================================================================

# Global cache for secrets (persists across Lambda invocations during warm starts)
_secrets_cache: dict[str, str] = {}


def get_secrets_from_manager(secret_name: str, region: str, endpoint_url: str | None = None) -> dict:
    """
    Fetch secrets from AWS Secrets Manager with caching.
    
    On warm Lambda starts, secrets are cached in global scope.
    On cold starts, fetches from Secrets Manager.
    
    Args:
        secret_name: Name of the secret in Secrets Manager (e.g., 'CvBuilderSecretsManager')
        region: AWS region
        endpoint_url: LocalStack endpoint (for local dev)
    
    Returns:
        Dict with 'HF_API_TOKEN' and/or 'GEMINI_API_KEY'
    """
    # Return cached secrets if available (warm Lambda start)
    if _secrets_cache:
        logger.info("[CONFIG] Returning secrets from cache (warm start)")
        return _secrets_cache
    
    env = get_env()
    logger.info(f"[CONFIG] Environment: {env}")
    
    # Local/LocalStack: Fetch from Secrets Manager
    if env == "local":
        try:
            sm_client = boto3.client(
                "secretsmanager",
                region_name=region,
                endpoint_url=endpoint_url,
            )
            response = sm_client.get_secret_value(SecretId=secret_name)
            
            if "SecretString" in response:
                secret_dict = json.loads(response["SecretString"])
                _secrets_cache.update(secret_dict)
                logger.info(f"[CONFIG] Secrets loaded from LocalStack Secrets Manager")
                return secret_dict
        except ClientError as e:
            logger.warning(f"[CONFIG] Failed to get secrets from LocalStack: {e}")
            # Fall back to environment variables
    
    # Dev/AWS Lambda: Fetch from Secrets Manager
    elif env == "dev":
        try:
            sm_client = boto3.client(
                "secretsmanager",
                region_name=region,
            )
            response = sm_client.get_secret_value(SecretId=secret_name)
            
            if "SecretString" in response:
                secret_dict = json.loads(response["SecretString"])
                _secrets_cache.update(secret_dict)
                logger.info(f"[CONFIG] Secrets loaded from AWS Secrets Manager")
                return secret_dict
        except ClientError as e:
            logger.error(f"[CONFIG] Failed to get secrets from AWS: {e}")
            raise
    
    # Fallback to environment variables
    logger.info("[CONFIG] Using environment variables for secrets (fallback)")
    return {
        "HF_API_TOKEN": os.getenv("HF_API_TOKEN", ""),
        "GEMINI_API_KEY": os.getenv("GEMINI_API_KEY", ""),
    }


# ============================================================================
# SETTINGS CLASS
# ============================================================================

class Settings:
    # Environment and AWS Config
    ENV: str = get_env()
    AWS_REGION: str = os.getenv("AWS_REGION", "us-east-1")
    AWS_ENDPOINT_URL: str | None = os.getenv("AWS_ENDPOINT_URL", None)
    
    # For LocalStack: default to http://localhost:4566
    if ENV == "local" and not AWS_ENDPOINT_URL:
        AWS_ENDPOINT_URL = "http://localhost:4566"
    
    # Secrets Manager
    SECRETS_MANAGER_NAME: str = os.getenv("SECRETS_MANAGER_NAME", "CvBuilderSecretsManager")
    
    # S3 Configuration
    S3_BUCKET: str = os.getenv("S3_BUCKET", "ai-resume-cv-bucket")
    S3_CV_PREFIX: str = os.getenv("S3_CV_PREFIX", "rawcvs/")
    S3_RESUME_PREFIX: str = os.getenv("S3_RESUME_PREFIX", "processedresumes/")
    
    # DynamoDB (trace)
    TRACE_TABLE: str = os.getenv("TRACE_TABLE", "CvBuilderDb")
    
    # LLM Provider selector ("gemini" or "hf_endpoint")
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "hf_endpoint").lower()
    
    # HuggingFace Model Config
    HF_MODEL: str = os.getenv("HF_MODEL", "Qwen/Qwen2.5-14B-Instruct-1M")
    HF_TASK: str = os.getenv("HF_TASK", "text-generation")
    HF_MAX_NEW_TOKENS: int = int(os.getenv("HF_MAX_NEW_TOKENS", "1024"))
    HF_TEMPERATURE: float = float(os.getenv("HF_TEMPERATURE", "0.2"))
    HF_TOP_P: float = float(os.getenv("HF_TOP_P", "0.95"))
    
    # Gemini Model Config
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
    
    # Fetch secrets from Secrets Manager (with fallback to env vars)
    _secrets = get_secrets_from_manager(
        SECRETS_MANAGER_NAME,
        AWS_REGION,
        AWS_ENDPOINT_URL if ENV == "local" else None
    )
    
    # Extract API keys from secrets (or env vars as fallback)
    HF_API_TOKEN: str | None = _secrets.get("HF_API_TOKEN") or os.getenv("HF_API_TOKEN")
    GEMINI_API_KEY: str | None = _secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
    
    @property
    def LLM_MODEL_NAME(self) -> str:
        """Returns the human-readable model name for database tracking."""
        if self.LLM_PROVIDER == "gemini":
            return self.GEMINI_MODEL
        return self.HF_MODEL
    
    @classmethod
    def get_boto_clients(cls):
        """
        Get configured boto3 clients (S3, DynamoDB, Secrets Manager).
        Automatically uses correct endpoints based on environment.
        """
        return get_aws_clients(
            cls.AWS_REGION,
            cls.AWS_ENDPOINT_URL if cls.ENV == "local" else None
        )

# Global settings instance
settings = Settings()

logger.info(f"[CONFIG] Initialized: ENV={settings.ENV}, PROVIDER={settings.LLM_PROVIDER}")
logger.info(f"[CONFIG] S3: bucket={settings.S3_BUCKET}, cv_prefix={settings.S3_CV_PREFIX}")
logger.info(f"[CONFIG] DynamoDB: table={settings.TRACE_TABLE}")
logger.info(f"[CONFIG] LLM Model: {settings.LLM_MODEL_NAME}")