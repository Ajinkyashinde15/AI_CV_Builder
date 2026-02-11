# Unified LangGraph Pipeline for Resume Generation

## Overview

The AI-CV-Builder now uses a **single, unified LangGraph pipeline** for the entire resume generation process. This replaces the previous approach where extraction, generation, writing, and uploading were handled separately.

## Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────┐
│              Resume Generation Pipeline (LangGraph)          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  [Extract (LLM)]  ──→  [Generate (LLM)]  ──→  [Write DOCX] │
│         ↓                     ↓                      ↓        │
│  Download CV from S3  LLM Tailoring         Create formatted │
│  Extract text via      to Job Description   DOCX file        │
│  LLM Base64 decoding                                         │
│                                                    ↓          │
│                    [Upload to S3]  ←──────────────┘          │
│                          ↓                                    │
│                      Store result                            │
│                         ↓                                    │
│                      [END]                                   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## State Definition

The pipeline uses a single `State` TypedDict that flows through all nodes:

```python
class State(TypedDict, total=False):
    # Input Configuration
    file_path: str           # S3 path to input CV
    job_description: str     # Target job description
    bucket: str              # S3 bucket name
    cv_prefix: str           # S3 prefix for CVs
    resume_prefix: str       # S3 prefix for output resumes
    
    # Processing Pipeline
    cv_text: str             # Extracted CV text (node_extract → node_generate)
    resume_text: str         # Generated resume (node_generate → node_write)
    
    # Output
    output_key: str          # Final S3 key (node_upload → response)
    local_docx_path: str     # Temporary local DOCX path (node_write → node_upload)
```

## Pipeline Nodes

### 1. **node_extract** - LLM-Based DOCX Extraction
**Purpose:** Extract all visible text from a Word document using LLM

**Input State:**
- `file_path` - S3 path to CV document
- `bucket` - S3 bucket name

**Process:**
1. Download DOCX file from S3 to local `/tmp` directory
2. Read binary file and encode to Base64
3. Send to LLM (Gemini or HF) with extraction instructions
4. LLM decodes and extracts all visible text
5. Normalize whitespace and collapse blank lines

**Output State:**
- `cv_text` - Extracted text ready for generation

**Error Handling:**
- Validates file exists and is not empty
- Raises error if LLM returns empty content
- Logs warnings if extraction is below minimum threshold

---

### 2. **node_generate** - Resume Tailoring (LLM)
**Purpose:** Generate a tailored, ATS-friendly resume from CV and job description

**Input State:**
- `cv_text` - From previous extraction node
- `job_description` - From API request

**Process:**
1. Validate both cv_text and job_description are present and non-empty
2. Truncate to safe token limits (cv: 12K chars, jd: 8K chars)
3. Build prompt using `resume_prompt()` template
4. Invoke LLM to generate tailored resume
5. Extract and normalize response content

**Output State:**
- `resume_text` - Formatted, tailored resume text

**Prompt Features:**
- Strict output format: plain text only (no Markdown)
- Section headers in UPPERCASE
- Bullets with "•" or "-" characters
- Quantified achievements and metrics
- ATS-optimized structure

---

### 3. **node_write** - DOCX File Creation
**Purpose:** Convert plain text resume to a formatted Word document

**Input State:**
- `resume_text` - From generation node
- `file_path` - To determine output filename

**Process:**
1. Extract original filename from `file_path`
2. Create output filename: `{original_name}_resume.docx`
3. Use `write_resume_docx()` to format and write DOCX
4. Store local file path for next node

**Output State:**
- `local_docx_path` - Path to temporary DOCX file

**Formatting Features:**
- Recognizes UPPERCASE headers as section titles
- Converts bullets from "•" / "-" to Word bullet formatting
- Applies Calibri 11pt font
- Proper paragraph spacing

---

### 4. **node_upload** - S3 Upload
**Purpose:** Upload generated resume to S3 and cleanup temporary files

**Input State:**
- `local_docx_path` - Path to DOCX file
- `bucket` - S3 bucket
- `resume_prefix` - Output S3 prefix

**Process:**
1. Verify local DOCX file exists
2. Build S3 output key: `{resume_prefix}{original_name}_resume.docx`
3. Upload file with proper content type (Word DOCX MIME type)
4. Delete temporary local file
5. Store S3 key in state

**Output State:**
- `output_key` - S3 path to generated resume

**Cleanup:**
- Automatically removes temporary files after upload

---

## Data Flow Example

### Request
```python
# API: POST /resume/generate
{
    "job_description": "Senior Python Engineer with 5+ years experience..."
}
```

### Graph Invocation
```python
initial_state = {
    "file_path": "cvs/john_smith.docx",  # From S3 listing
    "job_description": "Senior Python Engineer...",
    "bucket": "ai-resume-cv-bucket",
    "cv_prefix": "cvs/",
    "resume_prefix": "resumes/",
}

result = graph.invoke(initial_state)
# result["output_key"] = "resumes/john_smith_resume.docx"
```

### State Evolution Through Pipeline

