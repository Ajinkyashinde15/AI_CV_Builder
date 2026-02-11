#!/usr/bin/env python3
"""
Demo script showing the unified LangGraph pipeline for resume generation.
This demonstrates the complete flow: Extract → Generate → Write → Upload
"""
from app.core.graph import build_graph, visualize_graph

def main():
    print("\n" + "=" * 70)
    print("AI-CV-Builder: Unified LangGraph Pipeline Demo")
    print("=" * 70)
    
    # Show the pipeline architecture
    print("\n📊 PIPELINE ARCHITECTURE:\n")
    print(visualize_graph())
    
    # Build the graph
    print("\n🔧 Building the graph...\n")
    graph = build_graph()
    
    # Show graph structure
    print("\n📈 GRAPH STRUCTURE:\n")
    try:
        # Try to get Mermaid/ASCII representation
        print(graph.get_graph().draw_ascii())
    except Exception as e:
        print(f"  [Graph structure visualization not available: {e}]")
    
    # Explain the state flow
    print("\n" + "=" * 70)
    print("STATE FLOW & DATA TRANSFORMATION")
    print("=" * 70)
    
    state_flow = """
    
    INITIAL STATE (from API request):
    ├── file_path: str          (S3 path to input CV)
    ├── job_description: str    (Job description text)
    ├── bucket: str             (S3 bucket name)
    ├── cv_prefix: str          (S3 prefix for CVs)
    └── resume_prefix: str      (S3 prefix for output resumes)
    
    NODE 1: [extract] - LLM-based DOCX text extraction
    ├── Input: file_path, bucket
    ├── Process: Download DOCX → Encode to Base64 → LLM extraction
    └── Output: cv_text (extracted text from DOCX)
    
    NODE 2: [generate] - Tailored resume generation
    ├── Input: cv_text, job_description
    ├── Process: Create prompt → LLM generation (tailored to JD)
    └── Output: resume_text (ATS-friendly resume)
    
    NODE 3: [write] - DOCX file creation
    ├── Input: resume_text
    ├── Process: Format text → Create DOCX with headers/bullets
    └── Output: local_docx_path (path to local DOCX file)
    
    NODE 4: [upload] - S3 upload
    ├── Input: local_docx_path, bucket, resume_prefix
    ├── Process: Upload DOCX to S3 with correct content type
    └── Output: output_key (S3 path to generated resume)
    
    FINAL STATE:
    └── output_key: str  (S3 path to successfully generated resume)
    """
    
    print(state_flow)
    
    # Key benefits
    print("\n" + "=" * 70)
    print("KEY BENEFITS OF UNIFIED LANGRAPH PIPELINE")
    print("=" * 70)
    
    benefits = """
    
    ✅ Single Traceable DAG
       → All steps in one graph, easy to visualize and debug
       → Clear data flow from input to output
    
    ✅ Persistent State
       → State persists through entire pipeline
       → Each node can access all previous outputs
       → Easy to add intermediate logging/validation
    
    ✅ Error Handling
       → Errors propagate cleanly through the pipeline
       → Failed operations can be caught and reported
       → No mysterious failures halfway through process
    
    ✅ Modularity
       → Each node is independent and testable
       → Easy to add/modify/remove pipeline steps
       → Simple to add conditional branches later
    
    ✅ LLM Integration
       → Two LLM calls (extraction + generation) in one flow
       → Could add more LLM steps later (validation, polish, etc.)
       → All LLM logic centralized in node functions
    
    ✅ Monitoring & Logging
       → Added detailed logging at each stage
       → Progress tracking for batch operations
       → Pipeline visualization for documentation
    """
    
    print(benefits)
    
    # Example usage
    print("\n" + "=" * 70)
    print("EXAMPLE API USAGE")
    print("=" * 70)
    
    usage = """
    
    1. LIST AVAILABLE CVs:
       GET /resume/list-cvs
       
    2. VIEW PIPELINE ARCHITECTURE:
       GET /resume/graph-visualization
       
    3. GENERATE TAILORED RESUMES:
       POST /resume/generate
       {
           "job_description": "We are looking for a Senior Python Developer..."
       }
       
       Response:
       {
           "processed_keys": ["cvs/john.docx", "cvs/jane.docx"],
           "output_keys": ["resumes/john_resume.docx", "resumes/jane_resume.docx"]
       }
    """
    
    print(usage)
    
    print("\n" + "=" * 70)
    print("Pipeline initialized successfully! ✨")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
