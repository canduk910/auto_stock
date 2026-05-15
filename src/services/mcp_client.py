"""외부 MCP 백테스트 서버 통신 클라이언트 (Phase 1).

JSON-RPC 2.0 over Streamable HTTP/SSE (MCP 2025-03-26 프로토콜).

특징:
- ``httpx.AsyncClient`` 기반 async 환경 일관성 (auto_stock 의 KIS REST 와 동일)
- 모듈 레벨 싱글톤(`_client_instance`) — 세션 ID + 커넥션 풀 재사용
- 421 (세션 만료) → 1회 자동 재초기화 + 재시도
- ``KIS_MCP_ENABLED=false`` 면 ``call_tool`` 은 ``ConfigError``,
  ``health_check`` 는 ``False`` 반환 (자동매매 핵심 흐름 영향 0)

참조 패턴: ``stock-manager/services/mcp_client.py`` (동기 → async 이식)
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx

from src.config import settings
from src.services.exceptions import ConfigError, ExternalAPIError

logger = logging.getLogger(__name__)


# MCP 프로토콜 상수
_PROTOCOL_VERSION = "2025-03-26"
_CLIENT_INFO = {"name": "auto_stock", "version": "1.0"}
_DEFAULT_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "Content-Type": "application/json",
}


class MCPClient:
    """MCP Streamable HTTP/SSE 클라이언트 (async).

    프로토콜 흐름:
    1. ``POST {base_url}`` + ``method=initialize`` → 응답 헤더 ``mcp-session-id`` 추출
    2. ``POST {base_url}`` + ``method=tools/call`` (헤더 ``Mcp-Session-Id``) → SSE/JSON 응답
       - SSE: ``data: {jsonrpc...}`` 라인에서 ``result`` 추출
       - 또는 표준 ``application/json``
    3. 응답 코드 421 → 세션 만료 → ``initialize`` 재호출 + ``tools/call`` 재시도 (1회)
    """

    def __init__(self, base_url: str, enabled: bool, timeout: dict | None = None) -> None:
        self._base_url = base_url
        self._enabled = enabled
        # plan 명세 기본값: connect=5s, read=300s, write=10s, pool=10s
        t = timeout or {}
        self._timeout = httpx.Timeout(
            connect=t.get("connect", 5.0),
            read=t.get("read", 300.0),
            write=t.get("write", 10.0),
            pool=t.get("pool", 10.0),
        )
        # 세션 ID 와 요청 ID — 세션 재사용으로 initialize 비용 절감
        self._session_id: str | None = None
        self._req_id: int = 0
        self._lock = asyncio.Lock()
        self._http: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # 내부 헬퍼
    # ------------------------------------------------------------------
    def _check_enabled(self) -> None:
        if not self._enabled:
            raise ConfigError(
                "KIS MCP 서버가 비활성화되어 있습니다. KIS_MCP_ENABLED=true 로 설정하세요."
            )

    def _get_client(self) -> httpx.AsyncClient:
        """lazy 초기화 — 매번 동일 인스턴스 + 커넥션 풀 재사용."""
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=self._timeout)
        return self._http

    def _next_req_id(self) -> int:
        self._req_id += 1
        return self._req_id

    async def initialize(self) -> str:
        """MCP 세션 초기화. 응답 헤더 ``mcp-session-id`` 를 저장하고 반환한다.

        호출자는 보통 직접 호출할 필요 없음 — ``call_tool`` 이 lazy 호출.
        명시 호출은 헬스체크/디버그 용.
        """
        self._check_enabled()
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_req_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": _PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": _CLIENT_INFO,
            },
        }
        client = self._get_client()
        try:
            resp = await client.post(
                self._base_url, json=payload, headers=_DEFAULT_HEADERS
            )
        except httpx.TimeoutException as e:
            raise ExternalAPIError(f"MCP 서버 응답 시간 초과 (initialize): {e}") from e
        except httpx.ConnectError as e:
            raise ExternalAPIError(f"MCP 서버에 연결할 수 없습니다 (initialize): {e}") from e
        except httpx.HTTPError as e:
            raise ExternalAPIError(f"MCP 서버 통신 오류 (initialize): {e}") from e

        if resp.status_code >= 400:
            raise ExternalAPIError(
                f"MCP initialize 실패: HTTP {resp.status_code}"
            )

        session_id = resp.headers.get("mcp-session-id", "") or ""
        self._session_id = session_id or None
        if session_id:
            logger.info("[mcp] 세션 초기화 완료: %s", session_id[:8])
        else:
            # Phase 6 결함 C: stock-manager 외부 서버는 stateless 모드 — session-id 미반환이 정상.
            # WARNING 노이즈 다운그레이드. tools/call 은 헤더 미부착으로 진행.
            logger.debug("[mcp] initialize 응답에 mcp-session-id 헤더 없음 (stateless 모드)")
        return session_id

    def _parse_response(self, resp: httpx.Response) -> dict:
        """SSE 또는 표준 JSON 응답에서 JSON-RPC ``result`` 추출."""
        text = resp.text
        # SSE: ``data: {...}\n\n``
        if "data: " in text:
            for line in text.split("\n"):
                line = line.strip()
                if not line.startswith("data: "):
                    continue
                try:
                    body = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                if "error" in body:
                    err = body["error"]
                    msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                    raise ExternalAPIError(msg)
                return body.get("result", {}) or {}
            # SSE 였지만 data 라인을 파싱하지 못한 경우 — JSON fallback 으로 넘어감
        # 표준 JSON
        try:
            body = json.loads(text)
        except json.JSONDecodeError as e:
            raise ExternalAPIError(f"MCP 응답 파싱 실패: {text[:200]}") from e
        if "error" in body:
            err = body["error"]
            msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
            raise ExternalAPIError(msg)
        return body.get("result", {}) or {}

    def _extract_mcp_content(self, result: Any) -> Any:
        """MCP Streamable HTTP 2겹 래핑 unwrap (Phase 6 결함 A).

        외부 서버 (stock-manager 패턴) 는 ``tools/call`` 결과를 항상 다음 구조로 감싼다::

            {"content": [{"type": "text", "text": "<JSON 문자열>"}]}

        본 헬퍼는:
        1. ``content`` 키 없으면 → 입력 그대로 반환 (회귀 보존, Phase 1 케이스).
        2. ``content[0].type != "text"`` 또는 ``text`` 누락 → 원본 그대로 반환.
        3. ``content[0].text`` JSON 파싱 실패 → 원본 그대로 + warning 로그.
        4. 파싱 OK + ``success: false`` → ``ExternalAPIError(error_msg)`` raise.
        5. 파싱 OK + ``success: true`` + ``data`` 존재 → ``data`` 평탄화 반환.
        6. 파싱 OK + ``data`` 없음 → parsed 전체 반환 (graceful).

        여러 ``content`` 항목이 있으면 첫 번째 text 만 사용 (외부 서버 컨벤션).
        """
        if not isinstance(result, dict):
            return result
        content = result.get("content")
        if not isinstance(content, list) or not content:
            return result
        first = content[0]
        if not isinstance(first, dict) or first.get("type") != "text":
            return result
        text = first.get("text")
        if not isinstance(text, str):
            return result
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            logger.warning(
                "[mcp] content.text JSON 파싱 실패 — 원본 result 반환: %s",
                text[:200],
            )
            return result
        if isinstance(parsed, dict):
            success = parsed.get("success")
            if success is False:
                err = parsed.get("error") or parsed.get("message") or "MCP tool error"
                raise ExternalAPIError(str(err))
            if success is True and "data" in parsed:
                return parsed["data"]
            return parsed
        return parsed

    async def _post_tool_call(self, name: str, params: dict) -> httpx.Response:
        """tools/call 1회 POST. 421 처리는 호출자 책임."""
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_req_id(),
            "method": "tools/call",
            "params": {"name": name, "arguments": params},
        }
        headers = dict(_DEFAULT_HEADERS)
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        client = self._get_client()
        return await client.post(self._base_url, json=payload, headers=headers)

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------
    async def call_tool(self, name: str, params: dict | None = None) -> dict:
        """MCP ``tools/call`` 호출.

        Args:
            name: 도구 이름 (예: ``run_backtest_tool``)
            params: 도구 인자 dict

        Returns:
            ``result`` 키 안의 dict (도구별 스키마 — Phase 2 에서 더 구체화)

        Raises:
            ConfigError: ``KIS_MCP_ENABLED=false``
            ExternalAPIError: 네트워크/타임아웃/HTTP 5xx/421-재시도-실패/JSON-RPC error
        """
        self._check_enabled()
        params = params or {}
        # 세션 초기화 + 1회 호출 — 동시 호출 시 initialize 중복 방지를 위해 lock
        async with self._lock:
            if not self._session_id:
                await self.initialize()

        try:
            resp = await self._post_tool_call(name, params)
            # 421 → 세션 만료 → 1회 재초기화 + 재시도
            if resp.status_code == 421:
                logger.info("[mcp] 421 세션 만료 — 재초기화 후 재시도: tool=%s", name)
                self._session_id = None
                async with self._lock:
                    await self.initialize()
                resp = await self._post_tool_call(name, params)
                if resp.status_code == 421:
                    raise ExternalAPIError(
                        f"MCP 세션 재초기화 후에도 만료(421): tool={name}"
                    )
            if resp.status_code >= 400:
                raise ExternalAPIError(
                    f"MCP tools/call HTTP {resp.status_code}: tool={name}"
                )
            result = self._parse_response(resp)
            # Phase 6 결함 A: MCP Streamable HTTP 2겹 래핑 자동 unwrap.
            # 외부 서버 응답이 ``{"content":[{"type":"text","text":"<JSON>"}]}`` 인 경우
            # 안쪽 JSON 의 ``data`` 를 평탄화. 일반 응답은 그대로 반환 (회귀 보존).
            return self._extract_mcp_content(result)
        except ExternalAPIError:
            raise
        except httpx.TimeoutException as e:
            raise ExternalAPIError(f"MCP 서버 응답 시간 초과: tool={name} ({e})") from e
        except httpx.ConnectError as e:
            raise ExternalAPIError(
                f"MCP 서버에 연결할 수 없습니다: tool={name} ({e})"
            ) from e
        except httpx.HTTPError as e:
            raise ExternalAPIError(f"MCP 통신 오류: tool={name} ({e})") from e

    async def list_tools(self) -> list:
        """MCP ``tools/list`` 호출 — 사용 가능 도구 목록 반환.

        응답 스키마는 서버 구현 따라 ``{tools: [...]}`` 또는 ``[{...}]`` 가능.
        본 메서드는 호출자가 도구명 추출만 쉽게 하도록 list 형태로 정규화한다.
        """
        self._check_enabled()
        async with self._lock:
            if not self._session_id:
                await self.initialize()
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_req_id(),
            "method": "tools/list",
            "params": {},
        }
        headers = dict(_DEFAULT_HEADERS)
        if self._session_id:
            headers["Mcp-Session-Id"] = self._session_id
        client = self._get_client()
        try:
            resp = await client.post(self._base_url, json=payload, headers=headers)
        except httpx.TimeoutException as e:
            raise ExternalAPIError(f"MCP tools/list 시간 초과: {e}") from e
        except httpx.ConnectError as e:
            raise ExternalAPIError(f"MCP tools/list 연결 실패: {e}") from e
        except httpx.HTTPError as e:
            raise ExternalAPIError(f"MCP tools/list 통신 오류: {e}") from e

        if resp.status_code >= 400:
            raise ExternalAPIError(f"MCP tools/list HTTP {resp.status_code}")
        result = self._parse_response(resp)
        # 스키마 정규화 — result["tools"] 가 표준
        if isinstance(result, dict) and "tools" in result:
            tools = result["tools"]
            if isinstance(tools, list):
                return tools
        if isinstance(result, list):
            return result
        return []

    async def health_check(self) -> bool:
        """헬스체크 — 비활성 시 항상 False. 활성 시 ``tools/list`` 호출 성공 여부.

        외부 서버 다운/네트워크 단절 시에도 예외 대신 ``False`` 반환 (graceful).
        """
        if not self._enabled:
            return False
        try:
            tools = await self.list_tools()
            return isinstance(tools, list)
        except (ConfigError, ExternalAPIError) as e:
            logger.warning("[mcp] health_check 실패: %s", e)
            return False
        except Exception as e:  # pragma: no cover — 예상 외 예외도 graceful
            logger.exception("[mcp] health_check 예외: %s", e)
            return False

    async def close(self) -> None:
        """httpx.AsyncClient 정리."""
        if self._http is not None:
            try:
                await self._http.aclose()
            except Exception:  # pragma: no cover
                pass
            self._http = None
        self._session_id = None


# ── 싱글톤 ──────────────────────────────────────────────────────────────────
_client_instance: MCPClient | None = None


def get_mcp_client() -> MCPClient:
    """모듈 레벨 ``MCPClient`` 싱글톤.

    최초 호출 시 ``settings.kis_mcp_url`` / ``settings.kis_mcp_enabled`` /
    ``settings.backtest_timeout_secs`` 로 인스턴스를 생성한다.

    테스트에서는 ``src.services.mcp_client._client_instance = None`` 으로 리셋 가능.
    """
    global _client_instance
    if _client_instance is None:
        _client_instance = MCPClient(
            base_url=settings.kis_mcp_url,
            enabled=settings.kis_mcp_enabled,
            timeout={
                "connect": 5.0,
                "read": float(settings.backtest_timeout_secs),
                "write": 10.0,
                "pool": 10.0,
            },
        )
    return _client_instance
