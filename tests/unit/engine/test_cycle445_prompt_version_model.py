"""cycle445 D7 — `prompt_version` 에 모델명을 포함한다.

배경(`_workspace/domain_consult/weekly_advice_2026-10-08.md` §4.4, 사용자 결정
"응 모델명 넣자") — `prompt_version` 은 SYSTEM 프롬프트·user 프리앰블·스냅샷 키·
전략 META 의 해시뿐이라 모델 교체(10-06 `gpt-5.6-luna` → `gpt-6-luna`)에는
반응하지 않는다. 실측으로 `bull_flag_breakout|77b27be33ac1` 한 키에 두 모델
6건이 섞였다. 이 파일은 모델명이 바뀌면 `prompt_version` 도 바뀐다는 계약을
고정한다.

형식 = `<model>|<prompt_hash>`(모델이 비어도 구분자는 유지 — 빈 모델 문자열
자체가 신호다). 과거 행(모델 미포함 12-hex 단독)과 새 행은 글자 모양이 달라
자동으로 섞이지 않는다 — DB UPDATE 로 과거 행을 바꾸지 않는다(되돌리기 어려운
운영 조치 금지, 루트 CLAUDE.md).
"""

from __future__ import annotations

import re

import pytest

pytestmark = pytest.mark.unit

_VB = "volatility_breakout"


def _g():
    import importlib

    import src.engine.llm_buy_gate as mod

    importlib.reload(mod) if False else None  # no-op — 모듈은 이미 import 돼 있다
    return mod


def test_prompt_version_format_is_model_pipe_hash():
    mod = _g()
    pv = mod._prompt_version(_VB)
    assert re.fullmatch(r"[^|]+\|[0-9a-f]{12}", pv), f"형식 위반: {pv!r}"
    model_part, hash_part = pv.split("|", 1)
    assert model_part, "모델 부분이 비었다"
    assert re.fullmatch(r"[0-9a-f]{12}", hash_part)


def test_prompt_version_model_part_matches_settings(monkeypatch):
    mod = _g()
    monkeypatch.setattr(mod.settings, "openai_buy_gate_model", "gpt-9-nova", raising=False)
    monkeypatch.setattr(mod, "_prompt_version_cache", {})

    pv = mod._prompt_version(_VB)
    assert pv.startswith("gpt-9-nova|"), f"설정 모델명이 키에 반영되지 않았다: {pv!r}"


def test_prompt_version_changes_when_model_switches_even_if_prompt_text_unchanged(monkeypatch):
    """핵심 회귀 — 프롬프트 텍스트·스냅샷 키·META 는 그대로인데 모델만 바뀌어도
    `prompt_version` 이 달라진다(실측 사고의 직접 재현: 10-06 모델 교체인데 같은
    해시였다)."""
    mod = _g()

    monkeypatch.setattr(mod.settings, "openai_buy_gate_model", "gpt-5.6-luna", raising=False)
    monkeypatch.setattr(mod, "_prompt_version_cache", {})
    before = mod._prompt_version(_VB)

    monkeypatch.setattr(mod.settings, "openai_buy_gate_model", "gpt-6-luna", raising=False)
    monkeypatch.setattr(mod, "_prompt_version_cache", {})
    after = mod._prompt_version(_VB)

    assert before != after, (
        "모델을 바꿨는데 prompt_version 이 그대로다 — 두 모델이 같은 키로 섞인다"
        " (실측 사고 = bull_flag_breakout|77b27be33ac1 한 키에 두 모델 6건)"
    )
    # 해시 부분(프롬프트 내용)은 변하지 않는다 — 모델만 바뀌었으니까.
    assert before.split("|", 1)[1] == after.split("|", 1)[1]


def test_prompt_version_still_fails_open_to_empty_string(monkeypatch):
    """C30 fail-open 계약 보존 — 계산 실패는 빈 문자열(모델 접두 없이도)."""
    mod = _g()
    monkeypatch.setattr(mod, "_prompt_version_cache", {})

    def _boom(*a, **kw):
        raise RuntimeError("llm_features 로드 실패")

    import src.engine.llm_features as lf

    monkeypatch.setattr(lf, "snapshot_keys_for", _boom)

    pv = mod._prompt_version(_VB)
    assert pv == "", f"실패 경로가 빈 문자열이 아니다: {pv!r}"


def test_composite_key_with_pipe_in_prompt_version_does_not_break_aggregation():
    """`llm_retrospective.aggregate` 의 `by_prompt_version["<sid>|<pv>"]` 합성 키가
    `pv` 안에 `|` 가 섞여도(이제 `<model>|<hash>`) 그냥 문자열로 동작한다 — 어느
    소비처도 `|` 로 분할해 정확히 2토큰을 기대하지 않는다."""
    from src.engine import llm_retrospective as retro

    row = {
        "strategy": _VB,
        "status": "closed",
        "profit_rate": -1.0,
        "primary": {"prompt_version": "gpt-6-luna|abcdef012345", "score": 50},
    }
    agg = retro.aggregate([row], cost_pct=0.25)
    assert "volatility_breakout|gpt-6-luna|abcdef012345" in agg["by_prompt_version"], (
        f"합성 키가 예상과 다르다: {sorted(agg['by_prompt_version'])}"
    )
