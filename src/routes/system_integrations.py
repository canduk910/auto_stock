"""사이클 5 (2026-05-17): 외부 통합 토글 라우트 (`/api/integrations/*`).

3 토글:
- `dkstock-regime` — 매크로 레짐(우리 `macro` 컨테이너) 활성 여부.
  🔴 슬러그·DB 키 이름은 유지한다 — 운영 DB 행·프론트·E2E 가 이 이름을 공유한다.
- `kis-mcp` — 외부 백테스트 서버 활성 여부.
- `auto-regime-adjust` — 매크로 레짐 기반 cash_usage_ratio 자동 갱신 (사이클 2 이미 존재 키, 통합 위치 이동).

공통 동작:
- GET: 현재 enabled + source(db/env) + env_value + db_value 응답.
- PUT: DB 갱신 + 응답 갱신값.
- dkstock-regime 활성화(True) 시 백그라운드 fetch trigger 발화 (매크로 즉시 반영).
- kis-mcp 활성화는 즉시 fetch 안 함 (백테스트는 자문 시점 발화).

하위 호환성:
- DB 미설정 시 settings.* 환경변수로 fallback — Phase 1 / 사이클 2 운영자 영향 0.
- 즉시 fetch 실패는 graceful — toggle 자체는 성공 유지.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Optional

from fastapi import APIRouter, HTTPException

from src.config import settings
from src.db import system_config as sc
from src.models.response import ApiResponse
from src.models.system_integrations import (
    AutoApplyRequest,
    AutoApplyStatus,
    BuyBlockStatusResponse,
    BuyBlockThresholdsModel,
    BuyBlockUpdateRequest,
    IntegrationToggleRequest,
    IntegrationToggleStatus,
    StatusExitModeRequest,
)
from src.models.krx_open_api import (
    KrxOpenApiStatus,
    KrxOpenApiUpdateRequest,
    mask_secret as krx_mask_secret,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/integrations", tags=["integrations"])


# ---------------------------------------------------------------------------
# 백그라운드 fetch trigger (dkstock-regime 활성화 직후)
# ---------------------------------------------------------------------------
async def _refresh_market_regime_and_persist_safely() -> None:
    """macro 컨테이너 매크로 fetch + 메모리 + DB snapshot. 모든 예외 graceful 흡수.

    PUT /api/integrations/dkstock-regime enabled=true 직후 백그라운드 task 발화.
    toggle 자체는 성공 응답 후 즉시 반환 — fetch 결과는 GET /api/market-regime/current
    폴링으로 확인. fetch 실패해도 DB 갱신은 성공 마킹 (운영자 가시성 위해 로그만).
    """
    try:
        from datetime import datetime, timezone, timedelta

        from src.engine import market_regime as mr_mod

        # 🔴 캐시를 먼저 비운다. 클라이언트가 24시간 메모리 캐시를 들고 있어서,
        #    운영자가 토글을 껐다 켜도 그대로 두면 하루 묵은 값이 다시 저장되고 화면에 실린다.
        #    "지금 다시 받아 봐" 가 이 경로의 존재 이유라 캐시 hit 은 그 계약을 깬다.
        try:
            from src.services.macro_client import get_macro_client

            get_macro_client().clear_cache()
        except Exception:  # 캐시 비우기 실패가 fetch 를 막지는 않는다
            logger.debug("[market_regime] macro 캐시 비우기 실패 — fetch 는 계속", exc_info=True)

        regime = await mr_mod.refresh_from_dkstock()
        mr_mod.set_current_regime(regime)
        if not regime.is_empty():
            KST = timezone(timedelta(hours=9))
            today = datetime.now(tz=KST).date()
            await mr_mod.persist_snapshot(regime, today)
            logger.info(
                "[integrations] dkstock fetch 성공 — regime=%s vix=%s fg=%s buy_blocked=%s",
                regime.regime, regime.vix, regime.fear_greed_score, regime.buy_blocked,
            )
        else:
            logger.warning(
                "[integrations] dkstock fetch empty 응답 — 매수 가드 비활성 유지"
            )
    except Exception:
        logger.exception("[integrations] dkstock 백그라운드 fetch 실패 — DB 토글은 성공")


# ---------------------------------------------------------------------------
# 공통 헬퍼
# ---------------------------------------------------------------------------
async def _build_status(
    db_getter: Callable[[], Awaitable[Optional[bool]]],
    env_value: bool,
) -> IntegrationToggleStatus:
    """공통 GET 응답 빌더 — DB 우선 / .env fallback 결정."""
    try:
        db_value = await db_getter()
    except Exception:
        logger.exception("[integrations] DB getter 실패 — .env fallback")
        db_value = None

    if db_value is not None:
        return IntegrationToggleStatus(
            enabled=bool(db_value),
            source="db",
            env_value=bool(env_value),
            db_value=bool(db_value),
        )
    return IntegrationToggleStatus(
        enabled=bool(env_value),
        source="env",
        env_value=bool(env_value),
        db_value=None,
    )


# ---------------------------------------------------------------------------
# dkstock-regime
# ---------------------------------------------------------------------------
@router.get("/dkstock-regime", response_model=ApiResponse)
async def get_dkstock_regime():
    """매크로 레짐(우리 `macro` 컨테이너) 활성 여부 조회 — DB 우선 / .env fallback."""
    status = await _build_status(
        sc.get_dkstock_regime_enabled, settings.dkstock_regime_enabled,
    )
    return ApiResponse(success=True, data=status.model_dump())


@router.put("/dkstock-regime", response_model=ApiResponse)
async def set_dkstock_regime(req: IntegrationToggleRequest):
    """외부 매크로 서버 활성 토글 + 활성화 시 백그라운드 fetch trigger."""
    try:
        await sc.set_dkstock_regime_enabled(req.enabled)
    except Exception as e:
        logger.exception("[integrations] dkstock_regime DB 갱신 실패: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    # 활성화 시 백그라운드 fetch 발화 — 응답은 즉시 반환.
    if req.enabled:
        try:
            asyncio.create_task(_refresh_market_regime_and_persist_safely())
        except RuntimeError:
            # event loop 미보유 등 예상외 — toggle 자체는 성공 보존
            logger.warning("[integrations] fetch task 발화 실패 (event loop 부재)")
    else:
        # 비활성화 — 메모리 regime 초기화 (graceful, 매수 가드 즉시 해제)
        try:
            from src.engine import market_regime as mr_mod

            mr_mod.set_current_regime(mr_mod.MarketRegime.empty())
        except Exception:
            logger.exception("[integrations] dkstock 비활성화 후 메모리 reset 실패")

    status = await _build_status(
        sc.get_dkstock_regime_enabled, settings.dkstock_regime_enabled,
    )
    return ApiResponse(
        success=True,
        data=status.model_dump(),
        message=(
            "외부 매크로 서버를 활성화했습니다. 백그라운드 fetch 진행 중 — 잠시 후 GET /api/market-regime/current 로 확인하세요."
            if req.enabled
            else "외부 매크로 서버를 비활성화했습니다. 매수 가드 즉시 해제됩니다."
        ),
    )


# ---------------------------------------------------------------------------
# kis-mcp
# ---------------------------------------------------------------------------
@router.get("/kis-mcp", response_model=ApiResponse)
async def get_kis_mcp():
    status = await _build_status(
        sc.get_kis_mcp_enabled, settings.kis_mcp_enabled,
    )
    return ApiResponse(success=True, data=status.model_dump())


@router.put("/kis-mcp", response_model=ApiResponse)
async def set_kis_mcp(req: IntegrationToggleRequest):
    """외부 백테스트 서버 활성 토글.

    즉시 fetch 안 함 — 백테스트는 자문 시점(20:00) 발화. 운영 매매 흐름 무관.
    """
    try:
        await sc.set_kis_mcp_enabled(req.enabled)
    except Exception as e:
        logger.exception("[integrations] kis_mcp DB 갱신 실패: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    status = await _build_status(
        sc.get_kis_mcp_enabled, settings.kis_mcp_enabled,
    )
    return ApiResponse(
        success=True,
        data=status.model_dump(),
        message=(
            "외부 백테스트 서버를 활성화했습니다. 다음 20:00 자문부터 백테스트 검증이 반영됩니다."
            if req.enabled
            else "외부 백테스트 서버를 비활성화했습니다. 자문 흐름은 backtest_summary=null 로 graceful degrade."
        ),
    )


# ---------------------------------------------------------------------------
# auto-regime-adjust (사이클 2 기존 키 — 라우트만 통합 위치 이동)
# ---------------------------------------------------------------------------
async def _get_auto_regime_adjust_value() -> Optional[bool]:
    """`get_auto_regime_adjust` 는 항상 bool 반환(키 부재시 True). 본 라우트는 None
    분기가 무의미하지만 통합 API 응답 구조를 맞추기 위해 wrap.
    """
    try:
        v = await sc.get_auto_regime_adjust()
        return bool(v)
    except Exception:
        return None


@router.get("/auto-regime-adjust", response_model=ApiResponse)
async def get_auto_regime_adjust():
    """매크로 레짐 → cash_usage_ratio 자동 조정 토글 조회.

    기존 system_config 키 `auto_regime_adjust` 사용 (사이클 2). 본 라우트는 통합
    Settings UI 노출 일관성용. `env_value` 는 의미 없지만 응답 구조 동일성 위해 False
    고정.
    """
    status = await _build_status(
        _get_auto_regime_adjust_value, env_value=True,  # 기본 True (사이클 2)
    )
    return ApiResponse(success=True, data=status.model_dump())


@router.put("/auto-regime-adjust", response_model=ApiResponse)
async def set_auto_regime_adjust(req: IntegrationToggleRequest):
    try:
        await sc.set_auto_regime_adjust(req.enabled)
    except Exception as e:
        logger.exception("[integrations] auto_regime_adjust DB 갱신 실패: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    status = await _build_status(
        _get_auto_regime_adjust_value, env_value=True,
    )
    return ApiResponse(
        success=True,
        data=status.model_dump(),
        message=(
            "자동 조정 활성 — 다음 _boot 부터 매크로 레짐 cash_min 기반 cash_usage_ratio 자동 갱신."
            if req.enabled
            else "수동 모드 — 운영자 cash_usage_ratio 보존."
        ),
    )


# ---------------------------------------------------------------------------
# 사이클 E-1 / I — ETF 레짐 관찰 토글 (etf_regime_enabled, 관찰 전용)
# ---------------------------------------------------------------------------
@router.get("/etf-regime", response_model=ApiResponse)
async def get_etf_regime():
    """지수ETF 고지로 스테이지 레짐 관찰 활성 여부 조회 (관찰 전용).

    `etf_regime_enabled` DB 토글 (.env fallback 없음). ETF 신호는 boot 에서 항상
    계산·노출되며 본 토글은 관찰 opt-in 플래그. **매수 가드 미연계** (사이클 I 게이트 제거).
    """
    try:
        enabled = await sc.get_etf_regime_enabled()
    except Exception:
        logger.exception("[integrations] etf_regime get 실패 — False fallback")
        enabled = False
    status = IntegrationToggleStatus(
        enabled=bool(enabled), source="db", env_value=False, db_value=bool(enabled),
    )
    return ApiResponse(success=True, data=status.model_dump())


@router.put("/etf-regime", response_model=ApiResponse)
async def set_etf_regime(req: IntegrationToggleRequest):
    """ETF 레짐 관찰 토글 (관찰 전용 — 매수 미개입)."""
    try:
        await sc.set_etf_regime_enabled(req.enabled)
    except Exception as e:
        logger.exception("[integrations] etf_regime DB 갱신 실패: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
    status = IntegrationToggleStatus(
        enabled=bool(req.enabled), source="db", env_value=False, db_value=bool(req.enabled),
    )
    return ApiResponse(
        success=True,
        data=status.model_dump(),
        message=(
            "지수ETF 레짐 관찰을 활성화했습니다. 대시보드에서 코스피200/코스닥150 스테이지를 확인하세요."
            if req.enabled
            else "지수ETF 레짐 관찰을 비활성화했습니다."
        ),
    )


# ---------------------------------------------------------------------------
# 사이클 8 (2026-05-18) — 매수 가드 4 모드 + 4 임계값
# ---------------------------------------------------------------------------
async def _build_buy_block_status() -> BuyBlockStatusResponse:
    """현재 모드 + 임계 + 메모리 regime 평가 결과 → 응답 빌더.

    `get_current_regime().get_buy_block_state()` 가 진실의 원천 — DB 조회 1회 + 메모리 regime
    평가 1회로 구성. empty regime / fetch 실패 graceful.

    사이클 D (2026-07-31) — `data_available`/`guard_inert` 관찰성 필드 추가.
    `data_available = regime.has_regime_data`, `guard_inert = mode != "OFF" and
    not data_available` (가드 설정됐으나 매크로 데이터 미유입으로 무력). 기존
    mode/blocked/reasons/soft_multiplier 로직은 완전 무변경.

    사이클 E-1 (2026-07-31) — `etf_kospi_stage`/`etf_kosdaq_stage`/`etf_defensive`/
    `etf_enabled` 관찰 필드 4종 추가. 소스 = boot 부착 싱글톤
    `market_regime.get_current_etf_signal()` (요청마다 재계산 X) +
    `system_config.get_etf_regime_enabled()`. 신호 부재(None) 시 스테이지/방어도
    None — 배제 0(매수 가드 미연계).
    """
    from src.engine import market_regime as mr_mod

    mode = await sc.get_buy_block_mode()
    thresholds_db = await sc.get_buy_block_thresholds()
    regime = mr_mod.get_current_regime()
    try:
        state = await regime.get_buy_block_state()
    except Exception:
        logger.exception("[buy_block] state 조회 실패 — HARD/기본 fallback")
        state = mr_mod.BuyBlockState(
            mode=mode, blocked=False, soft_multiplier=1.0, reasons=[],
            data_available=regime.has_regime_data,
        )

    data_available = regime.has_regime_data
    guard_inert = state.mode != "OFF" and not data_available

    etf_sig = mr_mod.get_current_etf_signal()
    etf_enabled = await sc.get_etf_regime_enabled()

    return BuyBlockStatusResponse(
        mode=state.mode,  # type: ignore[arg-type]
        thresholds=BuyBlockThresholdsModel(
            vix_threshold=thresholds_db.vix_threshold,
            fg_high_threshold=thresholds_db.fg_high_threshold,
            fg_low_threshold=thresholds_db.fg_low_threshold,
            defensive_enabled=thresholds_db.defensive_enabled,
        ),
        blocked=state.blocked,
        reasons=list(state.reasons),
        soft_multiplier=state.soft_multiplier,
        data_available=data_available,
        guard_inert=guard_inert,
        etf_kospi_stage=etf_sig.kospi_stage if etf_sig is not None else None,
        etf_kosdaq_stage=etf_sig.kosdaq_stage if etf_sig is not None else None,
        etf_defensive=etf_sig.etf_defensive if etf_sig is not None else None,
        etf_enabled=etf_enabled,
    )


@router.get("/buy-block", response_model=ApiResponse)
async def get_buy_block():
    """매수 가드 현재 상태 조회 (사이클 8, 2026-05-18).

    응답:
    - mode: OFF/WARN/SOFT/HARD
    - thresholds: VIX/FG_high/FG_low/defensive_enabled
    - blocked: 현재 가드 발동 여부 (mode 무관, 임계 OR 평가)
    - reasons: 발동 사유 (UI 표시용 — defensive/vix/fg_high/fg_low)
    - soft_multiplier: SOFT 시 0.5, 그 외 1.0
    """
    status = await _build_buy_block_status()
    return ApiResponse(success=True, data=status.model_dump())


@router.put("/buy-block", response_model=ApiResponse)
async def set_buy_block(req: BuyBlockUpdateRequest):
    """매수 가드 모드/임계 부분 갱신 (사이클 8, 2026-05-18).

    body 의 None 필드는 기존 값 보존. Pydantic 이 mode literal + 임계 ge/le 검증을
    수행하므로 잘못된 값은 422 자동. 갱신 후 전체 상태를 응답.
    """
    try:
        if req.mode is not None:
            await sc.set_buy_block_mode(req.mode)
        if (
            req.vix_threshold is not None
            or req.fg_high_threshold is not None
            or req.fg_low_threshold is not None
            or req.defensive_enabled is not None
        ):
            await sc.set_buy_block_thresholds(
                vix_threshold=req.vix_threshold,
                fg_high_threshold=req.fg_high_threshold,
                fg_low_threshold=req.fg_low_threshold,
                defensive_enabled=req.defensive_enabled,
            )
    except ValueError as e:
        # set_buy_block_mode 가 4 모드 외 값을 거부할 수 있음 (이중 안전망)
        logger.warning("[buy_block] PUT 검증 실패: %s", e)
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.exception("[buy_block] DB 갱신 실패: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    # 사이클 11 (2026-05-18) — 메모리 regime 의 buy_block_state 캐시 즉시 무효화.
    # 운영자 토글 후 60s TTL 만료 기다리지 않고 다음 매수 신호부터 즉시 반영.
    try:
        from src.engine import market_regime as mr_mod

        current = mr_mod.get_current_regime()
        if current is not None:
            current.invalidate_buy_block_cache()
    except Exception:
        # 캐시 무효화 실패는 toggle 성공 자체를 깨뜨리지 않음 — 다음 TTL 만료에 자연 갱신
        logger.debug("[buy_block] cache invalidate 실패 (graceful)", exc_info=True)

    status = await _build_buy_block_status()
    return ApiResponse(
        success=True,
        data=status.model_dump(),
        message=(
            f"매수 가드 모드 '{status.mode}' 적용. 다음 매수 신호부터 즉시 반영됩니다."
        ),
    )


# ---------------------------------------------------------------------------
# 사이클 23 (2026-05-20) — AI 자문 자동 적용 토글
# ---------------------------------------------------------------------------
@router.get("/auto-apply", response_model=ApiResponse)
async def get_auto_apply():
    """AI 자문 자동 적용 토글 조회.

    기본 False — 안전 우선. 운영자 명시 활성화 후에만 자동 감액 + 보수적 파라미터 적용.
    """
    enabled = await sc.get_auto_apply_enabled()
    return ApiResponse(success=True, data=AutoApplyStatus(enabled=enabled).model_dump())


@router.put("/auto-apply", response_model=ApiResponse)
async def put_auto_apply(req: AutoApplyRequest):
    """AI 자문 자동 적용 토글 변경.

    ON: 20:00 AI 자문 직후 weight 감액(50% cap) + 보수적 파라미터 자동 적용.
    OFF: 기존 수동 흐름 (apply_weight=true 명시) 만 유지.
    """
    try:
        await sc.set_auto_apply_enabled(req.enabled)
    except Exception as e:
        logger.exception("[auto_apply] DB 갱신 실패: %s", e)
        raise HTTPException(status_code=500, detail="DB 저장 실패")
    return ApiResponse(
        success=True,
        data=AutoApplyStatus(enabled=req.enabled).model_dump(),
        message=(
            "AI 자문 자동 적용을 활성화했습니다. 매일 20:00 자문 직후 weight 감액(50% cap) + 보수적 파라미터가 자동 적용됩니다."
            if req.enabled
            else "AI 자문 자동 적용을 비활성화했습니다. 모든 자문은 운영자 수동 적용에서만 반영됩니다."
        ),
    )


# ---------------------------------------------------------------------------
# 사이클 112 (2026-06-12) — KRX 정식 OPEN API 키 관리 (인프라 사전 구성)
# ---------------------------------------------------------------------------
# openapi.krx.co.kr (KRX Data Marketplace) 키를 안전 저장/조회/토글.
# 평문 key 응답 절대 노출 금지 — `key_masked` (`****1234`) 단독.
# 본 사이클은 인프라만 — 실제 호출은 사이클 113+ 별도 사이클.
async def _build_krx_open_api_status() -> KrxOpenApiStatus:
    """KRX 키 설정 응답 빌더 — DB 평문 → 마스킹 변환.

    `src/db/system_config.py::get_krx_open_api_config` 가 평문 key 포함 dict 반환.
    본 함수가 응답 직전 `krx_mask_secret` 호출 → `key_masked` 단독 노출.
    """
    config = await sc.get_krx_open_api_config()
    return KrxOpenApiStatus(
        enabled=config.enabled,
        base_url=config.base_url,
        key_masked=krx_mask_secret(config.key),
    )


@router.get("/krx-open-api", response_model=ApiResponse)
async def get_krx_open_api():
    """KRX 정식 OPEN API 설정 조회 (사이클 112, 2026-06-12).

    응답:
    - enabled: 활성 여부
    - base_url: 호출 base URL (디폴트 `https://data-dbg.krx.co.kr/svc/apis`)
    - key_masked: API key 마스킹 (`****1234` 형식, **평문 절대 노출 안 함**)

    DB 미설정 시 디폴트 (enabled=False, key="" → `****` 마스킹).
    """
    status = await _build_krx_open_api_status()
    return ApiResponse(success=True, data=status.model_dump())


@router.put("/krx-open-api", response_model=ApiResponse)
async def set_krx_open_api(req: KrxOpenApiUpdateRequest):
    """KRX 정식 OPEN API 설정 부분 갱신 (사이클 112).

    body:
    - key?: 평문 API key (DB 평문 저장 + 응답 마스킹). None 이면 기존 보존.
    - base_url?: 호출 base URL. None 이면 기존 보존.
    - enabled?: 활성 토글. None 이면 기존 보존.

    빈 body 도 허용 — 현재 상태 응답.

    **보안**: 평문 key 는 응답/로그 절대 노출 안 함. 백엔드 → 응답 직전 마스킹.
    DB 갱신 실패 시 500. 사이클 5 패턴 답습.
    """
    try:
        await sc.set_krx_open_api_config(
            key=req.key,
            base_url=req.base_url,
            enabled=req.enabled,
        )
    except Exception as e:
        # 보안: 예외 메시지에 평문 key 노출 차단 — 일반 에러 메시지만
        logger.exception("[integrations] krx_open_api DB 갱신 실패")
        raise HTTPException(status_code=500, detail="KRX OPEN API 설정 저장 실패")

    status = await _build_krx_open_api_status()
    return ApiResponse(
        success=True,
        data=status.model_dump(),
        message=(
            "KRX 정식 OPEN API 설정을 저장했습니다."
            if (req.key or req.base_url is not None or req.enabled is not None)
            else "변경 사항이 없습니다."
        ),
    )


# ---------------------------------------------------------------------------
# cycle369 — 종목상태(관리 51·단기과열 59) 청산·당일 매수차단 킬스위치 2키
# ---------------------------------------------------------------------------
async def _status_exit_stored() -> dict:
    """DB 저장값 조회 — 축마다 독립 try(한쪽 실패가 다른 쪽 값을 가리지 않는다)."""
    from src.engine import status_exit_watch as sew

    async def _safe(getter):
        try:
            return await getter()
        except Exception:
            logger.debug("[status_exit_stored_read_failed]", exc_info=True)
            return None

    return {
        sew.SELL_MODE_KEY: await _safe(sc.get_status_exit_mode_raw),
        sew.BUY_MODE_KEY: await _safe(sc.get_status_buy_block_mode_raw),
    }


def _status_exit_shape(sew, *, extra: Optional[dict] = None) -> dict:
    """GET·PUT 공통 응답 뼈대 — `stored`/`today` 는 호출부가 채운다."""
    data = {
        "sell_mode": sew.current_modes()["sell"],
        "buy_block_mode": sew.current_modes()["buy"],
        "default": sew.DEFAULT_MODE,
        "valid_modes": list(sew.VALID_MODES),
        "config_keys": {"sell": sew.SELL_MODE_KEY, "buy": sew.BUY_MODE_KEY},
        "fire_window": {
            "start": sew.FIRE_WINDOW_START.isoformat(),
            "end": sew.FIRE_WINDOW_END.isoformat(),
        },
        "today": sew.snapshot(),
    }
    if extra:
        data.update(extra)
    return data


@router.get("/status-exit", response_model=ApiResponse)
async def get_status_exit():
    """관리종목(51)·단기과열(59) 보유 청산 + 당일 매수차단 킬스위치 현재 상태.

    `sell_mode`/`buy_block_mode` 는 엔진 메모리 현재값(즉시 반영 확인용),
    `stored` 는 DB 원값(축마다 독립 조회 — 한쪽 실패가 다른 쪽을 가리지 않고
    그 축만 null). `today` 는 오늘 관측 스냅샷(`blocks`/`armed`/`passes`).
    """
    from src.engine import status_exit_watch as sew

    stored = await _status_exit_stored()
    return ApiResponse(success=True, data=_status_exit_shape(sew, extra={"stored": stored}))


@router.put("/status-exit", response_model=ApiResponse)
async def set_status_exit(req: StatusExitModeRequest):
    """종목상태 킬스위치 부분 갱신 — 메모리를 먼저 고정 반영한 뒤 DB 에 쓴다.

    둘 다 없으면 422(아무것도 바꾸지 않는다). DB 저장 실패는 `persisted=false`
    로 알리고도 메모리 반영은 계속한다 — 사고 중에는 `off` 가 먼저다(cycle293).

    🔁 cycle369 — 각 축을 **먼저** `apply_mode(kind, mode, persisted=False)`
    로 고정 반영한다(메모리가 DB 쓰기를 기다리지 않는다 — `pg.execute` 는 acquire
    타임아웃이 없어 RDS 가 멈추면 30초 넘게 운영자의 off 가 메모리에 안 닿았다).
    그 다음 DB 쓰기를 하고, 성공한 축만 `apply_mode(kind, mode, persisted=True)`
    로 고정을 푼다. 실패한 축은 고정된 채 남는다(다음 성공 저장 또는 재시작까지).
    한 요청의 두 축은 **둘 다** 고정 반영을 끝낸 뒤에야 첫 DB 쓰기가 시작된다 —
    한 축의 쓰기가 걸려도 다른 축의 메모리 반영이 묶이지 않는다.
    """
    if req.sell_mode is None and req.buy_block_mode is None:
        raise HTTPException(status_code=422, detail="sell_mode 또는 buy_block_mode 중 하나는 필요합니다")

    from src.engine import status_exit_watch as sew

    if req.sell_mode is not None:
        sew.apply_mode("sell", req.sell_mode, persisted=False)
    if req.buy_block_mode is not None:
        sew.apply_mode("buy", req.buy_block_mode, persisted=False)

    persisted = True
    if req.sell_mode is not None:
        ok = True
        try:
            await sc.set_status_exit_mode(req.sell_mode)
        except Exception:
            logger.exception("[status_exit_mode] status_exit_mode DB 저장 실패")
            ok = False
            persisted = False
        # cycle369 — 저장 실패는 그 축을 leaf 에 고정한 채 둔다(위에서 이미
        # persisted=False 로 고정했다). 다음 refresh 가 DB 를 다시 읽어 60초(매수)·
        # 300초(청산) 안에 이 off 를 enforce 로 되돌리지 못하게 한다(그 축의
        # 다음 성공 저장 또는 재시작까지). 성공한 축만 고정을 푼다.
        if ok:
            sew.apply_mode("sell", req.sell_mode, persisted=True)
    if req.buy_block_mode is not None:
        ok = True
        try:
            await sc.set_status_buy_block_mode(req.buy_block_mode)
        except Exception:
            logger.exception("[status_exit_mode] status_buy_block_mode DB 저장 실패")
            ok = False
            persisted = False
        if ok:
            sew.apply_mode("buy", req.buy_block_mode, persisted=True)

    modes = sew.current_modes()
    logger.warning(
        "[status_exit_mode] sell_mode=%s buy_block_mode=%s persisted=%s",
        modes["sell"], modes["buy"], persisted,
    )
    stored = await _status_exit_stored()
    return ApiResponse(
        success=True,
        data=_status_exit_shape(sew, extra={"stored": stored, "persisted": persisted}),
        message=(
            "저장했습니다."
            if persisted
            else "DB 저장에 실패했습니다 — 메모리에는 즉시 반영했고, 그 축을 고정했습니다"
            "(다음 성공 저장 또는 재시작까지 유지 — refresh 가 되돌리지 않습니다)."
        ),
    )
