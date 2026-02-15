from __future__ import annotations
from pydantic import BaseModel, Field
from typing import List

class GenerateRequest(BaseModel):
    job_description: str = Field(..., description="Job Description to tailor resumes")

class GenerateResponse(BaseModel):
    processed_keys: List[str]
    output_keys: List[str]
    api_unique_no: str
    generated_count: int
    
class ListCvsResponse(BaseModel):
    bucket: str
    prefix: str
    keys: List[str]
