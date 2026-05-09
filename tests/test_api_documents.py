from io import BytesIO
import hashlib
import json
from pathlib import Path
import re
import time
from uuid import uuid4
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.api.documents import resolve_convert_asset_path
from app.core.id_generator import generate_file_id
from app.core.storage import storage_manager
from app.db.database import get_connection
from app.db.repository import get_document, get_latest_success_parse, replace_document_assets
from app.db.task_repository import insert_conversion_task
from app.main import app


@pytest.fixture
def client(monkeypatch):
    data_dir = Path(__file__).parent / "_tmp" / f"api_{uuid4().hex}" / "data"
    monkeypatch.setattr(settings, "data_dir", data_dir)
    monkeypatch.setattr(storage_manager, "data_dir", data_dir)
    monkeypatch.setattr(settings, "max_upload_size_mb", 100)
    monkeypatch.setattr(settings, "admin_username", "admin")
    monkeypatch.setattr(settings, "admin_password", "admin123")
    monkeypatch.setattr(settings, "session_secret", f"test-secret-{uuid4().hex}")
    monkeypatch.setattr(settings, "session_expire_hours", 12)
    monkeypatch.setattr(settings, "task_worker_count", 1)

    with TestClient(app) as test_client:
        yield test_client


def upload_text(client: TestClient, content: bytes = b"hello\nworld"):
    return client.post(
        "/api/documents/convert",
        files={"file": ("demo.txt", content, "text/plain")},
    )


def login_admin(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert response.status_code == 200


def wait_for_task(client: TestClient, task_id: str) -> dict:
    for _ in range(50):
        response = client.get(f"/api/tasks/{task_id}")
        assert response.status_code == 200
        data = response.json()
        if data["status"] in {"success", "failed", "timeout", "cancelled"}:
            return data
        time.sleep(0.1)
    pytest.fail("task did not finish in time")


def test_auth_login_logout_and_me(client: TestClient) -> None:
    unauthenticated = client.get("/api/auth/me")
    assert unauthenticated.status_code == 401

    invalid_login = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "wrong"},
    )
    assert invalid_login.status_code == 401
    assert invalid_login.json()["detail"]["error_code"] == "invalid_credentials"

    login_response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert login_response.status_code == 200
    assert login_response.json()["username"] == "admin"

    me_response = client.get("/api/auth/me")
    assert me_response.status_code == 200
    assert me_response.json()["username"] == "admin"

    logout_response = client.post("/api/auth/logout")
    assert logout_response.status_code == 200

    logged_out = client.get("/api/auth/me")
    assert logged_out.status_code == 401


def test_convert_txt_get_markdown_cache_and_download(client: TestClient) -> None:
    response = upload_text(client)

    assert response.status_code == 200
    data = response.json()
    assert data["cached"] is False
    assert data["status"] == "success"
    assert data["file_format"] == "txt"
    assert data["file_id"] != hashlib.md5(b"hello\nworld").hexdigest()
    assert data["metadata"]["engine"] == "text"
    assert "assets" not in data["metadata"]

    file_id = data["file_id"]
    markdown_response = client.get(data["markdown_url"])
    assert markdown_response.status_code == 200
    assert markdown_response.text == "hello\nworld"
    assert "text/markdown" in markdown_response.headers["content-type"]

    info_response = client.get(f"/api/documents/{file_id}")
    assert info_response.status_code == 200
    info = info_response.json()
    assert info["markdown_url"] == data["markdown_url"]
    assert info["download_url"] == f"/api/documents/{file_id}/download"
    assert info["original_url"] == f"/api/documents/{file_id}/original"
    assert info["original_filename"] == "demo.txt"
    assert info["file_size"] == len(b"hello\nworld")

    original_response = client.get(info["original_url"])
    assert original_response.status_code == 200
    assert original_response.content == b"hello\nworld"
    assert "text/plain" in original_response.headers["content-type"]

    cached_response = upload_text(client)
    assert cached_response.status_code == 200
    assert cached_response.json()["cached"] is True
    assert cached_response.json()["file_id"] == file_id

    download_response = client.get(f"/api/documents/{file_id}/download")
    assert download_response.status_code == 200
    with zipfile.ZipFile(BytesIO(download_response.content)) as archive:
        assert set(archive.namelist()) == {"result.md", "metadata.json"}
        assert archive.read("result.md").decode("utf-8") == "hello\nworld"


