"""平台配置加载与路径约束。"""
from __future__ import annotations

import json
import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "platform.json"


def _inside_project(relative_path: str) -> Path:
    path = (PROJECT_ROOT / relative_path).resolve()
    path.relative_to(PROJECT_ROOT)
    return path


def load_platform_config(path: str | Path = DEFAULT_CONFIG) -> dict:
    config_path = Path(path).resolve()
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    admin = payload.setdefault("security", {}).setdefault("default_admin", {})
    env_hash = os.environ.get("VOICEPRINT_ADMIN_PASSWORD_HASH")
    env_password = os.environ.get("VOICEPRINT_ADMIN_PASSWORD")
    if env_hash:
        admin["password_hash"] = env_hash
        admin.pop("password", None)
    elif env_password:
        admin["password"] = env_password
        admin.pop("password_hash", None)
    payload["config_path"] = str(config_path)
    payload["project_root"] = str(PROJECT_ROOT)
    payload["storage_path"] = str(_inside_project(payload["storage_root"]))
    payload["backend_path"] = str(
        _inside_project(payload["models"]["backend_dir"])
    )
    payload["role_model_path"] = str(
        _inside_project(payload["models"]["role_model_path"])
    )
    payload["black_bootstrap_path"] = str(
        _inside_project(payload["black_search"]["bootstrap_db"])
    )
    return payload
