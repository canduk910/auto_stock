"""사이클 F Red — `GET /api/strategies/te` 전용 엔드포인트 + 5분 캐시 회귀 가드.

명세: `_workspace/red/_behaviors_cycleF_te_rr_20260802.md` (F-B7, F-B8)
자문: §138 (장중 DB 부하 → 전용 엔드포인트 + 5분 TTL 프로세스 캐시).

대상: `src.routes.strategies.get_strategies_te(months: int = 3) -> ApiResponse`.
- **등록된 전략 전부**(`trading_scheduler.registry.all()`, 지금 7개) 각각 `get_trade_pairs(strategy)` →
  `compute_te_rr(...)` → asdict 리스트 반환. 기대값도 같은 등록 명부에서 읽는다(리팩토링 카드 #1 —
  7개 고정 목록이면 여덟째 전략을 등록하는 순간 이 파일이 거짓으로 붉는다). 파일 명부
  (`tests/_strategy_census.py`)가 아니라 **등록 축**이다 — 엔드포인트가 등록 축을 돈다.
- **5분 TTL 프로세스 캐시** (months 키, `time.monotonic`): TTL 내 재호출 시
  get_trade_pairs 재조회 0 (기존 `/api/strategies` 60s 폴링 미변경).
- **months 파라미터** → window_days = months × 30 (3→90 / 6→180). 캐시 키 분리.
- **graceful(F-B8)**: 전략 1개 계산 실패 → 그 전략 빈 디폴트, 나머지 진행.

검증 패턴: TestClient 지양, 라우트 함수 직접 await (사이클 127 anyio portal hang 차단).

RED 상태: `get_strategies_te` / `invalidate_te_cache` / te_metrics 모듈 부재 →
ImportError·AttributeError 로 전 케이스 실패.
"""
from __future__ import annotations

import pytest

from tests._strategy_census import MIN_STRATEGIES

pytestmark = pytest.mark.unit

#: 등록 명부 하한(탐지기 무효화 방지) — 등록이 비면 `len(data) == len(regs)` 가 0 == 0 으로 공허해진다.
#: 기대값은 등록 축에서 읽지만 **하한 값만** 파일 명부와 공유한다 — 전략을 빼는 사이클이 한 곳만 내리면 되게.
_MIN_REGISTERED = MIN_STRATEGIES


def _registered_ids(st) -> list[str]:
    """엔드포인트가 도는 것과 같은 등록 명부(`trading_scheduler.registry.all()`)."""
    ids = [s.strategy_id for s in st.trading_scheduler.registry.all()]
    assert len(ids) >= _MIN_REGISTERED, (
        f"등록 전략 {len(ids)}개 < {_MIN_REGISTERED} — 등록 경로가 바뀌었는지 확인하라: {ids}"
    )
    return ids


@pytest.fixture(autouse=True)
def _reset_te_cache():
    """전용 TE 캐시 격리 — 각 테스트 시작/종료 시 무효화 (convention: invalidate_*)."""
    from src.routes import strategies as st

    st.invalidate_te_cache()
    yield
    st.invalidate_te_cache()


# ===========================================================================
# F-B7 — 등록 전략 전부(지금 7개) 리스트 반환
# ===========================================================================
@pytest.mark.asyncio
async def test_te_endpoint_returns_all_seven_strategies(monkeypatch):
    """엔드포인트가 등록된 전략 전부(지금 7개) 각각의 TeRrMetrics(asdict) 리스트를 반환."""
    from src.routes import strategies as st

    async def _fake_pairs(strategy=None, ticker=None):
        return []  # 모든 전략 빈 이력 (윈도우 내 closed 0건)

    monkeypatch.setattr(st, "get_trade_pairs", _fake_pairs, raising=True)

    resp = await st.get_strategies_te(months=3)

    assert resp.success is True
    data = resp.data
    assert isinstance(data, list), "data 는 전략별 리스트"
    registered = _registered_ids(st)
    assert len(data) == len(registered), "등록 전략마다 1항목"

    ids = {d["strategy_id"] for d in data}
    assert ids == set(registered), f"등록 명부 {sorted(registered)} ≠ 응답 {sorted(ids)}"

    # 각 항목은 TeRrMetrics asdict — 핵심 필드 존재 계약
    sample = data[0]
    for key in (
        "strategy_id",
        "n",
        "win",
        "loss",
        "even",
        "win_rate",
        "te_pct",
        "te_krw_avg",
        "realized_sum_krw",
        "rr",
        "required_rr",
        "rr_margin",
        "rr_available",
        "sample_tier",
        "verdict",
        "structure_tag",
        "single_trade_dominant",
    ):
        assert key in sample, f"TeRrMetrics asdict 필드 누락: {key}"


