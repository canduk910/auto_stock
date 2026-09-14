# cycle292 — `_subscribe_market_operation_tickers` leaf 추출 명세

> **상태**: RED 명세(구현 전). 프로덕션 코드 미변경.
> **작성 시점 기준선**: `src/engine/scheduler.py` **3,897L** · sha `50658e06062a0d38afecab1baa08871b89212e295cc95f2a3af62a2ae076115d` ·
> `src/engine/*.py` **60개** · `src/**/*.py` **148개**(cycle287 `_CHANGED` 3파일 제외) ·
> 트리 digest `d491c518cb200717246577be3bcfd904c854f9a6c9fe625e28f639666477a277`.
> 네 수치 전부 이 문서 작성 중 실측 재현했다. 구현 착수 시 다시 재보고, 하나라도 다르면
> 이 문서의 파생값(아래 §5 라인 산식 · §6 핀 표)을 **전부 재산출**한다.
> **사용자 승인**: "스케쥴러 리팩터 오늘 수행하자". **커밋·push 금지**(정규장 중 · 보유 11종목 · D6).

---

## 1. 왜

`scheduler.py` 가 3,897L 이고 영구 상한이 **3,900L 미만**(cycle257 A4 가 정본, 자매 가드 8곳이
복창)이라 **여유가 3줄**이다. 다음 사이클이 관측 로그 한 줄을 넣으려 해도 예산이 없다.
`tests/unit/ast/test_cycle291_ast_scope.py:9` 가 이미 "여유 3줄 · 오늘 별도 사이클 cycle292 가
이 파일을 리팩터 예정" 이라고 예고해 뒀다.

추출 대상 `_subscribe_market_operation_tickers` 는 **176줄**이고 절단면이 깨끗하다:

- `self` 접근이 **3속성 6곳**뿐이고(§3), 모듈 전역 의존이 `logger`·`asyncio` 둘뿐이다.
- 외부 심볼(`kis_ws`·`kis_ws_pool`·`MARKET_OP_TR_ID`·`MAX_SUBSCRIPTIONS`·`State`·
  `ConnectionClosedError`) 전부를 **함수-로컬 import** 로 직접 가져온다 — 모듈 전역을 거치지 않는다.
- `scheduler.py` 안에서 그 여섯 심볼을 쓰는 **다른** 코드가 0건(grep 확인)이라 추출 후 잔여 참조가 없다.
- 시계 호출 0건 → freezegun 결합 없음.
- 호출부가 단 하나(`_scan_loop`, `scheduler.py:2429`)이고 이미 `try/except` 로 감싸여 있다.

착지: **3,897 → 3,726L**(여유 3 → **174**).

---

## 2. 무엇을 옮기는가

### 2.1 경계 (실측)

| 구간 | 줄 | 줄 수 |
|---|---|---|
| 시그니처 | 3169–3171 | 3 |
| docstring | 3172–3199 | 28 |
| 본체 | 3200–3344 (`return subscribed`) | 145 |
| **함수 전체 = 이동 대상** | **3169–3344** | **176** |

- 3168 = 빈 줄 · **3345 = 빈 줄** · 3346 = `async def _refresh_stale_ccnl_cache(`.
  3169–3344 를 통째로 떼어내고 그 자리에 위임부를 넣으면 앞뒤 빈 줄 규약이 유지된다.
- docstring 28줄은 **leaf 로 함께 옮긴다.** 역사 서술(cycle149/214/221 F1·F2 정정, 08-19 사고 경위)이고,
  남기면 위임부가 비대해지고 지우면 F1/F2 의 "되살리지 않는다" 근거가 사라진다.

### 2.2 새 파일

**`src/engine/market_op_subscribe.py`**

파일명 근거: 마커 5종이 전부 `[market_op_subscribe_*]` / `[market_op_no_quote_session]` 이라
운영 로그에서 파일을 바로 찾는다(`selling_reconcile.py` ↔ `[selling_reconcile]`,
`quote_token_refresh.py` ↔ `[quote_token_refresh]` 와 같은 관례). 형제
`market_operation_monitor.py` 와 **역할이 반대**라 이름이 갈려야 한다 — 그쪽은 H0UNMKO0
**수신·상태 추적**(순수 leaf), 이쪽은 **송신·구독 배치**(scheduler 인스턴스를 받는다). 합치면
순수 leaf 가 오염된다.

비추천: `market_op_manager.py`(`*_manager` 는 `stale_manager.py` 처럼 re-export facade 전용 명명) ·
`vi_subscribe.py`(코드·문서가 일관되게 `market_op`/H0UNMKO0 로 부른다) ·
`market_operation_subscriber.py`(마커 접두와 어긋나 grep 이 한 단계 늘어난다).

### 2.3 새 시그니처 (확정안, 대안 없음)

```python
"""종목별 H0UNMKO0(VI) 구독 leaf — cycle292 에서 `scheduler.py` 에서 이동.

`scheduler._subscribe_market_operation_tickers` 가 이 함수에 위임한다. 행위는
cycle221/230 계약 그대로이고 이동만 했다 — 자세한 설계 근거는 함수 docstring.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger("src.engine.scheduler")  # §4 — 임의 변경 금지


async def subscribe_market_operation_tickers(
    scheduler: Any, candidate_tickers: set[str], *, cap: int = 60,
) -> int:
```

- 위치 1번 인자 = scheduler, 키워드 `cap` — `stale_watcher_core.resubscribe_stale_priority(scheduler, cap=10)` 와 동형.
- **`cap` 을 제거하지 않는다.** vestigial 이지만 `test_G_214_4_cap_default_is_60` 이
  `inspect.signature(...).parameters["cap"].default == 60` 을 단언하고, 요약 로그의
  `cap=%d` 인자로 실제 쓰인다.
- 함수명은 leaf 관례대로 `_` 접두를 뗀다(`check_and_resubscribe_stale`·`reconcile_stale_selling` 선례).
- `from __future__ import annotations` 는 `Any` 와 무관하게 관례로 넣는다(전 leaf 공통).

### 2.4 왜 `fn(scheduler, ...)` 이고 좁은 목이 아닌가

본체가 `scheduler.registry`(읽기) · `scheduler._pending_next_day_clear`(읽기) ·
`scheduler._market_op_subs`(**쓰기** — `pop` L3266 / `__setitem__` L3312) 세 속성을 쓴다.
`_market_op_subs` 의 소유권은 scheduler 에 남아야 한다(선언 `scheduler.py:378`, 일일 clear `:3842`,
그 두 자리를 재는 가드 `test_init_declares_market_op_subs`·`test_reset_daily_state_clears_market_op_subs`).

좁은 목(`selling_reconcile.reconcile_stale_selling(order_engine, holdings, *, min_age_s)` 형)으로
쪼개면 인자가 4개가 되고 본체가 `self.X` → 지역변수로 갈려 **"라인 단위 동일" 증명이 약해진다**
(cycle67 계약 = "함수 본체 변경 0, `self.*` → `scheduler.*` 치환만", `stale_watcher_core.py:16`).

### 2.5 함수-로컬 import 5줄은 🔴 **byte 동일하게 leaf 안에 유지한다**

```python
        from websockets.exceptions import ConnectionClosedError
        from websockets.protocol import State

        from src.api.market_operation import MARKET_OP_TR_ID
        from src.realtime.websocket import MAX_SUBSCRIPTIONS, kis_ws
        from src.realtime.websocket_pool import kis_ws_pool
```

**이것을 모듈 최상단으로 "정리" 하는 것이 이 사이클의 단일 최대 위험이다.** 리팩터 상식처럼
보이지만:

1. 기존 테스트 4파일이 전부 **정의 모듈의 속성**을 덮는다 —
   `monkeypatch.setattr("src.realtime.websocket.kis_ws", …)`(`test_cycle214_h0unmko0_pool.py:106` ·
   `test_cycle221_market_op_off_main.py:152` · `test_market_op_subscribe_socket_guard.py:109` ·
   `test_market_op_subscribe_import_regression.py:98`) /
   `("src.realtime.websocket_pool.kis_ws_pool", …)`. 함수-로컬 import 는 **매 호출 재실행**되므로
   본체가 어느 모듈에 있든 그 patch 가 걸린다. 이것이 이 추출이 안전한 유일한 이유다.
2. 최상단으로 올리면 이름이 leaf 모듈 전역에 **import 시점 바인딩**되어 patch 가 leaf 가 보는
   참조를 더는 바꾸지 못한다. 그러면 테스트가 **실제** `kis_ws` 를 만나 `_ws is None` →
   **`return 0` 즉시 반환**한다. 그리고 그 조기 반환은 다음 6케이스를 **조용히 초록으로** 통과시킨다
   (전부 부정 단언이라 조기 반환과 구별 불가):
   - `test_cycle214_h0unmko0_pool.py::test_low_candidates_are_not_subscribed_at_all`
   - `test_cycle214_h0unmko0_pool.py::test_cap_is_vestigial_no_candidate_placement`
   - `test_market_op_subscribe_socket_guard.py::test_non_open_socket_skips_without_sending[closing/closed/connecting]`
   - `test_market_op_subscribe_socket_guard.py::test_none_socket_still_skips`
