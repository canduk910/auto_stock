"""외부 MCP 백테스트 서버 통합 엔진 (Phase 2).

흐름:
1. ``run_for_strategy(strategy_id, params, days, kind)``
   → YAML build → ``validate_yaml_tool`` → ``run_backtest_tool`` → job_id 반환
2. ``poll(job_id)`` → ``get_backtest_result_tool(wait=False)`` 1회
   - status=running 시 None
   - status=completed 시 ``BacktestMetrics`` 정규화 반환
   - status=failed 시 ``ExternalAPIError`` raise

핵심 안전 원칙:
- 운영 매매 흐름(scheduler/order_engine/risk) 영역 침범 0.
- 외부 서버 다운/timeout/연결실패 → ``ExternalAPIError`` propagate.
  호출자(recommendation_engine, Phase 3) 가 잡아서 backtest_summary=null 로 degrade.
- ``KIS_MCP_ENABLED=false`` → ``ConfigError`` (즉시 거부).
- (b) 폴백 전략은 ``BacktestNotSupportedError`` propagate.

기본 universe (Phase 2 디폴트):
- 다양성 확보 + 외부 서버 캐시 적중률 향상을 위해 코스피200 대표 5 종목:
  005930(삼성전자), 000660(SK하이닉스), 035420(NAVER), 005380(현대차), 051910(LG화학)
- Phase 3 자문 통합에서 실거래 30일 metrics 의 대표 종목으로 동적 교체 검토.

외부 서버 ``run_backtest_tool`` 인자:
- yaml_content: str
- symbols: list[str]
- start_date / end_date: "YYYY-MM-DD" (선택)
- initial_capital: 10_000_000 (디폴트)
- commission_rate / tax_rate / slippage
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, Optional

from src.engine.backtest_yaml import build_yaml
from src.models.backtest import BacktestMetrics
from src.services.exceptions import (
    BacktestNotSupportedError,
    ConfigError,
    ExternalAPIError,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 디폴트 universe (대표 5 종목)
# ---------------------------------------------------------------------------
DEFAULT_SYMBOLS: tuple[str, ...] = (
    "005930",  # 삼성전자
    "000660",  # SK하이닉스
    "035420",  # NAVER
    "005380",  # 현대차
    "051910",  # LG화학
)


class BacktestEngine:
    """외부 MCP 백테스트 서버 통합 엔진.

    ``client`` 는 ``src.services.mcp_client.MCPClient`` 인스턴스 (테스트는 mock).
    ``enabled`` 는 ``settings.kis_mcp_enabled`` 로 주입 (싱글톤이 아닌 인자 — 테스트 친화).
    """

    def __init__(
        self,
        client: Any,
        enabled: bool,
        *,
        default_symbols: Optional[list[str]] = None,
        initial_capital: float = 10_000_000.0,
    ) -> None:
        self._client = client
        self._enabled = enabled
        self._default_symbols: list[str] = (
            list(default_symbols) if default_symbols else list(DEFAULT_SYMBOLS)
        )
        self._initial_capital = initial_capital

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------
    async def run_for_strategy(
        self,
        strategy_id: str,
        params: dict[str, Any],
        days: int = 90,
        kind: str = "current",
        *,
        symbols: Optional[list[str]] = None,
        end_date: Optional[date] = None,
    ) -> str:
        """전략별 백테스트 제출 → job_id 반환.

        Raises:
            ConfigError: KIS_MCP_ENABLED=false (graceful degrade — 자문 흐름은 backtest_summary=null).
            BacktestNotSupportedError: 외부 YAML 표현 불가 전략 (Phase 4-bis 로컬 어댑터 위임).
            ExternalAPIError: MCP 통신 오류 / validate_yaml 실패 / job_id 누락.
        """
        if not self._enabled:
            raise ConfigError(
                "KIS_MCP_ENABLED=false — 외부 백테스트 서버가 비활성. "
                "운영 자문은 backtest_summary=null 로 graceful degrade."
            )

        # 1) YAML 빌드 — 미지원 전략이면 여기서 raise 됨
        yaml_str = build_yaml(strategy_id, params or {})

        # 2) validate_yaml_tool 호출
        validate_resp = await self._client.call_tool(
            "validate_yaml_tool", {"yaml_content": yaml_str}
        )
        valid = _extract_validate_ok(validate_resp)
        if not valid:
            errors = _extract_validate_errors(validate_resp)
            logger.error(
                "[backtest] validate_yaml_tool 실패: strategy=%s errors=%s",
                strategy_id, errors,
            )
            raise ExternalAPIError(
                f"validate_yaml_tool 거부 — strategy={strategy_id}, errors={errors}"
            )

        # 3) run_backtest_tool 호출
        target_symbols = list(symbols) if symbols else self._default_symbols
        end = end_date or date.today()
        start = end - timedelta(days=days)

        run_resp = await self._client.call_tool(
            "run_backtest_tool",
            {
                "yaml_content": yaml_str,
                "symbols": target_symbols,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
                "initial_capital": self._initial_capital,
            },
        )
        job_id = _extract_job_id(run_resp)
        if not job_id:
            logger.error(
                "[backtest] run_backtest_tool job_id 누락: strategy=%s resp=%s",
                strategy_id, _short(run_resp),
            )
            raise ExternalAPIError(
                f"run_backtest_tool 응답에 job_id 없음: strategy={strategy_id}"
            )
        logger.info(
            "[backtest] submit: strategy=%s kind=%s days=%d job_id=%s",
            strategy_id, kind, days, job_id,
        )
        return job_id

    async def poll(self, job_id: str) -> Optional[BacktestMetrics]:
        """``get_backtest_result_tool(wait=False)`` 1회 호출.

        Returns:
            running → None
            completed → BacktestMetrics
        Raises:
            ConfigError: enabled=False
            ExternalAPIError: failed status / 통신 오류
        """
        if not self._enabled:
            raise ConfigError("KIS_MCP_ENABLED=false")

        resp = await self._client.call_tool(
            "get_backtest_result_tool", {"job_id": job_id, "wait": False}
        )
        status = _extract_status(resp)
        if status == "running":
            return None
        if status == "completed":
            metrics_dict = _extract_metrics(resp)
            return BacktestMetrics.model_validate(metrics_dict)
        # failed / unknown
        err = _extract_error_message(resp) or f"unknown status: {status!r}"
        logger.error("[backtest] poll failed: job_id=%s err=%s", job_id, err)
        raise ExternalAPIError(f"백테스트 실패 — job_id={job_id}: {err}")

    async def wait_for_result(
        self, job_id: str, *, timeout: float = 300.0
    ) -> BacktestMetrics:
        """완료까지 외부 서버 내부 대기 (``wait=True``). Phase 3 자문 통합 사용.

        외부 서버가 timeout 까지 폴링을 서버측에서 수행 후 결과 반환.
        """
        if not self._enabled:
            raise ConfigError("KIS_MCP_ENABLED=false")

        resp = await self._client.call_tool(
            "get_backtest_result_tool",
            {"job_id": job_id, "wait": True, "timeout": timeout},
        )
        status = _extract_status(resp)
        if status == "completed":
            metrics_dict = _extract_metrics(resp)
            return BacktestMetrics.model_validate(metrics_dict)
        err = _extract_error_message(resp) or f"unknown status: {status!r}"
        raise ExternalAPIError(f"백테스트 실패 — job_id={job_id}: {err}")

    @property
    def enabled(self) -> bool:
        return self._enabled


# ---------------------------------------------------------------------------
# 내부 헬퍼 — 외부 MCP 응답 파싱 (success/data 또는 직접 dict)
# ---------------------------------------------------------------------------
def _unwrap(resp: Any) -> dict:
    """외부 MCP 응답을 dict 로 정규화.

    실측: ``{"success": True, "data": {...}}`` 또는 ``{...}`` (data 가 바로 평탄화).
    """
    if isinstance(resp, dict):
        if "data" in resp and isinstance(resp["data"], dict):
            return resp["data"]
        return resp
    return {}


def _extract_validate_ok(resp: Any) -> bool:
    data = _unwrap(resp)
    # 외부 서버는 valid 또는 ok 필드 사용 가능 — 둘 다 처리
    if "valid" in data:
        return bool(data["valid"])
    if "ok" in data:
        return bool(data["ok"])
    # 응답이 explicit valid 키 없으면 보수적으로 False
    return False


def _extract_validate_errors(resp: Any) -> list:
    data = _unwrap(resp)
    errs = data.get("errors") or data.get("error") or []
    if isinstance(errs, str):
        return [errs]
    if isinstance(errs, list):
        return errs
    return []


def _extract_job_id(resp: Any) -> Optional[str]:
    data = _unwrap(resp)
    jid = data.get("job_id") or data.get("backtest_id") or data.get("id")
    return str(jid) if jid else None


def _extract_status(resp: Any) -> str:
    data = _unwrap(resp)
    return str(data.get("status", "unknown"))


def _extract_metrics(resp: Any) -> dict:
    data = _unwrap(resp)
    return data.get("metrics") or {}


def _extract_error_message(resp: Any) -> Optional[str]:
    data = _unwrap(resp)
    err = data.get("error") or data.get("error_message")
    return str(err) if err else None


def _short(obj: Any, limit: int = 300) -> str:
    s = repr(obj)
    return s if len(s) <= limit else s[:limit] + "..."


# ---------------------------------------------------------------------------
# 싱글톤 — Phase 3 자문 엔진에서 import 편의용
# ---------------------------------------------------------------------------
_engine_instance: Optional[BacktestEngine] = None


def get_backtest_engine() -> BacktestEngine:
    """모듈 레벨 싱글톤. 테스트는 ``_engine_instance = None`` 으로 리셋."""
    global _engine_instance
    if _engine_instance is None:
        from src.config import settings
        from src.services.mcp_client import get_mcp_client

        _engine_instance = BacktestEngine(
            client=get_mcp_client(),
            enabled=bool(settings.kis_mcp_enabled),
        )
    return _engine_instance


__all__ = [
    "BacktestEngine",
    "BacktestMetrics",
    "BacktestNotSupportedError",
    "DEFAULT_SYMBOLS",
    "get_backtest_engine",
]