```
[INITIAL] →
{
  file_path: "cvs/john_smith.docx",
  job_description: "Senior Python Engineer...",
  bucket: "ai-resume-cv-bucket",
  cv_prefix: "cvs/",
  resume_prefix: "resumes/"
}

[AFTER Extract] →
{
  ...(previous fields)...
  cv_text: "EXPERIENCE\n2020-present: Senior Developer at TechCorp..."
}

[AFTER Generate] →
{
  ...(previous fields)...
  resume_text: "SUMMARY\nSenior Python developer with 5+ years...\n\nCORE SKILLS..."
}

[AFTER Write] →
{
  ...(previous fields)...
  local_docx_path: "/tmp/john_smith_resume.docx"
}

[AFTER Upload - FINAL] →
{
  ...(previous fields)...
  output_key: "resumes/john_smith_resume.docx"
}
```

## API Endpoints

### 1. List CVs
```
GET /resume/list-cvs
```
Returns: List of available CV files in S3

### 2. View Pipeline Visualization
```
GET /resume/graph-visualization
```
Returns: ASCII art visualization of the pipeline structure

### 3. Generate Resumes
```
POST /resume/generate
Content-Type: application/json

{
    "job_description": "We are looking for..."
}
```

**Response:**
```json
{
    "processed_keys": [
        "cvs/john.docx",
        "cvs/jane.docx"
    ],
    "output_keys": [
        "resumes/john_resume.docx",
        "resumes/jane_resume.docx"
    ]
}
```

## Key Benefits

### ✅ Single Traceable DAG
- All steps visible in one graph
- Easy to debug and understand flow
- Can be visualized and documented

### ✅ Persistent State
- State persists through entire pipeline
- Each node has access to all previous outputs
- Easy to add validation/logging between steps

### ✅ Robust Error Handling
- Errors propagate cleanly
- Each node validates its inputs
- Failed operations don't silently fail
- Detailed logging at each stage

### ✅ Modularity & Extensibility
- Independent, testable nodes
- Easy to add/modify pipeline steps
- Can add conditional branches: success/failure paths, retries, etc.
- Simple to add new intermediate processing

### ✅ Two LLM Calls in One Flow
- Extraction (DOCX → Text)
- Generation (CV + JD → Resume)
- Future: Can add validation, polish, or summary steps

### ✅ Better Monitoring
- Detailed logging at each node
- Progress tracking for batch operations
- Pipeline visualization available via API
- Clear stage breakdown for debugging

## Logging Output Example

```
============================================================
Resume Generation Pipeline
============================================================
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
============================================================

[1/2] Processing cvs/john.docx...
[EXTRACT] Starting extraction from cvs/john.docx
[EXTRACT] Downloaded to /tmp/john.docx
[EXTRACT] Successfully extracted 3245 characters
[GENERATE] Starting resume generation
[GENERATE] Successfully generated resume (1847 characters)
[WRITE] Starting DOCX creation
[WRITE] DOCX written to /tmp/john_resume.docx
[UPLOAD] Starting S3 upload
[UPLOAD] Successfully uploaded to resumes/john_resume.docx
✓ Successfully processed cvs/john.docx

[2/2] Processing cvs/jane.docx...
✓ Successfully processed cvs/jane.docx

============================================================
Pipeline Complete: 2/2 files processed
============================================================
```

## Configuration & Tuning

### LLM Extraction Settings (`extract.py`)
```python
MIN_MEANINGFUL_LEN = 32                  # Minimum extracted text length
MAX_BASE64_PART_CHARS = 130_000          # Chunk size for large DOCX files
NORMALIZE_WHITESPACE = True              # Clean up extracted text
```

### Token Limits (`graph.py`)
```python
cv_text = _truncate(cv_text, 12000)     # Max 12K chars for CV
jd_text = _truncate(jd_text, 8000)      # Max 8K chars for JD
```

### LLM Provider (`config.py`)
```python
LLM_PROVIDER = "hf_endpoint"              # "gemini" or "hf_endpoint"
HF_MAX_NEW_TOKENS = 1024                  # Generation token budget
HF_TEMPERATURE = 0.2                      # Lower = more deterministic
```

## Future Enhancements

Possible additions to the pipeline:

1. **Validation Node** - Check resume quality/completeness
2. **Polish Node** - Second LLM pass to improve formatting
3. **Caching** - Cache extracted CV text to avoid re-extraction
4. **Parallel Processing** - Process multiple files in parallel with LangGraph subgraphs
5. **Conditional Routing** - Different paths based on resume quality
6. **Retry Logic** - Automatic retries for failed LLM calls

Example future pipeline:
```
Extract → Validate → [Pass] → Generate → Polish → Write → Upload
                        ↓
                     [Fail] → Notify/Retry
```

## Implementation Notes

- All file cleanup is done with best-effort exception handling
- Logging uses the configured logger from `logging_setup.py`
- S3 operations delegate to `s3.py` module
- LLM operations delegate to `llm.py` module
- DOCX formatting is handled by `docx_writer.py`
- Prompt templates come from `prompt.py`

---

**Generated:** 2024  
**Status:** Production-ready  
**Tested:** Yes - Batch processing with detailed logging
