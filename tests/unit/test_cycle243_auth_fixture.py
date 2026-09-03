"""cycle243 Red (C) — 기존 스위트 보호 픽스처의 **작동 증명**.

명세: `_workspace/red/cycle243_api_auth_spec.md` §3.C(C-1~C-3) · §0-⑦

인증을 켜면 40파일·수집 **201케이스가 401 로 전멸**하고 coverage gate(`fail_under=60`)
까지 동반 실패한다(진입 경로 = `tests/contract/conftest.py:303` 13파일 + 직접
`from src.main import app` 27파일). TestClient 가 27곳에서 각자 생성되므로 "기본 헤더
주입" 은 27곳 수정이 필요해 부적합하고, seam 은 한 곳이어야 한다.

## 픽스처 계약 (Green 에서 `tests/conftest.py` 에 추가된다)

```python
@pytest.fixture(autouse=True)
def _neutralize_api_auth(request, monkeypatch):
    if request.node.get_closest_marker("real_api_auth"):
        return                      # 인증 자체를 검증하는 테스트 — 중립화 금지
    try:
        from src.middleware import api_auth as _mod
        monkeypatch.setattr(_mod, "authorize", lambda scope: "", raising=False)
    except Exception:
        pass
```

⚠️ **프로덕션 코드에 `_TEST_BYPASS` 류 플래그를 두지 않는다.** 판정 함수 자체를
테스트가 갈아끼우는 형태여야 런타임에 우회 경로가 **존재하지 않는다**. 그래서
미들웨어는 `authorize` 를 모듈 전역 이름으로 호출해야 하고(§2.3.1), M-21(메서드로
변경)은 이 파일의 C-1 이 잡는다.

## C-1 의 공허성 방지

"마커 없는 테스트가 200 이다" 는 인증이 아예 없는 Red 에서도 참이라 그것만으로는
공허하다. 그래서 C-1 은 **판정 함수가 실제로 중립화됐다는 것**을 함께 단언한다 —
설정 키가 있고 헤더가 없는 scope 에서도 `authorize` 가 `""` 를 돌려주는지.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[2]
REAL_KEY = "cycle243FIXTUREKEYaaaaaaaaaaaaaaaaaaaaaaaaaa"


def _mw():
    try:
        import src.middleware.api_auth as mod
    except Exception as exc:  # pragma: no cover - Red 경로
        pytest.fail(f"Red — src/middleware/api_auth.py 미구현: {exc!r}")
    return mod


def _set_key(monkeypatch: pytest.MonkeyPatch, key: str = REAL_KEY) -> None:
    from src.config import settings

    for name, value in (("api_auth_key", key), ("api_allowed_origins", "")):
        if not hasattr(settings, name):
            pytest.fail(f"Red — settings.{name} 미구현 (src/config.py §2.2)")
        monkeypatch.setattr(settings, name, value)


def _bare_scope() -> dict:
    return {
        "type": "http",
        "method": "GET",
        "path": "/api/trading/status",
        "headers": [(b"host", b"testserver")],
        "client": ("203.0.113.9", 51234),
        "query_string": b"",
    }


def test_unmarked_test_when_auth_enabled_then_still_200(monkeypatch):
    """C-1 — 마커 없는 기존 케이스는 인증이 켜져도 종전대로 200 을 본다."""
    mod = _mw()
    _set_key(monkeypatch)

    # (1) 픽스처가 실제로 판정을 중립화했는가 — 이 단언이 없으면 C-1 은 공허하다.
    verdict = mod.authorize(_bare_scope())
    assert verdict == "", (
        "autouse 픽스처가 `authorize` 를 중립화하지 않았다 — 기존 201 케이스가 401 로 "
        f"전멸한다 (verdict={verdict!r})"
    )

    # (2) 그 결과로 앱 호출이 종전대로 200.
    from src.main import app

    resp = TestClient(app).get("/api/trading/status")
    assert resp.status_code == 200


@pytest.mark.real_api_auth
def test_marked_test_when_opted_out_then_401(monkeypatch):
    """C-2 — 마커를 붙이면 실제 판정이 살아난다(옵트아웃 작동 증명).

    이 케이스가 없으면 "픽스처가 전역으로 인증을 죽였다" 와 "인증이 애초에 없다" 를
    구분할 수 없다.
    """
    _mw()
    _set_key(monkeypatch)

    from src.main import app

    resp = TestClient(app).get("/api/trading/status")
    assert resp.status_code == 401


def test_marker_when_declared_then_registered_in_pyproject():
    """C-3 — `real_api_auth` 마커가 `pyproject.toml` 에 등재돼 있다.

    `filterwarnings = ["error"]` 라 미등록 마커는 `PytestUnknownMarkWarning` → 즉시
    스위트 사망이다. Red 와 같은 커밋에 등재하는 것이 계약(명세 §9.1).
    """
    data = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    markers = data["tool"]["pytest"]["ini_options"]["markers"]
    names = {m.split(":", 1)[0].strip() for m in markers}
    assert "real_api_auth" in names, sorted(names)
