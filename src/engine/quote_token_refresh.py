"""cycle269 (2026-09-08) — 보조 시세 계정 접근토큰 **장 마감 후 고정 시각 강제 재발급** leaf.

## 무엇을 고치는가 (원인 = 메인 세션 3일치 EC2 로그 실측 확정)

보조 시세 계정(quote pool) 7개의 "토큰 발급 완료" 시각이 매일 정확히 ~10분씩
앞으로 당겨져 왔다 — 09-06(토) 15:07~15:13 → 09-07(월) 14:58~15:04 →
09-08(화) 14:48~14:54. 자기 안정화가 없는 **단조 드리프트**라 방치하면 ~5주 뒤
장 시작 전으로 빠진다.

수학적 원인은 `src/auth/token.py::TokenManager._is_valid()` 의 선제 갱신 마진이다::

    return datetime.now() < self.token_expired - timedelta(minutes=10)

보조 계정은 하루 종일 시세 REST 에 쓰이므로 "만료 10분 전" 문턱에 닿는 즉시
다음 `get_token()` 이 `issue()` 를 트리거한다. 새 토큰의 만료는 *그 발급 시점*
+24h 인데 그 시점이 이론적 24h 지점보다 10분 이르다 ⇒ 매일 10분씩 누적 전진.

## 어떻게 고치는가

`token.py` 는 **한 글자도 고치지 않는다**. `TokenManager.issue()` 는 이미 유효성
검사 없이 강제 발급하는 public 메서드이므로, 매일 **고정된 장외 시각**에 활성
보조 계정 전부를 대상으로 `issue()` 를 부르면 그 시각이 매일 새 24h 창의 앵커가
된다. 자연 재발급(위 드리프트 경로)은 그 앵커 뒤에서 다시 앵커를 덮어쓰지 못한다.

## 왜 15:45 인가 (팀장 제안 15:35 에서 조정 — 근거 있는 변경)

강제 재발급을 매일 T 에 걸면 정상 상태에서 자연 문턱은 **T − 10분**에 온다
(어제 T 에 발급 → 만료 오늘 T → 문턱 오늘 T−10분). 이 문턱 창에서 시세 풀이
쓰이면 자연 재발급이 한 번 더 일어나고, 그 직후 T 의 강제 발급이 다시 앵커를
잡는다(드리프트는 어느 쪽이든 멈춘다 — 강제 발급이 항상 **마지막**이므로).

따라서 사용자의 요구("장마감 후에 받았으면 좋겠다")를 만족하려면 T 뿐 아니라
**T − 10분도 KRX 마감(15:30) 이후**여야 한다. T=15:35 는 문턱이 15:25 = 장중이라
요구를 못 지킨다. T=15:45 는 문턱 15:35 이 마감 뒤라 두 경로가 **모두** 장외다.

15:45 는 기존 예정 작업과 겹치지 않는다(비충돌 실측):
- 15:20 `TIME_KRX_MAIN_BUY_STOP`(강제 청산) / 15:30 `TIME_KRX_MAIN_CLOSE` — 이전
- 15:40 `TIME_POST_NXT_OPEN` — WS 구독 이벤트라 토큰 발급 lock 과 무관
- 16:00 일봉 / 16:10 basics / 16:15 purge / 16:20 funnel / 16:30 마스터 /
  16:40 재무 — 7계정 × 61s 직렬화로 15:45~15:52 에 끝나므로 16:00 이전에 완료
- 20:00~20:15(자문/정산)는 CLAUDE.md 금기 창 — 근처도 아니다

## 안전 계약

- **대상은 보조 시세 계정뿐이다.** 주계정(`label=None`, 매매용)은 건드리지
  않는다 — 그 계정의 자연 재발급은 백엔드 재기동 시각에 묶여 있고 재기동은 D6
  (보유 중 장중 재시작 금지)로 이미 장외에만 일어난다.
- **매매 행위 영향 0.** 보조 계정은 주문에 쓰이지 않는다(시세 풀 전용).
  `risk.py` / `order_engine.py` / `api/order.py` / `realtime/**` / `auth/**` /
  전략 7파일 diff 0.
- **WebSocket 무영향.** WS 세션은 `access_token` 이 아니라 별도 엔드포인트
  `/oauth2/Approval` 이 주는 `approval_key` 로 접속·구독한다
  (`src/realtime/websocket.py:213` 이 connect 시 1회 발급 → `:603` 구독 프레임
  재사용). `issue()` 는 `access_token`/`token_expired`/캐시 파일만 갱신하고
  `_approval_key` 를 건드리지 않는다. 게다가 이 드리프트 경로의 자연 재발급이
  지금도 매일 일어나고 있으나 그로 인한 WS 장애 보고는 없다(3일치 로그 실측).
- **계정 단위 예외 흡수.** 한 계정의 발급 실패가 다음 계정을 막지 않는다
  (`_preissue_all_tokens()` 의 try/except 패턴 답습). `issue()` 는 HTTP 성공
  *후*에만 필드를 대입하므로 실패해도 기존 토큰이 살아 있다.
- **61초 직렬화를 우회하지 않는다.** `issue()` 내부의 모듈 전역 lock + 61s gap
  (KIS `/oauth2/tokenP` 분당 1개)을 그대로 탄다. 7계정 ≈ 7분은 **정상**이다.
- **`immediate_first_run=False`.** 부팅 직후 즉시 실행하면 (a) `_boot()` 의
  `_preissue_all_tokens()` 가 방금 캐시로 살린 토큰을 7분에 걸쳐 버리고
  (b) 그 부팅 시각이 새 앵커가 되어 "고정 장외 시각" 이라는 설계가 무너진다.
- **`write_log`/DB 를 쓰지 않는다** — `logger` 만 쓴다(cycle264 leaf 계약).
  단 `src/main.py::_DbLogHandler` 가 INFO 이상을 `system_logs` 로 올리므로
  아래 마커는 20:10 리포트에서도 조회된다.

## 관측 마커 (`[quote_token_refresh]`)

1. `scheduled at=...` — task 기동 시 1회. "배선이 살아 있는가" 의 카나리아.
2. `label=<label> issued expired=<만료시각>` — 계정별 성공 1행.
3. `accounts=%d issued=%d failed=%d` — 회차 요약 1행(`run_periodic_task_loop`).

판독법: 배포 D+1 부터 `[quote_token_refresh]` 요약이 매일 15:45 대에 1행씩
남고, 보조 계정의 "토큰 발급 완료(label=quote-*)" 가 15:35~15:52 창 밖에서는
더 이상 나오지 않아야 한다(D+1 하루는 옛 앵커 탓에 장중 자연 재발급이 한 번 더
날 수 있다 — D+2 부터가 정상 상태다).
"""
from __future__ import annotations

