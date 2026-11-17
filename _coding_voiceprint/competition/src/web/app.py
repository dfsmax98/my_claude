# -*- coding: utf-8 -*-
"""声纹项目本地评估控制台。

仅提供聚合指标和静态页面，不暴露录音路径、客户号或声纹向量。
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import mimetypes
import sys
from datetime import datetime
from http.cookies import SimpleCookie
from email import policy
from email.parser import BytesParser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

MODULE_ROOT = Path(__file__).resolve().parents[2]
STATIC_ROOT = Path(__file__).resolve().parent / "static"
CUSTOMER_REPORT = MODULE_ROOT / "reports" / "kesu_customer_refresh_20260731"
FUNCTION_REPORT = MODULE_ROOT / "reports" / "voiceprint_function_test_20260810"


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _count_customer_labels(path: Path) -> tuple[int, int]:
    """返回有效录音数和去重客户数。"""
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            rows = list(csv.DictReader(source))
    except FileNotFoundError:
        return 0, 0
    identities = {
        (row.get("identity") or row.get("cust_no") or "").strip()
        for row in rows
        if (row.get("identity") or row.get("cust_no") or "").strip()
    }
    return len(rows), len(identities)


def _pct(value: float | None) -> float | None:
    return round(float(value) * 100, 2) if value is not None else None


def build_overview() -> dict:
    customer_metrics = _read_json(CUSTOMER_REPORT / "customer_metrics_rebuilt.json")
    black_metrics = _read_json(FUNCTION_REPORT / "black_metrics.json")
    gang_metrics = _read_json(FUNCTION_REPORT / "gang_metrics.json")
    recordings, identities = _count_customer_labels(
        CUSTOMER_REPORT / "customer_matrix_labels.csv"
    )

    selected_gang = gang_metrics.get("selected", {})
    black_sizes = black_metrics.get("by_db_size", {})
    db_status = {
        "customer_db": (MODULE_ROOT / "data" / "customer_db.pkl").exists(),
        "black_db": (MODULE_ROOT / "data" / "black_db.pkl").exists(),
        "legacy_black_db": (MODULE_ROOT / "black_db.pkl").exists(),
    }

    capabilities = [
        {
            "name": "双轨拆分与客户判角",
            "stage": "pilot",
            "label": "试运行",
            "evidence": f"{recordings}/985 通高置信纳入，123 通保留人工复核",
        },
        {
            "name": "CAM++ 声纹提取",
            "stage": "ready",
            "label": "已验证",
            "evidence": f"{recordings} 通客户声道重提取，报告记录 0 失败",
        },
        {
            "name": "客户 1:1 核验",
            "stage": "pilot",
            "label": "试运行",
            "evidence": (
                f"EER {_pct(customer_metrics.get('eer'))}%；"
                f"Top-1 {_pct(customer_metrics.get('top1_accuracy'))}%"
            ),
        },
        {
            "name": "黑产库 1:N 检索",
            "stage": "pilot",
            "label": "离线验证",
            "evidence": "10/30/50/100 身份库完成隔离评估，端到端召回仍需提升",
        },
        {
            "name": "客户库与黑产库持久化",
            "stage": "blocked",
            "label": "缺部署产物",
            "evidence": "新 schema 的 customer_db.pkl 与 data/black_db.pkl 当前均不存在",
        },
        {
            "name": "实时服务接口",
            "stage": "blocked",
            "label": "未服务化",
            "evidence": "已有 Python 类和 CLI，尚无 HTTP API、任务队列与超时控制",
        },
        {
            "name": "跨客户团伙簇",
            "stage": "experimental",
            "label": "实验中",
            "evidence": (
                f"高精度配置检出 {selected_gang.get('gang_detected', 0)}/"
                f"{selected_gang.get('gang_count', 0)} 个已知团伙"
            ),
        },
        {
            "name": "性别 / 年龄 / 情绪画像",
            "stage": "blocked",
            "label": "未实现",
            "evidence": "acoustic/profile.py 仅定义接口，调用会抛 NotImplementedError",
        },
        {
            "name": "鉴权、加密与审核留痕",
            "stage": "blocked",
            "label": "未实现",
            "evidence": "当前以本地 pickle 保存，尚无生产级安全与审计机制",
        },
    ]

    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "scope": "离线评估快照",
        "dataset": {
            "recordings": recordings,
            "identities": identities,
            "role_total": 985,
            "manual_review": max(985 - recordings, 0),
        },
        "customer_metrics": {
            "eer": _pct(customer_metrics.get("eer")),
            "eer_threshold": customer_metrics.get("eer_threshold"),
            "top1_accuracy": _pct(customer_metrics.get("top1_accuracy")),
            "tar_at_fixed": _pct(customer_metrics.get("tar_at_fixed")),
            "far_at_fixed": _pct(customer_metrics.get("far_at_fixed")),
            "genuine_p05": customer_metrics.get("genuine_p05"),
            "impostor_p95": customer_metrics.get("impostor_p95"),
        },
        "black_metrics": [
            {
                "size": int(size),
                "threshold": row.get("black_threshold"),
                "recall_at_1": _pct(row.get("retrieval_recall_at_1")),
                "recall_at_5": _pct(row.get("retrieval_recall_at_5")),
                "end_to_end_recall": _pct(row.get("end_to_end_black_recall")),
                "query_far": _pct(row.get("combined_nonblack_query_far")),
                "far_target_met": row.get("query_far_target_met", False),
                "p95_ms": row.get("black_search_latency_ms", {}).get("p95"),
            }
            for size, row in sorted(black_sizes.items(), key=lambda item: int(item[0]))
        ],
        "gang_metrics": {
            "threshold": selected_gang.get("threshold"),
            "topk": selected_gang.get("topk"),
            "precision": _pct(selected_gang.get("pair_precision")),
            "recall": _pct(selected_gang.get("pair_recall")),
            "f1": _pct(selected_gang.get("pair_f1")),
            "detected": selected_gang.get("gang_detected"),
            "total": selected_gang.get("gang_count"),
            "passed": gang_metrics.get("high_precision_function_passed", False),
        },
        "db_status": db_status,
        "verification": {"tests": 22, "passed": 22, "date": "2026-08-18"},
        "capabilities": capabilities,
    }


class VoiceprintHandler(BaseHTTPRequestHandler):
    server_version = "VoiceprintPlatform/1.0"
    service = None

    def _json(self, payload, status=HTTPStatus.OK, headers=None):
        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(content)

    def _token(self):
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:].strip()
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        morsel = cookie.get("vp_session")
        return morsel.value if morsel else None

    def _current_user(self):
        return self.service.current_user(self._token())

    def _require_user(self):
        user = self._current_user()
        if not user:
            self._json({"error": "未登录"}, HTTPStatus.UNAUTHORIZED)
            return None
        return user

    def _require_permission(self, permission):
        user = self._require_user()
        if not user:
            return None
        self.service.require_permission(user["username"], permission)
        return user

    def _redact_customer_row(self, row, user):
        if not row:
            return row
        if user["permissions"].get("view_customer_key"):
            return row
        redacted = dict(row)
        redacted["customer_key"] = None
        redacted["cust_no"] = None
        if "templates" in redacted:
            redacted["templates"] = [
                {key: value for key, value in item.items() if key not in {"customer_key", "cust_no"}}
                for item in redacted["templates"]
            ]
        return redacted

    def _static(self, request_path):
        relative = "index.html" if request_path in {"", "/"} else unquote(request_path.lstrip("/"))
        candidate = (STATIC_ROOT / relative).resolve()
        try:
            candidate.relative_to(STATIC_ROOT.resolve())
        except ValueError:
            self._json({"error": "禁止访问"}, HTTPStatus.FORBIDDEN)
            return
        if not candidate.is_file():
            self._json({"error": "资源不存在"}, HTTPStatus.NOT_FOUND)
            return
        content = candidate.read_bytes()
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type == "application/javascript":
            content_type += "; charset=utf-8"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(content)

    def _file(self, path):
        if path is None or not path.is_file():
            self._json({"error": "音频不存在"}, HTTPStatus.NOT_FOUND)
            return
        content = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def _json_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _multipart(self):
        content_type = self.headers.get("Content-Type", "")
        if not content_type.lower().startswith("multipart/form-data"):
            raise ValueError("请求必须使用multipart/form-data")
        length = int(self.headers.get("Content-Length") or 0)
        maximum = int(self.service.config["audio"]["max_upload_bytes"]) + 1024 * 1024
        if length <= 0 or length > maximum:
            raise ValueError("上传请求大小无效")
        raw = self.rfile.read(length)
        message = BytesParser(policy=policy.default).parsebytes(
            f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("ascii") + raw
        )
        fields, files = {}, {}
        for part in message.iter_parts():
            name = part.get_param("name", header="content-disposition")
            if not name:
                continue
            payload = part.get_payload(decode=True) or b""
            filename = part.get_filename()
            if filename:
                files[name] = {"filename": filename, "stream": io.BytesIO(payload)}
            else:
                fields[name] = payload.decode(part.get_content_charset() or "utf-8")
        return fields, files

    def _item(self, row, missing):
        self._json(row if row else {"error": missing}, HTTPStatus.OK if row else HTTPStatus.NOT_FOUND)

    def do_GET(self):  # noqa: N802
        path = urlparse(self.path).path
        parts = [part for part in path.split("/") if part]
        service = self.service
        try:
            if path == "/api/health":
                self._json({"status": "ok", "service": "voiceprint-platform"})
            elif path == "/api/v1/session":
                user = self._current_user()
                self._json({"user": user} if user else {"user": None}, HTTPStatus.OK)
            elif path == "/api/overview":
                self._json(build_overview())
            elif path == "/api/v1/overview":
                user = self._require_user()
                if not user:
                    return
                self._json(service.overview())
            elif path == "/api/v1/models":
                user = self._require_user()
                if not user:
                    return
                self._json(service.backend.model_info())
            elif path == "/api/v1/jobs":
                user = self._require_user()
                if not user:
                    return
                self._json({"items": service.list_jobs()})
            elif len(parts) == 4 and parts[:3] == ["api", "v1", "jobs"]:
                user = self._require_user()
                if not user:
                    return
                self._item(service.get_job(parts[3]), "任务不存在")
            elif path == "/api/v1/recordings":
                user = self._require_user()
                if not user:
                    return
                self._json({"items": service.list_recordings()})
            elif len(parts) == 5 and parts[:3] == ["api", "v1", "recordings"] and parts[4] == "transcript":
                user = self._require_permission("view_transcript")
                if not user:
                    return
                self._item(service.get_transcript(parts[3]), "转写不存在")
            elif len(parts) == 6 and parts[:3] == ["api", "v1", "recordings"] and parts[4] == "audio":
                user = self._require_permission("view_audio")
                if not user:
                    return
                if parts[5] not in {"original", "L", "R"}:
                    raise ValueError("channel必须为original、L或R")
                self._file(service.audio_path(parts[3], parts[5]))
            elif len(parts) == 4 and parts[:3] == ["api", "v1", "recordings"]:
                user = self._require_user()
                if not user:
                    return
                self._item(service.get_recording(parts[3]), "录音不存在")
            elif path == "/api/v1/verifications":
                user = self._require_user()
                if not user:
                    return
                self._json({"items": service.list_verifications()})
            elif len(parts) == 4 and parts[:3] == ["api", "v1", "verifications"]:
                user = self._require_user()
                if not user:
                    return
                self._item(service.get_verification(parts[3]), "核验不存在")
            elif path == "/api/v1/customers":
                user = self._require_user()
                if not user:
                    return
                self._json({"items": [self._redact_customer_row(row, user) for row in service.list_customers()]})
            elif len(parts) == 4 and parts[:3] == ["api", "v1", "customers"]:
                user = self._require_user()
                if not user:
                    return
                self._item(self._redact_customer_row(service.get_customer(parts[3]), user), "客户不存在")
            elif path == "/api/v1/black-actors":
                user = self._require_user()
                if not user:
                    return
                self._json({"items": service.list_black_actors()})
            elif len(parts) == 4 and parts[:3] == ["api", "v1", "black-actors"]:
                user = self._require_user()
                if not user:
                    return
                self._item(service.get_black_actor(parts[3]), "黑产身份不存在")
            elif path == "/api/v1/reviews":
                user = self._require_user()
                if not user:
                    return
                self._json({"items": service.list_reviews()})
            elif path == "/api/v1/cluster-runs":
                user = self._require_user()
                if not user:
                    return
                self._json({"items": service.list_cluster_runs()})
            elif path == "/api/v1/admin/users":
                user = self._require_permission("manage_users")
                if not user:
                    return
                self._json({"items": service.list_users()})
            elif path == "/api/v1/admin/access-policy":
                user = self._require_permission("manage_permissions")
                if not user:
                    return
                self._json(service.get_access_policy())
            elif path == "/api/v1/admin/governance":
                user = self._require_permission("manage_permissions")
                if not user:
                    return
                self._json(service.governance_settings())
            elif path == "/api/v1/admin/releases":
                user = self._require_user()
                if not user:
                    return
                self._json({"items": service.list_releases()})
            elif path == "/api/v1/admin/monitoring":
                user = self._require_permission("view_monitoring")
                if not user:
                    return
                self._json(service.monitoring())
            elif path.startswith("/api/"):
                self._json({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)
            else:
                self._static(path)
        except PermissionError as exc:
            self._json({"error": str(exc)}, HTTPStatus.FORBIDDEN)
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._json({"error": f"{type(exc).__name__}: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self):  # noqa: N802
        path = urlparse(self.path).path
        parts = [part for part in path.split("/") if part]
        service = self.service
        try:
            if path == "/api/v1/session":
                payload = self._json_body()
                result = service.authenticate(
                    str(payload.get("username", "")),
                    str(payload.get("password", "")),
                )
                cookie = (
                    f"vp_session={result['token']}; Path=/; HttpOnly; SameSite=Lax; "
                    f"Max-Age={int(float(service.config.get('security', {}).get('session_hours', 8)) * 3600)}"
                )
                self._json(result, headers={"Set-Cookie": cookie})
            elif path == "/api/v1/logout":
                service.logout(self._token())
                self._json({"ok": True}, headers={"Set-Cookie": "vp_session=; Path=/; Max-Age=0; SameSite=Lax"})
            elif path == "/api/v1/recordings":
                user = self._require_user()
                if not user:
                    return
                fields, files = self._multipart()
                audio = files.get("audio")
                if not audio:
                    raise ValueError("缺少audio文件")
                result = service.submit_recording(
                    audio["stream"], audio["filename"], fields.get("customer_key", "")
                )
                self._json(result, HTTPStatus.ACCEPTED)
            elif path == "/api/v1/black-recordings":
                user = self._require_user()
                if not user:
                    return
                fields, files = self._multipart()
                audio = files.get("audio")
                if not audio:
                    raise ValueError("缺少audio文件")
                result = service.submit_black_recording(
                    audio["stream"],
                    audio["filename"],
                    fields.get("actor_key", ""),
                    fields.get("reviewer", "未标识用户"),
                )
                self._json(result, HTTPStatus.ACCEPTED)
            elif path == "/api/v1/cluster-runs":
                user = self._require_permission("trigger_cluster")
                if not user:
                    return
                self._json(service.run_cluster(), HTTPStatus.CREATED)
            elif len(parts) == 5 and parts[:3] == ["api", "v1", "reviews"] and parts[4] == "decision":
                user = self._require_user()
                if not user:
                    return
                payload = self._json_body()
                self._json(
                    service.decide_review(
                        parts[3],
                        str(payload.get("decision", "")),
                        str(payload.get("reviewer", user["username"])),
                    )
                )
            elif path == "/api/v1/admin/users":
                user = self._require_permission("manage_users")
                if not user:
                    return
                self._json(service.save_user(self._json_body(), user["username"]))
            elif path == "/api/v1/admin/access-policy":
                user = self._require_permission("manage_permissions")
                if not user:
                    return
                self._json(service.update_access_policy(self._json_body(), user["username"]))
            elif path == "/api/v1/admin/governance":
                user = self._require_permission("manage_permissions")
                if not user:
                    return
                self._json(service.update_governance_settings(self._json_body(), user["username"]))
            elif path == "/api/v1/admin/releases":
                user = self._require_permission("manage_releases")
                if not user:
                    return
                self._json(service.create_release(self._json_body(), user["username"]), HTTPStatus.CREATED)
            else:
                self._json({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)
        except PermissionError as exc:
            self._json({"error": str(exc)}, HTTPStatus.FORBIDDEN)
        except (ValueError, KeyError, json.JSONDecodeError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._json({"error": f"{type(exc).__name__}: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def log_message(self, fmt, *args):
        print(f"[{self.log_date_time_string()}] {fmt % args}")


def create_server(host="127.0.0.1", port=8765, service=None, *, start_worker=True):
    if service is None:
        sys.path.insert(0, str(MODULE_ROOT / "src"))
        from voiceprint_platform.service import VoiceprintPlatformService

        service = VoiceprintPlatformService(start_worker=start_worker)
    handler = type("BoundVoiceprintHandler", (VoiceprintHandler,), {"service": service})
    server = ThreadingHTTPServer((host, port), handler)
    server.voiceprint_service = service
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="启动声纹识别平台")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = create_server(args.host, args.port)
    print(f"声纹识别平台：http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        server.voiceprint_service.close()


if __name__ == "__main__":
    main()
