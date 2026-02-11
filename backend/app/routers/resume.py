from __future__ import annotations
import os
from fastapi import APIRouter, HTTPException
from ..config import settings
from ..core.s3 import list_keys
from ..core.graph import build_graph, visualize_graph
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


@router.get("/graph-visualization")
async def graph_visualization():
    """
    Returns ASCII visualization of the resume generation pipeline.
    """
    try:
        visualization = visualize_graph()
        return {"graph": visualization}
    except Exception as e:
        logger.exception("Failed to visualize graph")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate", response_model=GenerateResponse)
async def generate_all(req: GenerateRequest):
    try:
        cv_keys = list_keys(settings.S3_BUCKET, settings.S3_CV_PREFIX)
        if not cv_keys:
            return GenerateResponse(processed_keys=[], output_keys=[])

        # Build the unified pipeline graph
        graph = build_graph()
        
        # Log the graph structure
        logger.info("=" * 60)
        logger.info("Resume Generation Pipeline")
        logger.info("=" * 60)
        logger.info(visualize_graph())
        logger.info("=" * 60)
        
        out_keys: list[str] = []
        processed: list[str] = []

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
                }
                
                # Invoke the unified graph pipeline
                result = graph.invoke(initial_state)
                
                # Check if processing was successful
                output_key = result.get("output_key")
                if output_key:
                    processed.append(key)
                    out_keys.append(output_key)
                    logger.info(f"✓ Successfully processed {key}")
                else:
                    logger.warning(f"✗ No output key for {key}")
                    
            except Exception as ex:
                logger.warning(f"✗ Skipping {key}: {ex}", exc_info=True)

        logger.info(f"\n{'=' * 60}")
        logger.info(f"Pipeline Complete: {len(processed)}/{len(cv_keys)} files processed")
        logger.info(f"{'=' * 60}")
        
        return GenerateResponse(processed_keys=processed, output_keys=out_keys)

    except Exception as e:
        logger.exception("Generation failed")
        raise HTTPException(status_code=500, detail=str(e))