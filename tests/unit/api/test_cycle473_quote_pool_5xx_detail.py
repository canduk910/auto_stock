"""cycle473 — 보조 시세 풀 HTTP 5xx WARNING 에 KIS 본문 요약(`msg_cd`/`msg1`)을 싣는다.

10-14 4380 계정 500 원인 추적이 늦었던 이유 = 시세 풀 경고에 본문이 없었다(메인 `_request` 는
cycle447 부터 `detail=` 을 싣는다). 같은 요약 함수 `_extract_5xx_detail` 를 쓴다.
"""
from __future__ import annotations

import ast
import logging
from pathlib import Path

import httpx
import pytest

from src.api import base

pytestmark = pytest.mark.unit
_SRC = Path(base.__file__)


def test_warning_includes_detail_when_present(caplog):
    with caplog.at_level(logging.WARNING, logger=base.logger.name):
        base._warn_quote_http_status(500, 1, 3, "/p", "4380", detail="msg_cd=EGW00201 msg1=초당 거래건수")
    assert caplog.messages == ["[quote_pool] HTTP 500 (attempt 1/3): /p label=4380 detail=msg_cd=EGW00201 msg1=초당 거래건수"]


def test_warning_byte_identical_without_detail(caplog):
    with caplog.at_level(logging.WARNING, logger=base.logger.name):
        base._warn_quote_http_status(500, 1, 3, "/p", "4380", detail="")
    assert caplog.messages == ["[quote_pool] HTTP 500 (attempt 1/3): /p label=4380"]


def test_detail_extracted_from_json_body():
    resp = httpx.Response(500, json={"rt_cd": "1", "msg_cd": "EGW00201", "msg1": "초당 거래건수를 초과"})
    assert base._extract_5xx_detail(resp) == "msg_cd=EGW00201 msg1=초당 거래건수를 초과"


def test_quote_pool_uses_helper_with_response_detail():
    tree = ast.parse(_SRC.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "_request_via_quote_pool")
    src = ast.get_source_segment(_SRC.read_text(encoding="utf-8"), fn)
    assert "_warn_quote_http_status(" in src and "_extract_5xx_detail(e.response)" in src
    assert '"[quote_pool] HTTP %s (attempt %d/%d): %s label=%s",' not in src
