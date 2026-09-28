from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from multiprocessing import get_context
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from mindmate.ai.providers.deepseek import DEEPSEEK_MODEL, DeepSeekChatProvider
from mindmate.application.provider_configuration import (
    openai_public_cost_estimate,
    public_cost_estimate,
)
from mindmate.application.usage_budget import (
    BudgetRejected,
    assert_external_budget_allows,
    budget_status,
    mark_external_operation_possibly_sent,
    reserve_external_operation,
    set_budget,
    summarize_usage,
)
from mindmate.config import Settings
from mindmate.infrastructure.db import create_session_factory, create_sqlite_engine
from mindmate.infrastructure.models import (
    AiOperation,
    Conversation,
    LearningProviderOperation,
    LearningSession,
    Message,
)
from mindmate.main import create_app
from mindmate.security.credentials import InMemoryCredentialStore

ORIGIN = "http://127.0.0.1:5173"


def _stream_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        content=(
            b'data: {"id":"probe","model":"deepseek-flash",'
            b'"choices":[{"delta":{"content":"ok"},"finish_reason":null}]}\n\n'
            b'data: {"id":"probe","model":"deepseek-flash",'
            b'"choices":[{"delta":{},"finish_reason":"stop"}],'
            b'"usage":{"prompt_tokens":8,"completion_tokens":3,"total_tokens":11}}\n\n'
            b"data: [DONE]\n\n"
        ),
        request=request,
    )


def _make_app(tmp_path: Path) -> tuple[TestClient, InMemoryCredentialStore]:
    settings = Settings(data_dir=tmp_path, env="test", provider_base_url="https://fixture.invalid")
    app = create_app(settings)
    store = InMemoryCredentialStore()
    app.state.credential_store = store
    app.state.deepseek_provider = DeepSeekChatProvider(
        base_url="https://fixture.invalid",
        model=DEEPSEEK_MODEL,
        transport=httpx.MockTransport(_stream_response),
    )
    return TestClient(app, base_url="http://127.0.0.1"), store


def _session_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/api/v1/system/session", headers={"Origin": ORIGIN})
    assert response.status_code == 200
    return {"Origin": ORIGIN, "Idempotency-Key": str(uuid4())}


def _seed_operation(
    session: Session,
    *,
    provider: str,
    input_tokens: int | None,
    output_tokens: int | None,
    with_price_snapshot: bool = True,
    created_at: datetime | None = None,
    mode: str = "GENERAL_CHAT",
    request_stage: str | None = None,
    status: str = "SUCCEEDED",
    reserved_at: datetime | None = None,
    request_sent_at: datetime | None = None,
    reserved_estimate_usd: Decimal | None = None,
) -> str:
    now = created_at or datetime.now(UTC)
    conversation = Conversation(
        title="fixture",
        status="ACTIVE",
        created_at=now,
        updated_at=now,
        last_active_at=now,
    )
    session.add(conversation)
    session.flush()
    user = Message(
        conversation_id=conversation.conversation_id,
        role="user",
        content="q",
        status="COMPLETED",
        sequence_number=1,
        mode_snapshot=mode,
        created_at=now,
        updated_at=now,
    )
    assistant = Message(
        conversation_id=conversation.conversation_id,
        role="assistant",
        content="a",
        status="COMPLETED",
        sequence_number=2,
        mode_snapshot=mode,
        created_at=now,
        updated_at=now,
    )
    session.add_all([user, assistant])
    session.flush()
    is_online = provider.upper() in {"DEEPSEEK", "OPENAI", "ONLINE"}
    rates = openai_public_cost_estimate() if provider.upper() == "OPENAI" else public_cost_estimate()
    snapshot = (
        {
            "provider": provider.upper(),
            "model": rates["model"],
            "checked_on": rates["checked_on"],
            "pricing_url": rates["pricing_url"],
            "input_usd_per_million_tokens": rates["input_usd_per_million_tokens"],
            "output_usd_per_million_tokens": rates["output_usd_per_million_tokens"],
            "rate_assumption": rates["rate_assumption"],
        }
        if is_online and with_price_snapshot
        else None
    )
    operation = AiOperation(
        conversation_id=conversation.conversation_id,
        user_message_id=user.message_id,
        assistant_message_id=assistant.message_id,
        idempotency_key=str(uuid4()),
        client_request_id=str(uuid4()),
        request_hash="a" * 64,
        status=status,
        provider=provider,
        requested_model=str(rates["model"]) if is_online else DEEPSEEK_MODEL,
        resolved_model=str(rates["model"]) if is_online else DEEPSEEK_MODEL,
        prompt_template_version="fixture-v1",
        usage_input_tokens=input_tokens,
        usage_output_tokens=output_tokens,
        usage_total_tokens=(
            None
            if input_tokens is None or output_tokens is None
            else input_tokens + output_tokens
        ),
        request_stage=request_stage
        or (
            "USAGE_KNOWN"
            if is_online and input_tokens is not None and output_tokens is not None
            else "UNKNOWN" if is_online else "NOT_SENT"
        ),
        reserved_at=reserved_at,
        request_sent_at=request_sent_at,
        reserved_estimate_usd=reserved_estimate_usd,
        price_snapshot_json=snapshot,
        created_at=now,
        updated_at=now,
        completed_at=now,
    )
    session.add(operation)
    session.commit()
    return operation.operation_id


