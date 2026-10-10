"""대시보드 경고등 — 집계 명부 + 순수 집계 함수 (cycle434).

사용자 지시(2026-10-10) — "잔고/권리 불일치 등 일일작업 작업오류 발생 시 대시보드에
경고등 추가". `GET /api/system/alerts`(`src/routes/system.py`)가 이 모듈 하나만
참조한다 — 명부를 고치는 사이클은 이 파일 한 곳만 보면 된다(cycle433 이 동시에
`[holding_qty_unexplained]` 세부 분류를 늘리고 있어 접두사/포함 매칭으로 흡수한다).

설계:
- `MARKERS` 의 `pattern` 은 SQL `ILIKE` 패턴(`%` 포함)이자 `_like_to_regex()` 로
  파이썬 정규식으로도 변환된다 — DB 쪽 필터(`src/db/system_logs.py::get_today_alert_logs`)와
  집계 쪽 분류(`categorize()`)가 같은 문자열을 쓴다(이중 정의 금지).
- `_DbLogHandler`(`src/main.py`)가 `logger.*` 호출을 `f"[{record.name}] {message}"` 로
  한 번 더 감싸 `system_logs` 에 적재하는 경로와, 코드가 `write_log()` 를 직접 불러 원문
  그대로 적재하는 경로가 공존한다(같은 사건이 두 줄로 남을 수도 있다) — 그래서 패턴은
  전부 **포함(contains) 매칭**이다(`%marker%`), 메시지 맨 앞에 붙는다고 가정하지 않는다.
- 이 모듈은 `src.db`/`src.engine.scheduler` 등 무엇도 import 하지 않는다(순수 leaf,
  8영역·`scheduler.py` 무접촉).

제외한 것(명부에 넣지 않는다, "항상 켜진 경고등은 무시당한다"):
- 매크로 레짐·외부 백테스트 MCP 다운 — 이미 알려진 상시 상태(운영 결정으로 방치 중).
- `[priority_drop]`/`[universe_excluded]`/`[no_feed_held]` 류 중 *설계상 정상 범위*로
  문서화된 관측(예: 41슬롯 초과 시 LOW 드롭)은 넣지 않는다. `no_feed_held` 자체는
  "KRX 전용 보유 종목의 WS 결손 증거"라 넣는다(장부 불일치 쪽 — 아래 참조).
- `[weight_config_anomaly]`, `[weight_unit_violation]` 등 즉시 422/거부로 끝나는 쓰기
  경로 가드 — 그 호출이 이미 실패를 반환해 운영자가 즉시 안다(경고등 없이도 보인다).
- `[corporate_action_midsync]`(cycle433, 진행 중 — 15분 잔고 동기화 중간 관측,
  `result=in_progress|pending_notice|operator_share|explained_by_orders|lookup_failed`) —
  **INFO 뿐이라 WARNING 이상만 보는 이 쿼리에 안 걸린다**(명부에 패턴을 올려도 효과가 없어
  올리지 않는다). 그 종목이 끝까지 안 풀리면 `[holding_qty_unexplained]`(ERROR 이상)로
  승격해 여기 명부가 잡는다 — 중간 관측 자체를 경고등 재료로 쓰지 않는다.
"""

from __future__ import annotations

import re
from typing import NamedTuple

# ---------------------------------------------------------------------------
# 범주 명부
# ---------------------------------------------------------------------------


class AlertCategory(NamedTuple):
    key: str
    label: str
    color: str  # "red" | "yellow"


CATEGORIES: tuple[AlertCategory, ...] = (
    AlertCategory("ledger_mismatch", "장부 불일치", "red"),
    AlertCategory("order_unknown_or_exit_failure", "주문 결과 모름 · 청산 실패", "red"),
    AlertCategory("daily_job_failure", "일일 작업 실패", "yellow"),
)

_CATEGORY_BY_KEY: dict[str, AlertCategory] = {c.key: c for c in CATEGORIES}

# 레벨 랭크(높을수록 심각) — `system_logs.log_level` 비교용.
_LEVEL_RANK: dict[str, int] = {"WARNING": 1, "ERROR": 2, "CRITICAL": 3}

# `get_today_alert_logs` 가 거를 최소 레벨 — WARNING 이상.
ALERT_LOG_LEVELS: tuple[str, ...] = ("WARNING", "ERROR", "CRITICAL")


class AlertMarker(NamedTuple):
    pattern: str  # SQL ILIKE 패턴(%  wildcard 포함) — message 컬럼 대상, 포함 매칭
    category: str  # CATEGORIES 의 key
    note: str  # 디버깅용 설명(응답에는 나가지 않는다)


