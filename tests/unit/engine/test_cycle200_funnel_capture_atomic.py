"""사이클 200 (D-1) — VCP funnel step1/2 기록 정합 (관찰성 race, 매매 무관).

출처: `_workspace/ai_advisory_review/2026-07-09_3day_consolidation.md` §6-3 D-1.

근본 원인 (진단 완료):
`scheduler.capture_funnel_snapshots` L216 이 라이브 `_funnel_steps` 리스트를 참조
(`funnel_steps = getattr(strategy, "_funnel_steps", []) or []`) 하며, step 마다
`await insert_snapshot(...)` (yield) 로 iterate 한다. 동시에 concurrent `prepare()`
(09:30 auto capture vs boot re-prepare / `_scan_loop` 5분 re-prepare /
`_reprepare_breakout_if_empty`) 가 `_record_funnel_step` (strategy_base.py L280-284,
`self._funnel_steps[idx] = entry` in-place 요소 replace) 로 같은 리스트를 변형하면,
capture 의 await 사이에 인터리빙 발생 → 나중 step 이 먼저 기록되어 논리 불가
단조성 (step3 survived > step1/2 survived) 이 DB 에 기록된다.

운영 실측 (Supabase, 7/9 VCP is_provisional): step1=0, step2=0, step3=67, step4=67,
step5=3 (step3≤step2≤step1 위반) = 간헐 race.

확정 수정 (backend-dev Green):
`capture_funnel_snapshots` L216 을 원자적 shallow copy 로:
    funnel_steps = list(getattr(strategy, "_funnel_steps", []) or [])
`_record_funnel_step` 이 리스트 요소를 replace (`[idx]=entry`, 기존 dict 변형 아님)
하므로 `list(...)` shallow copy 로 capture 시작 시점 요소 참조 고정 → 단조 일관성 보장.

회귀 가드:
- G-200-1 (HIGH, 핵심 race): capture 중 라이브 `_funnel_steps` in-place 변형 시
  캡처 결과가 capture 시작 시점 원본 일관 스냅샷과 동일 + 단조 비증가.
  현재 코드 (라이브 참조) = step2/3 변형값(0) 캡처 → RED. 수정(copy) = PASS.
- G-200-2 (무변형 시 불변): concurrent 변형 없는 정상 경우 캡처 결과가 원본과
  정확히 일치 (회귀 0). is_provisional 전파 불변.
- G-200-3 (graceful 보존): `_funnel_steps` 빈 리스트 → 단계 row 0 + step99 최종 row
  (사이클 132 momentum 패턴) 불변. registry 예외 graceful 불변.

SAFETY: capture_funnel_snapshots = 관찰성 (사이클 171 SAFETY = check_exit/buy hook 0).
risk/order_engine/realtime/scanner 무관 — 8영역 밖.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.unit


# ──────────────────────────────────────────────────────────────────────
# 픽스처 헬퍼 (사이클 171 test_cycle171_evening_funnel.py 답습)
# ──────────────────────────────────────────────────────────────────────


def _make_strategy(sid: str, funnel_steps: list[dict], scanned: list[str]):
    strat = MagicMock()
    strat.strategy_id = sid
    strat._funnel_steps = funnel_steps
    strat.get_scanned_tickers = MagicMock(return_value=scanned)
    return strat


def _make_registry(strategies):
    reg = MagicMock()
    reg.all = MagicMock(return_value=strategies)
    return reg


def _step(step_no: int, survived_count: int, step_name: str = "") -> dict:
    """일관 상태 funnel step dict (survived 리스트 길이 == survived_count)."""
    survived = [f"{step_no:03d}{i:03d}" for i in range(survived_count)]
    return {
        "step_no": step_no,
        "step_name": step_name or f"VCP step{step_no}",
        "step_conditions": None,
        "survived": survived,
        "survived_count": survived_count,
        "excluded": [],
        "excluded_count": 0,
    }


def _pipeline_counts(captured: list[dict]) -> dict[int, int]:
    """캡처된 insert_snapshot 호출 → {step_no: survived_count} (step99 제외)."""
    return {
        c["step_no"]: c["survived_count"]
        for c in captured
        if c["step_no"] != 99
    }


# ──────────────────────────────────────────────────────────────────────
# G-200-1 (HIGH) — 핵심 race 재현
# ──────────────────────────────────────────────────────────────────────


class TestCaptureRace:
    """capture 중 concurrent prepare 리스트 변형 → 원자성 위반 재현."""

    @pytest.mark.asyncio
    async def test_g_200_1_atomic_capture_under_concurrent_mutation(self, monkeypatch):
        """G-200-1 (HIGH): capture 시작 시점 원본 일관 스냅샷 보존 + 단조 비증가.

        VCP 운영 실측 재현: 일관 스냅샷 (step1=330, step2=330, step3=67).
        insert_snapshot mock 이 첫 호출(step1) 처리 중 라이브 `_funnel_steps` 를
        in-place 변형 (step1/step2 를 survived_count=0 dict 으로 replace =
        concurrent prepare reset 시뮬레이션).

        현재 코드 (L216 라이브 참조): 캡처 루프가 변형된 리스트를 계속 읽음 →
        step2 = 0 (변형값) 캡처 → 원본(330) 불일치 + 단조 위반 (step3=67 > step2=0)
        = RED.
        수정 (L216 `list(...)` copy): capture 시작 시점 요소 참조 고정 → step2=330
        원본 유지 = PASS.
        """
        from src.engine import scheduler as sched_mod
        from src.db import strategy_funnel as sf_mod

        # 일관 상태 스냅샷 (단조 비증가: 330 >= 330 >= 67)
        live_steps = [
            _step(1, 330),
            _step(2, 330),
            _step(3, 67),
        ]
        strat = _make_strategy("vcp_breakout", live_steps, scanned=["005930"])

        captured: list = []
        call_idx = {"n": 0}

        async def _fake_insert(**kwargs):
            captured.append(kwargs)
            # 첫 호출 (step1) 처리 중 라이브 리스트 in-place 변형 =
            # concurrent prepare 의 `_record_funnel_step` (`[idx]=entry` replace) 시뮬레이션.
            if call_idx["n"] == 0:
                strat._funnel_steps[0] = _step(1, 0)
                strat._funnel_steps[1] = _step(2, 0)
            call_idx["n"] += 1
            return {"id": f"row-{kwargs['step_no']}"}

        monkeypatch.setattr(sf_mod, "insert_snapshot", _fake_insert, raising=False)

        await sched_mod.capture_funnel_snapshots(
            _make_registry([strat]), is_provisional=True
        )

        counts = _pipeline_counts(captured)

        # (a) 원본 일관 스냅샷 정확 보존 (변형값 0 미유입)
        assert counts.get(1) == 330, f"step1 원본 330 미보존: {counts}"
        assert counts.get(2) == 330, (
            f"step2 = concurrent 변형값(0) 캡처 → 원자성 위반 (실측 {counts.get(2)}, "
            f"전체 {counts}). L216 라이브 참조 결함 = RED."
        )
        assert counts.get(3) == 67, f"step3 원본 67 미보존: {counts}"

        # (b) 단조 비증가 (파이프라인 논리: step1 >= step2 >= step3)
        ordered = [counts[k] for k in sorted(counts)]
        for prev, cur in zip(ordered, ordered[1:]):
            assert prev >= cur, (
                f"단조성 위반 (step 별 survived_count = {ordered}) — "
                f"나중 step 이 앞 step 보다 큼 = race 결함 RED."
            )

    @pytest.mark.asyncio
    async def test_g_200_1b_mutation_after_first_step_does_not_leak(self, monkeypatch):
        """G-200-1b (HIGH): 변형이 뒷 step 만 건드려도 원본 유지.

        capture 시작 시점 스냅샷 이후 리스트 요소 replace 가 발생해도 캡처값 불변.
        """
        from src.engine import scheduler as sched_mod
        from src.db import strategy_funnel as sf_mod

        live_steps = [_step(1, 328), _step(2, 100), _step(3, 40)]
        strat = _make_strategy("vcp_breakout", live_steps, scanned=[])

        captured: list = []
        call_idx = {"n": 0}

        async def _fake_insert(**kwargs):
            captured.append(kwargs)
            # step1 캡처 직후 step2/3 을 급증값으로 오염 (단조 위반 유발 시도)
            if call_idx["n"] == 0:
                strat._funnel_steps[1] = _step(2, 999)
                strat._funnel_steps[2] = _step(3, 999)
            call_idx["n"] += 1
            return {"id": "x"}

        monkeypatch.setattr(sf_mod, "insert_snapshot", _fake_insert, raising=False)

        await sched_mod.capture_funnel_snapshots(
            _make_registry([strat]), is_provisional=False
        )

        counts = _pipeline_counts(captured)
        assert counts.get(2) == 100, (
            f"step2 오염값(999) 유입 → 원자성 위반 (실측 {counts.get(2)}) = RED"
        )
        assert counts.get(3) == 40, (
            f"step3 오염값(999) 유입 → 원자성 위반 (실측 {counts.get(3)}) = RED"
        )


# ──────────────────────────────────────────────────────────────────────
# G-200-2 — 무변형 시 불변 (회귀 0)
# ──────────────────────────────────────────────────────────────────────


class TestNoMutationInvariant:
    """concurrent 변형 없는 정상 경우 = 기존 동작 정확 보존."""

    @pytest.mark.asyncio
    async def test_g_200_2_normal_capture_matches_original(self, monkeypatch):
        """G-200-2: 변형 없으면 캡처 결과가 원본과 정확 일치 + is_provisional 전파."""
        from src.engine import scheduler as sched_mod
        from src.db import strategy_funnel as sf_mod

        live_steps = [_step(1, 330), _step(2, 328), _step(3, 67), _step(4, 67), _step(5, 3)]
        strat = _make_strategy("vcp_breakout", live_steps, scanned=["005930", "000660"])

        captured: list = []

        async def _fake_insert(**kwargs):
            captured.append(kwargs)
            return {"id": f"row-{kwargs['step_no']}"}

        monkeypatch.setattr(sf_mod, "insert_snapshot", _fake_insert, raising=False)

        await sched_mod.capture_funnel_snapshots(
            _make_registry([strat]), is_provisional=True
        )

        counts = _pipeline_counts(captured)
        assert counts == {1: 330, 2: 328, 3: 67, 4: 67, 5: 3}, (
            f"무변형 캡처 원본 불일치 (회귀): {counts}"
        )
        # step99 최종 row + is_provisional 전파
        step_nos = {c["step_no"] for c in captured}
        assert 99 in step_nos, "step_no=99 최종 row 누락 (사이클 34 호환)"
        assert all(c.get("is_provisional") is True for c in captured), (
            "is_provisional=True 전파 누락 (회귀)"
        )

    @pytest.mark.asyncio
    async def test_g_200_2b_provisional_false_propagated(self, monkeypatch):
        """G-200-2b: is_provisional=False 전파 불변 (09:30/수동 trigger 경로)."""
        from src.engine import scheduler as sched_mod
        from src.db import strategy_funnel as sf_mod

        strat = _make_strategy("donchian_swing", [_step(1, 5)], scanned=["005930"])
        captured: list = []

        async def _fake_insert(**kwargs):
            captured.append(kwargs)
            return {"id": "x"}

        monkeypatch.setattr(sf_mod, "insert_snapshot", _fake_insert, raising=False)

        await sched_mod.capture_funnel_snapshots(
            _make_registry([strat]), is_provisional=False
        )

        assert captured, "insert 호출 0건"
        assert all(c.get("is_provisional") is False for c in captured), (
            "is_provisional=False 전파 누락 (회귀)"
        )


# ──────────────────────────────────────────────────────────────────────
# G-200-3 — graceful 보존
# ──────────────────────────────────────────────────────────────────────


class TestGracefulPreservation:
    """빈 리스트 / 예외 graceful 불변 (사이클 132 momentum + 사이클 88)."""

    @pytest.mark.asyncio
    async def test_g_200_3_empty_funnel_steps_final_row_only(self, monkeypatch):
        """G-200-3: `_funnel_steps` 빈 리스트 → 단계 row 0 + step99 최종 row (momentum 패턴)."""
        from src.engine import scheduler as sched_mod
        from src.db import strategy_funnel as sf_mod

        strat = _make_strategy("momentum", funnel_steps=[], scanned=["005930"])
        captured: list = []

        async def _fake_insert(**kwargs):
            captured.append(kwargs)
            return {"id": "x"}

        monkeypatch.setattr(sf_mod, "insert_snapshot", _fake_insert, raising=False)

        saved = await sched_mod.capture_funnel_snapshots(
            _make_registry([strat]), is_provisional=False
        )

        step_nos = [c["step_no"] for c in captured]
        assert step_nos == [99], f"빈 funnel = step99 최종 row 만 의무 (실측 {step_nos})"
        assert saved == 1

    @pytest.mark.asyncio
    async def test_g_200_3b_registry_exception_graceful(self, monkeypatch):
        """G-200-3b: registry.all() 예외 → 0 반환 graceful (사이클 88 답습)."""
        from src.engine import scheduler as sched_mod

        reg = MagicMock()
        reg.all = MagicMock(side_effect=RuntimeError("boom"))

        saved = await sched_mod.capture_funnel_snapshots(reg, is_provisional=True)
        assert saved == 0, "registry 예외 시 graceful 0 반환 의무"

    @pytest.mark.asyncio
    async def test_g_200_3c_per_strategy_exception_isolated(self, monkeypatch):
        """G-200-3c: 한 전략 `_funnel_steps` 접근 예외 → 다른 전략 계속 (graceful)."""
        from src.engine import scheduler as sched_mod
        from src.db import strategy_funnel as sf_mod

        bad = MagicMock()
        bad.strategy_id = "bull_flag_breakout"
        # _funnel_steps 접근 시 예외
        type(bad)._funnel_steps = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("access fail"))
        )
        bad.get_scanned_tickers = MagicMock(return_value=[])

        good = _make_strategy("vcp_breakout", [_step(1, 10)], scanned=["005930"])

        captured: list = []

        async def _fake_insert(**kwargs):
            captured.append(kwargs)
            return {"id": "x"}

        monkeypatch.setattr(sf_mod, "insert_snapshot", _fake_insert, raising=False)

        # 예외 전략 있어도 good 전략은 캡처됨
        await sched_mod.capture_funnel_snapshots(
            _make_registry([bad, good]), is_provisional=False
        )

        good_steps = {c["step_no"] for c in captured}
        assert 1 in good_steps, "정상 전략 캡처 누락 (graceful 격리 실패)"
