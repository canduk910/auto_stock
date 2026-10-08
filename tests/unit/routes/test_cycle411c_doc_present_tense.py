"""cycle411 2차 보완 Red F14·B2 — 정본 문서의 실비용 행은 현재형으로 (루트 `CLAUDE.md` 「문서 규약」).

계약 정본 = `_workspace/red/cycle411/cost_overlay.md` 「2차 보완 결정」 F14.

정본(`README.md` · `src/routes/CLAUDE.md`)에는 **지금 동작하는 규칙만** 적는다. 사이클 꼬리표로 「언제
무엇이 추가·보완됐나」 를 적지 않는다 — 그 경위는 `docs/history/<정본 이름>.history.md` 에 append 한다.

| # | 계약 |
|---|---|
| F14a | 두 정본 어디에도 굵은 사이클 꼬리표 `**cycle411…**` 와 `cycle411 보완` 이 없다 |
| F14b | 실비용 칸·엔드포인트를 말하는 표 행에 「보완」 이 없다(`**보완**` · `보완 M1` · `보완 H2` …) |
| F14c | 그 행들에 문장 끝 「추가」(`… 추가.` · `… 추가 —`) 가 없다 — 「언제 추가됐나」 는 이력이다 |
| F14d | 경위는 history 로 — `docs/history/README.history.md` · `docs/history/src-routes-CLAUDE.history.md` 에 cycle411 기록이 있다 |
| B2 | `/api/performance/summary` 행이 「비용 조회 실패 = gross 폴백」 을 말하지 않는다(실패 = net 칸 None) · `/api/strategies/te` 행이 「실패해도 pairs 는 gross 그대로」 를 말하지 않는다 |

「실비용 행」 = 아래 키 중 하나라도 담은 표 행(`|` 로 시작하는 줄). 다른 주제의 「보완」(예: 인증 절의
「보완 = 화면의 2단계 확인」)은 대상이 아니다. `(cycle411, 사용자 결정 10-08 §3 …)` 처럼 값의 출처를
괄호로 다는 것은 규약이 허용한다(굵은 꼬리표·「보완」 만 금지).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]
CANON = {
    "README.md": ROOT / "README.md",
    "src/routes/CLAUDE.md": ROOT / "src" / "routes" / "CLAUDE.md",
}
HISTORY = {
    "README.md": ROOT / "docs" / "history" / "README.history.md",
    "src/routes/CLAUDE.md": ROOT / "docs" / "history" / "src-routes-CLAUDE.history.md",
}

_COST_KEYS = (
    "buy_fee_paid", "sell_cost_rate", "net_profit_loss", "net_total_profit_rate", "daily_fee",
    "/api/costs/today", "/api/costs/daily", "realized_net_sum_krw", "_gross", "fee_sum",
    "cost_overlay", "partial_fee",
)


def _cost_rows(text: str) -> list[str]:
    return [ln for ln in text.splitlines()
            if ln.lstrip().startswith("|") and any(k in ln for k in _COST_KEYS)]


@pytest.mark.parametrize("name", sorted(CANON))
def test_f14a_no_bold_cycle411_tag(name):
    text = CANON[name].read_text(encoding="utf-8")
    bad = [ln[:120] for ln in text.splitlines()
           if re.search(r"\*\*cycle411", ln) or re.search(r"cycle411\s*보완", ln)]
    assert bad == [], bad


@pytest.mark.parametrize("name", sorted(CANON))
def test_f14b_cost_rows_have_no_bowan_history_label(name):
    rows = _cost_rows(CANON[name].read_text(encoding="utf-8"))
    assert rows, f"{name}: 실비용 행을 하나도 못 찾았다 — 키 목록 점검"
    bad = [ln[:120] for ln in rows if "보완" in ln]
    assert bad == [], bad


@pytest.mark.parametrize("name", sorted(CANON))
def test_f14c_cost_rows_have_no_sentence_final_chuga(name):
    rows = _cost_rows(CANON[name].read_text(encoding="utf-8"))
    bad = [ln[:120] for ln in rows if re.search(r"추가\s*(?:[.—|]|$)", ln)]
    assert bad == [], bad


@pytest.mark.parametrize("name", sorted(HISTORY))
def test_f14d_history_carries_cycle411(name):
    path = HISTORY[name]
    assert path.exists(), f"{path.relative_to(ROOT)} 부재 — 걷어낸 경위를 append 할 곳"
    assert "cycle411" in path.read_text(encoding="utf-8")


def _row(path: Path, needle: str) -> str:
    rows = [ln for ln in path.read_text(encoding="utf-8").splitlines()
            if ln.lstrip().startswith("|") and needle in ln]
    assert len(rows) == 1, (needle, len(rows))
    return rows[0]


def test_b2_routes_doc_summary_row_does_not_claim_gross_fallback():
    row = _row(CANON["src/routes/CLAUDE.md"], "`/api/performance/summary")
    assert not re.search(r"gross\s*(값으로|로)\s*폴백", row), row[:200]


def test_b4_routes_doc_te_row_does_not_claim_gross_passthrough():
    row = _row(CANON["src/routes/CLAUDE.md"], "`/api/strategies/te")
    assert "gross 그대로" not in row, row[:200]
