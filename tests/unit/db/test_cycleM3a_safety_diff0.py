"""사이클 M3a (Red) — 매매 안전성 8영역 diff 0 + 호출부 미변경 불변식.

승인 계획: `~/.claude/plans/partitioned-kindling-lollipop.md` (단계 3 — 분석·관찰, 비 hot-path).

M3a = parameter_recommendations / kis_quote_accounts / stock_master_financial 를 pg.* 로 전환하되
**함수 계약(시그니처·반환형·graceful·캐시) 100% 보존** → 소비처(recommendation_engine/scheduler/
scanner/auth.token 등)는 db 함수만 호출하므로 diff 0.

이 파일 = 불변식 가드:
- 매매 안전성 8영역 git diff 0 (3모듈 자체는 8영역 밖 = src/db/).
- 3모듈 함수 심볼(계약 시그니처) 보존.

Red 단계: 대부분 불변식 PASS (전환은 db 모듈 내부 구현 교체일 뿐 계약 불변). M3a 가 8영역을
건드리면 즉시 FAIL. 8영역 파일이 M2 in-flight 로 이미 변경돼 있으면 안 됨(M3a 대상 아님).
"""

from __future__ import annotations

import inspect
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO = Path(__file__).resolve().parents[3]

# 매매 안전성 8영역 (CLAUDE.md 명문화)
_SAFETY_PATHS = (
    "src/engine/risk.py",
    "src/engine/order_engine.py",
    "src/realtime/",
    "src/auth/",
    "src/api/order.py",
    "src/engine/session.py",
    "src/engine/scanner.py",
    "src/engine/strategy_registry.py",
)


def _git_changed_files() -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(_REPO), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    files: list[str] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        files.append(path)
    return files


# ---------------------------------------------------------------------------
# 매매 안전성 8영역 diff 0 (불변식)
# ---------------------------------------------------------------------------
@pytest.mark.skip(reason="RDS 이전(M0~M6) 완료 은퇴 — 워킹트리 git status 기반 8영역 가드는 마이그레이션 종료 후 dead(커밋 시 항상 통과, 로컬 미커밋 8영역 작업마다 오발화). 실 8영역 보호는 각 변경의 git diff 규율로 대체.")
def test_safety_8_areas_unchanged():
    """M3a 는 3 db 모듈 내부 구현 전환 → 8영역 git diff 0 (3모듈 소비처는 db 함수만 호출)."""
    changed = _git_changed_files()
    violations = [
        f for f in changed
        if any(f == p or f.startswith(p) for p in _SAFETY_PATHS)
    ]
    assert not violations, (
        "M3a 는 매매 안전성 8영역 diff 0 이어야 함 (함수 계약 보존 → 호출부 무변경). 변경 감지:\n  "
        + "\n  ".join(violations)
    )


# ---------------------------------------------------------------------------
# 함수 계약 시그니처 보존 — 3모듈
# ---------------------------------------------------------------------------
def test_parameter_recommendations_functions_exist():
    """parameter_recommendations 계약 함수 심볼 보존 (18 호출 계약)."""
    from src.db import parameter_recommendations as pr

    for fn in (
        "insert_recommendation",
        "list_recommendations",
        "get_recommendation",
        "update_recommendation_status",
        "update_backtest_summary",
        "list_recommendations_pending_backtest",
        "list_pending_by_date",
        "expire_pending_before",
    ):
        assert hasattr(pr, fn), f"{fn} 심볼 삭제 금지 (AI자문 계약)."


def test_insert_recommendation_signature_preserved():
    """insert_recommendation 핵심 인자 보존."""
    from src.db import parameter_recommendations as pr

    params = inspect.signature(pr.insert_recommendation).parameters
    for name in (
        "target_date", "strategy_id", "current_params", "recommended_params",
        "reasoning", "metrics", "recommended_weight", "code_review_notes",
        "weight_reasoning",
    ):
        assert name in params, f"insert_recommendation 인자 {name} 삭제 금지."


def test_kis_quote_accounts_functions_exist():
    """kis_quote_accounts 계약 함수 심볼 보존 (11 호출 + 캐시)."""
    from src.db import kis_quote_accounts as kqa

    for fn in (
        "list_accounts",
        "get_account",
        "get_account_by_label",
        "get_credentials_for_token_manager",
        "insert_account",
        "update_account",
        "delete_account",
        "invalidate_list_cache",
    ):
        assert hasattr(kqa, fn), f"{fn} 심볼 삭제 금지 (시세 계좌 풀 계약)."
    assert hasattr(kqa, "LabelConflictError"), "LabelConflictError 심볼 삭제 금지."


def test_stock_master_financial_functions_exist():
    """stock_master_financial 계약 함수 심볼 보존 (8 호출)."""
    from src.db import stock_master_financial as smf

    for fn in (
        "upsert_financial_batch",
        "get_financial_series",
        "max_stac_yymm",
        "count_all",
    ):
        assert hasattr(smf, fn), f"{fn} 심볼 삭제 금지 (재무 계층 계약)."


# ---------------------------------------------------------------------------
# 호출부 계약 보존 — 소비처가 여전히 db 함수를 호출 (텍스트 존재 = 계약 유지)
# ---------------------------------------------------------------------------
def test_auth_token_still_calls_credentials_contract():
    """auth/token.py 가 get_credentials_for_token_manager 계약을 여전히 호출 (평문 노출 유일 경로).

    ⚠️ auth/ 는 매매 안전성 8영역 — M3a 는 이 파일을 건드리지 않고 db 함수 계약만 보존.
    """
    auth_dir = _REPO / "src" / "auth"
    combined = "".join(
        p.read_text(encoding="utf-8") for p in auth_dir.glob("*.py")
    )
    assert "get_credentials_for_token_manager" in combined, (
        "auth 의 credentials 계약 호출이 사라짐 — 계약 변경 신호 (M3a 는 계약 보존)."
    )
