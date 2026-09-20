"""cycle287 Red — 범위 가드: **세 파일 외 프로덕션 diff 0** + 불변 봉인 + 구조 계약.

정본 = cycle287 도메인 자문 §9-J·§제약 (2026-09-12) + 브리프 제약.

## 이 사이클의 제1 계약

**프로덕션 코드는 딱 세 파일만 바뀐다.**

- `src/models/order.py`      (K1 — `OrderDivision` 에 `41`/`44` 추가, sha 핀 **0곳**)
- `src/engine/order_engine.py` (R·K — 라우팅 + 애프터 변환 + 봉인, **8영역 승인**)
- `src/api/order.py`         (§S7 — **docstring 만**, 본문 byte 동일, **8영역 승인**)

그 주장을 사람의 선언이 아니라 **sha** 로 증명한다(S1/S2). 세 파일은 정당하게 바뀌므로
핀 목록에서 **의도적으로 빠져 있고**(S1d), 대신 손대지 않기로 한 구간은 세그먼트 sha 로
따로 잠근다(S3).

## ⚠️ 브리프가 자문 §9-F 를 덮는다 — 전략 7파일은 diff 0

자문 §9-F 는 두 신규 파라미터(`order_exchange_clock_mode`·`after_market_exit_division`)를
7 전략 `DEFAULT_PARAMS` 에 명시하라고 했지만, **브리프 제약이 전략 7파일·`strategy_base.py`
를 diff 0 으로 못 박는다.** 그래서 이 사이클의 계약은:

* cycle287 배포 시점에는 두 키가 **어느 전략 `DEFAULT_PARAMS` 에도 없었다**(S5).
* 기본값은 `order_engine` 의 **모듈 상수**가 정본이고, 등재 전 키 부재 = `enforce` / `44` 였다(S5).
* ✅ **정정(cycle290, 2026-09-13)** — 장중 킬스위치가 이제 **있다.** cycle287 배포
  당일 실측 = `validate_params` 가 `key not in current_params or spec is None` 을
  `unknown_key` 로 만들고 라우트가 422 + all-or-nothing 이었다(그래서 종전 이 문서는
  그런 킬스위치가 없다고 적었다). cycle290 이 두 키를 **7 전략 전부**의
  `DEFAULT_PARAMS` + `param_catalog` 에 코드 상수와 같은 값으로 등재해 그 PUT 통로를
  열었다(매매 행위는 등재 자체로 변경 0). `test_s5b`(아래) 는 이제 **존재** 를,
  `test_s7`(아래) 은 이제 **PUT 200 + accepted** 를 단언한다.
* `DEFAULT_PARAMS`·`param_catalog` 등재와 화면 문구(자문 §3·§9-K)는 **cycle290** 이며,
  그 사이클이 S5·S7 을 함께 갱신했다(이 파일).

## 왜 `ast.dump` 의 sha 를 핀하지 않는가

3.12(CI)/3.13(로컬)의 `ast.dump` 출력이 달라 로컬 초록·CI 실패가 난다
(cycle256 G-250-5 · cycle259 S4a). 무변경 핀은 **파일 내용 sha256** 또는
`ast.get_source_segment`/원문 부분문자열의 sha256 으로만 잰다.

## 왜 `git grep`/`git ls-files`/bare `git diff HEAD` 를 쓰지 않는가

추적 파일만 보므로 Green 이 만든 **미추적** 파일을 로컬에서 못 보고 CI 에서만 잡는다
(cycle259 S4b). bare `git diff HEAD` 는 커밋 직후 공허해지고 다음 편집에서 무조건 RED 가
된다(cycle240 A11b · cycle252 G-252-5b). 스캔은 `Path(...).rglob("*.py")` + AST.

## ⚠️ 사이클 한정 — 커밋 후 갱신/삭제 의무

`_BASE_SHA` · `_SRC_TREE_DIGEST` · `_FROZEN_SEGMENTS` 는 base `a42f519` 의 blob 을 고정한
것이라 cycle287 의 무접촉 증거로만 유효하다. 그 파일들을 **정당하게** 바꾸는 다음 사이클이
이 dict 를 갱신하거나 이 테스트를 삭제한다(고아 가드 방지).

⚠️ dict 이름을 `*_CONTENT_SHA` 로 **짓지 않았다** — `test_cycle223g3_ast_guard_sees_staged.py`
의 `test_g3_9a` 가 모듈 레벨 `*_CONTENT_SHA` dict 를 가진 테스트 파일 집합을
`_PIN_GUARD_FILES`(4개)로 고정한다. cycle274/278/282/286 관례대로 `_BASE_SHA` 를 쓴다.

## Green 이 함께 해야 하는 핀 갱신 (이 파일 밖, 자문 §9-J)

`order_engine.py` 내용 sha **7곳** — 자매 4곳(`test_cycle222a3`:469 · `test_cycle223`:452 ·
`test_cycle223f`:364 · `test_cycle226`:1157, `test_g3_9b` 계약상 **넷 전부 같은 값**) +
무조건 3곳(`test_cycle274`:563 · `test_cycle278`:198 · `test_cycle282`:379).
`src/api/order.py` **9곳** — 무조건 5곳(`test_cycle274`:570 · `test_cycle276`:346 ·
`test_cycle278`:205 · `test_cycle282`:388 · `test_cycle286`:82) + **자매 4곳에 신규 등록**
(현재 dict 에 없어 `unexpected` 로 붉어진다).  `src/models/order.py` 는 **0곳**.
"""

from __future__ import annotations

import ast
import hashlib
import os
from datetime import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]

_ORDER_ENGINE_REL = "src/engine/order_engine.py"
_API_ORDER_REL = "src/api/order.py"
_MODELS_ORDER_REL = "src/models/order.py"

#: 이 사이클이 정당하게 바꾸는 세 파일 — 핀 목록에서 의도적으로 제외한다.
_CHANGED = (_MODELS_ORDER_REL, _ORDER_ENGINE_REL, _API_ORDER_REL)

#: base `a42f519` blob 의 파일 내용 sha256. **세 변경 파일은 없다**(S1d).
_BASE_SHA = {
    # 8영역 — 엔진 4파일 (order_engine 은 승인된 변경 대상이라 제외)
    "src/engine/risk.py":
        "e8614235cc0bea638f8c349b2f6910c94f5f9a5b849f5d65bef0583f959d81c9",
    "src/engine/session.py":
        "36257d86af1c26a868dc991a74a9eb139c98a9358d739d24600f5be2f9c5666c",
    # 🔁 cycle302(2026-09-18) 재핀 — 사용자 승인 일봉 backfill **대상** 확대
    #    (분기에서 지수 소속 판정 제거 · `vcp_universe_tickers` 집합 소멸.
    #    목표 깊이 상수는 불변). 값만 옮긴다 — 단언은 그대로다.
    #    구 값은 cycle299 기준선(3b7366cc…)이다.
    "src/engine/scanner.py":
        "95cbb103a38821bb3b68d267a3662094b192fa55ad6071fa8dc4a63726e1c942",
    "src/engine/strategy_registry.py":
        "d794696e54ffdc36efa6df917879d780e86bc1f373bb3b5d8dcbc0beac8cef8b",
    # 8영역 — realtime 전부
    "src/realtime/__init__.py":
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "src/realtime/handler.py":
        "37b1755210c83cdb2a462e6a37f919b326f8b48bee73d924adcc277d770a8d17",
    "src/realtime/websocket.py":
        "d4c443bde2ed7aeafba3e9471db0ca4efc15a654610555435145a9b305150c5b",
    "src/realtime/websocket_pool.py":
        "8b02442bcf5f558d6f7095b47d2016f004e3746e07ddc91dae8768b1dd46a10d",
    # 8영역 — auth 전부
    "src/auth/__init__.py":
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "src/auth/hashkey.py":
        "7c2aacc703839bdc274b463ee48777006504d70e4d59a1e57120ac5b612396d2",
    # 🔁 cycle296(2026-09-17) 재핀 — 사용자 승인 `issue()` 매니저 단위 in-flight 합류(`src/auth/**`). 같은 값을 10곳 동시 갱신했다.
    "src/auth/token.py":
        "4125c271b4147e59922f4f000e523429fb4bbef37058dc754fd92b9475ec58f1",
    # 8영역은 아니지만 이 사이클이 무접촉을 약속한 파일
    "src/engine/strategy_base.py":
        "869dc20ca561adc561a9ebe9fdb5fe5a3e097f7ec176fdf274d577d509de9252",
    # 시각 표의 **유일 정본** — cycle287 은 읽기만 했다. 바꾸면 픽스처 동기 사슬
    # (`tools/test_fixtures/gen_market_state_fixture.py` + 프론트/E2E 픽스처 2)이
    # 통째로 딸려 오고, cycle282 `test_i1/i2/i3` 가 즉시 RED 다(실증: cycle289 가
    # 이 파일을 건드리자 정확히 그 둘이 붉어져 생성기를 다시 돌렸다).
    # ⚠️ 핀 값은 **cycle287b**(SOR 폐기 각주) 기준선이다 — cycle287 이
    # 이 파일을 바꿨다는 뜻이 아니다. cycle287 배포분(`7dc6dae`)에서 이 파일의 sha 는
    # `7594ccadec61aacc6a47b0ef7be46d96d9a82912235622edd790694209d0b48c` 였다.
    "src/engine/market_state.py":
        "7cef2efeb55a7184391ac2cc447c90102fdd7ba507fd6e3834d24a8ad9ce006b",
    # TTL 축 — 호출부가 넘기는 **인자의 의미**만 바꾸고 이 파일은 손대지 않는다(K9-g/h).
    "src/engine/sell_rejection.py":
        "6df3a6c697019f0d0a35e4870d0fc115171d1504f11fb3e43ae16aea4883fdec",
    # 거부 분류기 — 키워드 집합을 늘리지 않는다(미분류 봉인이 정면 대응이다).
    "src/api/balance.py":
        "d8f3da874b3e2623695935d768cf5a502a3756e3425c41185e42576c27f6aa35",
    # 전략 7파일 (+ 패키지) — cycle287 당시 "전원 diff 0" 이었으나 **cycle290(킬스위치
    # 등재) 이 정당하게 갱신**했다 — `DEFAULT_PARAMS` 말미에 `order_exchange_clock_mode`
    # `after_market_exit_division` 2키 추가뿐, 그 외 한 글자도 안 바뀌었다는 증거는
    # `test_cycle290_ast_scope.py::test_g290_2`(세그먼트 sha 28핀) 가 별도로 잠근다.
    # 구 값(cycle287 기준선)은 이 dict 의 git 이력에 남는다.
    "src/engine/strategies/__init__.py":
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "src/engine/strategies/bull_flag_breakout.py":
        "0feb3b629bab5ad08ad589315ca12e76b57a73950b948570a78dfe84ba792595",
    "src/engine/strategies/donchian_swing.py":
        "cc57e5673f9982aca97f61677084e040171fff307483fedf10459b567a4679e3",
    "src/engine/strategies/kojiro.py":
        "9477790e9d20eb6d17f36fc7586ada77ac5e2e4b0136a334888244afdb7e9cbc",
    "src/engine/strategies/long_tail_volatility.py":
        "51b50560a1240df3fc6085da7253438605079d7d453ff3e77a806e814473be25",
    "src/engine/strategies/momentum.py":
        "50d5c0b9a232d6110f6b85fc524569853f2b8edffe2fd44adc24289800b95ae2",
    "src/engine/strategies/vcp_breakout.py":
        "5b324b34335f922f82b848ae2313e08660bde75c02d12432867ed224e9709228",
    "src/engine/strategies/volatility_breakout.py":
        "d13efaa4a9424e2822b5476ce159987d2a5192a4bca30af3f1a0cae9c3ffcabc",
}

