"""cycle233 M2·M3 — 순수 판정 leaf + system_config 임계 getter (R4·R12).

- `account_risk_guard.evaluate_soft_gate` — 순수 함수. **block_pct None = 다크런치**
  (어떤 pct 도 block 불가). pct None/음수 → ok (fail-open — 판정 실패가 매수를
  막으면 안 된다, 코드베이스 불변 규약).
- `system_config.get_account_risk_warn_pct`(기본 4.0 — 관측 경보 상시)
  + `get_account_risk_block_pct`(기본 None — SOFT 차단 다크런치, DB 한 줄 활성).
"""

from __future__ import annotations

import pytest

from src.engine.account_risk_guard import evaluate_soft_gate


class TestR4EvaluateSoftGate:
    def test_dark_launch_block_none_never_blocks(self):
        """다크런치 — block_pct=None 이면 아무리 커도 block 이 아니다."""
        v = evaluate_soft_gate(99.0, warn_pct=4.0, block_pct=None)
        assert v["level"] == "warn"          # 관측 경보는 발화
        assert v["level"] != "block"

    def test_ok_below_warn(self):
        v = evaluate_soft_gate(3.31, warn_pct=4.0, block_pct=6.0)
        assert v["level"] == "ok"

    def test_warn_at_threshold(self):
        v = evaluate_soft_gate(4.0, warn_pct=4.0, block_pct=6.0)
        assert v["level"] == "warn"

    def test_block_at_threshold(self):
        v = evaluate_soft_gate(6.0, warn_pct=4.0, block_pct=6.0)
        assert v["level"] == "block"
        assert v["reasons"]                  # 사유 병기 (관측)

    def test_none_pct_fail_open(self):
        assert evaluate_soft_gate(None, warn_pct=4.0, block_pct=6.0)["level"] == "ok"

    def test_negative_pct_fail_open(self):
        assert evaluate_soft_gate(-1.0, warn_pct=4.0, block_pct=6.0)["level"] == "ok"

    def test_warn_none_disables_warn(self):
        v = evaluate_soft_gate(5.0, warn_pct=None, block_pct=None)
        assert v["level"] == "ok"


class TestR12SystemConfigGetters:
    @pytest.mark.asyncio
    async def test_defaults_when_missing(self, monkeypatch):
        from src.db import system_config as sc

        async def _missing(key):
            return sc._MISSING

        monkeypatch.setattr(sc, "_select_value", _missing)
        assert await sc.get_account_risk_warn_pct() == pytest.approx(4.0)
        assert await sc.get_account_risk_block_pct() is None

    @pytest.mark.asyncio
    async def test_value_dict_parsed(self, monkeypatch):
        from src.db import system_config as sc

        async def _val(key):
            return {"value": 6.0}

        monkeypatch.setattr(sc, "_select_value", _val)
        assert await sc.get_account_risk_warn_pct() == pytest.approx(6.0)
        assert await sc.get_account_risk_block_pct() == pytest.approx(6.0)

    @pytest.mark.asyncio
    async def test_exception_falls_back_to_default(self, monkeypatch):
        from src.db import system_config as sc

        async def _boom(key):
            raise RuntimeError("db down")

        monkeypatch.setattr(sc, "_select_value", _boom)
        assert await sc.get_account_risk_warn_pct() == pytest.approx(4.0)
        assert await sc.get_account_risk_block_pct() is None
