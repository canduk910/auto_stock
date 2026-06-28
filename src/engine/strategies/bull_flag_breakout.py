"""눌림목 돌파(Bull Flag Breakout) 전략.

강한 상승(폴, flag pole) 직후 짧은 횡보·완만 조정(플래그) → 플래그 상단 재돌파 시 매수.
모멘텀(+29% 폭발) 전략의 후속 정리 후 2차 상승 진입로.

진입:
- 폴: 직전 3~10영업일 누적 +15% 이상, 음봉 비율 ≤ 45% (사이클 48 — DEFAULT_PARAMS
  pole_min_return=15.0 / pole_max_red_ratio=0.45. 한국 ±30% 환경에서 +20%/음봉 30% 교집합 0 차단)
- 플래그: 폴 종료 후 3~10영업일, 조정 폭 ≤ 폴 폭의 38.2%, 거래량 < 폴 평균의 60%
- 매수: 플래그 상단 돌파 + 당일 거래량 ≥ 플래그 평균 × 2
- 시간대: 09:05~13:00 KRX 메인 (`tradable_boards=("main",)`)

청산:
- 하드 손절 -5% / 플래그 하단 이탈
- 측정된 이동 도달 → 절반 익절 (1차 구현은 전량 청산)
- 잔여 ATR(14)×2 트레일링
- 진입 후 5영업일 경과 시 잔량 시장가

매수 회전:
- 종목당 1회 (`_bought_today` set)
- 청산 후 3영업일 쿨다운 (`_cooldown_until` dict)

명세: `_workspace/00_leader_trading_rules.md` 6-E
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, time, timedelta, timezone

from src.engine.strategy_base import FunnelStage, Signal, StrategyBase, StrategyConfig

KST = timezone(timedelta(hours=9))
logger = logging.getLogger(__name__)


# 사이클 47 (2026-05-22, refactor-review 카드 #3) — Funnel 단계 정의 모듈 상수.
# `prepare()` 의 `_record_funnel_pipeline_step(FUNNEL_STAGES[i-1], ...)` 위임 헬퍼와 결합.
# step_conditions 는 runtime 평가 (f-string) — 호출 시점 별도 인자 전달.
FUNNEL_STAGES: tuple[FunnelStage, ...] = (
    FunnelStage(1, "유니버스 후보"),
    FunnelStage(2, "유니버스 필터 통과 (시총·거래대금)"),
    # 사이클 157 (2026-06-17) — 1단계 진입 차단 13건 step 신규 영구 영속 → 9단계.
    FunnelStage(3, "1단계 진입 차단 13건 통과 (거래정지/관리/단기과열/투자유의 등)"),
    FunnelStage(4, "일봉 fetch 성공"),
    FunnelStage(5, "폴(Pole) 자동 검출"),
    FunnelStage(6, "플래그(Flag) 자동 검출"),
    FunnelStage(7, "거래량 수축"),
    FunnelStage(8, "ATR(14) > 0"),
    FunnelStage(9, "최종 prepared"),
)


def _empty_scan_stats() -> dict:
    return {
        "universe_candidates": 0,
        "universe_filtered": 0,
        "candle_fetch_ok": 0,
        "pole_pass": 0,
        "flag_pass": 0,
        "volume_contraction_pass": 0,
        "atr_pass": 0,
        "final_prepared": 0,
        "min_trade_amount_failed": 0,  # 사이클 23 P1-2 — 거래대금 미달 카운터
        "last_run_at": None,
    }


def _parse_time_hhmm(s: str) -> time:
    """`"09:05"` → `time(9, 5)` (간단한 HH:MM 파서)."""
    if not s or ":" not in s:
        return time(0, 0)
    h, m = s.split(":")
    return time(int(h), int(m))


class BullFlagBreakoutStrategy(StrategyBase):
    """눌림목 돌파 (Bull Flag) — KRX 메인 한정."""

    DEFAULT_TRADABLE_BOARDS = ("main",)

    DEFAULT_PARAMS = {
        "tradable_boards": list(DEFAULT_TRADABLE_BOARDS),
        "exchange": "KRX",
        # 폴 (사이클 48, 2026-05-27 — Pole 검출 0건 결함 완화)
        "pole_lookback_min": 3,
        "pole_lookback_max": 10,
        "pole_min_return": 15.0,    # 사이클 48 — 20.0→15.0. 한국 ±30% 환경 + 음봉 45% 와 교집합 0 차단
        "pole_max_red_ratio": 0.45,  # 사이클 48 — 0.30→0.45. 강한 폴도 1~2일 음봉 정상
        # 플래그
        "flag_lookback_min": 3,
        "flag_lookback_max": 10,
        "flag_retracement_max": 0.382,
        "flag_volume_ratio": 0.60,
        # 매수
        "breakout_volume_mult": 2.0,
        "entry_start": "09:05",
        "entry_end": "13:00",
        "position_ratio": 0.25,
        "max_positions": 4,
        # 청산
        "stop_loss_rate": -5.0,
        "atr_period": 14,
        "atr_trail_mult": 2.0,
        "max_hold_days": 5,
        "reentry_cooldown_days": 3,
        # 유니버스
        "min_market_cap": 50_000_000_000,
        "min_trade_amount": 2_000_000_000,
        "max_scan_stocks": 100,
        # 일반
        "daily_loss_limit": -6.0,
        # 사이클 23 P2-1 — 돌파 유지시간 조건 (가짜 돌파 차단)
        "breakout_retention_minutes": 3,
    }

    def __init__(self, config: StrategyConfig):
        merged = {**self.DEFAULT_PARAMS, **config.params}
        config.params = merged
        super().__init__(config)
        self._candidates: dict[str, dict] = {}
        self._scanned_tickers: list[str] = []
        self._bought_today: set[str] = set()
        # ticker -> 직전 틱 가격 (돌파 순간 감지용)
        self._prev_price: dict[str, int] = {}
        # ticker -> 측정된 이동 도달 여부 (절반 익절 후 ATR 트레일링 분기)
        self._partial_exit: dict[str, bool] = {}
        # ticker -> 쿨다운 만료일(이날 이전엔 재진입 금지)
        self._cooldown_until: dict[str, date] = {}
        # 사이클 23 P2-1 — ticker -> 첫 돌파 감지 시각 (retention 대기용)
        self._breakout_first_seen: dict[str, datetime] = {}
        self._scan_stats: dict = _empty_scan_stats()

    # ------------------------------------------------------------------
    # prepare — 일봉 fetch → 폴/플래그 자동 검출
    # ------------------------------------------------------------------
    async def prepare(self) -> None:
        import asyncio

        # 사이클 173 (2026-06-22) — 일봉 source KIS → DB 어댑터 전환 (행위 보존).
        from src.db.stock_master_daily import get_recent_daily_normalized

        params = self.config.params
        pole_max = params["pole_lookback_max"]
        flag_max = params["flag_lookback_max"]
        atr_period = params["atr_period"]
        fetch_days = pole_max + flag_max + atr_period + 10  # 여유

        self._candidates = {}
        stats = _empty_scan_stats()
        self._scan_stats = stats
        # 사이클 39 (2026-05-22) — 단계별 ticker 캡처 reset
        self._reset_funnel_steps(FUNNEL_STAGES)

        # 사이클 163 (2026-06-18) — stock_master 0건 race 자동 재시도 hook (cap 3회 + sleep 30s).
        # 6/18 08:24:25 운영 사고 영구 차단 (사이클 158 VB 패턴 답습).
        tickers = await self._scan_universe()
        for retry_attempt in range(3):
            if tickers:
                break
            logger.warning(
                "[bfb_prepare_retry] stock_master 0건 — %d초 후 재시도 (cap=%d/3)",
                30, retry_attempt + 1,
            )
            await asyncio.sleep(30)
            self._candidates = {}
            stats = _empty_scan_stats()
            self._scan_stats = stats
            self._reset_funnel_steps(FUNNEL_STAGES)
            tickers = await self._scan_universe()
        # 사이클 39 — 1단계: 유니버스 후보 + 2단계: 유니버스 필터 (시총·거래대금 컷 통과)
        # `_scan_universe` 내부에서 ranked → filtered 분리. `_scan_stats` 가 이미 양쪽 카운트.
        # 단계별 ticker 정확 캡처는 `_scan_universe` 가 후보 리스트와 통과 리스트 둘 다 반환해야
        # 가능. 현재는 통과 리스트만 반환 → 1단계는 통과 카운트 (raw ranked 는 미보유).
        # 사이클 47 (2026-05-22, refactor-review 카드 #3) — FUNNEL_STAGES 위임
        # 사이클 170 카드 C — step_conditions 구버전 등락률 순위 문구 → 실제 소스 정합.
        # 사이클 108 부터 stock_master.list_by_filter 기반 (KIS 거래량순위 API 폐기).
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[0],
            survived=tickers,
            step_conditions="stock_master.list_by_filter 원천 유니버스 후보 + ETF/ETN 키워드 제외",
        )
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[1],
            survived=tickers,
            step_conditions=(
                f"시총 ≥ {params['min_market_cap']/100_000_000:.0f}억 "
                f"+ 거래대금 ≥ {params['min_trade_amount']/100_000_000:.0f}억"
            ),
        )

        # 사이클 157 — step 3: 1단계 진입 차단 13건 (master_raw 7 + raw 6)
        tickers, master_block_excluded = await self._apply_master_block_filter_in_prepare(tickers)
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[2],
            survived=tickers,
            step_conditions=(
                "1단계 진입 차단 13건 (거래정지/관리/단기과열/투자유의/공매도과열/이상급등 등)"
            ),
            excluded=master_block_excluded[:20],
        )

        if not tickers:
            logger.info("눌림목 돌파 유니버스 0종목")
            self._scanned_tickers = []
            stats["last_run_at"] = datetime.now(KST).isoformat()
            return

        today_str = datetime.now(KST).strftime("%Y%m%d")

        # 사이클 173 — DB 우선 어댑터 (락/신선도/부족 시 KIS 폴백). min_required=35 명시 (자문 §4).
        async def _fetch_one(ticker: str):
            try:
                return ticker, await get_recent_daily_normalized(
                    ticker, days=fetch_days, min_required=35,
                )
            except Exception as e:
                logger.warning("눌림목 일봉 fetch 실패: %s — %s", ticker, e)
                return ticker, None

        fetched = await asyncio.gather(*[_fetch_one(t) for t in tickers])

        # 사이클 39 — 단계별 ticker 캡처 (회귀 가드 — 결과 무변경)
        # 사이클 41 (2026-05-22) — 탈락 사유 (수치 포함) 캡처 추가
        candle_fetch_ok_tickers: list[str] = []
        pole_pass_tickers: list[str] = []
        # 사이클 50 (2026-06-01) — 플래그/거래량수축 단계별 생존 추적 (계측 정밀화)
        flag_pass_tickers: list[str] = []
        atr_pass_tickers: list[str] = []
        final_prepared_tickers: list[str] = []
        # 사이클 41 — 단계별 탈락 sample (수치 포함)
        candle_fetch_excluded: list[dict] = []
        pole_excluded: list[dict] = []
        atr_excluded: list[dict] = []
        # 사이클 50 — 폴 검출 4 sub-condition 을 funnel step 4/5/6 에 정밀 분배
        flag_excluded: list[dict] = []           # step 5 (플래그 조정폭)
        volume_contraction_excluded: list[dict] = []  # step 6 (거래량 수축)

        for ticker, candles in fetched:
            from src.engine.strategy_base import _resolve_ticker_name
            ticker_name = _resolve_ticker_name(ticker)
            if candles is None or not candles:
                # 사이클 41 — 일봉 fetch 실패 사유 캡처
                candle_fetch_excluded.append({
                    "ticker": ticker, "name": ticker_name,
                    "reason": "KIS 일봉 응답 빈/None",
                })
                continue
            try:
                # 부분봉 가드 — candles[0] 이 오늘이면 [1] 부터 사용
                prev_idx = 1 if candles[0].get("stck_bsop_date") == today_str else 0
                required_len = prev_idx + pole_max + flag_max + 2
                if len(candles) <= required_len:
                    candle_fetch_excluded.append({
                        "ticker": ticker, "name": ticker_name,
                        "reason": f"일봉 길이 {len(candles)} < 필요 {required_len+1}",
                    })
                    continue
                if prev_idx:
                    candles = candles[prev_idx:]
                stats["candle_fetch_ok"] += 1
                candle_fetch_ok_tickers.append(ticker)  # 사이클 39

                # 사이클 50 (2026-06-01) — 단계별 실패 사유 계측. 검출 결과(result) 무변경,
                # fail_stage/detail 로 funnel step 4/5/6 정밀 분배 (근본 원인 3 시정).
                result, fail_stage, detail = self._detect_pole_and_flag_detailed(candles)
                if not result:
                    if fail_stage == "flag_retracement":
                        # step 5 (플래그 조정폭) 바인딩 — 폴(상승률+음봉)은 통과
                        stats["pole_pass"] += 1
                        pole_pass_tickers.append(ticker)
                        flag_excluded.append({
                            "ticker": ticker, "name": ticker_name,
                            "reason": (
                                f"플래그 조정 폭 {detail.get('retracement', 0)*100:.1f}% > "
                                f"폴 폭 × {params['flag_retracement_max']*100:.1f}% "
                                f"(폴 +{detail.get('best_return', 0):.1f}%)"
                            ),
                        })
                    elif fail_stage == "volume_contraction":
                        # step 6 (거래량 수축) 바인딩 — 폴+플래그조정 모두 통과,
                        # 거래량만 미수축. 06/01 운영 가설 (거래량순위 = 폭발 ⊥ 수축).
                        stats["pole_pass"] += 1
                        stats["flag_pass"] += 1
                        pole_pass_tickers.append(ticker)
                        flag_pass_tickers.append(ticker)
                        volume_contraction_excluded.append({
                            "ticker": ticker, "name": ticker_name,
                            "reason": (
                                f"거래량 수축 미달 — 플래그/폴 평균 거래량 비율 "
                                f"{detail.get('vol_ratio', 0)*100:.0f}% ≥ "
                                f"임계 {params['flag_volume_ratio']*100:.0f}% "
                                f"(폴 +{detail.get('best_return', 0):.1f}%, "
                                f"수축 조건은 비율 < 임계 요구)"
                            ),
                        })
                    else:
                        # step 4 (폴 상승률/음봉비율) 바인딩 또는 no_candle
                        if fail_stage == "pole_red_ratio":
                            reason = (
                                f"폴 음봉 비율 {detail.get('red_ratio', 0)*100:.0f}% > "
                                f"임계 {params['pole_max_red_ratio']*100:.0f}% "
                                f"(폴 상승률 +{detail.get('best_return', 0):.1f}%)"
                            )
                        elif fail_stage == "pole_return":
                            reason = (
                                f"폴 상승률 +{detail.get('best_return', 0):.1f}% < "
                                f"임계 +{params['pole_min_return']:.0f}%"
                            )
                        else:
                            reason = detail.get("reason", "폴 검출 실패 (유효 조합 없음)")
                        pole_excluded.append({
                            "ticker": ticker, "name": ticker_name,
                            "reason": reason,
                        })
                    continue
                stats["pole_pass"] += 1
                stats["flag_pass"] += 1
                pole_pass_tickers.append(ticker)  # 사이클 39
                flag_pass_tickers.append(ticker)  # 사이클 50

                # 거래량 수축 확인은 _detect_pole_and_flag 내부에서 통과한 것
                stats["volume_contraction_pass"] += 1

                # ATR
                atr = self._atr(
                    [int(c.get("stck_hgpr", "0")) for c in candles],
                    [int(c.get("stck_lwpr", "0")) for c in candles],
                    [int(c.get("stck_clpr", "0")) for c in candles],
                    atr_period,
                )
                if atr <= 0:
                    atr_excluded.append({
                        "ticker": ticker, "name": ticker_name,
                        "reason": "ATR 계산 실패 (값 ≤ 0)",
                    })
                    continue
                stats["atr_pass"] += 1
                atr_pass_tickers.append(ticker)  # 사이클 39

                from src.engine.scanner import ticker_prev_close
                prev_close = int(candles[0].get("stck_clpr", "0"))
                if prev_close > 0:
                    ticker_prev_close[ticker] = prev_close

                self._candidates[ticker] = {
                    **result,
                    "atr14": int(atr),
                    "prev_close": prev_close,
                }
                stats["final_prepared"] += 1
                final_prepared_tickers.append(ticker)  # 사이클 39
            except Exception as e:
                logger.warning("눌림목 prepare 실패: %s — %s", ticker, e)
                continue

        # 사이클 47 + 157 — FUNNEL_STAGES 위임 (사이클 157 step 3 master block 후 인덱스 +1)
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[3],
            survived=candle_fetch_ok_tickers, excluded=candle_fetch_excluded,
            step_conditions=f"KIS 일봉 ≥ {pole_max + flag_max + 3}일",
        )
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[4],
            survived=pole_pass_tickers, excluded=pole_excluded,
            step_conditions=(
                f"3~10영업일 누적 +{params['pole_min_return']:.0f}%↑ + "
                f"음봉 비율 ≤ {params['pole_max_red_ratio']*100:.0f}%"
            ),
        )
        # 사이클 50 (2026-06-01) — step 5(플래그 조정폭)/6(거래량 수축) 정밀 분배.
        # 기존엔 둘 다 survived=pole_pass_tickers + excluded=None 이라 어느 조건이
        # 바인딩인지 계측 불가 (근본 원인 3). 이제 단계별 생존/탈락 분리.
        # step 6 거래량 수축 생존 = 검출 완전 통과 종목 (flag_pass 중 수축 탈락 제외).
        vol_excluded_set = {e["ticker"] for e in volume_contraction_excluded}
        volume_contraction_pass_tickers = [
            t for t in flag_pass_tickers if t not in vol_excluded_set
        ]
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[5],
            survived=flag_pass_tickers, excluded=flag_excluded,
            step_conditions=f"3~10영업일 조정 폭 ≤ 폴 폭 × {params['flag_retracement_max']*100:.1f}%",
        )
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[6],
            survived=volume_contraction_pass_tickers,
            excluded=volume_contraction_excluded,
            step_conditions=f"플래그 평균 거래량 < 폴 평균 × {params['flag_volume_ratio']*100:.0f}%",
        )
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[7],
            survived=atr_pass_tickers, excluded=atr_excluded,
            step_conditions="ATR(14) > 0 (변동성 측정 가능)",
        )
        self._record_funnel_pipeline_step(
            FUNNEL_STAGES[8],
            survived=final_prepared_tickers,
            step_conditions="모든 단계 통과 — 매수 후보 등록",
        )

        self._scanned_tickers = list(self._candidates.keys())
        self._bought_today.clear()
        stats["last_run_at"] = datetime.now(KST).isoformat()
        logger.info(
            "눌림목 돌파 준비 완료: %d/%d종목 — pole=%d flag=%d vol_cnt=%d atr=%d",
            stats["final_prepared"], len(tickers),
            stats["pole_pass"], stats["flag_pass"],
            stats["volume_contraction_pass"], stats["atr_pass"],
        )

    # 사이클 50 (2026-06-01) — 단계별 실패 사유 우선순위 (멀리 도달할수록 큰 값).
    # `_detect_pole_and_flag_detailed` 가 "가장 멀리 도달한" 조합의 바인딩 단계를
    # 보고하는 데 사용 (funnel step 4/5/6 사유 분배의 근거).
    _FAIL_STAGE_ORDER = {
        "": 99,                    # 통과 (어떤 fail 보다 우선)
        "no_candle": 0,            # 일봉 파싱/길이 실패
        "pole_return": 1,          # 폴 상승률 임계 미달
        "pole_red_ratio": 2,       # 음봉 비율 초과
        "flag_retracement": 3,     # 플래그 조정 폭 초과
        "volume_contraction": 4,   # 거래량 수축 미달
    }

    def _detect_pole_and_flag(self, candles: list[dict]) -> dict | None:
        """일봉(최신순) → 폴/플래그 자동 검출 (기존 계약 유지 — dict | None).

        사이클 50 (2026-06-01): 내부 구현을 `_detect_pole_and_flag_detailed` 로 위임하고
        result 만 반환하는 thin wrapper. 모든 기존 호출처/테스트 계약 무변경 (행위 보존).
        """
        result, _fail_stage, _detail = self._detect_pole_and_flag_detailed(candles)
        return result

    def _detect_pole_and_flag_detailed(
        self, candles: list[dict]
    ) -> tuple[dict | None, str, dict]:
        """폴/플래그 자동 검출 + 단계별 실패 사유 계측 (사이클 50, 2026-06-01).

        candles[0] 이 가장 최근 영업일. flag 종료 = candles[0:flag_len],
        그 이전 = pole 구간 (candles[flag_len:flag_len+pole_len]).
        다양한 (pole_len, flag_len) 조합을 시도해 처음 통과하는 셋업을 반환.

        근본 원인 3 (진단 인프라 결함) 시정 — 실패 시 `None` 만 반환하던 기존 동작을
        "가장 멀리 도달한 sub-condition" + 측정 수치 보고로 확장. 사이클 49 VCP
        `last_pullback_pct 항상 기록` 동일 계열. 검출 결과(result) 자체는 무변경.

        Returns:
            (result, fail_stage, detail)
            - result: 통과 시 dict (기존과 동일), 실패 시 None
            - fail_stage: 통과 시 "" / 실패 시 가장 멀리 도달한 조합의 바인딩 단계
              ("pole_return"/"pole_red_ratio"/"flag_retracement"/"volume_contraction"
               /"no_candle")
            - detail: 가장 멀리 도달한 조합의 측정 수치 dict
              (best_return / red_ratio / retracement / vol_ratio / pole_len / flag_len)
        """
        p = self.config.params
        pole_min, pole_max = p["pole_lookback_min"], p["pole_lookback_max"]
        flag_min, flag_max = p["flag_lookback_min"], p["flag_lookback_max"]
        min_return = p["pole_min_return"]
        max_red_ratio = p["pole_max_red_ratio"]
        retracement_max = p["flag_retracement_max"]
        flag_vol_ratio = p["flag_volume_ratio"]

        try:
            closes = [int(c.get("stck_clpr", "0")) for c in candles]
            highs = [int(c.get("stck_hgpr", "0")) for c in candles]
            lows = [int(c.get("stck_lwpr", "0")) for c in candles]
            opens = [int(c.get("stck_oprc", "0")) for c in candles]
            vols = [int(c.get("acml_vol", "0")) for c in candles]
        except (TypeError, ValueError):
            return None, "no_candle", {"reason": "일봉 파싱 실패"}

        # 가장 멀리 도달한 실패 조합 추적 (사이클 50 — 바인딩 단계 계측)
        best_fail_stage = "no_candle"
        best_fail_detail: dict = {"reason": "유효한 (pole_len, flag_len) 조합 없음"}
        best_fail_rank = -1

        def _note_fail(stage: str, detail: dict) -> None:
            nonlocal best_fail_stage, best_fail_detail, best_fail_rank
            rank = self._FAIL_STAGE_ORDER.get(stage, 0)
            if rank > best_fail_rank:
                best_fail_rank = rank
                best_fail_stage = stage
                best_fail_detail = detail

        # 다양한 (flag_len, pole_len) 조합 시도
        # 가장 짧은 셋업 우선 (최근 신호)
        for flag_len in range(flag_min, flag_max + 1):
            if flag_len > len(candles):
                break
            flag_slice_highs = highs[:flag_len]
            flag_slice_lows = lows[:flag_len]
            flag_slice_vols = vols[:flag_len]
            if not flag_slice_highs or not flag_slice_lows:
                continue
            flag_high = max(flag_slice_highs)
            flag_low = min(flag_slice_lows)
            flag_avg_volume = sum(flag_slice_vols) / flag_len if flag_len > 0 else 0
            if flag_avg_volume <= 0:
                continue

            for pole_len in range(pole_min, pole_max + 1):
                if flag_len + pole_len > len(candles):
                    break
                pole_slice_closes = closes[flag_len: flag_len + pole_len]
                pole_slice_highs = highs[flag_len: flag_len + pole_len]
                pole_slice_opens = opens[flag_len: flag_len + pole_len]
                pole_slice_vols = vols[flag_len: flag_len + pole_len]
                if not pole_slice_closes:
                    continue

                pole_start = pole_slice_closes[-1]  # 폴 구간 가장 옛날 종가
                pole_high = max(pole_slice_highs)
                if pole_start <= 0 or pole_high <= 0:
                    continue

                # (1) 폴 상승률
                pole_return_pct = (pole_high - pole_start) / pole_start * 100
                if pole_return_pct < min_return:
                    _note_fail("pole_return", {
                        "best_return": round(pole_return_pct, 1),
                        "min_return": min_return,
                        "pole_len": pole_len, "flag_len": flag_len,
                    })
                    continue

                # (2) 음봉 비율
                red_count = sum(
                    1
                    for o, c in zip(pole_slice_opens, pole_slice_closes)
                    if o > 0 and c < o
                )
                red_ratio = red_count / pole_len if pole_len > 0 else 1.0
                if red_ratio > max_red_ratio:
                    _note_fail("pole_red_ratio", {
                        "best_return": round(pole_return_pct, 1),
                        "red_ratio": round(red_ratio, 2),
                        "max_red_ratio": max_red_ratio,
                        "pole_len": pole_len, "flag_len": flag_len,
                    })
                    continue

                # (3) 플래그 조정 폭 ≤ 폴 폭의 retracement_max
                pole_width = pole_high - pole_start
                if pole_width <= 0:
                    continue
                actual_retracement = (pole_high - flag_low) / pole_width
                if actual_retracement > retracement_max:
                    _note_fail("flag_retracement", {
                        "best_return": round(pole_return_pct, 1),
                        "retracement": round(actual_retracement, 3),
                        "retracement_max": retracement_max,
                        "pole_len": pole_len, "flag_len": flag_len,
                    })
                    continue

                # (4) 거래량 수축
                pole_avg_volume = sum(pole_slice_vols) / pole_len if pole_len > 0 else 0
                if pole_avg_volume <= 0:
                    continue
                vol_ratio = flag_avg_volume / pole_avg_volume if pole_avg_volume > 0 else 99.0
                if flag_avg_volume >= pole_avg_volume * flag_vol_ratio:
                    _note_fail("volume_contraction", {
                        "best_return": round(pole_return_pct, 1),
                        "vol_ratio": round(vol_ratio, 2),
                        "flag_volume_ratio": flag_vol_ratio,
                        "pole_len": pole_len, "flag_len": flag_len,
                    })
                    continue

                # 통과
                return (
                    {
                        "pole_start": pole_start,
                        "pole_high": pole_high,
                        "flag_high": flag_high,
                        "flag_low": flag_low,
                        "flag_avg_volume": int(flag_avg_volume),
                        "pole_len": pole_len,
                        "flag_len": flag_len,
                    },
                    "",
                    {
                        "best_return": round(pole_return_pct, 1),
                        "red_ratio": round(red_ratio, 2),
                        "retracement": round(actual_retracement, 3),
                        "vol_ratio": round(vol_ratio, 2),
                        "pole_len": pole_len, "flag_len": flag_len,
                    },
                )

        return None, best_fail_stage, best_fail_detail

    @staticmethod
    def _atr(highs, lows, closes, period: int) -> float:
        """ATR(period). highs/lows/closes 최신순(idx=0 이 어제)."""
        if len(highs) <= period or len(lows) <= period or len(closes) <= period + 1:
            return 0.0
        trs = []
        for i in range(period):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i + 1]),
                abs(lows[i] - closes[i + 1]),
            )
            trs.append(tr)
        return sum(trs) / period

    async def _scan_universe(self) -> list[str]:
        """stock_master DB 기반으로 시총·거래대금 조건 종목을 스캔한다 (사이클 108).

        사이클 108 (Plan Phase A) — 사전 적재된 stock_master (~2,800종목,
        사이클 101/106 _full_universe_load_task_loop) 를 DB 필터링으로 대체한다.
        사이클 48 도입 이유였던 "acml_vol=0 시간 의존 결함" 은 stock_master DB 조회로
        근본 해소된다 (DB는 24h TTL 갱신 기반으로 시간 의존이 없음).
        KIS API 직접 호출 0건.
        hts_avls (시가총액, 백만원 단위) 는 사이클 108 inquire_stock_basics 5-key merge 에서
        stock_master.raw 에 적재됨.
        """
        from src.db import stock_master as _sm_mod
        from src.engine.scanner import ETF_KEYWORDS, ticker_names

        p = self.config.params
        min_mcap = p.get("min_market_cap", 100_000_000_000)
        min_trade = p.get("min_trade_amount", 20_000_000_000)
        max_stocks = p.get("max_scan_stocks", 100)

        # 사이클 156 Q0 — nxt_tradable 강제 필터 제거 (주문 시점 분기용으로만 활용).
        rows = await _sm_mod.list_by_filter(
            min_market_cap=min_mcap,
            min_trade_amount=min_trade,
            limit=max_stocks,
        )

        self._scan_stats["universe_candidates"] = len(rows)

        filtered: list[str] = []
        for row in rows:
            ticker = row.get("ticker", "")
            # 종목코드 형식 검증 — ETF·ETN·신주인수권 등 알파벳 포함 코드 차단
            if not ticker or not (len(ticker) == 6 and ticker.isdigit()):
                continue
            name = row.get("name", "") or (row.get("raw") or {}).get("prdt_abrv_name", "")
            if any(kw in name for kw in ETF_KEYWORDS):
                continue
            if name:
                ticker_names[ticker] = name
            filtered.append(ticker)

        self._scan_stats["universe_filtered"] = len(filtered)
        self._scan_stats["last_run_at"] = datetime.now(KST).isoformat()

        if not filtered:
            from src.db.system_logs import write_log

            msg = (
                f"눌림목 돌파 유니버스 0종목 — stock_master {len(rows)}건 중 "
                f"시총 {min_mcap // 100_000_000}억+ / 거래대금 "
                f"{min_trade // 100_000_000}억+ / ETF 제외 후 통과 없음"
            )
            logger.error(msg)
            try:
                await write_log("ERROR", msg)
            except Exception:
                logger.exception("system_logs 기록 실패")

        # 사이클 151 — PriceFilter 후처리 (사이클 148 VB 영역 답습, Q2=C 단일 source 영속)
        filtered = await self._apply_price_filter_in_prepare(filtered)

        return filtered

    async def _apply_master_block_filter_in_prepare(
        self, tickers: list[str]
    ) -> tuple[list[str], list[dict]]:
        """BFB prepare 영역 1단계 진입 차단 13건 hook (사이클 157 Q2).

        사이클 32 R4 보유/익일청산 절대 보호 + scanner.apply_master_block_filter 위임.

        Returns:
            (survived, excluded). excluded = [{ticker, name, reason}] (사이클 41 답습).
        """
        from src.engine import scanner as _scanner_mod

        protected: set[str] = set()
        try:
            protected = _scanner_mod._collect_protected_tickers_for_scanner()
        except Exception:
            logger.debug(
                "[bfb_master_block_prepare] protected_tickers 조회 실패 graceful",
                exc_info=True,
            )
        return await _scanner_mod.apply_master_block_filter(
            tickers, protected_tickers=protected
        )

    async def _apply_price_filter_in_prepare(self, tickers: list[str]) -> list[str]:
        """BFB prepare 영역 가격 필터 후처리 (사이클 151, 사이클 148 VB 답습).

        사이클 64 scanner `_apply_price_filter` 패턴 답습 + PriceFilter 단일 source.
        보유 종목 절대 보호 (사이클 32 R4 답습) + raw.bfdy_clpr miss graceful 통과.

        - PriceFilter 비활성 (min=0, max=0) → 전체 통과 (회귀 보존)
        - 보유 종목 → 무조건 통과 (사이클 30 005935 매매 안전성 영속)
        - raw.bfdy_clpr miss → graceful 통과 (사이클 64 답습)
        - min_price > 0 + bfdy_clpr < min_price → 차단
        - max_price > 0 + bfdy_clpr > max_price → 차단
        """
        from src.db import stock_master as _sm_mod
        from src.db.system_config import get_price_filter

        pf = await get_price_filter()
        if not pf.is_active:
            return tickers

        # 보유 종목 절대 보호 (사이클 32 R4 + 사이클 64 답습)
        protected: set[str] = set()
        try:
            from src.engine import scanner as _scanner_mod
            protected = _scanner_mod._collect_protected_tickers_for_scanner()
        except Exception:
            logger.debug(
                "[bfb_price_filter_prepare] protected_tickers 조회 실패 graceful",
                exc_info=True,
            )

        survivors: list[str] = []
        for ticker in tickers:
            if ticker in protected:
                survivors.append(ticker)
                continue
            prdy_clpr = 0
            try:
                basics = await _sm_mod.get(ticker)
                if basics and basics.raw:
                    raw_val = basics.raw.get("bfdy_clpr", 0)
                    if raw_val:
                        prdy_clpr = int(raw_val)
            except Exception:
                logger.debug(
                    "[bfb_price_filter_prepare] stock_master 조회 실패 graceful: %s",
                    ticker, exc_info=True,
                )

            if prdy_clpr <= 0:
                # graceful 통과 (사이클 64 Q2 답습 — 신규 상장 영구 차단 방지)
                survivors.append(ticker)
                continue

            below_min = pf.min_price > 0 and prdy_clpr < pf.min_price
            above_max = pf.max_price > 0 and prdy_clpr > pf.max_price
            if not (below_min or above_max):
                survivors.append(ticker)

        return survivors

    # ------------------------------------------------------------------
    # 외부 노출 (사전 구독, 깔때기, 대시보드)
    # ------------------------------------------------------------------
    def get_scanned_tickers(self) -> list[str]:
        return self._scanned_tickers

    def get_scan_stats(self) -> dict:
        return dict(self._scan_stats)

    def get_targets_status(self) -> dict[str, dict]:
        """대시보드 노출용."""
        return {
            ticker: {
                "pole_start": info["pole_start"],
                "pole_high": info["pole_high"],
                "flag_high": info["flag_high"],
                "flag_low": info["flag_low"],
                "atr14": info["atr14"],
                "k": 0.0,
                "target_price": info["flag_high"],
                "open_price": 0,
                "target_offset": 0,
                "open_confirmed": True,
            }
            for ticker, info in self._candidates.items()
        }

    # ------------------------------------------------------------------
    # 신호 평가
    # ------------------------------------------------------------------
    def check_buy_signal(self, ticker, current_price, open_price) -> Signal:
        if self.state.buy_disabled:
            return Signal.NONE
        if self.state.has_position(ticker) or self.state.is_buy_pending(ticker):
            return Signal.NONE
        if self.state.is_sold_today(ticker):
            return Signal.NONE
        if ticker in self._bought_today:
            return Signal.NONE
        if self.is_max_positions():
            return Signal.NONE
        if self.is_daily_loss_exceeded():
            return Signal.NONE

        info = self._candidates.get(ticker)
        if not info:
            return Signal.NONE

        # 시간 가드
        now_t = datetime.now().time()
        entry_start = _parse_time_hhmm(self.config.params["entry_start"])
        entry_end = _parse_time_hhmm(self.config.params["entry_end"])
        if now_t < entry_start or now_t > entry_end:
            return Signal.NONE

        # 쿨다운
        today = datetime.now(KST).date()
        cd_until = self._cooldown_until.get(ticker)
        if cd_until and cd_until >= today:
            return Signal.NONE

        flag_high = info["flag_high"]
        if flag_high <= 0 or current_price <= 0:
            return Signal.NONE

        # 사이클 23 P2-1 — breakout_retention_minutes 유지시간 가드
        prev = self._prev_price.get(ticker, 0)
        self._prev_price[ticker] = current_price
        now_kst = datetime.now(KST)
        retention_min = int(self.config.params.get("breakout_retention_minutes", 3))

        first_seen = self._breakout_first_seen.get(ticker)
        if first_seen is not None:
            # 이미 돌파 대기 중
            if current_price < flag_high:
                # 후퇴 — 대기 종료
                self._breakout_first_seen.pop(ticker, None)
                logger.info("BFB 돌파 후퇴(retention 대기 종료): %s", ticker)
                return Signal.NONE
            elapsed = (now_kst - first_seen).total_seconds()
            if elapsed < retention_min * 60:
                # 아직 대기 중
                return Signal.NONE
            # retention 충족 — 정상 흐름 (거래량 컷 등 다음 가드로 진행)
            self._breakout_first_seen.pop(ticker, None)
        else:
            # 첫 돌파 감지 여부 확인 (prev<flag_high AND now>=flag_high)
            if not (prev < flag_high <= current_price):
                return Signal.NONE
            if retention_min > 0:
                # 첫 돌파 감지 → 대기 등록 + NONE
                self._breakout_first_seen[ticker] = now_kst
                logger.info(
                    "BFB 돌파 1차 감지(retention 대기 시작): %s flag_high(%d) retention=%d분",
                    ticker, flag_high, retention_min,
                )
                return Signal.NONE
            # retention_min == 0 이면 즉시 진행 (기존 동작 회귀)

        # 거래량 컷
        from src.engine.scanner import ticker_prices
        info_price = ticker_prices.get(ticker, {})
        acml_vol = int(info_price.get("acml_vol", 0) or 0)
        vol_threshold = int(info["flag_avg_volume"] * self.config.params["breakout_volume_mult"])
        if acml_vol < vol_threshold:
            return Signal.NONE

        # 진입 확정
        self._bought_today.add(ticker)
        logger.info(
            "눌림목 돌파 매수 신호: %s 현재가(%d) — flag_high(%d) 돌파 + 거래량(%d≥%d)",
            ticker, current_price, flag_high, acml_vol, vol_threshold,
        )
        self.state.buy_signals.append({
            "ticker": ticker,
            "name": "",
            "price": current_price,
            "flag_high": flag_high,
            "target_price": flag_high + (info["pole_high"] - info["pole_start"]),
            "atr": info["atr14"],
            "change_rate": 0,
            "time": datetime.now().strftime("%H:%M:%S"),
        })
        if len(self.state.buy_signals) > 20:
            self.state.buy_signals.pop(0)
        return Signal.BUY

    def check_exit_signal(self, ticker, current_price, open_price) -> Signal:
        pos = self.state.positions.get(ticker)
        if not pos:
            return Signal.NONE

        # 1) 하드 손절 -5%
        loss_rate = (
            (current_price - pos.buy_price) / pos.buy_price * 100
            if pos.buy_price > 0 else 0
        )
        stop_loss = self.config.params["stop_loss_rate"]
        if loss_rate <= stop_loss:
            logger.info(
                "눌림목 손절: %s 매수가(%d) 대비 %.1f%%",
                ticker, pos.buy_price, loss_rate,
            )
            return Signal.STOP_LOSS

        info = self._candidates.get(ticker)

        # 2) 플래그 하단 이탈
        if info and info.get("flag_low") and current_price < info["flag_low"]:
            logger.info(
                "눌림목 플래그 하단 이탈: %s 현재가(%d) < flag_low(%d)",
                ticker, current_price, info["flag_low"],
            )
            return Signal.STOP_LOSS

        # 3) 측정된 이동 (measured move) 도달 — 절반 익절 (1차 구현은 마킹만, 전량 청산은 호출자 책임)
        # 마킹 후 잔여는 ATR 트레일링으로 처리
        if info:
            pole_width = info["pole_high"] - info["pole_start"]
            measured_target = info["flag_high"] + pole_width if pole_width > 0 else 0
            already_partial = self._partial_exit.get(ticker, False)
            if measured_target > 0 and current_price >= measured_target and not already_partial:
                self._partial_exit[ticker] = True
                logger.info(
                    "눌림목 측정된 이동 도달: %s 현재가(%d) ≥ 타겟(%d) — 익절 신호",
                    ticker, current_price, measured_target,
                )
                # 1차 구현: 전량 청산 신호 (부분 매도 헬퍼는 향후 도입)
                return Signal.TRAILING_STOP

        # 4) ATR×2 트레일링
        if info and pos.high_since_buy > 0:
            atr = info.get("atr14", 0)
            mult = self.config.params["atr_trail_mult"]
            if atr > 0:
                chandelier = pos.high_since_buy - atr * mult
                if current_price <= chandelier:
                    logger.info(
                        "눌림목 ATR 트레일링: %s 고점(%d) - ATR×%.1f = %d / 현재 %d",
                        ticker, pos.high_since_buy, mult, int(chandelier), current_price,
                    )
                    return Signal.TRAILING_STOP

        # 5) 시간 청산 (max_hold_days 영업일 초과)
        max_hold = self.config.params["max_hold_days"]
        today = datetime.now(KST).date()
        # 단순 캘린더일 + 2일 보정 — 영업일 정확도 미흡하지만 1차 구현
        if pos.buy_date and (today - pos.buy_date).days > max_hold + 2:
            logger.info(
                "눌림목 시간 청산: %s buy_date=%s today=%s 보유일수 초과",
                ticker, pos.buy_date, today,
            )
            return Signal.TRAILING_STOP

        return Signal.NONE

    def check_force_clear(self) -> list[str]:
        """15:20 강제 청산 없음 — max_hold_days 시간 청산은 check_exit_signal 에서 처리."""
        return []

    def calc_buy_quantity(self, current_price: int) -> int:
        if current_price <= 0:
            return 0
        ratio = self.config.params["position_ratio"]
        amount = int(self.state.total_investment * ratio)
        qty = amount // current_price
        if qty > 0:
            return qty
        return self._fallback_one_share(current_price)

    def register_cooldown_after_exit(self, ticker: str) -> None:
        """청산 완료 후 호출 — 쿨다운 등록.

        OrderEngine.execute_sell 체결 처리 또는 RiskManager 매도 완료 시 호출 가능.
        1차 구현은 메모리만, 향후 DB 영속화 가능.
        """
        days = self.config.params["reentry_cooldown_days"]
        today = datetime.now(KST).date()
        self._cooldown_until[ticker] = today + timedelta(days=days)
        # 사이클 23 P2-1 — 청산 후 retention 대기 상태 정리
        self._breakout_first_seen.pop(ticker, None)
        # 매수 1회 가드도 함께 해제 (당일 매도 set 이 차단하므로 영향 없음)

    def _reset_daily_state(self) -> None:
        """사이클 23 P2-1 — 일일 초기화 시 _breakout_first_seen 정리."""
        self._breakout_first_seen.clear()

    def on_position_closed(self, ticker: str) -> None:
        """사이클 185 — 포지션 청산 시 partial_exit 보유결합 상태 정리."""
        self._partial_exit.pop(ticker, None)