3. **두 줄 분리는 그 자체가 회귀 가드의 대상이다.** `kis_ws_pool` 은 `websocket_pool.py:619` 에만
   있고 `websocket.py` 에 재노출 0건 — 2026-07-24 에 이 한 줄이 합쳐져 있어서 cycle214 가
   **배포 이래 완전 미작동**(매 호출 ImportError, 하루 117건 = 일일 ERROR 94%)이었다.
   `test_market_op_subscribe_import_regression.py:103` 이 `monkeypatch.delattr(
   "src.realtime.websocket.kis_ws_pool")` 로 프로덕션 부재를 강제해 그 사고를 재현한다.

⚠️ `test_market_op_subscribe_import_path_guard.py::test_no_src_module_imports_kis_ws_pool_from_websocket`
은 `_SRC.rglob("*.py")` 전수라 신규 leaf 를 자동 커버하지만, **최상단으로 올려도 여전히 초록이다**
(경로는 맞으니까). 위 (2) 의 함정은 그 가드가 막지 못한다 — §7 의 신규 가드가 맡는다.

---

## 3. 행위 보존 계약

### 3.1 무엇이 byte 동일해야 하는가

이동 중 **바뀌는 것은 정확히 7개 토큰**뿐이다(실측 재현):

| # | 무엇 | 어디 |
|---|---|---|
| 1 | 첫 인자명 `self` → `scheduler: Any` | 시그니처 2행(구 L3170) |
| 2 | 함수명 `_subscribe_market_operation_tickers` → `subscribe_market_operation_tickers` | 시그니처 1행(구 L3169) |
| 3–7… | `self.` → `scheduler.` **6곳** | 구 L3221 · 3229 · 3265 · 3266 · 3284 · 3312 |

그리고 **전 줄 4칸 dedent**(`async def` 4→0, 본체 8→4). 변환 뒤 `self` 토큰 잔여 **0건**(실측).

그 밖 전부 불변 — 이 목록은 금지 목록이다:

- **로그 문구·레벨·필드 순서·`%`-포맷 인자 순서** (§3.3). f-string 으로 바꾸지 않는다.
- **`[market_op_subscribe_summary]` 가 INFO(요약) 와 WARNING(한도 초과) 두 레벨에 같은 마커로
  쓰인다** — 레벨을 통일하려는 유혹이 있는데 `test_cycle221_market_op_off_main.py:331` 이
  `r.levelno == logging.WARNING` 으로 no_slot 을 세므로 **레벨 축은 계약**이다.
- **호출 순서**: 소켓 가드 → HIGH 수집 → low_skipped 관측 → 메인 점유 계측 → `quotes` 확보 →
  **델타 해제** → 배치 루프 → 요약 INFO → main_over WARNING → no_slot WARNING → `return subscribed`.
- **예외 처리 분기**: `try/except: pass` 3곳(HIGH 수집 outer/inner, NDC) · `except: low_skipped = 0` ·
  `except: main_total = 0` / `main_tick = 0` · 해제 실패 WARNING 후 continue ·
  `except ConnectionClosedError` → WARNING + `placed = None` + 내부 break + 외부 break ·
  `except Exception` → `logger.exception` + `placed = True` + 내부 break(종목별 격리) ·
  `used` 산출 실패 시 `used = limit`(**fail-closed = 만석 취급**).
- **`pop` 이 `unsubscribe` 보다 먼저**(SEND 실패해도 맵에서 빠진다 — 재시도는 다음 5분 사이클).
- **`_market_op_subs[ticker] = ws` 가 `subscribed += 1` 앞.**
- **라운드로빈 커서 `idx = (idx + offset + 1) % len(quotes)` 는 성공 시에만 전진.**
- **`await asyncio.sleep(0.05)` 는 성공 배치 뒤에만**(사이클 17 Rate Limit). 🔴 `import asyncio` +
  `asyncio.sleep(...)` 형태 유지 — `from asyncio import sleep` 로 바꾸면
  `test_rate_limit_sleep_preserved` 의 `patch("asyncio.sleep", …)` 가 안 걸려 실제 0.05초를 자고
  `sleeps == []` 로 깨진다.
- **`targets = sorted(high_tickers)`** — 후보(`candidate_tickers`)는 배치 대상에 들어가지 않고
  `low_skipped` 관측 카운트로만 쓰인다(cycle221 F2).
- **메인 폴백 금지** — `quotes` 가 비면 INFO 1행 + `return 0`. tick > VI 명시적 교환.
- **`ws.subscribe(MARKET_OP_TR_ID, ticker, bypass_limit=False)`** — 보조 세션 객체 **직접** 호출.
  `kis_ws.subscribe` 0건 · `kis_ws_pool.subscribe/unsubscribe` 0건.
- **`getattr(_ws_obj, "state", None) is not State.OPEN`** — `is not` 동일성 비교(`==` 아님).
- **`limit = MAX_SUBSCRIPTIONS`** 하드리밋 41. `_MARKET_OP_QUOTE_RESERVE` 예약 슬롯 재도입 금지(F1).

### 3.2 증명 방법 — 변환 후 세그먼트 sha (권고, 1회용) — ✅ **2026-09-14 대조 완료·폐기**

> **이 절의 핀은 이미 소임을 다했다.** 구현 직후 실측 sha 가 아래 기대값 `0343fe38…` 와
> **일치**했고(3렌즈가 각각 독립 재현: 행위보존·가드무력화·전량실행), 그것으로 "본체 라인 단위
> 동일" 이 기계 증명됐다. 이제부터 이 hex 는 **공허하다** — 남긴 것은 감사 기록일 뿐이다.
> 🔴 **어떤 영속 가드에도 복사해 넣지 않는다.** 넣으면 다음 사이클의 정당한 한 줄 추가가
> "핀을 재산출하지 말고 코드를 되돌려라" 문구를 만난다(cycle264 C7 선례 = 이 사이클이 피한 함정).
> 영속 대조는 `test_cycle292_ast_market_op_leaf.py::_BASE_SHA`(파일 단위 3개)가 맡는다.


`ast.dump` **금지**(3.12 CI ↔ 3.13 로컬 출력이 달라 CI 만 붉어진다 —
`test_cycle264_scope_and_pins.py:203-205` · cycle256 G-250-5 · cycle259 S4a 실측).
파일 sha·원문 세그먼트 sha 는 dedent + 치환 때문에 정의상 달라진다. 그래서 **변환 후 세그먼트 sha**
를 쓴다. 변환을 기계적으로 정의하고 기대값을 지금 산출해 둔다:

```
HEAD 원문 세그먼트(ast.get_source_segment) sha = 3d6cc8589c162cd8ead32600bcd7cd75ab8bf9faebcbaa6846bf84e6879feb79  (176줄)
변환 규칙:
  1) scheduler.py L3169–3344 (1-indexed, inclusive) 를 취한다
  2) 각 줄에서 선행 4칸을 제거한다(4칸으로 시작하는 줄만; 빈 줄 불변)
  3) "self." → "scheduler."  (6곳)
  4) 1행: "async def _subscribe_market_operation_tickers(" → "async def subscribe_market_operation_tickers("
  5) 2행: "    self, candidate_tickers: set[str], *, cap: int = 60,"
        → "    scheduler: Any, candidate_tickers: set[str], *, cap: int = 60,"
  6) "\n" 으로 join (trailing newline 없음 = get_source_segment 규약)
기대 결과 sha256 = 0343fe38c64aedb57cef27a2982deef21ef38347722fde2cdda3395a081543b6   (176줄, bare self 0건)
```

구현 직후 leaf 의 `ast.get_source_segment(leaf_src, fn)` sha 가 **`0343fe38…`** 와 같으면
"본체 라인 단위 동일" 이 기계적으로 증명된다. 이 핀은 커밋 뒤 공허해지므로 **그 커밋에서 삭제한다**
(cycle264 C7 선례). CI 에 영속시키지 않는다 — 영속시키면 다음 사이클의 정당한 한 줄 추가가
"핀을 재산출하지 말고 코드를 되돌려라" 문구를 만난다.

보조 증명 2종(이쪽이 영속):
- **기존 행위 테스트 4파일 무수정 통과**(§6-H). 하나라도 수정이 필요하면 **그 자체가 행위 변경 신호**다.
- 산문 계약: 위 §3.1 금지 목록.

### 3.3 로그 마커 5종 7발화점 (원문 인용 — 한 글자도 바뀌지 않는다)

