# 카드 #2·#3 구조 설계 — 2026-10-02

> 요청: 사용자 10-02 「리팩터링 본체 시작하자. 스케쥴러.py 수정 승인할게. 자문부터 받아보자.」
> 명세: `_workspace/refactor/2026-09-27_strategy_add_remove_structure.md` 카드 #2·#3 · §2 · §3 · §4 · §11.
> 성격: **읽기 전용 설계.** 리포의 `src/`·`tests/`·설정·DB 는 손대지 않았고 git 쓰기도 없다. 기준 커밋 `09ecc598`(카드 #1·#5 배포 뒤).
> 표기: **[실측]** = 스크래치 사본(`git clone` → 시제품 수정 → pytest)에서 잰 값 · **[코드]** = 파일:줄을 읽은 사실 · **[추정]** = 판단.
> 사본: `scratchpad/c23/{base,pr1,pr2,cls,sb,rk}` · 로그 `run_base.txt`(13,603 통과 · 실패 0) · `run_pr2.txt` · `*_ast.txt`.

---

## 0. 결론 (10줄)

1. 전략 id 목록은 `src/` 안 **51곳**에 흩어져 있다(AST 스캔, 2개 이상 담은 리터럴 컬렉션)[실측]. 축은 11개다(§1). 카드 #2·#3 이 다루는 것은 「등록」·「평가 방식」·「돌파 구독」·「시가 목표가」 네 축의 `scheduler.py` 9자리다.
2. **카드 #2**: 새 모듈 `src/engine/strategy_manifest.py` 에 등록 7행을 둔다. `scheduler.__init__` 는 62줄 → 7줄 반복문이 된다. `scheduler.py` **3,786 → 3,730줄**(상한 3,900 여유 114 → 170)[실측].
3. 시제품으로 레지스트리 7행(id·이름·켜짐·비중·클래스·**순서**)이 현행과 같음을 확인했다[실측].
4. **카드 #3**: 원형 선언을 **명부의 행 칸**으로 둔다(명세의 「클래스 속성」 대신). 클래스 속성 방식은 전략 7파일을 건드려 AST 핀이 **64건** 더 깨진다. 명부 칸 방식은 **추가로 0건**이다[실측].
5. 파생한 네 튜플(`_SWING_POLL_STRATEGIES`·돌파 구독 순서·돌파 재준비 대상·시가 목표가 대상)은 현행 리터럴과 **순서까지** 같다[실측].
6. **`risk.py:88` 은 (가) 리터럴 유지 + 교차 검사를 권한다.** (나) 파생은 테스트 21건을 깬다(8영역 sha 핀 12 · 승인표·형제 핀 4 · 새 파일 인지 4 · r10b 1). 또 `test_cycle273e` r10b(「소스 리터럴이어야 한다」, 런타임 조작 차단 가드)를 **약화**해야 한다[실측].
7. `MARKET_UNIT_POLICY` 는 명부 칸(`"scale"|"none"`)으로 둔다. 지금은 **선언 + 교차 검사**일 뿐이고 행위는 없다. `"block_zero"` 는 소비자(평균회귀)가 생길 때 더한다.
8. 핀 비용: PR 마다 `scheduler.py` 핀 **22곳**을 같은 값으로 옮긴다(sha 10 · 줄 수 11 · 트리 전체 1). PR1 은 새 파일 인지 가드 3건과 소스 grep 테스트 1건이 더 붉다. PR2 는 소스 grep 테스트 1건이 더 붉다[실측].
9. 행위 동일 증명은 **PR0(테스트만)** 에서 현행 코드의 배선 표를 골든으로 얼린다. 켜짐 조합 128가지 × 배선 함수 방문 순서, 그리고 `scheduler.py` 의 `for sid in …` 반복 대상 전수를 담는다(§5).
10. 권고 순서 = PR0 골든(LOW, 핀 0) → PR1 카드 #2(MEDIUM) → PR2 카드 #3(HIGH, 도메인 확인) · `risk.py` 무접촉.

---

## 1. 전략 id 리터럴 전수 — 축별 (HEAD `09ecc598`)

스캔 스크립트: `scratchpad/find_sid_lits.py` (튜플·리스트·셋·딕트 키에 전략 id 2개 이상) + 단일 비교 `grep`.

| 축 | 사실 | 자리 [코드] | 8영역 | 이번 범위 |
|---|---|---|---|---|
| **A 등록·정체** | 전략 7개와 등록 순서(= `risk.on_tick` 평가 순서 = 같은 틱 매수 우선순위) | `scheduler.py:34-40` import · `:327-383` 생성·등록 · `param_catalog.py:138-146` `STRATEGY_IDS`(순수 데이터, 같은 순서) | — | **#2** |
| **B 평가 방식(폴)** | donchian·kojiro 는 폴로 매수 평가 | `scheduler.py:145` `_SWING_POLL_STRATEGIES`(사용 `:788` `:1843` `:2309` `:2763` `:2887`) · `risk.py:88` `_TICK_BUY_EVAL_SKIP_STRATEGIES` · `status_exit_watch.py:78` 그룹 3 · `:80` `_SWING_GROUP` | risk | **#3** (`scheduler` 파생 · `risk` 교차) |
| **C 돌파 구독** | BFB·VCP·VB·LTV 후보를 WS 구독에 넣는다. 우선순위 BFB→VCP→VB→LTV | `scheduler.py:1821-1826` `_collect_breakout_tickers` · `:2665-2666` `_reprepare_breakout_if_empty`(순서 VB→LTV→BFB→VCP = 등록 순서) · `status_exit_watch.py:76-77` 그룹 1·2 | — | **#3** |
| **D 시가 목표가** | VB·LTV 는 시가 기준 목표가 | `scheduler.py:782` · `:1671` · `:2624` · `open_price_rest.py:82` · `open_price_observe.py:101` · `param_catalog.py:427` `_VBLTV` | — | **#3** (`scheduler` 3자리만) |
| E 청산 일정 | 익일 청산 = momentum·LTV·VB · 15:20 강제청산 = VB·LTV · 멀티데이 배지 = donchian·VCP·kojiro(BFB 제외) · LTV 전용 분기 | `scheduler.py:1389` · `:2038` · `:1529` · `strategy_base.py:82` `_MULTIDAY_STRATEGIES` · `risk.py:79` `_PRE_MARKET_EXIT_EVAL_STRATEGIES` · `risk.py:232` `_DAY_HIGH_ANCHOR_EXCLUDED_STRATEGIES` | risk | 제외(각 1곳 · 안전 규약 상수) |
| F 시장 유닛 | 터틀 4전략만 설계 랏 축소 | **`src/` 에 집합 리터럴 없음** — 4전략 파일이 `_refresh_market_unit`(`vcp:297` `kojiro:298` `donchian:323` `bfb:235`)·`_market_unit_sizing`(`vcp:1790` `kojiro:1273` `donchian:1887` `bfb:1470`)을 직접 부른다 · `param_catalog.py:426` `_TURTLE4`(`market_unit_mode`·`sizing_mode` 등 `applies_to`) · 테스트 `test_cycle382_ast_market_unit.py:34` `TURTLE_FILES` | — | **#3** (선언 + 교차 검사만) |
| G 게이트 원형 | 발사 직전 게이트 = momentum·VB | `strategy_base.py:45` `_ALWAYS_STATUS_GATE_CANDIDATE_SIDS` · `status_exit_watch.py:454` | — | 교차(부분집합)만 |
| H 보드 폴백 | 4전략 기본 보드 | `session.py:75-84` `_DEFAULT_TRADABLE_BOARDS` | session | 교차(부분집합)만 |
| I 표시·관측 | 청산선 표시 · 깔때기 순서 · 피라미딩 섀도 · VCP 이벤트 · 구독 출처 카운트 | `position_exit_lines.py:58,75` · `funnel_capture.py:53` `_ORDER`(**등록 순서와 다르다** — 표시 순서) · `pyramid_shadow.py:74,81,374-378,561` · `log_metrics_collector.py:719,796` · `scheduler.py:1880-1918`(로그 서식 `vb=`·`ltv=`… D+1 grep 계약) | — | 제외 |
| J AI 매수평가 | 전략별 문맥·진입선 | `llm_buy_gate.py:289-301,358-449,375,485` · `llm_features.py:493,610,662` | — | 제외(명세 B12 — 부수) |
| K 백테스트 | 외부 MCP 지원 범위 | `backtest_orchestration.py:46,55` · `backtest_yaml.py:62-110` | — | 제외 |
| L 「momentum」 폴백 | 미등록·미상 전략을 momentum 으로 | `boot_manager.py:305,347,428,433,455-456` · `scheduler.py:2362,2393,3442-3444` · `order_engine.py:2844,3104,3409,3578` · `routes/trading.py:166` · `db/trade_history.py:92` · `models/trade.py:33` | order_engine | 제외(명세 D-2 — 행위 결정) |
| M 전략 전용 훅 | 재시작 기준점 재계산 | `boot_manager.py:506`(BFB) · `scheduler.py:2320`(VCP) | — | 제외(2회 — 3계명) |

- `scanner.py` 에는 전략 id 가 없다. `"momentum"`·`"breakout"`·`"swing"` 은 **구독 우선순위 그룹 이름**이다(`scanner.py:1643,1717,1779,1804,1896`). 전략 id 와 글자가 겹치지만 다른 축이다[코드].
- `routes/` 에는 `trading.py:166`(L축) 하나뿐이다. `strategy_funnel.py:91` 은 독스트링이다[코드].
- 「시장 유닛 4전략 집합」은 `src/` 에 **목록으로 존재하지 않는다**. 함수 호출의 유무가 곧 소속이다. 그래서 카드 #3 의 `MARKET_UNIT_POLICY` 는 새 사실을 만드는 게 아니라 흩어진 소속을 **하나의 선언으로 이름 붙이고 교차 검사**하는 것이다.

---

## 2. 카드 #2 구체안 — 등록 명부

### 2.1 위치·모양

`src/engine/strategy_manifest.py` (새 파일). 이 자리를 고른 이유는 셋이다.

- `src/engine/strategies/` 안은 안 된다. 카드 #1 명부(`tests/_strategy_census.py`)가 그 디렉터리의 `*.py` 를 **전부 전략으로 센다**. 명부 모듈을 두면 `NON_STRATEGY_FILES` 에 넣어야 한다. 전략 디렉터리를 glob 하는 가드 5곳도 그 파일을 읽는다.
- `strategies/__init__.py` 도 안 된다. 전략 모듈 하나만 import 해도 7개 전부가 로드된다. 그러면 순환 import 위험이 생긴다.
- `strategy_registry.py` 는 8영역이다.

```python
# src/engine/strategy_manifest.py — 시제품(scratchpad/c23/pr1) 기준
from dataclasses import dataclass
from src.engine.strategies.bull_flag_breakout import BullFlagBreakoutStrategy
...   # 🔴 import 순서는 scheduler.py:34-40 원래 순서 그대로(모듈 로드 순서 보존)
from src.engine.strategy_base import StrategyBase

@dataclass(frozen=True)
class StrategyEntry:          # 기본값 없음 — 칸을 빠뜨리면 import 시 TypeError
    cls: type[StrategyBase]
    strategy_id: str
    name: str
    enabled: bool
    weight: float

STRATEGY_MANIFEST: tuple[StrategyEntry, ...] = (   # 순서 = 등록 = 평가 우선순위
    StrategyEntry(MomentumStrategy, "momentum", "상한가 모멘텀", True, 1.0),
    StrategyEntry(VolatilityBreakoutStrategy, "volatility_breakout", "변동성 돌파", False, 0.0),
    ... (현행 7행, 순서 그대로)
)
```

- **순환 import 없음**[실측]. 이 모듈을 import 하는 곳은 `scheduler.py` 하나다. 전략 모듈이 `scheduler` 를 부르는 곳은 함수 안 지연 import 한 곳뿐이다(`strategies/` 내 `from src.engine.scheduler import trading_scheduler`). `risk`·`strategy_base`·`status_exit_watch` 는 이 모듈을 import 하지 않는다(교차 검사는 테스트가 한다).
- `param_catalog.STRATEGY_IDS` 는 「순수 데이터 · src import 0」 설계라 리터럴을 유지한다. 교차 검사만 건다(§4.2).
- 전략 import 를 정적으로 둔다. 문자열 경로 + `importlib` 은 영향 인덱스(AST import 그래프)에서 사라진다.

### 2.2 `scheduler.py` 의 바뀌는 줄

| 자리 | 지금 | 바뀐 뒤 |
|---|---|---|
| `:34-40` | 전략 클래스 import 7줄 | `from src.engine.strategy_manifest import STRATEGY_MANIFEST` 1줄 |
| `:327-383` | 생성·등록 7블록(57줄, kojiro 주석 2줄 포함) | `for entry in STRATEGY_MANIFEST: self.registry.register(entry.cls(StrategyConfig(strategy_id=entry.strategy_id, name=entry.name, enabled=entry.enabled, weight=entry.weight)))` 7줄 |

- 줄 수: **3,786 → 3,730**(−56)[실측]. 상한 `<3,900` 의 여유가 114 에서 170 으로 늘어난다.
- `scheduler` 모듈 속성으로 전략 클래스를 패치하는 테스트는 **0건**이다(`grep "src.engine.scheduler.<X>Strategy"`)[실측].
- kojiro 주석(「다크런치 · `_SWING_POLL_STRATEGIES` 대상」)은 명부 행 옆으로 옮긴다.

### 2.3 시제품 확인 [실측]

`TradingScheduler().registry.all()` →
`[('momentum','상한가 모멘텀',True,1.0,'MomentumStrategy'), ('volatility_breakout','변동성 돌파',False,0.0,…), ('long_tail_volatility','롱테일 변동성 돌파',…), ('donchian_swing','20일 신고가 스윙',…), ('bull_flag_breakout','눌림목 돌파',…), ('vcp_breakout','변동성 수축 돌파',…), ('kojiro','고지로 대순환',False,0.0,'KojiroStrategy')]` — 현행과 같다.

---

## 3. 카드 #3 구체안 — 원형 선언과 파생

### 3.1 선언 자리: 명부 행 칸 (명세의 클래스 속성안 대신)

| 안 | 원형을 적는 곳 | 추가로 깨지는 AST 핀 [실측] | 새 전략에게 선택을 강제하나 |
|---|---|---|---|
| **명부 칸(권고)** | `StrategyEntry` 의 칸(기본값 없음) + import 시 검증 | **0** (scheduler 핀은 PR1 에서 이미 옮김) | 예 — 행을 쓰려면 칸을 다 채워야 한다(`TypeError`) |
| 클래스 속성(명세 원안) | 전략 7파일 `EVAL_DRIVER = …` + `StrategyBase.__init_subclass__` | 전략 7파일만 **64건**(11 테스트 파일 — cycle223·274·276·278·282·286·287·291·293·294·297) + `strategy_base.py` 1줄당 **12건** | 예 |

- 명부 칸으로도 「원형을 고르지 않으면 로드되지 않는다」(명세 카드 #3 ②)가 그대로 성립한다. 새 전략이 실제로 등록되는 길이 명부 하나뿐이기 때문이다.
- 클래스 속성이 필요해지는 경우는 하나다. **`StrategyBase` 코드가 런타임에 그 값을 읽어야 할 때**다(예: 평균회귀 `block_zero` 를 공통 게이트에서 처리). `strategy_base` → 명부 import 는 순환이라, 그때 그 칸 하나만 클래스 속성으로 내린다. 지금은 그런 소비자가 없다(3계명).

### 3.2 칸과 검증

```python
EvalDriver = Literal["tick_breakout", "tick_scan", "swing_poll"]
#   tick_breakout = 돌파 구독 그룹으로 후보를 구독하고 틱으로 평가(BFB·VCP·VB·LTV)
#   tick_scan     = 자기 스캔(scan_stocks) 결과로 구독하고 틱으로 평가(momentum)
#   swing_poll    = REST 폴로 평가, 틱 매수 평가 제외(donchian·kojiro)

@dataclass(frozen=True)
class StrategyEntry:
    ...(카드 #2 칸)
    eval_driver: EvalDriver
    breakout_rank: int | None          # tick_breakout 이면 필수, 아니면 None
    open_price_target: bool            # VB·LTV
    market_unit_policy: Literal["scale", "none"]

# import 시 검증 — raise(assert 아님, -O 에서도)
#  · strategy_id 중복 0 · breakout_rank 중복 0
#  · (eval_driver == "tick_breakout") ⇔ (breakout_rank is not None)
#  · open_price_target ⇒ eval_driver == "tick_breakout"
```

- `tick_scan` 을 따로 둔 이유: 지금 momentum 만 「틱 평가 + 돌파 구독 아님」이다. 「틱」 하나로 묶으면 **새 틱형 전략이 순위를 빠뜨려도 통과**한다. 그것이 §4.3 의 조용한 무매매 경로(cycle48)다. 세 값으로 나누면 순위 누락이 import 오류가 된다.
- 행 값(현행 그대로): momentum `tick_scan/None/False/none` · VB `tick_breakout/2/True/none` · LTV `tick_breakout/3/True/none` · donchian `swing_poll/None/False/scale` · BFB `tick_breakout/0/False/scale` · VCP `tick_breakout/1/False/scale` · kojiro `swing_poll/None/False/scale`.

### 3.3 파생 집합(명부 모듈에서 계산, 등록 순서 보존)

| 이름 | 식 | 값 [실측] | 대체하는 리터럴 |
|---|---|---|---|
| `SWING_POLL_IDS` | `eval_driver=="swing_poll"`, 명부 순서 | `('donchian_swing','kojiro')` | `scheduler.py:145`(이름 `_SWING_POLL_STRATEGIES` 는 유지 — 테스트 3곳이 그 이름으로 import 한다) |
| `BREAKOUT_IDS` | `breakout_rank is not None`, 명부 순서 | `(VB, LTV, BFB, VCP)` | `scheduler.py:2665-2666`(**순서가 현행과 같다** — 등록 순서) |
| `BREAKOUT_SUBSCRIBE_ORDER` | 같은 집합, `breakout_rank` 오름차순 | `(BFB, VCP, VB, LTV)` | `scheduler.py:1821-1826` |
| `OPEN_PRICE_TARGET_IDS` | `open_price_target`, 명부 순서 | `(VB, LTV)` | `scheduler.py:782` · `:1671` · `:2624` |

- 그대로 두는 `scheduler` 리터럴: `:1389` 익일 청산 · `:2038` 15:20 강제청산 · `:1529` LTV 분기 · `:1880-1918` 구독 출처 카운트. 각각 한 곳이거나(3계명) 로그 서식 계약이다. **`:2038`(VB·LTV)은 `OPEN_PRICE_TARGET_IDS` 와 값이 우연히 같지만 다른 사실**이다(당일 청산). 합치지 않는다.
- PR2 시제품의 `scheduler.py` diff = import 블록 + 위 6자리. 줄 수는 3,730 그대로다(import 블록 +6, 튜플 −6)[실측].

### 3.4 8영역·리터럴 정책 목록 — (가) / (나)

| | (가) 리터럴 유지 + 교차 검사 **(권고)** | (나) 파생 |
|---|---|---|
| `risk.py:88` diff | 0 | `frozenset({"donchian_swing","kojiro"})` → `frozenset(SWING_POLL_IDS)` + import 1줄 |
| 필요한 새 모듈 | 없음 | `risk` 가 명부(전략 7개 import)를 끌어오지 않게 **순수 역할 모듈**을 따로 둬야 한다. 그러면 전략 추가 때 고칠 곳이 명부 + 역할 모듈 둘이 된다 |
| 깨지는 테스트 [실측] | 0 | 21건 — 8영역 sha 핀 12 · `test_cycle276` c6_4c 승인표 1 · `test_cycle223g3` 형제 핀 3 · 새 파일 인지·트리 sha 4 · **`test_cycle273e` r10b** 1 |
| 약화해야 하는 가드 | 없음 | r10b 「`frozenset({...})` **소스 리터럴**이어야 한다」(cycle262 G-262-1 — 런타임 조작 우회 차단) |
| 승인 | 없음 | 8영역 승인 + sha 핀 절차 |
| 이후 폴형 전략 추가 시 | `risk.py:88` 한 줄(8영역 승인 1회) — 교차 검사가 **붉어서 알려 준다** | 0 |

- 같은 기준으로 그대로 두고 교차 검사만 거는 것: `strategy_base.py:82` `_MULTIDAY_STRATEGIES`(BFB 제외라 원형에서 파생되지 않는 독립 사실 — `strategies/CLAUDE.md` 의 「리터럴 정본」) · `status_exit_watch.py:75-79` `_GROUP` · `session.py:75-84` · `strategy_base.py:45`.
- `MARKET_UNIT_POLICY` 자리 = 명부 칸 `market_unit_policy`. 지금은 행위가 없다. `"block_zero"` 는 평균회귀가 연구를 통과해 등록될 때 그 사이클이 더한다. 런타임에 공통 코드가 읽어야 하면 §3.1 의 예외에 따라 클래스 속성으로 내린다.

---

## 4. sha 핀·AST 가드 비용

### 4.1 PR 별 붉어지는 테스트 [실측 — 전체 `tests/unit + tests/contract`, 기준 13,603 통과·실패 0]

| 묶음 | PR1(카드 #2) | PR2(카드 #3, PR1 위) | 클래스 속성안(참고) | `risk` (나)(참고) |
|---|---|---|---|---|
| `scheduler.py` 내용 sha 핀 | 10 (cycle274 c15_1 · 276 c5_1 · 278 C31 · 282 h3 · 290 g290_1 · 291 a1 · 292 g292_6b · 293 a1 · 294 a1 · 297 g2_9a) | 10 (같은 곳) | — | — |
| `scheduler.py` 줄 수 핀 | 11 (274 c16_1 · 276 c5_2 · 286 g1b · 287 s1c · 290 g290_1b · 291 a2 · 292 g292_6 · 293 a2 · 294 a2 · 297 g2_9b · `tests/unit/engine/test_cycle294_stage3.py`) | 11 | — | — |
| `src/` 트리 전체 sha(287 s1b) | 1 | 1 | 1 | 1 |
| 형제 핀 메타 가드(298 g298_7) | 1 (위 21곳을 다 옮기면 저절로 초록) | 1 | — | — |
| 새 파일 인지(287 s1d · 290 g290_3 · 291 a8) | 3 | 0 (PR1 에서 허용 목록에 넣음) | — | 3 |
| 소스 grep 테스트 | 1 — `test_kojiro_wiring.py:67` (`'strategy_id="kojiro"' in inspect.getsource(...)`) | 1 — `test_scanner_priority_order.py:439` (소스 문자열 위치로 BFB→VCP→VB→LTV 판정) | — | 1 (273e r10b) |
| 영향 인덱스 신선도 | 1 (재생성) | 0~1 | — | — |
| 전략 파일 · `strategy_base` sha | 0 | 0 | **64 + 12** | — |
| 8영역 sha·승인표 | 0 | 0 | — | 16 |
| **합계** | **28** | **24~25** | 76+ | 21 |

### 4.2 재핀 절차(PR 마다)

1. 구현 → `pytest tests/unit/ast/test_cycle298_ast_scan_loop_callsites.py::test_g298_7_sibling_scheduler_pins_agree_with_the_file`. 실패 메시지가 낡은 sha·줄 수 자리를 **이름으로 전부** 꼽는다.
2. 옛 sha → 새 sha 를 `tests/` 전체에서 한 번에 바꾼다(sha 문자열은 유일하다). 줄 수 `3786` → 새 값도 같은 방식이다(`_SCHEDULER_LINES = …`·`lines == …`·`n == …` 세 모양). 단언 메시지의 계보 문자열(「… → cycle369 재핀 …」)에 「→ 카드#2 재핀 3,730」 을 덧붙인다(cycle292 선례).
3. `tests/unit/engine/test_cycle294_stage3.py:1478`(`assert lines == 3786`)을 함께 고친다. G-298-7 이 `tests/unit/engine` 도 훑고 이 모양을 잡는다[코드].
4. PR1 만: 새 파일 인지 가드 3곳의 허용 목록에 `src/engine/strategy_manifest.py` 를 넣는다. `287 s1b` 트리 sha 를 다시 잰다.
5. 소스 grep 테스트는 **약화가 아니라 행위 단언으로 바꾼다** — `test_kojiro_wiring` → `[e.strategy_id for e in STRATEGY_MANIFEST]` 에 kojiro 가 있고 `TradingScheduler().registry.get("kojiro")` 가 `KojiroStrategy` 다. `test_scanner_priority_order` → 4전략 스텁 후보로 `_collect_breakout_tickers()` 를 실제로 불러 병합 순서를 단언한다(§5 골든과 같은 방식).
6. `python tools/test_impact/build_index.py` → 전체 스위트 재실행(메모리 「고친 뒤 전체 스위트 재실행」).

### 4.3 핀 이동을 줄이는 순서

- **PR0(테스트만)** 은 핀을 하나도 건드리지 않는다. 골든과 교차 검사의 뼈대를 먼저 들여, PR1·PR2 가 「골든 초록 + 핀만 이동」으로 끝나게 한다.
- PR1·PR2 를 한 PR 로 합치면 `scheduler` 재핀이 1회로 준다(22곳 × 1). 대신 「PR 하나 = 의도 하나」(5계명)와 되돌리기 단위를 잃는다. 재핀은 sed 수준의 기계 작업(§4.2-2)이라 **나눠서 두 번 하는 쪽을 권한다**.
- 전략 파일·`strategy_base`·8영역은 세 PR 모두 **무접촉**이다. 그래서 「전략 7파일 sha」 계열 핀(수십 건)은 한 건도 움직이지 않는다.

---

## 5. 행위 동일성 증명 — 차분 테스트 설계 (PR0)

### 5.1 골든 생성(현행 코드에서 한 번)

`tools/test_fixtures/gen_strategy_wiring_golden.py` → `tests/fixtures/strategy_wiring_golden.json`. 생성 시점의 `scheduler.py` sha·커밋을 파일에 함께 적는다. 담는 것은 넷이다.

1. **등록 표** — `TradingScheduler().registry.all()` 의 `(id, name, enabled, weight, 클래스명)` 7행, 순서 포함.
2. **상수 표** — `scheduler._SWING_POLL_STRATEGIES` · `risk._TICK_BUY_EVAL_SKIP_STRATEGIES` · `risk._PRE_MARKET_EXIT_EVAL_STRATEGIES` · `strategy_base.Position._MULTIDAY_STRATEGIES` · `strategy_base._ALWAYS_STATUS_GATE_CANDIDATE_SIDS` · `status_exit_watch._GROUP` · `session._DEFAULT_TRADABLE_BOARDS` 키 · `param_catalog.STRATEGY_IDS`·`_TURTLE4`·`_VBLTV` · `funnel_capture._ORDER`.
3. **반복 대상 표(AST)** — `scheduler.py` 의 모든 `for <이름> in <식>` 중, 식을 평가하면 전략 id 튜플이 되는 것(튜플 리터럴이거나 모듈 이름). 키는 `(함수 qualname, 그 함수 안 몇 번째)` 이고 값은 평가한 튜플이다. **줄 번호를 쓰지 않아** 줄이 밀려도 안정적이다. 지금 **12자리**가 잡힌다(`:782 :788 :1389 :1671 :1821 :1843 :2038 :2309 :2624 :2665 :2763 :2887`)[실측]. 거대한 async 루프 안의 자리(`:782`)도 실행 없이 덮는다.
4. **행위 추적(켜짐 조합 128가지)** — 새 `TradingScheduler` 에서 7전략의 `config.enabled` 를 비트마스크로 켜고 끈다. 각 전략의 `get_scanned_tickers` 는 전략마다 다른 가짜 종목을 돌려준다. 그 상태로 다음을 기록한다.
   - `_collect_breakout_tickers()` 결과 목록(순서 포함) · `_collect_swing_tickers()` · `_collect_presubscribe_tickers()`(집합)
   - `_reprepare_breakout_if_empty()`(후보를 비운 상태): `funnel_capture.live_prepare_one` 을 패치해 **부른 순서**
   - `_confirm_breakout_open_prices_if_pending()`: `_targets` 를 채우고 `_confirm_breakout_open_prices` 를 패치해 순회한 sid 순서
   - `registry.enabled()` 의 id 순서(= `risk.on_tick` 평가 순서)

### 5.2 단언

- `test_strategy_wiring_golden.py` 가 같은 값을 다시 만들어 골든과 **같은지** 본다. PR1·PR2 에서 이 파일은 고치지 않는다. **골든을 다시 생성하는 것은 행위 변경 사이클에서만 한다.**
- 돌연변이 확인(PR0 에서 1회, 결과를 PR 설명에 적는다):
  - `breakout_rank` BFB↔VCP 교환 → 4번 붉음
  - kojiro `swing_poll` → `tick_breakout` → 2·3·4번 붉음
  - 등록 순서에서 VB·LTV 교환 → 1·4번 붉음
  - `:2038` 을 `OPEN_PRICE_TARGET_IDS` 로 바꿔도 값이 같아 **초록**이다. 이것은 골든의 한계다. §3.3 의 「다른 사실은 합치지 않는다」는 리뷰 규약으로 지킨다.

### 5.3 교차 검사 (PR2, 테스트만)

| 단언 | 지키는 것 |
|---|---|
| `set(census.STRATEGY_IDS) == {e.strategy_id for e in STRATEGY_MANIFEST}` | 파일만 두고 명부에 없는 전략(또는 반대) — 실패 메시지 「명부에 행을 추가하라」 |
| `param_catalog.STRATEGY_IDS == tuple(명부 순서)` | 카탈로그 순서 = 등록 순서 |
| `risk._TICK_BUY_EVAL_SKIP_STRATEGIES == frozenset(SWING_POLL_IDS)` | (가) — 폴형 추가 때 `risk.py:88` 누락을 붉혀서 알림 |
| `status_exit_watch._GROUP`: 그룹 1 = `OPEN_PRICE_TARGET_IDS` · 그룹 2 = 돌파 − 시가 · 그룹 3 = `SWING_POLL_IDS` · `tick_scan` 은 키 없음 | §4.2 「폴형」·「틱 구독형」 사실의 셋째 자리 |
| `Position._MULTIDAY_STRATEGIES` · `_ALWAYS_STATUS_GATE_CANDIDATE_SIDS` · `session._DEFAULT_TRADABLE_BOARDS` 키 ⊆ 명부 id | 오탈자·제거된 전략의 잔재 |
| `{scale}` == `param_catalog._TURTLE4` == `_market_unit_sizing` 을 부르는 파일 == `DEFAULT_PARAMS` 에 `market_unit_mode` 가 있는 파일 == cycle382 `TURTLE_FILES` | `MARKET_UNIT_POLICY` 선언이 거짓이 되지 않게 |
| `param_catalog._VBLTV == OPEN_PRICE_TARGET_IDS`(집합) | 시가 목표가 키의 적용 범위 |

---

## 6. 위험·되돌리기

| 위험 | 등급 | 대응 |
|---|---|---|
| 모듈 로드 순서가 바뀌어 import 부작용이 달라진다 | LOW | 명부의 import 순서를 `scheduler.py:34-40` 원래 순서 그대로 둔다. 과거의 VCP import 부작용 패턴은 이미 리터럴로 없앴다(`strategy_base.py:78-80` 주석) |
| 기동 시 순환 import | LOW | 시제품에서 `import src.engine.scheduler` · `TradingScheduler()` 성공[실측]. CI 전체 스위트가 같은 경로를 탄다 |
| 파생 순서가 어긋나 구독 우선순위·폴 순차성이 바뀐다 | HIGH(영향) / LOW(확률) | §5 골든이 순서까지 고정한다. 폴 순차성(같은 종목 이중 매수 차단)은 `_SWING_POLL_STRATEGIES` 값과 순서가 같으면 그대로다 |
| 선언 칸이 실제 동작과 갈라진다(특히 `market_unit_policy` — 행위 없는 선언) | MEDIUM | §5.3 교차 검사 |
| 「같은 값, 다른 사실」을 파생으로 합친다(`:2038`) | MEDIUM | 이 설계는 합치지 않는다. 골든이 못 잡으므로 리뷰 항목으로 둔다 |
| 재핀 누락으로 CI 가 붉다 | LOW | G-298-7 이 자리를 전부 꼽는다. push 전 전체 스위트 |

- **되돌리기**: PR 마다 커밋 1개 → `git revert` 1회. DB·설정·스키마 무변경이다. 배포 모드는 `src/` 변경이라 **full(backend 재시작)** 이다. 그래서 배포는 장외 창(15:30~16:00 · 21:35~익일 07:45 · 주말)에만 한다. 20:00~21:35 는 피한다. 보유가 있으면 장중 push 를 하지 않는다(D6). 행위 동일이라 되돌릴 일은 기동 실패(import 오류) 정도다. 그 경우 CI 가 먼저 막는다.
- 카드 #3 은 명세상 HIGH 라 domain-expert 행위 영향 평가가 선행 조건이다. 이 설계에서는 행위 차이가 0 이고 골든이 그것을 증명한다. 그래서 자문 범위는 좁다 — ① `tick_breakout`/`tick_scan`/`swing_poll` 세 원형 이름과 경계가 맞는가 ② `breakout_rank` 를 「구독 우선순위」 하나로 정의해도 되는가(2026-08-08 사용자 결정 BFB·VCP head).

---

## 7. 결정 필요 항목

1. **원형 선언 자리** — 명부 칸(권고, 추가 핀 0) / 명세 원안 클래스 속성(전략 7파일 + `strategy_base`, 핀 76건 이상). 명세에서 벗어나는 부분이라 확인을 받는다.
2. **`risk.py:88`** — (가) 리터럴 + 교차 검사(권고) / (나) 파생(8영역 승인 + r10b 가드 약화).
3. **명부 = 파일 일치 단언** — 전략 디렉터리에 파일만 두고 등록하지 않은 상태를 붉게 할지. 권고는 「붉게」다. 재현 실험은 `tools/replay/` 에 둔다(명세 §7).
4. **PR1·PR2 분리** — 분리(권고, 재핀 2회) / 합침(재핀 1회, 되돌리기 단위 상실).
5. **PR2 도메인 확인** — §6 의 좁은 범위 두 질문으로 할지.
