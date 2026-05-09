"""src/api/base.py 단위 테스트 — Phase A 시드.

KisApiError 직렬화와 호출 메트릭 누적/리셋만 다룬다.
실제 KIS 호출(_request)은 통합 단계에서 respx로 별도 검증.
"""

from __future__ import annotations

import pytest

from src.api import base

pytestmark = pytest.mark.unit


def test_kis_api_error_when_constructed_then_carries_codes_and_msg():
    err = base.KisApiError(rt_cd="1", msg_cd="APBK0660", msg1="예수금이 부족합니다.")
    assert err.rt_cd == "1"
    assert err.msg_cd == "APBK0660"
    assert err.msg1 == "예수금이 부족합니다."
    assert "[APBK0660]" in str(err)
    assert "예수금이 부족합니다." in str(err)


def test_get_request_metrics_returns_snapshot_keys():
    snapshot = base.get_request_metrics()
    assert {"total", "http_5xx", "http_4xx", "network_err", "kis_error", "retries", "top_5xx_paths"} <= set(
        snapshot
    )


def test_reset_request_metrics_when_called_then_zeros_counters():
    base._request_metrics["total"] = 42
    base._request_metrics["http_5xx"] = 3
    base._request_metrics["by_path_5xx"]["/uapi/x"] = 3

    base.reset_request_metrics()
    snapshot = base.get_request_metrics()

    assert snapshot["total"] == 0
    assert snapshot["http_5xx"] == 0
    assert snapshot["top_5xx_paths"] == []


def test_top_5xx_paths_when_recorded_then_sorted_desc():
    base.reset_request_metrics()
    base._request_metrics["by_path_5xx"]["/a"] = 1
    base._request_metrics["by_path_5xx"]["/b"] = 5
    base._request_metrics["by_path_5xx"]["/c"] = 3

    top = base.get_request_metrics()["top_5xx_paths"]
    assert top[0] == ("/b", 5)
    assert top[1] == ("/c", 3)
    assert top[2] == ("/a", 1)
    base.reset_request_metrics()