| 구 줄 | 레벨 | 마커 / 문구 선두 |
|---|---|---|
| 3215 | `logger.info` | `[market_op_subscribe_skip] 소켓 미개방 — 사이클 skip, 다음 재개` |
| 3257 | `logger.info` | `[market_op_no_quote_session] 보조 세션 0 — 종목별 VI skip(메인 폴백 금지)` |
| 3273 | `logger.warning` | `[market_op_subscribe] VI 해제 실패 ticker=%s graceful` |
| 3300 | `logger.warning` | `[market_op_subscribe] 소켓 재연결 중 — VI 잔여 %d종목 skip` |
| 3307 | `logger.exception` | `[market_op_subscribe] VI 구독 실패 ticker=%s graceful` |
| 3324 | `logger.info` | `[market_op_subscribe_summary] high=%d low_skipped=%d placed=%d released=%d skipped_no_slot=%d main_direct=0 sessions=%d main_tick=%d main_total=%d main_over=%d cap=%d` — 인자 순서 `len(high_tickers), low_skipped, subscribed, released, skipped_no_slot, len(quotes), main_tick, main_total, main_over, cap` |
| 3331 | `logger.warning` | `[market_op_subscribe_summary] 메인 세션 서버 한도 초과 main_total=%d max=%d main_over=%d — tick 구독 거부(OPSP0008) 위험` |
| 3338 | `logger.warning` | `[market_op_subscribe_no_slot] 보조 세션 전 세션 만석 — … is_ticker_stale_excluded 가 VI/거래정지 종목을 stale 에서 제외하지 못해 강제 재구독 지속 → KIS LMS 압력 증가` |

`write_log` 호출 0건(이 함수는 DB 에 쓰지 않는다). 프론트엔드 소비처 0건.
**배포 전후 grep 합산 가능** — 문구·레벨·로거 이름이 전부 같으므로 의미 전환이 없다.
(그래서 이 사이클엔 "3세대 합산 금지" 류 경고가 붙지 않는다. 그게 성공의 서명이다.)

---

## 4. logger 정체성 — 🔴 `"src.engine.scheduler"` 명시 바인딩

```python
logger = logging.getLogger("src.engine.scheduler")  # 사이클 60 I1 영속
```

### 4.1 근거 셋

1. **`system_logs` 접두 연속성** — `src/main.py::_DbLogHandler.emit` 이
   `message = f"[{record.name}] {record.getMessage()}"` 로 적재한다. 이름이 갈리면 위 마커 5종의
   `system_logs` 접두가 전부 `[src.engine.market_op_subscribe]` 로 바뀌어 **운영 grep·판독 문서
   인용이 파괴된다 = 행위 변경 0 위반**. `_DbLogHandler` 는 `setLevel(logging.INFO)` 이므로
   INFO 마커 2종도 실제로 DB 에 간다 — **레벨도 바꾸지 않는다**.
2. **caplog 스코프 6곳이 로거 이름에 의존한다**(실측) —
   `test_cycle221_market_op_off_main.py:78` `_LOGGER = "src.engine.scheduler"` +
   이를 쓰는 `caplog.at_level(logging.INFO, logger=_LOGGER)` **5곳**(:222 · :240 · :321 · :375 · :596) ·
   `test_market_op_subscribe_import_regression.py:109`.
   `pyproject.toml` 에 `log_level` 설정이 없어 루트 로거가 **WARNING(30)** 이므로,
   `__name__` 이면 그 스코프 밖 INFO 는 **캡처 자체가 안 된다**(핀·가드지형 프로브 실증).
3. **부분 위장 주의** — `__name__` 을 쓰면 대부분의 caplog 단언이 붉어지지만
   `test_main_over_emits_warning` 은 **조용히 통과한다**(검사 문자열 `main_over=4` 가 INFO 요약 외에
   WARNING 1행에도 있고 WARNING 은 루트 기본 레벨에서 캡처된다). 또
   `test_market_op_subscribe_socket_guard.py:131/217/246` 은 `caplog.at_level(logging.INFO)`(로거 미지정)
   이라 이름과 무관하게 통과한다 — **이 파일만 돌려보면 결함을 못 잡는다.**

### 4.2 선례가 균일하지 않다 — 판별 기준을 남긴다

`src/engine/` 의 leaf 로거는 **두 갈래**다(실측):

| 바인딩 | 파일 |
|---|---|
| `"src.engine.scheduler"` | `selling_reconcile.py:57` · `stale_watcher_core.py:44` · `stale_diagnostics.py:23` · `data_load_tasks.py:22` · `account_risk_watcher.py:121` |
| `__name__` | `boot_manager.py:32`(cycle51, 관례가 굳기 **전**) · `open_price_observe.py:75` · `open_price_rest.py:68` · `quote_token_refresh.py:111` · `daily_metrics_snapshot.py:37` · `kojiro_gap_observe.py:65` |

**판별 기준(이 문서가 명문화한다)**: 옮겨 가는 마커가 **이미 `[src.engine.scheduler]` 접두로
운영 로그에 쌓여 있었는가**. 그렇다면 이름을 고정한다(접두 단절 = 판독 사슬 파괴). 그 leaf 가
**새로** 만드는 마커라면 `__name__` 이 맞다(접두가 그 leaf 를 가리키는 게 더 정직하다).

cycle292 의 마커 5종은 **전부 기존**(cycle149/214/221 부터 쌓여 있다) ⇒ **`"src.engine.scheduler"` 필수**.
`open_price_rest.py` 가 `__name__` 인 것을 보고 "관례가 폐기됐다" 고 읽으면 안 된다 — 그쪽 마커
(`[main_rest_basis_*]`)는 cycle272 가 새로 만든 것이다.

### 4.3 자매 가드 선례

행위 축 = `test_cycle273b_selling_hold_observe.py::test_f7_logger_identity_is_scheduler` ·
`test_cycle60_phase2A1_stale_manager.py:544`.
AST 축 = `test_cycle273b_ast_no_behavior_guards.py::test_g273b_ast3_…`.
cycle292 도 같은 형태 1건을 신규로 건다(§7 G-292-2).

---

## 5. `scheduler.py` 에 남는 것

### 5.1 위임부 (그대로 붙일 수 있는 전문)

**(a) import — 기존 줄에 합류(신규 줄 0)**. 현재 `scheduler.py:43`:

```python
from src.engine import quote_token_refresh  # cycle269 토큰 갱신 leaf (라인 상한 보호)
```

→

```python
from src.engine import market_op_subscribe, quote_token_refresh  # cycle292 VI 구독 leaf / cycle269 토큰 갱신 leaf (라인 상한 보호)
```

(`:42` 가 이미 `open_price_observe, open_price_rest` 두 이름을 한 줄에 담고 있고 131자다 —
합류는 확립된 관례이고 lint 설정도 없다. 줄 길이는 scheduler.py 최장 470자.)

**(b) 위임부 — 구 3169–3344 자리에 5줄**:

```python
    async def _subscribe_market_operation_tickers(
        self, candidate_tickers: set[str], *, cap: int = 60,
    ) -> int:
        """종목별 H0UNMKO0(VI) 구독 — cycle292 market_op_subscribe leaf 위임."""
        return await market_op_subscribe.subscribe_market_operation_tickers(self, candidate_tickers, cap=cap)
```

- 🔴 **시그니처를 글자 그대로 복제한다**(3행 형태 포함). `**kwargs` 위임으로 만들면
  `test_G_214_4_cap_default_is_60` 이 `KeyError: 'cap'` 으로 깨진다.
- docstring 은 **1행**. 🔴 여기에 `State`/`state` 라는 단어를 **넣지 않는다** —
  `test_guard_reads_socket_state_in_scheduler` 가 `inspect.getsource` 부분문자열 검사라
  docstring 한 단어로 거짓 초록이 된다(§6-G).
- `return` 은 1행(109자). `stale_manager.resubscribe_stale_priority` 위임부(`:3162`)와 같은 형태.

**(c) 모듈-레벨 import 를 고른 이유**(두 조사가 갈렸다 — 함수-레벨 안을 기각한 근거):

`scheduler.py:3118-3167` 의 `stale_manager` 11 wrapper 는 함수-레벨
(`from src.engine import stale_manager` 후 `return await …`)이고, 옮길 함수가 바로 그 블록
**옆**이라 지역 일관성은 함수-레벨을 가리킨다. 그런데 그 블록이 함수-레벨인 이유는 순환 import 가
아니라 **`scheduler.py:108-119` 가 `from src.engine.stale_manager import (10 상수)` 를 이미 갖고
있어서 모듈 *이름* 이 바인딩돼 있지 않기 때문**이다(부차적으로 stale 계열은
`sys.modules.get("src.engine.scheduler")` 로 scheduler 를 되읽어 import 시점 결합을 피할 이유도 있었다).
cycle292 는 그 사정이 없다:

- leaf 가 scheduler 를 **import 하지 않는다**(인자로만 받는다) ⇒ 순환 0.
  판정 기준의 정본 = `data_load_tasks.py:11-12` 배너("이 모듈은 scheduler 를 import 하지 않는다").
- 최신 선례 4개(`data_load_tasks`·`open_price_observe`·`open_price_rest`·`quote_token_refresh`)가
  전부 `scheduler.py:41-43` 의 모듈-레벨 블록에 모여 있고, 그 블록의 주석이 이미
  "라인 상한 보호" 라는 **같은 목적**을 명시한다 — cycle292 leaf 는 그 블록의 다섯 번째다.
- 합류로 **1줄 싸다**(함수-레벨 6줄 vs 모듈-레벨 5줄 + 0). 부수로 leaf 부재가 import 시점에 즉시 드러난다.

