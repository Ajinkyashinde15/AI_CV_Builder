from __future__ import annotations
import os
import boto3
from botocore.config import Config
from ..config import settings

_session = None


def s3_client():
    global _session
    if _session is None:
        _session = boto3.session.Session(region_name=settings.AWS_REGION)
    params = {"config": Config(retries={"max_attempts": 3, "mode": "standard"})}
    endpoint = settings.AWS_ENDPOINT_URL
    if endpoint:
        params["endpoint_url"] = endpoint
    return _session.client("s3", **params)


def ensure_bucket(bucket: str):
    client = s3_client()
    # For LocalStack, CreateBucket works without LocationConstraint; for AWS, include it if region != us-east-1
    if settings.AWS_REGION == "us-east-1":
        client.create_bucket(Bucket=bucket)
    else:
        client.create_bucket(
            Bucket=bucket,
            CreateBucketConfiguration={"LocationConstraint": settings.AWS_REGION},
        )


def list_keys(bucket: str, prefix: str) -> list[str]:
    client = s3_client()
    keys: list[str] = []
    continuation = None
    while True:
        kwargs = {"Bucket": bucket, "Prefix": prefix}
        if continuation:
            kwargs["ContinuationToken"] = continuation
        resp = client.list_objects_v2(**kwargs)
        for obj in resp.get("Contents", []) :
            key = obj["Key"]
            if key.endswith("/"):
                continue
            keys.append(key)
        if resp.get("IsTruncated"):
            continuation = resp.get("NextContinuationToken")
        else:
            break
    return keys


def get_object_to_path(bucket: str, key: str, dest_path: str):
    client = s3_client()
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    client.download_file(bucket, key, dest_path)

def put_file(bucket: str, key: str, src_path: str, content_type: str | None = None):
    client = s3_client()
    extra = {"ContentType": content_type} if content_type else None
    client.upload_file(src_path, bucket, key, ExtraArgs=extra or {})
