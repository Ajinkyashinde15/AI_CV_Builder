# Graph Visualization & API Reference

## 📊 Quick View: Pipeline Architecture

You can view the pipeline in three ways:

### 1. **ASCII Visualization (In Logs)**
Every time `/resume/generate` is called, the pipeline logs this visualization:

```
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
```

### 2. **Via API Endpoint**
```bash
curl http://localhost:8000/resume/graph-visualization
```

Response:
```json
{
  "graph": "╔════════════════════════════════════════════════════════════╗\n║         Resume Generation Pipeline (LangGraph)             ║\n..."
}
```

### 3. **Programmatically**
```python
from app.core.graph import visualize_graph, build_graph

# Get ASCII visualization
Graph structure:
print(visualize_graph())

# Build and inspect the graph object
graph = build_graph()
print(graph.get_graph().draw_ascii())  # LangGraph native visualization
```

---

## 📈 State Flow Diagram

```
                    ┌─────────────────────────┐
                    │   API Request State     │
                    │ - file_path             │
                    │ - job_description       │
                    │ - bucket, prefixes      │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │  node_extract           │
                    │  (LLM-based extraction) │
                    │  ▼                      │
                    │ cv_text → state        │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │  node_generate          │
                    │  (Resume tailoring)     │
                    │  ▼                      │
                    │ resume_text → state    │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │  node_write             │
                    │  (DOCX creation)        │
                    │  ▼                      │
                    │ local_docx_path → state│
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │  node_upload            │
                    │  (S3 upload & cleanup)  │
                    │  ▼                      │
                    │ output_key → state     │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   API Response          │
                    │ - output_key            │
                    │ - processed_keys        │
                    └─────────────────────────┘
```

---

## 🔄 Node Details

### Extract Node
```
INPUT:  file_path (S3 key), bucket
↓
1. Download from S3
2. Read DOCX binary
3. Encode to Base64
4. LLM extracts visible text
5. Normalize whitespace
↓
OUTPUT: cv_text
```

### Generate Node
```
INPUT:  cv_text, job_description
↓
1. Validate inputs
2. Truncate to token limits
3. Build prompt
4. LLM generates tailored resume
5. Extract response content
↓
OUTPUT: resume_text
```

### Write Node
```
INPUT:  resume_text, file_path
↓
1. Parse original filename
2. Create format spec (headers, bullets)
3. Write formatted DOCX
↓
OUTPUT: local_docx_path
```

### Upload Node
```
INPUT:  local_docx_path, bucket, resume_prefix
↓
1. Build S3 key
2. Upload file
3. Cleanup temp file
↓
OUTPUT: output_key
```

---

## 🧪 Testing the Pipeline

### Test via Python REPL

```python
# Test the unified graph
from app.core.graph import build_graph

# Build graph
graph = build_graph()

# Example state (you'd get file_path from S3 listing)
test_state = {
    "file_path": "cvs/test.docx",
    "job_description": "Senior Python Engineer with 5+ years experience.",
    "bucket": "ai-resume-cv-bucket",
    "cv_prefix": "cvs/",
    "resume_prefix": "resumes/",
}

# Run the pipeline
result = graph.invoke(test_state)

# Check output
print(f"Success! Output: {result.get('output_key')}")
```

### Test via API

```bash
# List available CVs
curl http://localhost:8000/resume/list-cvs

# View pipeline
curl http://localhost:8000/resume/graph-visualization

# Generate resumes
curl -X POST http://localhost:8000/resume/generate \
  -H "Content-Type: application/json" \
  -d '{
    "job_description": "We are looking for a Senior Python Developer with 5+ years of experience..."
  }'
```

---

## 📝 Logging Output Example

When you run the pipeline, you'll see:

```
============================================================
Resume Generation Pipeline
============================================================
╔════════════════════════════════════════════════════════════╗
║         Resume Generation Pipeline (LangGraph)             ║
╠════════════════════════════════════════════════════════════╣
[Visualization shown here]
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
[EXTRACT] Starting extraction from cvs/jane.docx
...
✓ Successfully processed cvs/jane.docx

============================================================
Pipeline Complete: 2/2 files processed
============================================================
```

---

## ⚙️ Environment Variables

Key config from `config.py`:

```bash
# S3 Configuration
S3_BUCKET="ai-resume-cv-bucket"
S3_CV_PREFIX="cvs/"
S3_RESUME_PREFIX="resumes/"
S3_ENDPOINT_URL="http://localhost:4566"  # LocalStack for local dev

# LLM Provider
LLM_PROVIDER="hf_endpoint"  # or "gemini"

# Hugging Face
HF_API_TOKEN="your-token"
HF_MODEL="Qwen/Qwen2.5-14B-Instruct-1M"
HF_MAX_NEW_TOKENS="1024"
HF_TEMPERATURE="0.2"
```

---

## 🚀 Key Improvements from Old Approach

| Aspect | Old (Separate) | New (Unified) |
|--------|---|---|
| **Flow** | Manual: Extract → Generate → Write → Upload | Single DAG pipeline |
| **State** | Passed manually between calls | Persists through graph |
| **Visibility** | Hard to track | Clear node-by-node logging |
| **Error Handling** | Manual try-catch per step | Built-in error propagation |
| **Extensibility** | Would need to refactor all steps | Add nodes to graph |
| **Testing** | Test each step separately | Test full pipeline atomically |
| **Code Clarity** | Mixed in resume.py | Separated into clean node functions |

---

## 📚 Related Files

- **[graph.py](../backend/app/core/graph.py)** - Graph definition and node implementations
- **[resume.py](../backend/app/routers/resume.py)** - API endpoints
- **[extract.py](../backend/app/core/extract.py)** - LLM extraction logic
- **[llm.py](../backend/app/core/llm.py)** - LLM provider abstraction
- **[s3.py](../backend/app/core/s3.py)** - S3 operations
- **[docx_writer.py](../backend/app/core/docx_writer.py)** - DOCX formatting
- **[UNIFIED_LANGRAPH_PIPELINE.md](../UNIFIED_LANGRAPH_PIPELINE.md)** - Detailed architecture docs

---

## 🔗 References

- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [State Management in LangGraph](https://langchain-ai.github.io/langgraph/tutorials/basic_graph/)
- [Graph Visualization](https://langchain-ai.github.io/langgraph/concepts/#visualization)