### 5.2 무변경

- 호출부 `scheduler.py:2429` `await self._subscribe_market_operation_tickers(new_set)` +
  그 `except Exception: logger.exception("_subscribe_market_operation_tickers 실패 — 다음 사이클 자연 재시도")`(2430–2433) **불변**.
- `self._market_op_subs: dict = {}` 선언(`:378`) · `.clear()`(`:3842`) **불변**.
- `self._pending_next_day_clear`(`:376`) · `self.registry`(`:300`) **불변**.
- `MAX_SUBSCRIPTIONS` 는 leaf 가 realtime 에서 직접 읽으므로 scheduler 에 남길 상수 **없음**
  (`selling_reconcile` 의 `SELLING_RECONCILE_MIN_AGE_S` 같은 잔류 상수가 이 사이클엔 해당 없다).

### 5.3 라인 산식

```
3,897  (기준선)
 −176  (구 3169–3344 제거)
   +5  (위임부)
   +0  (import 합류)
------
3,726L    상한 3,900 대비 여유 174줄  (종전 3)
```

leaf 파일은 ≈187L(헤더 10 + 본체 176 + 여백) 예상.
🔴 구현 직후 `wc -l src/engine/scheduler.py` 와 `ls src/engine/*.py | wc -l` 를 기록한다 —
그 두 수가 §6 의 3·4단계 입력이다. **3,726 이 아니면 §6 의 라인 핀 6곳에 실측값을 넣는다**
(이 문서의 숫자를 믿고 넣지 말 것).

---

## 6. 손대야 하는 가드·핀

### 실측 근거 — 프로브 2회

1. **빈 파일 프로브**(핀·가드지형): `touch src/engine/_probe.py` → 3건 실패.
2. **실내용 프로브**(이 문서, 직접 실행): 실제 176줄 본체 + `logger = getLogger("src.engine.scheduler")`
   + 함수-로컬 import 5줄 + 마커 5종을 담은 leaf 를 만들고
   `pytest tests/unit/ast tests/unit/engine`(7,261케이스) 전량 실행 → **3 failed, 7,258 passed**.
   실패는 아래 A군 3건뿐이었다. ⇒ **어떤 내용-스캔 가드도 신규 leaf 에 트립하지 않는다**
   (`test_cycle72_ast_no_logger_write_log_pair` · `test_cycleM5_no_supabase_outside_db` ·
   `test_cycle282_ast_purity` 등 src 전수 스캐너 30여 개 전부 초록). 프로브는 즉시 삭제했고
   워킹트리 청결을 확인했다.

⚠️ 프로브는 scheduler.py 를 **건드리지 않았다** — 그래서 B·C군(라인·sha)과 D군(함수 지향)은
아직 발화하지 않았다. 실제 리팩터의 총 실패 예상 = **A 3 + B 6 + C 6 + D 4 = 19건**
(A 의 cycle287 s1b 하나가 파일 수와 트리 digest를 동시에 재므로 C 의 트리 digest 는 별항이 아니다).

---

### A군 — 신규 파일 등록 3곳 (실측 확정)

| # | 파일 : 줄 | 테스트 | 무엇을 어떻게 | 불변식이 같은 강도로 지켜지는 근거 |
|---|---|---|---|---|
| A1 | `tests/unit/ast/test_cycle287_ast_scope.py:164` · `:179` | `test_s1b_whole_src_tree_is_byte_identical_except_the_three` | `_SRC_TREE_FILES = 148` → **149** + `_SRC_TREE_DIGEST` 재산출 | 이 가드는 "cycle287 이 세 파일 외를 건드리지 않았다"를 재는 **사후 증거**다. cycle292 가 `scheduler.py` + 신규 leaf 를 **승인 하에** 바꾸므로 기준선을 옮기는 것이 절차다(`:50-51` 가 "정당하게 바꾸는 다음 사이클이 이 dict 를 갱신한다"고 이미 적어 뒀다). 검사 면적은 그대로 `src/**/*.py` 전수 — **좁아지지 않는다** |
| A2 | `tests/unit/ast/test_cycle290_ast_scope.py:278` `_ENGINE_PY_FILES["src/engine"]` | `test_g290_3_no_new_module_under_src_engine[src/engine]` | 명시 tuple 60개에 `"market_op_subscribe.py"` 를 **사전순 자리**(`log_metrics_collector.py` 뒤, `market_operation_monitor.py` 앞)에 추가 | 가드는 `tuple(sorted(glob("*.py")))` 과 **집합 동일**을 요구한다. 이름을 등재하면 "다음 신규 파일"은 여전히 붉어진다 — 강도 불변. 개수만 늘리는 형태로 바꾸면 안 된다(이름 축이 사라진다) |
| A3 | `tests/unit/ast/test_cycle291_ast_scope.py:304` | `test_a8_no_new_leaf_in_src_engine` | `== 60` → **`== 61`** | docstring "이 사이클은 leaf 를 만들지 않는다" 는 cycle291 의 서술이다. 값만 옮기고 docstring 에 "cycle292 가 `market_op_subscribe.py` 를 신설해 61" 한 줄을 덧붙인다(값 변경 근거를 남기지 않으면 다음 사람이 가드를 지운다) |

🔴 **발견 — `_PINNED_DIRS` 는 신규 파일을 막지 못한다(문서 오류 + 동어반복 가드).**
`src/engine/CLAUDE.md:67`(market_state.py 절)은 이렇게 적고 있다:

> `_PINNED_DIRS`(`test_cycle287_ast_scope.py`)가 `src/engine/` 최상위 신규 파일을 막고

**거짓이다.** `test_cycle287_ast_scope.py:341-357` 의 `test_s1d_no_new_files_slip_into_pinned_dirs` 는
비교의 **양변을 모두 디스크에서** 만든다 — `found` 는 `(_ROOT/rel_dir).rglob("*.py")`,
`pinned` 는 `_tree_digest()` 가 돌려주는 `all_rels`(역시 `_ROOT.glob("src/**/*.py")`). 새 파일이
양쪽에 동시에 들어오므로 **항상 초록**이고, 두 프로브에서 실제로 통과했다. 신규 파일을 실제로
막는 것은 같은 파일의 `test_s1b`(`_SRC_TREE_FILES`)다.
- 대조군: `test_cycle286_ast_scope.py:219-234::test_g1c` 는 `pinned` 를 하드코딩 dict `_BASE_SHA`
  에서 만들어 **진짜 가드**다(다만 cycle286 `_PINNED_DIRS` 에 `src/engine` 이 없어 무관).
- **cycle292 의 할 일** = `src/engine/CLAUDE.md:67` 문장을 사실로 정정(§6-J).
  `test_s1d` 자체의 동어반복 시정은 **별건 카드**로 남긴다 — 그 파일은 cycle287 무접촉 증거라
  손대면 계약 서술이 흐려진다.

---

### B군 — `scheduler.py` 정확 라인 핀 6곳 (전부 갱신)

| # | 파일 : 줄 | 테스트 | 무엇을 어떻게 |
|---|---|---|---|
| B1 | `test_cycle274_ast_llm_gate.py:631` | `test_c16_1_scheduler_line_count_unchanged` | 인라인 `assert lines == 3897` → 실측값. 메시지의 "기대 3,897" 문구도 함께 |
| B2 | `test_cycle276_ast_order_hook.py:726` · `:729` | `test_c5_2_scheduler_line_count_is_3897` | 리터럴 + 🔴 **함수명 개명**(`…_is_3897` → `…_is_pinned`). 함수명에 숫자를 다시 박으면 다음 사이클이 또 개명해야 한다 |
| B3 | `test_cycle286_ast_scope.py:125` | `test_g1b_scheduler_line_count_is_exact_and_under_cap` | `_SCHEDULER_LINES = 3897` → 실측값 |
| B4 | `test_cycle287_ast_scope.py:189` | `test_s1c_scheduler_line_count_is_exact_and_under_cap` | 〃 |
| B5 | `test_cycle290_ast_scope.py:145` | `test_g290_1b_scheduler_line_count_is_under_the_permanent_cap` | 〃 |
| B6 | `test_cycle291_ast_scope.py:130` | `test_a2_scheduler_line_count_is_pinned_under_the_permanent_cap` | 〃 (그 파일 `:9` 의 "여유 3줄 · cycle292 예정" 서술도 정직화) |

**불변식 강도**: 이 여섯은 "그 사이클이 scheduler.py 를 건드리지 않았다"의 **대리 지표**다.
값을 실측으로 옮기면 대리 기능이 그대로 살아난다(다음 사이클의 무단 1줄 추가가 여전히 6곳을 붉힌다).
🔴 **`< _SCHEDULER_LINE_CAP` 로 완화하지 않는다** — 정확 핀을 상한 핀으로 바꾸면 174줄의 무단
증식을 아무도 못 잡는다. 그건 예산을 확보하자고 예산 감시자를 끄는 것이다.

### B-cap군 — 상한 가드 9곳 (값 유지, 자동 통과)

