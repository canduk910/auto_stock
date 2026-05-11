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

import httpx

from src.auth.token import token_manager
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

# 일일 로그 분석용 호출 메트릭 — generate_daily_log_report 후 reset_request_metrics() 호출
_request_metrics: dict = {
    "total": 0,
    "http_5xx": 0,
    "http_4xx": 0,
    "network_err": 0,
    "kis_error": 0,
    "retries": 0,
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
        "top_5xx_paths": sorted(
            _request_metrics["by_path_5xx"].items(),
            key=lambda x: -x[1],
        )[:5],
    }


def reset_request_metrics() -> None:
    """일일 리포트 INSERT 직후 호출."""
    for k in ("total", "http_5xx", "http_4xx", "network_err", "kis_error", "retries"):
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
