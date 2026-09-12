"""Object storage behind one interface (contract §2). LocalStorage writes under api/storage/ and is served
at /media/<key> by main.py; keys under `private/` need a signature. S3Storage when S3_* env vars are set."""
from __future__ import annotations

import hashlib
import hmac
import mimetypes
import os
import time
from pathlib import Path

SECRET = os.environ.get("PIXIE_SECRET") or "dev-secret-change-me"
HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL_DIR = os.environ.get("PIXIE_STORAGE_DIR", os.path.join(HERE, "storage"))
PUBLIC_URL = (os.environ.get("PIXIE_PUBLIC_URL") or "").rstrip("/")  # "" → relative /media URLs


def _sig(key: str, exp: int) -> str:
    return hmac.new(SECRET.encode(), f"{key}.{exp}".encode(), hashlib.sha256).hexdigest()[:24]


class Storage:
    kind = "abstract"

    def put(self, key: str, data: bytes, content_type: str | None = None) -> str:
        raise NotImplementedError

    def get(self, key: str) -> bytes | None:
        raise NotImplementedError

    def exists(self, key: str) -> bool:
        return self.get(key) is not None

    def url(self, key: str, private: bool = False, ttl: int = 3600) -> str:
        raise NotImplementedError

    def verify(self, key: str, sig: str | None, exp: str | None) -> bool:
        if not key.startswith("private/"):
            return True
        try:
            e = int(exp or 0)
        except ValueError:
            return False
        return e >= time.time() and bool(sig) and hmac.compare_digest(sig, _sig(key, e))


class LocalStorage(Storage):
    kind = "local"

    def __init__(self, base_dir: str = LOCAL_DIR):
        self.base = Path(base_dir)
        self.base.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.base / key).resolve()
        if self.base.resolve() not in p.parents:
            raise ValueError("bad key")
        return p

    def put(self, key: str, data: bytes, content_type: str | None = None) -> str:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return key

    def get(self, key: str) -> bytes | None:
        try:
            p = self._path(key)
        except ValueError:
            return None
        return p.read_bytes() if p.is_file() else None

    def url(self, key: str, private: bool = False, ttl: int = 3600) -> str:
        u = f"{PUBLIC_URL}/media/{key}"
        if private or key.startswith("private/"):
            exp = int(time.time()) + ttl
            u += f"?sig={_sig(key, exp)}&exp={exp}"
        return u


class S3Storage(Storage):
    kind = "s3"

    def __init__(self):
        import boto3

        self.bucket = os.environ["S3_BUCKET"]
        self.client = boto3.client(
            "s3", endpoint_url=os.environ.get("S3_ENDPOINT"), aws_access_key_id=os.environ.get("S3_KEY"),
            aws_secret_access_key=os.environ.get("S3_SECRET"), region_name=os.environ.get("S3_REGION", "auto"),
        )
        self.cdn = (os.environ.get("S3_PUBLIC_URL") or "").rstrip("/")

    def put(self, key: str, data: bytes, content_type: str | None = None) -> str:
        ct = content_type or mimetypes.guess_type(key)[0] or "application/octet-stream"
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=ct)
        return key

    def get(self, key: str) -> bytes | None:
        try:
            return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except Exception:
            return None

    def url(self, key: str, private: bool = False, ttl: int = 3600) -> str:
        if private or key.startswith("private/") or not self.cdn:
            return self.client.generate_presigned_url("get_object", Params={"Bucket": self.bucket, "Key": key}, ExpiresIn=ttl)
        return f"{self.cdn}/{key}"


def open_storage() -> Storage:
    if os.environ.get("S3_BUCKET"):
        try:
            s = S3Storage()
            print("[storage] S3 storage ready")
            return s
        except Exception as e:
            print(f"[storage] S3 unavailable ({e}); using local storage")
    return LocalStorage()


def content_type_for(key: str) -> str:
    return mimetypes.guess_type(key)[0] or "application/octet-stream"
