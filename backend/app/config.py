# config.py
import os

class Settings:
    ENV: str = os.getenv("ENV", "local")
    AWS_REGION: str = os.getenv("AWS_REGION", "us-east-1")
    S3_BUCKET: str = os.getenv("S3_BUCKET", "ai-resume-cv-bucket")
    S3_CV_PREFIX: str = os.getenv("S3_CV_PREFIX", "cvs/")
    S3_RESUME_PREFIX: str = os.getenv("S3_RESUME_PREFIX", "resumes/")
    S3_ENDPOINT_URL: str | None = os.getenv("S3_ENDPOINT_URL", "http://localhost:4566")

    # ---- LLM provider selector ----
    # Allowed: "gemini", "hf_endpoint"
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "hf_endpoint")

    # ---- Gemini ----
    GEMINI_API_KEY: str | None = os.getenv("GEMINI_API_KEY")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-pro")

    # ---- Hugging Face Inference API ----
    HF_API_TOKEN: str | None = os.getenv("HF_API_TOKEN", "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")
    HF_MODEL: str = os.getenv("HF_MODEL", "Qwen/Qwen2.5-14B-Instruct-1M")
    HF_TASK: str = os.getenv("HF_TASK", "text-generation")
    HF_MAX_NEW_TOKENS: int = int(os.getenv("HF_MAX_NEW_TOKENS", "1024"))
    HF_TEMPERATURE: float = float(os.getenv("HF_TEMPERATURE", "0.2"))
    HF_TOP_P: float = float(os.getenv("HF_TOP_P", "0.95"))

settings = Settings()