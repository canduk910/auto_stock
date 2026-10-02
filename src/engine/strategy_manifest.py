"""전략 등록 명부 — `scheduler.__init__` 의 등록 7블록을 데이터로 얼린 단일 출처.

리팩토링 카드 #2 (cycle398 PR1, 설계 = `_workspace/refactor/2026-10-02_cards_2_3_design.md` §2,
사용자 10-02 승인 「스케쥴러.py 수정 승인할게」). `scheduler.TradingScheduler.__init__` 는
이 모듈의 `STRATEGY_MANIFEST` 를 순회해 등록할 뿐이고, 전략 id·이름·초기 켜짐/비중·클래스·
**순서**(= `risk.on_tick` 평가 순서 = 같은 틱 매수 우선순위)의 정본은 여기 하나다.

카드 #3 (cycle398 PR2, 같은 설계 §3 · 자문 = `_workspace/domain_consult/cycle398_refactor_cards_2_3.md`,
사용자 결정 10-02 A~D) — 원형(= 매수 평가 방식) 축을 명부의 **필수 칸**(기본값 없음)으로 연다.
칸을 빠뜨리면 `STRATEGY_MANIFEST` import 시 `TypeError`(dataclass 필수 인자 누락) 또는
`_validate_manifest()` 의 `ValueError` 로 드러난다 — 조용한 무매매(사이클 48 선례) 대신 기동 실패.

- `eval_driver` — 매수 평가 방식. `risk.py:88` `_TICK_BUY_EVAL_SKIP_STRATEGIES` 는 **리터럴로
  유지**한다(사용자 결정 B — risk 가 명부를 import 하지 않게). 교차 검사만 건다
  (`tests/unit/engine/test_cycle398_strategy_manifest.py`).
- `breakout_rank` — 돌파 구독 우선순위(`_collect_breakout_tickers` 병합 순서). `eval_driver ==
  "tick_breakout"` 일 때만 값을 가진다.
- `open_price_target` — KRX 메인 시가 확정 대상(VB·LTV, `_confirm_breakout_open_prices` 등).
- `close_at_1520` — 15:20 강제청산 대상(`_force_clear_main_only`). **`open_price_target` 과
  값이 우연히 같지만(둘 다 VB·LTV) 독립된 사실이다** — 합치지 않는다(설계 §3.3 리뷰 규약,
  자문 §2.1 `CLOSE_AT_1520` 행). 이 칸을 열어 두면 ETF 「15:20 판단 청산」을 `scheduler.py`
  재수정 없이 이 칸만 켜서 붙일 수 있다(자문 §2.2).
- `market_unit_policy` — 시장 유닛(cycle382) 소속. `"scale"` = 터틀 4전략(설계 랏 축소 대상),
  `"none"` = 대상 아님. 지금은 **선언 + 교차 검사일 뿐 행위가 없다**(시장 유닛 적용은 각 전략의
  `calc_buy_quantity`/`check_buy_signal` 안 명시 호출이 정본이고 이 칸이 그것을 대신하지 않는다).
  `"block_zero"` 는 평균회귀가 연구를 통과해 등록될 때 그 사이클이 더한다.

🔴 import 순서는 옛 `scheduler.py:34-40` 순서 그대로 둔다(모듈 로드 순서 보존 — 과거 VCP
import 부작용 패턴은 이미 리터럴로 없앴다, `strategy_base.py` 주석 참조). import 를 바꾸지 않는다.

이 모듈을 import 하는 곳은 `scheduler.py` 하나뿐이다(순환 import 없음). 전략 모듈이
`scheduler` 를 참조하는 곳은 함수 안 지연 import 뿐이라 이 모듈을 끌어올리지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
from src.engine.strategies.momentum import MomentumStrategy
from src.engine.strategies.donchian_swing import DonchianSwingStrategy
from src.engine.strategies.kojiro import KojiroStrategy
from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy
from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy
from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy
from src.engine.strategy_base import StrategyBase

#: 매수 평가 방식 — `tick_breakout` = 돌파 구독 그룹으로 후보를 구독하고 틱으로 평가(BFB·VCP·VB·LTV) ·
#: `tick_scan` = 자기 스캔(`scan_stocks`) 결과로 구독하고 틱으로 평가(momentum) ·
#: `swing_poll` = REST 폴로 평가, 틱 매수 평가 제외(donchian·kojiro).
EvalDriver = Literal["tick_breakout", "tick_scan", "swing_poll"]

#: 시장 유닛(cycle382) 소속 — `scale` = 터틀 4전략(설계 랏 축소 대상) · `none` = 대상 아님.
MarketUnitPolicy = Literal["scale", "none"]


@dataclass(frozen=True)
class StrategyEntry:
    """등록 1행. 기본값을 두지 않는다 — 칸을 빠뜨리면 import 시 `TypeError` 로 드러난다."""

    cls: type[StrategyBase]
    strategy_id: str
    name: str
    enabled: bool
    weight: float
    eval_driver: EvalDriver
    breakout_rank: int | None
    open_price_target: bool
    close_at_1520: bool
    market_unit_policy: MarketUnitPolicy


#: 등록 명부 — 순서 = `scheduler.__init__` 등록 순서 = `risk.on_tick` 평가 순서(같은 틱
#: 매수 우선순위). 값(현행 리터럴과 동일, 설계 §3.2 표) —
#: momentum tick_scan/None/False/False/none · VB tick_breakout/2/True/True/none ·
#: LTV tick_breakout/3/True/True/none · donchian swing_poll/None/False/False/scale ·
#: BFB tick_breakout/0/False/False/scale · VCP tick_breakout/1/False/False/scale ·
#: kojiro swing_poll/None/False/False/scale.
STRATEGY_MANIFEST: tuple[StrategyEntry, ...] = (
    StrategyEntry(
        MomentumStrategy, "momentum", "상한가 모멘텀", True, 1.0,
        eval_driver="tick_scan", breakout_rank=None, open_price_target=False,
        close_at_1520=False, market_unit_policy="none",
    ),
    StrategyEntry(
        VolatilityBreakoutStrategy, "volatility_breakout", "변동성 돌파", False, 0.0,
        eval_driver="tick_breakout", breakout_rank=2, open_price_target=True,
        close_at_1520=True, market_unit_policy="none",
    ),
    StrategyEntry(
        LongTailVolatilityStrategy, "long_tail_volatility", "롱테일 변동성 돌파", False, 0.0,
        eval_driver="tick_breakout", breakout_rank=3, open_price_target=True,
        close_at_1520=True, market_unit_policy="none",
    ),
    StrategyEntry(
        DonchianSwingStrategy, "donchian_swing", "20일 신고가 스윙", False, 0.0,
        eval_driver="swing_poll", breakout_rank=None, open_price_target=False,
        close_at_1520=False, market_unit_policy="scale",
    ),
    StrategyEntry(
        BullFlagBreakoutStrategy, "bull_flag_breakout", "눌림목 돌파", False, 0.0,
        eval_driver="tick_breakout", breakout_rank=0, open_price_target=False,
        close_at_1520=False, market_unit_policy="scale",
    ),
    StrategyEntry(
        VcpBreakoutStrategy, "vcp_breakout", "변동성 수축 돌파", False, 0.0,
        eval_driver="tick_breakout", breakout_rank=1, open_price_target=False,
        close_at_1520=False, market_unit_policy="scale",
    ),
    # 고지로 대순환 스윙 (2026-07) — 다크런치(enabled=False, DB strategy_config 가 실제 값
    # 로드). donchian 동형 멀티데이 스윙 → 공유 순차 폴루프(SWING_POLL_IDS) 대상.
    StrategyEntry(
        KojiroStrategy, "kojiro", "고지로 대순환", False, 0.0,
        eval_driver="swing_poll", breakout_rank=None, open_price_target=False,
        close_at_1520=False, market_unit_policy="scale",
    ),
)


def _validate_manifest(manifest: tuple[StrategyEntry, ...]) -> None:
    """명부 불변식 — 위반은 `ValueError`(기동 실패, 조용한 무매매 금지, 설계 §3.2)."""
    seen_ids: set[str] = set()
    seen_ranks: set[int] = set()
    for e in manifest:
        if e.strategy_id in seen_ids:
            raise ValueError(f"strategy_manifest: strategy_id 중복 — {e.strategy_id!r}")
        seen_ids.add(e.strategy_id)

        if e.breakout_rank is not None:
            if e.breakout_rank in seen_ranks:
                raise ValueError(f"strategy_manifest: breakout_rank 중복 — {e.breakout_rank!r}")
            seen_ranks.add(e.breakout_rank)

        if (e.eval_driver == "tick_breakout") != (e.breakout_rank is not None):
            raise ValueError(
                f"strategy_manifest: {e.strategy_id!r} — eval_driver=='tick_breakout' 은 "
                "breakout_rank is not None 과 동치여야 한다"
            )

        if e.open_price_target and e.eval_driver != "tick_breakout":
            raise ValueError(
                f"strategy_manifest: {e.strategy_id!r} — open_price_target=True 는 "
                "eval_driver=='tick_breakout' 일 때만 허용된다"
            )


_validate_manifest(STRATEGY_MANIFEST)

#: 스윙 폴 대상(파생, 등록 순서 보존) — `scheduler._SWING_POLL_STRATEGIES` 가 이 이름으로 가져간다.
#: `risk.py:88` `_TICK_BUY_EVAL_SKIP_STRATEGIES` 는 사용자 결정 B 에 따라 리터럴로 유지하고,
#: 교차 검사만 건다(`test_cycle398_strategy_manifest.py`).
SWING_POLL_IDS: tuple[str, ...] = tuple(e.strategy_id for e in STRATEGY_MANIFEST if e.eval_driver == "swing_poll")

#: 돌파 구독 대상(파생, **등록 순서**) — `_reprepare_breakout_if_empty` 재시도 순서(X2, 등록 순서 유지).
BREAKOUT_IDS: tuple[str, ...] = tuple(e.strategy_id for e in STRATEGY_MANIFEST if e.breakout_rank is not None)

#: 돌파 구독 우선순위(파생, **`breakout_rank` 오름차순**) — `_collect_breakout_tickers` 병합 순서
#: (2026-08-08 사용자 결정, BFB/VCP 를 head 로).
BREAKOUT_SUBSCRIBE_ORDER: tuple[str, ...] = tuple(
    e.strategy_id for e in sorted(
        (x for x in STRATEGY_MANIFEST if x.breakout_rank is not None),
        key=lambda x: x.breakout_rank,
    )
)

#: 시가 목표가 대상(파생, 등록 순서) — `_confirm_breakout_open_prices` 등.
OPEN_PRICE_TARGET_IDS: tuple[str, ...] = tuple(e.strategy_id for e in STRATEGY_MANIFEST if e.open_price_target)

#: 15:20 강제청산 대상(파생, 등록 순서) — `_force_clear_main_only`. `OPEN_PRICE_TARGET_IDS` 와
#: 값이 우연히 같지만(VB·LTV) 독립된 사실이다(합치지 않는다, 모듈 docstring 참조).
CLOSE_AT_1520_IDS: tuple[str, ...] = tuple(e.strategy_id for e in STRATEGY_MANIFEST if e.close_at_1520)

#: 시장 유닛 축소 대상(파생, 등록 순서) — `param_catalog._TURTLE4` 와 교차 검사 대상(값은 같다).
MARKET_UNIT_SCALE_IDS: tuple[str, ...] = tuple(
    e.strategy_id for e in STRATEGY_MANIFEST if e.market_unit_policy == "scale"
)
