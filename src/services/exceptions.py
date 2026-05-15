"""services 계층 공용 예외.

- ConfigError: 설정 문제 (MCP 비활성 등). 운영 흐름은 graceful degrade.
- ExternalAPIError: 외부 서비스 통신 오류 (네트워크/타임아웃/HTTP/JSON-RPC error).
"""
from __future__ import annotations


class ConfigError(Exception):
    """설정으로 인해 기능을 제공할 수 없는 상태.

    예: ``KIS_MCP_ENABLED=false`` 인데 ``call_tool()`` 이 호출되는 경우.
    호출부는 ``health_check()`` 로 사전 점검하거나 본 예외를 명시 처리해야 한다.
    """


class ExternalAPIError(Exception):
    """외부 API 통신 오류.

    네트워크 단절·타임아웃·5xx·JSON-RPC error 등을 단일 예외로 묶는다.
    운영 흐름에서는 본 예외 발생 시 graceful degrade (자동매매 핵심에 영향 0).
    """


class BacktestNotSupportedError(Exception):
    """해당 전략은 외부 MCP YAML DSL 로 표현 불가능한 경우 (Phase 2).

    YAML DSL 한계:
    - 상한가 모드 전환 (long_tail_volatility)
    - 폴/플래그 패턴 자동 검출 (bull_flag_breakout)
    - 베이스 수축·swing high/low 검출 (vcp_breakout)
    - 보드별 K값·시간 청산 (volatility_breakout 일부 — 근사 처리)

    호출자(recommendation_engine) 가 본 에러를 잡아 ``backtest_runs.status=skipped``
    또는 로컬 어댑터 분기로 라우팅한다 (Phase 4-bis 에서 구체화).
    """