`test_cycle257_ast_dead_code_removed.py:275/277`(**정본 A4**) · `test_cycle264_scope_and_pins.py:88` ·
`test_cycle264_scope_and_pins.py:94`(리터럴 교차 대조) · `test_cycle268_ast_gap_observe.py:606` ·
`test_cycle269_quote_token_refresh_wiring.py:43/46` · `test_cycle272_ast_main_rest_basis.py:515` ·
`test_cycle273_ast_kojiro_rank.py:366` · `test_cycle273b_ast_no_behavior_guards.py:39/207` ·
`test_cycle283_evening_window.py:461/474`.
줄이 줄어들므로 전부 그대로 통과한다.
🔴 **`cycle257` 의 `3900` 리터럴은 절대 바꾸지 않는다** —
`test_cycle264_scope_and_pins.py:94` 와 `test_cycle269:43` 이 그 파일에서 정규식으로 값을 뽑아
교차 대조하므로, 건드리면 두 테스트가 동시에 붉어진다. 상한을 **올리는** 유혹도 금지
(이 사이클의 목적이 상한 준수이지 상한 완화가 아니다).

---

### C군 — `scheduler.py` 내용 sha 핀 6곳 (같은 한 값으로 **동시** 갱신)

현재 값 `50658e06062a0d38afecab1baa08871b89212e295cc95f2a3af62a2ae076115d`, 여섯 dict 전부 동일.

| # | 파일 : 줄 | dict | 테스트 |
|---|---|---|---|
| C1 | `test_cycle274_ast_llm_gate.py:559`/`:572` | `_BASE_SHA` | `test_c15_1_untouchable_files_are_byte_identical[src/engine/scheduler.py]` |
| C2 | `test_cycle276_ast_order_hook.py:337`/`:348` | `_BASE_SHA` | `test_c5_1_untouchable_files_byte_identical[…]` |
| C3 | `test_cycle278_ast_catalog_guards.py:202`/`:224` | `_BASE_SHA` | `test_eight_areas_and_scheduler_and_strategy_base_untouched[…]` |
| C4 | `test_cycle282_ast_purity.py:375`/`:407` | `_BASE_SHA` | `test_h3_eight_areas_untouched[…]` |
| C5 | `test_cycle290_ast_scope.py:99`/`:131` | `_BASE_SHA` | `test_g290_1_untouched_production_files_are_byte_identical[…]` |
| C6 | `test_cycle291_ast_scope.py:72`/`:99` | `_BASE_SHA` | `test_a1_forbidden_files_are_byte_identical[…]` |

🔴 **한 곳만 넣으면 안 된다.** 나머지 다섯이 "핀을 재산출하지 말고 코드를 되돌려라" 문구로
붉어져 **승인된 변경을 되돌리도록 오도한다**(cycle263 실측 7 failed 사고 계열,
`test_cycle223g3_ast_guard_sees_staged.py::test_g3_9b` 가 이 계약을 재는 가드다).
절차 = `shasum -a 256 src/engine/scheduler.py` **한 값**을 여섯 곳에 동시에.

**불변식 강도**: 여섯 핀은 각 사이클의 "scheduler 무접촉" 증거다. 값을 옮기면 그 사이클 이후의
무단 변경을 여전히 전부 잡는다. 🔴 **scheduler.py 를 `_BASE_SHA` 에서 삭제하거나
`_CHANGED` 로 옮기는 완화 금지** — 그러면 그 사이클의 무접촉 증거가 영구 소멸한다
(cycle287 `test_s1e` 가 "변경 대상은 `_BASE_SHA` 에 없다"를 재지만, 그건 **그 사이클의** 변경 대상 얘기다).

### C-무영향군 (근거 명시, 손대지 않는다)

- `_SEGMENT_SHA`(cycle290, 28핀) · `_STRATEGY_PINS`(cycle264 / cycle274 `test_c18`) ·
  `_LTV_FROZEN_METHODS`(cycle286) — **전략 파일 메서드 전용**.
- `_FROZEN_SEGMENTS`(cycle287) · `_SELL_PRECONVERT_SEGMENT`(cycle291 A3) — **`order_engine.py` 구간 전용**.
- `test_cycle222a3_ast_anchor_owner_coupling.py:87` 의 `("src/engine/scheduler.py", "_execute_next_day_clear")`
  — `high_since_buy` 절대대입 소유자 화이트리스트. 옮기는 함수는 `high_since_buy` 를 대입하지 않으므로 무영향
  (키가 `(경로, 함수명)` 이라 **그 함수를 옮겼다면** 붉어졌다 — 다행히 다른 함수다).
- `*_CONTENT_SHA` 자매 4핀(`test_cycle222a3_ast_followup_fixes` · `test_cycle223_ast_donchian_exit_fix` ·
  `test_cycle223f_ast_manual_apply_safeguard` · `test_cycle226_zero_breakout_defense`) — scheduler.py 를 핀하지 않는다(프로브 확인).
- `test_cycle253_ast_channel_probe.py:264` `_FROZEN_PATHS` — `_skip_if_cycle_committed` 로 현재 skip.
- 좀비 task / 멤버 가드 전부 무영향: `test_scheduler_stop_zombie_tasks.py` `expected_members`
  (옮기는 함수는 task 를 만들지 않고 `_scan_loop` 안에서 `await` 로 불린다) ·
  `test_cycle79/83/89_ast_task_cancel_required` · `test_cycle78/89_ast_flush_required` ·
  `test_cycle269:~55 test_g269_2` · `test_cycle245_ratio_notional_cap.py:1171` ·
  `test_cycle84_scan_pool_emit_persistence.py:29`(`[scan_pool_eager_refresh]` 는 scheduler 에 남는다).

---

### D군 — 🔴 함수 노드를 `scheduler.py` 에서 찾는 가드 4파일 (이 사이클의 최대 위험)

값만 옮기는 A·B·C 와 달리, 이쪽은 **"본체가 scheduler.py 안에 있다"를 구조적으로 요구**한다.
위임부만 남기면 **3건은 실패하고 5건은 조용히 공허해진다.** 후자가 더 위험하다.

🔴 **왜 공허해지는가**: `_get_function_node(tree, "_subscribe_market_operation_tickers")` 는
scheduler.py 에 남는 **위임 wrapper 노드를 찾아낸다** — `raise AssertionError("함수 미발견")` 는
발화하지 않는다. 그 wrapper 노드에 대해 "…가 0건이어야 한다" 는 **부정 단언은 전부 참**이 된다.

#### D1. `tests/unit/ast/test_cycle221_ast_market_op_no_main.py` — 08-19 실사고 재발 방지 정본

`_SCHEDULER_PATH`(`:32`) + `_FN`(`:39`) + `_vi_hook()`(`:52`) 를 **leaf 경로 + leaf 함수명**으로 재조준한다.

```python
_BODY_PATH = _ROOT / "src" / "engine" / "market_op_subscribe.py"
_BODY_FN = "subscribe_market_operation_tickers"
```

그리고 **네 개의 "0건" 단언 전부에 양성 대조군(anti-vacuity)을 같은 테스트 안에 심는다.**
각 한 줄이면 되고, 현행 본체가 이미 만족하므로 **느슨해지는 게 아니라 조인다**:

| 테스트 | 이동 후 | 재조준 + 양성 대조군 | 불변식 강도 근거 |
|---|---|---|---|
| `test_no_main_subscribe_in_vi_hook` | **공허 초록** | `kis_ws.subscribe` 0건 **+ 세션 직접 호출(`ws.subscribe`)이 ≥1건 존재** | 지금은 구독 호출이 통째로 사라져도 초록이다. 대조군을 넣으면 "SEND 는 있는데 그 owner 가 kis_ws 가 아니다"를 재게 되어 08-19 OPSP0008(메인 45/41 → 보유 4종목 ~58분 tick blind) 재발 차단이 **복원되고 강화**된다 |
| `test_no_bypass_limit_true_literal` | **공허 초록** | `bypass_limit=True` 0건 **+ `bypass_limit` 키워드 ≥1건**(현행 `False` 1건) | 〃 |
| `test_no_pool_subscribe_unsubscribe_calls` | **공허 초록** | `kis_ws_pool.subscribe/unsubscribe` 0건 **+ `kis_ws_pool` 식별자 ≥1건**(`_quotes` 읽기 생존) | F-P(`_ticker_to_session` 이 `tr_key` 단일 키 → VI 가 풀 경유 시 TICK drop 종목이 quote-N 고착 = TICK 영구 미구독) 봉인 복원 |
| `test_socket_state_guard_persists` | **FAIL(시끄럽게)** | `_BODY_PATH` 소스로 이식. `"State.OPEN" in fn_src` + `ExceptHandler` 의 `ConnectionClosedError` 둘 다 leaf 에 byte 동일하게 남으므로 **강도 불변** | 2026-08-07 닫힌 소켓 send 레이스(11:24:57 HIGH 7종목 ERROR 폭주) 가드 |
| `test_quote_reserve_constant_absent` | **부분 공허** | 스캔 대상을 scheduler.py **단독 → scheduler.py + leaf 두 파일**로 넓힌다(`hasattr` 단언도 leaf 모듈에 추가) | 불변식("예약선 41−8=33 재도입 금지 — 만석 근처에서 보유 VI 가 전량 skip")은 그대로이고 **검사 면적만 본체를 따라간다**. 이것이 느슨해지지 않는 유일한 방향이다 |
| `test_execution_notice_tr_ids_unchanged` · `test_eight_areas_untouched` | 통과 | 무수정 | 경로 무관(`_EXECUTION_NOTICE_TR_IDS` / 8영역 3파일 스캔). leaf 는 8영역이 아니므로 구멍 없음 |

