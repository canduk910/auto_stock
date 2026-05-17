"""KIS REST API 공통 호출 래퍼.

- 헤더 자동 구성 (authorization, appkey, appsecret, tr_id, custtype)
- Rate Limit: asyncio.Semaphore 초당 20건
- 에러 처리: rt_cd / msg_cd 기반
- 자동 재시도: 네트워크 오류 시 최대 3회 지수 백오프
- 토큰 만료 시 자동 갱신 후 재시도
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections import defaultdict
from typing import Optional

import httpx

from src.auth.token import get_token_manager, token_manager
from src.config import settings
from src.db import system_logs as _system_logs

logger = logging.getLogger(__name__)

# Rate Limit: 초당 최대 20건
_semaphore = asyncio.Semaphore(20)
_last_reset = time.monotonic()
_call_count = 0
_rate_lock = asyncio.Lock()

MAX_RETRIES = 3
BACKOFF_BASE = 0.5  # 초
BACKOFF_JITTER = 0.25  # thundering herd 완화

# ---------------------------------------------------------------------------
# 사이클 7-C (2026-05-18) — REST 시세성 호출 풀 (`kis_request_quote`).
#
# 자금 안전 절대 원칙:
# - 매매(`place_order`/`cancel_order`) / 잔고(`get_balance`/`get_buyable`)
#   / 체결조회(`get_daily_orders`) / 체결통보 → 영원히 메인 단일 (`kis_request`)
# - 시세성 호출만 본 풀에 라우트:
#     fetch_daily_candles, fetch_stock_detail, _fetch_fluctuation_rank,
#     inquire_stock_basics, is_market_open, next_trading_day
# - 보조 계좌(`kis_quote_accounts`) 라운드로빈 + 보조 0개 시 메인 fallback.
# - path 가드 (`QuotePoolPathError`): 시세 화이트리스트 외 경로는 raise.
#
# 메트릭 격리 — 시세 풀 호출은 메인 `_request_metrics` 에 누적되지 않음.
# 일일 로그 분석은 별도 dict `_quote_request_metrics` 조회 가능.
# ---------------------------------------------------------------------------


class QuotePoolPathError(ValueError):
    """매매/잔고/체결조회 path 를 시세 풀에서 호출 시도 시 발생.

    자금 안전 정책 위반 차단용 — 시세 풀은 화이트리스트 6 path 만 허용.
    """


# 시세 풀이 허용하는 KIS REST path 화이트리스트 (정확 일치)
_QUOTE_ALLOWED_PATHS: frozenset[str] = frozenset({
    "/uapi/domestic-stock/v1/quotations/inquire-price",
    "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
    "/uapi/domestic-stock/v1/ranking/fluctuation",
    "/uapi/domestic-stock/v1/quotations/search-stock-info",
    "/uapi/domestic-stock/v1/quotations/chk-holiday",
})

# 보조 매니저별 격리된 Rate Limit 세마포어 (메인 20, 보조 18 보수적)
# label → Semaphore(18). lazy 생성.
_quote_semaphores: dict[str, asyncio.Semaphore] = {}
_quote_semaphores_lock = asyncio.Lock()

# 라운드로빈 인덱스 + 락 (보조 매니저 선택 회전용)
_quote_request_index: int = 0
_quote_index_lock = asyncio.Lock()

# 시세 풀 호출 메트릭 (격리)
_quote_request_metrics: dict = {
    "total": 0,
    "http_5xx": 0,
    "http_4xx": 0,
    "network_err": 0,
    "kis_error": 0,
    "retries": 0,
    "retry_recovered": 0,
    "retry_exhausted": 0,
    "by_label": defaultdict(int),  # label → 호출 카운트 (메인=fallback 카운트 포함)
}


def get_quote_request_metrics() -> dict:
    """시세 풀 누적 메트릭 스냅샷 — 일일 로그 분석에서 사용."""
    return {
        "total": _quote_request_metrics["total"],
        "http_5xx": _quote_request_metrics["http_5xx"],
        "http_4xx": _quote_request_metrics["http_4xx"],
        "network_err": _quote_request_metrics["network_err"],
        "kis_error": _quote_request_metrics["kis_error"],
        "retries": _quote_request_metrics["retries"],
        "retry_recovered": _quote_request_metrics["retry_recovered"],
        "retry_exhausted": _quote_request_metrics["retry_exhausted"],
        "by_label": dict(_quote_request_metrics["by_label"]),
    }


def reset_quote_request_metrics() -> None:
    """시세 풀 메트릭 리셋 — 일일 리포트 INSERT 직후 호출."""
    for k in (
        "total", "http_5xx", "http_4xx", "network_err", "kis_error",
        "retries", "retry_recovered", "retry_exhausted",
    ):
        _quote_request_metrics[k] = 0
    _quote_request_metrics["by_label"].clear()


async def _get_quote_semaphore(label: str) -> asyncio.Semaphore:
    """보조 매니저별 격리된 세마포어 반환 (lazy 생성).

    같은 label 두 번째 호출 → 동일 인스턴스 (단일 락 동기화).
    메인 fallback 은 본 함수 사용 안 함 — `_semaphore` 그대로 사용.
    """
    async with _quote_semaphores_lock:
        sem = _quote_semaphores.get(label)
        if sem is None:
            sem = asyncio.Semaphore(18)
            _quote_semaphores[label] = sem
        return sem


async def _select_quote_label() -> Optional[str]:
    """라운드로빈으로 다음 보조 매니저 label 선택.

    - 보조 0개 또는 DB 조회 실패 → ``None`` (메인 fallback).
    - 같은 label 연속 호출 시 N 회전 후 동일 label.
    """
    global _quote_request_index

    try:
        from src.db import kis_quote_accounts as kqa
        accounts = await kqa.list_accounts(active_only=True)
    except Exception:
        logger.debug("[quote_pool] kis_quote_accounts 조회 실패 — 메인 fallback", exc_info=True)
        return None

    active_labels = [
        a.label for a in accounts
        if getattr(a, "label", None) and getattr(a, "active", True)
    ]
    if not active_labels:
        return None

    async with _quote_index_lock:
        idx = _quote_request_index % len(active_labels)
        _quote_request_index = (_quote_request_index + 1) % (len(active_labels) * 1024 or 1)
        return active_labels[idx]

# 일일 로그 분석용 호출 메트릭 — generate_daily_log_report 후 reset_request_metrics() 호출
_request_metrics: dict = {
    "total": 0,
    "http_5xx": 0,
    "http_4xx": 0,
    "network_err": 0,
    "kis_error": 0,
    "retries": 0,
    # PR-B (2026-05-14): 재시도 최종 결과 카운터 (recovered=재시도 후 성공, exhausted=최대 재시도 후 최종 실패)
    "retry_recovered": 0,
    "retry_exhausted": 0,
    "by_path_5xx": defaultdict(int),
}


def get_request_metrics() -> dict:
    """KIS REST 호출 누적 메트릭 스냅샷 — 일일 로그 분석에서 사용."""
    return {
        "total": _request_metrics["total"],
        "http_5xx": _request_metrics["http_5xx"],
        "http_4xx": _request_metrics["http_4xx"],
        "network_err": _request_metrics["network_err"],
        "kis_error": _request_metrics["kis_error"],
        "retries": _request_metrics["retries"],
        "retry_recovered": _request_metrics["retry_recovered"],
        "retry_exhausted": _request_metrics["retry_exhausted"],
        "top_5xx_paths": sorted(
            _request_metrics["by_path_5xx"].items(),
            key=lambda x: -x[1],
        )[:5],
    }


def reset_request_metrics() -> None:
    """일일 리포트 INSERT 직후 호출."""
    for k in (
        "total",
        "http_5xx",
        "http_4xx",
        "network_err",
        "kis_error",
        "retries",
        "retry_recovered",
        "retry_exhausted",
    ):
        _request_metrics[k] = 0
    _request_metrics["by_path_5xx"].clear()


class KisApiError(Exception):
    """KIS API 응답 에러 (rt_cd != "0")."""

    def __init__(self, rt_cd: str, msg_cd: str, msg1: str) -> None:
        self.rt_cd = rt_cd
        self.msg_cd = msg_cd
        self.msg1 = msg1
        super().__init__(f"KIS API Error [{msg_cd}]: {msg1}")


async def _rate_limit() -> None:
    """초당 20건 Rate Limit을 적용한다."""
    global _last_reset, _call_count
    async with _rate_lock:
        now = time.monotonic()
        if now - _last_reset >= 1.0:
            _last_reset = now
            _call_count = 0
        if _call_count >= 20:
            wait = 1.0 - (now - _last_reset)
            if wait > 0:
                await asyncio.sleep(wait)
            _last_reset = time.monotonic()
            _call_count = 0
        _call_count += 1


async def kis_get(
    path: str,
    tr_id: str,
    params: dict | None = None,
    *,
    hashkey: str = "",
) -> dict:
    """KIS REST GET 요청."""
    return await _request("GET", path, tr_id, params=params, hashkey=hashkey)


async def kis_post(
    path: str,
    tr_id: str,
    body: dict | None = None,
    *,
    hashkey: str = "",
) -> dict:
    """KIS REST POST 요청."""
    return await _request("POST", path, tr_id, body=body, hashkey=hashkey)


async def _request(
    method: str,
    path: str,
    tr_id: str,
    *,
    params: dict | None = None,
    body: dict | None = None,
    hashkey: str = "",
) -> dict:
    """공통 요청 래퍼. 재시도 + Rate Limit + 토큰 갱신."""
    url = f"{settings.kis_base_url}{path}"
    _request_metrics["total"] += 1

    for attempt in range(1, MAX_RETRIES + 1):
        await _rate_limit()
        async with _semaphore:
            token = await token_manager.get_token()
            headers = token_manager.build_headers(tr_id, hashkey=hashkey)
            try:
                async with httpx.AsyncClient() as client:
                    if method == "GET":
                        resp = await client.get(
                            url, headers=headers, params=params, timeout=10
                        )
                    else:
                        resp = await client.post(
                            url, headers=headers, json=body, timeout=10
                        )
                    resp.raise_for_status()
                    data = resp.json()
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if 500 <= status < 600:
                    _request_metrics["http_5xx"] += 1
                    _request_metrics["by_path_5xx"][path] += 1
                elif 400 <= status < 500:
                    _request_metrics["http_4xx"] += 1
                logger.warning(
                    "HTTP %s (attempt %d/%d): %s",
                    status,
                    attempt,
                    MAX_RETRIES,
                    path,
                )
                if attempt == MAX_RETRIES:
                    # PR-B 보강 (Copilot, 2026-05-14): 5xx 한정 — 영구 4xx 는
                    # exhausted 의미 아님 (retry 자체가 무의미한 클라이언트 에러).
                    if 500 <= status < 600:
                        _request_metrics["retry_exhausted"] += 1
                        try:
                            _log_msg = (
                                f"[api_retry_exhausted] path={path} tr_id={tr_id} "
                                f"attempts={MAX_RETRIES} last_status={status} "
                                f"last_msg=HTTPStatusError"
                            )
                            await _system_logs.write_log("ERROR", _log_msg)
                        except Exception:
                            pass
                    raise
                _request_metrics["retries"] += 1
                await asyncio.sleep(
                    BACKOFF_BASE * (2 ** (attempt - 1))
                    + random.uniform(0, BACKOFF_JITTER)
                )
                continue
            except httpx.RequestError as e:
                _request_metrics["network_err"] += 1
                logger.warning(
                    "네트워크 오류 (attempt %d/%d): %s — %s",
                    attempt,
                    MAX_RETRIES,
                    path,
                    e,
                )
                if attempt == MAX_RETRIES:
                    # PR-B (2026-05-14): 최종 실패 카운터 + 영구 로그
                    _request_metrics["retry_exhausted"] += 1
                    try:
                        _log_msg = (
                            f"[api_retry_exhausted] path={path} tr_id={tr_id} "
                            f"attempts={MAX_RETRIES} last_status=network "
                            f"last_msg={type(e).__name__}"
                        )
                        await _system_logs.write_log("ERROR", _log_msg)
                    except Exception:
                        pass
                    raise
                _request_metrics["retries"] += 1
                await asyncio.sleep(
                    BACKOFF_BASE * (2 ** (attempt - 1))
                    + random.uniform(0, BACKOFF_JITTER)
                )
                continue

        # KIS 응답 코드 확인
        rt_cd = data.get("rt_cd", "")
        if rt_cd == "0":
            # PR-B (2026-05-14): 재시도 후 성공 시 recovered 카운터 + 영구 로그
            if attempt > 1:
                _request_metrics["retry_recovered"] += 1
                try:
                    _log_msg = (
                        f"[api_retry_recovered] path={path} tr_id={tr_id} "
                        f"attempts={attempt}"
                    )
                    await _system_logs.write_log("INFO", _log_msg)
                except Exception:
                    pass  # fire-and-forget — 본 흐름 보존
            return data

        msg_cd = data.get("msg_cd", "")
        msg1 = data.get("msg1", "")

        # 토큰 만료 에러 시 갱신 후 재시도
        if "token" in msg1.lower() or "만료" in msg1:
            logger.info("토큰 만료 감지, 재발급 시도")
            await token_manager.issue()
            if attempt < MAX_RETRIES:
                _request_metrics["retries"] += 1
                continue
            # PR-B 보강 (Codex, 2026-05-14): 마지막 시도까지 토큰 만료 지속
            # → KIS-level retry exhaustion. metrics + 영구 로그 누락 차단.
            _request_metrics["retry_exhausted"] += 1
            try:
                _log_msg = (
                    f"[api_retry_exhausted] path={path} tr_id={tr_id} "
                    f"attempts={MAX_RETRIES} last_status=token_expired "
                    f"last_msg={msg1}"
                )
                await _system_logs.write_log("ERROR", _log_msg)
            except Exception:
                pass
            # 그대로 떨어져 [kis_rejection] + raise KisApiError 흐름 보존

        _request_metrics["kis_error"] += 1
        logger.error("KIS API 에러: rt_cd=%s, msg_cd=%s, msg1=%s", rt_cd, msg_cd, msg1)

        # 거부 응답 영구 저장 — 다음 거부부터 원인 즉시 추적 가능 (Phase A1)
        # fire-and-forget: write_log 실패해도 KisApiError raise 흐름은 보존
        try:
            # 민감 키 마스킹: CANO, ACNT_PRDT_CD 제외
            _LOG_BODY_KEYS = (
                "PDNO", "ORD_DVSN", "ORD_UNPR", "ORD_QTY",
                "EXCG_ID_DVSN_CD", "SLL_BUY_DVSN_CD",
            )
            _body_ctx: dict = {}
            if body:
                for _k in _LOG_BODY_KEYS:
                    if _k in body:
                        _body_ctx[_k] = body[_k]
            import json as _json
            _log_msg = (
                f"[kis_rejection] path={path} tr_id={tr_id} "
                f"msg_cd={msg_cd} msg1={msg1} "
                f"body={_json.dumps(_body_ctx, ensure_ascii=False)}"
            )
            await _system_logs.write_log("ERROR", _log_msg)
        except Exception:
            pass  # 로깅 실패는 무시 — 본래 흐름 보존

        raise KisApiError(rt_cd, msg_cd, msg1)

    # 여기까지 도달하면 안 됨
    raise RuntimeError("Unreachable: max retries exhausted")


# ---------------------------------------------------------------------------
# 사이클 7-C — 시세 풀 라우팅 본체
# ---------------------------------------------------------------------------
async def kis_get_quote(
    path: str,
    tr_id: str,
    params: dict | None = None,
    *,
    hashkey: str = "",
) -> dict:
    """시세성 KIS REST GET 요청 — 보조 풀 라운드로빈 + 메인 fallback.

    `_QUOTE_ALLOWED_PATHS` 화이트리스트 외 path 는 `QuotePoolPathError` raise.
    매매/잔고/체결조회는 `kis_get`/`kis_post` (메인 단일) 그대로 사용.
    """
    return await _request_via_quote_pool(
        "GET", path, tr_id, params=params, hashkey=hashkey
    )


async def kis_post_quote(
    path: str,
    tr_id: str,
    body: dict | None = None,
    *,
    hashkey: str = "",
) -> dict:
    """시세성 KIS REST POST 요청 (현재 시세 함수 중엔 미사용, 인터페이스 대칭용)."""
    return await _request_via_quote_pool(
        "POST", path, tr_id, body=body, hashkey=hashkey
    )


async def _request_via_quote_pool(
    method: str,
    path: str,
    tr_id: str,
    *,
    params: dict | None = None,
    body: dict | None = None,
    hashkey: str = "",
) -> dict:
    """시세 풀 요청 본체.

    1. **Path 가드** — 화이트리스트 외 path 거부 (자금 안전 정책)
    2. **라벨 선택** — 라운드로빈 또는 메인 fallback (`_select_quote_label`)
    3. **토큰 매니저** — 메인이면 `token_manager`, 보조면 `get_token_manager(label)`
       — 보조 발급 실패 (`ValueError` 등) → 메인 fallback
    4. **요청 + 재시도** — 메인 `_request` 와 동일 정책 (BACKOFF/JITTER/3회)
    5. **메트릭 격리** — `_quote_request_metrics` 만 갱신
    """
    # 1) Path 가드 — 화이트리스트 외 거부
    if path not in _QUOTE_ALLOWED_PATHS:
        raise QuotePoolPathError(
            f"시세 풀은 화이트리스트 path 만 허용: path={path!r} "
            f"(매매/잔고/체결조회는 kis_request 사용)"
        )

    _quote_request_metrics["total"] += 1

    # 2) 라벨 선택 — 라운드로빈
    label = await _select_quote_label()

    # 3) 토큰 매니저 결정 (보조 실패 시 메인 fallback)
    manager = None
    if label is not None:
        try:
            manager = await get_token_manager(label)
        except Exception:
            logger.debug(
                "[quote_pool] 보조 매니저 발급 실패: label=%s — 메인 fallback",
                label, exc_info=True,
            )
            # 사이클 9 (2026-05-18) — 토큰 발급 실패 카운팅 (KIS 차단 회피)
            try:
                from src.services.quote_session_health import health_monitor as _hm
                await _hm.record_failure(label, reason="token_issue_fail")
            except Exception:
                logger.debug("[quote_pool] health_monitor 호출 실패", exc_info=True)
            manager = None
            label = None  # 메인 fallback

    if manager is None:
        manager = token_manager  # 메인 매니저
        actual_label = "main"
        semaphore = _semaphore
    else:
        actual_label = label
        semaphore = await _get_quote_semaphore(label)

    _quote_request_metrics["by_label"][actual_label] += 1

    url = f"{manager.base_url}{path}"

    for attempt in range(1, MAX_RETRIES + 1):
        await _rate_limit()
        async with semaphore:
            token = await manager.get_token()
            headers = manager.build_headers(tr_id, hashkey=hashkey)
            try:
                async with httpx.AsyncClient() as client:
                    if method == "GET":
                        resp = await client.get(
                            url, headers=headers, params=params, timeout=10
                        )
                    else:
                        resp = await client.post(
                            url, headers=headers, json=body, timeout=10
                        )
                    resp.raise_for_status()
                    data = resp.json()
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if 500 <= status < 600:
                    _quote_request_metrics["http_5xx"] += 1
                    # 사이클 9 (2026-05-18) — 5xx 카운팅 (KIS 차단 회피)
                    # 보조 라벨만 추적 (메인은 안전 가드로 noop)
                    if actual_label != "main":
                        try:
                            from src.services.quote_session_health import (
                                health_monitor as _hm,
                            )
                            await _hm.record_failure(
                                actual_label, reason=f"http_{status}",
                            )
                        except Exception:
                            logger.debug(
                                "[quote_pool] health_monitor 5xx 호출 실패",
                                exc_info=True,
                            )
                elif 400 <= status < 500:
                    _quote_request_metrics["http_4xx"] += 1
                logger.warning(
                    "[quote_pool] HTTP %s (attempt %d/%d): %s label=%s",
                    status, attempt, MAX_RETRIES, path, actual_label,
                )
                if attempt == MAX_RETRIES:
                    if 500 <= status < 600:
                        _quote_request_metrics["retry_exhausted"] += 1
                    raise
                _quote_request_metrics["retries"] += 1
                await asyncio.sleep(
                    BACKOFF_BASE * (2 ** (attempt - 1))
                    + random.uniform(0, BACKOFF_JITTER)
                )
                continue
            except httpx.RequestError as e:
                _quote_request_metrics["network_err"] += 1
                logger.warning(
                    "[quote_pool] 네트워크 오류 (attempt %d/%d): %s — %s label=%s",
                    attempt, MAX_RETRIES, path, e, actual_label,
                )
                if attempt == MAX_RETRIES:
                    _quote_request_metrics["retry_exhausted"] += 1
                    raise
                _quote_request_metrics["retries"] += 1
                await asyncio.sleep(
                    BACKOFF_BASE * (2 ** (attempt - 1))
                    + random.uniform(0, BACKOFF_JITTER)
                )
                continue

        # KIS 응답 코드 확인
        rt_cd = data.get("rt_cd", "")
        if rt_cd == "0":
            if attempt > 1:
                _quote_request_metrics["retry_recovered"] += 1
            # 사이클 9 (2026-05-18) — 성공 카운팅 (KIS 차단 회피 — consecutive reset)
            if actual_label != "main":
                try:
                    from src.services.quote_session_health import (
                        health_monitor as _hm,
                    )
                    await _hm.record_success(actual_label)
                except Exception:
                    logger.debug(
                        "[quote_pool] health_monitor 성공 호출 실패", exc_info=True,
                    )
            return data

        msg_cd = data.get("msg_cd", "")
        msg1 = data.get("msg1", "")

        # 토큰 만료 → 매니저 재발급 후 재시도
        if "token" in msg1.lower() or "만료" in msg1:
            logger.info("[quote_pool] 토큰 만료 감지(label=%s), 재발급 시도", actual_label)
            try:
                await manager.issue()
            except Exception:
                logger.debug("[quote_pool] 토큰 재발급 실패", exc_info=True)
            if attempt < MAX_RETRIES:
                _quote_request_metrics["retries"] += 1
                continue
            _quote_request_metrics["retry_exhausted"] += 1

        _quote_request_metrics["kis_error"] += 1
        logger.error(
            "[quote_pool] KIS API 에러: rt_cd=%s, msg_cd=%s, msg1=%s, label=%s",
            rt_cd, msg_cd, msg1, actual_label,
        )

        # 거부 응답 영구 저장 — fire-and-forget
        try:
            _log_msg = (
                f"[kis_rejection_quote] path={path} tr_id={tr_id} label={actual_label} "
                f"msg_cd={msg_cd} msg1={msg1}"
            )
            await _system_logs.write_log("ERROR", _log_msg)
        except Exception:
            pass

        raise KisApiError(rt_cd, msg_cd, msg1)

    raise RuntimeError("Unreachable: max retries exhausted (quote pool)")
