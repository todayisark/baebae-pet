"""
google_tasks.py — Google Tasks API 封装

职责：
  - OAuth 2.0 token 管理（读取、刷新、保存、loopback 授权流）
  - Google Tasks REST API 的 CRUD 操作封装

不含任何 Qt 代码，可在后台线程中安全调用。
"""
from __future__ import annotations

from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/tasks"]


def _find_client_secret() -> Path | None:
    from config.settings import APP_SUPPORT
    candidates = [
        Path(__file__).resolve().parent.parent.parent / "client_secret_desktop.json",
        Path(__file__).resolve().parent.parent / "client_secret_desktop.json",
        APP_SUPPORT / "client_secret.json",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _token_path() -> Path:
    from config.settings import APP_SUPPORT
    return APP_SUPPORT / "google_token.json"


# ---------------------------------------------------------------------------
# 认证状态
# ---------------------------------------------------------------------------

def has_token() -> bool:
    return _token_path().exists()


def revoke_token() -> None:
    p = _token_path()
    if p.exists():
        p.unlink()


def _load_credentials() -> Credentials | None:
    p = _token_path()
    if not p.exists():
        return None
    try:
        creds = Credentials.from_authorized_user_file(str(p), SCOPES)
    except Exception:
        return None
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _save_credentials(creds)
        except Exception:
            return None
    return creds if (creds and creds.valid) else None


def _save_credentials(creds: Credentials) -> None:
    from config.settings import APP_SUPPORT
    APP_SUPPORT.mkdir(parents=True, exist_ok=True)
    _token_path().write_text(creds.to_json(), encoding="utf-8")


def authenticate() -> Credentials:
    """运行 loopback OAuth 流，保存 token 并返回凭据。在后台线程调用。"""
    secret = _find_client_secret()
    if not secret:
        raise FileNotFoundError(
            "找不到 client_secret_desktop.json，请将凭据文件放到项目根目录或数据目录。"
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(secret), SCOPES)
    creds = flow.run_local_server(port=0)
    _save_credentials(creds)
    return creds


# ---------------------------------------------------------------------------
# API 服务构建
# ---------------------------------------------------------------------------

def _service():
    creds = _load_credentials()
    if not creds:
        raise RuntimeError("未登录，请先完成 Google 账号授权。")
    return build("tasks", "v1", credentials=creds)


# ---------------------------------------------------------------------------
# 任务 CRUD
# ---------------------------------------------------------------------------

def list_tasks(tasklist_id: str = "@default") -> tuple[list[dict], list[dict]]:
    """返回 (待办列表, 已完成列表)，单次 API 调用。"""
    svc = _service()
    result = svc.tasks().list(
        tasklist=tasklist_id,
        showCompleted=True,
        showHidden=True,
        maxResults=100,
    ).execute()
    items = result.get("items", [])
    pending = sorted(
        (t for t in items if t.get("status") == "needsAction"),
        key=lambda t: t.get("position", ""),
    )
    completed = sorted(
        (t for t in items if t.get("status") == "completed"),
        key=lambda t: t.get("completed", ""),
        reverse=True,
    )
    return pending, completed


def create_task(title: str, tasklist_id: str = "@default") -> dict:
    svc = _service()
    return svc.tasks().insert(
        tasklist=tasklist_id,
        body={"title": title},
    ).execute()


def update_task(
    task_id: str,
    *,
    title: str | None = None,
    status: str | None = None,
    tasklist_id: str = "@default",
) -> dict:
    body: dict = {}
    if title is not None:
        body["title"] = title
    if status is not None:
        body["status"] = status
        if status == "needsAction":
            body["completed"] = None  # 清除完成时间戳
    svc = _service()
    return svc.tasks().patch(
        tasklist=tasklist_id,
        task=task_id,
        body=body,
    ).execute()


def complete_task(task_id: str, tasklist_id: str = "@default") -> dict:
    return update_task(task_id, status="completed", tasklist_id=tasklist_id)


def uncomplete_task(task_id: str, tasklist_id: str = "@default") -> dict:
    return update_task(task_id, status="needsAction", tasklist_id=tasklist_id)


def delete_task(task_id: str, tasklist_id: str = "@default") -> None:
    svc = _service()
    svc.tasks().delete(tasklist=tasklist_id, task=task_id).execute()
