"""cycle340 — 고지로 대순환 MACD shadow 관측 회귀.

🔴 **관측 전용이다 — 매매를 한 글자도 바꾸지 않는다.** 그래서 이 그물이 재는 것은
두 가지다: ① 기록되는 **값**이 맞는가 ② 관측이 실패해도 **행위가 그대로인가**.

「마커가 찍혔다」만 보면 골든크로스 판정이 뒤집혀도, 원전 3단 진입(rule6/5/4)이
엉뚱한 국면에 붙어도 전부 초록이다. 이 표본은 나중에 진입 규약을 바꿀지 판단하는
유일한 근거가 되므로 **값이 틀리면 관측이 없느니만 못하다**.

실측 배경 = `_workspace/domain_consult/cycle340_kojiro_macd.md`
"""
from __future__ import annotations

import logging

import pandas as pd
import pytest

from src.engine.kojiro_band_observe import (
    MACD_MARKER, observe_macd, reset_kojiro_band_observe_cap,
)


@pytest.fixture(autouse=True)
def _fresh_cap():
    reset_kojiro_band_observe_cap()
    yield
    reset_kojiro_band_observe_cap()


def row(
    stage=1, m1=1.0, m2=2.0, m3=3.0, s1=0.5, s2=1.5, s3=2.5,
    gc3=1, bars_since=0, m1_up=1, m2_up=1, m3_up=1,
) -> tuple:
    return (stage, m1, m2, m3, s1, s2, s3, gc3, bars_since, m1_up, m2_up, m3_up)


def emit(caplog, macd_raw, ranked=("005930",), held=()):
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="src.engine.kojiro_band_observe"):
        observe_macd(macd_raw, list(ranked), list(held))
    return [r.getMessage() for r in caplog.records if MACD_MARKER in r.getMessage()]


# ── 값 ────────────────────────────────────────────────────────────────────


def test_records_every_macd_value(caplog):
    msgs = emit(caplog, {"005930": row(m1=1.25, m2=2.5, m3=3.75, s1=0.5, s2=1.5, s3=2.5)})
    assert len(msgs) == 1
    m = msgs[0]
    # 🔴 여섯 수가 서로 달라야 맞바꿈을 잡는다.
    assert "m1=1.25" in m and "m2=2.50" in m and "m3=3.75" in m
    assert "s1=0.50" in m and "s2=1.50" in m and "s3=2.50" in m


def test_histogram_is_macd3_minus_signal3(caplog):
    """히스토그램 = MACD(하) − 시그널. 원전이 「예측 도구」라 부른 값이다."""
    msgs = emit(caplog, {"005930": row(m3=3.75, s3=2.50)})
    assert "hist3=1.25" in msgs[0]


def test_golden_cross_flag_is_recorded(caplog):
    assert "gc3=1" in emit(caplog, {"005930": row(gc3=1)})[0]
    reset_kojiro_band_observe_cap()
    assert "gc3=0" in emit(caplog, {"005930": row(gc3=0)})[0]


def test_bars_since_cross_is_recorded(caplog):
    assert "bars_since_gc3=9" in emit(caplog, {"005930": row(bars_since=9)})[0]
    reset_kojiro_band_observe_cap()
    # 크로스가 한 번도 없으면 `-` 다 — 0 으로 접으면 "오늘 크로스" 와 뒤섞인다.
    assert "bars_since_gc3=-" in emit(caplog, {"005930": row(bars_since=None)})[0]


def test_all_macd_up_requires_all_three(caplog):
    assert "all_macd_up=1" in emit(caplog, {"005930": row(m1_up=1, m2_up=1, m3_up=1)})[0]
    for kw in ("m1_up", "m2_up", "m3_up"):
        reset_kojiro_band_observe_cap()
        msgs = emit(caplog, {"005930": row(**{kw: 0})})
        assert "all_macd_up=0" in msgs[0], f"{kw}=0 인데 all_macd_up 이 1 이다"


