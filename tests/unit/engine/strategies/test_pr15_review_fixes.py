"""PR #15 (사이클 48) copilot 재리뷰 지적 2건 시정 — TDD 회귀 가드.

배경: BFB/VCP 0건 매매 결함 시정 PR 에 대한 copilot 재리뷰에서 2건 지적.

지적 ① (표기 정직성, P2) — VCP `ema_long=120` 이 KIS 100일 한도 가드로 런타임 ~75 로 캡됨.
  config·docstring·FUNNEL_STAGES·step_conditions·_check_trend_filter docstring 은 "120" 을
  말하지만 실제 계산은 ~75EMA. "the stated 120EMA behavior is not exercised."
  → team-leader 도메인 판단: 방향 (c) 채택 — 매매 동작 무변경, 표기만 정직화.
    docstring/FUNNEL_STAGES/step_conditions 에 "가드로 ~75 캡됨" 명시. 키 이름(ema150/ema200)
    rename 보류(funnel UI/테스트 호환). config 값 120 유지(진입 빈도 영향 0).

지적 ② (관찰성) — BFB `_scan_universe` 가 빈 유니버스 시 조용히 `[]` 반환.
  컨벤션(strategies/CLAUDE.md "0종목 확정 시 ERROR 로그 + system_logs 기록") 위반.
  VB/LTV 는 구현됨. 이 PR 이 바로 "universe 0" 진단 목적이라 누락 시 동일 결함 재발견 실패.
  → rank API 0건(rank_items 빈) vs 필터 전부 탈락(rank_items>0 but filtered=0) 구분 로깅.

회귀 가드 원칙: 빈 유니버스가 아닐 때 BFB 동작 무변경. ① 매매 동작(진입 빈도) 무변경.
"""
from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.unit


def _volume_rank_item(ticker: str, name: str, price: int, listed: int,
                      prdy_vol: int, prdy_vrss: int = 0) -> dict:
    """KIS volume-rank(FHPST01710000) output 단일 항목 모사."""
    return {
        "mksc_shrn_iscd": ticker,
        "hts_kor_isnm": name,
        "stck_prpr": str(price),
        "lstn_stcn": str(listed),
        "prdy_vol": str(prdy_vol),
        "prdy_vrss": str(prdy_vrss),
    }


def _make_bfb():
    from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
    from src.engine.strategy_base import StrategyConfig
    return BullFlagBreakoutStrategy(
        StrategyConfig(strategy_id="bull_flag_breakout", name="눌림목 돌파", weight=0.0)
    )


# ===========================================================================
# 지적 ② — BFB 빈 유니버스 ERROR 로그 + system_logs (관찰성)
# ===========================================================================
@pytest.mark.asyncio
async def test_bfb_empty_universe_rank_api_empty_emits_error_log(monkeypatch, caplog):
    """rank API 가 0건(전 BLNG 빈 응답) → ERROR 로그 + system_logs + '비어있음' 사유 구분."""
    from src.engine.strategies import bull_flag_breakout as bfb_mod

    async def _fake_kis_get(path, tr_id, params):
        return {"output": []}

    monkeypatch.setattr(bfb_mod, "kis_get", _fake_kis_get, raising=False)
    from src.api import base as base_mod
    monkeypatch.setattr(base_mod, "kis_get", _fake_kis_get, raising=False)
    from src.engine import scanner
    monkeypatch.setattr(scanner, "ticker_names", {})

    write_log_mock = AsyncMock()
    strat = _make_bfb()
    with patch("src.db.system_logs.write_log", write_log_mock):
        with caplog.at_level("ERROR"):
            result = await strat._scan_universe()

    assert result == []
    # ERROR 로그 + system_logs 1회
    write_log_mock.assert_called_once()
    call_args = write_log_mock.call_args
    assert call_args.args[0] == "ERROR"
    msg = call_args.args[1]
    assert "0종목" in msg
    # rank API 0건 vs 필터 탈락 구분 — rank 비었음을 명시
    assert ("비어" in msg or "API" in msg), (
        f"rank API 0건 사유가 메시지에 구분 표기 필요. msg={msg!r}"
    )


@pytest.mark.asyncio
async def test_bfb_empty_universe_all_filtered_emits_error_log(monkeypatch, caplog):
    """rank API 는 종목 반환했으나 시총/거래대금 필터 전부 탈락 → ERROR + 후보 수 명시."""
    from src.engine.strategies import bull_flag_breakout as bfb_mod

    async def _fake_kis_get(path, tr_id, params):
        # 거래대금 빈약(1000 × 100 = 10만원 << 20억) → 전부 필터 탈락
        return {
            "output": [
                _volume_rank_item("100001", "빈약1", 1000, 100_000_000, prdy_vol=100),
                _volume_rank_item("100002", "빈약2", 1000, 100_000_000, prdy_vol=100),
            ]
        }

    monkeypatch.setattr(bfb_mod, "kis_get", _fake_kis_get, raising=False)
    from src.api import base as base_mod
    monkeypatch.setattr(base_mod, "kis_get", _fake_kis_get, raising=False)
    from src.engine import scanner
    monkeypatch.setattr(scanner, "ticker_names", {})

    write_log_mock = AsyncMock()
    strat = _make_bfb()
    with patch("src.db.system_logs.write_log", write_log_mock):
        with caplog.at_level("ERROR"):
            result = await strat._scan_universe()

    assert result == []
    write_log_mock.assert_called_once()
    call_args = write_log_mock.call_args
    assert call_args.args[0] == "ERROR"
    msg = call_args.args[1]
    assert "0종목" in msg
    # 필터 전부 탈락 — 후보 수(2) 가 메시지에 포함되어 rank API 0건과 구분
    assert "2" in msg, (
        f"필터 전부 탈락 시 후보 수가 메시지에 포함되어 rank API 0건과 구분 필요. msg={msg!r}"
    )


