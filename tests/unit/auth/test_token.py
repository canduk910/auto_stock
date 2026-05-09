"""src/auth/token.py 단위 테스트 — Phase A 시드.

TokenManager의 만료 판정과 헤더 구성만 다룬다.
실제 발급(POST /oauth2/tokenP)은 통합 단계에서 respx로 검증.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from src.auth.token import TokenManager


pytestmark = pytest.mark.unit


@pytest.fixture
def isolated_cache(tmp_path, monkeypatch):
    """TokenManager 캐시 파일을 tmp_path로 격리.

    모듈 전역 _TOKEN_CACHE_PATH 를 격리하여 실제 .token_cache.json 영향을 받지 않게.
    """
    from src.auth import token as token_mod

    monkeypatch.setattr(token_mod, "_TOKEN_CACHE_PATH", tmp_path / ".token_cache.json")
    return tmp_path


def test_is_valid_when_no_token_then_false(isolated_cache):
    tm = TokenManager()
    assert tm._is_valid() is False


def test_is_valid_when_token_set_and_not_near_expiry_then_true(isolated_cache):
    tm = TokenManager()
    tm.access_token = "fake-token"
    tm.token_expired = datetime.now() + timedelta(hours=2)
    assert tm._is_valid() is True


def test_is_valid_when_within_10min_grace_then_false(isolated_cache):
    tm = TokenManager()
    tm.access_token = "fake-token"
    tm.token_expired = datetime.now() + timedelta(minutes=5)
    assert tm._is_valid() is False


def test_build_headers_when_called_then_contains_required_keys(isolated_cache):
    tm = TokenManager()
    tm.access_token = "abc"
    headers = tm.build_headers(tr_id="TTTC0012U")
    assert headers["authorization"] == "Bearer abc"
    assert "appkey" in headers
    assert "appsecret" in headers
    assert headers["custtype"] == "P"
    assert "tr_id" in headers


def test_build_headers_with_hashkey_when_provided_then_included(isolated_cache):
    tm = TokenManager()
    headers = tm.build_headers(tr_id="TTTC0012U", hashkey="hk-1")
    assert headers["hashkey"] == "hk-1"


def test_build_headers_when_hashkey_absent_then_omitted(isolated_cache):
    tm = TokenManager()
    headers = tm.build_headers(tr_id="TTTC0012U")
    assert "hashkey" not in headers


def test_save_and_load_cache_roundtrip(isolated_cache):
    tm = TokenManager()
    tm.access_token = "tok"
    tm.token_expired = datetime.now() + timedelta(hours=1)
    tm._save_cache()

    fresh = TokenManager()
    assert fresh.access_token == "tok"
    assert fresh.token_expired is not None


def test_load_cache_when_expired_then_clears(isolated_cache):
    tm = TokenManager()
    tm.access_token = "tok"
    tm.token_expired = datetime.now() - timedelta(hours=1)
    tm._save_cache()

    fresh = TokenManager()
    assert fresh.access_token == ""
    assert fresh.token_expired is None