#: `src/**/*.py` 전수(세 변경 파일 제외)의 (경로, 내용sha) 누적 digest.
#: 명시 dict 가 못 보는 나머지 ~120 파일의 **diff 0** 을 한 줄로 잠근다 —
#: `routes/`·`services/`·`db/`·`middleware/`·`workers/` 가 조용히 바뀌는 것도 접촉이다.
#: ⚠️ 값은 **cycle285 적대 검증 반영**(야간작업 현황 라우트 `src/routes/market_ops.py`
#: 수정 — 휴장일 오탐·overwritten 오분류·evidence-time 게이트·is_provisional 필터
#: 시정) 기준선이다 — cycle287 이 이 수를 바꿨다는 뜻이 아니다. 파일 수는 148 로
#: **불변**(신규 파일 0 — market_ops.py 는 기존 파일을 편집만 했다). cycle287b
#: 배포분에서는 147 이었다(신규 파일 없음).
#: ⚠️ **cycle293(시세 채널 리졸버 2단계, 2026-09-14) 기준선으로 갱신** — 파일 수가
#: 149 → **150**(신규 킬스위치 leaf `src/engine/tick_channel_mode.py` 1개). digest 에는
#: 그 leaf + 이 사이클이 정당하게 바꾼 파일들(`scanner.py`·`websocket.py`·
#: `websocket_pool.py`·`risk.py`·`no_feed_registry.py`·`stale_*`·`db/stock_master.py`·
#: `db/system_config.py`·`routes/realtime.py`)이 포함돼 재계산했다. `_CHANGED` 3파일
#: (`models/order.py`·`order_engine.py`·`api/order.py`)은 digest 에서 제외되고
#: `_BASE_SHA`/자매 핀이 따로 잡는다. 검사 면적은 여전히 `src/**/*.py` 전수다.
#: ⚠️ **cycle294(시세 채널 3단계 · 시각축 전환, 2026-09-14) 기준선으로 갱신** —
#: 파일 수가 150 → **152**(신규 leaf 2개: `tick_channel_clock.py` 시각축 판정 ·
#: `tick_channel_switch.py` 전환/자동 원복. 둘 다 8영역 **밖**이고 사용자 승인
#: 범위 안이다). digest 에는 그 둘 + 이 사이클이 정당하게 바꾼 파일들
#: (`scanner.py`·`risk.py`·`websocket.py`·`websocket_pool.py`·`stale_watcher_core.py`·
#: `tick_channel_mode.py`·`routes/realtime.py`)이 포함돼 재계산했다.
#: ⚠️ **cycle296+297 통합(2026-09-17) 기준선으로 갱신** — 파일 수가 152 → **153**.
#: 신규 leaf 1 = `src/engine/llm_retrospective.py`(cycle297 — 회고 조인·집계 순수
#: 함수, `src.*` import 0). cycle296 은 신규 파일 **0** — 기존 `auth/token.py`·
#: `engine/quote_token_refresh.py` 편집만이다.
_SRC_TREE_FILES = 154
#: ⚠️ 값은 **cycle285 적대 검증 반영** 기준선이다. 그 직전(초판 cycle285 배포)
#: digest 는 `97483c5114a1d00dc8f7ca7c1ed08e1b3dc1d0b585065b14176dc227da9bed8c` 였다.
#: cycle287b 배포분의 digest 는
#: `7d122ab634df31ce986770c6390a52b245f68d2e693835880d608dff64e73b6a` 였다.
#: 기준선은 옮겨도 단언은 그대로다 — 다음 사이클이 `src/` 를 조용히 바꾸면 여전히 붉어진다.
#: ⚠️ **cycle290(킬스위치 등재, 2026-09-13) 기준선으로 갱신** — 전략 7파일의
#: `DEFAULT_PARAMS` 에 키 2개가 추가돼 그 파일들의 sha 가 바뀌었고, 이 digest 는 그
#: sha 를 포함해 재계산한 것이다. 파일 수는 148 로 불변(신규 파일 0).
#: cycle290 Green 직후 값은 `b3997180dbe258f7816e51725d12b2de88d9234f7f9e3405008f12a5a3a70bb0`
#: 였다 — **cycle290 적대 검증 반영**(help 텍스트 정직화: 전제 조건·전략별 스위치·
#: 카나리아 과장 정정을 `param_catalog.py` 에 추가)으로 `param_catalog.py` 내용이
#: 다시 바뀌어 이 값으로 갱신한다. 전략 7파일 세그먼트 sha(`_DEFAULT_PARAMS_SHA`,
#: `test_cycle278_ast_catalog_guards.py`)는 무접촉 — 움직인 것은 `param_catalog.py`
#: 하나뿐이다.
#: ⚠️ **cycle292(`_subscribe_market_operation_tickers` leaf 추출, 2026-09-14) 기준선으로
#: 갱신** — 파일 수가 148 → **149** 로 처음 늘었다(신규 leaf
#: `src/engine/market_op_subscribe.py` 1개). `scheduler.py` 는 176줄이 빠지고 5줄 위임
#: wrapper 가 들어와 sha 가 바뀌었으며 digest 는 그 둘을 포함해 재계산했다. 행위 변경 0
#: (본체 라인 단위 동일 — `self.` → `scheduler.` 6곳 + dedent 뿐). 검사 면적은 그대로
#: `src/**/*.py` 전수다 — **좁아지지 않았다**.
#: cycle290 적대 검증 반영분 값은
#: `d491c518cb200717246577be3bcfd904c854f9a6c9fe625e28f639666477a277` 였다.
#: ⚠️ **cycle292 적대 검증 반영으로 한 번 더 갱신** — `market_operation_monitor.py` 의
#: `get_market_op_active_tickers()` docstring 이 적은 소비처 2개가 **둘 다 거짓**임이
#: 확인돼(프로덕션 호출자 0건 · 델타는 `scheduler._market_op_subs` 로 잰다) 정직화했다.
#: **docstring 1곳뿐 — 코드(AST) 불변**. 그 직전(추출 직후) 값은
#: `94ff236b51ad636e914f9ab271d87306d187119c5b1a291a8c8d2e918fa7c7c6` 였다.
#: ⚠️ cycle292 배포분 값은
#: `78c0618e60cefe842b9108f93e1e8a50fcce07a228f87a368a85d792c3bcb3a5` 였다
#: (cycle293 기준선으로 갱신 — 위 `_SRC_TREE_FILES` 주석 참조).
#: ⚠️ cycle293 Green(적대 검증 시정) 직전 값은
#: `b7731d72a1e3fd3587d805459b2bfbdb80f0c77784b2daaf75d73bd275116308` 였다.
#: ⚠️ cycle293 착지(= cycle294 착수) 값은
#: `61401aa6dbf4fc2d816a30454a9d6501259152bd8d5d29e09e33a4b9996d19cd` 였다.
#: ⚠️ **cycle295(갭 홀드 제거 + 15:30~16:00 주문 컷, 2026-09-16) 기준선으로 갱신.**
#: 움직인 파일 6 = `engine/tick_channel_clock.py`·`engine/tick_channel_mode.py`(A축 —
#: 갭 판정·다이얼 삭제) · `db/system_config.py`(A축 getter/setter 삭제 + C축 bool 정규화)
#: · `routes/realtime.py`(A축 라우트 표면) · `engine/order_engine.py`(B·D축 — 컷 게이트
#: + 손절 잔여 재주문 매핑) · `routes/trading.py`(§9-Q3 ② manual-sell 컷 **면제** 경고).
#: 그중 `order_engine.py` 만 이 가드의 **예외 3파일**에 이미 들어 있어 digest 에는
#: 나머지 5개의 변경이 반영됐다. 파일 수는 **152 로 불변**(신규 파일 0 — 이 사이클의
#: 신규는 테스트뿐이다). `engine/tick_channel_switch.py` 는 docstring 1곳만 바뀌었다
#: (전환 창 3→1 서술 정정, AST 불변).
#: cycle294 착지(= cycle295 착수) 값은
#: `7b496e80aa6dbb3e3b132367cb3c356c2bb93ee1136486b0af6ddf4cfe20b767` 였다.
#: ⚠️ **cycle296(보조 토큰 재발급 in-flight 합류 · T=20:45 · 관측 5키) +
#: cycle297(LLM 매수평가 7전략 확대 + 회고 라우트) 통합 기준선으로 갱신, 2026-09-17.**
#: 움직인 파일 12 = **cycle296 2** (`auth/token.py` — `issue()` 매니저 단위 합류
#: Future · `engine/quote_token_refresh.py` — T 19:00→20:45 + `elapsed_s`/
#: `window_issues_total`) + **cycle297 10** (`engine/llm_retrospective.py` 신규 ·
#: `engine/llm_features.py` · `engine/llm_buy_gate.py` · `engine/param_catalog.py` ·
#: `routes/llm_evaluations.py` · 전략 5파일 `momentum`/`donchian_swing`/
#: `bull_flag_breakout`/`vcp_breakout`/`kojiro`).
#: ⚠️ 전략 5파일은 `DEFAULT_PARAMS` 리터럴 말미에 LLM shadow 4키를 더한 것뿐이고
#: `check_buy_signal`/`check_exit_signal`/`calc_buy_quantity`/`prepare` 28세그먼트
#: sha 는 cycle290 핀과 동일하다(`test_cycle297_ast_scope.py::test_g2_3b` 가 기계 증명).
#: 8영역 중 움직인 것은 `auth/token.py` **하나뿐**이다(사용자 승인).
#: cycle295 착지(= cycle296/297 착수) 값은
#: `d4d6622a112829230c2d342b70a99b99153fa465527a38d1e9cd78ddd056c685` 였다.
#: ⚠️ **NUMERIC 직렬화 시정 기준선으로 갱신, 2026-09-17.** 움직인 파일 2 =
#: `routes/history.py`(`get_trades` 의 `SELECT t.*` raw 행에서 `Decimal` → `float`
#: 사영) + `routes/performance.py`(`latest_asset` 에 빠져 있던 `float()`).
#: 고친 것 = PG NUMERIC 을 asyncpg 가 `Decimal` 로 주고 pydantic v2 가 JSON
#: **문자열**로 직렬화해, 거래내역의 '가격'·'매매손익' 두 열이 전 행 `-` 로
#: 보이고(사용자 신고) 대시보드 '최근 자산' 이 천단위 구분 없이 렌더되던 결함이다
#: (2026-07-16 RDS 이전 `2c44b44` 이후 상시). **8영역 무접촉 · 매매 행위 변경 0**
#: — 두 라우트 모두 읽기 전용이고 값의 *타입*만 계약(`number`)에 맞춘다.
#: 회귀 가드 = `tests/contract/test_routes_history.py::
#: test_history_numeric_fields_are_json_numbers` + `test_routes_balance_perf.py::
#: test_performance_summary_latest_asset_is_json_number`(둘 다 스텁을 `Decimal` 로
#: 바꿔 프로덕션을 재현한다 — 종전 스텁은 python int 라 Decimal 을 한 번도
#: 태우지 않았고 그래서 이 결함을 못 잡았다).
#: cycle296/297 착지 값은
#: `c1df70acc5c048cb23330cc337095b21bd7e3270063b3772481f2412d7ae7f3e` 였다.
#: ⚠️ **cycle298(재기동 시 시세 구독 공백 시정, 2026-09-17) 기준선으로 갱신.**
#: 움직인 파일 1 = `engine/scheduler.py`(`_scan_loop` 첫 회차 지연을 호출부가
#: 정하도록 시그니처 확장 + 15:30 POST_NXT 전환 호출부 `first_delay=0` 배정 +
#: 관측 마커 1행). 파일 수는 **153 으로 불변**(신규 파일 0). NUMERIC 직렬화
#: 시정 착지 값은 `06fef48ad7b3094b4a1041b23a6a627b191931bd0fd72b74a76d0b6413261e16`
#: 였다.
#: ⚠️ **cycle298 후속(2026-09-17) — `first_delay` 상한 결손 Green 1건으로 재갱신.**
#: `_scan_loop` 의 `min(SCAN_INTERVAL, max(0.0, float(first_delay)))` 한 줄 치환뿐
#: (라인 수 불변 3,785). 파일 수 **153 불변**(신규 파일 0).
#: ⚠️ **cycle299(일봉 보유·backfill 창 확대, 2026-09-17) 기준선으로 갱신.**
#: 움직인 파일 3 = `engine/scanner.py`(`_DAILY_LOAD_VCP_BACKFILL_DAYS` 120 → 220,
#: **8영역 · 사용자 명시 승인** — 위 `_BASE_SHA` 의 재핀 주석과 자매 4곳이 같은 값을
#: 든다) · `db/stock_master_daily.py`(`DAILY_RETENTION_DAYS` 230 → 390) ·
#: `api/condition.py`(`fetch_daily_candles_backfill` docstring — 기본값 120 이
#: 호출되지 않는 폴백임과 1회 backfill 부족분을 명시, **AST 불변**).
#: ③ 사용자 요청("데이터 지금 바로 채울 수는 없어?")으로 `api/condition.py` 의 깊이 환산에
#: 휴일 보정을 비례로 얹어 1회 backfill 이 target 을 넘게 했다(225 영업일 목표 → 실도달
#: 232). 🔴 stride(윈도우 간격)는 7/5 그대로다 — 키우면 윈도우 사이에 구멍이 생긴다.
#: `engine/scanner.py` 는 ③ 에서 무접촉이라 8영역 sha 핀 13곳은 ② 의 값을 유지한다.
#: ④ 커밋 전 감사에서 운영자에게 보이는 낡은 인과 2건을 고쳤다 — `engine/param_catalog.py` 의
#: `donchian_period`·`volume_period` help(상한의 근거는 retention 이 아니라 100행 읽기 클램프다) ·
#: `engine/strategies/vcp_breakout.py` 의 100일 cap 근거 주석(적재 깊이는 이제 225영업일이다).
#: 둘 다 문자열·주석뿐이고 `VcpBreakoutStrategy.prepare` 는 **AST dump 동일**을 확인했다. 두 상수는 함께 움직인다 —
#: target > 보유 영업일이면 매일 밤 전량 재backfill churn 이다(cycle196 이 시정한 결함).
#: 파일 수는 **153 으로 불변**(신규 파일 0 — 이 사이클의 신규는 테스트뿐이다).
#: cycle298 후속 착지(= cycle299 착수) 값은
#: `12d793b51d82228e755ded6748177dcb7ba2ae64a2246d528900bc808965b9b9` 였다.
#: cycle299 안에서 두 번 더 움직였다 — ① `db/stock_master_daily.py` 의 낡은 이력 주석 2건
#: (retention 절 머리말의 "150 → 230" 계보 · `purge_old_rows` docstring 의 "VCP T-120일 +
#: 30일 안전 마진")을 현재 규칙으로 덮어썼다 ② 사용자 결정으로 목표를 220 → 225,
#: 보존을 380 → 390 으로 다시 올렸다(실효 장기선이 정확히 200 이 되는 깊이가 225 다).
#: ③ 사용자 요청("데이터 지금 바로 채울 수는 없어?")으로 `api/condition.py` 의 깊이 환산에
#: 휴일 보정을 비례로 얹어 1회 backfill 이 target 을 넘게 했다(225 영업일 목표 → 실도달
#: 232). 🔴 stride(윈도우 간격)는 7/5 그대로다 — 키우면 윈도우 사이에 구멍이 생긴다.
#: `engine/scanner.py` 는 ③ 에서 무접촉이라 8영역 sha 핀 13곳은 ② 의 값을 유지한다.
#: ④ 커밋 전 감사로 `engine/param_catalog.py` help 2건과 `engine/strategies/vcp_breakout.py`
#: 주석을 고쳤으나, **그 두 변경은 핀을 동반하지 않아 CI 를 붉혔고 핫픽스 2건
#: (`08a2138`·`96e46ce`)이 되돌렸다.** 그래서 cycle299 가 최종적으로 남긴 것은 ①~③ 뿐이다.
#: ⑤ cycle300 — 읽기 100행 클램프 해제. `db/stock_master_daily.py` 에 `_MAX_DAILY_ROWS=400`
#: (`min()` 구조 유지 = 폭주 방어 존속) · `engine/strategies/vcp_breakout.py` 에 VCP 전용
#: 스위치 `daily_fetch_depth_mode`(기본 `cap100` = 행위 byte 동일) · `engine/param_catalog.py`
#: 에 그 키 스펙 1건(101→102). ④ 가 되돌려진 help·주석도 이 사이클이 **다시 썼다** —
#: 클램프가 400 이 되면 "100봉만 온다" 는 인과 자체가 틀리므로 두 번 고치지 않고 한 번에
#: 썼다. 매매 행위는 스위치를 `full` 로 PUT 해야 비로소 바뀐다.
#: 🔴 이 사이클의 교훈 = **이 파일을 포함한 핀 5종을 파일 확정 뒤 한 값으로 동시에 옮긴다**
#: (`vcp_breakout.py` 전체 7곳 · `param_catalog.py` 전체 3곳 · `DEFAULT_PARAMS` 세그먼트 ·
#: `prepare` 세그먼트 2곳 · 이 digest). 하나라도 빠지면 CI 가 붉는다.
#: 🔁 cycle301(2026-09-18, 사용자 승인 D3·D4) 재핀 — `vcp_breakout.py` `DEFAULT_PARAMS`
#: 3값(ema_mid 60→150 · ema_long 120→200 · min_swing_atr_mult 0.5→1.0, 운영 DB 실측
#: 정합) + 주석 갱신. 파일 수(`_SRC_TREE_FILES`)는 불변 — 신규/삭제 0.
#: 🔁 cycle301 **보강**(2026-09-18) — `engine/param_catalog.py` 의 `ema_mid`/`ema_long`
#: help 문구를 배포된 새 기본값(VCP 150/200)에 맞춰 고쳤다("VCP 60"·"VCP 120" 은
#: 배포 즉시 거짓이었다). `vcp_breakout.py` 는 이 보강에서 무접촉 — sha 는
#: `5b324b34335f922f82b848ae2313e08660bde75c02d12432867ed224e9709228` 로 그대로다.
#: cycle301 착지(= 이 보강 착수) 값은
#: `2a7302c214888b79661a660419bcbaadfb71d2ae2d82eebefb788e04e58a54a1` 였다.
#: 🔁 **cycle302(2026-09-18, 사용자 명시 승인) 재핀 — 일봉 backfill 대상 확대.**
#: 움직인 파일 **1** = `engine/scanner.py`(8영역). backfill 분기에서 지수 소속 판정을
#: 빼 적재 대상(index ∪ 시총·거래대금 자격 ∪ 보유·익일청산 보호) 전부가 같은 목표
#: 깊이를 받게 했고, 그 판정에만 쓰이던 `vcp_universe_tickers` 집합을 지웠다.
#: 목표 깊이 상수(225)·retention(390cal)·적재 대상 집합 구성은 **불변**이다.
#: 같은 주석 블록에서 워크리스트에 파킹돼 있던 cycle300 후속 ②(인용 줄번호
#: `vcp_breakout.py:162-164` → `:309-314` + "VCP 실사용 100일" 이 `daily_fetch_depth_mode`
#: 로 바뀐 사실)도 함께 처리했다 — "다음에 `scanner.py` 를 승인받아 만질 때" 가 그 카드의
#: 착지 조건이었다. 주석 3줄이고 AST 는 불변이다.
#: 파일 수 **153 불변**(신규 파일 0 — 이 사이클의 신규는 테스트 1파일뿐).
#: 8영역 sha 핀 13곳과 이 digest 를 **한 값으로 동시에** 옮겼다.
#: cycle301 보강 착지(= cycle302 착수) 값은
#: `b25ba89bbbca1953be417f8d899f312c62f59c46cf80a96f7b4f400d50b6fe11` 였다.
#: 🔁 **cycle309(2026-09-18, 사용자 결정 "로그는 20일치만 저장하면 될듯해") 재핀 —
#: 로그 보관 일수 30→20.** 움직인 파일 **1** = `main.py`(8영역 아님). 두 개의
#: `TimedRotatingFileHandler` 가 각자 들고 있던 `backupCount=30` 리터럴을 모듈 상수
#: `_LOG_BACKUP_DAYS = 20` 하나로 모았다 — 두 핸들러가 갈라지면 `auto_stock.log` 와
#: `error.log` 의 보관 기간이 조용히 달라진다. 값을 줄인 이유는 용량이다: 하루 약 300MB 라
#: 30일이면 9GB 이고 EC2 루트가 19GB 뿐이라 이미지 3개를 굽는 배포에서 디스크가 마른다
#: (2026-09-18 실측 `logs/` 6.4GB · 루트 여유 3.4GB 로 배포 기준 5GB 미달).
#: 매매 행위·스케줄·AST 는 불변이고 로깅 설정 한 줄이다.
#: 파일 수 **153 불변**(신규 0). cycle302 착지(= 이 재핀 착수) 값은
#: `2b5d2a9936f7edd36ae360f851ce6856386a22341e07a5ca5dab71f650a72419` 였다.
#: 🔁 **cycle313(2026-09-19, 사용자 결정 "압축 안 하고 바로 지우기") 재핀 — 로그 압축 금지
#: 명문화.** 움직인 파일 **1** = `main.py`(8영역 아님), `_LOG_BACKUP_DAYS` 위 **주석만**.
#: 값·AST·매매 행위 전부 불변이다. 손으로 `.gz` 압축한 파일은 핸들러의 이름 규칙에서 벗어나
#: 자동 삭제 대상에서 영구히 빠진다(2026-09-18 실측 37개 1.9GB) — 디스크가 모자라면 압축이
#: 아니라 보관 일수를 줄이는 것이 답이라는 금기를 상수 옆에 붙였다.
#: 파일 수 **153 불변**. cycle309 착지(= 이 재핀 착수) 값은
#: `e1344ee4ef5d1e78ae81023fd27ba0ef21615f776051bbd9a38e8423573b3e20` 였다.
#:
#: 🔁 **cycle315(2026-09-19, 사용자 지시 "매크로레짐은 외부를 보던 걸 이제 우리 컨테이너에서
#: 확인하는걸로 전면 수정") 재핀 — 매크로 레짐 출처를 외부 `dkstock.cloud` 에서 우리 `macro`
#: 컨테이너로 전환.** 그 외부 서버는 2026-08-18 terraform destroy 로 철거됐고 되살릴 계획이 없다.
#: 움직인 파일 **9** = `config.py` · `engine/market_regime.py` · `engine/boot_manager.py` ·
#: `engine/recommendation_engine.py`(프롬프트 문구) · `routes/market_regime.py` ·
#: `routes/system_integrations.py` · `models/market_regime.py` · `db/system_config.py`(주석) ·
#: `db/market_regime_snapshots.py`(주석). **신규 1** `services/macro_client.py`,
#: **삭제 1** `services/dkstock_client.py` → 파일 수 **153 불변**(1 삭제 1 추가 상쇄).
#: 🔴 **8영역과 `scheduler.py` 는 diff 0** — 함수명 `refresh_from_dkstock` 을 유지해
#: `scheduler.py` 의 import·호출을 byte 동일로 두었다(개명은 그 파일의 승인 절차를 부른다).
#: 🔴 매수·손절 경로에 레짐이 닿는 코드는 여전히 **0건**이다 — 레짐은 관찰 지표다.
#: cycle313 착지(= 이 재핀 착수) 값은
#: `7408c8fd1555b1c08e28db4aac650d7fef3b980a6aa7d39d0bdf4623f3f6748c` 였다.
#:
#: 🔁 **cycle316(2026-09-19, `domain-consult` + 사용자 승인) 재핀 — 자금 자동조정 판정을
#: 「판독 불가면 수동」으로 뒤집고 관측 2종을 세웠다.** 움직인 파일 **1** =
#: `db/system_config.py`(8영역 아님). `_AUTO_REGIME_ADJUST_DEFAULT` True→**False** +
#: `[auto_regime_adjust] default_used reason=` WARNING + `set_cash_usage_ratio` 의 대폭 축소 경보.
#: 🔴 **현행 운영 행위는 한 바이트도 안 바뀐다** — 운영 DB 가 이미 `auto_regime_adjust=false` 다.
#: 달라지는 것은 키가 사라지거나 읽기가 실패한 순간뿐이고, 그때 원하는 행위가 운영자 값 보존이다.
#: 같은 사이클이 **백테스트 낡은 문구**도 정정했다 — 외부 MCP 서버가 2026-08-18 철거됐으므로
#: `Phase 4-bis 로컬 어댑터 대기` 는 착수된 계획이 있다는 오해를 만든다.
#: 움직인 파일 **4** = `engine/backtest_orchestration.py` · `engine/backtest_yaml.py` ·
#: `engine/backtest_engine.py` · `services/exceptions.py`(전부 문자열·주석, 행위 diff 0).
#: cycle315 착지(= 이 재핀 착수) 값은
#: `fc11588e2b689496f2d3133e6c252e5d649eb7a6811ca60d3107abc79c9937ab` 였다.
_SRC_TREE_DIGEST = (
    "71f5fa7ae79e74ae2a09495103b01542d5dff32abda680b3d1d4345e2b72af2b"
)