def test_async_convert_txt_status_result_and_open_document_access(client: TestClient) -> None:
    response = client.post(
        "/api/tasks/convert",
        files={"file": ("async.txt", b"async\ncontent", "text/plain")},
    )

    assert response.status_code == 202
    created = response.json()
    assert created["status"] == "queued"
    assert created["status_text"] == "排队中"
    assert created["progress"] == 10
    assert created["stage_text"] == "排队中"
    assert created["message"] == "任务等待转换"
    assert created["status_url"] == f"/api/tasks/{created['task_id']}"

    task = wait_for_task(client, created["task_id"])
    assert task["status"] == "success"
    assert task["status_text"] == "成功"
    assert task["progress"] == 100
    assert task["stage"] == "completed"
    assert task["stage_text"] == "已完成"
    assert task["message"] == "文档转换完成"
    assert task["cached"] is False
    assert task["result"]["status"] == "success"
    assert task["result"]["file_id"] == task["file_id"]

    markdown_response = client.get(task["result"]["markdown_url"])
    assert markdown_response.status_code == 200
    assert markdown_response.text == "async\ncontent"

    document_response = client.get(task["document_url"])
    assert document_response.status_code == 200
    assert document_response.json()["status"] == "success"


def test_async_convert_uses_success_cache(client: TestClient) -> None:
    first = client.post(
        "/api/tasks/convert",
        files={"file": ("cached.txt", b"cached content", "text/plain")},
    )
    first_task = wait_for_task(client, first.json()["task_id"])
    assert first_task["status"] == "success"

    cached = client.post(
        "/api/tasks/convert",
        files={"file": ("cached.txt", b"cached content", "text/plain")},
    )

    assert cached.status_code == 200
    cached_task = cached.json()
    assert cached_task["status"] == "success"
    assert cached_task["progress"] == 100
    assert cached_task["cached"] is True
    assert cached_task["file_id"] == first_task["file_id"]


def test_management_task_apis_require_login_and_support_actions(client: TestClient) -> None:
    created = client.post(
        "/api/tasks/convert",
        files={"file": ("managed.txt", b"managed content", "text/plain")},
    ).json()
    completed = wait_for_task(client, created["task_id"])

    assert client.get("/api/tasks").status_code == 401
    assert client.get(f"/api/tasks/{completed['task_id']}").status_code == 200

    login_admin(client)
    list_response = client.get("/api/tasks")
    assert list_response.status_code == 200
    assert list_response.json()["total"] >= 1
    task_date = completed["created_at"].split()[0]

    range_response = client.get(f"/api/tasks?start_date={task_date}&end_date={task_date}")
    assert range_response.status_code == 200
    assert any(item["task_id"] == completed["task_id"] for item in range_response.json()["items"])

    future_response = client.get("/api/tasks?start_date=2099-01-01&end_date=2099-01-02")
    assert future_response.status_code == 200
    assert future_response.json()["total"] == 0

    invalid_range = client.get("/api/tasks?start_date=2099-01-02&end_date=2099-01-01")
    assert invalid_range.status_code == 400
    assert invalid_range.json()["detail"]["error_code"] == "invalid_date_range"

    queued_task_id = generate_file_id()
    with get_connection() as conn:
        insert_conversion_task(
            conn,
            {
                "task_id": queued_task_id,
                "file_id": completed["file_id"],
                "original_filename": "managed.txt",
                "file_format": "txt",
                "status": "queued",
                "progress": 10,
                "stage": "queued",
                "message": "waiting",
            },
        )
        conn.commit()

    cancel_response = client.post(f"/api/tasks/{queued_task_id}/cancel")
    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"

    retry_response = client.post(f"/api/tasks/{completed['task_id']}/retry")
    assert retry_response.status_code == 202
    retried = wait_for_task(client, retry_response.json()["task_id"])
    assert retried["status"] == "success"

    delete_response = client.delete(f"/api/tasks/{retried['task_id']}")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted_tasks"] == 1

    deleted_lookup = client.get(f"/api/tasks/{retried['task_id']}")
    assert deleted_lookup.status_code == 404


