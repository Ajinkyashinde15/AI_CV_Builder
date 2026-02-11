from __future__ import annotations
import os
from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END
from .llm import get_model
from .prompt import resume_prompt
from .extract import llm_extract_text_from_docx
from .docx_writer import write_resume_docx
from .s3 import get_object_to_path, put_file
from .logging_setup import logger


class State(TypedDict, total=False):
    # Input
    file_path: str
    job_description: str
    bucket: str
    cv_prefix: str
    resume_prefix: str
    
    # Processing
    cv_text: str
    resume_text: str
    
    # Output
    output_key: str
    local_docx_path: str


def _coerce_content(resp) -> str:
    """Return a consistent string from various LangChain response types."""
    if hasattr(resp, "content"):
        return str(getattr(resp, "content"))
    return str(resp)


def _truncate(text: str, max_chars: int) -> str:
    """Truncate overly long inputs to avoid model context errors."""
    if len(text) <= max_chars:
        return text
    head = text[: max_chars // 2]
    tail = text[-(max_chars // 2) :]
    return f"{head}\n...\n{tail}"


def node_extract(state: State) -> State:
    """
    Extract text from DOCX using LLM-based extraction.
    Reads file from S3, extracts content, stores in state.
    """
    logger.info(f"[EXTRACT] Starting extraction from {state['file_path']}")
    
    try:
        # Download file from S3
        local_in = f"/tmp/{os.path.basename(state['file_path'])}"
        get_object_to_path(state["bucket"], state["file_path"], local_in)
        logger.debug(f"[EXTRACT] Downloaded to {local_in}")
        
        # Extract text using LLM
        cv_text = llm_extract_text_from_docx(local_in)
        
        if not cv_text or not cv_text.strip():
            raise ValueError(f"LLM extraction returned empty text for {state['file_path']}")
        
        logger.info(f"[EXTRACT] Successfully extracted {len(cv_text)} characters")
        state["cv_text"] = cv_text
        
        # Cleanup temp file
        try:
            if os.path.exists(local_in):
                os.remove(local_in)
        except Exception as e:
            logger.warning(f"[EXTRACT] Failed to cleanup {local_in}: {e}")
        
        return state
    
    except Exception as e:
        logger.exception(f"[EXTRACT] Extraction failed for {state['file_path']}")
        raise


def node_generate(state: State) -> State:
    """
    Generate tailored resume using LLM.
    Takes CV text and job description, produces tailored resume text.
    """
    logger.info("[GENERATE] Starting resume generation")
    
    try:
        # Validate presence
        missing = [k for k in ("cv_text", "job_description") if k not in state or state[k] is None]
        if missing:
            raise ValueError(
                f"node_generate missing required state keys: {missing}. "
                f"State keys present: {list(state.keys())}"
            )
        
        # Validate non-empty
        cv_text = str(state.get("cv_text", "")).strip()
        jd_text = str(state.get("job_description", "")).strip()
        if not cv_text or not jd_text:
            raise ValueError("Both 'cv_text' and 'job_description' must be non-empty strings.")
        
        # Protect against oversized prompts
        cv_text = _truncate(cv_text, 12000)
        jd_text = _truncate(jd_text, 8000)
        
        # Build prompt and invoke model
        prompt = resume_prompt(cv_text, jd_text)
        model = get_model()
        
        resp = model.invoke(prompt)
        resume_text = _coerce_content(resp)
        
        if not resume_text or not resume_text.strip():
            raise ValueError("LLM returned empty resume text")
        
        logger.info(f"[GENERATE] Successfully generated resume ({len(resume_text)} characters)")
        state["resume_text"] = resume_text
        return state
    
    except Exception as e:
        logger.exception("[GENERATE] Resume generation failed")
        raise


def node_write(state: State) -> State:
    """
    Write resume text to DOCX file.
    Creates a local DOCX file from the generated resume text.
    """
    logger.info("[WRITE] Starting DOCX creation")
    
    try:
        resume_text = state.get("resume_text", "").strip()
        if not resume_text:
            raise ValueError("No resume text available to write")
        
        # Generate output filename
        input_basename = os.path.basename(state["file_path"])
        out_name = os.path.splitext(input_basename)[0] + "_resume.docx"
        local_out = f"/tmp/{out_name}"
        
        # Write DOCX
        write_resume_docx(resume_text, local_out)
        logger.info(f"[WRITE] DOCX written to {local_out}")
        
        state["local_docx_path"] = local_out
        return state
    
    except Exception as e:
        logger.exception("[WRITE] DOCX creation failed")
        raise


def node_upload(state: State) -> State:
    """
    Upload DOCX file to S3.
    Reads local DOCX file and uploads to S3 with proper key and content type.
    """
    logger.info("[UPLOAD] Starting S3 upload")
    
    try:
        local_docx = state.get("local_docx_path")
        if not local_docx or not os.path.exists(local_docx):
            raise ValueError(f"Local DOCX file not found: {local_docx}")
        
        # Build output S3 key
        input_basename = os.path.basename(state["file_path"])
        out_name = os.path.splitext(input_basename)[0] + "_resume.docx"
        out_key = f"{state['resume_prefix']}{out_name}"
        
        # Upload to S3
        put_file(
            state["bucket"],
            out_key,
            local_docx,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
        
        logger.info(f"[UPLOAD] Successfully uploaded to {out_key}")
        state["output_key"] = out_key
        
        # Cleanup local file
        try:
            if os.path.exists(local_docx):
                os.remove(local_docx)
        except Exception as e:
            logger.warning(f"[UPLOAD] Failed to cleanup {local_docx}: {e}")
        
        return state
    
    except Exception as e:
        logger.exception("[UPLOAD] S3 upload failed")
        raise


def build_graph() -> Graph:
    """
    Build and compile the unified resume generation pipeline:
    Extract (LLM) → Generate (LLM) → Write DOCX → Upload (S3)
    """
    g = StateGraph(State)
    
    # Add nodes
    g.add_node("extract", node_extract)
    g.add_node("generate", node_generate)
    g.add_node("write", node_write)
    g.add_node("upload", node_upload)
    
    # Define edges (pipeline flow)
    g.set_entry_point("extract")
    g.add_edge("extract", "generate")
    g.add_edge("generate", "write")
    g.add_edge("write", "upload")
    g.add_edge("upload", END)
    
    return g.compile()


def visualize_graph() -> str:
    """
    Generate ASCII art visualization of the graph structure.
    """
    graph = build_graph()
    try:
        # Try to get the graph visualization (LangGraph feature)
        return graph.get_graph().draw_ascii()
    except Exception:
        # Fallback ASCII visualization
        return """
╔════════════════════════════════════════════════════════════╗
║         Resume Generation Pipeline (LangGraph)             ║
╠════════════════════════════════════════════════════════════╣
║                                                            ║
║  [Extract (LLM)]                                          ║
║         ↓                                                  ║
║  [Generate Tailored Resume (LLM)]                         ║
║         ↓                                                  ║
║  [Write DOCX]                                             ║
║         ↓                                                  ║
║  [Upload to S3]                                           ║
║         ↓                                                  ║
║      [END]                                                ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝

State Flow:
  Input: file_path, job_description, bucket, cv_prefix, resume_prefix
  Extract: cv_text ← LLM(DOCX binary)
  Generate: resume_text ← LLM(cv_text + job_description)
  Write: local_docx_path ← DOCX(resume_text)
  Upload: output_key ← S3(local_docx_path)
"""