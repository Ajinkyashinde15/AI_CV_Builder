from __future__ import annotations
from ..config import settings

def get_model():
    provider = (settings.LLM_PROVIDER or "gemini").lower()

    if provider == "gemini":
        # --- Gemini via LangChain ---
        from langchain_google_genai import ChatGoogleGenerativeAI

        if not settings.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is not set (required for provider=gemini)")

        return ChatGoogleGenerativeAI(
            model=settings.GEMINI_MODEL,
            google_api_key=settings.GEMINI_API_KEY,
            temperature=0.2,  # keep aligned with your current behavior
        )

    if provider == "hf_endpoint":
        # --- Hugging Face Inference API via LangChain ---
        # Use HuggingFaceEndpoint (LLM) + ChatHuggingFace (ChatModel wrapper)
        from langchain_huggingface import HuggingFaceEndpoint, ChatHuggingFace

        if not settings.HF_API_TOKEN:
            raise RuntimeError("HF_API_TOKEN is not set (required for provider=hf_endpoint)")

        llm = HuggingFaceEndpoint(
            repo_id=settings.HF_MODEL,
            task=settings.HF_TASK,  # typically "text-generation"
            max_new_tokens=settings.HF_MAX_NEW_TOKENS,
            temperature=settings.HF_TEMPERATURE,
            top_p=settings.HF_TOP_P,           
            huggingfacehub_api_token=settings.HF_API_TOKEN,  # <- correct kw name
            timeout=120,
        )
        # Wrap into a ChatModel so your graph code remains unchanged
        return ChatHuggingFace(llm=llm)

    raise ValueError(f"Unsupported LLM_PROVIDER='{settings.LLM_PROVIDER}'. Use 'gemini' or 'hf_endpoint'.")