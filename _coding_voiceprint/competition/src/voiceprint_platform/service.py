"""声纹平台任务编排、声纹库和审核服务。"""
from __future__ import annotations

import hashlib
import hmac
import io
import os
import pickle
import secrets
import shutil
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from .backend import VoiceprintBackend
from .clustering import run_customer_clustering
from .config import load_platform_config
from .processing import AudioPipeline
from .store import JsonStateStore, new_id, now_text


PERMISSION_KEYS = [
    "view_customer_key",
    "view_audio",
    "view_transcript",
    "view_embedding_metadata",
    "manage_users",
    "manage_permissions",
    "manage_releases",
    "view_monitoring",
    "trigger_cluster",
]


def identity_id(value: str, prefix: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError("业务主键不能为空")
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:24]}"


def _b64_decode(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    import base64

    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _b64_encode(value: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def hash_password(password: str, *, salt: bytes | None = None, iterations: int = 260000) -> str:
    salt = salt or os.urandom(18)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${_b64_encode(salt)}${_b64_encode(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt, digest = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        expected = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), _b64_decode(salt), int(iterations)
        )
        return hmac.compare_digest(_b64_encode(expected), digest)
    except (ValueError, TypeError):
        return False


class VoiceprintPlatformService:
    def __init__(
        self,
        config: dict | None = None,
        *,
        start_worker: bool = True,
        pipeline: AudioPipeline | None = None,
        backend: VoiceprintBackend | None = None,
    ):
        self.config = config or load_platform_config()
        self.store = JsonStateStore(self.config["storage_path"])
        self.pipeline = pipeline or AudioPipeline(self.config)
        self.backend = backend or VoiceprintBackend(self.config)
        self._stop = threading.Event()
        self._worker = None
        self._sessions: dict[str, dict] = {}
        self._bootstrap_governance()
        self.bootstrap_black_library()
        if start_worker:
            self._worker = threading.Thread(
                target=self._worker_loop,
                name="voiceprint-worker",
                daemon=True,
            )
            self._worker.start()

    def close(self) -> None:
        self._stop.set()
        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=3)

    def _bootstrap_governance(self) -> None:
        security = self.config.get("security", {})
        admin = security.get("default_admin", {})
        username = str(admin.get("username") or "admin").strip()
        if username and not self.store.get("users", username):
            password_hash = admin.get("password_hash")
            if not password_hash and admin.get("password"):
                password_hash = hash_password(str(admin["password"]))
            if not password_hash:
                raise RuntimeError(
                    "首次启动必须设置VOICEPRINT_ADMIN_PASSWORD_HASH或VOICEPRINT_ADMIN_PASSWORD"
                )
            created = now_text()
            self.store.put(
                "users",
                username,
                {
                    "username": username,
                    "display_name": admin.get("display_name") or username,
                    "role": "admin",
                    "status": "active",
                    "password_hash": password_hash,
                    "created_at": created,
                    "updated_at": created,
                },
            )
        if not self.store.get("access_policies", "default"):
            policy = {
                "id": "default",
                "roles": self.config.get("governance", {}).get("default_permissions", {}),
                "updated_by": "system",
                "created_at": now_text(),
                "updated_at": now_text(),
            }
            self.store.put("access_policies", "default", policy)
        if not self.store.get("platform_settings", "governance"):
            governance = self.config.get("governance", {})
            settings = {
                "id": "governance",
                "single_instance": bool(governance.get("single_instance", True)),
                "thresholds_frozen": bool(governance.get("thresholds_frozen", True)),
                "customer_active_template_limit": int(
                    governance.get("customer_active_template_limit", 3)
                ),
                "review_policy": governance.get("review_policy", {}),
                "created_at": now_text(),
                "updated_at": now_text(),
            }
            self.store.put("platform_settings", "governance", settings)
        if not self.store.list("release_announcements"):
            release = self.config.get("release", {})
            announcement = {
                "id": new_id("release"),
                "version": release.get("current_version", "voiceprint-platform-v1"),
                "title": "初始测试版本",
                "body": release.get("announcement", "平台初始版本。"),
                "status": "published",
                "created_by": "system",
                "created_at": now_text(),
                "updated_at": now_text(),
            }
            self.store.put("release_announcements", announcement["id"], announcement)

    def _public_user(self, user: dict) -> dict:
        return {key: value for key, value in user.items() if key != "password_hash"}

    def _policy(self) -> dict:
        return self.store.get("access_policies", "default") or {"roles": {}}

    def permissions_for(self, username: str | None) -> dict:
        if not username:
            return {}
        user = self.store.get("users", username)
        if not user or user.get("status") != "active":
            return {}
        role = user.get("role", "viewer")
        policy = self._policy()
        return {key: bool(policy.get("roles", {}).get(role, {}).get(key)) for key in PERMISSION_KEYS}

    def authenticate(self, username: str, password: str) -> dict:
        user = self.store.get("users", str(username).strip())
        if not user or user.get("status") != "active":
            raise ValueError("账号或密码错误")
        if not verify_password(password, user.get("password_hash", "")):
            raise ValueError("账号或密码错误")
        token = secrets.token_urlsafe(32)
        expires = datetime.now().astimezone() + timedelta(
            hours=float(self.config.get("security", {}).get("session_hours", 8))
        )
        self._sessions[token] = {"username": user["username"], "expires_at": expires}
        self.store.patch("users", user["username"], last_login_at=now_text())
        self.store.append_audit("login", user["username"])
        public_user = self._public_user(self.store.get("users", user["username"]))
        permissions = self.permissions_for(user["username"])
        return {
            "token": token,
            "expires_at": expires.isoformat(timespec="seconds"),
            "user": public_user | {"permissions": permissions},
            "permissions": permissions,
        }

    def logout(self, token: str | None) -> None:
        if token:
            self._sessions.pop(token, None)

    def current_user(self, token: str | None) -> dict | None:
        session = self._sessions.get(token or "")
        if not session:
            return None
        if datetime.now().astimezone() > session["expires_at"]:
            self._sessions.pop(token or "", None)
            return None
        user = self.store.get("users", session["username"])
        if not user or user.get("status") != "active":
            return None
        return self._public_user(user) | {"permissions": self.permissions_for(user["username"])}

    def require_permission(self, username: str | None, permission: str) -> None:
        if not self.permissions_for(username).get(permission):
            raise PermissionError(f"缺少权限: {permission}")

    def list_users(self) -> list[dict]:
        return [self._public_user(row) for row in self.store.list("users")]

    def save_user(self, payload: dict, operator: str) -> dict:
        username = str(payload.get("username", "")).strip()
        if not username:
            raise ValueError("用户名不能为空")
        role = str(payload.get("role") or "viewer")
        if role not in {"admin", "operator", "viewer"}:
            raise ValueError("角色必须为admin、operator或viewer")
        current = self.store.get("users", username)
        password = str(payload.get("password") or "")
        changes = {
            "username": username,
            "display_name": str(payload.get("display_name") or username),
            "role": role,
            "status": str(payload.get("status") or "active"),
        }
        if password:
            changes["password_hash"] = hash_password(password)
        elif not current:
            raise ValueError("新建账号必须设置密码")
        if current:
            user = self.store.patch("users", username, **changes)
        else:
            created = now_text()
            user = {**changes, "created_at": created, "updated_at": created}
            self.store.put("users", username, user)
        self.store.append_audit("user_saved", username, {"operator": operator})
        return self._public_user(user)

    def get_access_policy(self) -> dict:
        return self._policy()

    def update_access_policy(self, payload: dict, operator: str) -> dict:
        roles = payload.get("roles")
        if not isinstance(roles, dict):
            raise ValueError("roles必须为对象")
        cleaned = {}
        for role in ("admin", "operator", "viewer"):
            values = roles.get(role, {})
            cleaned[role] = {key: bool(values.get(key)) for key in PERMISSION_KEYS}
        policy = self.store.patch(
            "access_policies", "default", roles=cleaned, updated_by=operator
        )
        self.store.append_audit("access_policy_updated", "default", {"operator": operator})
        return policy

    def governance_settings(self) -> dict:
        return self.store.get("platform_settings", "governance")

    def update_governance_settings(self, payload: dict, operator: str) -> dict:
        current = self.governance_settings()
        limit = int(payload.get("customer_active_template_limit", current["customer_active_template_limit"]))
        if limit < 1 or limit > 10:
            raise ValueError("客户活动模板上限必须在1到10之间")
        settings = self.store.patch(
            "platform_settings",
            "governance",
            customer_active_template_limit=limit,
            thresholds_frozen=bool(payload.get("thresholds_frozen", current["thresholds_frozen"])),
            single_instance=True,
        )
        self.store.append_audit("governance_settings_updated", "governance", {"operator": operator})
        return settings

    def list_releases(self) -> list[dict]:
        return self.store.list("release_announcements")

    def create_release(self, payload: dict, operator: str) -> dict:
        version = str(payload.get("version", "")).strip()
        title = str(payload.get("title", "")).strip()
        body = str(payload.get("body", "")).strip()
        if not version or not title or not body:
            raise ValueError("版本号、标题和公告内容不能为空")
        release_id = new_id("release")
        release = {
            "id": release_id,
            "version": version,
            "title": title,
            "body": body,
            "status": str(payload.get("status") or "published"),
            "created_by": operator,
            "created_at": now_text(),
            "updated_at": now_text(),
        }
        self.store.put("release_announcements", release_id, release)
        self.store.append_audit("release_created", release_id, {"operator": operator})
        return release

    def _save_upload(self, stream, filename: str) -> tuple[str, str, int]:
        suffix = Path(filename or "audio.bin").suffix.lower()
        if suffix not in set(self.config["audio"]["allowed_extensions"]):
            raise ValueError(f"不支持的音频格式: {suffix}")
        digest = hashlib.sha256()
        temp = self.store.upload_root / f"upload_{new_id('tmp')}.part"
        total = 0
        limit = int(self.config["audio"]["max_upload_bytes"])
        try:
            with temp.open("wb") as handle:
                while True:
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > limit:
                        raise ValueError("录音超过上传大小限制")
                    digest.update(chunk)
                    handle.write(chunk)
        except Exception:
            temp.unlink(missing_ok=True)
            raise
        if total == 0:
            temp.unlink(missing_ok=True)
            raise ValueError("录音文件为空")
        audio_hash = digest.hexdigest()
        final = self.store.upload_root / f"audio_{audio_hash[:24]}{suffix}"
        if final.exists():
            temp.unlink(missing_ok=True)
        else:
            temp.replace(final)
        return str(final.relative_to(self.store.root).as_posix()), audio_hash, total

    def submit_recording(self, stream, filename: str, customer_key: str) -> dict:
        customer_key = str(customer_key).strip()
        customer_id = identity_id(customer_key, "cust")
        upload_path, audio_hash, size = self._save_upload(stream, filename)
        recording_id = new_id("rec")
        created = now_text()
        recording = {
            "id": recording_id,
            "kind": "customer_verification",
            "customer_id": customer_id,
            "customer_key": customer_key,
            "cust_no": customer_key,
            "audio_sha256": audio_hash,
            "bytes": size,
            "status": "queued",
            "upload_path": upload_path,
            "transcript_path": None,
            "channel_paths": {},
            "role": None,
            "quality": None,
            "vector_path": None,
            "verification_id": None,
            "created_at": created,
            "updated_at": created,
        }
        self.store.put("recordings", recording_id, recording)
        job = self.store.create_job(
            "customer_verification",
            {"recording_id": recording_id, "customer_id": customer_id},
        )
        self.store.append_audit("recording_submitted", recording_id)
        return self._public_job(job)

    def submit_black_recording(
        self, stream, filename: str, actor_key: str, reviewer: str
    ) -> dict:
        actor_id = identity_id(actor_key, "black_actor")
        upload_path, audio_hash, size = self._save_upload(stream, filename)
        recording_id = new_id("black_rec")
        created = now_text()
        recording = {
            "id": recording_id,
            "kind": "black_enrollment",
            "actor_id": actor_id,
            "reviewer": str(reviewer).strip() or "未标识用户",
            "audio_sha256": audio_hash,
            "bytes": size,
            "status": "queued",
            "upload_path": upload_path,
            "transcript_path": None,
            "channel_paths": {},
            "role": None,
            "quality": None,
            "vector_path": None,
            "created_at": created,
            "updated_at": created,
        }
        self.store.put("recordings", recording_id, recording)
        job = self.store.create_job("black_enrollment", {"recording_id": recording_id})
        self.store.append_audit("black_recording_submitted", recording_id)
        return self._public_job(job)

    def _worker_loop(self) -> None:
        next_maintenance = 0.0
        while not self._stop.is_set():
            if time.monotonic() >= next_maintenance:
                self.purge_expired_transcripts()
                self.run_scheduled_cluster_if_due()
                next_maintenance = time.monotonic() + 60.0
            if not self.run_next_job():
                self._stop.wait(0.5)

    def run_next_job(self) -> bool:
        job = self.store.claim_next_job()
        if job is None:
            return False
        try:
            if job["kind"] == "customer_verification":
                result_id = self._process_customer_job(job)
            elif job["kind"] == "black_enrollment":
                result_id = self._process_black_job(job)
            else:
                raise ValueError(f"未知任务类型: {job['kind']}")
            self.store.patch(
                "jobs",
                job["id"],
                status="completed",
                stage="completed",
                progress=100,
                result_id=result_id,
            )
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            self.store.patch(
                "jobs", job["id"], status="failed", stage="failed", error=error
            )
            recording_id = job["payload"].get("recording_id")
            if recording_id and self.store.get("recordings", recording_id):
                self.store.patch("recordings", recording_id, status="failed", error=error)
                self.store.add_review("processing_failure", recording_id, error, "P0")
        return True

    def _job_stage(self, job_id: str, stage: str, progress: int) -> None:
        self.store.patch("jobs", job_id, stage=stage, progress=progress)

    def _process_audio(self, job: dict, recording: dict) -> tuple[dict, np.ndarray | None]:
        recording_id = recording["id"]
        audio_path = self.store.root / recording["upload_path"]
        channel_dir = self.store.artifact_root / "channels" / recording_id
        self._job_stage(job["id"], "split_and_asr", 25)
        result = self.pipeline.process(audio_path, channel_dir)
        role = result["role"]
        expires = datetime.now().astimezone() + timedelta(
            hours=int(self.config["audio"]["transcript_retention_hours"])
        )
        transcript_path = self.store.save_artifact(
            "transcripts",
            recording_id,
            {
                **result["transcript"],
                "expires_at": expires.isoformat(timespec="seconds"),
            },
        )
        channel_paths = {
            key: str(Path(path).resolve().relative_to(self.store.root).as_posix())
            for key, path in result["channels"].items()
        }
        self.store.patch(
            "recordings",
            recording_id,
            status="role_identified" if result["embedding"] is not None else "review_required",
            audio_info=result["audio_info"],
            role=role,
            transcript_path=transcript_path,
            channel_paths=channel_paths,
        )
        return result, result["embedding"]

    def _active_customer_templates(self, customer_id: str) -> list[dict]:
        return [
            row
            for row in self.store.list("customer_templates")
            if row["customer_id"] == customer_id and row["status"] == "active"
        ]

    def _active_black_templates(self) -> list[tuple[dict, np.ndarray]]:
        rows = []
        for template in self.store.list("black_templates"):
            if template["status"] == "active":
                rows.append((template, self.store.load_vector(template["vector_path"])))
        return rows

    def _ensure_customer(self, customer_id: str, customer_key: str | None = None) -> dict:
        current = self.store.get("customers", customer_id)
        if current:
            if customer_key and not current.get("customer_key"):
                return self.store.patch(
                    "customers",
                    customer_id,
                    customer_key=customer_key,
                    cust_no=customer_key,
                )
            return current
        created = now_text()
        customer = {
            "id": customer_id,
            "customer_key": customer_key,
            "cust_no": customer_key,
            "status": "pending_enrollment",
            "active_template_count": 0,
            "pending_template_count": 0,
            "created_at": created,
            "updated_at": created,
        }
        return self.store.put("customers", customer_id, customer)

    def _add_customer_template(
        self, customer_id: str, recording_id: str, vector: np.ndarray, status: str
    ) -> dict:
        customer = self.store.get("customers", customer_id) or {}
        template_id = new_id("cust_tpl")
        path = self.store.save_vector("customer", template_id, vector)
        created = now_text()
        template = {
            "id": template_id,
            "customer_id": customer_id,
            "customer_key": customer.get("customer_key") or customer.get("cust_no"),
            "cust_no": customer.get("cust_no") or customer.get("customer_key"),
            "recording_id": recording_id,
            "vector_path": path,
            "status": status,
            "model_version": self.config["models"]["embedding_model_version"],
            "created_at": created,
            "updated_at": created,
        }
        self.store.put("customer_templates", template_id, template)
        if status == "active":
            self._enforce_customer_template_limit(customer_id)
        self._refresh_customer_counts(customer_id)
        return template

    def _enforce_customer_template_limit(self, customer_id: str) -> None:
        settings = self.governance_settings() or {}
        limit = int(settings.get("customer_active_template_limit", 3))
        active = [
            row
            for row in self.store.list("customer_templates")
            if row["customer_id"] == customer_id and row["status"] == "active"
        ]
        active.sort(key=lambda row: row.get("created_at", ""))
        while len(active) > limit:
            oldest = active.pop(0)
            vector_path = oldest.get("vector_path")
            if vector_path:
                self.store.delete_vector(vector_path)
            self.store.patch(
                "customer_templates",
                oldest["id"],
                status="rolled_out",
                vector_path=None,
                rolled_out_reason=f"超过活动模板上限{limit}，滚动出库",
                rolled_out_at=now_text(),
            )
            self.store.append_audit(
                "customer_template_rolled_out",
                oldest["id"],
                {"customer_id": customer_id, "limit": limit},
            )

    def _refresh_customer_counts(self, customer_id: str) -> None:
        templates = [
            row
            for row in self.store.list("customer_templates")
            if row["customer_id"] == customer_id
        ]
        active = sum(row["status"] == "active" for row in templates)
        pending = sum(row["status"] == "pending" for row in templates)
        self.store.patch(
            "customers",
            customer_id,
            status="active" if active else "pending_enrollment",
            active_template_count=active,
            pending_template_count=pending,
        )

    def _process_customer_job(self, job: dict) -> str:
        recording_id = job["payload"]["recording_id"]
        customer_id = job["payload"]["customer_id"]
        recording = self.store.get("recordings", recording_id)
        result, vector = self._process_audio(job, recording)
        if vector is None:
            self.store.patch(
                "recordings",
                recording_id,
                status="failed",
                error=f"角色识别状态={result['role'].get('status')}，未生成客户embedding",
            )
            self.store.append_audit("customer_embedding_unavailable", recording_id)
            return recording_id

        self._job_stage(job["id"], "quality_and_verification", 65)
        vector_path = self.store.save_vector("query", recording_id, vector)
        quality = self.backend.quality_score(vector, result["role"])
        self.store.patch(
            "recordings", recording_id, status="verifying", vector_path=vector_path, quality=quality
        )
        customer = self._ensure_customer(customer_id, recording.get("customer_key"))
        templates = self._active_customer_templates(customer_id)
        template_vectors = [self.store.load_vector(row["vector_path"]) for row in templates]
        self_result = self.backend.self_check(vector, template_vectors, quality)
        if self_result.get("template_index") is not None:
            self_result["template_id"] = templates[self_result.pop("template_index")]["id"]
        else:
            self_result.pop("template_index", None)
        black_result = self.backend.black_search(vector, self._active_black_templates())

        labels = []
        if self_result["status"] == "not_self":
            labels.append("非本人")
        elif self_result["status"] == "review":
            labels.append("客户1:1灰区")
        elif self_result["status"] == "no_template":
            labels.append("首录建库")
        elif self_result["status"] == "quality_rejected":
            labels.append("质量未达标")
        if black_result["status"] == "suspected":
            labels.append("疑似黑产中介代办")
        elif black_result["status"] == "review":
            labels.append("黑产1:N灰区")

        verification_id = new_id("verify")
        verification = {
            "id": verification_id,
            "recording_id": recording_id,
            "customer_id": customer_id,
            "self_check": self_result,
            "black_search": black_result,
            "quality": quality,
            "labels": labels,
            "model_versions": self.backend.model_info(),
            "created_at": now_text(),
        }
        self.store.put("verifications", verification_id, verification)

        external_review = False
        if not templates:
            if quality["status"] == "accepted" and black_result["status"] == "clear":
                self._add_customer_template(customer_id, recording_id, vector, "active")
        elif self_result["status"] == "verified" and black_result["status"] == "clear":
            self._add_customer_template(customer_id, recording_id, vector, "active")
        if self_result["status"] == "review":
            external_review = True
            self.store.add_review(
                "self_check_gray_zone",
                verification_id,
                (
                    f"客户1:1分数{self_result.get('score')}落在"
                    f"{self_result.get('reject_below')}至"
                    f"{self_result.get('accept_at_or_above')}灰区"
                ),
                "P1",
            )
        if black_result["status"] == "review":
            external_review = True
            top_score = black_result.get("topk", [{}])[0].get("score") if black_result.get("topk") else None
            self.store.add_review(
                "black_search_gray_zone",
                verification_id,
                (
                    f"黑产1:N Top-1分数{top_score}落在"
                    f"{black_result.get('review_below')}至{black_result.get('threshold')}灰区"
                ),
                "P0",
            )

        self.store.patch(
            "recordings",
            recording_id,
            status="external_review" if external_review else "completed",
            verification_id=verification_id,
        )
        self.store.append_audit("verification_completed", verification_id, {"labels": labels})
        return verification_id

    def _process_black_job(self, job: dict) -> str:
        recording_id = job["payload"]["recording_id"]
        recording = self.store.get("recordings", recording_id)
        result, vector = self._process_audio(job, recording)
        if vector is None:
            self.store.patch(
                "recordings",
                recording_id,
                status="failed",
                error=f"角色识别状态={result['role'].get('status')}，未生成黑产embedding",
            )
            self.store.append_audit("black_embedding_unavailable", recording_id)
            return recording_id
        quality = self.backend.quality_score(vector, result["role"])
        actor_id = recording["actor_id"]
        actor = self.store.get("black_actors", actor_id)
        if not actor:
            actor = {
                "id": actor_id,
                "status": "pending",
                "active_template_count": 0,
                "created_at": now_text(),
                "updated_at": now_text(),
            }
            self.store.put("black_actors", actor_id, actor)
        template_id = new_id("black_tpl")
        vector_path = self.store.save_vector("black", template_id, vector)
        template = {
            "id": template_id,
            "actor_id": actor_id,
            "recording_id": recording_id,
            "vector_path": vector_path,
            "status": "active" if quality["status"] == "accepted" else "rejected",
            "quality": quality,
            "reviewer": recording["reviewer"],
            "created_at": now_text(),
            "updated_at": now_text(),
        }
        self.store.put("black_templates", template_id, template)
        self.store.patch(
            "recordings",
            recording_id,
            status="completed" if quality["status"] == "accepted" else "failed",
            quality=quality,
            vector_path=vector_path,
        )
        active_count = sum(
            row["actor_id"] == actor_id and row["status"] == "active"
            for row in self.store.list("black_templates")
        )
        self.store.patch(
            "black_actors",
            actor_id,
            status="active" if active_count else "pending",
            active_template_count=active_count,
        )
        self.store.append_audit("black_template_created", template_id)
        return template_id

    def decide_review(self, review_id: str, decision: str, reviewer: str) -> dict:
        if decision not in {"approve", "reject"}:
            raise ValueError("decision必须为approve或reject")
        review = self.store.get("review_tasks", review_id)
        if not review or review["status"] != "pending":
            raise KeyError("待复核任务不存在或已处理")
        target_id = review["target_id"]
        self.store.patch(
            "review_tasks",
            review_id,
            status="approved" if decision == "approve" else "rejected",
            reviewer=str(reviewer).strip() or "未标识用户",
            decided_at=now_text(),
            external_flow=True,
        )
        self.store.append_audit(
            f"external_review_{decision}",
            target_id,
            {"review_id": review_id, "kind": review["kind"]},
        )
        return self.store.get("review_tasks", review_id)

    def run_cluster(self) -> dict:
        run_id = new_id("cluster_run")
        result = run_customer_clustering(self.store, self.config)
        run = {
            "id": run_id,
            "status": "completed",
            **result,
            "created_at": now_text(),
        }
        self.store.put("cluster_runs", run_id, run)
        for cluster in result["clusters"]:
            self.store.add_review(
                "gang_cluster",
                f"{run_id}:{cluster['cluster_id']}",
                f"疑似团伙候选，成员数={cluster['member_count']}",
                "P1",
            )
        self.store.append_audit("cluster_run_completed", run_id)
        return run

    def run_scheduled_cluster_if_due(self) -> dict | None:
        if len(self.store.list("customers")) < int(
            self.config["gang_cluster"]["min_cluster_size"]
        ):
            return None
        runs = self.store.list("cluster_runs")
        if runs:
            last = datetime.fromisoformat(runs[0]["created_at"])
            interval = timedelta(hours=float(self.config["gang_cluster"]["interval_hours"]))
            if datetime.now().astimezone() - last < interval:
                return None
        return self.run_cluster()

    def purge_expired_transcripts(self) -> int:
        removed = 0
        now = datetime.now().astimezone()
        for recording in self.store.list("recordings"):
            relative = recording.get("transcript_path")
            if not relative:
                continue
            try:
                artifact = self.store.read_artifact(relative)
                expired = now > datetime.fromisoformat(artifact["expires_at"])
            except (FileNotFoundError, KeyError, ValueError):
                expired = True
            if expired:
                self.store.delete_artifact(relative)
                self.store.patch("recordings", recording["id"], transcript_path=None)
                removed += 1
        if removed:
            self.store.append_audit("expired_transcripts_purged", "transcripts", {"count": removed})
        return removed

    def bootstrap_black_library(self) -> int:
        if self.store.list("black_templates"):
            return 0
        path = Path(self.config["black_bootstrap_path"])
        if not path.exists():
            return 0
        with path.open("rb") as handle:
            database = pickle.load(handle)
        count = 0
        for source in database.get("records", []):
            actor_id = str(source.get("actor_id") or source.get("id"))
            if not self.store.get("black_actors", actor_id):
                self.store.put(
                    "black_actors",
                    actor_id,
                    {
                        "id": actor_id,
                        "status": "active",
                        "active_template_count": 0,
                        "created_at": now_text(),
                        "updated_at": now_text(),
                    },
                )
            template_id = f"bootstrap_{hashlib.sha256(str(source['id']).encode()).hexdigest()[:20]}"
            vector_path = self.store.save_vector("black", template_id, source["emb"])
            self.store.put(
                "black_templates",
                template_id,
                {
                    "id": template_id,
                    "actor_id": actor_id,
                    "recording_id": str(source["id"]),
                    "vector_path": vector_path,
                    "status": "active",
                    "quality": source.get("quality", "formal"),
                    "reviewer": source.get("reviewer", "历史审核"),
                    "created_at": source.get("added", now_text()),
                    "updated_at": now_text(),
                },
            )
            count += 1
        for actor in self.store.list("black_actors"):
            active_count = sum(
                row["actor_id"] == actor["id"] and row["status"] == "active"
                for row in self.store.list("black_templates")
            )
            self.store.patch("black_actors", actor["id"], active_template_count=active_count)
        if count:
            self.store.append_audit("black_library_bootstrapped", "black_library", {"count": count})
        return count

    def overview(self) -> dict:
        state = self.store.snapshot()
        jobs = list(state["jobs"].values())
        reviews = list(state["review_tasks"].values())
        settings = self.governance_settings()
        return {
            "jobs": {
                "total": len(jobs),
                "queued": sum(row["status"] == "queued" for row in jobs),
                "processing": sum(row["status"] == "processing" for row in jobs),
                "failed": sum(row["status"] == "failed" for row in jobs),
            },
            "recordings": len(state["recordings"]),
            "customers": len(state["customers"]),
            "active_customer_templates": sum(
                row["status"] == "active" for row in state["customer_templates"].values()
            ),
            "black_actors": sum(
                row["status"] == "active" for row in state["black_actors"].values()
            ),
            "black_templates": sum(
                row["status"] == "active" for row in state["black_templates"].values()
            ),
            "pending_reviews": sum(row["status"] == "pending" for row in reviews),
            "cluster_runs": len(state["cluster_runs"]),
            "models": self.backend.model_info(),
            "governance": {
                "single_instance": settings.get("single_instance", True),
                "thresholds_frozen": settings.get("thresholds_frozen", True),
                "customer_active_template_limit": settings.get(
                    "customer_active_template_limit", 3
                ),
            },
        }

    def monitoring(self) -> dict:
        state = self.store.snapshot()
        jobs = list(state["jobs"].values())
        recordings = list(state["recordings"].values())
        reviews = list(state["review_tasks"].values())
        vectors = list(state["customer_templates"].values()) + list(state["black_templates"].values())
        storage_bytes = 0
        for root in (self.store.upload_root, self.store.artifact_root, self.store.vector_root):
            for path in root.rglob("*"):
                if path.is_file():
                    storage_bytes += path.stat().st_size
        return {
            "service": {"mode": "single_instance", "worker_alive": bool(self._worker and self._worker.is_alive())},
            "jobs": {
                "total": len(jobs),
                "queued": sum(row["status"] == "queued" for row in jobs),
                "processing": sum(row["status"] == "processing" for row in jobs),
                "failed": sum(row["status"] == "failed" for row in jobs),
                "completed": sum(row["status"] == "completed" for row in jobs),
            },
            "recordings": {
                "total": len(recordings),
                "completed": sum(row["status"] == "completed" for row in recordings),
                "external_review": sum(row["status"] == "external_review" for row in recordings),
                "failed": sum(row["status"] == "failed" for row in recordings),
            },
            "reviews": {
                "pending": sum(row["status"] == "pending" for row in reviews),
                "processed": sum(row["status"] != "pending" for row in reviews),
            },
            "templates": {
                "customer_active": sum(
                    row["status"] == "active" for row in state["customer_templates"].values()
                ),
                "customer_rolled_out": sum(
                    row["status"] == "rolled_out" for row in state["customer_templates"].values()
                ),
                "black_active": sum(
                    row["status"] == "active" for row in state["black_templates"].values()
                ),
                "vectors_with_path": sum(bool(row.get("vector_path")) for row in vectors),
            },
            "storage": {
                "bytes": storage_bytes,
                "uploads": len([path for path in self.store.upload_root.rglob("*") if path.is_file()]),
                "artifacts": len([path for path in self.store.artifact_root.rglob("*") if path.is_file()]),
                "vectors": len([path for path in self.store.vector_root.rglob("*") if path.is_file()]),
            },
            "generated_at": now_text(),
        }

    @staticmethod
    def _public_job(job: dict) -> dict:
        return {key: value for key, value in job.items() if key != "payload"} | {
            "recording_id": job.get("payload", {}).get("recording_id")
        }

    def get_job(self, job_id: str) -> dict | None:
        job = self.store.get("jobs", job_id)
        return self._public_job(job) if job else None

    def list_jobs(self) -> list[dict]:
        return [self._public_job(row) for row in self.store.list("jobs")]

    def get_recording(self, recording_id: str) -> dict | None:
        row = self.store.get("recordings", recording_id)
        if not row:
            return None
        private = {"upload_path", "transcript_path", "vector_path", "channel_paths"}
        public = {key: value for key, value in row.items() if key not in private}
        public["transcript_available"] = bool(row.get("transcript_path"))
        public["channels_available"] = sorted(row.get("channel_paths", {}))
        return public

    def get_verification(self, verification_id: str) -> dict | None:
        return self.store.get("verifications", verification_id)

    def get_transcript(self, recording_id: str) -> dict | None:
        row = self.store.get("recordings", recording_id)
        if not row or not row.get("transcript_path"):
            return None
        artifact = self.store.read_artifact(row["transcript_path"])
        expires = datetime.fromisoformat(artifact["expires_at"])
        if datetime.now().astimezone() > expires:
            return {"expired": True, "expires_at": artifact["expires_at"]}
        return artifact

    def audio_path(self, recording_id: str, channel: str) -> Path | None:
        row = self.store.get("recordings", recording_id)
        if not row:
            return None
        if channel == "original":
            relative = row.get("upload_path")
        else:
            relative = row.get("channel_paths", {}).get(channel.upper())
        if not relative:
            return None
        path = (self.store.root / relative).resolve()
        path.relative_to(self.store.root)
        return path

    def list_customers(self) -> list[dict]:
        return self.store.list("customers")

    def get_customer(self, customer_id: str) -> dict | None:
        customer = self.store.get("customers", customer_id)
        if not customer:
            return None
        templates = [
            {key: value for key, value in row.items() if key != "vector_path"}
            for row in self.store.list("customer_templates")
            if row["customer_id"] == customer_id
        ]
        return {**customer, "templates": templates}

    def list_black_actors(self) -> list[dict]:
        return self.store.list("black_actors")

    def get_black_actor(self, actor_id: str) -> dict | None:
        actor = self.store.get("black_actors", actor_id)
        if not actor:
            return None
        templates = [
            {key: value for key, value in row.items() if key != "vector_path"}
            for row in self.store.list("black_templates")
            if row["actor_id"] == actor_id
        ]
        return {**actor, "templates": templates}

    def list_recordings(self) -> list[dict]:
        return [self.get_recording(row["id"]) for row in self.store.list("recordings")]

    def list_verifications(self) -> list[dict]:
        return self.store.list("verifications")

    def list_reviews(self) -> list[dict]:
        return self.store.list("review_tasks")

    def list_cluster_runs(self) -> list[dict]:
        return self.store.list("cluster_runs")
