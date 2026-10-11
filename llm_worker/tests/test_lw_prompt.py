"""cycle446 — 출력 검증·프롬프트 조립(`lw/prompt.py`)."""
from __future__ import annotations

import json

import pytest

from lw import prompt

pytestmark = pytest.mark.unit


def test_validate_output_valid_hold():
    content = json.dumps({"action": "hold", "exit_score": 40, "rationale": "r",
                          "key_risks": ["a"], "invalidations": ["b"]})
    action, score, rationale, risks, invalid, inconsistent, reason = prompt.validate_output(content)
    assert reason is None
    assert action == "hold" and score == 40 and inconsistent is False


def test_validate_output_valid_exit():
    content = json.dumps({"action": "exit", "exit_score": 80, "rationale": "r"})
    action, score, *_rest, inconsistent, reason = prompt.validate_output(content)
    assert reason is None and action == "exit" and inconsistent is False


def test_validate_output_inconsistent_not_discarded():
    content = json.dumps({"action": "exit", "exit_score": 20, "rationale": "r"})
    action, score, _r, _k, _i, inconsistent, reason = prompt.validate_output(content)
    assert reason is None, "불일치는 버리지 않는다 — 기록만 한다"
    assert inconsistent is True
    assert action == "exit" and score == 20


def test_validate_output_missing_action_is_schema_error():
    content = json.dumps({"exit_score": 50})
    *_rest, reason = prompt.validate_output(content)
    assert reason == "schema_error"


def test_validate_output_bad_action_value():
    content = json.dumps({"action": "sell", "exit_score": 50})
    *_rest, reason = prompt.validate_output(content)
    assert reason == "schema_error"


def test_validate_output_score_out_of_range():
    content = json.dumps({"action": "hold", "exit_score": 101})
    *_rest, reason = prompt.validate_output(content)
    assert reason == "schema_error"


def test_validate_output_score_bool_rejected():
    content = json.dumps({"action": "hold", "exit_score": True})
    *_rest, reason = prompt.validate_output(content)
    assert reason == "schema_error"


def test_validate_output_none_content_is_schema_error():
    *_rest, reason = prompt.validate_output(None)
    assert reason == "schema_error"


def test_validate_output_empty_with_length_finish_is_truncated():
    *_rest, reason = prompt.validate_output("", finish_reason="length")
    assert reason == "truncated"


def test_validate_output_empty_without_length_is_schema_error():
    *_rest, reason = prompt.validate_output("", finish_reason="stop")
    assert reason == "schema_error"


def test_validate_output_bad_json_is_parse_error():
    *_rest, reason = prompt.validate_output("{not json")
    assert reason == "parse_error"


def test_describe_exit_rule_known_strategies_nonempty():
    for sid in ("donchian_swing", "kojiro", "vcp_breakout", "bull_flag_breakout", "etf_trend"):
        assert prompt.describe_exit_rule(sid, {}) != ""


def test_describe_exit_rule_unknown_strategy_empty():
    assert prompt.describe_exit_rule("momentum", {}) == ""


def test_build_messages_two_roles_and_json_payload():
    position = {"strategy_id": "donchian_swing", "close_won": 1000, "exit_rule_text": "손절 -8%"}
    messages = prompt.build_messages(position)
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "손절 -8%" in messages[1]["content"]
    assert '"close_won": 1000' in messages[1]["content"]


def test_prompt_version_stable_for_same_model():
    a = prompt.prompt_version("gpt-6-luna")
    b = prompt.prompt_version("gpt-6-luna")
    c = prompt.prompt_version("other-model")
    assert a == b
    assert a != c
    assert a.startswith("exit-v1-gpt-6-luna-")