def _seed_learning_operation(
    session: Session,
    *,
    provider: str,
    task_type: str,
    created_at: datetime,
) -> None:
    rates = openai_public_cost_estimate() if provider.upper() == "OPENAI" else public_cost_estimate()
    learning = LearningSession(
        topic="fixture",
        goal_type="CUSTOM",
        goal_text="fixture",
        knowledge_base_id="fixture-kb",
        target_question_count=1,
        status="COMPLETED",
        idempotency_key=str(uuid4()),
        client_request_id=str(uuid4()),
        request_hash="b" * 64,
        provider=provider,
        live_model_called=True,
        requested_model=str(rates["model"]),
        created_at=created_at,
        updated_at=created_at,
        row_version=1,
    )
    session.add(learning)
    session.flush()
    session.add(
        LearningProviderOperation(
            learning_session_id=learning.learning_session_id,
            task_type=task_type,
            idempotency_key=f"{task_type}:{uuid4()}",
            client_request_id=f"{task_type}:{uuid4()}",
            request_hash="c" * 64,
            status="COMPLETED",
            provider=provider,
            requested_model=str(rates["model"]),
            resolved_model=str(rates["model"]),
            prompt_template_version="fixture-v1",
            usage_input_tokens=1_000,
            usage_output_tokens=500,
            usage_total_tokens=1_500,
            request_stage="USAGE_KNOWN",
            price_snapshot_json={
                "provider": provider,
                "model": rates["model"],
                "checked_on": rates["checked_on"],
                "pricing_url": rates["pricing_url"],
                "input_usd_per_million_tokens": rates["input_usd_per_million_tokens"],
                "output_usd_per_million_tokens": rates["output_usd_per_million_tokens"],
            },
            created_at=created_at,
            updated_at=created_at,
            started_at=created_at,
            completed_at=created_at,
            row_version=1,
        )
    )
    session.commit()


def _reserve_in_process(data_dir: str, operation_id: str) -> str:
    settings = Settings(data_dir=Path(data_dir), env="test")
    settings.ensure_data_dirs()
    engine = create_sqlite_engine(settings.database_path)
    factory = create_session_factory(engine)
    try:
        with factory() as session:
            result = reserve_external_operation(
                session,
                operation_id=operation_id,
                provider="DEEPSEEK",
                model=DEEPSEEK_MODEL,
                estimated_input_tokens=1_000,
                estimated_output_tokens=1_000,
            )
            return "reserved" if result["reserved"] else str(result["stage"])
    except BudgetRejected as exc:
        return exc.code
    finally:
        engine.dispose()


