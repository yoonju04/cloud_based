"""DynamoDB-shaped conditional store, with memory and file backends.

The control plane depends on this protocol, not on boto3. A later adapter
could map the methods onto DynamoDB as follows:

- ``put_item`` + ``attribute_not_exists`` -> PutItem with
  ``ConditionExpression attribute_not_exists(#key)``
- ``update_item`` + ``equals`` on ``version`` -> UpdateItem with
  ``ConditionExpression version = :expected``
- ``ConditionFailed`` -> ``ConditionalCheckFailedException``

No AWS credentials are read. SQS is at-least-once; callers still have to
pass an idempotency key, because this store does not remove duplicate
delivery by itself. It only makes the conditional write and the key check
possible.
"""

from __future__ import annotations

import copy
import fcntl
import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

TABLE_KEYS = {
    "jobs": ("job_id",),
    "idempotency": ("idempotency_key",),
}


class ConditionFailed(Exception):
    """The conditional write lost. ``item`` is the current row, if any."""

    def __init__(self, item: dict[str, Any] | None) -> None:
        super().__init__("conditional write rejected")
        self.item = item


@dataclass(frozen=True)
class Condition:
    attribute_not_exists: tuple[str, ...] = ()
    equals: tuple[tuple[str, Any], ...] = ()
    greater_than: tuple[tuple[str, float], ...] = ()


def _pk(table: str, key_or_item: dict[str, Any]) -> str:
    names = TABLE_KEYS[table]
    return "|".join(str(key_or_item[name]) for name in names)


def _condition_ok(current: dict[str, Any] | None, condition: Condition | None) -> bool:
    if condition is None:
        return True
    for name in condition.attribute_not_exists:
        if current is not None and name in current:
            return False
    if current is None:
        return not condition.equals and not condition.greater_than
    for name, expected in condition.equals:
        if current.get(name) != expected:
            return False
    for name, bound in condition.greater_than:
        value = current.get(name)
        if value is None or float(value) <= float(bound):
            return False
    return True


def _get(data: dict, table: str, key: dict) -> dict | None:
    item = data.setdefault(table, {}).get(_pk(table, key))
    return copy.deepcopy(item) if item is not None else None


def _put(data: dict, table: str, item: dict, condition: Condition | None) -> None:
    bucket = data.setdefault(table, {})
    pk = _pk(table, item)
    current = bucket.get(pk)
    if not _condition_ok(current, condition):
        raise ConditionFailed(copy.deepcopy(current) if current is not None else None)
    bucket[pk] = copy.deepcopy(item)


def _update(data: dict, table: str, key: dict, changes: dict, condition: Condition | None) -> dict:
    bucket = data.setdefault(table, {})
    pk = _pk(table, key)
    current = bucket.get(pk)
    if current is None or not _condition_ok(current, condition):
        raise ConditionFailed(copy.deepcopy(current) if current is not None else None)
    updated = copy.deepcopy(current)
    updated.update(copy.deepcopy(changes))
    bucket[pk] = updated
    return copy.deepcopy(updated)


def _scan(data: dict, table: str) -> list[dict]:
    return [copy.deepcopy(item) for item in data.get(table, {}).values()]


class DynamoShape(Protocol):
    def get_item(self, table: str, key: dict) -> dict | None: ...

    def put_item(self, table: str, item: dict, condition: Condition | None = None) -> None: ...

    def update_item(
        self,
        table: str,
        key: dict,
        changes: dict,
        condition: Condition | None = None,
    ) -> dict: ...

    def scan(self, table: str) -> list[dict]: ...


class MemoryStore:
    """Process-local backend. Conditional updates are serialized by a lock."""

    def __init__(self) -> None:
        self._data: dict[str, dict] = {}
        self._lock = threading.Lock()

    def get_item(self, table: str, key: dict) -> dict | None:
        with self._lock:
            return _get(self._data, table, key)

    def put_item(self, table: str, item: dict, condition: Condition | None = None) -> None:
        with self._lock:
            _put(self._data, table, item, condition)

    def update_item(self, table: str, key: dict, changes: dict, condition: Condition | None = None) -> dict:
        with self._lock:
            return _update(self._data, table, key, changes, condition)

    def scan(self, table: str) -> list[dict]:
        with self._lock:
            return _scan(self._data, table)


class FileStore:
    """One JSON document, updated under an exclusive file lock.

    The lock makes a read-modify-write of a single operation atomic across
    threads and local processes. It is the stand-in for a DynamoDB
    conditional write, not a multi-region database.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._thread_lock = threading.Lock()

    def get_item(self, table: str, key: dict) -> dict | None:
        return self._transact(lambda data: _get(data, table, key))

    def put_item(self, table: str, item: dict, condition: Condition | None = None) -> None:
        def run(data: dict) -> None:
            _put(data, table, item, condition)

        self._transact(run)

    def update_item(self, table: str, key: dict, changes: dict, condition: Condition | None = None) -> dict:
        return self._transact(lambda data: _update(data, table, key, changes, condition))

    def scan(self, table: str) -> list[dict]:
        return self._transact(lambda data: _scan(data, table))

    def _transact(self, fn):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        with self._thread_lock:
            with open(lock_path, "a+", encoding="utf-8") as lock:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
                try:
                    data = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
                    result = fn(data)
                    temporary = self.path.with_suffix(self.path.suffix + ".tmp")
                    temporary.write_text(
                        json.dumps(data, sort_keys=True, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    os.replace(temporary, self.path)
                    return result
                finally:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
