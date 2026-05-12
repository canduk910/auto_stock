"""I3 Red — `_boot()` 후 보유 + 익일청산 후보 ticker 를 stock_master 에 eager 갱신.

Phase G(2026-05-11) 의 lazy 갱신 한계:
- `_strategy_exchange_async` 가 매수/매도 직전 `stock_master.get(ticker)` 로 lazy 조회.
- 첫 사이클(캐시 miss) 은 전략 기본 exchange(SOR/NXT) 그대로 발사 → KIS 가 NXT 미등록 종목을 거부.
- 2026-05-12 09:00:12 KST 계양전기(012200) NEXT_DAY_CLEAR 매도 시 EXCG_ID_DVSN_CD=SOR 로 발사 → 거부.

I3 요구 행위:
1. _boot() 끝부분에서 `_eager_refresh_stock_master_for_held_positions()` 호출.
2. 대상: 모든 전략 보유 포지션 + `_pending_next_day_clear` set 의 ticker (합집합, dedupe).
3. ticker 형식: 6자리 영숫자(`isalnum()`)만 — 사후처리 규약. 5자리/특수문자/소문자 OK 는 영숫자 통과.
4. 24h TTL fresh(`is_stale=False`)면 KIS 호출 skip → 불필요한 호출 차단.
5. 종목별 KIS 호출 실패는 흡수 + 다음 종목 계속 + WARNING 로그. total 카운트 정확.
6. parallel 금지 — sequential await (보통 10개 미만, Rate Limit 안전).
7. 보유 0종목 → KIS 호출 0건, upsert 0건.

이 테스트는 `_eager_refresh_stock_master_for_held_positions` 를 직접 호출해 단위 단계로 검증한다.
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from src.engine.strategy_base import Position
from src.models.stock import StockBasics

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------
def _seed_position(strategy, ticker, *, is_next_day: bool = False):
    """전략에 단일 포지션 시드."""
    buy_dt = date.today() - timedelta(days=1) if is_next_day else date.today()
    strategy.state.positions[ticker] = Position(
        ticker=ticker,
        buy_price=10_000,
        quantity=10,
        order_no="BOOT-EAGER-SEED",
        strategy_id=strategy.strategy_id,
        buy_date=buy_dt,
        high_since_buy=10_000,
    )


@pytest.fixture
def stub_stock_master(monkeypatch: pytest.MonkeyPatch):
    """src.db.stock_master 모듈을 stub.

    - is_stale: ticker → bool 매핑으로 응답
    - upsert_one: 호출 인자 추적
    - inquire_stock_basics: ticker → StockBasics 또는 예외 매핑
    """
    state = SimpleNamespace(
        stale_map={},          # ticker → bool (True = stale → KIS 호출 필요)
        upsert_calls=[],       # 누적 호출 ticker
        kis_calls=[],          # inquire_stock_basics 호출 ticker
        kis_error_map={},      # ticker → Exception (있으면 raise)
    )

    async def fake_is_stale(ticker: str, max_age_hours: int = 24) -> bool:
        return state.stale_map.get(ticker, True)

    async def fake_upsert_one(basics: StockBasics) -> None:
        state.upsert_calls.append(basics.ticker)

    async def fake_inquire(pdno: str) -> StockBasics:
        state.kis_calls.append(pdno)
        if pdno in state.kis_error_map:
            raise state.kis_error_map[pdno]
        return StockBasics(
            ticker=pdno,
            name=f"NAME-{pdno}",
            excg_dvsn_cd="02",
            nxt_tradable=True,
            krx_halted=False,
            admin_item=False,
            raw={},
        )

    import src.db.stock_master as _sm
    import src.api.condition as _cond

    monkeypatch.setattr(_sm, "is_stale", fake_is_stale)
    monkeypatch.setattr(_sm, "upsert_one", fake_upsert_one)
    monkeypatch.setattr(_cond, "inquire_stock_basics", fake_inquire)
    # scheduler 가 inline import 한다는 가정 — 모듈 attr 패치로 충분
    return state


# ---------------------------------------------------------------------------
# Case A — 보유 3종목 + 익일청산 1종목 → 합집합 4건 upsert
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_eager_refresh_covers_held_and_pending_next_day_clear(
    scheduler_env,
    stub_stock_master,
):
    """보유 3종목 (서로 다른 전략) + `_pending_next_day_clear` 의 1종목.

    중복은 dedupe — 보유 종목과 pending 이 같은 ticker 면 1건만.
    """
    sched = scheduler_env.scheduler
    momentum = sched.registry.get("momentum")
    vb = sched.registry.get("volatility_breakout")
    donchian = sched.registry.get("donchian_swing")

    _seed_position(momentum, "012200", is_next_day=True)
    _seed_position(vb, "005930")
    _seed_position(donchian, "000660")

    # _pending_next_day_clear 에 새로운 종목 1개 추가 — 보유엔 없는 종목 (테스트 명세)
    sched._pending_next_day_clear.add(("035720", "momentum"))

    # 모두 stale (캐시 miss) — 모두 KIS 호출 발생해야 함
    for t in ("012200", "005930", "000660", "035720"):
        stub_stock_master.stale_map[t] = True

    await sched._eager_refresh_stock_master_for_held_positions()

    # 4종목 모두 KIS 조회 + upsert (정렬 무관, set 비교)
    assert set(stub_stock_master.kis_calls) == {"012200", "005930", "000660", "035720"}
    assert set(stub_stock_master.upsert_calls) == {"012200", "005930", "000660", "035720"}


# ---------------------------------------------------------------------------
# Case B — 일부 종목 fresh (24h TTL 미경과) → KIS 호출 skip
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_eager_refresh_skips_fresh_tickers(
    scheduler_env,
    stub_stock_master,
):
    """24h 이내 갱신된 종목은 `is_stale=False` → KIS 호출 안 함."""
    sched = scheduler_env.scheduler
    momentum = sched.registry.get("momentum")
    _seed_position(momentum, "012200")
    _seed_position(momentum, "005930")
    _seed_position(momentum, "000660")

    # 005930 만 fresh, 나머지는 stale
    stub_stock_master.stale_map["012200"] = True
    stub_stock_master.stale_map["005930"] = False
    stub_stock_master.stale_map["000660"] = True

    await sched._eager_refresh_stock_master_for_held_positions()

    assert "005930" not in stub_stock_master.kis_calls, "fresh 종목은 KIS 호출 skip"
    assert set(stub_stock_master.kis_calls) == {"012200", "000660"}
    assert "005930" not in stub_stock_master.upsert_calls


# ---------------------------------------------------------------------------
# Case C — KIS 호출 실패 1종목 → WARNING 로그 + 다른 종목 계속
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_eager_refresh_isolates_kis_failure(
    scheduler_env,
    stub_stock_master,
):
    """종목 1개의 KIS 호출이 실패해도 다른 종목 계속, total 카운트 정확."""
    sched = scheduler_env.scheduler
    momentum = sched.registry.get("momentum")
    _seed_position(momentum, "012200")
    _seed_position(momentum, "005930")
    _seed_position(momentum, "000660")

    # 모두 stale
    for t in ("012200", "005930", "000660"):
        stub_stock_master.stale_map[t] = True

    # 005930 만 KIS 호출 실패
    stub_stock_master.kis_error_map["005930"] = RuntimeError("KIS timeout")

    await sched._eager_refresh_stock_master_for_held_positions()

    # 실패한 005930 는 upsert 안 됨, 나머지는 정상 upsert
    assert set(stub_stock_master.upsert_calls) == {"012200", "000660"}
    # KIS 호출은 3건 모두 시도됐어야 함 (실패도 호출은 발생)
    assert set(stub_stock_master.kis_calls) == {"012200", "005930", "000660"}

    # WARNING 로그 1행 노출 — 실패 종목 표시
    warn_logs = [
        log for log in scheduler_env.calls.write_log
        if log["level"] == "WARNING" and "stock_master_eager" in log["message"]
    ]
    assert any("005930" in log["message"] for log in warn_logs), (
        f"실패 ticker WARNING 로그 누락: {warn_logs}"
    )


# ---------------------------------------------------------------------------
# Case D — 보유 0종목 + pending 0종목 → KIS 호출 0건
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_eager_refresh_noop_when_no_positions(
    scheduler_env,
    stub_stock_master,
):
    """보유 + pending 모두 비면 KIS / upsert 호출 0건."""
    sched = scheduler_env.scheduler
    # 어떤 전략에도 포지션 없음, _pending_next_day_clear 비어있음
    assert all(len(s.state.positions) == 0 for s in sched.registry.all())
    assert len(sched._pending_next_day_clear) == 0

    await sched._eager_refresh_stock_master_for_held_positions()

    assert stub_stock_master.kis_calls == []
    assert stub_stock_master.upsert_calls == []


# ---------------------------------------------------------------------------
# Case E — ticker 형식 invalid → 대상에서 제외
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_eager_refresh_filters_invalid_tickers(
    scheduler_env,
    stub_stock_master,
):
    """5자리/특수문자/공백/너무 긴 ticker 는 제외. 6자리 영숫자만 통과."""
    sched = scheduler_env.scheduler
    momentum = sched.registry.get("momentum")

    # 유효: 6자리 영숫자 (대문자 알파벳 포함 — ETN/신주인수권)
    _seed_position(momentum, "012200")
    _seed_position(momentum, "K12345")  # 영숫자 6자리 — 통과
    # 무효: 길이 5
    _seed_position(momentum, "01220")
    # 무효: 길이 7
    _seed_position(momentum, "0122000")
    # 무효: 특수문자
    _seed_position(momentum, "012-20")

    # 무효 ticker 가 pending 에도 있어도 제외
    sched._pending_next_day_clear.add(("01@200", "momentum"))

    for t in ("012200", "K12345", "01220", "0122000", "012-20", "01@200"):
        stub_stock_master.stale_map[t] = True

    await sched._eager_refresh_stock_master_for_held_positions()

    # 6자리 영숫자만 통과
    assert set(stub_stock_master.kis_calls) == {"012200", "K12345"}
    assert set(stub_stock_master.upsert_calls) == {"012200", "K12345"}