# ── 원전 3단 진입 판정 ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "stage,expect",
    [(6, "rule6=1 rule5=0 rule4=0"),
     (5, "rule6=0 rule5=1 rule4=0"),
     (4, "rule6=0 rule5=0 rule4=1"),
     (1, "rule6=0 rule5=0 rule4=0"),
     (3, "rule6=0 rule5=0 rule4=0")],
)
def test_rules_bind_to_the_right_stage(caplog, stage, expect):
    """원전 §7 — 조건은 같고 **국면만 다르다**(본매매 6 / 조기 5 / 시험 4)."""
    msgs = emit(caplog, {"005930": row(stage=stage, gc3=1, m1_up=1, m2_up=1, m3_up=1)})
    assert expect in msgs[0]


def test_rules_need_golden_cross(caplog):
    """골든크로스가 없으면 어느 국면이든 규칙이 서지 않는다."""
    msgs = emit(caplog, {"005930": row(stage=6, gc3=0, m1_up=1, m2_up=1, m3_up=1)})
    assert "rule6=0 rule5=0 rule4=0" in msgs[0]


def test_rules_need_all_three_macd_rising(caplog):
    """🔴 3 MACD 우상향은 원전 조건의 일부다 — 빼면 규칙이 헐거워진다."""
    msgs = emit(caplog, {"005930": row(stage=6, gc3=1, m2_up=0)})
    assert "rule6=0" in msgs[0]


# ── 역할·cap·안전성 ───────────────────────────────────────────────────────


def test_candidate_and_held_roles_are_separate(caplog):
    msgs = emit(caplog, {"005930": row(), "000660": row()},
                ranked=("005930",), held=("000660",))
    assert any("ticker=005930 role=candidate" in m for m in msgs)
    assert any("ticker=000660 role=held" in m for m in msgs)


def test_cap_is_once_per_ticker_role_per_day(caplog):
    data = {"005930": row()}
    assert len(emit(caplog, data)) == 1
    assert len(emit(caplog, data)) == 0      # 같은 날 두 번째는 침묵


def test_macd_cap_key_does_not_collide_with_band_cap(caplog):
    """🔴 band 관측과 cap 슬롯을 다투면 한쪽이 다른 쪽을 통째로 침묵시킨다."""
    from src.engine.kojiro_band_observe import observe_band

    caplog.clear()
    with caplog.at_level(logging.INFO, logger="src.engine.kojiro_band_observe"):
        observe_band({"005930": tuple(range(12))}, ["005930"], [], scores={})
        observe_macd({"005930": row()}, ["005930"], [])
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "[kojiro_band_observe]" in text
    assert MACD_MARKER in text


def test_level_is_warning_so_it_survives_retention(caplog):
    """🔴 INFO 면 21:30 리포트에 안 오르고 retention 2일에 지워진다.

    이 마커는 **표본 수집이 목적**이라 30일 보존(WARNING+)이 필요하다.
    """
    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger="src.engine.kojiro_band_observe"):
        observe_macd({"005930": row()}, ["005930"], [])
    recs = [r for r in caplog.records if MACD_MARKER in r.getMessage()]
    assert recs and all(r.levelno >= logging.WARNING for r in recs)


@pytest.mark.parametrize(
    "bad", [None, {}, {"005930": None}, {"005930": ()},
            {"005930": (1, 2, 3)}, {"005930": "문자열"}, "dict 아님"],
)
def test_broken_input_never_raises(bad):
    observe_macd(bad, ["005930"], [])      # 예외가 나오면 실패다


def test_one_bad_ticker_does_not_kill_the_batch(caplog):
    msgs = emit(caplog, {"005930": ("깨짐",), "000660": row()},
                ranked=("005930", "000660"))
    assert any("ticker=000660" in m for m in msgs)


def test_non_numeric_values_fall_back_without_raising(caplog):
    msgs = emit(caplog, {"005930": row(m1="x", s3=None)})
    assert len(msgs) == 1
    assert "m1=-" in msgs[0]
    assert "hist3=-" in msgs[0]          # 한쪽이 비수치면 히스토그램도 `-`
