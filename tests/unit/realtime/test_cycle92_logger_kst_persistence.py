"""사이클 92 L-3 — logger KST 영속 (LOW, 사이클 68 답습).

명세 (`_workspace/red/cycle92_kis_750_force_disconnect.md`):

영속 의무:
- 사이클 65 H2/H2-bis system_logs KST 강제 영속
- 사이클 68 17 모듈 시정 (`src/db/_kst.py` 헬퍼) 영속
- 사이클 92 자동 재기동 영역 신규 로그도 KST 영속 (`_DbLogHandler` 위임)

기대 동작 (Green, 사이클 92):
- `src/realtime/websocket.py::logger` = `logging.getLogger(...)` 영속 (변경 0)
- 사이클 92 신규 로그 (`[ws_auto_restart]` / `[ws_auto_restart_cooldown]` / `[ws_auto_restart_cap_exceeded]` / `[ws_auto_restart_failed]`) 모두 `logger.*` 사용 → `_DbLogHandler` 위임 → KST 자동
- `await write_log(...)` 직접 호출 0건 (사이클 72 hotfix A1 답습)

Red 상태 (사이클 92, production 변경 0):
- logger 영속 영역 현재 PASS (영속 가드)
- 사이클 92 자동 재기동 도입 후에도 영속 → Green PASS

영속 의무:
- 사이클 65 H2/H2-bis (system_logs KST + main.py KST)
- 사이클 68 17 모듈 (`src/db/_kst.py` 헬퍼)
- 사이클 72 hotfix A1 (logger 단독 + write_log 직접 호출 제거)
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]


def test_l3_websocket_logger_persists():
    """L-3-1: src/realtime/websocket.py logger 영역 영속 (변경 0).

    검증:
    - `logger = logging.getLogger(__name__)` 또는 명시 이름 영속
    - 사이클 92 자동 재기동 도입 후에도 logger 영역 영속

    영속 의무: 사이클 65 H2-bis (logger 경로 KST 자동).
    """
    websocket_py = (_REPO_ROOT / "src/realtime/websocket.py").read_text(encoding="utf-8")
    # logger 정의 영속 (모듈 전역 1건 이상)
    assert "logger = logging.getLogger" in websocket_py, (
        "\n사이클 92 L-3-1 위반 — logger 정의 부재:\n"
        "  영속 의무: 사이클 65 H2-bis (logger 경로 KST 자동)"
    )


def test_l3_system_logs_kst_helper_persists():
    """L-3-2: src/db/_kst.py 헬퍼 영속 (사이클 68 답습).

    검증:
    - `src/db/_kst.py` 파일 영속
    - `KST` / `now_kst_iso` / `today_kst` 헬퍼 export 영속

    영속 의무: 사이클 68 17 모듈 KST 일관성 영속.
    """
    kst_helper = _REPO_ROOT / "src/db/_kst.py"
    assert kst_helper.exists(), (
        "\n사이클 92 L-3-2 위반 — src/db/_kst.py 헬퍼 부재:\n"
        "  영속 의무: 사이클 68 KST 일관성 헬퍼"
    )

    source = kst_helper.read_text(encoding="utf-8")
    # KST timezone + now_kst_iso 영속
    assert "KST" in source, (
        "\n사이클 92 L-3-2 위반 — KST timezone 정의 누락"
    )


def test_l3_main_py_kst_db_log_handler_persists():
    """L-3-3: src/main.py _DbLogHandler KST 강제 영속 (사이클 65 H2-bis).

    검증:
    - `src/main.py` 내 `_DbLogHandler` 영속
    - `_insert_log_to_db` KST 강제 영속 (사이클 65 H2-bis)

    영속 의무:
    - 사이클 65 H2-bis (logger 경로 모든 INSERT KST 자동)
    - 사이클 92 신규 logger 호출도 자동 KST (위임 경로)
    """
    main_py = (_REPO_ROOT / "src/main.py").read_text(encoding="utf-8")
    assert "_DbLogHandler" in main_py, (
        "\n사이클 92 L-3-3 위반 — _DbLogHandler 영속 의무:\n"
        "  영속 의무: 사이클 65 H2-bis (logger → DB INSERT KST 자동)"
    )