#: 디렉터리 통째로 잠그는 영역 — 새 파일이 조용히 들어오는 것도 접촉이다.
#: ⚠️ 자문 §9-B 는 신규 leaf 를 `src/engine/` 최상위에 두는 것을 허용했지만
#: 브리프 제약("세 파일뿐")이 그것을 막는다 — 라우터는 `order_engine.py` 안에 둔다.
_PINNED_DIRS = ("src/realtime", "src/auth", "src/engine/strategies", "src/engine")

#: 잠근 디렉터리의 **파일 수 핀**(cycle316 시정).
#: 🔴 이 dict 가 없으면 `test_s1d` 는 **구조적으로 공허**하다 — 종전 구현은 비교 양변
#: (`rglob` 결과와 `_tree_digest()` 의 `glob` 결과)이 **둘 다 라이브 디스크**에서 만들어져
#: 신규 파일이 양쪽에 동시에 들어갔고, 그래서 어긋날 수가 없었다.
#: 실제 탐지는 `test_s1b` 의 `_SRC_TREE_FILES`/`_SRC_TREE_DIGEST` 가 했다.
#: 그 둘은 "뭔가 바뀌었다" 만 말하고 **어디인지는 말하지 않는다** — 이 핀이 그 자리를 메운다.
#: ⚠️ 유지 규약 = `_SRC_TREE_FILES` 를 옮기는 사이클이 여기도 같이 옮긴다. 신규 파일이
#: 생긴 디렉터리만 +1 이므로 어느 줄을 고칠지는 실패 메시지가 알려 준다.
#: `src/engine` 은 하위 디렉터리(`strategies`·`util`)를 포함한 재귀 집계다.
_PINNED_DIR_FILE_COUNTS = {
    "src/realtime": 4,
    "src/auth": 3,
    "src/engine/strategies": 8,
    "src/engine": 76,
}