MARKERS: tuple[AlertMarker, ...] = (
    # ------------------------------------------------------------------
    # 장부 불일치 (red)
    # ------------------------------------------------------------------
    AlertMarker(
        "%[holding_qty_unexplained]%",
        "ledger_mismatch",
        "보유수량이 KIS 잔고와 다른데 설명이 안 됨 (corporate_action_reconcile/boot_manager)."
        " cycle433 — 3영업일 연속이면 그 행이 CRITICAL 로 올라간다. 접두사 매칭이라 그 승격도"
        " 그대로 걸린다(이 모듈이 레벨을 가정하지 않고 system_logs 의 실제 log_level 을 읽는다).",
    ),
    AlertMarker(
        "%[fill_notice_missing]%",
        "ledger_mismatch",
        "cycle433(진행 중, main 미병합) — 우리 주문의 체결통보가 30분 넘게 안 옴(통보 유실"
        " 확정). ERROR.",
    ),
    AlertMarker(
        "%[corporate_action_ctrga_reconciled] result=mismatch%",
        "ledger_mismatch",
        "액면병합·분할·감자 대사 결과 불일치 (21:30 정산)",
    ),
    AlertMarker(
        "%[corporate_action_ctrga_merger_held]%",
        "ledger_mismatch",
        "합병·회사분할 권리가 걸린 보유 종목 (자동 반영 없음)",
    ),
    AlertMarker(
        "%[sell_insufficient_unexplained]%",
        "ledger_mismatch",
        "매도 수량부족 거부가 설명 안 됨 (실보유 추정치와 장부가 어긋남)",
    ),
    AlertMarker(
        "%[boot_recover_strategy_unknown]%",
        "ledger_mismatch",
        "부팅 복구 시 보유 종목의 소유 전략을 특정하지 못함",
    ),
    AlertMarker(
        "%[buy_fill_fallback_orphan]%",
        "ledger_mismatch",
        "체결통보가 주문번호 매핑 없이 도착 — 고아 체결 귀속 (momentum 폴백)",
    ),
    AlertMarker(
        "%[no_feed_held]%",
        "ledger_mismatch",
        "구독 중인데 WS 체결 기록이 0인 KRX 전용 보유 종목 (REST 는 체결이 늘고 있다)",
    ),

    # ------------------------------------------------------------------
    # 주문 결과 모름 · 청산 실패 (red)
    # ------------------------------------------------------------------
    AlertMarker(
        "%[sell_send_unknown]%",
        "order_unknown_or_exit_failure",
        "매도 주문을 보냈는지 자체를 모름 (전송 중 예외, 증거 없음)",
    ),
    AlertMarker(
        "%[force_clear_ticker_error]%",
        "order_unknown_or_exit_failure",
        "15:20 강제청산 루프에서 종목 하나가 예외로 실패",
    ),
    AlertMarker(
        "%[sell_post_send_error]%",
        "order_unknown_or_exit_failure",
        "매도 접수 성공 후(장부 기록 전) 예외 — 예산을 점유한 채 장부가 없는 주문",
    ),
    AlertMarker(
        "%[buy_post_send_error]%",
        "order_unknown_or_exit_failure",
        "매수 접수 성공 후(장부 기록 전) 예외 — 예산을 점유한 채 장부가 없는 주문",
    ),
    AlertMarker(
        "%매도 주문 최종 실패:%",
        "order_unknown_or_exit_failure",
        "재시도를 다 쓴 미분류 매도 거부 (_handle_sell_final_failure)",
    ),
    AlertMarker(
        "%[after_exit_giveup]%",
        "order_unknown_or_exit_failure",
        "애프터마켓 청산 재시도를 포기 — 다음 09:00 로 전환",
    ),
    AlertMarker(
        "%[status_exit_giveup]%",
        "order_unknown_or_exit_failure",
        "관리종목·단기과열 강제청산을 하루 발사 한도 안에서 포기",
    ),

    # ------------------------------------------------------------------
    # 일일 작업 실패 (yellow)
    # ------------------------------------------------------------------
    AlertMarker(
        "%전략수정 AI자문 생성 실패%",
        "daily_job_failure",
        "20:00 AI 자문(recommendation_engine.generate_recommendations) 실패",
    ),
    AlertMarker(
        "%AI 자문 자동 적용 실패%",
        "daily_job_failure",
        "20:00 AI 자문 자동 적용(auto_apply_recommendations) 실패",
    ),
    AlertMarker(
        "%[daily_metrics_snapshot_failed]%",
        "daily_job_failure",
        "20:05 metrics 1차 스냅샷 저장 실패",
    ),
    AlertMarker(
        "%[daily_metrics_snapshot] 배선 실패%",
        "daily_job_failure",
        "20:05 metrics 1차 스냅샷 — 호출부 배선 자체 예외",
    ),
    AlertMarker(
        "%[stock_master_daily_load]%예외 graceful%",
        "daily_job_failure",
        "20:30 일봉 적재 task loop 예외 (즉시실행/정기루프 공통)",
    ),
    AlertMarker(
        "%일일 로그 분석 리포트 생성 실패%",
        "daily_job_failure",
        "21:30 일일 로그 분석(log_analysis_engine.generate_daily_log_report) 실패",
    ),
    AlertMarker(
        "%[stock_master_financial_load]%예외 graceful%",
        "daily_job_failure",
        "16:40(주1회) 재무 5TR 적재 task loop 예외",
    ),
    AlertMarker(
        "%[trade_cost_reconcile_failed]%",
        "daily_job_failure",
        "수수료·제세금 자동 대사 실패(system_config.trade_cost_reconcile_time)",
    ),
    AlertMarker(
        "%[daily_head_stale]%",
        "daily_job_failure",
        "부팅 시 일봉 헤드가 직전 영업일보다 오래됨 — 저녁 일봉 적재 결손",
    ),
    AlertMarker(
        "%[daily_bar_finalize]%result=error%",
        "daily_job_failure",
        "다음날 아침 일봉 확정(daily_bar_finalize) 실패",
    ),
    AlertMarker(
        "%[daily_bar_finalize]%result=hard_cap%",
        "daily_job_failure",
        "일봉 확정이 하드캡에 걸려 중단",
    ),
)

