"""macro_lite/cache.py 신규 단위 테스트 (REQ-PKG-02).

파일 캐시(get/set/delete/delete_prefix) + NaN/Inf 정제 + MACRO_LITE_CACHE_DIR
호출 시점 반영 + 당일 1회 캐시(get_today/save_today/delete_today) + 자정 경계 +
now_kst_iso() 오프셋 검증.
"""

from datetime import datetime, timedelta

from macro_lite import cache


# ── 기본 TTL 캐시 ────────────────────────────────────────────────

def test_set_and_get_roundtrip():
    cache.set_cached("k1", {"a": 1, "b": "x"}, ttl_hours=1)
    assert cache.get_cached("k1") == {"a": 1, "b": "x"}


def test_get_missing_key_returns_none():
    assert cache.get_cached("does-not-exist") is None


def test_delete_cached_removes_key():
    cache.set_cached("k2", 123)
    assert cache.get_cached("k2") == 123
    cache.delete_cached("k2")
    assert cache.get_cached("k2") is None


def test_delete_prefix_removes_matching_only():
    cache.set_cached("pfx:a", 1)
    cache.set_cached("pfx:b", 2)
    cache.set_cached("other:c", 3)
    cache.delete_prefix("pfx:")
    assert cache.get_cached("pfx:a") is None
    assert cache.get_cached("pfx:b") is None
    assert cache.get_cached("other:c") == 3


def test_ttl_expired_returns_none(monkeypatch):
    fixed_now = datetime(2026, 9, 17, 10, 0, tzinfo=cache.KST)
    monkeypatch.setattr(cache, "now_kst", lambda: fixed_now)
    cache.set_cached("k3", "v", ttl_hours=1)
    assert cache.get_cached("k3") == "v"  # 아직 만료 전

    monkeypatch.setattr(cache, "now_kst", lambda: fixed_now + timedelta(hours=1, minutes=1))
    assert cache.get_cached("k3") is None  # 만료 후


def test_ttl_not_yet_expired_returns_value(monkeypatch):
    fixed_now = datetime(2026, 9, 17, 10, 0, tzinfo=cache.KST)
    monkeypatch.setattr(cache, "now_kst", lambda: fixed_now)
    cache.set_cached("k3b", "v", ttl_hours=1)
    monkeypatch.setattr(cache, "now_kst", lambda: fixed_now + timedelta(minutes=59))
    assert cache.get_cached("k3b") == "v"


# ── NaN/Inf 정제 (get/set 양쪽) ───────────────────────────────────

def test_sanitize_nan_inf_roundtrip_via_set_and_get():
    cache.set_cached("k4", {"a": float("nan"), "b": float("inf"), "c": float("-inf"), "d": 1.5})
    result = cache.get_cached("k4")
    assert result == {"a": None, "b": None, "c": None, "d": 1.5}


def test_sanitize_function_direct():
    assert cache._sanitize(float("nan")) is None
    assert cache._sanitize(float("inf")) is None
    assert cache._sanitize(float("-inf")) is None
    assert cache._sanitize(1.5) == 1.5
    assert cache._sanitize({"x": [float("nan"), 1.0, {"y": float("inf")}]}) == {
        "x": [None, 1.0, {"y": None}]
    }
    assert cache._sanitize("string") == "string"
    assert cache._sanitize(None) is None


def test_sanitize_applied_even_when_value_already_sane():
    cache.set_cached("k5", [1, 2, 3])
    assert cache.get_cached("k5") == [1, 2, 3]


# ── MACRO_LITE_CACHE_DIR 호출 시점 반영 ──────────────────────────

def test_cache_dir_env_reflected_at_call_time(tmp_path, monkeypatch):
    dir_a = tmp_path / "dir_a"
    dir_b = tmp_path / "dir_b"

    monkeypatch.setenv("MACRO_LITE_CACHE_DIR", str(dir_a))
    cache.set_cached("envtest", "A")
    assert (dir_a / "cache.db").exists()

    monkeypatch.setenv("MACRO_LITE_CACHE_DIR", str(dir_b))
    assert cache.get_cached("envtest") is None  # dir_b는 별도 DB — A는 안 보임
    cache.set_cached("envtest", "B")
    assert (dir_b / "cache.db").exists()
    assert cache.get_cached("envtest") == "B"

    # dir_a로 되돌리면 여전히 A가 남아있음 (파일이 분리된 DB라는 증거)
    monkeypatch.setenv("MACRO_LITE_CACHE_DIR", str(dir_a))
    assert cache.get_cached("envtest") == "A"


def test_cache_dir_default_is_home_macro_lite(monkeypatch):
    monkeypatch.delenv("MACRO_LITE_CACHE_DIR", raising=False)
    from pathlib import Path
    assert cache._cache_dir() == Path.home() / "macro-lite"


# ── now_kst / now_kst_iso ─────────────────────────────────────────

def test_now_kst_is_aware_with_kst_offset():
    now = cache.now_kst()
    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(hours=9)


def test_now_kst_iso_has_plus_9_offset():
    iso = cache.now_kst_iso()
    assert iso.endswith("+09:00")


# ── 당일 1회 캐시 (macro_store.get_today/save_today/delete_today 대체) ──

def test_daily_key_format(monkeypatch):
    fixed_now = datetime(2026, 9, 17, 10, 0, tzinfo=cache.KST)
    monkeypatch.setattr(cache, "now_kst", lambda: fixed_now)
    assert cache._daily_key("credit_spread") == "macro:daily:credit_spread:2026-09-17"