#### D2. `tests/unit/ast/test_cycle214_ast_h0unmko0_pool.py`

- `test_G_214_5_pool_referenced_for_quote_sessions_only`(`:71`) — **FAIL**. `_BODY_PATH`/`_BODY_FN`
  으로 재조준. `kis_ws_pool`·`kis_ws` Name + `_quotes` 읽기 단언을 그대로 이식(leaf 가 함수-로컬
  import 를 유지하므로 성립) ⇒ 강도 불변.
- `test_G_214_5b_bypass_true_is_now_forbidden`(`:98`) — **공허 초록**. 재조준 +
  D1 과 같은 `bypass_limit` 키워드 ≥1 대조군.
- `test_G_214_3_execution_notice_tr_ids_unchanged` — 무수정.

#### D3. `tests/unit/ast/test_market_op_subscribe_import_path_guard.py`

- `test_market_op_function_imports_pool_from_websocket_pool`(`:79-80`) — **FAIL**
  (`pool_import_ok == False`). `_BODY_PATH`/`_BODY_FN` 으로 재조준. 이 테스트는 이미
  **존재 단언 + 부재 단언 쌍**이라 공허 통과가 구조적으로 불가능하다(강도 불변).
- `test_no_src_module_imports_kis_ws_pool_from_websocket` — 무수정. `_SRC.rglob("*.py")` 전수라
  신규 leaf 를 **자동 커버**한다. ⚠️ 단 §2.5 의 새 함정(최상단 승격)은 못 막는다 → §7 G-292-1.

#### D4. `tests/unit/engine/test_market_op_subscribe_socket_guard.py:266-272`

`test_guard_reads_socket_state_in_scheduler` — **FAIL**. 고치는 방법이 둘이고 **하나가 거짓 초록**이다:

- ❌ **금지** — wrapper docstring 에 "소켓 state 가드는 leaf 로 위임" 같은 문장을 넣어 초록으로
  만드는 것. `inspect.getsource` 는 docstring 을 포함하므로 **통과하지만 실제 가드를 전혀
  검증하지 않는다.** 원래도 `"State" in src or "state" in src` 라는 대단히 느슨한 부분문자열
  검사라, 그 상태로 leaf 를 가리키게만 해도 강도가 낮다.
- ✅ **권고** — 대상을 leaf 함수 소스로 옮기면서 **동시에 조인다**: `"State.OPEN" in src` +
  실제 판정식(`getattr(_ws_obj, "state", None)`) 존재 + `from websockets.protocol import State`
  import 존재. 이미 D1 `test_socket_state_guard_persists` 가 `"State.OPEN"` 을 요구하므로
  두 가드를 같은 강도로 맞추는 것이 정합적이다. 테스트명은 `…_in_leaf` 로 바꿔 의미 전환을 명시한다.
- `test_realtime_send_subscribe_unchanged` — 무수정(8영역 `_send_subscribe` 대상, 추출 무관).
  이 가드가 반대편에서 "근본 시정을 8영역에 넣지 않았다"를 봉인한다.

#### D-절차 (중요)

**D군을 2단계에서 먼저 초록으로 만든 뒤 B·C군 값을 옮긴다.** 값 핀을 먼저 옮기면
어느 실패가 구조 결함(D)이고 어느 것이 단순 값 드리프트(B·C)인지 구분이 안 된다.

---

### H군 — 무수정 통과해야 하는 행위 테스트 4파일 (위임부를 남기는 이유)

| 파일 | 케이스 | 왜 통과하는가 |
|---|---|---|
| `tests/unit/engine/test_cycle221_market_op_off_main.py` | 19 | 전부 `sched._subscribe_market_operation_tickers(...)` 호출 + `src.realtime.*` 원본 모듈 patch + `_LOGGER="src.engine.scheduler"` caplog. 메인 슬롯 확보 4 / tick 우선 6 / 슬롯 누수 5 / LMS chain 4 |
| `tests/unit/engine/test_market_op_subscribe_socket_guard.py` | 8테스트 10케이스 | 〃 (`test_guard_reads_socket_state_in_scheduler` 1건만 D4) |
| `tests/unit/engine/test_market_op_subscribe_import_regression.py` | 1 | 런타임 `delattr` 로 프로덕션 import 부재 재현 — **wrapper 가 실제로 leaf 본체를 태우는지 확인하는 유일한 런타임 증거**. 삭제·약화 금지 |
| `tests/unit/engine/test_cycle214_h0unmko0_pool.py` | 5 | `test_G_214_4_cap_default_is_60` 은 wrapper 시그니처 글자 복제로 통과 |

🔴 **하나라도 수정이 필요하면 그 자체가 행위 변경 신호다.** 전제 조건 둘:
(1) `import asyncio` + `asyncio.sleep(...)` 유지(§3.1) (2) logger 이름 `"src.engine.scheduler"`(§4).

**추가 의무** — `test_G_214_4` 와 같은 `cap` 기본값 핀을 **leaf 시그니처에도** 건다(§7 G-292-4).
wrapper 만 핀하면 vestigial `cap` 이 leaf 에서 조용히 사라질 수 있다.

---

### J군 — 문서 동기화 (Phase 4.8 `/sync-docs`, `report-writer` 실행)

1. 🔴 `src/engine/CLAUDE.md:67` — **`_PINNED_DIRS` 가 `src/engine/` 최상위 신규 파일을 막는다는
   서술을 정정**(§6-A 발견). 실제 차단자는 `_SRC_TREE_FILES`(cycle287 `test_s1b`) ·
   `_ENGINE_PY_FILES`(cycle290 `test_g290_3`) · `test_a8`(cycle291) 세 곳.
2. `src/engine/CLAUDE.md` 모듈 맵에 `market_op_subscribe.py` 1항 추가 +
   `market_operation_monitor.py` 절(`:27`)의 cycle214/221/230 서술에 **위임 사실 병기**
   (그 절이 `scheduler._subscribe_market_operation_tickers` 를 코드 위치로 인용한다).
3. `src/engine/market_operation_monitor.py:122` docstring 이 이 함수명을 인용 — 정정.
4. `docs/architecture.md` 스케줄러 절 + 엔진 모듈 목록.
5. "3,897L / 여유 3행" 서술 정직화 — `test_cycle257:17` · `test_cycle268:21` ·
   `test_cycle273b_ast_no_behavior_guards.py:11/156/179/205`("현재 3,898L") ·
   `test_cycle241_ast_silent_inactive_relative.py:381-382` · `test_cycle264_open_source_compare.py:36/70` ·
   `test_cycle273_daily_load_1810.py:22` · `test_cycle273b_selling_hold_observe.py:16/67` ·
   `test_cycle283_metrics_snapshot.py:22` · `test_cycle283_evening_window.py:28/456-458` ·
   `test_cycle291_pre_nxt_gtp.py:1117` · `test_cycle291_ast_scope.py:9` ·
   `_workspace/00_URGENT_WORKLIST.md:976` · `_workspace/00_leader_trading_rules.md` 대조.
6. `docs/HARNESS_CHANGELOG.md` append + 루트 `CLAUDE.md` 15행 표 상단 1행(+가장 오래된 1행 제거).
7. `python tools/test_impact/build_index.py` 재생성.
   ⚠️ `tools/test_impact/manual_overrides.yaml` 의 `"src/engine/scheduler.py": tests/integration/*`
   매핑은 leaf 로 **자동 승계되지 않는다** — 통합 시나리오 영향이 필요하면 leaf 항목을 명시 추가할지 판단.

**grep 오검출(손대지 말 것)**: `tests/unit/api/test_vi_status_quote_allowlist.py:40`(`FHPST01390000` 안의 `3900`) ·
`tests/unit/engine/strategies/test_cycle_p2a2_donchian_turtle.py:95`(가격 `53900`) ·
`tests/unit/engine/strategies/test_p1a_donchian_layered_exit.py:216`(`53_900`).

---

## 7. 새 회귀 가드 — `tests/unit/ast/test_cycle292_ast_market_op_leaf.py`