# DB 질의용 — 중복 패턴 제거, 순서는 보존(먼저 나온 것이 우선 분류).
ALL_PATTERNS: tuple[str, ...] = tuple(dict.fromkeys(m.pattern for m in MARKERS))


def _like_to_regex(pattern: str) -> re.Pattern[str]:
    """SQL `ILIKE` 패턴(`%` wildcard) → 대소문자 무시 파이썬 정규식.

    `%` 외 문자는 전부 리터럴로 escape 한다(`[`·`]`·`.` 등이 패턴에 그대로 나온다
    — 예: `%[holding_qty_unexplained]%`).
    """
    parts = pattern.split("%")
    body = ".*".join(re.escape(p) for p in parts)
    return re.compile(body, re.IGNORECASE | re.DOTALL)


_COMPILED: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (_like_to_regex(m.pattern), m.category) for m in MARKERS
)


def categorize(message: str) -> str | None:
    """메시지가 명부의 어느 범주에 속하는지 — 첫 매치 우선, 없으면 `None`."""
    if not message:
        return None
    for regex, category in _COMPILED:
        if regex.search(message):
            return category
    return None


def _level_rank(level: str | None) -> int:
    if not level:
        return 0
    return _LEVEL_RANK.get(level.upper(), 0)


def _max_level(a: str | None, b: str) -> str:
    return b if _level_rank(b) >= _level_rank(a) else a  # type: ignore[return-value]


def build_summary(rows: list[dict], *, as_of_iso: str, recent_limit: int = 5) -> dict:
    """오늘(KST) 대상 WARNING 이상 행(이미 날짜·레벨로 좁혀진 것)을 범주별로 집계한다.

    Args:
        rows: `{"log_level": str, "message": str, "timestamp": str}` 꼴 dict 리스트
            (`src/db/system_logs.py::get_today_alert_logs` 반환 그대로, `timestamp` 순서 무관
            — 이 함수가 min/max 로 재계산한다).
        as_of_iso: 응답 `as_of`(집계 실행 시각, KST ISO).
        recent_limit: 범주별 최근 메시지 cap.

    Returns:
        `{as_of, status, categories: [...]}`. DB 조회 자체가 실패한 경우는 이 함수가
        아니라 호출자(`unknown_summary`)가 처리한다 — 이 함수는 "조회는 됐다"를 전제한다.
    """
    buckets: dict[str, dict] = {
        c.key: {"count": 0, "max_level": None, "first_at": None, "last_at": None, "recent": []}
        for c in CATEGORIES
    }

    for row in rows:
        message = row.get("message") or ""
        category = categorize(message)
        if category is None or category not in buckets:
            continue
        b = buckets[category]
        b["count"] += 1
        level = (row.get("log_level") or "").upper() or None
        b["max_level"] = _max_level(b["max_level"], level) if level else b["max_level"]
        ts = row.get("timestamp")
        if ts:
            if b["first_at"] is None or ts < b["first_at"]:
                b["first_at"] = ts
            if b["last_at"] is None or ts > b["last_at"]:
                b["last_at"] = ts
        if len(b["recent"]) < recent_limit:
            b["recent"].append(
                {"level": level, "message": message[:500], "timestamp": ts}
            )

    categories_out = []
    has_red = False
    has_yellow = False
    for c in CATEGORIES:
        b = buckets[c.key]
        if b["count"] > 0:
            if c.color == "red":
                has_red = True
            elif c.color == "yellow":
                has_yellow = True
        categories_out.append({
            "key": c.key,
            "label": c.label,
            "color": c.color,
            "count": b["count"],
            "max_level": b["max_level"],
            "first_at": b["first_at"],
            "last_at": b["last_at"],
            "recent_messages": b["recent"],
        })

    status = "red" if has_red else ("yellow" if has_yellow else "green")
    return {"as_of": as_of_iso, "status": status, "categories": categories_out}


def unknown_summary(as_of_iso: str) -> dict:
    """DB 조회 자체가 실패했을 때 — `status="unknown"`, 범주는 전부 모름."""
    categories_out = [
        {
            "key": c.key,
            "label": c.label,
            "color": c.color,
            "count": None,
            "max_level": None,
            "first_at": None,
            "last_at": None,
            "recent_messages": [],
        }
        for c in CATEGORIES
    ]
    return {"as_of": as_of_iso, "status": "unknown", "categories": categories_out}