#: `scheduler.py` 정확 라인 수 + cycle257 영구 상한.
#: ⚠️ cycle292(2026-09-14) 가 `_subscribe_market_operation_tickers` 176줄을
#: 신규 leaf `src/engine/market_op_subscribe.py` 로 추출해(행위 변경 0 · 5줄
#: 위임 wrapper) 3,897 → 3,726 이 됐다. 값만 옮긴다 — 정확 핀을 상한 핀으로
#: 완화하면 cycle287 의 무접촉 대리 지표가 사라진다.
_SCHEDULER_LINES = 3795
_SCHEDULER_LINE_CAP = 3900

#: 손대지 않기로 한 **원문 구간**의 sha256 (base `a42f519`).
#: 키 = 구간 이름 / 값 = (시작 부분문자열, 끝 부분문자열, sha256).
_FROZEN_SEGMENTS = {
    # 매수 PR-F 사전 변환 — 브리프: "로직 자체는 byte 동일해야 한다".
    # ⚠️ cycle291(2026-09-13) 이 이 구간을 **정당하게** 바꿨다(GTP(27) 승격 —
    # 사용자 결정 "(나)안"). 자문이 명시한 절차대로 값만 새 기준선으로 옮긴다 —
    # `execute_buy` 의 시장가/`00` 사전 변환 *로직*(anchors 사이 구조)은 여전히
    # byte 동일해야 한다는 원 계약은 유지되고, 그 안에 GTP 승격이 순수 추가됐다.
    # sha 는 cycle291 적대 검증(3렌즈) 시정 반영 후 값으로 한 번 더 갱신됐다
    # (B5 카나리아 `[pre_nxt_division_config]` 배관이 이 구간 안에 순수 추가).
    "execute_buy_prf": (
        "        order_division = OrderDivision.MARKET\n        order_price = 0\n",
        "            order_price = 0\n",
        "8d8b23a042f33020d0c4339201777ec7f45baa872af8df08f5295a9fdbc8f039",
    ),
    # 매도 프리장 사전 지정가 변환 — 애프터 분기는 이 블록 **뒤**에 순수 추가한다.
    "execute_sell_pre_nxt_preconvert": (
        "        if order_division == OrderDivision.MARKET:\n            try:\n"
        "                from src.engine.scanner import ticker_prices as _tp",
        "                    ticker, exc_info=True,\n                )\n",
        "768b9f144b95bcfcfb7f3110b20e71d6588f36e8aa93af3e28a77f141922ecaf",
    ),
    # cycle286 C4-a 판정 3줄 — 되돌리지 않는다.
    "cycle286_nxt_evidence": (
        '                        _exchange_ok = target_exchange in ("NXT", "SOR")',
        "                        _nxt_evidence = _exchange_ok and _window_ok\n",
        "9fc283054484b408e8055ce75cb090df103a7d8149d01a9cef0a0a41660d4b0a",
    ),
}