import logging
from datetime import time

from src.engine.daily_emit_cap import KstDailyEmitCap
from src.engine.task_loop_helper import run_periodic_task_loop

logger = logging.getLogger(__name__)

MARKER = "[quote_token_refresh]"

# 매일 강제 재발급 시각 (KST). 상단 "왜 15:45 인가" 참조 — T 와 T−10분이 **모두**
# KRX 마감(15:30) 이후여야 한다는 제약이 이 값을 결정한다.
TIME_QUOTE_TOKEN_REFRESH = time(15, 45)

# `run_periodic_task_loop` 로그 prefix. 신선도 마커(`immediate_skip_if_fresh_hours`)를
# 쓰지 않으므로 `system_config` 접근은 0건이다.
TASK_LABEL = "quote_token_refresh"

_SUMMARY_KEYS = ("accounts", "issued", "failed")
_SUMMARY_LOG_FORMAT = MARKER + " accounts=%d issued=%d failed=%d"

# 관측기 자기 실패 흔적 cap — WARNING 1회/(marker, label)/일 (cycle258 카드 #5).
_emit_cap: KstDailyEmitCap = KstDailyEmitCap()


def _trace_failure(key: str) -> None:
    """관측 emit 자신의 실패 흔적. never-raise (무흔적 `pass` 금지)."""
    try:
        from src.engine.observer_trace import trace_observer_failure

        trace_observer_failure(MARKER, key, _emit_cap, dest_logger=logger)
    except Exception:  # pragma: no cover — 2차 예외도 흡수
        pass


