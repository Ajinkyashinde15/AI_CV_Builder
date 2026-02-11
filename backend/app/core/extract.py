from __future__ import annotations
from typing import List, Optional
import os
import re
import base64
import logging

from .llm import get_model  # reuse your existing provider selection

logger = logging.getLogger(__name__)

# ---- knobs you can tune ----
MIN_MEANINGFUL_LEN = 32                  # keep or tune as needed
MAX_BASE64_PART_CHARS = 130_000          # chunk size (chars) for very large DOCX
STRICT_MIN_BYTES = 1                     # zero-byte guard
NORMALIZE_WHITESPACE = True              # keep true for cleaner downstream prompts

EXTRACTION_SYSTEM_PROMPT = (
    "You are a highly accurate text extraction engine.\n"
    "You will receive a Microsoft Word DOCX file encoded in Base64.\n"
    "Tasks:\n"
    "1) Decode the file.\n"
    "2) Extract ALL visible text exactly as a human sees it:\n"
    "   - body paragraphs, headers, footers\n"
    "   - tables (row order preserved)\n"
    "   - text boxes/shapes/sidebars/multi-column text\n"
    "   - bullet lists and numbering\n"
    "3) Output ONLY the clean, readable text.\n"
    "4) Preserve headings and section labels when possible.\n"
    "5) DO NOT summarize or omit content.\n"
)

def _normalize(text: str) -> str:
    """Normalize whitespace and collapse blank lines."""
    if not NORMALIZE_WHITESPACE:
        return text
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)       # collapse runs of spaces
    text = re.sub(r"\n{3,}", "\n\n", text)    # collapse 3+ \n to 2
    text = "\n".join(line.strip() for line in text.split("\n"))
    return text.strip()

def _file_to_b64(path: str) -> str:
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    size = os.path.getsize(path)
    if size < STRICT_MIN_BYTES:
        raise ValueError(f"Zero-byte file: {path}")
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

def _chunk(text: str, chunk_chars: int) -> List[str]:
    if len(text) <= chunk_chars:
        return [text]
    return [text[i : i + chunk_chars] for i in range(0, len(text), chunk_chars)]

def _build_prompt_for_parts(b64_parts: List[str]) -> str:
    """
    Build a single human message that includes all parts with clear delimiters.
    Keeping it single-message avoids provider-specific multi-part quirks.
    """
    head = [EXTRACTION_SYSTEM_PROMPT, "BEGIN_DOCX_BASE64"]
    body = []
    for i, part in enumerate(b64_parts, start=1):
        body.append(f"\n--- PART {i}/{len(b64_parts)} START ---\n")
        body.append(part)
        body.append(f"\n--- PART {i}/{len(b64_parts)} END ---\n")
    tail = [
        "END_DOCX_BASE64\n",
        "Reconstruct the complete document text from all parts.\n"
        "Return ONLY the extracted text (no explanations)."
    ]
    return "\n".join(head + body + tail)

def llm_extract_text_from_docx(
    file_path: str,
    *,
    chunk_chars: int = MAX_BASE64_PART_CHARS,
    min_len: int = MIN_MEANINGFUL_LEN,
) -> str:
    """
    LLM-based extraction:
      - Reads DOCX bytes and Base64-encodes them
      - Chunks if necessary
      - Asks the LLM to decode and extract all visible text
      - Returns normalized text (empty string if model returns nothing)
    """
    abs_path = os.path.abspath(file_path)
    if not os.path.exists(abs_path):
        raise FileNotFoundError(abs_path)

    size = os.path.getsize(abs_path)

    # Encode DOCX to Base64 and chunk large payloads
    b64 = _file_to_b64(abs_path)
    parts = _chunk(b64, chunk_chars)

    # Build prompt and invoke model
    prompt = _build_prompt_for_parts(parts)

    llm = get_model()  # Gemini or HF endpoint via your existing wrapper
    try:
        # LangChain chat models accept a plain string as message content
        resp = llm.invoke(prompt)
        content = getattr(resp, "content", str(resp))
    except Exception as e:
        raise RuntimeError(f"LLM extraction failed: {e}") from e

    text = (content or "").strip()
    if not text:
        logger.warning("[LLM-EXTRACT] Model returned empty content.")
        return ""

    text = _normalize(text)
    logger.debug(f"[LLM-EXTRACT] extracted_chars={len(text)} preview={text[:160]!r}")

    # Optional minimum-length gate
    if min_len and len(text) < min_len:
        logger.info(f"[LLM-EXTRACT] extracted text below threshold ({len(text)} < {min_len})")
    return text

# Optional convenience wrapper if elsewhere you still call `extract_text`
def extract_text(file_path: str) -> Optional[str]:
    """
    DOCX-only public entrypoint using the LLM extractor.
    Returns None if the result is below MIN_MEANINGFUL_LEN.
    """
    txt = llm_extract_text_from_docx(file_path)
    return txt if txt and len(txt) >= MIN_MEANINGFUL_LEN else None