#: 라우팅 판정 함수 이름 (자문 §9-B).
_ROUTER = "_route_exchange_by_clock"

#: 신규 파라미터 2키 — `PARAM_RANGES`/`INT_PARAMS` 편입 **금지**(리스크 정체성 상수).
_NEW_PARAM_KEYS = ("order_exchange_clock_mode", "after_market_exit_division")

_STRATEGY_FILES = tuple(
    rel for rel in _BASE_SHA if rel.startswith("src/engine/strategies/")
    and not rel.endswith("__init__.py")
)


# ---------------------------------------------------------------------------
# 공통 헬퍼
# ---------------------------------------------------------------------------
def _content_sha(rel: str) -> str:
    return hashlib.sha256((_ROOT / rel).read_bytes()).hexdigest()


def _src(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


def _tree_digest() -> tuple[int, str, list[str]]:
    changed = set(_CHANGED)
    h = hashlib.sha256()
    rels: list[str] = []
    for path in sorted(_ROOT.glob("src/**/*.py")):
        rel = str(path.relative_to(_ROOT)).replace(os.sep, "/")
        if rel in changed:
            continue
        rels.append(rel)
        h.update(rel.encode())
        h.update(b"\0")
        h.update(hashlib.sha256(path.read_bytes()).digest())
    return len(rels), h.hexdigest(), rels


def _function(rel: str, name: str):
    src = _src(rel)
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return src, node
    raise AssertionError(f"{rel}: 함수 `{name}` 부재")


def _method(rel: str, cls_name: str, name: str):
    src = _src(rel)
    tree = ast.parse(src)
    cls = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls_name
    )
    for node in cls.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return src, node
    raise AssertionError(f"{rel}: `{cls_name}.{name}` 부재")


# ===========================================================================
# S1 — 세 파일 외 프로덕션 diff 0
# ===========================================================================
@pytest.mark.parametrize("rel", sorted(_BASE_SHA))
def test_s1_pinned_files_are_byte_identical(rel: str) -> None:
    """S1 — 8영역(order/api 제외)·전략 7파일·`strategy_base`·`market_state`·
    `sell_rejection`·`balance` **diff 0**.

    한 파일이라도 바뀌면 "cycle287 은 세 파일만 바꾼다" 가 거짓이고, 별도 승인
    (8영역 승인 + `domain-consult` 선행)이 필요하다.

    ⚠️ 이 가드는 **cycle287 당시의 무접촉 약속**을 기록한 것이고, 핀 값은 그 뒤 사이클이
    같은 파일을 정당하게 바꿀 때마다 기준선으로 옮겨진다(값만 옮기고 단언은 약화시키지
    않는다). 어느 사이클이 무엇을 바꿨는지는 `_BASE_SHA` 의 주석이 남긴다.
    """
    path = _ROOT / rel
    assert path.exists(), f"{rel} 이 사라졌다 — 무접촉 계약 위반"
    got = _content_sha(rel)
    assert got == _BASE_SHA[rel], (
        f"{rel} 이 base(a42f519) 에서 바뀌었다 — {got} != {_BASE_SHA[rel]}. "
        "cycle287 의 프로덕션 범위는 models/order · order_engine · api/order 셋뿐이다"
    )


def test_s1b_whole_src_tree_is_byte_identical_except_the_three() -> None:
    """S1 — `src/**/*.py` **전수** 무접촉(세 파일 제외).

    명시 dict 가 못 보는 `routes/`·`services/`·`db/`·`middleware/`·`config.py` 가 조용히
    바뀌는 것도 접촉이다. 자문 §9-K 의 후속(param_catalog·Settings·manual-sell·
    sell_rejection 정식 인자·`excg_id_dvsn_Cd` 수집)은 **이 사이클 밖**이고, 이 가드가
    그 경계를 지킨다.
    """
    count, digest, rels = _tree_digest()
    assert count == _SRC_TREE_FILES, (
        f"`src/` 아래 .py 파일 수가 {count} (기대 {_SRC_TREE_FILES}) — "
        f"신규/삭제가 있다. 세 파일 외 신규 모듈은 이 사이클 범위 밖이다"
    )
    assert digest == _SRC_TREE_DIGEST, (
        "세 파일 외 `src/` 프로덕션 코드가 바뀌었다. 범인 찾기:\n"
        "  python3 -c \"import hashlib,pathlib;[print(hashlib.sha256(p.read_bytes())"
        ".hexdigest(), p) for p in sorted(pathlib.Path('src').rglob('*.py'))]\"\n"
        f"  기대 digest {_SRC_TREE_DIGEST} / 실제 {digest}"
    )


def test_s1c_scheduler_line_count_is_exact_and_under_cap() -> None:
    """S1 — `scheduler.py` 무접촉의 대리 지표 = 정확 라인 수 + 영구 상한 **< 3,900**.

    익일청산·15:20 강제청산이 `execute_sell` 경유라 규칙 1 을 `scheduler.py` 무접촉으로
    물려받는 것이 계약이다(자문 §I).
    """
    n = len(_src("src/engine/scheduler.py").splitlines())
    assert n < _SCHEDULER_LINE_CAP, (
        f"`scheduler.py` 가 {n}L — cycle257 영구 상한 {_SCHEDULER_LINE_CAP} 위반"
    )
    assert n == _SCHEDULER_LINES, (
        f"`scheduler.py` 가 {n}L 로 바뀌었다 (기대 {_SCHEDULER_LINES}L)"
    )


@pytest.mark.parametrize("rel_dir", _PINNED_DIRS)
def test_s1d_no_new_files_slip_into_pinned_dirs(rel_dir: str) -> None:
    """S1 — 잠근 디렉터리에 **새 .py 가 생기는 것**도 접촉이다.

    비교 기준은 **하드코딩 핀**(`_PINNED_DIR_FILE_COUNTS`)이다. 라이브 디스크끼리 비교하면
    신규 파일이 양변에 동시에 들어가 영원히 통과한다 — cycle316 이전 구현이 그랬다.

    `test_s1b`(트리 digest)와 역할이 다르다. 그쪽은 **무엇이든 바뀌면** 붉어지지만
    어느 디렉터리인지 말하지 않는다. 이 테스트는 **어디에 몇 개가 들고 났는지**를 짚는다.

    ⚠️ `src/engine` 도 잠근다 — 신규 leaf 를 만들 때 그 사실이 조용히 지나가면 안 된다.
    정당한 추가라면 이 핀을 같이 옮긴다.
    """
    found = sorted(
        str(p.relative_to(_ROOT)).replace(os.sep, "/")
        for p in (_ROOT / rel_dir).rglob("*.py")
    )
    expected = _PINNED_DIR_FILE_COUNTS[rel_dir]
    assert len(found) == expected, (
        f"{rel_dir}: 파일 수가 {expected} → {len(found)} 로 바뀌었다.\n"
        f"  현재 목록: {found}\n"
        f"  정당한 변경이면 `_PINNED_DIR_FILE_COUNTS[\"{rel_dir}\"]` 를 {len(found)} 로 옮기고 "
        f"`_SRC_TREE_FILES`/`_SRC_TREE_DIGEST` 도 함께 재핀한다."
    )


def test_s1e_changed_files_are_excluded_from_the_pin_on_purpose() -> None:
    """S1 — 변경 대상 세 파일은 `_BASE_SHA` 에 **없다**.

    있으면 정당한 변경이 이 가드에 막혀 Green 이 "핀을 재산출하지 마라" 문구를 만나고,
    그 문구가 승인된 변경을 되돌리도록 오도한다(cycle263 실측 사고 계열).
    """
    for rel in _CHANGED:
        assert (_ROOT / rel).exists(), f"{rel} 경로 오류"
        assert rel not in _BASE_SHA, f"{rel} 이 무접촉 핀 목록 안이다 — 범위 설계 오류"


# ===========================================================================
# S2 — 불변 구간 세그먼트 봉인
# ===========================================================================
@pytest.mark.parametrize("name", sorted(_FROZEN_SEGMENTS))
def test_s2_frozen_source_segments_are_byte_identical(name: str) -> None:
    """S2 — 손대지 않기로 한 원문 구간 3종의 sha256 불변.

    * `execute_buy_prf` — 브리프: "매수 시장가 사전 변환(PR-F) 로직 자체는 byte 동일"
    * `execute_sell_pre_nxt_preconvert` — 애프터 분기는 이 블록 **뒤**에 순수 추가
    * `cycle286_nxt_evidence` — cycle286 판정을 되돌리지 않는다

    ⚠️ `_window_ok` 를 지우지 말 것 — 라우팅을 `off` 로 내리면 16:05 의 `target_exchange`
    가 base 로 복귀해 `_exchange_ok` 가 참이 된다. 그때 오염을 막는 **유일한 방어**가
    `_window_ok` 다(두 축의 논리적 중복은 enforce 모드에서만 성립한다).
    """
    head, tail, expected = _FROZEN_SEGMENTS[name]
    src = _src(_ORDER_ENGINE_REL)
    assert head in src, f"`{name}` 시작 구간이 사라졌다"
    start = src.index(head)
    idx = src.index(tail, start)
    seg = src[start: idx + len(tail)]
    got = hashlib.sha256(seg.encode()).hexdigest()
    assert got == expected, (
        f"구간 `{name}` 이 바뀌었다 — {got} != {expected}\n--- 현재 ---\n{seg}"
    )


def test_s2b_ttl_axis_window_is_not_narrowed() -> None:
    """S2 — `is_nxt_session_hours` 의 `15:30~20:00` 을 **좁히지 않는다**.

    TTL 축 재정의(K9-g)는 `sell_rejection.py` 를 고치는 것이 아니라 **호출부가 넘기는
    인자의 의미**를 "매도 가능 창 안인가" 로 바꾸는 방식이다. 그래야 그 파일이
    diff 0 이고, 그 사실을 여기서 리터럴 존재로 복창한다(cycle286 `test_g4_2` 답습).
    """
    src = _src("src/engine/sell_rejection.py")
    fn = next(
        n for n in ast.walk(ast.parse(src))
        if isinstance(n, ast.FunctionDef) and n.name == "is_nxt_session_hours"
    )
    seg = ast.get_source_segment(src, fn) or ""
    for token in ("15, 30", "20, 0", "8, 0", "9, 0"):
        assert token in seg, f"`is_nxt_session_hours` 에서 `time({token})` 가 사라졌다"