def test_management_document_apis_and_web_page(client: TestClient) -> None:
    file_id = upload_text(client, b"document management").json()["file_id"]

    assert client.get(f"/api/documents/{file_id}").status_code == 200
    assert client.get("/api/documents").status_code == 401
    assert client.get("/web").status_code == 200
    assert client.get("/web/static/app.js").status_code == 200

    login_admin(client)
    list_response = client.get("/api/documents")
    assert list_response.status_code == 200
    list_items = list_response.json()["items"]
    assert any(item["file_id"] == file_id for item in list_items)
    listed = next(item for item in list_items if item["file_id"] == file_id)
    assert listed["original_url"] == f"/api/documents/{file_id}/original"
    assert listed["download_url"] == f"/api/documents/{file_id}/download"
    assert listed["file_size"] == len(b"document management")
    document_date = listed["created_at"].split()[0]

    date_range_response = client.get(f"/api/documents?start_date={document_date}&end_date={document_date}")
    assert date_range_response.status_code == 200
    assert any(item["file_id"] == file_id for item in date_range_response.json()["items"])

    future_documents = client.get("/api/documents?start_date=2099-01-01&end_date=2099-01-02")
    assert future_documents.status_code == 200
    assert future_documents.json()["total"] == 0

    reconvert_response = client.post(f"/api/documents/{file_id}/reconvert")
    assert reconvert_response.status_code == 202
    reconverted = wait_for_task(client, reconvert_response.json()["task_id"])
    assert reconverted["status"] == "success"

    delete_response = client.delete(f"/api/documents/{file_id}")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted_documents"] == 1
    assert delete_response.json()["deleted_uploads"] == 1

    missing_response = client.get(f"/api/documents/{file_id}")
    assert missing_response.status_code == 404


def test_database_times_use_beijing_text_format(client: TestClient) -> None:
    file_id = upload_text(client).json()["file_id"]

    with get_connection() as conn:
        document = get_document(conn, file_id)
        parse_record = get_latest_success_parse(conn, file_id)

    time_pattern = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
    assert time_pattern.fullmatch(document["created_at"])
    assert time_pattern.fullmatch(document["updated_at"])
    assert time_pattern.fullmatch(parse_record["created_at"])
    assert time_pattern.fullmatch(parse_record["updated_at"])


def test_delete_cache_then_convert_again(client: TestClient) -> None:
    file_id = upload_text(client).json()["file_id"]

    unauthenticated = client.delete(f"/api/documents/{file_id}/cache")
    assert unauthenticated.status_code == 401

    login_admin(client)
    delete_response = client.delete(f"/api/documents/{file_id}/cache")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted_parse_records"] == 1
    assert delete_response.json()["deleted_output_dirs"] == 1

    markdown_response = client.get(f"/api/documents/{file_id}/markdown")
    assert markdown_response.status_code == 404
    assert markdown_response.json()["detail"]["error_code"] == "markdown_not_found"

    retry_response = upload_text(client)
    assert retry_response.status_code == 200
    assert retry_response.json()["cached"] is False
    assert retry_response.json()["file_id"] == file_id


def test_invalid_success_cache_is_not_returned(client: TestClient) -> None:
    first_response = upload_text(client)
    file_id = first_response.json()["file_id"]

    with get_connection() as conn:
        parse_record = get_latest_success_parse(conn, file_id)
    markdown_path = storage_manager.resolve_data_path(parse_record["markdown_path"])
    markdown_path.unlink()

    info_response = client.get(f"/api/documents/{file_id}")
    assert info_response.status_code == 200
    assert info_response.json()["status"] == "failed"
    assert info_response.json()["error_code"] == "cache_invalid"

    retry_response = upload_text(client)
    assert retry_response.status_code == 200
    assert retry_response.json()["cached"] is False
    assert retry_response.json()["file_id"] == file_id

    markdown_response = client.get(f"/api/documents/{file_id}/markdown")
    assert markdown_response.status_code == 200
    assert markdown_response.text == "hello\nworld"


