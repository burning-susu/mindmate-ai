from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from mindmate.config import Settings
from mindmate.infrastructure.models import KnowledgeBase
from mindmate.main import create_app


def test_knowledge_base_list_limit_uses_update_order_and_skips_trash(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path, env="test")
    with TestClient(create_app(settings), base_url="http://127.0.0.1") as client:
        client.post("/api/v1/system/session", headers={"Origin": "http://127.0.0.1:5173"})
        created = []
        for index, name in enumerate(["最早", "其次", "中间", "较新", "最新", "已回收"]):
            response = client.post(
                "/api/v1/knowledge-bases",
                headers={
                    "Origin": "http://127.0.0.1:5173",
                    "Idempotency-Key": f"home-kb-{index}",
                },
                json={"name": name, "description": "公开合成资料"},
            )
            assert response.status_code == 201
            created.append(response.json())

        baseline = datetime(2026, 9, 26, 8, 0, tzinfo=UTC)
        app = client.app
        if not isinstance(app, FastAPI):
            raise AssertionError("测试客户端没有返回 FastAPI 应用。")
        with app.state.session_factory() as session:
            rows = {
                row.knowledge_base_id: row
                for row in session.scalars(select(KnowledgeBase))
            }
            for index, item in enumerate(created):
                row = rows[item["knowledge_base_id"]]
                row.updated_at = baseline + timedelta(minutes=index)
                if item["name"] == "已回收":
                    row.deleted_at = baseline + timedelta(hours=1)
                    row.status = "IN_TRASH"
                elif item["name"] == "中间":
                    row.status = "FAILED"
                elif item["name"] == "最新":
                    row.status = "READY"
            session.commit()

        limited = client.get("/api/v1/knowledge-bases", params={"limit": 4})
        assert limited.status_code == 200
        names = [item["name"] for item in limited.json()["items"]]
        assert names == ["最新", "较新", "中间", "其次"]
        failed = next(item for item in limited.json()["items"] if item["name"] == "中间")
        assert failed["status"] == "FAILED"
        assert failed["file_count"] == 0
        assert "已回收" not in names

        complete = client.get("/api/v1/knowledge-bases")
        assert [item["name"] for item in complete.json()["items"]] == [
            "最新",
            "较新",
            "中间",
            "其次",
            "最早",
        ]