def test_storage_usage_budget_and_privacy_endpoints(tmp_path: Path) -> None:
    (tmp_path / "objects").mkdir(parents=True, exist_ok=True)
    (tmp_path / "objects" / "a.bin").write_bytes(b"12345")
    (tmp_path / "logs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "logs" / "app.log").write_text("no-secret", encoding="utf-8")
    client, _ = _make_app(tmp_path)
    with client:
        headers = _session_headers(client)
        storage = client.get("/api/v1/system/storage")
        assert storage.status_code == 200
        body = storage.json()
        assert body["database"] == "sqlite"
        assert body["writable"] is True
        assert "MindMateAI" in body["data_dir_display"] or body["data_dir_display"]
        objects = next(item for item in body["categories"] if item["key"] == "objects")
        assert objects["byte_size"] == 5
        assert "api_key" not in storage.text.lower() or "api_key" not in body

        usage = client.get("/api/v1/system/ai-usage")
        assert usage.status_code == 200
        usage_body = usage.json()
        assert usage_body["totals"]["online"]["operations"] == 0
        assert "尚无在线 Provider 响应 usage 记录" in (usage_body["online_actual_usage_message"] or "")

        privacy = client.get("/api/v1/system/privacy")
        assert privacy.status_code == 200
        assert privacy.json()["log_retention"]["available"] is True
        assert privacy.json()["log_retention"]["retention_days"] == 30
        assert privacy.json()["log_retention"]["max_bytes"] == 100 * 1024 * 1024
        assert "Key" in privacy.json()["secrets_policy"]["message"]

        budget = client.put(
            "/api/v1/system/ai-budget",
            headers=headers,
            json={
                "enabled": True,
                "hard_stop_usd": "1.00",
                "soft_remind_usd": "0.50",
                "period": "30d",
                "unknown_usage_policy": "deny",
            },
        )
        assert budget.status_code == 200
        assert budget.json()["budget"]["enabled"] is True
        assert budget.json()["budget"]["hard_stop_usd"] == "1.00"

        bad = client.put(
            "/api/v1/system/ai-budget",
            headers={**headers, "Idempotency-Key": str(uuid4())},
            json={"enabled": True, "hard_stop_usd": None},
        )
        assert bad.status_code == 400
        assert bad.json()["code"] == "BUDGET_HARD_STOP_REQUIRED"


def test_usage_isolates_mock_and_online_and_unknown_tokens(tmp_path: Path) -> None:
    client, _ = _make_app(tmp_path)
    with client:
        factory = cast(Any, client.app).state.session_factory
        with factory() as session:
            _seed_operation(session, provider="MOCK", input_tokens=10, output_tokens=5)
            _seed_operation(session, provider="DEEPSEEK", input_tokens=100, output_tokens=20)
            _seed_operation(session, provider="DEEPSEEK", input_tokens=None, output_tokens=None)
            summary = summarize_usage(session, days=30)
        assert summary["totals"]["mock"]["operations"] == 1
        assert summary["totals"]["mock"]["input_tokens"] == 10
        assert summary["totals"]["online"]["operations"] == 2
        assert summary["totals"]["online"]["input_tokens"] == 100
        assert summary["totals"]["online"]["unknown_usage_operations"] == 1
        assert summary["unknown_usage_operations"] == 1
        assert Decimal(summary["estimated_online_usd"]) > 0


def test_budget_hard_stop_blocks_external_and_serializes_concurrency(tmp_path: Path) -> None:
    client, store = _make_app(tmp_path)
    with client:
        headers = _session_headers(client)
        factory = cast(Any, client.app).state.session_factory
        with factory() as session:
            # Large online usage so estimated spend exceeds $0.01 hard stop.
            _seed_operation(session, provider="DEEPSEEK", input_tokens=1_000_000, output_tokens=1_000_000)
            set_budget(
                session,
                enabled=True,
                hard_stop_usd="0.01",
                soft_remind_usd="0.005",
                period="30d",
                unknown_usage_policy="deny",
            )
            assert budget_status(session)["soft_remind_triggered"] is True

        store.set_secret("provider/deepseek/api-key", "fixture-key")
        consent = client.post(
            "/api/v1/ai/consent",
            headers=headers,
            json={"version": "deepseek-external-ai-v1"},
        )
        assert consent.status_code == 200
        probe = client.post(
            "/api/v1/ai/provider/test",
            headers={**headers, "Idempotency-Key": str(uuid4())},
            json={"confirm_external_transfer": True},
        )
        assert probe.status_code == 409
        assert probe.json()["code"] == "BUDGET_HARD_STOP_REACHED"
        assert "fixture-key" not in probe.text

        results: list[str] = []

        def attempt(_: int) -> None:
            with factory() as session:
                try:
                    assert_external_budget_allows(session)
                    results.append("allow")
                except BudgetRejected as exc:
                    results.append(exc.code)

        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(attempt, range(12)))
        assert results
        assert all(code == "BUDGET_HARD_STOP_REACHED" for code in results)


def test_budget_unknown_usage_denies_conservatively(tmp_path: Path) -> None:
    client, _ = _make_app(tmp_path)
    with client:
        factory = cast(Any, client.app).state.session_factory
        with factory() as session:
            _seed_operation(session, provider="DEEPSEEK", input_tokens=None, output_tokens=None)
            set_budget(
                session,
                enabled=True,
                hard_stop_usd="10.00",
                unknown_usage_policy="deny",
            )
            with pytest.raises(BudgetRejected) as caught:
                assert_external_budget_allows(session)
            assert caught.value.code == "BUDGET_USAGE_UNTRUSTED"


