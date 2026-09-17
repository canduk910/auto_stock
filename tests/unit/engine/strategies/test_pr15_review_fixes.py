"""PR #15 (사이클 48) copilot 재리뷰 지적 2건 시정 — TDD 회귀 가드.

배경: BFB/VCP 0건 매매 결함 시정 PR 에 대한 copilot 재리뷰에서 2건 지적.

지적 ① (표기 정직성, P2) — VCP `ema_long=120` 이 KIS 100일 한도 가드로 런타임 ~75 로 캡됨.
  config·docstring·FUNNEL_STAGES·step_conditions·_check_trend_filter docstring 은 "120" 을
  말하지만 실제 계산은 ~75EMA. "the stated 120EMA behavior is not exercised."
  → team-leader 도메인 판단: 방향 (c) 채택 — 매매 동작 무변경, 표기만 정직화.
    docstring/FUNNEL_STAGES/step_conditions 에 "가드로 ~75 캡됨" 명시. 키 이름(ema150/ema200)
    rename 보류(funnel UI/테스트 호환). config 값 120 유지(진입 빈도 영향 0).
    (cycle301(2026-09-18)이 config 값을 120→200 미너비니 원설계로 되돌렸다 — 100봉 읽기
    에서는 ~75 캡 산식이 그대로 적용된다.)

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

from tests.unit.engine.strategies.test_cycle300_daily_depth_switch import (
    _capture_prepare_fetch,
    _kis_candles,
    _make_vcp,
)

pytestmark = pytest.mark.unit

_xfail_cycle108 = pytest.mark.xfail(
    strict=False,
    reason="사이클 108 stock_master 전환으로 BFB volume-rank 호출 패턴 폐기 — "
           "과거 계약 영속 보존 (사이클 97 K-2 패턴 답습)",
)


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
@_xfail_cycle108
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


@_xfail_cycle108
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


@_xfail_cycle108
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
@pytest.mark.asyncio
async def test_vcp_effective_ema_long_capped_in_default_cap100_mode():
    """VCP 실효 장기선 캡 — cycle301(2026-09-18, 사용자 승인 D3·D4)이 뒤집은 세계.

    **옛 전제(폐기)**: "`ema_long` 이 120 이어야 KIS 100일 한도 안에서 계산 가능하다."
    KIS `FHKST03010100` 의 100일 한도는 **호출당** 한도였을 뿐이고, cycle299(윈도우
    분할 backfill 로 일봉 적재를 225영업일까지 확장)와 cycle300(DB 읽기 클램프를
    100→400 으로 올리고 `daily_fetch_depth_mode` 스위치를 신설)이 그 한도를 걷어냈다.
    지금 `ema_long` 은 200(미너비니 원설계)이고, ~75 캡은 "KIS 한도" 가 아니라 **VCP
    전략이 그날 실제로 요청·수신한 보유 봉 수**(`daily_fetch_depth_mode` 가 그 요청
    깊이를 정한다)에서 나온다는 것이 새 명제다.

    **cycle301 신규 가드와의 중복 확인** — `test_cycle301_vcp_default_alignment.py`
    의 `test_g301_3_effective_ema_long_follows_available_rows` 가 이미 실제
    `_check_trend_filter` 인자 경로로 "보유 행수가 캡을 정한다" 는 산식 자체를 100행
    →75 · 225행→200 두 값 모두 봉인하지만, 그쪽은 **`daily_fetch_depth_mode="full"`
    을 명시**해서 잰다. 이 테스트는 그 파일이 안 재는 각도 — **오늘 운영이 실제로
    쓰는 기본값 `"cap100"`**(전환 안 한 다크런치 상태, `strategies/CLAUDE.md` VCP
    절)에서 같은 산식이 그대로 적용됨 — 을 잰다. `ema_long==200`/`ema_mid==150`
    값 자체의 정적 단언은 cycle301 G-301-2 가 이미 더 강하게 재고 있어 여기서
    다시 하지 않는다.

    산식(`prepare()`) = `effective_ema_long = min(ema_long, available_len -
    uptrend_days(20) - 5)`. cap100 기본값은 `fetch_days=100` 을 요청하고,
    DB 가 정확히 100행을 돌려주면 `available_len=100` → `min(200, 100-20-5)=75`.
    측정은 `_check_trend_filter` 를 스파이로 감싸 **실제로 넘어온 인자**를 읽는다
    (산식을 테스트에 복제하지 않는다).
    """
    seen_eff: list[int | None] = []
    strat = _make_vcp(base_max_days=75, max_scan_stocks=10)  # daily_fetch_depth_mode 기본값(cap100)
    real_filter = type(strat)._check_trend_filter

    def _spy(self, candles, *, effective_ema_long=None):
        seen_eff.append(effective_ema_long)
        return real_filter(self, candles, effective_ema_long=effective_ema_long)

    with patch.object(type(strat), "_check_trend_filter", new=_spy):
        seen_fetch = await _capture_prepare_fetch(strat, _kis_candles(100))

    assert seen_fetch["days"] == 100, (
        f"cap100 기본값에서 fetch_days={seen_fetch['days']} (기대 100 — 배포 전후 byte 동일)"
    )
    assert seen_eff and seen_eff[0] == 75, (
        f"cap100 기본값 100행 응답에서 effective_ema_long={seen_eff[0] if seen_eff else None} "
        "(기대 75 = min(200, 100-20-5)) — 캡의 출처가 KIS 한도가 아니라 보유 행수임을 "
        "실제 코드 경로로 확인"
    )


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
    → config `ema_long`(PR15 당시 120, cycle301 이후 200)이 하드 표기되면 100봉 읽기의
    실제 effective ~75 와 불일치한다. effective 표기로 정직화.
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
