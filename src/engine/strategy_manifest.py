"""전략 등록 명부 — `scheduler.__init__` 의 등록 7블록을 데이터로 얼린 단일 출처.

리팩토링 카드 #2 (cycle398 PR1, 설계 = `_workspace/refactor/2026-10-02_cards_2_3_design.md` §2,
사용자 10-02 승인 「스케쥴러.py 수정 승인할게」). `scheduler.TradingScheduler.__init__` 는
이 모듈의 `STRATEGY_MANIFEST` 를 순회해 등록할 뿐이고, 전략 id·이름·초기 켜짐/비중·클래스·
**순서**(= `risk.on_tick` 평가 순서 = 같은 틱 매수 우선순위)의 정본은 여기 하나다.

🔴 import 순서는 옛 `scheduler.py:34-40` 순서 그대로 둔다(모듈 로드 순서 보존 — 과거 VCP
import 부작용 패턴은 이미 리터럴로 없앴다, `strategy_base.py` 주석 참조). import 를 바꾸지 않는다.

이 모듈을 import 하는 곳은 `scheduler.py` 하나뿐이다(순환 import 없음). 전략 모듈이
`scheduler` 를 참조하는 곳은 함수 안 지연 import 뿐이라 이 모듈을 끌어올리지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
from src.engine.strategies.momentum import MomentumStrategy
from src.engine.strategies.donchian_swing import DonchianSwingStrategy
from src.engine.strategies.kojiro import KojiroStrategy
from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy
from src.engine.strategies.vcp_breakout import VcpBreakoutStrategy
from src.engine.strategies.volatility_breakout import VolatilityBreakoutStrategy
from src.engine.strategy_base import StrategyBase


@dataclass(frozen=True)
class StrategyEntry:
    """등록 1행. 기본값을 두지 않는다 — 칸을 빠뜨리면 import 시 `TypeError` 로 드러난다."""

    cls: type[StrategyBase]
    strategy_id: str
    name: str
    enabled: bool
    weight: float


#: 등록 명부 — 순서 = `scheduler.__init__` 등록 순서 = `risk.on_tick` 평가 순서(같은 틱
#: 매수 우선순위). 카드 #2 범위는 등록뿐이다 — 원형 선언(`eval_driver` 등, 카드 #3)은
#: 이 PR 에서 다루지 않는다.
STRATEGY_MANIFEST: tuple[StrategyEntry, ...] = (
    StrategyEntry(MomentumStrategy, "momentum", "상한가 모멘텀", True, 1.0),
    StrategyEntry(VolatilityBreakoutStrategy, "volatility_breakout", "변동성 돌파", False, 0.0),
    StrategyEntry(LongTailVolatilityStrategy, "long_tail_volatility", "롱테일 변동성 돌파", False, 0.0),
    StrategyEntry(DonchianSwingStrategy, "donchian_swing", "20일 신고가 스윙", False, 0.0),
    StrategyEntry(BullFlagBreakoutStrategy, "bull_flag_breakout", "눌림목 돌파", False, 0.0),
    StrategyEntry(VcpBreakoutStrategy, "vcp_breakout", "변동성 수축 돌파", False, 0.0),
    # 고지로 대순환 스윙 (2026-07) — 다크런치(enabled=False, DB strategy_config 가 실제 값
    # 로드). donchian 동형 멀티데이 스윙 → 공유 순차 폴루프(_SWING_POLL_STRATEGIES) 대상.
    StrategyEntry(KojiroStrategy, "kojiro", "고지로 대순환", False, 0.0),
)