def test_cross_process_budget_reservation_counts_before_second_request(tmp_path: Path) -> None:
    client, _ = _make_app(tmp_path)
    with client:
        factory = cast(Any, client.app).state.session_factory
        with factory() as session:
            operation_ids = [
                _seed_operation(
                    session,
                    provider="DEEPSEEK",
                    input_tokens=None,
                    output_tokens=None,
                    status="QUEUED",
                    request_stage="NOT_SENT",
                )
                for _ in range(2)
            ]
            set_budget(
                session,
                enabled=True,
                hard_stop_usd="0.002",
                period="30d",
                unknown_usage_policy="deny",
            )

        with ProcessPoolExecutor(max_workers=2, mp_context=get_context("spawn")) as executor:
            results = list(executor.map(_reserve_in_process, [str(tmp_path)] * 2, operation_ids))

        assert results.count("reserved") == 1
        assert results.count("BUDGET_HARD_STOP_REACHED") == 1
        with factory() as session:
            summary = summarize_usage(session, period="30d")
        assert Decimal(summary["reserved_online_usd"]) == Decimal("0.001500")
        assert summary["totals"]["online"]["unknown_usage_operations"] == 0


def test_utc_calendar_month_and_historical_window_are_half_open(tmp_path: Path) -> None:
    client, _ = _make_app(tmp_path)
    with client:
        factory = cast(Any, client.app).state.session_factory
        with factory() as session:
            _seed_operation(
                session,
                provider="DEEPSEEK",
                input_tokens=100,
                output_tokens=10,
                created_at=datetime(2026, 9, 30, 23, 59, tzinfo=UTC),
            )
            _seed_operation(
                session,
                provider="OPENAI",
                input_tokens=100,
                output_tokens=10,
                created_at=datetime(2026, 10, 1, 0, 0, tzinfo=UTC),
            )
            current_month = summarize_usage(
                session,
                period="calendar_month",
                now=datetime(2026, 10, 5, 12, tzinfo=UTC),
            )
            previous_month = summarize_usage(
                session,
                start=datetime(2026, 9, 1, tzinfo=UTC),
                end=datetime(2026, 10, 1, tzinfo=UTC),
            )
        historical_response = client.get(
            "/api/v1/system/ai-usage",
            params={
                "start": "2026-09-01T00:00:00Z",
                "end": "2026-10-01T00:00:00Z",
            },
        )
        invalid_window = client.get(
            "/api/v1/system/ai-usage",
            params={"start": "2026-09-01T00:00:00Z"},
        )
        assert current_month["window_start"] == "2026-10-01T00:00:00+00:00"
        assert current_month["totals"]["online"]["operations"] == 1
        assert current_month["by_provider"][0]["provider"] == "OPENAI"
        assert previous_month["window_end"] == "2026-10-01T00:00:00+00:00"
        assert previous_month["totals"]["online"]["operations"] == 1
        assert previous_month["by_provider"][0]["provider"] == "DEEPSEEK"
        assert historical_response.status_code == 200
        assert historical_response.json()["totals"]["online"]["operations"] == 1
        assert invalid_window.status_code == 400


def test_sent_time_owns_cycle_and_old_reservation_still_protects_current_cycle(tmp_path: Path) -> None:
    client, _ = _make_app(tmp_path)
    with client:
        factory = cast(Any, client.app).state.session_factory
        with factory() as session:
            _seed_operation(
                session,
                provider="DEEPSEEK",
                input_tokens=100,
                output_tokens=10,
                created_at=datetime(2026, 9, 28, 12, tzinfo=UTC),
                request_sent_at=datetime(2026, 10, 2, 8, tzinfo=UTC),
            )
            _seed_operation(
                session,
                provider="OPENAI",
                input_tokens=None,
                output_tokens=None,
                status="QUEUED",
                request_stage="RESERVED",
                reserved_at=datetime(2026, 9, 30, 23, 59, tzinfo=UTC),
                reserved_estimate_usd=Decimal("0.005"),
                created_at=datetime(2026, 9, 28, 12, tzinfo=UTC),
            )
            october = summarize_usage(
                session,
                period="calendar_month",
                now=datetime(2026, 10, 5, 12, tzinfo=UTC),
                include_active_reservations=True,
            )
            september = summarize_usage(
                session,
                start=datetime(2026, 9, 1, tzinfo=UTC),
                end=datetime(2026, 10, 1, tzinfo=UTC),
            )

        october_providers = {item["provider"] for item in october["by_provider"]}
        september_providers = {item["provider"] for item in september["by_provider"]}
        assert october["totals"]["online"]["operations"] == 2
        assert october_providers == {"DEEPSEEK", "OPENAI"}
        assert Decimal(october["reserved_online_usd"]) == Decimal("0.005000")
        assert september["totals"]["online"]["operations"] == 1
        assert september_providers == {"OPENAI"}