# ===========================================================================
# F-B7 — 5분 TTL 프로세스 캐시 (monotonic mock)
# ===========================================================================
@pytest.mark.asyncio
async def test_te_endpoint_5min_cache_skips_db(monkeypatch):
    """TTL(300s) 내 재호출 → get_trade_pairs 재조회 0. TTL 경과 → 재조회."""
    from src.routes import strategies as st

    call_count = {"n": 0}

    async def _counting_pairs(strategy=None, ticker=None):
        call_count["n"] += 1
        return []

    monkeypatch.setattr(st, "get_trade_pairs", _counting_pairs, raising=True)

    clock = {"t": 1000.0}
    monkeypatch.setattr(st.time, "monotonic", lambda: clock["t"], raising=False)

    await st.get_strategies_te(months=3)
    first = call_count["n"]
    assert first == len(_registered_ids(st)), "첫 호출 = 등록 전략 수 × get_trade_pairs 1회"

    clock["t"] = 1200.0  # 200s 경과 (< 300s TTL)
    await st.get_strategies_te(months=3)
    assert call_count["n"] == first, "TTL 내 재호출 = 캐시 hit (get_trade_pairs 추가 0)"

    clock["t"] = 1400.0  # 400s 경과 (> 300s TTL) → 만료
    await st.get_strategies_te(months=3)
    assert call_count["n"] == first * 2, "TTL 만료 후 재조회"


# ===========================================================================
# F-B7 — months 파라미터 → window_days 매핑 + 캐시 키 분리
# ===========================================================================
@pytest.mark.asyncio
async def test_te_endpoint_months_maps_window_and_separates_cache_key(monkeypatch):
    """months → window_days = months × 30. 다른 months = 별개 캐시 키."""
    from src.engine.te_metrics import TeRrMetrics
    from src.routes import strategies as st

    async def _fake_pairs(strategy=None, ticker=None):
        return []

    monkeypatch.setattr(st, "get_trade_pairs", _fake_pairs, raising=True)

    captured_windows: list[int] = []

    def _fake_compute(pairs, *, now, window_days=90, strategy_id="", costs_available=True):
        captured_windows.append(window_days)
        return TeRrMetrics(
            strategy_id=strategy_id,
            n=0,
            win=0,
            loss=0,
            even=0,
            win_rate=0.0,
            avg_win_pct=None,
            avg_loss_pct=None,
            te_pct=0.0,
            te_krw_avg=0.0,
            realized_sum_krw=0.0,
            rr=None,
            required_rr=None,
            rr_margin=None,
            rr_available=False,
            sample_tier="insufficient",
            verdict="undecided",
            structure_tag=None,
            single_trade_dominant=False,
        )

    monkeypatch.setattr(st, "compute_te_rr", _fake_compute, raising=True)

    clock = {"t": 5000.0}
    monkeypatch.setattr(st.time, "monotonic", lambda: clock["t"], raising=False)

    await st.get_strategies_te(months=3)
    assert captured_windows, "compute_te_rr 호출 발생"
    assert all(w == 90 for w in captured_windows), "months=3 → window_days=90"
    captured_windows.clear()

    # 동일 시각(캐시 TTL 내) 이지만 months 가 다르면 별개 키 → 재계산
    await st.get_strategies_te(months=6)
    assert all(w == 180 for w in captured_windows), "months=6 → window_days=180"
    assert len(captured_windows) == len(_registered_ids(st)), "months=3 캐시 재사용 안 함 (키 분리)"


# ===========================================================================
# F-B8 — 전략별 예외 격리 (graceful)
# ===========================================================================
@pytest.mark.asyncio
async def test_te_endpoint_isolates_per_strategy_exception(monkeypatch):
    """전략 1개 계산 실패 → 그 전략 빈 디폴트(n=0), 나머지 정상 진행."""
    from src.routes import strategies as st

    async def _pairs_raises_for_momentum(strategy=None, ticker=None):
        if strategy == "momentum":
            raise RuntimeError("DB 일시 장애")
        return []

    monkeypatch.setattr(st, "get_trade_pairs", _pairs_raises_for_momentum, raising=True)

    resp = await st.get_strategies_te(months=3)

    assert resp.success is True
    data = resp.data
    assert len(data) == len(_registered_ids(st)), "실패 전략도 항목 유지 (전략 누락 금지)"

    by_id = {d["strategy_id"]: d for d in data}
    assert "momentum" in by_id, "실패 전략 항목 존재"
    assert by_id["momentum"]["n"] == 0, "실패 시 빈 디폴트로 격리"
    assert by_id["momentum"]["verdict"] == "undecided"
    # 나머지 전략은 정상 진행
    assert {"donchian_swing", "kojiro"}.issubset(by_id.keys())
