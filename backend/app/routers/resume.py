from __future__ import annotations
import os
import uuid
from fastapi import APIRouter, HTTPException
from ..config import settings
from app.core.trace_store import ResumeTraceStore
from ..core.s3 import list_keys
from ..core.graph import build_graph
from ..models.schemas import GenerateRequest, GenerateResponse, ListCvsResponse
from ..core.logging_setup import logger

router = APIRouter(prefix="/resume", tags=["resume"])


@router.get("/list-cvs", response_model=ListCvsResponse)
async def list_cvs():
    try:
        keys = list_keys(settings.S3_BUCKET, settings.S3_CV_PREFIX)
        return ListCvsResponse(bucket=settings.S3_BUCKET, prefix=settings.S3_CV_PREFIX, keys=keys)
    except Exception as e:
        logger.exception("Failed to list CVs")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/generate", response_model=GenerateResponse)
async def generate_all(req: GenerateRequest):
    try:
        cv_keys = list_keys(settings.S3_BUCKET, settings.S3_CV_PREFIX)
        request_id = str(uuid.uuid4())
        store = ResumeTraceStore()

        if not cv_keys:            
            api_unique_no = f"REQ-{request_id}"
            store.create_parent(
                request_id=request_id,
                api_unique_no=api_unique_no,
                job_description=req.job_description,
                created_at=None,
                llm_model=settings.LLM_MODEL_NAME
            )
            return GenerateResponse(processed_keys=[], output_keys=[], api_unique_no=api_unique_no, generated_count=0)
        
        # Create request trace (parent)
        api_unique_no = f"REQ-{request_id}"
        store.create_parent(
            request_id=request_id,
            api_unique_no=api_unique_no,
            job_description=req.job_description,
            created_at=None,
            llm_model=settings.LLM_MODEL_NAME
        )

        # Build the unified pipeline graph
        graph = build_graph()
        
        out_keys: list[str] = []
        processed: list[str] = []
        generated_count = 0

        for idx, key in enumerate(cv_keys, start=1):
            logger.info(f"\n[{idx}/{len(cv_keys)}] Processing {key}...")
            
            try:
                # Prepare initial state for the graph
                initial_state = {
                    "file_path": key,
                    "job_description": req.job_description,
                    "bucket": settings.S3_BUCKET,
                    "cv_prefix": settings.S3_CV_PREFIX,
                    "resume_prefix": settings.S3_RESUME_PREFIX,
                    "api_unique_no": api_unique_no
                }
                
                # Invoke the unified graph pipeline
                result = graph.invoke(initial_state)
                
                # Check if processing was successful
                output_key = result.get("output_key")
                if output_key:
                    processed.append(key)
                    out_keys.append(output_key)
                    
                    store.add_child_generation(
                        request_id=request_id,
                        file_path=key,
                        bucket=settings.S3_BUCKET,
                        resume_prefix=settings.S3_RESUME_PREFIX,
                        output_key=output_key,
                        llm_model=settings.LLM_MODEL_NAME
                    )

                    # increment the parent's count atomically
                    generated_count = store.increment_cv_count(request_id, by=1)

                    logger.info(f"✓ Successfully processed {key}")
                else:
                    logger.warning(f"✗ No output key for {key}")
                    
            except Exception as ex:
                logger.warning(f"✗ Skipping {key}: {ex}", exc_info=True)

        logger.info(f"\n{'=' * 60}")
        logger.info(f"Pipeline Complete: {len(processed)}/{len(cv_keys)} files processed")
        logger.info(f"{'=' * 60}")
        
        return GenerateResponse(processed_keys=processed, output_keys=out_keys, api_unique_no=api_unique_no, generated_count=generated_count)

    except Exception as e:
        logger.exception("Generation failed")
        raise HTTPException(status_code=500, detail=str(e))