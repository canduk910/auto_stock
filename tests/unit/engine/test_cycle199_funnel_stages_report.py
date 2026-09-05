"""사이클 199 (E-1) — 일일 리포트 전략별 funnel 단계별 노출 + 0신호 자동 판정.

출처:
- `_workspace/ai_advisory_review/2026-07-09_3day_consolidation.md` §6-4 E-1 (최우선)
- `_workspace/domain_consult/cycle198_pattern_strictness_korea.md` 후속검증 #2
  (VCP step5 EMA 정렬 생존 수 노출 = EMA 축소 vs 순수 희소 분리 판정 근거)

배경:
- 현재 `metrics["strategy_funnel"]` = coarse 3-count `{signals, orders, fills}` 뿐 →
  AI 가 "왜 0신호인지" (패턴 희소 vs 후보 부족) 못 봄.
- 풍부한 per-step funnel 은 `strategy_funnel_snapshots` DB (사이클 170/175) 에 있음.
  → 신규 `_collect_strategy_funnel_stages(target_date)` 가 `list_snapshots` 로 읽어
    전략별 steps + verdict (패턴희소 / 후보부족 / 후보준비완료 / 미상 / 기록없음) 산출.

순수 관찰성 (매매 무관). log_analysis_engine 은 8영역 밖.

**Red 상태**: 현재 코드에 `_collect_strategy_funnel_stages` 부재 →
AttributeError. `list_snapshots` import 부재.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.engine import log_metrics_collector as lae  # cycle259 카드 ⑦ — 이동처

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# 헬퍼 — strategy_funnel_snapshots row 합성
# ---------------------------------------------------------------------------
def _snap(
    strategy_id: str,
    step_no: int,
    step_name: str,
    survived_count: int,
    excluded_count: int = 0,
) -> dict:
    """list_snapshots 가 반환하는 row 의 최소 키."""
    return {
        "strategy_id": strategy_id,
        "step_no": step_no,
        "step_name": step_name,
        "survived_count": survived_count,
        "excluded_count": excluded_count,
    }


def _install_snapshots(monkeypatch, rows: list[dict]) -> None:
    """lae.list_snapshots 를 stub 으로 교체 (target_date 무관 rows 반환).

    `_collect_strategy_funnel_stages` 는 `list_snapshots` 를 lae 네임스페이스로
    참조 (`from src.db.strategy_funnel import list_snapshots`) 하므로 module attr
    교체로 충분.
    """
    async def _fake(*_a, **_kw):
        return list(rows)

    monkeypatch.setattr(lae, "list_snapshots", _fake, raising=False)


_TARGET = date(2026, 7, 9)


# ---------------------------------------------------------------------------
# (1) 패턴희소 판정 — BFB 유형 (필터 통과 다수 → 폴 2 → 플래그 0)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_bfb_pattern_scarce_verdict(monkeypatch):
    """BFB 유형: step5 폴 2 → step6 플래그 0 (패턴 단계 붕괴) → 패턴희소.

    실측 구조: step1 유니버스47 → step2 필터47 → step3 차단16 → step4 일봉16
    → step5 폴2 → step6 플래그0 → step9 최종0.
    """
    rows = [
        _snap("bull_flag_breakout", 1, "원천 유니버스 후보", 47),
        _snap("bull_flag_breakout", 2, "시총+거래대금 컷 통과", 47),
        _snap("bull_flag_breakout", 3, "1단계 진입 차단 통과", 16),
        _snap("bull_flag_breakout", 4, "일봉 fetch 성공", 16),
        _snap("bull_flag_breakout", 5, "폴(pole) 검출", 2),
        _snap("bull_flag_breakout", 6, "플래그 형성", 0),
        _snap("bull_flag_breakout", 9, "최종 prepared", 0),
        # step99 auto 중복 — 파이프라인 판정 제외
        _snap("bull_flag_breakout", 99, "최종 prepared (auto)", 0),
    ]
    _install_snapshots(monkeypatch, rows)

    result = await lae._collect_strategy_funnel_stages(_TARGET)

    assert "bull_flag_breakout" in result
    bfb = result["bull_flag_breakout"]
    assert bfb["verdict"] == "패턴희소", bfb
    assert bfb["final_prepared"] == 0
    # drop_step = survived 이 직전>0 → 현재==0 으로 처음 떨어지는 step (플래그)
    assert bfb["drop_step"] is not None
    assert bfb["drop_step"]["step_no"] == 6
    assert "플래그" in bfb["drop_step"]["step_name"]


# ---------------------------------------------------------------------------
# (2) 후보부족 판정 — donchian 유형 (이른 단계 붕괴, 패턴 도달 전)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_donchian_candidate_shortage_verdict(monkeypatch):
    """donchian 유형: union → 필터 → 차단 0 (이른 단계 붕괴, 패턴 도달 전) → 후보부족.

    실측 구조: step1 union348 → step2 필터157 → step3 차단0 → 최종0.
    drop_step 이 유니버스/필터/차단 등 이른 단계(패턴 키워드 미매칭) → 후보부족.
    """
    rows = [
        _snap("donchian_swing", 1, "코스피200+코스닥150 합집합", 348),
        _snap("donchian_swing", 2, "시총+거래대금 컷 통과", 157),
        _snap("donchian_swing", 3, "1단계 진입 차단 통과", 0),
        _snap("donchian_swing", 9, "최종 prepared", 0),
    ]
    _install_snapshots(monkeypatch, rows)

    result = await lae._collect_strategy_funnel_stages(_TARGET)

    don = result["donchian_swing"]
    assert don["verdict"] == "후보부족", don
    assert don["final_prepared"] == 0
    # drop_step = step3 (차단), 이른 단계 → 패턴 키워드 미매칭
    assert don["drop_step"] is not None
    assert don["drop_step"]["step_no"] == 3


# ---------------------------------------------------------------------------
# (3) 후보준비완료 판정 — final_prepared>0 (VB/LTV intraday 대기 유형)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_final_prepared_ready_verdict(monkeypatch):
    """final_prepared>0 → 후보준비완료 (후보 존재, 0신호 = intraday 돌파 대기 = 정상)."""
    rows = [
        _snap("volatility_breakout", 1, "원천 유니버스 후보", 300),
        _snap("volatility_breakout", 2, "시총+거래대금 컷 통과", 120),
        _snap("volatility_breakout", 3, "가격 정합성", 100),
        _snap("volatility_breakout", 4, "일봉 fetch 성공", 95),
        _snap("volatility_breakout", 5, "K값 계산 완료", 30),
    ]
    _install_snapshots(monkeypatch, rows)

    result = await lae._collect_strategy_funnel_stages(_TARGET)

    vb = result["volatility_breakout"]
    assert vb["verdict"] == "후보준비완료", vb
    assert vb["final_prepared"] == 30
    assert vb["peak_survived"] == 300


# ---------------------------------------------------------------------------
# (4) VCP step5 EMA 정렬 생존 수 노출 (domain 후속검증 #2)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_vcp_ema_step5_exposed(monkeypatch):
    """VCP 유형: EMA정렬 step5 survived=2 → Pullback 0.

    domain 후속검증 #2 = EMA 축소 vs 순수 희소 분리 판정 근거.
    steps 에 step5 (EMA 정렬) survived_count==2 가 포함됨을 단언.
    drop_step="Pullback" (패턴 키워드) → verdict="패턴희소".

    실측 구조: step1 union330 → step3 차단66 → step4 일봉66 → step5 EMA정렬2
    → step6 베이스2 → step7 Pullback0 → 최종0.
    """
    rows = [
        _snap("vcp_breakout", 1, "코스피200+코스닥150 합집합", 330),
        _snap("vcp_breakout", 3, "1단계 진입 차단 통과", 66),
        _snap("vcp_breakout", 4, "일봉 fetch 성공", 66),
        _snap("vcp_breakout", 5, "EMA 정렬 통과", 2),
        _snap("vcp_breakout", 6, "베이스 형성", 2),
        _snap("vcp_breakout", 7, "Pullback 수축 시퀀스", 0),
        _snap("vcp_breakout", 9, "최종 prepared", 0),
    ]
    _install_snapshots(monkeypatch, rows)

    result = await lae._collect_strategy_funnel_stages(_TARGET)

    vcp = result["vcp_breakout"]
    # step5 EMA 정렬 생존 수 노출 (EMA 축소 vs 순수 희소 분리 근거)
    step5 = next((s for s in vcp["steps"] if s["step_no"] == 5), None)
    assert step5 is not None, "step5 (EMA 정렬) 가 steps 에 노출되어야 함"
    assert "EMA" in step5["step_name"]
    assert step5["survived_count"] == 2
    # drop_step = Pullback (패턴 키워드) → 패턴희소
    assert vcp["drop_step"] is not None
    assert vcp["drop_step"]["step_no"] == 7
    assert "Pullback" in vcp["drop_step"]["step_name"]
    assert vcp["verdict"] == "패턴희소", vcp
    assert vcp["final_prepared"] == 0


# ---------------------------------------------------------------------------
# (5) graceful — list_snapshots 예외/빈 리스트 → {} 반환, 리포트 무중단
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_graceful_on_list_snapshots_exception(monkeypatch):
    """list_snapshots 가 raise 해도 {} 반환 (리포트 생성 무중단, 사이클 88 패턴)."""
    async def _raise(*_a, **_kw):
        raise RuntimeError("supabase connection lost")

    monkeypatch.setattr(lae, "list_snapshots", _raise, raising=False)

    result = await lae._collect_strategy_funnel_stages(_TARGET)
    assert result == {}


@pytest.mark.asyncio
async def test_graceful_on_empty_snapshots(monkeypatch):
    """빈 리스트 → {} 반환 (휴장일/미캡처)."""
    _install_snapshots(monkeypatch, [])
    result = await lae._collect_strategy_funnel_stages(_TARGET)
    assert result == {}


# ---------------------------------------------------------------------------
# (7) step99 제외 — step_no=99 row 가 있어도 steps/판정에서 배제
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_step99_excluded_from_pipeline(monkeypatch):
    """step_no=99 (auto 중복) 는 steps / verdict / final_prepared 에서 배제.

    step99 를 배제하지 않으면 final_prepared 가 step99 survived 를 잘못 취할 수 있음.
    """
    rows = [
        _snap("bull_flag_breakout", 1, "원천 유니버스 후보", 47),
        _snap("bull_flag_breakout", 4, "일봉 fetch 성공", 16),
        _snap("bull_flag_breakout", 5, "폴(pole) 검출", 2),
        _snap("bull_flag_breakout", 6, "플래그 형성", 0),
        _snap("bull_flag_breakout", 9, "최종 prepared", 0),
        # step99 = auto 중복 (survived 값이 달라도 파이프라인 무관)
        _snap("bull_flag_breakout", 99, "최종 prepared (auto)", 99),
    ]
    _install_snapshots(monkeypatch, rows)

    result = await lae._collect_strategy_funnel_stages(_TARGET)

    bfb = result["bull_flag_breakout"]
    # steps 에 step99 없음
    assert all(s["step_no"] != 99 for s in bfb["steps"]), bfb["steps"]
    # final_prepared = 최대 step_no(≠99) = step9 survived = 0 (step99 의 99 아님)
    assert bfb["final_prepared"] == 0
    # peak_survived 도 step99(99) 무시 → 47
    assert bfb["peak_survived"] == 47


# ---------------------------------------------------------------------------
# (보강) steps 정렬 + peak/final 계산 정확성
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_steps_sorted_and_final_is_max_step(monkeypatch):
    """steps 는 step_no ASC 정렬 + final_prepared = 최대 step_no(≠99) survived."""
    rows = [
        _snap("volatility_breakout", 5, "K값 계산 완료", 30),
        _snap("volatility_breakout", 1, "원천 유니버스 후보", 300),
        _snap("volatility_breakout", 3, "가격 정합성", 100),
    ]
    _install_snapshots(monkeypatch, rows)

    result = await lae._collect_strategy_funnel_stages(_TARGET)
    vb = result["volatility_breakout"]
    step_nos = [s["step_no"] for s in vb["steps"]]
    assert step_nos == sorted(step_nos), step_nos
    assert vb["final_prepared"] == 30  # 최대 step_no=5 survived


# ---------------------------------------------------------------------------
# (보강) 기록없음 — 특정 전략 snapshot 부재
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_no_steps_verdict(monkeypatch):
    """steps 없는 전략 → verdict='기록없음'.

    (다른 전략 row 만 존재하고 대상 전략 row 는 없을 때는 result 에 키가 없거나,
    step 이 전부 99 뿐이면 steps 비어 '기록없음'.)
    """
    rows = [
        # momentum 은 파이프라인 step 없이 step99 만 (funnel 미적재, 사이클 132)
        _snap("momentum", 99, "최종 prepared (auto)", 0),
    ]
    _install_snapshots(monkeypatch, rows)

    result = await lae._collect_strategy_funnel_stages(_TARGET)
    mom = result["momentum"]
    assert mom["steps"] == []
    assert mom["verdict"] == "기록없음", mom