형식은 `test_cycle273b_ast_no_behavior_guards.py` 를 따른다. 그 파일 헤더의 **규약**을 승계:
`ast.dump` sha 핀 금지(3.12 CI ↔ 3.13 로컬) · `git grep`/`git ls-files` 금지(미추적 파일 실종) ·
**기준선 소실은 명시 FAIL**(vacuous PASS 차단 — `assert _LEAF_PATH.exists()` 를 모든 테스트가
먼저 통과해야 한다, cycle273b `_LEAF` 선례 `:155`).
모듈 레벨 sha dict 이름은 🔴 **`_BASE_SHA`** 로 한다 — `*_CONTENT_SHA` 로 지으면
`test_cycle223g3_ast_guard_sees_staged.py::test_g3_9a` 의 `_PIN_GUARD_FILES`(고정 4개 목록,
정규식 `^_[A-Z0-9_]+_CONTENT_SHA\s*(?::[^=]+)?=\s*\{`)와 불일치해 즉시 붉어진다.

| ID | 무엇을 잠그는가 | 형태 | 왜 필요한가 |
|---|---|---|---|
| **G-292-1** | leaf 의 **함수-로컬 import 5줄** — 6심볼이 `subscribe_market_operation_tickers` **함수 노드 안**에서 import 되고 **모듈 최상단에는 없다** | leaf AST: 함수 안 `ImportFrom`/`Import` 로 `ConnectionClosedError`·`State`·`MARKET_OP_TR_ID`·`MAX_SUBSCRIPTIONS`·`kis_ws`·`kis_ws_pool` 6개 전부 존재 ∧ 모듈 레벨 import 에서 그 6개 이름 0건 | §2.5 의 단일 최대 위험. `import_path_guard` 는 경로만 보므로 최상단 승격을 못 막고, 승격되면 부정 단언 6케이스가 **조용히 초록**이 된다 |
| **G-292-2** | leaf **logger 정체성** | `market_op_subscribe.logger.name == "src.engine.scheduler"` **+** 소스에 `getLogger("src.engine.scheduler")` 리터럴 존재 ∧ `getLogger(__name__)` 0건 | §4. `_DbLogHandler` 접두 = 운영 grep 사슬. 자매 = `test_f7_logger_identity_is_scheduler` |
| **G-292-3** | **위임 실재** — scheduler wrapper 가 leaf 를 부르고 본체를 재인라인하지 않았다 | scheduler.py 의 `_subscribe_market_operation_tickers` 노드: leaf 함수 호출 **정확히 1건** ∧ `ws.subscribe`/`kis_ws`/`kis_ws_pool`/`MARKET_OP_TR_ID` 참조 **0건** ∧ `State`·`state` 문자열 **0건**(D4 거짓 초록 차단) | 없으면 누군가 leaf 를 남긴 채 scheduler 에 **두 번째 사본**을 인라인해도 D군 가드가 못 잡는다(leaf 쪽은 초록, scheduler 쪽은 아무도 안 본다) |
| **G-292-4** | **`cap` 시그니처 양쪽** | `inspect.signature` 로 wrapper **와** leaf 둘 다 `cap` 기본값 `60` ∧ KEYWORD_ONLY | `test_G_214_4` 는 wrapper 만 본다. leaf 에서 vestigial `cap` 이 조용히 사라지면 요약 로그의 `cap=%d` 가 깨진다 |
| **G-292-5** | **마커 5종의 거처** | `[market_op_subscribe_skip]`·`[market_op_no_quote_session]`·`[market_op_subscribe]`·`[market_op_subscribe_summary]`·`[market_op_subscribe_no_slot]` 가 leaf 에 존재 ∧ `src/**/*.py` 중 leaf 밖 **0건** | `test_cycle274_ast_llm_gate.py:374::test_g1_4_markers_live_only_in_the_leaf` 선례. 마커가 두 곳에서 나오면 D+1 판독이 두 세대를 합산한다 |
| **G-292-6** | **라인 상한 + 정확 핀** | `scheduler.py` 라인 수 `== <실측>` ∧ `< 3900` | cycle292 자신의 무접촉 후속 증거(B군과 같은 역할, 다음 사이클용 기준선) |
| **G-292-7** | **leaf 는 scheduler 를 import 하지 않는다** | leaf AST: `src.engine.scheduler` 를 가리키는 `Import`/`ImportFrom` 0건 ∧ `sys.modules.get("src.engine.scheduler")` 0건 | `data_load_tasks.py:11-12` 배너 계약. cycle61 이 stale 계열에 넣은 `sys.modules.get` seam 은 **이번엔 불필요**하고(원천 모듈 patch 로 충분), 만들면 cycle61 D-2 의 "`sys.modules.get` 출현 6건 고정" 가드까지 건드리게 되어 해롭다 |

**1회용 — ✅ 대조 완료(2026-09-14), 폐기**: §3.2 의 변환 후 세그먼트 sha
`0343fe38c64aedb57cef27a2982deef21ef38347722fde2cdda3395a081543b6` 는 실측과 **일치**했다.
영속 가드에 편입하지 않았다(§3.2 배너 참조). 커밋 뒤 이 hex 는 기록 이상의 의미가 없다.

---

## 8. 금기

1. **행위 변경 0.** 로그 문구·레벨·로거 이름·필드 순서·`%` 인자 순서·호출 순서·예외 분기·
   구독 우선순위·`pop`↔`unsubscribe` 순서·커서 전진 조건·`sleep` 자리 — 한 글자도 바뀌지 않는다(§3.1).
2. **8영역 무접촉** — `src/engine/{risk,order_engine,session,scanner,strategy_registry}.py` ·
   `src/api/order.py` · `src/realtime/**` · `src/auth/**` **diff 0**. `market_operation_monitor.py` 도
   무접촉(§6-J 는 docstring 1줄 정정이며 그 파일은 8영역이 아니다 — 단 프로덕션 diff 를 늘리므로
   문서 단계에서 별도로 처리한다).
3. **커밋·push 금지.** 정규장 중 · 보유 11종목 · cycle232 D6. `src/**` 변경은 cycle248 분류상
   **full 모드**(backend 재생성 1~5분 tick blind). 장외 창 = **15:30~19:55** 또는 21:35 이후.
   ⚠️ **20:00~21:35 은 자율 구간 중에도 금지**(cycle283 D8).
4. **가드 완화 금지.** 구체적으로: 정확 라인 핀을 상한 핀으로 바꾸지 않는다 ·
   `cycle257` 의 `3900` 리터럴을 건드리지 않는다(상향 포함) · `scheduler.py` 를 `_BASE_SHA` 에서
   삭제하거나 `_CHANGED` 로 옮기지 않는다 · sha 핀은 6곳 **동시** 갱신 · D군 부정 단언 4건을
   "이미 초록이니까" 방치하지 않는다 · D4 를 docstring 으로 통과시키지 않는다 ·
   `test_quote_reserve_constant_absent` 의 스캔 면적을 scheduler 단독으로 두지 않는다.
5. **함수-로컬 import 5줄을 모듈 최상단으로 올리지 않는다**(§2.5). 두 줄 분리
   (`kis_ws`←websocket / `kis_ws_pool`←websocket_pool)도 유지.
6. **`_MARKET_OP_QUOTE_RESERVE` 예약 슬롯을 leaf 에 재도입하지 않는다**(cycle221 F1).
7. **후보 VI 배치를 되살리지 않는다**(cycle221 F2) · **메인 폴백을 만들지 않는다** ·
   **`kis_ws_pool.subscribe/unsubscribe` 를 쓰지 않는다**(F-P).
8. **leaf 에 `await`/DB/HTTP 를 새로 넣지 않는다** — 이동만 한다. `write_log` 0건 유지.
9. **`test_market_op_subscribe_import_regression.py` 를 삭제·약화하지 않는다** —
   wrapper 가 실제로 leaf 본체를 태우는지 확인하는 유일한 런타임 증거다.

---

## 9. 미해결 · 위험

### 9.1 🔴 가장 큰 위험 = 부정 단언의 조용한 소멸 (D군)

cycle221 의 계약은 전부 "…가 없어야 한다" 형태이고, **부정 단언은 검사 대상이 사라져도 초록이다.**
추출 직후 **3건이 시끄럽게 실패**(`test_G_214_5` · `test_socket_state_guard_persists` ·
`test_market_op_function_imports_pool_from_websocket_pool`)하므로 당일에는 알아차린다. 그러나
**가장 자연스러운 실수 경로**는 "붉어진 3건만 경로를 leaf 로 바꿔 통과시키고, 나머지 4~5건은
이미 초록이라 손대지 않는 것"이다. 그러면:

- 배포 후 누군가 leaf 안에서 `kis_ws.subscribe(..., bypass_limit=True)` 로 되돌려도 **스위트는 초록**이다.
- 08-19 실사고(메인 45/41 → OPSP0008 117건 → 보유 4종목 ~58분 tick blind = 손절 사각) 재발
  방지 가드 **전부**가 그 4건이다.

⇒ **D군 전부를 같은 커밋에서 재조준 + 양성 대조군**을 넣는다. 이것이 이 사이클의 유일한
설계 결정이고(0단계), 나머지는 기계적이다.

### 9.2 조사:참조테스트가 (B) monkeypatch 경로 의존으로 분류한 것 — **0건이었다**

