#  Copyright (c) 2026 Cisco Systems, Inc. and its affiliates
#  SPDX-License-Identifier: Apache-2.0
import json
import time
from abc import ABCMeta, abstractmethod
from http.client import IncompleteRead
from pathlib import Path
from typing import Any, Iterable, List, Optional, Union

import boto3
from botocore.exceptions import ClientError, ResponseStreamingError
from urllib3.exceptions import ProtocolError


class AbstractDataStore(metaclass=ABCMeta):
    @abstractmethod
    def load_content_from_path(self, fpath: Union[str, Path]) -> str:
        """Load text content from a path/key."""

    def load_bytes_content_from_path(self, fpath: Union[str, Path]) -> bytes:
        """Load bytes content from a path/key."""

    @abstractmethod
    def write_content(
        self, fpath: Union[str, Path], content: Union[str, bytes]
    ) -> None:
        """Write content to a path/key."""

    @abstractmethod
    def list_files(self, prefix: str, suffix: Optional[str] = None) -> List[str]:
        """List all keys under prefix, optionally filtered by suffix."""

    @abstractmethod
    def path_exists(self, fpath: Union[str, Path]) -> bool:
        """Return True if the key/path exists."""

    @abstractmethod
    def delete_files(self, file_paths: Iterable[Union[str, Path]]) -> None:
        """Delete all given paths/keys."""

    def write_jsonl_records(self, fpath: Union[str, Path], records: List[dict]) -> None:
        content = "\n".join(json.dumps(record) for record in records)
        self.write_content(fpath=fpath, content=content)


class LocalDataStore(AbstractDataStore):
    """Filesystem-backed data store for local development and tests."""

    def __init__(self, root: Union[str, Path]):
        self.root = Path(root)

    def _full_path(self, fpath: Union[str, Path]) -> Path:
        return self.root / Path(fpath)

    def load_content_from_path(self, fpath: Union[str, Path]) -> str:
        return self._full_path(fpath).read_text()

    def load_bytes_content_from_path(self, fpath: Union[str, Path]) -> bytes:
        return self._full_path(fpath).read_bytes()

    def write_content(
        self, fpath: Union[str, Path], content: Union[str, bytes]
    ) -> None:
        full_path = self._full_path(fpath)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            full_path.write_bytes(content)
        else:
            full_path.write_text(content)

    def path_exists(self, fpath: Union[str, Path]) -> bool:
        return self._full_path(fpath).exists()

    def list_files(self, prefix: str, suffix: Optional[str] = None) -> List[str]:
        base = self.root / prefix
        if not base.exists():
            return []
        result = []
        for p in base.rglob("*"):
            if p.is_file():
                rel = str(p.relative_to(self.root))
                if suffix is None or rel.endswith(suffix):
                    result.append(rel)
        return sorted(result)

    def delete_files(self, file_paths: Iterable[Union[str, Path]]) -> None:
        for fp in file_paths:
            self._full_path(fp).unlink(missing_ok=True)


class Boto3DataStore(AbstractDataStore):
    """MinIO/AWS S3 backed data store."""

    _READ_RETRY_ATTEMPTS = 3
    _READ_RETRY_BASE_DELAY_SECONDS = 0.25

    def __init__(
        self,
        bucket_name: str,
        user: str,
        password: str,
        endpoint: Optional[str] = None,
    ):
        self.bucket_name = bucket_name
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=user,
            aws_secret_access_key=password,
        )
        self._ensure_bucket()

    def _read_object_bytes(self, key: str) -> bytes:
        last_error: Optional[Exception] = None
        for attempt in range(1, self._READ_RETRY_ATTEMPTS + 1):
            try:
                response = self._client.get_object(Bucket=self.bucket_name, Key=key)
                with response["Body"] as stream:
                    return stream.read()
            except (IncompleteRead, ProtocolError, ResponseStreamingError) as exc:
                last_error = exc
                if attempt >= self._READ_RETRY_ATTEMPTS:
                    break
                time.sleep(self._READ_RETRY_BASE_DELAY_SECONDS * attempt)

        if last_error is not None:
            raise last_error
        raise RuntimeError(
            f"Failed to read key '{key}' from bucket '{self.bucket_name}'"
        )

    def load_content_from_path(self, fpath: Union[str, Path]) -> str:
        key = str(Path(fpath))
        return self._read_object_bytes(key).decode()

    def load_bytes_content_from_path(self, fpath: Union[str, Path]) -> bytes:
        key = str(Path(fpath))
        return self._read_object_bytes(key)

    def write_content(
        self, fpath: Union[str, Path], content: Union[str, bytes]
    ) -> None:
        key = str(Path(fpath))
        if isinstance(content, str):
            content = content.encode()
        self._client.put_object(Bucket=self.bucket_name, Key=key, Body=content)

    def path_exists(self, fpath: Union[str, Path]) -> bool:
        key = str(Path(fpath))
        res = self._client.list_objects_v2(
            Bucket=self.bucket_name, Prefix=key, MaxKeys=1
        )
        return "Contents" in res

    def list_files(self, prefix: str, suffix: Optional[str] = None) -> List[str]:
        paginator = self._client.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=self.bucket_name, Prefix=prefix)
        result = []
        for page in pages:
            if "Contents" in page:
                for obj in page["Contents"]:
                    key = obj["Key"]
                    if suffix is None or key.endswith(suffix):
                        result.append(key)
        return result

    def delete_files(self, file_paths: Iterable[Union[str, Path]]) -> None:
        paths = list(file_paths)
        for chunk in self._chunk(paths, 1000):
            delete_keys = [{"Key": str(Path(p))} for p in chunk]
            self._client.delete_objects(
                Bucket=self.bucket_name, Delete={"Objects": delete_keys}
            )

    @staticmethod
    def _chunk(lst: List[Any], size: int) -> Iterable[List[Any]]:
        for i in range(0, len(lst), size):
            yield lst[i : i + size]

    def _ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self.bucket_name)
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                self._client.create_bucket(Bucket=self.bucket_name)
            else:
                raise
