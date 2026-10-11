"""cycle446 — 오케스트레이터(`lw/exit_shadow.Runner`) 종단 간 검증. 실 I/O 0(가짜 http/db/openai)."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from lw.config import G0_PATH, G1_PATH
from lw.exit_shadow import Runner
from lw.http import FetchError
from lw_fakes import FakeDB, FakeHttpClient, FakeOpenAI, daily_row, g1_item, ok_body

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))
TODAY = date(2026, 10, 14)
BAR_DATE = date(2026, 10, 13)
NOW = datetime(2026, 10, 14, 8, 15, tzinfo=KST)
CONFIRMED_AT = datetime(2026, 10, 14, 7, 0, tzinfo=KST)  # 오늘 06:00 뒤 — 확정
PROVISIONAL_AT = datetime(2026, 10, 13, 20, 30, tzinfo=KST)  # 오늘 06:00 전 — 잠정


def _running_g0(strategies=None):
    return {"running": True, "phase": "running", "strategies": strategies or {"kojiro": {"params": {}}}}


def _setup_confirmed(db, ticker="005930"):
    db.daily_rows["069500"] = [daily_row(BAR_DATE)]
    db.daily_rows[ticker] = [daily_row(BAR_DATE, updated_at=CONFIRMED_AT)]
    db.head_rows[ticker] = {"bas_dd": BAR_DATE, "updated_at": CONFIRMED_AT}


def _runner(*, client, db, openai_client=None, model="gpt-6-luna", mode="shadow"):
    return Runner(client=client, db=db, openai_client=openai_client, model=model, mode=mode,
                  now=lambda: NOW)


@pytest.mark.asyncio
async def test_mode_off_writes_disabled_without_any_fetch():
    client = FakeHttpClient({})  # 호출되면 KeyError 대신 None 반환 → fetch() 가 FetchError
    db = FakeDB()
    runner = _runner(client=client, db=db, mode="off")
    run = await runner.run_once()
    assert run["status"] == "disabled"
    assert db.runs[-1]["status"] == "disabled"


@pytest.mark.asyncio
async def test_engine_not_running_writes_that_status():
    client = FakeHttpClient({G0_PATH: ok_body({"running": False, "phase": "idle"})})
    db = FakeDB()
    runner = _runner(client=client, db=db)
    run = await runner.run_once()
    assert run["status"] == "engine_not_running"


@pytest.mark.asyncio
async def test_g0_fetch_error_is_engine_not_running():
    client = FakeHttpClient({G0_PATH: FetchError("boom")})
    db = FakeDB()
    runner = _runner(client=client, db=db)
    run = await runner.run_once()
    assert run["status"] == "engine_not_running"


@pytest.mark.asyncio
async def test_g1_fetch_error_is_g1_failed():
    client = FakeHttpClient({G0_PATH: ok_body(_running_g0()), G1_PATH: FetchError("boom")})
    db = FakeDB()
    runner = _runner(client=client, db=db)
    run = await runner.run_once()
    assert run["status"] == "g1_failed"


@pytest.mark.asyncio
async def test_no_positions_at_all_is_no_targets():
    client = FakeHttpClient({G0_PATH: ok_body(_running_g0()), G1_PATH: ok_body({"items": []})})
    db = FakeDB()
    db.daily_rows["069500"] = [daily_row(BAR_DATE)]
    runner = _runner(client=client, db=db)
    run = await runner.run_once()
    assert run["status"] == "no_targets"
    assert run["bar_date"] == BAR_DATE


@pytest.mark.asyncio
async def test_bar_date_unresolved_when_proxy_has_no_prior_bar():
    client = FakeHttpClient({G0_PATH: ok_body(_running_g0()), G1_PATH: ok_body({"items": []})})
    db = FakeDB()
    db.daily_rows["069500"] = [daily_row(TODAY)]  # 오늘 봉만 있음 — 이전 없음
    runner = _runner(client=client, db=db)
    run = await runner.run_once()
    assert run["status"] == "no_targets"
    assert run["bar_date"] is None


@pytest.mark.asyncio
async def test_unlisted_strategy_item_is_excluded_from_targets():
    item = g1_item(strategy_id="momentum")
    client = FakeHttpClient({G0_PATH: ok_body(_running_g0()), G1_PATH: ok_body({"items": [item]})})
    db = FakeDB()
    db.daily_rows["069500"] = [daily_row(BAR_DATE)]
    runner = _runner(client=client, db=db)
    run = await runner.run_once()
    assert run["n_targets"] == 0
    assert run["status"] == "no_targets"


@pytest.mark.asyncio
async def test_provisional_bar_is_skipped_without_llm_call():
    item = g1_item()
    client = FakeHttpClient({G0_PATH: ok_body(_running_g0()), G1_PATH: ok_body({"items": [item]})})
    db = FakeDB()
    db.daily_rows["069500"] = [daily_row(BAR_DATE)]
    db.daily_rows["005930"] = [daily_row(BAR_DATE, updated_at=PROVISIONAL_AT)]
    db.head_rows["005930"] = {"bas_dd": BAR_DATE, "updated_at": PROVISIONAL_AT}
    openai_client = FakeOpenAI(content='{"action":"hold","exit_score":40}')
    runner = _runner(client=client, db=db, openai_client=openai_client)
    run = await runner.run_once()
    assert run["n_skipped"] == 1
    assert openai_client.calls == 0
    assert db.upserts[-1]["result"] == "skipped"
    assert db.upserts[-1]["reason"] == "provisional_bar"


@pytest.mark.asyncio
async def test_no_bars_for_ticker_is_skipped():
    item = g1_item()
    client = FakeHttpClient({G0_PATH: ok_body(_running_g0()), G1_PATH: ok_body({"items": [item]})})
    db = FakeDB()
    db.daily_rows["069500"] = [daily_row(BAR_DATE)]
    # head_rows["005930"] 없음 → no_bars
    runner = _runner(client=client, db=db, openai_client=FakeOpenAI())
    run = await runner.run_once()
    assert run["n_skipped"] == 1
    assert db.upserts[-1]["reason"] == "no_bars"


@pytest.mark.asyncio
async def test_ok_evaluation_is_persisted_with_action_and_score():
    item = g1_item()
    client = FakeHttpClient({G0_PATH: ok_body(_running_g0()), G1_PATH: ok_body({"items": [item]})})
    db = FakeDB()
    _setup_confirmed(db)
    openai_client = FakeOpenAI(content='{"action":"hold","exit_score":35,"rationale":"보유 유지"}')
    runner = _runner(client=client, db=db, openai_client=openai_client)
    run = await runner.run_once()
    assert run["status"] == "done"
    assert run["n_ok"] == 1
    assert openai_client.calls == 1
    row = db.upserts[-1]
    assert row["result"] == "ok"
    assert row["action"] == "hold"
    assert row["exit_score"] == 35
    assert row["prompt_version"].startswith("exit-v1-gpt-6-luna-")
    assert row["bar_date"] == BAR_DATE


@pytest.mark.asyncio
async def test_already_ok_evaluation_is_not_re_evaluated():
    item = g1_item()
    client = FakeHttpClient({G0_PATH: ok_body(_running_g0()), G1_PATH: ok_body({"items": [item]})})
    db = FakeDB()
    _setup_confirmed(db)
    db.existing[(BAR_DATE, "kojiro", "005930", date(2026, 10, 10), "1")] = {
        "id": 1, "attempts": 1, "result": "ok",
    }
    openai_client = FakeOpenAI(content='{"action":"hold","exit_score":40}')
    runner = _runner(client=client, db=db, openai_client=openai_client)
    run = await runner.run_once()
    assert run["n_ok"] == 1
    assert openai_client.calls == 0, "이미 ok 인 행은 다시 평가하지 않는다"
    assert db.upserts == []


@pytest.mark.asyncio
async def test_failed_evaluation_retried_up_to_max_attempts_then_skipped():
    item = g1_item()
    client = FakeHttpClient({G0_PATH: ok_body(_running_g0()), G1_PATH: ok_body({"items": [item]})})
    db = FakeDB()
    _setup_confirmed(db)
    db.existing[(BAR_DATE, "kojiro", "005930", date(2026, 10, 10), "1")] = {
        "id": 1, "attempts": 3, "result": "failed",  # 이미 3회 소진
    }
    openai_client = FakeOpenAI(content='{"action":"hold","exit_score":40}')
    runner = _runner(client=client, db=db, openai_client=openai_client)
    run = await runner.run_once()
    assert run["n_skipped"] == 1
    assert openai_client.calls == 0
    assert db.upserts == []


@pytest.mark.asyncio
async def test_failed_evaluation_below_max_attempts_is_retried():
    item = g1_item()
    client = FakeHttpClient({G0_PATH: ok_body(_running_g0()), G1_PATH: ok_body({"items": [item]})})
    db = FakeDB()
    _setup_confirmed(db)
    db.existing[(BAR_DATE, "kojiro", "005930", date(2026, 10, 10), "1")] = {
        "id": 1, "attempts": 1, "result": "failed",
    }
    openai_client = FakeOpenAI(content='{"action":"hold","exit_score":40}')
    runner = _runner(client=client, db=db, openai_client=openai_client)
    run = await runner.run_once()
    assert run["n_ok"] == 1
    assert openai_client.calls == 1
    assert db.upserts[-1]["attempts"] == 2


@pytest.mark.asyncio
async def test_no_key_when_openai_client_is_none():
    item = g1_item()
    client = FakeHttpClient({G0_PATH: ok_body(_running_g0()), G1_PATH: ok_body({"items": [item]})})
    db = FakeDB()
    _setup_confirmed(db)
    runner = _runner(client=client, db=db, openai_client=None)
    run = await runner.run_once()
    assert run["n_failed"] == 1
    assert db.upserts[-1]["reason"] == "no_key"


@pytest.mark.asyncio
async def test_daily_call_cap_blocks_further_evaluations_same_day():
    items = [g1_item(ticker=f"00{i:04d}") for i in range(2)]
    client = FakeHttpClient({G0_PATH: ok_body(_running_g0()), G1_PATH: ok_body({"items": items})})
    db = FakeDB()
    db.daily_rows["069500"] = [daily_row(BAR_DATE)]
    for it in items:
        db.daily_rows[it["ticker"]] = [daily_row(BAR_DATE, updated_at=CONFIRMED_AT)]
        db.head_rows[it["ticker"]] = {"bas_dd": BAR_DATE, "updated_at": CONFIRMED_AT}
    openai_client = FakeOpenAI(content='{"action":"hold","exit_score":40}')
    runner = _runner(client=client, db=db, openai_client=openai_client)
    runner._calls_today = 40  # DAILY_CALL_CAP
    runner._calls_day = NOW.date()
    run = await runner.run_once()
    assert run["n_failed"] == 2
    assert all(r["reason"] == "cap_exceeded" for r in db.upserts)


@pytest.mark.asyncio
async def test_schema_error_response_is_failed():
    item = g1_item()
    client = FakeHttpClient({G0_PATH: ok_body(_running_g0()), G1_PATH: ok_body({"items": [item]})})
    db = FakeDB()
    _setup_confirmed(db)
    openai_client = FakeOpenAI(content='{"action":"sell","exit_score":40}')  # 어휘 밖
    runner = _runner(client=client, db=db, openai_client=openai_client)
    run = await runner.run_once()
    assert run["n_failed"] == 1
    assert db.upserts[-1]["reason"] == "schema_error"


@pytest.mark.asyncio
async def test_api_error_from_openai_is_failed():
    item = g1_item()
    client = FakeHttpClient({G0_PATH: ok_body(_running_g0()), G1_PATH: ok_body({"items": [item]})})
    db = FakeDB()
    _setup_confirmed(db)
    openai_client = FakeOpenAI(raise_exc=RuntimeError("down"))
    runner = _runner(client=client, db=db, openai_client=openai_client)
    run = await runner.run_once()
    assert run["n_failed"] == 1
    assert db.upserts[-1]["reason"] == "api_error"


@pytest.mark.asyncio
async def test_inconsistent_output_is_persisted_not_discarded():
    item = g1_item()
    client = FakeHttpClient({G0_PATH: ok_body(_running_g0()), G1_PATH: ok_body({"items": [item]})})
    db = FakeDB()
    _setup_confirmed(db)
    openai_client = FakeOpenAI(content='{"action":"exit","exit_score":20,"rationale":"r"}')
    runner = _runner(client=client, db=db, openai_client=openai_client)
    run = await runner.run_once()
    assert run["n_ok"] == 1
    assert db.upserts[-1]["inconsistent"] is True
    assert db.upserts[-1]["action"] == "exit"


@pytest.mark.asyncio
async def test_one_target_exception_does_not_stop_the_rest():
    good = g1_item(ticker="005930")
    bad = g1_item(ticker="000660", buy_date="not-a-date")  # 파싱 실패 유도
    client = FakeHttpClient({G0_PATH: ok_body(_running_g0()), G1_PATH: ok_body({"items": [good, bad]})})
    db = FakeDB()
    _setup_confirmed(db, ticker="005930")
    openai_client = FakeOpenAI(content='{"action":"hold","exit_score":40}')
    runner = _runner(client=client, db=db, openai_client=openai_client)
    run = await runner.run_once()
    # bad 는 select_targets 단계에서 buy_date 파싱 실패로 이미 걸러진다(대상 1개).
    assert run["n_targets"] == 1
    assert run["n_ok"] == 1