이 함수의 모든 테스트는 **정의 모듈의 속성**(`src.realtime.websocket.*` /
`src.realtime.websocket_pool.*`)을 덮고, `src.engine.scheduler.*` 네임스페이스를 덮는 것은
**하나도 없다**(실측). 그래서 함수를 옮겨도 patch 경로를 고칠 필요가 없다.

**그러나 그 안전성은 §2.5 의 함수-로컬 import 유지에 전적으로 달려 있다.** 최상단으로 올리면
patch 가 무력화되고, 그때 조용히 초록으로 남는 것을 정확히 지목해 둔다:

| 파일 | 케이스 | 왜 공허하게 초록인가 |
|---|---|---|
| `test_cycle214_h0unmko0_pool.py` | `test_low_candidates_are_not_subscribed_at_all` | `SEND == []` · `n == 0` · `pool.subscribe` 0 · `kis_ws.subscribe` 0 — **조기 반환이 네 단언을 모두 만족**시킨다 |
| 〃 | `test_cap_is_vestigial_no_candidate_placement` | 같은 이유(`[]` + `n == 0`) |
| `test_market_op_subscribe_socket_guard.py` | `test_non_open_socket_skips_without_sending[closing/closed/connecting]` ×3 | `n == 0` + 모든 SEND `assert_not_awaited` + ERROR 0 — 조기 반환과 **구별 불가** |
| 〃 | `test_none_socket_still_skips` | `n == 0` 하나뿐 |

반대로 다음이 **시끄럽게 실패해 사고를 막는다**: `test_high_vi_never_touches_main`(배치 집합 ==
HIGH 2 양성 단언) · `test_no_bypass_limit_true_in_any_vi_call`(`assert calls,
"VI 구독이 아예 발생하지 않았다 — 픽스처/라우팅 확인"` 반공허 가드를 **이미** 갖고 있다 —
7파일 중 가장 잘 설계된 지점) · `test_open_socket_subscribes_normally`(`n == 2`) ·
`test_subscribe_market_op_does_not_raise_importerror`(`result == 2`) · cycle221 의 슬롯 누수·
LMS chain 델타 테스트들. **가드망은 살아 있지만, 살아 있는 이유가 몇 개의 양성 단언에 달려 있다.**

### 9.3 확신이 덜 선 것 / 남기는 판단

- **`market_op_subscribe.py` 의 최종 라인 수**는 헤더 서식(docstring 길이·공백)에 따라 ±3 흔들린다.
  §5.3 의 **3,726** 은 `scheduler.py` 쪽 산식이고 이쪽은 검증 대상이 아니다.
- **`test_s1d` 동어반복 시정**은 cycle292 범위 밖으로 남긴다(§6-A). 그 파일은 cycle287 의 무접촉
  증거라 손대면 계약 서술이 흐려진다. 별건 카드로 올린다. **대신 `src/engine/CLAUDE.md:67` 의
  거짓 서술은 이 사이클에서 반드시 고친다** — 그 문장을 믿고 다음 사람이 신규 파일 등록 3곳을
  건너뛰면 CI 에서 3건이 붉어질 뿐이지만, 더 나쁜 건 "이미 가드가 있다"고 믿어 **진짜 가드를
  만들지 않는 것**이다.
- **`manual_overrides.yaml` 승계**(§6-J-7): `scheduler.py → tests/integration/*` 매핑을 leaf 에도
  걸어야 하는지 판단이 필요하다. 이 함수는 KIS WS 구독을 SEND 하므로 통합 시나리오와 무관하지
  않지만, 기존에도 통합 테스트가 이 함수를 직접 태우는 곳은 없다(프로브에서 `tests/integration`
  483케이스 실패 0). **보수적으로 추가**하는 쪽을 권고하되 구현자 재량으로 남긴다.
- **cycle287 `_PINNED_DIRS` 에 `"src/engine"` 이 들어 있는 것 자체**는 이 사이클이 신규 leaf 를
  만드는 것과 **의도적으로 충돌한다**(그 주석: "자문 §9-B 는 신규 leaf 를 허용했지만 브리프
  제약이 세 파일뿐"). 그 제약은 **cycle287 의** 브리프 제약이고 cycle292 는 사용자 승인을 받은
  별 사이클이므로 등록으로 해소하는 것이 맞다. 다만 `test_s1d` 가 동어반복이라 그 의도가
  기계적으로 집행되고 있지 **않았다**는 사실을 changelog 에 남긴다.
- **`scheduler.py` 가 leaf 를 모듈 레벨로 import 하면 import 그래프가 한 노드 깊어진다** —
  `market_op_subscribe` 는 모듈 레벨에서 stdlib(`asyncio`·`logging`·`typing`)만 쓰므로 순환·
  부작용 0 이지만, 만약 구현 중 leaf 최상단에 `src.*` import 가 생기면 **그 즉시 함수-레벨
  import(형 B)로 되돌려야 한다**(§2.3 의 leaf 는 `src.*` 를 최상단에서 import 하지 않는 것이 전제).

### 9.4 조사 4갈래가 어긋난 지점과 채택

| 쟁점 | 갈림 | 채택 · 근거 |
|---|---|---|
| wrapper 형태 | 함수본체 = 함수-레벨 import(8줄) / 선례패턴 = 모듈-레벨(3~4줄) | **모듈-레벨 + 기존 줄 합류, 위임부 5줄**(§5.1-c). 최신 선례 4개가 모여 있는 `:41-43` 블록이 같은 목적("라인 상한 보호")을 명시 + leaf 가 scheduler 를 import 하지 않아 순환 0 + 1줄 싸다. 함수본체안의 8줄 wrapper 는 3줄 과다 |
| 착지 라인 수 | 3,729 / ~3,726 / 3,725 | **3,726**. 176 제거 · 5 추가 · import 합류 0 으로 산식을 명시했다(§5.3). 구현 후 실측이 정본 |
| logger 관례 | 양쪽 모두 "블랭킷 관례" 로 서술 | **선례가 균일하지 않다**(실측: `__name__` 6파일). 판별 기준을 §4.2 에 명문화했다 — "기존 마커는 이름 고정, 신규 마커는 `__name__`". cycle292 는 전자 |
| `_PINNED_DIRS` 차단력 | 함수본체·선례패턴은 언급 없음 / 핀·가드지형 = 거짓 | **거짓 확정**(`test_s1d` 양변 디스크 유래, 프로브 2회 통과 실증). 문서 정정 대상(§6-A) |
| 실패 가드 전수 | 핀·가드지형 = 빈 파일 프로브 15건 | **실내용 프로브로 재검증**: 신규 파일 3건 + (scheduler 미변경이라 미발화한) 라인 6 · sha 6 = 15 동일 ∧ **내용-스캔 가드 트립 0** 을 추가 확증 |
| 마커 배타 가드 선례 위치 | 핀·가드지형 = cycle276 `test_c26_1` | 실측 정본은 `test_cycle274_ast_llm_gate.py:374::test_g1_4_markers_live_only_in_the_leaf` |

---

## 부록 — 권고 실행 순서

0. **(사람의 판단)** §6-D 재조준 설계 확정. leaf 경로로 **교체**하고 wrapper 에는 아무 봉인도 걸지
   않는다(걸는 순간 공허해진다 — 대신 G-292-3 이 wrapper 를 양성 단언으로 잠근다).
1. **프로덕션 확정** — leaf 생성(logger 명시 · 함수-로컬 import 5줄 byte 동일 · 본체 라인 단위
   동일) → wrapper 교체 → import 합류. 직후 §3.2 변환 sha 대조 +
   `wc -l src/engine/scheduler.py` · `ls src/engine/*.py | wc -l` · `shasum -a 256` 기록.
2. **D군 4파일 재조준** → `pytest tests/unit/ast tests/unit/engine` 로 **D 실패 0** 확인.
3. **A군 3곳** 신규 파일 등록(148→149 · tuple 사전순 삽입 · 60→61).
4. **B군 6곳** 라인 핀(+ `test_c5_2` 개명).
5. **C군 6곳** sha 핀 — **한 값을 동시에** + cycle287 `_SRC_TREE_DIGEST` 재산출:
   ```
   python3 -c "import hashlib,os,pathlib;h=hashlib.sha256();C={'src/models/order.py','src/engine/order_engine.py','src/api/order.py'};n=0
   [ (h.update(r.encode()),h.update(b'\0'),h.update(hashlib.sha256(p.read_bytes()).digest())) for p in sorted(pathlib.Path('.').glob('src/**/*.py')) for r in [str(p).replace(os.sep,'/')] if r not in C ]
   print(h.hexdigest())"
   ```
   (작성 시점 재현값 = 파일 148 / `d491c518cb200717246577be3bcfd904c854f9a6c9fe625e28f639666477a277`
   = 현 핀과 일치 확인 → 알고리즘이 맞다는 증거)
6. **§7 신규 가드 7건** 작성(dict 이름 `_BASE_SHA`).
7. **문서 동기화**(§6-J) — `report-writer` 위임.
8. **검증** — `pytest tests/unit/ast tests/unit/engine`(§6 전수 초록) → `python -m pytest -q` 전체 →
   `python tools/test_impact/build_index.py`.
9. **정지.** 커밋하지 않는다.
