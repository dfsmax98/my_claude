"""单机平台的原子JSON状态库与向量文件存储。"""
from __future__ import annotations

import copy
import json
import os
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable

import numpy as np


STATE_SCHEMA_VERSION = 1
SAFE_NAME = re.compile(r"^[a-zA-Z0-9_.-]+$")


def now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:24]}"


def empty_state() -> dict:
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "jobs": {},
        "recordings": {},
        "customers": {},
        "customer_templates": {},
        "black_actors": {},
        "black_templates": {},
        "verifications": {},
        "cluster_runs": {},
        "review_tasks": {},
        "users": {},
        "access_policies": {},
        "release_announcements": {},
        "platform_settings": {},
        "audit_events": [],
    }


class JsonStateStore:
    """面向单进程写入、并发读取的可恢复本地状态库。"""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.state_path = self.root / "platform_state.json"
        self.vector_root = self.root / "vectors"
        self.artifact_root = self.root / "artifacts"
        self.upload_root = self.root / "uploads"
        for directory in (self.vector_root, self.artifact_root, self.upload_root):
            directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._state = self._load()
        self.recover_incomplete_jobs()

    def _load(self) -> dict:
        if not self.state_path.exists():
            state = empty_state()
            self._write(state)
            return state
        state = json.loads(self.state_path.read_text(encoding="utf-8"))
        if int(state.get("schema_version", 0)) != STATE_SCHEMA_VERSION:
            raise RuntimeError("不支持的平台状态库版本")
        defaults = empty_state()
        for key, value in defaults.items():
            state.setdefault(key, value)
        return state

    def _write(self, state: dict) -> None:
        temp = self.state_path.with_suffix(".json.tmp")
        temp.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(temp, self.state_path)

    def snapshot(self) -> dict:
        with self._lock:
            return copy.deepcopy(self._state)

    def mutate(self, callback: Callable[[dict], object]) -> object:
        with self._lock:
            result = callback(self._state)
            self._write(self._state)
            return copy.deepcopy(result)

    def get(self, section: str, item_id: str) -> dict | None:
        with self._lock:
            item = self._state[section].get(item_id)
            return copy.deepcopy(item) if item is not None else None

    def list(self, section: str) -> list[dict]:
        with self._lock:
            rows = list(self._state[section].values())
            rows.sort(key=lambda row: row.get("created_at", ""), reverse=True)
            return copy.deepcopy(rows)

    def put(self, section: str, item_id: str, payload: dict) -> dict:
        def update(state: dict) -> dict:
            state[section][item_id] = copy.deepcopy(payload)
            return state[section][item_id]

        return self.mutate(update)

    def patch(self, section: str, item_id: str, **changes: object) -> dict:
        def update(state: dict) -> dict:
            if item_id not in state[section]:
                raise KeyError(f"{section}不存在: {item_id}")
            state[section][item_id].update(copy.deepcopy(changes))
            state[section][item_id]["updated_at"] = now_text()
            return state[section][item_id]

        return self.mutate(update)

    def create_job(self, kind: str, payload: dict) -> dict:
        job_id = new_id("job")
        created = now_text()
        job = {
            "id": job_id,
            "kind": kind,
            "status": "queued",
            "stage": "received",
            "progress": 0,
            "payload": copy.deepcopy(payload),
            "result_id": None,
            "error": None,
            "created_at": created,
            "updated_at": created,
        }
        return self.put("jobs", job_id, job)

    def claim_next_job(self) -> dict | None:
        def claim(state: dict) -> dict | None:
            queued = [row for row in state["jobs"].values() if row["status"] == "queued"]
            if not queued:
                return None
            job = min(queued, key=lambda row: row["created_at"])
            job.update(
                status="processing",
                stage="validating",
                progress=5,
                updated_at=now_text(),
            )
            return job

        return self.mutate(claim)

    def recover_incomplete_jobs(self) -> None:
        def recover(state: dict) -> None:
            changed = False
            for job in state["jobs"].values():
                if job.get("status") == "processing":
                    job.update(
                        status="queued",
                        stage="recovered",
                        progress=0,
                        updated_at=now_text(),
                    )
                    changed = True
            return changed

        self.mutate(recover)

    def add_review(self, kind: str, target_id: str, reason: str, priority="P1") -> dict:
        review_id = new_id("review")
        created = now_text()
        review = {
            "id": review_id,
            "kind": kind,
            "target_id": target_id,
            "reason": reason,
            "priority": priority,
            "status": "pending",
            "created_at": created,
            "updated_at": created,
        }
        return self.put("review_tasks", review_id, review)

    def append_audit(self, action: str, target_id: str, detail: dict | None = None) -> None:
        event = {
            "id": new_id("audit"),
            "action": action,
            "target_id": target_id,
            "detail": detail or {},
            "created_at": now_text(),
        }

        def append(state: dict) -> None:
            state["audit_events"].append(event)
            state["audit_events"] = state["audit_events"][-5000:]

        self.mutate(append)

    def _safe_child(self, root: Path, *parts: str) -> Path:
        if not all(SAFE_NAME.fullmatch(part) for part in parts):
            raise ValueError("非法存储名称")
        path = root.joinpath(*parts).resolve()
        path.relative_to(root)
        return path

    def save_vector(self, namespace: str, vector_id: str, vector: np.ndarray) -> str:
        directory = self._safe_child(self.vector_root, namespace)
        directory.mkdir(parents=True, exist_ok=True)
        path = self._safe_child(directory, f"{vector_id}.npy")
        temp = path.with_name(f"{path.stem}.tmp.npy")
        np.save(temp, np.asarray(vector, dtype=np.float32))
        os.replace(temp, path)
        return str(path.relative_to(self.root).as_posix())

    def load_vector(self, relative_path: str) -> np.ndarray:
        path = (self.root / relative_path).resolve()
        path.relative_to(self.vector_root)
        return np.load(path, allow_pickle=False).astype(np.float32)

    def save_artifact(self, namespace: str, artifact_id: str, payload: dict) -> str:
        directory = self._safe_child(self.artifact_root, namespace)
        directory.mkdir(parents=True, exist_ok=True)
        path = self._safe_child(directory, f"{artifact_id}.json")
        temp = path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, path)
        return str(path.relative_to(self.root).as_posix())

    def read_artifact(self, relative_path: str) -> dict:
        path = (self.root / relative_path).resolve()
        path.relative_to(self.artifact_root)
        return json.loads(path.read_text(encoding="utf-8"))

    def delete_artifact(self, relative_path: str) -> None:
        path = (self.root / relative_path).resolve()
        path.relative_to(self.artifact_root)
        path.unlink(missing_ok=True)

    def delete_vector(self, relative_path: str) -> None:
        path = (self.root / relative_path).resolve()
        path.relative_to(self.vector_root)
        path.unlink(missing_ok=True)
