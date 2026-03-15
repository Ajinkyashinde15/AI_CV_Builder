# trace_store.py
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any

import boto3
from botocore.exceptions import ClientError


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class ResumeTraceStore:
    """
    Thin wrapper around a DynamoDB table with the following single-table design:

      - Parent item (one per request):
        pk = "TRACEREQ#{request_id}"
        sk = "PARENT"
        attrs: request_id, api_unique_no, job_description, created_at, cv_count (number)

      - Child item (one per generated CV):
        pk = "TRACEREQ#{request_id}"
        sk = "CHILD#{child_uuid}"
        attrs: file_path, bucket, resume_prefix, output_key, llm_model

    Notes:
      * 'cv_count' is incremented atomically on the parent using ADD.
      * We only write ONCE per CV generation (no per-stage logging).
    """

    def __init__(
        self,
        table_name: Optional[str] = None,
        region_name: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        boto3_session: Optional[boto3.session.Session] = None,
    ) -> None:
        self.table_name = table_name or os.getenv("TRACE_TABLE", "drc-core-dyn")
        self.region_name = region_name or os.getenv("AWS_REGION", "us-east-1")
        self.endpoint_url = endpoint_url or os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")

        session = boto3_session or boto3.session.Session(region_name=self.region_name)
        dynamodb = session.resource("dynamodb", endpoint_url=self.endpoint_url)
        self.table = dynamodb.Table(self.table_name)

    # ---------- Parent API ----------

    def create_parent(
        self,
        *,
        request_id: str,
        api_unique_no: str,
        job_description: str,
        created_at: Optional[str] = None,
        llm_model: Optional[str] = None,  # optional: store default/declared model on parent as well
    ) -> None:
        """
        Create the parent item for this request. Safe to call once per request.
        Uses a conditional put so we don't overwrite if it already exists.
        """
        created_at = created_at or _iso_now()
        item: Dict[str, Any] = {
            "pk": f"TRACEREQ#{request_id}",
            "sk": "PARENT",
            "request_id": request_id,
            "api_unique_no": api_unique_no,
            "job_description": job_description,
            "created_at": created_at,
            "cv_count": 0,
        }
        if llm_model:
            item["llm_model"] = llm_model

        try:
            self.table.put_item(
                Item=item,
                ConditionExpression="attribute_not_exists(pk) AND attribute_not_exists(sk)",
            )
        except ClientError as e:
            # If it already exists (ConditionalCheckFailed), that's fine; otherwise bubble up
            if e.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                raise

    def increment_cv_count(self, request_id: str, by: int = 1) -> int:
        """
        Atomically increment the cv_count on the parent and return the new value.
        """
        resp = self.table.update_item(
            Key={"pk": f"TRACEREQ#{request_id}", "sk": "PARENT"},
            UpdateExpression="ADD cv_count :inc",
            ExpressionAttributeValues={":inc": by},
            ReturnValues="UPDATED_NEW",
        )
        return int(resp["Attributes"]["cv_count"])

    def get_parent(self, request_id: str) -> Optional[Dict[str, Any]]:
        """
        Fetch parent item (returns dict or None).
        """
        resp = self.table.get_item(Key={"pk": f"TRACEREQ#{request_id}", "sk": "PARENT"})
        return resp.get("Item")

    # ---------- Child API ----------

    def add_child_generation(
        self,
        *,
        request_id: str,
        file_path: str,
        bucket: str,
        resume_prefix: str,
        output_key: str,
        llm_model: Optional[str] = None,
    ) -> str:
        """
        Write a child item representing a single successful CV generation.
        Returns the 'child_id' (UUID) used in the SK.
        """
        child_id = str(uuid.uuid4())
        item = {
            "pk": f"TRACEREQ#{request_id}",
            "sk": f"CHILD#{child_id}",
            "file_path": file_path,
            "bucket": bucket,
            "resume_prefix": resume_prefix,
            "output_key": output_key,
            "llm_model": llm_model or "unknown",
            "created_at": _iso_now(),
        }
        self.table.put_item(Item=item)
        return child_id