def test_s2c_ltv_main_buy_cutoff_is_unchanged() -> None:
    """S2 — cycle286 `MAIN_BUY_CUTOFF_KST` == 15:20 불변(브리프 제약).

    `long_tail_volatility.py` 는 `_BASE_SHA` 로 이미 잠겨 있지만, 값 자체를 한 번 더
    복창해 "이 상수는 cycle287 의 접촉 대상이 아니다" 를 사람이 읽을 수 있게 한다.
    """
    from src.engine.strategies import long_tail_volatility as ltv_mod

    assert getattr(ltv_mod, "MAIN_BUY_CUTOFF_KST", None) == time(15, 20)


def test_s2d_sell_market_preconvert_marker_is_still_emitted() -> None:
    """S2 — `[sell_market_preconvert_pre_nxt]` 마커가 소스에 존재한다.

    프리장 청산 경로를 좁히지 않는다는 계약의 텍스트 증거(행위 증거는
    `test_cycle287_krx_after_exit.py::test_k3d`).
    """
    assert "[sell_market_preconvert_pre_nxt]" in _src(_ORDER_ENGINE_REL)


# ===========================================================================
# S3 — 라우터 구조 계약
# ===========================================================================
def test_s3_router_exists_with_the_specified_signature() -> None:
    """S3 (RED) — `_route_exchange_by_clock(base, *, side, mode, now)` 존재.

    `side`/`mode`/`now` 는 **키워드 전용**이어야 한다 — 위치 인자로 열어 두면
    호출부가 `side`/`mode` 순서를 뒤바꿔 `sell_only` 가 조용히 반대로 동작한다.
    """
    _src_text, fn = _function(_ORDER_ENGINE_REL, _ROUTER)
    assert [a.arg for a in fn.args.args] == ["base"], (
        f"위치 인자는 `base` 하나여야 한다: {[a.arg for a in fn.args.args]}"
    )
    kwonly = [a.arg for a in fn.args.kwonlyargs]
    for name in ("side", "mode", "now"):
        assert name in kwonly, f"키워드 전용 인자 `{name}` 부재: {kwonly}"
    assert not isinstance(fn, ast.AsyncFunctionDef), (
        "라우터는 **동기** 함수다 — `await` 를 늘리면 A-ATOMIC 구간 계약과 "
        "매수 원자성 논증이 흔들린다"
    )


def test_s3b_router_has_no_time_literals() -> None:
    """S3 (RED) — 라우터 안에 **시각 리터럴 0건**.

    경계는 `market_state.MARKET_TABLE`(유일 정본)에서 나온다. 여기에 `time(16, 0)` 을
    적으면 두 번째 정본이 생기고, KIS 가 시간표를 옮기는 날 둘이 갈라진다
    (cycle283 이 커트오프를 15:40 → 20:00 로 옮긴 것이 정확히 그 종류의 변경이다).
    """
    _s, fn = _function(_ORDER_ENGINE_REL, _ROUTER)
    bad = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            fname = (
                node.func.attr if isinstance(node.func, ast.Attribute)
                else getattr(node.func, "id", "")
            )
            if fname in ("time", "dtime", "_dtime") and node.args:
                bad.append(ast.dump(node)[:80])
    assert bad == [], f"라우터가 시각 리터럴을 만든다: {bad}"


def test_s3c_router_is_never_raise() -> None:
    """S3 (RED) — 라우터는 `except Exception` 으로 **전부 흡수**하고 base 를 돌려준다.

    fail-safe 방향(브리프): 판정 실패가 주문 자체를 막아서는 안 된다.
    """
    _s, fn = _function(_ORDER_ENGINE_REL, _ROUTER)
    handlers = [
        h for n in ast.walk(fn) if isinstance(n, ast.Try) for h in n.handlers
    ]
    assert handlers, "라우터에 `try/except` 가 없다 — 판정 예외가 주문을 막는다"
    caught = {
        (h.type.id if isinstance(h.type, ast.Name) else getattr(h.type, "attr", None))
        for h in handlers
    }
    assert "Exception" in caught, f"`except Exception` 부재: {caught}"
    raises = [n for n in ast.walk(fn) if isinstance(n, ast.Raise)]
    assert raises == [], "라우터가 예외를 던진다 — never-raise 계약 위반"


def test_s3d_router_reads_market_state_and_session_lazily() -> None:
    """S3 (RED) — `market_state`·`session` 은 **함수 안 lazy import**.

    최상단에 넣으면 cycle286 `test_g4_3`(최상단 `src.*` import 집합 14개 고정)과
    cycle276 `test_c4_2`(증가분 = `{src.engine.llm_buy_gate}`)가 즉시 RED 다.
    cycle286 자신이 `_dtime`·`stock_master` 를 그렇게 했다.
    """
    _s, fn = _function(_ORDER_ENGINE_REL, _ROUTER)
    modules = {
        n.module
        for n in ast.walk(fn)
        if isinstance(n, ast.ImportFrom) and n.module
    }
    assert "src.engine.market_state" in modules, (
        f"라우터가 `market_state` 를 함수 안에서 import 하지 않는다: {sorted(modules)}"
    )
    assert "src.engine.session" in modules, (
        "프리장 판정은 `session_tracker.active`(PR-F 와 같은 출처)를 써야 한다 — "
        f"{sorted(modules)}"
    )


def test_s3e_order_engine_top_level_src_imports_are_unchanged() -> None:
    """S3 (RED) — `order_engine.py` **모듈 최상단** `src.*` import 집합 불변.

    cycle286 `test_g4_3` 이 이 집합을 정확히 고정한다. 새 의존(`market_state`·`session`·
    `config`)은 전부 **함수 안 lazy import** 여야 한다.
    """
    tree = ast.parse(_src(_ORDER_ENGINE_REL))
    top = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("src."):
            top.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("src."):
                    top.add(alias.name)
    expected = {
        "src.api.balance",
        "src.api.base",
        "src.api.order",
        "src.db.system_logs",
        "src.db.trade_history",
        "src.engine",
        "src.engine.daily_emit_cap",
        "src.engine.scanner",
        "src.engine.sell_rejection",
        "src.engine.strategy_base",
        "src.engine.strategy_registry",
        "src.engine.util.tick_size",
        "src.models.order",
        "src.models.trade",
    }
    assert top == expected, (
        f"최상단 `src.*` import 가 바뀌었다 — 신규 {sorted(top - expected)} / "
        f"삭제 {sorted(expected - top)}. 새 의존은 함수 안 lazy import 로 둔다"
    )


def test_s3f_sendable_divisions_agree_with_the_market_table() -> None:
    """S3 (RED) — `_SENDABLE_DIVISIONS` 가 `market_state` 표와 정합한다.

    `41`/`44` 는 K6(KRX 애프터), `00`/`01` 은 K3(KRX 정규장) 에 있어야 한다.
    이 정합이 깨지면 16:00~20:00 이 `both_unsupported_keep` 으로 떨어져 애프터
    청산이 통째로 열리지 않는다(무음 실패).
    """
    from src.engine import order_engine as _oe
    from src.engine.market_state import MARKET_TABLE

    sendable = set(getattr(_oe, "_SENDABLE_DIVISIONS", ()))
    assert sendable, "`_SENDABLE_DIVISIONS` 부재"
    rows = {r.row_id: set(r.order_divisions) for r in MARKET_TABLE}
    assert {"41", "44"} <= rows["K6"], "K6(KRX 애프터)에 41/44 가 없다"
    assert {"41", "44"} <= sendable, f"`_SENDABLE_DIVISIONS` 에 41/44 가 없다: {sendable}"
    assert {"00", "01"} <= rows["K3"] & sendable


def test_s3g_router_is_applied_inside_strategy_exchange_async() -> None:
    """S3 (RED) — 라우팅은 `_strategy_exchange_async` **안**에서 적용된다.

    * 호출부 2곳(`:361` 매수 · `:666` 매도)을 한 번에 덮는다.
    * cycle286 판정보다 **앞**이라 `target_exchange` = "실제로 보낸 거래소" 의미 보존.
    * `[nxt_downgrade]`/`[stock_master_miss]` 가 라우팅 **전**에 발화해 관측 회귀 0.
    * G-MKT1/G-MKT2(`test_cycle100_*`)가 요구하는 소스 문자열이 그대로 남는다.
    """
    _s, fn = _method(_ORDER_ENGINE_REL, "OrderEngine", "_strategy_exchange_async")
    calls = [
        n for n in ast.walk(fn)
        if isinstance(n, ast.Call)
        and (
            getattr(n.func, "id", None) == _ROUTER
            or getattr(n.func, "attr", None) == _ROUTER
        )
    ]
    assert calls, f"`_strategy_exchange_async` 가 `{_ROUTER}` 를 부르지 않는다"


def test_s3h_limit_price_nxt_branch_is_still_present() -> None:
    """S3 — `limit_price > 0` 분기를 **지우지 않는다**.

    `test_cycle100_strategy_exchange_persistence_sell.py:96` 이 이 문자열을 영속
    단정한다. 호출자가 0곳(dead)이지만 지우면 그 가드가 RED 다 — 대신 그 분기의
    결과에도 라우팅을 씌운다(`test_r7_*`).
    """
    src = _src(_ORDER_ENGINE_REL)
    assert "limit_price > 0" in src
    assert "await self._strategy_exchange_async" in src


# ===========================================================================
# S4 — enum · cancel_order
# ===========================================================================
def test_s4_order_division_members_are_exactly_four() -> None:
    """S4 — `OrderDivision` 값 집합 == `{00, 01, 27, 41, 44}`.

    IOC/FOK(42/43/45/46)는 잔량 자동취소라 손절 잔여를 잃고, 47(최우선지정가)은
    크로스하지 않아 체결 보장이 없다 = 손절 수단이 아니다(자문 §3-A). **cycle291
    (2026-09-13)이 `27`(NXT GTP지정가, 프리마켓 매수 승격)을 정당하게 추가했다** —
    함수명은 base 시점 이름을 보존한다(다섯 번째가 됐다는 사실은 값으로 잰다).
    """
    from src.models.order import OrderDivision

    assert {d.value for d in OrderDivision} == {"00", "01", "27", "41", "44"}
    assert OrderDivision.LIMIT.value == "00"
    assert OrderDivision.MARKET.value == "01"


