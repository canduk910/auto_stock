"""계좌 통합 리스크 SOFT 게이트 순수 판정 (cycle233, G3′ 패키지).

자문 정본 = `_workspace/domain_consult/cycle232_risk_control_review.md` §2.
Σ오픈리스크 계산은 `portfolio_risk.compute_portfolio_risk_snapshot` (척도 병기)이
담당하고, 이 모듈은 그 결과 %에 대한 **판정만** 한다 — DB/HTTP/시계/registry/
scheduler 절대 미접촉 (portfolio_risk/turtle_sizing/tick_volume 선례, AST G-3 봉인).

임계 의미 (자문 §2.6):
- warn(기본 4.0%) = 관측 경보 — 설계 천장(스윙 3.55%)을 넘으면 설계 밖 사건.
  행위 없음(WARNING only). **발화 빈도가 유일한 학습 신호**라 게이트보다 중요하다.
- block(기본 None = 다크런치) = SOFT 신규 매수 차단. 청산·손절은 절대 차단하지
  않는다(소비처가 check_buy_signal 뿐인 구조로 보장). HARD(강제 청산) 승격 금지.
- 임계를 발화시키려고 낮추는 것 금지 — 그건 통제가 아니라 무작위 매수 억제다.

fail-open: pct 가 None/음수(판정 불가)면 ok — 판정 실패가 매수를 막으면 안 된다
(kojiro Σ캡·check_budget_invariant·weight_config_anomaly 와 동일 규약).
"""

from __future__ import annotations

from typing import Optional


def evaluate_soft_gate(
    open_risk_pct: Optional[float],
    *,
    warn_pct: Optional[float],
    block_pct: Optional[float],
) -> dict:
    """계좌 Σ오픈리스크 % 에 대한 SOFT 게이트 판정.

    Args:
        open_risk_pct: 계좌 대비 실효 Σ오픈리스크 % (None = 판정 불가 → ok).
        warn_pct: 관측 경보선 % (None = 경보 비활성).
        block_pct: SOFT 차단선 % (**None = 다크런치** — 어떤 값도 block 이 되지 않는다).

    Returns:
        ``{"level": "ok"|"warn"|"block", "reasons": list[str]}`` — reasons 는
        관측 로그 병기용(사유 병기, 자문 D1). block > warn 우선.
    """
    try:
        if open_risk_pct is None:
            return {"level": "ok", "reasons": []}
        pct = float(open_risk_pct)
    except (TypeError, ValueError):
        return {"level": "ok", "reasons": []}
    if pct < 0:
        return {"level": "ok", "reasons": []}

    def _valid(threshold: Optional[float]) -> Optional[float]:
        if threshold is None:
            return None
        try:
            t = float(threshold)
        except (TypeError, ValueError):
            return None
        return t if t > 0 else None

    block = _valid(block_pct)
    warn = _valid(warn_pct)

    if block is not None and pct >= block:
        return {
            "level": "block",
            "reasons": [f"account_open_risk {pct:.2f}% >= block {block:.2f}%"],
        }
    if warn is not None and pct >= warn:
        return {
            "level": "warn",
            "reasons": [f"account_open_risk {pct:.2f}% >= warn {warn:.2f}%"],
        }
    return {"level": "ok", "reasons": []}
