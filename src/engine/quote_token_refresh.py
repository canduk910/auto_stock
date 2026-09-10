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

`token.py` 는 **한 글자도 고치지 않는다**. **cycle270 정정 (2026-09-10)**: 이
절의 원래 서술("`issue()` 를 부르면 그 시각이 새 앵커")은 09-10 실측으로
반증됐다 — 09-09/09-10 이틀 강제 발급 7/7 이 매번 같은 날 장중 자연 재발급과
**완전히 동일한 만료**를 돌려받아 앵커가 한 번도 옮겨지지 않았다. KIS
`/oauth2/tokenP` 는 유효 토큰이 살아 있으면 **같은 토큰·같은 만료**를 돌려주기
때문이다(사용자 승인 하 09-10 17:13 fire 계정 1건 수동 실측이 유일한 반증 —
`revoke` 0.20s → `issue` 0.23s 로 만료가 실제로 옮겨갔다). 그래서 이제
`issue()` 앞에 `TokenManager.revoke()` 를 **계정 단위로 먼저** 호출해 앵커를
비운 뒤 발급한다 — 매일 **고정된 장외 시각**에 활성 보조 계정 전부를 대상으로
`revoke()`→`issue()` 페어를 순차 실행하면 그 시각이 매일 새 24h 창의 앵커가
된다. 자연 재발급(위 드리프트 경로)은 그 앵커 뒤에서 다시 앵커를 덮어쓰지
못한다. `revoke()` 실패는 `issue()` 시도를 막지 않는다(무토큰 방치 금지 =
fail-open) — 다만 그 계정만 이번 회차에 앵커가 그대로 남는다.

## 왜 19:00 인가 (2026-09-10 밤 cycle270-C — 21:30 은 발화할 수 없었다)

강제 재발급을 매일 T 에 걸면 정상 상태에서 자연 문턱은 **T − 10분**에 온다
(어제 T 에 발급 → 만료 오늘 T → 문턱 오늘 T−10분). 이 문턱 창에서 시세 풀이
쓰이면 자연 재발급이 한 번 더 일어나고, 그 직후 T 의 강제 발급이 다시 앵커를
잡는다(드리프트는 어느 쪽이든 멈춘다 — 강제 발급이 항상 **마지막**이므로).

제약은 세 가지다:
(a) T 와 **T − 10분이 모두 KRX 장중(09:00~15:30) 밖**.
(b) 7계정 × 61s ≈ 7분의 직렬화 창이 REST 를 많이 쓰는 예정 작업과 겹치지 않을 것.
(c) **T 는 스케줄러 task 루프의 생존 창 안**이어야 한다 — `scheduler.start()` 는
    20:10 정산 → 로그 분석 → purge → `_reset_daily_state()` 뒤 본문이 끝나고
    `finally` 가 백그라운드 task(`_quote_token_refresh_task` 포함)를 전부 cancel 하며
    `_running = False` 가 된다. 그 뒤 시각은 **매일 0회 발화**한다(로그에는 부팅 시
    "scheduled at=" 한 줄만 남아 배선이 살아 있는 것처럼 보인다).

2026-09-10 사용자 요구 "장마감 후 20:00 이후" 에 맞춰 같은 날 21:30(cycle270-B)으로
옮겼으나 (c) 를 놓쳐 무발화였다(같은 밤 D8 명세 §7 이 실측+코드로 지적). 20:00 이후는
루프 수명 구조를 바꾸지 않는 한 불가능하다(20:00~20:10 은 자문·유니버스·정산의 REST
집중 창이라 더 나쁘다) → 루프 안에서 가장 늦고 조용한 19:00 으로 재이동.

19:00 은 아래 창을 전부 피한다(비충돌 실측, `test_c9`·`test_c10` 이 잠근다):
- 15:30 마감 / 16:00 일봉 / 16:10 basics / 16:15 purge / 16:20 funnel / 16:30 마스터 /
  16:40 재무 — 전부 문턱 18:50 이전에 끝난다(D8 로 일봉이 18:10 으로 가도 18:2x 완료)
- 19:50 `TIME_NXT_POST_BUY_STOP` / 20:00 자문·유니버스·NXT 종료 / 20:10 정산 — T+8분(19:08) 이전
- NXT 애프터(15:30~20:00)는 WS 기반이라 REST 시세 풀 부하가 작고, WS `approval_key` 는 별개 경로

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
2. `label=<label> issued expired=<만료시각> revoked=<True|False>` — 계정별
   성공 1행(**cycle270** — `revoked` 필드 추가, 접두는 byte 보존).
   `revoked=False` 면 `revoke()` 가 실패해 그 계정은 이번 회차에 앵커가
   이동하지 않았다는 뜻이다(별도 WARNING 도 동반).
3. `accounts=%d issued=%d failed=%d` — 회차 요약 1행(`run_periodic_task_loop`).
   **cycle270 에서도 이 3필드는 불변** — revoke 성패는 계정별 행으로 이미
   관측되므로 요약에 넣지 않기로 결정했다.

판독법: 배포 D+1 부터 `[quote_token_refresh]` 요약이 매일 19:00 대에 1행씩
남고, 보조 계정의 "토큰 발급 완료(label=quote-*)" 가 18:50~19:08 창 밖에서는
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

# 매일 강제 재발급 시각 (KST). 상단 "왜 19:00 인가" 참조 — T·T−10분이 장중 밖이고,
# T+8분이 19:50/20:00 앞이며, **T 가 스케줄러 루프 생존 창(~20:10) 안**이어야 한다.
# 이력: 15:45(cycle269) → 21:30(cycle270-B, 루프 밖이라 무발화) → 19:00(cycle270-C, 2026-09-10).
TIME_QUOTE_TOKEN_REFRESH = time(19, 0)

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


def _emit_issued(label: str, expired, revoked: bool) -> None:
    """계정별 성공 1행. 로그 실패가 다음 계정 발급을 막으면 안 된다."""
    try:
        logger.info(
            "%s label=%s issued expired=%s revoked=%s", MARKER, label, expired, revoked
        )
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

            # KIS `/oauth2/tokenP` 는 유효 토큰이 있으면 같은 토큰·같은 만료를
            # 돌려준다(cycle270, 09-10 실측) — issue() 단독으로는 앵커가 안
            # 옮겨진다. revoke() 로 먼저 비운다. 실패해도 issue() 는 시도한다
            # (무토큰 방치 금지 = fail-open 방향) — 그 계정만 앵커가 그대로 남는다.
            revoked = True
            try:
                await manager.revoke()
            except Exception:
                revoked = False
                logger.warning(
                    "%s label=%s 토큰 폐기 실패 — 발급은 계속 시도, "
                    "이번 회차 앵커는 이동하지 않음",
                    MARKER, label,
                )

            # 강제 발급. 내부 전역 lock + 61s gap 직렬화를 그대로 탄다.
            await manager.issue()
            summary["issued"] += 1
            _emit_issued(str(label), getattr(manager, "token_expired", None), revoked)
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