def test_corrupt_metadata_does_not_raise_unhandled_error(client: TestClient) -> None:
    file_id = upload_text(client).json()["file_id"]

    with get_connection() as conn:
        parse_record = get_latest_success_parse(conn, file_id)
    metadata_path = storage_manager.resolve_data_path(parse_record["metadata_path"])
    metadata_path.write_text("{broken json", encoding="utf-8")

    info_response = client.get(f"/api/documents/{file_id}")
    assert info_response.status_code == 200
    assert info_response.json()["status"] == "failed"
    assert info_response.json()["error_code"] == "cache_invalid"

    download_response = client.get(f"/api/documents/{file_id}/download")
    assert download_response.status_code == 200
    with zipfile.ZipFile(BytesIO(download_response.content)) as archive:
        assert archive.namelist() == ["result.md", "metadata.json"]
        with pytest.raises(json.JSONDecodeError):
            json.loads(archive.read("metadata.json").decode("utf-8"))


def test_large_upload_is_rejected_without_success_record(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "max_upload_size_mb", 1)
    response = client.post(
        "/api/documents/convert",
        files={"file": ("large.txt", b"x" * (1024 * 1024 + 1), "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["error_code"] == "file_too_large"


def test_asset_endpoint_and_download(client: TestClient) -> None:
    file_id = upload_text(client).json()["file_id"]

    with get_connection() as conn:
        parse_record = get_latest_success_parse(conn, file_id)
        asset_path = storage_manager.resolve_data_path(parse_record["output_dir"]) / "assets" / "demo.png"
        asset_path.write_bytes(b"fake-png")
        replace_document_assets(
            conn,
            file_id,
            [
                {
                    "asset_name": "demo.png",
                    "content_type": "image/png",
                    "asset_path": storage_manager.relative_to_data_dir(asset_path),
                }
            ],
        )
        conn.commit()

    info = client.get(f"/api/documents/{file_id}").json()
    assert info["assets"] == [
        {
            "name": "demo.png",
            "content_type": "image/png",
            "url": f"/api/documents/{file_id}/assets/demo.png",
        }
    ]

    asset_response = client.get(info["assets"][0]["url"])
    assert asset_response.status_code == 200
    assert asset_response.content == b"fake-png"
    assert "image/png" in asset_response.headers["content-type"]

    download_response = client.get(f"/api/documents/{file_id}/download")
    with zipfile.ZipFile(BytesIO(download_response.content)) as archive:
        assert "assets/demo.png" in archive.namelist()


def test_converter_asset_path_under_data_dir_is_not_duplicated() -> None:
    base_dir = Path(__file__).parent / "_tmp" / f"asset_path_{uuid4().hex}"
    output_dir = base_dir / "data" / "outputs" / "20260508" / "file-id"
    asset_path = output_dir / "assets" / "image-001.png"
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    asset_path.write_bytes(b"png")

    relative_asset_path = Path(asset_path.relative_to(Path.cwd()))
    resolved = resolve_convert_asset_path(relative_asset_path, output_dir)

    assert resolved == asset_path.resolve()


def test_input_validation_errors(client: TestClient) -> None:
    missing_file = client.post("/api/documents/convert")
    assert missing_file.status_code == 400
    assert missing_file.json()["detail"]["error_code"] == "empty_file"

    unsupported = client.post(
        "/api/documents/convert",
        files={"file": ("demo.png", b"not an image", "image/png")},
    )
    assert unsupported.status_code == 400
    assert unsupported.json()["detail"]["status"] == "unsupported"
    assert unsupported.json()["detail"]["error_code"] == "unsupported_file_format"

    invalid_file_id = client.get("/api/documents/not-a-md5")
    assert invalid_file_id.status_code == 400
    assert invalid_file_id.json()["detail"]["error_code"] == "invalid_file_id"

    file_id = upload_text(client).json()["file_id"]
    invalid_asset_name = client.get(f"/api/documents/{file_id}/assets/%2E%2E")
    assert invalid_asset_name.status_code == 400
    assert invalid_asset_name.json()["detail"]["error_code"] == "asset_not_found"

    missing_asset = client.get(f"/api/documents/{file_id}/assets/missing.png")
    assert missing_asset.status_code == 404
    assert missing_asset.json()["detail"]["error_code"] == "asset_not_found"