@pytest.mark.asyncio
async def test_bfb_non_empty_universe_no_error_log(monkeypatch, caplog):
    """빈 유니버스가 아니면 ERROR 로그/system_logs 호출 없음 — 행위 보존."""
    from src.engine.strategies import bull_flag_breakout as bfb_mod

    async def _fake_kis_get(path, tr_id, params):
        # 삼성전자: 65000 × 5M = 3,200억+ >> 20억 → 통과
        return {
            "output": [
                _volume_rank_item("005930", "삼성전자", 65000, 5_000_000_000,
                                  prdy_vol=5_000_000, prdy_vrss=0),
            ]
        }

    monkeypatch.setattr(bfb_mod, "kis_get", _fake_kis_get, raising=False)
    from src.api import base as base_mod
    monkeypatch.setattr(base_mod, "kis_get", _fake_kis_get, raising=False)
    from src.engine import scanner
    monkeypatch.setattr(scanner, "ticker_names", {})

    write_log_mock = AsyncMock()
    strat = _make_bfb()
    with patch("src.db.system_logs.write_log", write_log_mock):
        with caplog.at_level("ERROR"):
            result = await strat._scan_universe()

    assert "005930" in result
    # 정상 유니버스 → ERROR system_logs 미호출 (행위 보존)
    write_log_mock.assert_not_called()


# ===========================================================================
# 지적 ① — VCP ema_long=120 → 런타임 ~75 캡 표기 정직성 (방향 c)
# ===========================================================================
def test_vcp_effective_ema_long_capped_at_kis_limit():
    """회귀 가드: config ema_long=120 이지만 100일 응답 시 effective 가 ~75 로 캡됨.

    available_len=100, uptrend_days=20 → effective = min(120, 100-20-5) = 75.
    이 캡 동작은 copilot 지적의 근거이자 의도된 안전 가드. 동작 자체는 유지.
    """
    from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy

    p = VcpBreakoutStrategy.DEFAULT_PARAMS
    ema_long = p["ema_long"]
    uptrend_days = p["long_ema_uptrend_days"]
    available_len = 100  # KIS 단일호출 한도
    effective = min(ema_long, available_len - uptrend_days - 5)
    assert effective == 75, (
        f"100일 한도에서 ema_long=120 은 effective 75 로 캡됨. 실제={effective}"
    )
    # config 값 120 은 유지 (방향 c — 매매 동작 무변경)
    assert ema_long == 120


def test_vcp_trend_filter_docstring_documents_kis_cap():
    """`_check_trend_filter` docstring 이 KIS 100일 한도로 ~75 캡됨을 명시 (정직성)."""
    from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy

    doc = VcpBreakoutStrategy._check_trend_filter.__doc__ or ""
    assert "75" in doc, (
        "docstring 이 effective_ema_long 가 KIS 100일 한도로 ~75 로 캡됨을 명시 필요. "
        f"현재 docstring 은 120 만 언급. doc={doc!r}"
    )


def test_vcp_funnel_stage_label_documents_runtime_ema():
    """FUNNEL_STAGES EMA 정렬 단계 라벨이 런타임 실제 EMA(~75 캡)를 정직 표기.

    config 50/60/120 표기지만 런타임 50/60/75. 라벨이 캡을 명시해야 'stated 120 not
    exercised' 지적 해소.
    """
    from src.engine.strategies.vcp_breakout import FUNNEL_STAGES

    # FUNNEL_STAGES[3] = EMA 정렬 단계
    ema_stage = FUNNEL_STAGES[3]
    label = ema_stage.step_name
    assert isinstance(label, str)
    # 라벨/주변에 캡 사실(~75 또는 'KIS 한도' 또는 'effective')이 드러나야 함
    src = inspect.getsource(__import__("src.engine.strategies.vcp_breakout",
                                       fromlist=["vcp_breakout"]))
    # FUNNEL_STAGES 정의 주석 또는 step_conditions 에 캡 명시
    assert ("75" in src and "effective" in src.lower()), (
        "FUNNEL_STAGES 또는 step_conditions 에 effective EMA ~75 캡 명시 필요"
    )


def test_vcp_step_conditions_trend_filter_documents_cap():
    """추세필터 단계 step_conditions(FUNNEL_STAGES[3] 위임)가 런타임 effective EMA 를 표기.

    기존: f"종가 > {ema_short}EMA > {ema_mid}EMA > {ema_long}EMA + {ema_long}EMA {uptrend}일 우상향"
    → ema_long=120 이 하드 표기되어 실제 ~75 와 불일치. effective 표기로 정직화.
    """
    src = inspect.getsource(
        __import__("src.engine.strategies.vcp_breakout", fromlist=["vcp_breakout"])
    )
    # prepare() 의 FUNNEL_STAGES[3] step_conditions 에 effective 또는 ~75 캡 언급
    # (정확 텍스트는 구현 재량 — 'effective' 또는 'KIS 한도' 또는 '~75' 중 하나)
    import re
    # step_conditions 가 단순히 "{ema_long}EMA" 만 박지 않고 캡을 설명하는지
    assert re.search(r"effective|KIS\s*100|~?75|한도", src), (
        "추세필터 step_conditions 가 effective EMA 캡을 표기해야 함"
    )