def _emit_issued(label: str, expired) -> None:
    """계정별 성공 1행. 로그 실패가 다음 계정 발급을 막으면 안 된다."""
    try:
        logger.info("%s label=%s issued expired=%s", MARKER, label, expired)
    except Exception:
        _trace_failure(label)


async def refresh_quote_tokens_once() -> dict:
    """활성 보조 시세 계정 전부의 접근토큰을 **강제** 재발급한다.

    `get_token()`(유효하면 캐시 반환)이 아니라 `issue()` 를 부른다 — 이 호출의
    목적이 "토큰을 쓸 수 있게 하는 것" 이 아니라 **만료 앵커를 이 시각으로
    옮기는 것**이기 때문이다.

    Returns:
        `{"accounts": 조회된 활성 계정 수, "issued": 성공 수, "failed": 실패 수}`.
        계정 목록 조회 자체가 실패하면 전부 0 인 dict (회차 skip, 예외 미전파).
    """
    summary = {"accounts": 0, "issued": 0, "failed": 0}

    try:
        from src.db import kis_quote_accounts as kqa

        accounts = await kqa.list_accounts(active_only=True)
    except Exception:
        logger.exception("%s 보조 계정 목록 조회 실패 — 이번 회차 skip", MARKER)
        return summary

    summary["accounts"] = len(accounts)
    if not accounts:
        logger.info("%s 활성 보조 계정 0건 — 재발급 대상 없음", MARKER)
        return summary

    from src.auth.token import get_token_manager

    for account in accounts:
        label = getattr(account, "label", None)
        # 주계정 무접촉 계약의 **코드 레벨** 방어. `get_token_manager(None)` 은 매매용
        # 메인 매니저를 돌려주므로, label 이 비어 오면(스키마상 NOT NULL 이지만 조회
        # 계층이 바뀔 수 있다) 그 계정을 건너뛴다 — 조용히 넘기지 않고 WARNING 을 남긴다.
        if not label:
            summary["failed"] += 1
            logger.warning("%s label 이 비어 있어 skip — 주계정 무접촉 계약", MARKER)
            continue
        try:
            manager = await get_token_manager(label)
            # 강제 발급. 내부 전역 lock + 61s gap 직렬화를 그대로 탄다.
            await manager.issue()
            summary["issued"] += 1
            _emit_issued(str(label), getattr(manager, "token_expired", None))
        except Exception:
            summary["failed"] += 1
            logger.exception(
                "%s label=%s 강제 재발급 실패 — 다음 계정으로 진행", MARKER, label
            )

    return summary


async def task_loop(sched) -> None:
    """매일 `TIME_QUOTE_TOKEN_REFRESH` 에 1회 발화하는 lifecycle 루프.

    `run_periodic_task_loop`(사이클 134) 재사용 — `advance_if_passed=True` 폭주
    차단 · `CancelledError` break · 예외 후 60s 재시도가 이미 검증돼 있다.
    metrics collector 가 없는 task 이므로 `record_fn`/`flush_fn` 은 no-op 이다.
    """
    try:
        logger.info(
            "%s scheduled at=%02d:%02d (KST) — 보조 시세 계정 접근토큰 강제 재발급",
            MARKER, TIME_QUOTE_TOKEN_REFRESH.hour, TIME_QUOTE_TOKEN_REFRESH.minute,
        )
    except Exception:
        _trace_failure("scheduled")

    await run_periodic_task_loop(
        scheduler=sched,
        task_label=TASK_LABEL,
        wait_time=TIME_QUOTE_TOKEN_REFRESH,
        once_callable=refresh_quote_tokens_once,
        record_fn=lambda _summary: None,
        flush_fn=lambda: None,
        summary_log_format=_SUMMARY_LOG_FORMAT,
        summary_keys=_SUMMARY_KEYS,
        immediate_first_run=False,
    )