def test_provider_rate_snapshots_and_chat_learning_categories_are_separate(tmp_path: Path) -> None:
    client, _ = _make_app(tmp_path)
    with client:
        factory = cast(Any, client.app).state.session_factory
        with factory() as session:
            now = datetime(2026, 9, 28, 12, tzinfo=UTC)
            _seed_operation(
                session,
                provider="DEEPSEEK",
                input_tokens=1_000_000,
                output_tokens=1_000_000,
                created_at=now,
                mode="GENERAL_CHAT",
            )
            _seed_learning_operation(
                session,
                provider="OPENAI",
                task_type="QUESTION_GENERATION",
                created_at=now + timedelta(seconds=1),
            )
            _seed_operation(
                session,
                provider="OPENAI",
                input_tokens=1_000_000,
                output_tokens=1_000_000,
                created_at=now + timedelta(seconds=2),
                mode="KNOWLEDGE_CHAT",
            )
            _seed_learning_operation(
                session,
                provider="DEEPSEEK",
                task_type="LEARNING_FEEDBACK",
                created_at=now + timedelta(seconds=3),
            )
            summary = summarize_usage(session, period="30d", now=now + timedelta(days=1))

        by_provider = {item["provider"]: item for item in summary["by_provider"]}
        by_type = {item["operation_type"]: item for item in summary["by_operation_type"]}
        assert Decimal(by_provider["DEEPSEEK"]["estimated_usd"]) == Decimal("1.500900")
        assert Decimal(by_provider["OPENAI"]["estimated_usd"]) == Decimal("12.007000")
        assert by_type["CHAT"]["operations"] == 1
        assert by_type["RAG"]["operations"] == 1
        assert by_type["LEARNING_QUESTION"]["operations"] == 1
        assert by_type["LEARNING_FEEDBACK"]["operations"] == 1
        assert summary["totals"]["online"]["operations"] == 4


def test_legacy_price_snapshot_requires_policy_and_one_confirmation(tmp_path: Path) -> None:
    client, _ = _make_app(tmp_path)
    with client:
        factory = cast(Any, client.app).state.session_factory
        with factory() as session:
            _seed_operation(
                session,
                provider="DEEPSEEK",
                input_tokens=100,
                output_tokens=20,
                with_price_snapshot=False,
            )
            set_budget(
                session,
                enabled=True,
                hard_stop_usd="10.00",
                unknown_usage_policy="confirm",
            )
            summary = summarize_usage(session, period="30d")
            assert summary["totals"]["online"]["unknown_price_operations"] == 1
            assert summary["estimated_online_usd"] == "0.000000"
            with pytest.raises(BudgetRejected) as caught:
                assert_external_budget_allows(session)
            assert caught.value.code == "BUDGET_UNKNOWN_USAGE_CONFIRM_REQUIRED"
            assert_external_budget_allows(session, confirm_unknown_usage=True)


def test_unknown_external_usage_keeps_reservation_and_mock_has_no_cost(tmp_path: Path) -> None:
    client, _ = _make_app(tmp_path)
    with client:
        factory = cast(Any, client.app).state.session_factory
        with factory() as session:
            _seed_operation(
                session,
                provider="DEEPSEEK",
                input_tokens=None,
                output_tokens=None,
                status="QUEUED",
                request_stage="NOT_SENT",
            )
            _seed_operation(session, provider="MOCK", input_tokens=20, output_tokens=8)
            unknown_id = _seed_operation(
                session,
                provider="OPENAI",
                input_tokens=None,
                output_tokens=None,
                status="QUEUED",
                request_stage="NOT_SENT",
            )
            set_budget(
                session,
                enabled=True,
                hard_stop_usd="5.00",
                unknown_usage_policy="deny",
            )
            reservation = reserve_external_operation(
                session,
                operation_id=unknown_id,
                provider="OPENAI",
                model="gpt-6-sol",
                estimated_input_tokens=100,
                estimated_output_tokens=20,
            )
            assert reservation["reserved"] is True
            assert not mark_external_operation_possibly_sent(session, unknown_id)

            with factory() as inspect_session:
                operation = inspect_session.get(AiOperation, unknown_id)
                assert operation is not None
                assert operation.request_stage == "POSSIBLY_SENT"
                operation.request_stage = "UNKNOWN"
                inspect_session.commit()
                summary = summarize_usage(inspect_session, period="30d")
            assert summary["totals"]["online"]["unknown_usage_operations"] == 1
            assert Decimal(summary["unknown_exposure_estimated_usd"]) > 0
            assert summary["totals"]["mock"]["estimated_usd"] is None