def test_s4b_models_order_is_not_pinned_anywhere() -> None:
    """S4 — `src/models/order.py` 는 어느 sha 핀에도 없다(자문 §8-4 실측).

    enum 멤버 추가의 가드 비용이 0 이라는 사실을 고정한다 — 누가 이 파일을
    `_BASE_SHA` 류에 넣으면 다음 enum 확장이 이유 없이 막힌다.
    """
    needle = f'"{_MODELS_ORDER_REL}":'   # sha 핀 dict 의 키 형태만 찾는다
    hits = []
    for path in (_ROOT / "tests").rglob("*.py"):
        if path.name.startswith("test_cycle287_"):
            continue  # 이 사이클의 산출물(산문 인용)은 핀이 아니다
        if needle in path.read_text(encoding="utf-8", errors="ignore"):
            hits.append(str(path.relative_to(_ROOT)))
    assert hits == [], f"`{_MODELS_ORDER_REL}` 가 sha 핀 dict 키로 등장한다: {hits}"


def test_s4c_cancel_order_gains_an_opt_in_order_division() -> None:
    """S4 — ⚠️ **반전(cycle291, 2026-09-13)**. `cancel_order` 는 이제 취소 축
    Stage A(배관+매핑+관측)의 opt-in 인자를 갖는다 — 자문 §4·§7 이 이 사이클
    밖으로 밀어냈던 것을 사용자 결정 "(나)안" 이 다시 열었다. 조건 3개가
    이전 계약이 지키던 것을 대신 잰다:

    1. `order_division` 은 **키워드 전용** + 기본값 `None`(AST 구조 — 위치
       인자로 승격하면 `cancel_order(order_no, 0, cancel_all=…)` 3 호출부의
       위치 의미가 흔들린다).
    2. 미전달 시 KIS body 가 **런타임으로** `"00"` 과 완전히 같다(소스
       리터럴이 아니라 `kis_post` 캡처로 잰다 — 표현만 바꾸면 무력해지는
       문자열 가드를 피한다. cycle291 Stage A 는 호출자 3곳이 아직 전달하지
       않으므로 이것이 "정규장 byte 동일" 의 실제 증거다).
    3. 화이트리스트가 없다 — `44` 를 조용히 지우던 함정(`execute_buy` 의
       `== LIMIT` 열거)을 재현하지 않는다.
    """
    _s2, fn = _function(_API_ORDER_REL, "cancel_order")
    kwonly = [a.arg for a in fn.args.kwonlyargs]
    positional = [a.arg for a in fn.args.args]
    assert "order_division" not in positional, (
        f"`order_division` 이 위치 인자로 들어왔다: {positional}"
    )
    assert "order_division" in kwonly, (
        f"`cancel_order` 에 opt-in `order_division` 이 없다: {kwonly}"
    )
    idx = kwonly.index("order_division")
    default = fn.args.kw_defaults[idx]
    assert isinstance(default, ast.Constant) and default.value is None, (
        "기본값이 `None` 이 아니다 — 미전달 시 byte 동일이 성립하지 않는다"
    )

    body_src = ast.get_source_segment(_src(_API_ORDER_REL), fn) or ""
    for needle in ("order_division in (", "order_division in [", "order_division in {",
                   "order_division not in (", "order_division not in [",
                   "order_division not in {",
                   "order_division ==", "order_division !="):
        assert needle not in body_src, (
            f"`cancel_order` 에 값 비교 {needle!r} 가 들어왔다 — 화이트리스트 금지"
        )


@pytest.mark.asyncio
async def test_s4c_2_cancel_order_body_is_byte_identical_when_not_passed() -> None:
    """S4 — 미전달 시 KIS body 10키가 **현행과 완전히 동일**하다(런타임 캡처).

    호출자 3곳이 아직 전달하지 않는 cycle291 Stage A 에서 정규장 취소가 한
    글자도 바뀌지 않는 것이 이 사이클의 절대 조건이다.
    """
    import src.api.order as _order
    from src.config import settings
    from unittest.mock import AsyncMock

    captured: dict = {}

    async def _fake_post(url, tr_id, body, hashkey=None):
        captured.update(body)
        return {"output": {"ODNO": "C", "ORD_TMD": "100031", "KRX_FWDG_ORD_ORGNO": ""}}

    mp = pytest.MonkeyPatch()
    try:
        mp.setattr(_order, "kis_post", _fake_post)
        mp.setattr(_order, "generate_hashkey", AsyncMock(return_value="hk"))
        await _order.cancel_order("0000000800", 0, cancel_all=True, exchange="NXT")
    finally:
        mp.undo()

    assert captured == {
        "CANO": settings.kis_account_no,
        "ACNT_PRDT_CD": settings.kis_account_product,
        "KRX_FWDG_ORD_ORGNO": "",
        "ORGN_ODNO": "0000000800",
        "ORD_DVSN": "00",
        "RVSE_CNCL_DVSN_CD": "02",
        "ORD_QTY": "0",
        "ORD_UNPR": "0",
        "QTY_ALL_ORD_YN": "Y",
        "EXCG_ID_DVSN_CD": "NXT",
    }, captured


def test_s4c2_api_order_change_is_documentation_only() -> None:
    """S4 (RED, cycle287) — `src/api/order.py` 의 **cycle287 시점** 변경은 docstring
    뿐이었다(자문 §S7). ⚠️ **cycle291 정정** — 이름·의도는 cycle287 것을 그대로
    두지만, cycle291 이 `cancel_order` 에 진짜 kwonly 인자(`order_division`)를
    추가했다. 그건 **본문 문장이 아니라 시그니처**라 아래 "본문 문장 수" 단언은
    여전히 성립하고(dict 안 조건식 하나로만 흡수 — `test_a11`/`test_s4c` 가 그
    계약을 직접 잰다), 이 테스트가 잠그는 것은 "cycle287 이 손댄 본문이 cycle291
    이후에도 문장 수 기준으로 늘지 않았다" 는 더 좁은 사실이다.

    `place_order` docstring 이 `ORD_DVSN` 표(00·01·27·41·44 + 애프터 시장가 없음 +
    ETP 불가)와 거래소 규칙을 담고, `cancel_order` docstring 이 "애프터 원주문 취소는
    미검증" 을 명시한다. 그래야 다음 사람이 `"00"` 하드코딩을 보고 "검증됐다" 고
    오독하지 않는다.

    본문(문장 수) byte 동일은 이 사이클의 계약이므로, docstring 을 제외한 **AST
    구조**가 base 와 같은지를 함수별 인자·본문 문장 수로 잰다(`ast.dump` sha 는
    3.12/3.13 출력차 때문에 금지 — cycle256 G-250-5).
    """
    src = _src(_API_ORDER_REL)
    place_doc = ast.get_docstring(_function(_API_ORDER_REL, "place_order")[1]) or ""
    cancel_doc = ast.get_docstring(_function(_API_ORDER_REL, "cancel_order")[1]) or ""

    for token in ("41", "44"):
        assert token in place_doc, (
            f"`place_order` docstring 에 애프터 호가코드 `{token}` 설명이 없다"
        )
    assert "ETP" in place_doc or "ETF" in place_doc, (
        "`place_order` docstring 에 애프터 ETP 불가 경고가 없다"
    )
    for needle in ("미검증", "미실측", "미확인"):
        if needle in cancel_doc:
            break
    else:
        raise AssertionError(
            "`cancel_order` docstring 이 애프터 원주문 취소의 **미지** 상태를 적지 않았다 "
            f"— {cancel_doc!r}"
        )
    # 본문(문장 수)은 불변 — docstring 만 늘어난다.
    for fname, stmts in (("place_order", 9), ("cancel_order", 8)):
        _s3, fn = _function(_API_ORDER_REL, fname)
        body = [n for n in fn.body if not (
            isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
            and isinstance(n.value.value, str)
        )]
        assert len(body) == stmts, (
            f"`{fname}` 본문 문장 수가 {len(body)} (base {stmts}) — "
            "cycle287 시점 본문(문장 수 기준)이 그대로다. 시그니처(kwonly 인자) "
            "변경은 cycle291 이 별도로 반영한다(`test_a11`/`test_s4c` 참조)"
        )
    del src


def test_s4d_place_order_still_passes_the_value_through() -> None:
    """S4 — `place_order` 가 `ORD_DVSN` 을 값 그대로 흘려보낸다(화이트리스트 금지).

    누가 `if order_division in (LIMIT, MARKET)` 류 검증을 끼워 넣으면 `44` 가
    조용히 사라진다(`execute_buy:410` 의 화이트리스트가 정확히 그 함정이다).
    """
    body_src = ast.get_source_segment(
        _src(_API_ORDER_REL), _function(_API_ORDER_REL, "place_order")[1]
    ) or ""
    assert '"ORD_DVSN": order_division.value' in body_src


# ===========================================================================
# S5 — 파라미터 (브리프 제약: 전략 7파일 diff 0)
# ===========================================================================
@pytest.mark.parametrize("key", _NEW_PARAM_KEYS)
def test_s5_new_keys_are_not_in_param_ranges_or_int_params(key: str) -> None:
    """S5 (RED) — 두 신규 키는 `PARAM_RANGES`/`INT_PARAMS` **편입 금지**.

    리스크·라우팅 정체성 상수이고 AI 자문 자동 적용 경로 밖이다
    (cycle242 `max_lot_units` · cycle245 `max_lot_ratio_mult` 관례).
    """
    from src.engine.recommendation_engine import INT_PARAMS, PARAM_RANGES

    assert key not in PARAM_RANGES, f"`{key}` 가 PARAM_RANGES 에 들어왔다"
    assert key not in INT_PARAMS, f"`{key}` 가 INT_PARAMS 에 들어왔다"