def test_save_get_delete_today_roundtrip(monkeypatch):
    fixed_now = datetime(2026, 9, 17, 10, 0, tzinfo=cache.KST)
    monkeypatch.setattr(cache, "now_kst", lambda: fixed_now)

    assert cache.get_today("credit_spread") is None
    cache.save_today("credit_spread", {"x": 1})
    assert cache.get_today("credit_spread") == {"x": 1}

    deleted = cache.delete_today("credit_spread")
    assert deleted == 1
    assert cache.get_today("credit_spread") is None


def test_delete_today_nonexistent_returns_zero():
    assert cache.delete_today("no-such-category") == 0


def test_midnight_boundary_save_then_miss(monkeypatch):
    """23:59 KST 저장 → 같은 시각 hit. 00:01 KST로 이동 → miss (키 날짜 변경 + expires 경과)."""
    before = datetime(2026, 9, 17, 23, 59, tzinfo=cache.KST)
    monkeypatch.setattr(cache, "now_kst", lambda: before)
    cache.save_today("credit_spread", {"v": 1})
    assert cache.get_today("credit_spread") == {"v": 1}

    after = datetime(2026, 9, 18, 0, 1, tzinfo=cache.KST)
    monkeypatch.setattr(cache, "now_kst", lambda: after)
    assert cache.get_today("credit_spread") is None


def test_midnight_boundary_expires_axis_with_raw_stored_key(monkeypatch):
    """macro-sentinel 자문: daily 캐시는 '키의 날짜'(1차 경계)뿐 아니라
    'expires=다음날 00:00'(2차 가드)도 독립적으로 만료를 보장해야 한다.

    get_today()는 호출 시점의 날짜로 키를 다시 조립하므로 날짜 축만 검증된다.
    이 테스트는 23:59에 저장된 "그 순간의" 키 문자열을 고정해두고, 다음날 00:01에
    바로 그 문자열로 get_cached를 직접 호출해도 expires 경과로 None이어야 함을
    (키 축과 무관하게) 검증한다.
    """
    before = datetime(2026, 9, 17, 23, 59, tzinfo=cache.KST)
    monkeypatch.setattr(cache, "now_kst", lambda: before)
    stored_key = cache._daily_key("credit_spread")  # "macro:daily:credit_spread:2026-09-17"
    cache.save_today("credit_spread", {"v": 1})

    # 저장 직후 같은 시각에 같은 문자열로 조회 → hit
    assert cache.get_cached(stored_key) == {"v": 1}

    after = datetime(2026, 9, 18, 0, 1, tzinfo=cache.KST)
    monkeypatch.setattr(cache, "now_kst", lambda: after)
    # 날짜가 바뀌어도 "저장 당시의" 키 문자열 그대로 조회 — expires 축 단독 검증
    assert cache.get_cached(stored_key) is None


def test_daily_key_hit_just_before_midnight_23_59_59(monkeypatch):
    """23:59:59(만료 1초 전)에도 같은 날 저장분은 정상 hit — 과도한 만료 조기화 가드."""
    t = datetime(2026, 9, 17, 23, 59, 59, tzinfo=cache.KST)
    monkeypatch.setattr(cache, "now_kst", lambda: t)
    cache.save_today("credit_spread", {"v": 2})
    assert cache.get_today("credit_spread") == {"v": 2}
    stored_key = cache._daily_key("credit_spread")
    assert cache.get_cached(stored_key) == {"v": 2}


def test_seconds_until_next_kst_midnight(monkeypatch):
    fixed_now = datetime(2026, 9, 17, 10, 0, tzinfo=cache.KST)
    monkeypatch.setattr(cache, "now_kst", lambda: fixed_now)
    seconds = cache._seconds_until_next_kst_midnight()
    assert abs(seconds - 14 * 3600) < 1  # 10:00 -> 다음날 00:00 = 14시간

    fixed_now2 = datetime(2026, 9, 17, 23, 59, tzinfo=cache.KST)
    monkeypatch.setattr(cache, "now_kst", lambda: fixed_now2)
    seconds2 = cache._seconds_until_next_kst_midnight()
    assert abs(seconds2 - 60) < 1  # 23:59 -> 00:00 = 1분


def test_daily_ttl_is_not_fixed_24h(monkeypatch):
    """save_today의 TTL은 '다음날 KST 00:00까지' 동적 계산 — 고정 24h가 아니다."""
    fixed_now = datetime(2026, 9, 17, 15, 30, tzinfo=cache.KST)
    monkeypatch.setattr(cache, "now_kst", lambda: fixed_now)
    cache.save_today("credit_spread", {"v": 1})

    con = cache._conn()
    row = con.execute(
        "SELECT expires FROM cache WHERE key = ?",
        (cache._daily_key("credit_spread"),),
    ).fetchone()
    con.close()
    assert row is not None
    expires = datetime.fromisoformat(row[0])
    if expires.tzinfo is not None:
        expires = expires.astimezone(cache.KST).replace(tzinfo=None)
    # 15:30 KST 저장 -> 다음날 00:00 KST 만료 (8.5시간 후), 24시간 후(다음날 15:30)가 아님
    expected_next_midnight = datetime(2026, 9, 18, 0, 0)
    delta_seconds = abs((expires - expected_next_midnight).total_seconds())
    assert delta_seconds <= 60, f"expires={expires} expected~{expected_next_midnight}"

    not_fixed_24h = datetime(2026, 9, 18, 15, 30)
    assert abs((expires - not_fixed_24h).total_seconds()) > 3600
