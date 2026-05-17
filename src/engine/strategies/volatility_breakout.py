"""변동성 돌파 전략 (래리 윌리엄스).

- 대상: 코스피+코스닥 전체에서 시총/거래대금 조건 필터
- prepare(): 조건 충족 종목의 21일 일봉으로 K값(노이즈 비율 기반) 계산 → Target Price 설정
- 매수: 당일 현재가 >= Target Price (시가 + 전일 Range * K)
- 손절: 매수가 대비 -3%
- 강제 청산: 15:20 전량 청산
- 비중: 할당 자금의 10%
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime

from src.engine.strategy_base import Signal, StrategyBase, StrategyConfig

logger = logging.getLogger(__name__)


class VolatilityBreakoutStrategy(StrategyBase):
    """변동성 돌파 전략."""

    # 매매 가능 보드 — PRE_NXT(08:00~09:00) + MAIN(09:00~15:20) 만 활성.
    # 결정 (2026-05-15, 결함 D): VB 는 당일 15:20 일괄매도 정책 — NXT 애프터(15:30~20:00)
    # 매매 비활성. POST_NXT 포함 시 `_force_clear_main_only` 가 keeps_post_nxt=True 분기로
    # 15:20 청산을 스킵하는데, 19:50 청산 코드는 누락되어 OVERNIGHT 보유 결함 발생
    # (5/13~5/15 005930 멀티데이 보유 후 손절 사고). VB OVERNIGHT 거부 원칙 회복.
    DEFAULT_TRADABLE_BOARDS = ("pre_nxt", "main")

    DEFAULT_PARAMS = {
        "tradable_boards": list(DEFAULT_TRADABLE_BOARDS),
        "stop_loss_rate": -3.0,
        "position_ratio": 0.10,
        "max_positions": 10,
        "daily_loss_limit": -5.0,
        "k_period": 20,
        # 보드별 K값 곱 (Phase 5 Q1=C: 보드별 분리). 기본 동일값으로 시작 후 운영 데이터로 튜닝
        "k_value_krx_main": 1.0,
        "k_value_nxt_pre": 1.0,
        "k_value_nxt_post": 1.0,
        # 거래소 라우팅 (Phase 4): KRX / NXT / SOR. 미설정 시 KRX
        "exchange": "KRX",
        # 종목 스캔 조건 (Settings에서 변경 가능)
        "min_market_cap": 100_000_000_000,   # 시총 1,000억 이상
        "min_trade_amount": 20_000_000_000,  # 거래대금 200억 이상
        "max_scan_stocks": 100,              # 최대 스캔 종목 수
    }

    def __init__(self, config: StrategyConfig):
        merged = {**self.DEFAULT_PARAMS, **config.params}
        config.params = merged
        super().__init__(config)
        # ticker -> {target_offset_base, k, prev_range, boards: {board: {open_price, target_price, target_offset}}}
        self._targets: dict[str, dict] = {}
        # ticker -> {board: bool} — 보드별 시가 확정 여부 (Phase 5 분리)
        self._open_confirmed: dict[str, dict[str, bool]] = {}
        # ticker -> 보드별 이전 틱 가격 (보드별 돌파 순간 감지용)
        self._prev_price: dict[str, dict[str, int]] = {}
        # 익일 청산 안전망 (2026-05-15, 결함 D 잔여) — `_execute_next_day_clear` 의
        # 30s 시가 안정화 중 on_tick 청산 race 차단용 플래그. momentum 패턴과 동일.
        # VB 정책은 당일 15:20 일괄 매도지만 그게 누락되면 본 플래그 + check_exit_signal
        # 익일 청산 분기로 다음 영업일 NXT 프리 청산 안전망 발동.
        self._next_day_clear_pending = False
        # 스캔된 종목 리스트 (subscribe용)
        self._scanned_tickers: list[str] = []

    async def prepare(self) -> None:
        """장 시작 전: 시총/거래대금 조건 종목 스캔 → 21일 일봉으로 K값/Target 계산."""
        import asyncio

        from src.api.condition import fetch_daily_candles

        tickers = await self._scan_universe()
        k_period = self.config.params["k_period"]
        today_str = date.today().strftime("%Y%m%d")
        prepared = 0

        # 일봉 fetch 병렬화 (KIS Rate Limit semaphore가 자동 직렬화)
        async def _fetch_one(ticker: str):
            try:
                return ticker, await fetch_daily_candles(ticker, days=k_period + 2)
            except Exception as e:
                logger.warning("변동성돌파 일봉 fetch 실패: %s — %s", ticker, e)
                return ticker, None

        fetched = await asyncio.gather(*[_fetch_one(t) for t in tickers])

        for ticker, candles in fetched:
            if candles is None:
                continue
            try:
                if len(candles) < 2:
                    continue

                # candles[0]의 거래일이 오늘이면 candles[1]을 "전일"로 사용 (장 시작 전 빈/부분봉 방어)
                prev_idx = 1 if candles[0].get("stck_bsop_date") == today_str else 0
                if len(candles) <= prev_idx + 1:
                    continue

                # 노이즈 비율 계산: prev 기준 그 이전 k_period일
                noise_list = []
                for c in candles[prev_idx + 1 :]:
                    high = int(c.get("stck_hgpr", "0"))
                    low = int(c.get("stck_lwpr", "0"))
                    open_p = int(c.get("stck_oprc", "0"))
                    close_p = int(c.get("stck_clpr", "0"))
                    rng = high - low
                    if rng > 0:
                        noise = 1 - abs(close_p - open_p) / rng
                        noise_list.append(noise)

                if not noise_list:
                    continue

                k = sum(noise_list) / len(noise_list)

                # 전일 Range
                prev = candles[prev_idx]
                prev_high = int(prev.get("stck_hgpr", "0"))
                prev_low = int(prev.get("stck_lwpr", "0"))
                prev_range = prev_high - prev_low
                if prev_range <= 0:
                    logger.debug(
                        "변동성돌파 prev_range=0 skip: %s (date=%s)",
                        ticker, prev.get("stck_bsop_date"),
                    )
                    continue

                target_offset = int(prev_range * k)
                if target_offset <= 0:
                    logger.debug(
                        "변동성돌파 target_offset=0 skip: %s (k=%.4f, range=%d)",
                        ticker, k, prev_range,
                    )
                    continue

                self._targets[ticker] = {
                    "k": round(k, 4),
                    "prev_range": prev_range,
                    "target_offset_base": target_offset,  # k_value_* 곱 전 기본값
                    # backwards-compat (단일 보드 운영 시)
                    "target_offset": target_offset,
                    "target_price": 0,
                    "open_price": 0,
                    # 보드별 시가/타겟 (Phase 5 Q1=C 분리)
                    "boards": {},
                }
                # 보드별 confirmed 플래그
                self._open_confirmed[ticker] = {}

                # 09:30 scan_stocks() 이전에도 등락률 필터가 동작하도록 전일종가 사전 등록
                from src.engine.scanner import ticker_prev_close
                prev_close = int(prev.get("stck_clpr", "0"))
                if prev_close > 0:
                    ticker_prev_close[ticker] = prev_close

                prepared += 1

            except Exception as e:
                logger.warning("변동성돌파 prepare 실패: %s — %s", ticker, e)
                continue

        self._scanned_tickers = list(self._targets.keys())
        logger.info("변동성돌파 전략 준비 완료: %d/%d종목 (K값 계산)", prepared, len(tickers))

    async def _scan_universe(self) -> list[str]:
        """시총/거래대금 조건으로 코스피+코스닥 종목을 스캔한다.

        거래량순위 API 응답에 포함된 prdy_vol/lstn_stcn/stck_prpr/prdy_vrss로
        시총·전일 거래대금을 직접 산출한다 (개별 inquire-price 호출 없음).

        prdy_vol·prdy_close는 KIS 영업일 기준이므로 휴장 직후 첫 영업일이나
        장 시작 전이라도 시간 의존 없이 일관된 결과를 보장한다.
        """
        from src.api.base import kis_get, KisApiError
        from src.db.system_logs import write_log
        from src.engine.scanner import ticker_names, ETF_KEYWORDS

        min_mcap = self.config.params["min_market_cap"]
        min_trade = self.config.params["min_trade_amount"]
        max_stocks = self.config.params["max_scan_stocks"]

        # 거래량순위 API로 전체 시장 상위 종목 확보 ("J"가 코스피+코스닥 전체)
        # KIS 거래량순위는 단일 페이지(~30건). BLNG_CLS_CODE 별로 다른 정렬 기준의
        # 상위 종목 합집합 → 후보 풀 ~60~90종목으로 확장 (max_scan_stocks=100 활용도 향상)
        #   0: 평균거래량 / 1: 거래증가율 / 3: 거래금액순 (KIS 표준)
        BLNG_CODES = ("0", "1", "3")
        rank_items: list[dict] = []
        seen_tickers: set[str] = set()
        for blng in BLNG_CODES:
            try:
                params = {
                    "FID_COND_MRKT_DIV_CODE": "J",
                    "FID_COND_SCR_DIV_CODE": "20171",
                    "FID_INPUT_ISCD": "0000",
                    "FID_DIV_CLS_CODE": "0",
                    "FID_BLNG_CLS_CODE": blng,
                    "FID_TRGT_CLS_CODE": "111111111",
                    "FID_TRGT_EXLS_CLS_CODE": "000000",
                    "FID_INPUT_PRICE_1": "0",
                    "FID_INPUT_PRICE_2": "0",
                    "FID_VOL_CNT": "0",
                    "FID_INPUT_DATE_1": "0",
                }
                data = await kis_get(
                    "/uapi/domestic-stock/v1/quotations/volume-rank",
                    "FHPST01710000",
                    params,
                )
                for item in data.get("output", []) or []:
                    name = item.get("hts_kor_isnm", "")
                    if any(kw in name for kw in ETF_KEYWORDS):
                        continue
                    ticker = item.get("mksc_shrn_iscd", "")
                    if not ticker or ticker in seen_tickers:
                        continue
                    seen_tickers.add(ticker)
                    rank_items.append(item)
            except KisApiError:
                logger.warning("변동성돌파 거래량순위 조회 실패: blng=%s", blng)
            # KIS Rate Limit 보호 — 호출간 50ms (kis_get Semaphore 가 20/s 직렬화하지만 burst 회피)
            await asyncio.sleep(0.05)

        logger.info(
            "변동성돌파 유니버스 후보: %d종목 (blng 0/1/3 합집합 dedupe)",
            len(rank_items),
        )

        # 거래량순위 응답 데이터로 시총·전일 거래대금 추정 → 필터
        filtered: list[str] = []
        for item in rank_items:
            if len(filtered) >= max_stocks:
                break
            ticker = item.get("mksc_shrn_iscd", "")
            if not ticker:
                continue
            # 종목코드 형식 검증 — ETF·ETN·신주인수권 등 알파벳 포함 코드 차단
            if not (len(ticker) == 6 and ticker.isdigit()):
                continue
            try:
                price = int(item.get("stck_prpr", "0"))
                listed = int(item.get("lstn_stcn", "0"))
                prdy_vol = int(item.get("prdy_vol", "0"))
                # KIS prdy_vrss는 부호 포함 정수 (상승=+, 하락=-)
                prdy_vrss = int(item.get("prdy_vrss", "0"))
                prdy_close = price - prdy_vrss
            except (ValueError, TypeError):
                continue

            if price <= 0 or listed <= 0 or prdy_vol <= 0 or prdy_close <= 0:
                continue

            mcap = price * listed
            prdy_trade_amt = prdy_vol * prdy_close
            if mcap >= min_mcap and prdy_trade_amt >= min_trade:
                name = item.get("hts_kor_isnm", "")
                if name:
                    ticker_names[ticker] = name
                filtered.append(ticker)

        logger.info("변동성돌파 유니버스 확정: %d종목 (시총 %d억+, 거래대금 %d억+)",
                     len(filtered), min_mcap // 100_000_000, min_trade // 100_000_000)

        if not filtered:
            if not rank_items:
                msg = "변동성돌파 유니버스 0종목 — 거래량순위 API 응답이 비어있음"
            else:
                msg = (
                    f"변동성돌파 유니버스 0종목 — 후보 {len(rank_items)}종목 중 "
                    f"시총 {min_mcap // 100_000_000}억+ / 거래대금 "
                    f"{min_trade // 100_000_000}억+ 필터 통과 없음"
                )
            logger.error(msg)
            try:
                await write_log("ERROR", msg)
            except Exception:
                logger.exception("system_logs 기록 실패")

        return filtered

    def get_scanned_tickers(self) -> list[str]:
        """스캔된 종목 리스트를 반환한다 (WebSocket 구독용)."""
        return self._scanned_tickers

    def get_targets_status(self) -> dict[str, dict]:
        """종목별 타겟 가격 정보를 반환한다 (활성 보드 필터링, 2026-05-13 작업 1).

        - 활성 보드(`session_tracker.active`) ∩ 전략 `tradable_boards` 에 속하는 보드만 노출
        - 교집합 공집합 → `boards={}` + top-level 0 + `open_confirmed={}`
        - 노출 보드 있음 → 우선순위(main → post_nxt → pre_nxt) 첫 보드 기준 top-level 값
        - session 모듈 import/접근 예외 → fallback: 기존 모든 보드 노출 (외부 호환 + 운영자 시야 보존)

        Phase 5 응답 스키마 보존 — `boards` 빈 dict 허용, 키 자체는 제거하지 않는다.
        """
        # 활성 보드 ∩ tradable_boards = 노출 보드 집합
        visible: set[str] | None
        try:
            from src.engine.session import session_tracker, parse_tradable_boards

            active = session_tracker.active  # frozenset[MarketBoard]
            tradable_raw = self.config.params.get("tradable_boards")
            tradable = parse_tradable_boards(tradable_raw) if tradable_raw else None
            if not tradable:
                # 기본 tradable_boards fallback (전략 클래스 상수)
                tradable = parse_tradable_boards(list(self.DEFAULT_TRADABLE_BOARDS))
            visible = {b.value for b in (active & tradable)}
        except Exception:
            # session 모듈 장애 시 모든 보드 노출 (운영자 시야 보존)
            visible = None

        # 우선순위: main → post_nxt → pre_nxt
        _BOARD_PRIORITY = ("main", "post_nxt", "pre_nxt")

        result = {}
        for ticker, info in self._targets.items():
            board_states = self._open_confirmed.get(ticker, {})
            all_boards = info.get("boards", {})

            if visible is None:
                # fallback — 기존 모든 보드 노출
                exposed_boards = {
                    board: {
                        "open_price": b.get("open_price", 0),
                        "target_price": b.get("target_price", 0),
                        "target_offset": b.get("target_offset", 0),
                        "confirmed": board_states.get(board, False),
                    }
                    for board, b in all_boards.items()
                }
                result[ticker] = {
                    "k": info.get("k", 0),
                    "target_price": info.get("target_price", 0),
                    "open_price": info.get("open_price", 0),
                    "target_offset": info.get("target_offset", 0),
                    "boards": exposed_boards,
                    "open_confirmed": board_states,
                }
                continue

            # 노출 보드만 추출 (visible 으로 필터)
            exposed_boards = {
                board: {
                    "open_price": b.get("open_price", 0),
                    "target_price": b.get("target_price", 0),
                    "target_offset": b.get("target_offset", 0),
                    "confirmed": board_states.get(board, False),
                }
                for board, b in all_boards.items()
                if board in visible
            }
            exposed_confirmed = {b: v for b, v in board_states.items() if b in visible}

            if not exposed_boards:
                # 교집합 공집합 — top-level 도 0 으로 가린다
                result[ticker] = {
                    "k": info.get("k", 0),
                    "target_price": 0,
                    "open_price": 0,
                    "target_offset": 0,
                    "boards": {},
                    "open_confirmed": {},
                }
                continue

            # top-level: 노출 보드 중 우선순위 첫 보드 — confirmed 우선
            top_board: str | None = None
            for cand in _BOARD_PRIORITY:
                if cand in exposed_boards and exposed_boards[cand]["confirmed"]:
                    top_board = cand
                    break
            if top_board is None:
                for cand in _BOARD_PRIORITY:
                    if cand in exposed_boards:
                        top_board = cand
                        break
            # exposed_boards 비어있지 않으므로 top_board 는 반드시 결정됨
            top = exposed_boards[top_board] if top_board else {}

            result[ticker] = {
                "k": info.get("k", 0),
                "target_price": top.get("target_price", 0),
                "open_price": top.get("open_price", 0),
                "target_offset": top.get("target_offset", 0),
                "boards": exposed_boards,
                "open_confirmed": exposed_confirmed,
            }
        return result

    _BOARD_K_KEY = {
        "main": "k_value_krx_main",
        "pre_nxt": "k_value_nxt_pre",
        "post_nxt": "k_value_nxt_post",
    }

    def _resolve_active_board(self) -> str | None:
        """현재 활성 보드 중 전략의 tradable_boards에 포함된 첫 보드를 반환.

        우선순위 main → post_nxt → pre_nxt — KRX 메인 활성 시 그것을 우선.
        """
        from src.engine.session import session_tracker, MarketBoard

        active = session_tracker.active
        if not active:
            return None
        allowed = self.config.params.get("tradable_boards") or list(self.DEFAULT_TRADABLE_BOARDS)
        for candidate in ("main", "post_nxt", "pre_nxt"):
            if candidate in allowed and MarketBoard(candidate) in active:
                return candidate
        return None

    def on_open_price_confirmed(self, ticker: str, open_price: int, board: str = "main") -> None:
        """보드별 시가 확정 — Target Price를 보드별로 계산한다."""
        info = self._targets.get(ticker)
        if not info or open_price <= 0:
            return

        base = info.get("target_offset_base", info.get("target_offset", 0))
        k_key = self._BOARD_K_KEY.get(board, "k_value_krx_main")
        k_mult = float(self.config.params.get(k_key, 1.0))
        target_offset = max(int(base * k_mult), 0)

        info.setdefault("boards", {})[board] = {
            "open_price": open_price,
            "target_price": open_price + target_offset,
            "target_offset": target_offset,
        }
        self._open_confirmed.setdefault(ticker, {})[board] = True

        # backwards-compat: 첫 확정된 보드의 값을 top-level에도 (대시보드/AI자문 호환)
        if not info.get("open_price"):
            info["open_price"] = open_price
            info["target_price"] = open_price + target_offset
            info["target_offset"] = target_offset

    def check_buy_signal(
        self, ticker: str, current_price: int, open_price: int,
    ) -> Signal:
        """현재 활성 보드의 Target Price 돌파 시 매수."""
        if self.state.buy_disabled:
            return Signal.NONE
        if self.state.has_position(ticker) or self.state.is_buy_pending(ticker) or self.state.is_sold_today(ticker):
            return Signal.NONE
        if self.is_max_positions():
            return Signal.NONE
        if self.is_daily_loss_exceeded():
            return Signal.NONE

        info = self._targets.get(ticker)
        if not info:
            return Signal.NONE

        board = self._resolve_active_board()
        if board is None:
            return Signal.NONE

        # 시가 미확정 시 현재가를 보드 시가로 사용하여 즉시 확정
        confirmed = self._open_confirmed.get(ticker, {}).get(board, False)
        if not confirmed and open_price > 0:
            self.on_open_price_confirmed(ticker, open_price, board=board)

        board_info = info.get("boards", {}).get(board)
        if not board_info:
            return Signal.NONE

        target = board_info.get("target_price", 0)
        if target <= 0:
            return Signal.NONE

        prev = self._prev_price.setdefault(ticker, {}).get(board, 0)
        self._prev_price[ticker][board] = current_price

        # 보드별 첫 틱은 기록만, 돌파 순간만 감지
        if prev == 0:
            return Signal.NONE

        if prev < target and current_price >= target:
            from src.engine.scanner import t, ticker_names
            board_open = board_info.get("open_price", 0)
            change_rate = round((current_price - board_open) / board_open * 100, 1) if board_open > 0 else 0
            logger.info(
                "변동성돌파 매수 신호 [%s]: %s 현재가(%d) >= 목표가(%d), 이전가(%d), K=%.4f",
                board, t(ticker), current_price, target, prev, info["k"],
            )
            self.state.buy_signals.append({
                "ticker": ticker,
                "name": ticker_names.get(ticker, ""),
                "price": current_price,
                "target_price": target,
                "k": info["k"],
                "board": board,
                "change_rate": change_rate,
                "time": datetime.now().strftime("%H:%M:%S"),
            })
            if len(self.state.buy_signals) > 20:
                self.state.buy_signals.pop(0)
            return Signal.BUY

        return Signal.NONE

    @staticmethod
    def _get_stop_loss_for_board(params: dict, board: str | None) -> float:
        """보드별 손절 임계 우선순위 조회 (사이클 3, 2026-05-17).

        우선순위:
          1. `params[f"stop_loss_{board}"]` — 음수면 채택 (보드별 차별화)
          2. `params["stop_loss_rate"]` — top-level fallback

        `board` 가 None 이면(테스트 환경 / SessionTracker 미동작) 보드별 키 건너뛰고
        top-level fallback. 운영자가 5/15 운영값(`stop_loss_rate=-3.5`) 그대로 두면
        보드별 키 부재 → top-level 적용 → 동작 회귀 보존.

        Args:
          params: 전략 params (DEFAULT_PARAMS 머지 후 dict)
          board: 활성 보드 문자열 ("main"/"pre_nxt"/"post_nxt") 또는 None

        Returns:
          음수 손절 임계값(예: -3.5). 모든 후보 부재 시 0.0(손절 분기 skip).
        """
        if board:
            board_key = f"stop_loss_{board}"
            board_val = params.get(board_key)
            if board_val is not None:
                try:
                    bv = float(board_val)
                except (TypeError, ValueError):
                    bv = 0.0
                if bv < 0:
                    return bv
                # 양수/0 은 무의미 — top-level fallback 으로
        # top-level fallback
        top = params.get("stop_loss_rate")
        if top is None:
            return 0.0
        try:
            tv = float(top)
        except (TypeError, ValueError):
            return 0.0
        return tv if tv < 0 else 0.0

    def check_exit_signal(
        self, ticker: str, current_price: int, open_price: int,
    ) -> Signal:
        """손절: 보드별 손절 임계 우선 (사이클 3, 2026-05-17) — 활성 보드의
        `stop_loss_{board}` 키 있으면 그것, 부재/None 이면 top-level `stop_loss_rate`.

        익일 보유 종목은 NEXT_DAY_CLEAR 안전망 발동.

        VB 정책상 당일 15:20 일괄 청산이 정상 경로 — 본 함수의 익일 청산 분기는
        15:20 청산이 누락된 비상 상황(POST_NXT 설정 오류, 시세 미수신, 시장가 거부,
        프로세스 재시작 race 등)에서만 발동. 2026-05-15 결함 D 잔여.
        """
        pos = self.state.positions.get(ticker)
        if not pos:
            return Signal.NONE

        # 1. 손절 — 가장 우선. 익일 청산 대기 중에도 손절은 즉시 발동.
        loss_rate = (current_price - pos.buy_price) / pos.buy_price * 100
        # 사이클 3 — 활성 보드별 손절 임계. SessionTracker 미동작 시(테스트 환경)
        # `_resolve_active_board()` 가 None 반환 → top-level fallback.
        try:
            active_board = self._resolve_active_board()
        except Exception:
            active_board = None
        stop_loss = self._get_stop_loss_for_board(self.config.params, active_board)
        if loss_rate <= stop_loss:
            from src.engine.scanner import t
            logger.info(
                "변동성돌파 손절: %s 매수가(%d) 대비 %.1f%% (현재가: %d)",
                t(ticker), pos.buy_price, loss_rate, current_price,
            )
            return Signal.STOP_LOSS

        # 2. 익일 청산 안전망 (2026-05-15, 결함 D 잔여) — 전일 매수 종목이 남아 있으면
        # 즉시 청산 신호. 단 scheduler 가 시가 안정화 중(_next_day_clear_pending=True)
        # 이면 보류 — scheduler 가 직접 처리 중이라 race 차단.
        if pos.is_next_day and not self._next_day_clear_pending:
            from src.engine.scanner import t
            logger.warning(
                "변동성돌파 익일 청산 안전망 발동: %s (매수일: %s, 정상은 당일 15:20 청산)",
                t(ticker), pos.buy_date,
            )
            return Signal.NEXT_DAY_CLEAR

        return Signal.NONE

    def check_force_clear(self) -> list[str]:
        """15:20 강제 청산 대상 종목 리스트를 반환한다."""
        return list(self.state.positions.keys())

    def calc_buy_quantity(self, current_price: int) -> int:
        """할당 자금의 position_ratio 비중으로 매수 수량 계산.

        비중 기준 0주이지만 신호가 이미 발생한 상태에서 잔여 자금이 1주는 살 수 있으면
        1주 매수 — 매수 기회 누락 방지(고가 종목이라 비중 가드에 막혀도 신호 우선).
        StrategyBase._fallback_one_share 공통 헬퍼 — 4개 전략 동일.
        """
        if current_price <= 0:
            return 0
        ratio = self.config.params["position_ratio"]
        amount = int(self.state.total_investment * ratio)
        qty = amount // current_price
        if qty > 0:
            return qty
        return self._fallback_one_share(current_price)