@pytest.mark.parametrize("rel", sorted(_STRATEGY_FILES))
@pytest.mark.parametrize("key", _NEW_PARAM_KEYS)
def test_s5b_new_keys_are_present_in_strategy_defaults(rel: str, key: str) -> None:
    """S5 — ✅ **정정(cycle290)** — 두 키는 이제 **7 전략 전부**의 파일에 있다.

    cycle287 배포 시점엔 브리프 제약(전략 7파일 diff 0)으로 부재였다(구 계약 =
    "어느 전략 파일에도 없다"). cycle290 이 두 키를 `DEFAULT_PARAMS` 말미에
    `order_engine` 모듈 상수와 같은 값으로 등재했다 — 라우팅·애프터 청산은
    `strategy_id` 로 params 를 조회하는 전 전략 공통 경로라 일부만 등재하면
    나머지 전략은 여전히 `unknown_key` 422 다.
    """
    assert key in _src(rel), (
        f"{rel} 에 `{key}` 가 없다 — cycle290 등재가 되돌려졌다(그 전략은 장중에 "
        f"끌 수 없다)"
    )


@pytest.mark.parametrize(
    "const, value",
    [
        ("_ORDER_EXCHANGE_CLOCK_MODE_DEFAULT", "enforce"),
        ("_AFTER_EXIT_DIVISION_DEFAULT", "44"),
    ],
)
def test_s5c_default_constants_live_in_order_engine(const: str, value: str) -> None:
    """S5 — 기본값의 정본은 `order_engine` **모듈 상수**다.

    ✅ **정정(cycle290)** — 두 키는 이제 7 전략 `DEFAULT_PARAMS` 에도 등재돼 있지만
    (`test_s5b`), 그 등재 값은 **이 상수와 같은 값**이라야 한다는 것이 계약이다
    (cycle290 A3). 즉 이 모듈 상수는 여전히 "부재 시 폴백"의 정본이자, 등재값이
    지켜야 하는 기준선이다 — 리터럴을 판정 지점마다 흩뿌리면 롤백 PUT 이 한쪽만
    바꾸는 사고가 난다.
    """
    from src.engine import order_engine as _oe

    got = getattr(_oe, const, None)
    assert got == value, f"`order_engine.{const}` = {got!r} (기대 {value!r})"


def test_s5d_after_exit_division_whitelist_is_exactly_44_and_41() -> None:
    """S5 (RED) — dial 허용 집합 == `{"44", "41"}`.

    클램프가 아니라 **화이트리스트**다 — 집합 밖은 `44` 로 폴백해 청산을 여는
    방향으로 떨어진다(`test_k5c_*`). `47`·IOC/FOK 가 조용히 나가는 것도 막는다.
    """
    from src.engine import order_engine as _oe

    allowed = getattr(_oe, "_AFTER_EXIT_DIVISION_ALLOWED", None)
    assert allowed is not None, "`_AFTER_EXIT_DIVISION_ALLOWED` 부재"
    assert set(allowed) == {"44", "41"}, f"허용 집합 {sorted(allowed)}"


# ===========================================================================
# S6 — 자문 §S2 상수 전수 + `_apply_clock` 적용 지점 (cycle287 추가)
# ===========================================================================
def test_s6_clock_routed_bases_are_exactly_nxt_and_sor() -> None:
    """S6 (RED) — `_CLOCK_ROUTED_BASES == ("NXT", "SOR")`.

    `KRX` 가 이 집합에 들어오면 `base_krx` 조기통과가 사라져 `nxt_tradable=False`
    다운그레이드가 내린 `KRX` 를 라우터가 다시 판정한다 — 프리장에서 그 값이 base 로
    "복귀" 하면 NXT 비대상 종목에 NXT 주문이 나간다.
    """
    from src.engine import order_engine as _oe

    got = getattr(_oe, "_CLOCK_ROUTED_BASES", None)
    assert got is not None, "`_CLOCK_ROUTED_BASES` 부재"
    assert tuple(got) == ("NXT", "SOR"), got


def test_s6b_giveup_threshold_is_five() -> None:
    """S6 (RED) — `_AFTER_EXIT_GIVEUP_THRESHOLD == 5` (자문 §1-E 봉인 2).

    상한 검산: 종목당 ≤10 주문(5회 × 1차+폴백) / 보유 7종목 전건 실패 ≤70 주문/저녁.
    KIS 20/s 한도 대비 무해하고, 30초 TTL 만으로 남는 ticker 당 ≈1,440 요청을
    ≈10 으로 수렴시킨다.
    """
    from src.engine import order_engine as _oe

    assert getattr(_oe, "_AFTER_EXIT_GIVEUP_THRESHOLD", None) == 5


def test_s6c_exit_capable_krx_phases_are_the_three_sendable_ones() -> None:
    """S6 (RED) — `_EXIT_CAPABLE_KRX_PHASES == {REGULAR, CLOSE_AUCTION, AFTER_MARKET}`.

    TTL 축(자문 §4-I)의 정의 = "그 시각 KRX 가 우리 청산 호가를 받는가". 09-14 **전**에는
    이 술어가 `is_krx_main_hours` 와 **완전히 일치**하고(AFTER_SINGLE K7 은 집합 밖),
    09-14 부터 `AFTER_MARKET` 하나만 늘어난다 — 그래서 `sell_rejection.py` 를 고치지
    않고 호출부 인자의 **의미**만 바꾸는 것이 성립한다.

    ⚠️ `PRE_AUCTION`(시가 단일가)을 넣으면 안 된다 — 그 창의 거부는 09:00 재평가를
    기다리는 것이 옳고, 5분 TTL 로 줄이면 단일가에 시장가를 반복 발사한다.
    """
    from src.engine import order_engine as _oe
    from src.engine.market_state import MarketPhase

    got = getattr(_oe, "_EXIT_CAPABLE_KRX_PHASES", None)
    assert got is not None, "`_EXIT_CAPABLE_KRX_PHASES` 부재"
    assert set(got) == {
        MarketPhase.REGULAR, MarketPhase.CLOSE_AUCTION, MarketPhase.AFTER_MARKET,
    }, sorted(p.name for p in got)
    assert MarketPhase.PRE_AUCTION not in set(got), (
        "시가 단일가를 '청산 가능' 으로 보면 그 창의 TTL 이 5분으로 줄어 "
        "단일가에 시장가를 반복 발사한다"
    )


def test_s6d_apply_clock_is_the_single_application_seam() -> None:
    """S6 (RED) — 적용은 `_apply_clock` **하나**를 경유한다(자문 §S4).

    라우터를 호출부마다 직접 부르면 마커·mode 조회·예외 흡수가 네 군데로 복제되고,
    한 곳을 빠뜨리면 그 경로만 조용히 라우팅을 비켜간다. `_apply_clock` 은 **동기**여야
    한다 — 동기 취소 3경로(`_cancel_after_wait`·`_cancel_and_reorder`·`cancel_remaining`)가
    같은 seam 을 쓰기 때문이다(자문 §4-C2).
    """
    _s, fn = _method(_ORDER_ENGINE_REL, "OrderEngine", "_apply_clock")
    assert not isinstance(fn, ast.AsyncFunctionDef), (
        "`_apply_clock` 이 async 다 — 동기 취소 3경로가 이 seam 을 쓸 수 없다"
    )
    kwonly = [a.arg for a in fn.args.kwonlyargs]
    assert "side" in kwonly, f"`side` 키워드 전용 인자 부재: {kwonly}"


@pytest.mark.parametrize(
    "method",
    ["_cancel_after_wait", "_cancel_and_reorder", "cancel_remaining"],
)
def test_s6e_sync_cancel_paths_go_through_apply_clock(method: str) -> None:
    """S6 (RED) — 동기 취소·재주문 3경로가 `_apply_clock` 을 경유한다(자문 §4-C2).

    셋은 `self._strategy_exchange(strategy_id)`(DB 값 직독 = 전부 `SOR`)를 쓴다.
    라우팅을 async 관문에만 넣으면 **주문은 KRX, 취소는 SOR** 로 갈린다.
    """
    _s, fn = _method(_ORDER_ENGINE_REL, "OrderEngine", method)
    calls = {
        getattr(n.func, "attr", None)
        for n in ast.walk(fn) if isinstance(n, ast.Call)
    }
    assert "_apply_clock" in calls, (
        f"`{method}` 가 `_apply_clock` 을 경유하지 않는다 — 취소 거래소가 원주문과 "
        f"갈린다. 현재 호출: {sorted(c for c in calls if c)}"
    )


# ===========================================================================
# S7 — ✅ 정정(cycle290) — 장중 킬스위치가 **있다** (등재 후 PUT 이 통한다)
# ===========================================================================
@pytest.mark.parametrize("key", _NEW_PARAM_KEYS)
def test_s7_new_keys_can_be_put_at_runtime(key: str) -> None:
    """S7 — ✅ **정정(cycle290)** — 두 신규 키는 이제 `PUT` 으로 바꿀 수 있다.

    🔴 이 테스트는 종전 합성 dict `{"exchange": ..., "tradable_boards": ...}` 를
    `current_params` 로 넘겼었는데, 그 dict 에는 두 키가 애초에 없으므로
    `param_validation` 의 `key not in current_params or spec is None` 판정이
    등재와 **무관하게** 영원히 `unknown_key` 였다 — 초록인 채로 "장중 킬스위치는
    없다"는 거짓 주장을 계속 지키는 가짜 가드였다. 이제 실제 `DEFAULT_PARAMS` 를
    `current_params` 로 써서 진짜 등재 여부를 잰다.

    cycle290 이 두 키를 7 전략 전부의 `DEFAULT_PARAMS` + `param_catalog` 에 등재해
    `PUT /api/strategies/{id}/params` 가 200 + `accepted` 로 통과한다. 롤백은 이
    PUT 뿐이다(SQL UPDATE 는 다음 재시작에서만, cycle232 D6).
    """
    from src.engine.param_validation import validate_params
    from src.engine.strategies.long_tail_volatility import LongTailVolatilityStrategy

    current = dict(LongTailVolatilityStrategy.DEFAULT_PARAMS)
    value = "off" if key == "order_exchange_clock_mode" else "41"
    result = validate_params("long_tail_volatility", current, {key: value})
    codes = {(e.key, e.code) for e in result.errors}
    assert (key, "unknown_key") not in codes, (
        f"`{key}` 가 여전히 `unknown_key` 다 — cycle290 등재가 되돌려졌다. "
        f"실제 오류: {codes}"
    )
    assert result.errors == (), result.errors
    assert result.accepted == {key: value}, result.accepted
