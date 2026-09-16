# cycle295 — 갭 홀드 제거 + 15:30~16:00 완전 휴식 명세

> **작성 2026-09-15 · 이 문서는 명세다. 코드 변경 0.**
> 선행 = 오늘 **15:38~16:04 다이얼 OFF 실측**(§8-1). 그 실측 전에 (B) 를 착수하지 않는다.
> 이 문서가 `_workspace/red/cycle295_market_rest_window_spec.md`(같은 날 작성된 초안)를
> **대체**한다. 두 문서가 갈리는 지점은 §3-2 에 명시했다 — 초안의 라우터 내부 clause 5.5 는
> 실행값으로 기각됐다.

**표기 규약** — `[실측]` = 이 리포에서 실행하거나 파일을 열어 확인한 값. `[추정]` = 코드
구조에서 추론했으나 실행·로그로 확인하지 못한 것. `[미실측]` = 답이 없는 것. 이 셋을
섞어 쓰지 않는다.

---

## §1 왜 — 사용자 결정과 그것을 넘은 경위

### 1-1 cycle294 명세가 못박은 것

`_workspace/red/cycle294_stage3_time_axis_spec.md` §0 = **"이미 정해진 것(재론 금지) —
통합 채널 폐기 · 구간표 · 전환 1회"**. 같은 문서 824행 = "15:40~16:00 … NXT 로 전환하지
**않는다**(§0)". 828행 = "우리는 KRX 채널을 유지한다 … **D+1 판독 항목으로 올린다**".

### 1-2 착지 직후에 일어난 일

적대 검증이 그 항목을 CRITICAL-1 로 올렸다. 그 지적의 **사실**은 참이다 —
15:40~16:00 은 KRX 에 연속 체결이 없고 NXT 애프터만 continuous 이므로, 그 구간을 KRX
채널로 덮으면 `nxt_true` 보유의 손절 트리거가 매일 20분 사라진다.

메인 세션이 그 지적을 **승인 없이** 받아들여 전환 창을 1개에서 3개로 늘렸다 —
`pre_to_krx` + `krx_to_nxt_gap`(15:40~16:00) + `nxt_gap_to_krx`(16:00~16:05). 킬스위치
`tick_channel_gap_hold_enabled`(기본 `true`)를 달았다. **다이얼은 승인을 대신하지 않는다.**

### 1-3 2026-09-15 사용자 결정 (원문)

> "청산측으로도 참여를 하지 않고자 해. **15:30~16:00 은 완전 휴식**하도록 변경해야해."
>
> "`tick_channel_gap_hold_enabled` 변수와 그 변수를 케어하는 로직 … 시스템 복잡도를
> 올리는 수준이라면 제거하고 싶어."

같은 날 10:0x 에 `PUT /api/realtime/tick-channel-mode {"mode":"enforce","gap_hold_enabled":false}`
→ `gap_persisted: true`. 다이얼은 지금 꺼져 있고 DB 에 영속됐다. [실측]

### 1-4 이 사이클의 성격

**되돌리는 사이클이다.** cycle294 CRITICAL-1 의 *사실*은 유효하고 *시정*만 철회된다.
사용자는 그 20분의 손절 커버리지 손실을 **비용으로 수용**했다. 이력은 지우지 않고
철회 문장을 덧붙인다(§6-4).

### 1-5 🔴 "다이얼이 꺼져 있으니 순수 제거" 는 부정확하다

브리프와 초안이 "(A) 는 오늘 돌고 있는 상태 대비 행위 변경 0" 이라고 적었으나, 다이얼
OFF 는 **재시작을 못 견딘다**. [실측]

- `tick_channel_mode.py:97` `DEFAULT_GAP_HOLD_ENABLED = True`, `:106` 프로세스 기본값 True.
- DB 의 `false` 를 메모리에 심는 경로 = `refresh_switch_params()` 하나. 프로덕션 호출자는
  `src/engine/stale_watcher_core.py:257` **단 하나**다(`grep -rn refresh_switch_params src/`
  = 정의 1 + 호출 1). ⚠️ `src/db/CLAUDE.md:145` 의 "5분·120초 폴링" 서술은 **거짓**이다 —
  `scanner.subscribe_filtered_stocks` 는 `refresh_mode()` 만 부른다.
- `_stale_watcher_loop` 는 `await asyncio.sleep(...)` 을 먼저 하므로 기동 후 최초 반영이 **+120초**.

⇒ 15:36 에 backend 가 재생성되면(루트 CLAUDE.md 가 지금 15:30~19:55 를 배포 창으로
허용한다) 최대 ~120초 동안 갭 홀드가 **재무장**되고, 그 사이 HIGH 로 발사된 보유 구독은
`switch_windows()` 가 W1 만 돌려주는 상태로 돌아간 뒤에도 **되돌릴 창이 없어**
20:00 `unsubscribe_all` 까지 NXT 에 남는다. [추정 — 코드 경로 확인, 라이브 미재현]

⇒ (A) 축의 정당화 문장은 "행위 변경 0" 이 아니라 **"다이얼이 끌 수 없는 잔여 경로를
구조적으로 0 으로 만든다"** 이다. (B) 승인을 기다릴 이유가 없다.

---

## §2 무엇을 바꾸나 — 네 축으로 가른다

| 축 | 내용 | 8영역 | 승인 |
|---|---|---|---|
| **(A)** | 갭 홀드 코드 제거 (시세 채널 축) | 코드는 전부 밖 · **문서 `src/realtime/CLAUDE.md` 는 안** | 문서 1건 |
| **(B)** | 15:30~16:00 명시 주문 컷 | `src/engine/order_engine.py` **1파일** | 필요 |
| **(C)** | `_get_bool_or_none` 왕복 불변식 시정 | `src/db/system_config.py` — **밖** | 불요(사용자 승인 완료 2026-09-15) |
| **(D)** | 손절 잔여 재주문 매핑 등록 | `src/engine/order_engine.py` (B 와 같은 파일) | 필요(승인 완료 2026-09-15) |

(A) 와 (B) 를 한 커밋에 묶지 않는다 — (A) 가 (B) 승인을 기다리게 되기 때문이다.
**(C) 는 (A) 보다 먼저 간다**(§2-0 참조). (D) 는 (B) 와 같은 파일이라 (B) 커밋에 함께 넣는다.

### 2-0 🔴 (C) 를 가장 먼저 하는 이유 — 킬스위치가 "끄면 켜진다"

**2026-09-15 실증.** 10:0x 에 `PUT {"mode":"enforce","gap_hold_enabled":false}` 를 보냈고 응답이
`gap_hold_enabled: false · gap_persisted: true` 였다. 그런데 **15:41:56 에 갭 전환 7건이 그대로
일어났다**(`[tick_channel_switch] ... from=H0STCNT0 to=H0NXCNT0 mode=high` ×7 +
`[tick_channel_switch_summary] window=krx_to_nxt_gap`).

원인 = **setter 와 getter 의 왕복 불변식 파괴**.

```
set_tick_channel_gap_hold_enabled(False)
  → _set_string(key, "false")          → DB: {"value": "false"}   ← 문자열
_get_bool_or_none(key)
  → raw = {"value": "false"}  (dict)
  → isinstance(raw, dict) 분기 진입
  → return bool(raw.get("value")) = bool("false") = True          ← 🔴
```

`_get_bool_or_none` 은 바로 아래에 `"true"/"false"` 문자열 정규화 분기를 갖고 있지만
(`system_config.py:237-242`), **dict 로 감싸인 값은 그 분기에 도달하지 못한다**. PUT 직후에는
`apply_gap_hold_enabled(False)` 가 메모리를 직접 덮어 False 지만, 5분·120초 `refresh_switch_params()`
가 DB 를 다시 읽어 `bool("false")=True` 로 **되돌린다**.

**영향 범위 = cycle294 가 만든 bool 다이얼 2개뿐** [실측]:

| setter | 저장 방식 | 왕복 |
|---|---|---|
| `set_dkstock_regime_enabled` | `_set_bool` | ✅ |
| `set_kis_mcp_enabled` | `_set_bool` | ✅ |
| `set_auto_start` | JSONB `{"value": bool}` | ✅ |
| `set_tick_channel_switch_enabled` (`:793`) | `_set_string("true"/"false")` | 🔴 |
| `set_tick_channel_gap_hold_enabled` (`:822`) | `_set_string("true"/"false")` | 🔴 |

⚠️ `set_auto_start` 의 docstring 이 이 함정을 이미 경고하고 있었다 —
*"JSONB `{"value": bool}` — `get_auto_start` 의 `raw.get("value")` 파싱 계약과 정합
(**왕복 불변식 = split-brain 해소 핵심**)"*. cycle294 가 그 관례를 답습하지 않았다.

**즉시 조치(2026-09-15 실행 완료)** — DB 값을 JSON boolean 으로 교체했다:
`{"value": "false"}` → `{"value": false}` (`jsonb_typeof(value->'value') = boolean` 확인).
이것은 **우회**이고 코드 결함은 그대로다 — 누구든 다시 PUT 하면 문자열로 되돌아간다.

**(C) 시정** — `_get_bool_or_none` 의 dict 분기가 문자열을 정규화하게 한다(아래 셋 중 택일,
권고 = ①+②):
① dict 분기에서 꺼낸 `v` 를 기존 문자열 정규화 경로로 흘려보낸다(한 곳만 고쳐 모든 키가 이득)
② 두 setter 를 `_set_bool` 로 바꾼다(cycle294 가 답습했어야 할 관례)
③ 회귀 가드 = **왕복 불변식 테스트** — 모든 bool 다이얼에 대해 `set(False)` → `get()` 이
   `False` 인지 실 PG 로 단언한다. `switch_enabled` 는 현재 DB 에 행이 없어 잠복 중이므로
   이 가드가 없으면 같은 결함이 다음에 또 잠복한다.

**⚠️ (C) 는 cycle295 가 `gap_hold` 를 제거해도 필요하다** — `tick_channel_switch_enabled` 가
같은 결함을 그대로 갖고 남기 때문이다(그 킬스위치도 지금 작동하지 않는다).

### 2-0b (D) 손절 잔여 재주문이 매핑을 남기지 않는다

**2026-09-15 확인.** `order_engine.py` 의 프로덕션 `place_order` 호출 5곳 중 **`:2505` 하나만**
반환값을 버린다.

```
:906   result = await place_order(...)   →  매수 6종 등록
:1035  result = await place_order(...)   →  매수 폴백 5종
:1305  result = await place_order(...)   →  매도 5종 + _completed_orders.discard
:1645  fb_result = await place_order(...)
:2505  await place_order(**place_kwargs) →  🔴 0종
```

그 자리는 `_cancel_and_reorder`(`:2420`, `PARTIAL_FILL_WAIT=30` 뒤 잔여 취소 후 재주문,
유일 호출자가 `is_stop_loss=True`)다. 매핑이 없으면 그 재주문의 체결통보가:

```
_order_strategy.get(order_no)          → miss
_lookup_strategy_from_trade_history()  → miss (재주문은 trade_history INSERT 도 없다)
:2233  strategy_id = "momentum"        → 🔴 매도 전략 오귀속
```

추가로 `_order_qty` 부재 때문에 `ordered_qty` 가 통보 수량으로 대체돼(`:1877`)
**부분 체결이 전량 체결로 읽힌다**.

**시정 = 나머지 4곳과 같은 모양.** 필요한 값이 **전부 이미 그 스코프에 있다** [실측] —
`strategy_id`(`:2430`) · `ex`(`:2434`) · `ticker`/`remaining`(인자) · `reorder_division`.

```python
result = await place_order(**place_kwargs)
if result is not None and getattr(result, "order_no", None):
    self._order_qty[result.order_no] = remaining
    self._order_strategy[result.order_no] = strategy_id
    self._order_ticker[result.order_no] = ticker
    self._order_exchange[result.order_no] = ex
    if reorder_division is not None:
        self._order_division[result.order_no] = reorder_division.value
    self._completed_orders.discard(result.order_no)
```

⚠️ `strategy_id` 는 `:2430` 에서 `"momentum"` 폴백을 이미 탈 수 있다(원주문 매핑이 없을 때).
(D) 가 고치는 것은 **재주문이 원주문의 전략을 승계하지 못하는 것**이고, 원주문 매핑 자체의
결손은 별개다.

⚠️ 이 결함은 **4단계(프로세스 분리)와 무관하게 오늘 라이브에 도달 가능**하다 — 발화 조건은
"손절 주문이 부분체결되는 것" 하나다.

### 2-1 (A) 제거 대상 — 파일:행 [실측, `ast` 산출]

**`src/engine/tick_channel_clock.py`** (609L → ≈494L)

| 심볼 | 행 | 행수 | 비고 |
|---|---|---|---|
| `_spans()` | 178-183 | 6 | 유일 호출자 = `nxt_only_continuous_window` |
| `_subtract()` | 186-200 | 15 | 동상 |
| `nxt_only_continuous_window()` | 203-248 | 46 | 복잡도의 본체(두 시장 연속 구간 집합 빼기 + 최장 조각 + 날짜 메모) |
| `gap_hold_enabled()` (위임) | 251-262 | 12 | |
| `in_nxt_gap()` | 340-350 | 11 | |
| `switch_windows()` 안 `if gap_hold_enabled():` 블록 | 376-392 | 17 | W2·W3 생성부 |
| `clock_channel()` 안 갭 분기 | 330-332 | 3 | |
| `REASON_NXT_GAP_WINDOW` | 88 | 1 | 값 `"nxt_gap_window"` |
| `_GAP_MEMO` | 112, 216, 247, 605 | 4 | `reset_state_for_test` 의 `.clear()` 포함 |
| `_EPOCH_DAY` | 115, 240-241 | 1 | 갭 함수의 최장 조각 비교 전용 |
| `emit_clock_config()` 의 `nxt_gap=`·`gap_hold=` 필드 | 491, 497 | ~4 | **카나리아 나머지 4필드는 남긴다** |
| 모듈 docstring 의 `## 🔴 적대 검증 CRITICAL-1` 절 + `clock_channel` docstring 갭 문단 | — | ~35 | §6-4 대로 **재서술**(삭제 아님) |

**`src/engine/tick_channel_mode.py`** (361L) — `GAP_HOLD_ENABLED_KEY`(93) ·
`DEFAULT_GAP_HOLD_ENABLED`(97) · `_gap_hold_enabled`(106) · `gap_hold_enabled()`(121-123) ·
`refresh_switch_params` 안 블록(224·236-242) · `apply_gap_hold_enabled()`(279-283) ·
`reset_state_for_test`(319·322) · `_set_switch_params`(351·355). ≈ 25행.

**`src/db/system_config.py`** — `_TICK_CHANNEL_GAP_HOLD_ENABLED_KEY`(780) ·
`get_tick_channel_gap_hold_enabled()`(807-819) · `set_...`(822-825). 18행.

**`src/routes/realtime.py`** — 요청 선택 필드(901) · `_nxt_gap_window_repr()`(904-914) ·
GET 응답 3키(955-957) · PUT 분기(1007-1018) · `[tick_channel_mode]` 로그의
`gap_hold=`·`gap_persisted=`(1022-1023) · `failed` 항목(1029) · PUT 응답 2키(1040-1041). ≈ 36행.

**합계 프로덕션 ≈ 173행 + docstring/주석 ≈ 60행.**

### 2-2 (A) 접촉하지 않는 것 [실측 — grep 0건]

- `src/engine/tick_channel_switch.py`(595L) — gap 토큰 **0건**. 창 목록을 label 문자열로
  받아 로그·반환 dict 에만 쓴다. 창이 3→1 로 줄어드는 것을 소비자로서 그냥 받는다. **diff 0**.
- `src/engine/risk.py` · `src/engine/stale_watcher_core.py` — 0건.
- `frontend/src` · `e2e` · `tools` — 0건. **프론트 사이클이 딸려오지 않는다.**
- 테스트 = `tests/unit/engine/test_cycle294b_adversarial_fixes.py` **단일 파일**(:114-115, :139).

### 2-3 🔴 `clock_channel(..., priority=)` 는 남긴다

갭 분기(:332)가 `priority` 의 **유일한 사용처**다. 지우면 시그니처가
`scanner._resolve_channel`(:686) ← `tick_tr_id_for`(:740) ← `tick_channel_switch`(:197,:381,:555)
← `stale_watcher_core`(:76,:494,:838) 체인으로 연쇄 변경되고 `scanner.py` 는 **8영역**이다.
승인 파일 1개를 아끼는 쪽이 낫다.

⚠️ 남기면 다음 사람이 `tick_tr_id_for(t, priority="HIGH")` 를 보고 "HIGH 는 다른 채널로
간다" 고 오독한다 — 그것이 정확히 cycle294 가 만들고 cycle295 가 없애는 사실이다. 그래서
docstring 을 **지우지 말고 재서술**한다:

> `priority` 는 3단계 시각축에서 **판정에 쓰이지 않는다**. 코호트 축(`scanner`)만 본다.
> 시그니처는 `scanner.py`(8영역) diff 0 을 위해 유지한다.

그리고 가드 G-D2(§5)가 `priority="HIGH"`/`"LOW"` 가 하루 1,440분 전부에서 같은
`(tr_id, reason)` 을 냄을 **양성 대조군과 함께** 단언한다.

### 2-4 DB 고아 행 — 남긴다 [실측]

`system_config.tick_channel_gap_hold_enabled='false'` 행은 코드 제거 후 읽는 곳이 0 이 된다.
`system_config` 를 읽는 SQL 은 리포 전체에 정확히 둘 — 단건 `WHERE key = $1`
(`src/db/system_config.py:72`)과 bulk `WHERE key = ANY($1::text[])`(:952, `task_last_success_`
접두를 자기가 조립하고 결과도 그 접두로 필터). 전량 덤프 라우트 0건. 마이그레이션에
이 키를 seed 하는 SQL 도 0건.

⇒ 어디에도 노출되지 않는다. **DELETE 하지 않는다** — 되돌리기 어려운 운영 조치(승인
대상)이고 얻는 것이 0행이다. 대신 `src/db/CLAUDE.md` 에 1행:

> `tick_channel_gap_hold_enabled` — cycle295 로 소비처 소멸. 값 `false` 잔존.
> **이 키 이름 재사용 금지**(같은 이름을 반대 의미로 되살리면 저장된 `false` 가 조용히 적용된다).

### 2-5 (B) 신설 — `src/engine/order_engine.py` 1파일

1. 모듈 레벨 순수 술어 `_market_rest_now(now) -> tuple[bool, str]` (§3)
2. `execute_sell` 발사점 게이트 1블록
3. `execute_buy` 발사점 게이트 1블록 (§9-Q5 결정 대상)
4. `_cancel_and_reorder` 의 **쌍 게이트** 1블록 (§3-5)
5. 관측 마커 2종 (§3-6)

`_route_exchange_by_clock` 본체 7절 = **byte 동일**. `_apply_clock` = **byte 동일**.
`_cancel_after_wait`·`cancel_remaining` = **byte 동일**.

---

## §3 주문 컷 설계

### 3-1 선결 조건 확인 — 브리프가 요구한 clause 6 전수 확인 [실측]

`_route_exchange_by_clock(base, side=, mode="enforce", now=)` 를 1분 간격 1,440분 ×
base∈{SOR,NXT,KRX} × side∈{buy,sell} × 2날짜로 전수 실행했다.

**2026-09-15 (K6 발효 후 = 앞으로의 매일), base=SOR/NXT, side 무관:**
```
00:00 both_unsupported_keep
08:00 pre_nxt_keep
09:00 (KRX, krx_by_clock)
15:30 both_unsupported_keep
15:40 krx_unsupported_keep
16:00 (KRX, krx_by_clock)
20:00 both_unsupported_keep
```
**2026-09-11 (K6 발효 전):** `15:40 krx_unsupported_keep` 이 **20:00 까지** 이어진다.
**base=KRX:** 하루 전체가 `('KRX','base_krx')` 단일 세그먼트.

판정:
1. `krx_unsupported_keep` 은 09-14 이후 **15:40~16:00 단독**이다. (c) 는 과잉 차단이 아니다.
2. 🔴 **프리장 08:00~09:00 은 clause 4 `pre_nxt_keep` 이 먼저 잡는다.** 08:50~09:00(NXT N2
   휴장)도 마찬가지다 — `boards_at` 의 PRE_NXT 보드가 09:00 까지이기 때문이다. 프리장은
   과잉 차단 대상이 아니다.
3. 사용자 지시 구간의 **앞 10분(15:30~15:40)은 clause 7 `both_unsupported_keep`** 이고
   그 라벨은 야간(00:00~08:00·20:00~24:00)도 덮는다. `krx_unsupported_keep` 하나만 막으면
   **사용자 결정을 절반만 이행**한다.

### 3-2 🔴 (c) 를 라우터 **안**에 넣으면 안 된다 — 결정적 반증 [실측]

초안(`cycle295_market_rest_window_spec.md`)은 clause 5 와 6 **사이**에 clause 5.5 를
넣자고 했다. 실행값이 그것을 기각한다.

실매도 경로 `_strategy_exchange_async`(order_engine.py:606-645)는
`_probe_nxt_downgrade_base` 를 **먼저** 호출하고, 그 함수는 `stock_master.nxt_tradable=False`
종목에 `return "KRX"` 한다. 그 코호트는 라우터에 `base="KRX"` 로 들어가 **clause 1
`base_krx` 에서 즉시 반환**된다 — clause 5·5.5·6·7 어디에도 닿지 않는다.

`nxt_false` 는 마스터의 **83.2%** 다(루트 CLAUDE.md cycle293 행). 즉 **컷이 가장 필요한
다수 코호트가 컷을 통째로 비껴간다.** clause 5.5 를 clause 1 **앞**으로 올리면 시각축이
거래소축을 덮어 `base_krx` 의 의미(= `nxt_tradable=False` 다운그레이드 보호,
`_CLOCK_ROUTED_BASES` 주석이 명시)가 무너진다.

**추가로** — 라우터 결과는 취소 3경로(`_cancel_after_wait`:2370 · `_cancel_and_reorder`:2436 ·
`cancel_remaining`:2550)가 `_order_exchange[order_no]` 매핑 부재 시 `_apply_clock` 으로
fail-open 할 때도 쓰인다. 라우터가 "거부"를 내면 그 세 경로가 취소할 거래소를 못 얻는다.

⇒ **(c′) 채택**: 라우터는 무접촉, 같은 출처를 읽는 별도 술어를 **주문 발사점**에만 건다.
(a)(갭 함수 존치 + W2/W3 만 제거)와 (b)(order_engine 전용 시각 계산 신설)는 §3-7 에서 기각한다.

### 3-3 술어 — `_market_rest_now`

```python
# src/engine/order_engine.py — 모듈 레벨, 순수·never-raise
def _market_rest_now(now: datetime) -> tuple[bool, str]:
    """사용자 결정 2026-09-15 — 프리장은 NXT, 그 밖에는 KRX 가 우리 호가유형을
    받을 때만 주문한다. 「15:30~16:00 완전 휴식」은 그 규칙의 따름정리다.

    (가) 사실 — 15:40~16:00 은 KRX 에 연속 체결이 없고 NXT 애프터만 continuous 다
         (`market_state.MARKET_TABLE` 파생).
    (나) cycle294 의 판단 — 따라서 그 구간을 KRX 로 덮으면 `nxt_true` 보유의 손절
         커버리지가 사라진다. **이 문장은 여전히 참이다.**
    (다) 2026-09-15 사용자 결정 — "청산측으로도 참여를 하지 않고자 해.
         15:30~16:00 은 완전 휴식." 그 커버리지 손실을 **비용으로 수용**했다.
         결함이 아니라 결정이다. 되돌리기 전에 `_workspace/00_URGENT_WORKLIST.md`
         의 2026-09-15 결정을 확인하라.
    """
    try:
        from src.engine.market_state import get_market_state
        from src.engine.session import MarketBoard, boards_at, session_tracker

        active = session_tracker.active or boards_at(now.time())
        if MarketBoard.PRE_NXT in active and MarketBoard.MAIN not in active:
            return False, "pre_nxt_keep"          # 프리장 예외 — 라우터 clause 4 와 같은 출처

        krx = get_market_state(now, market="KRX")
        if _SENDABLE_DIVISIONS & set(krx.order_divisions):
            return False, "krx_sendable"          # KRX 가 우리 호가유형을 받는다

        nxt = get_market_state(now, market="NXT")
        if not krx.order_divisions and not nxt.order_divisions:
            return False, "no_session"            # 야간 — 현행 유지(검증된 안전망)

        return True, "market_rest"
    except Exception:
        return False, "probe_error"               # fail-open
```

**설계 근거 6**

1. **시각 리터럴 0건 유지** — 새 시각 계산이 0이다. 경계는 `MARKET_TABLE` 뿐이고
   `nxt_only_continuous_window()` 의 46행 집합 빼기가 **필요 없어진다**(⇒ §2-1 삭제 가능).
2. **base·side·mode 무관** — 창은 시계의 성질이지 방향·거래소·다이얼의 성질이 아니다.
   `nxt_false` 코호트(83.2%)도 똑같이 걸린다 — §3-2 의 구멍이 구조적으로 없다.
3. **프리장 예외를 라우터와 **같은 출처**로 판정** — `session_tracker.active`, 캐시가 비면
   `boards_at`. 라우터 clause 4 의 cycle287 적대 검증 시정(기동 직후 첫 tick 전 빈 집합)을
   그대로 답습한다. `market_state` 의 NXT phase 로 판정하면 08:50~09:00 에 갈린다.
4. **야간 가드** — 00:00~08:00·20:00~24:00 의 현행 동작(주문 발사 → APBK0918 →
   `is_market_closed_rejection` → 포지션 보존 + `_pending_next_day_clear` 전환)은 검증된
   안전망이라 이 사이클이 건드릴 이유가 없다. 15:30~15:40 은 KRX `order_divisions=('06',)`
   가 비지 않아 이 가드를 통과하고 컷에 걸린다 — **시각 리터럴 없이 두 구간이 갈린다.**
5. **새 다이얼 0개** — 사용자가 없애자고 한 것이 다이얼이다. `order_exchange_clock_mode`
   에도 **종속시키지 않는다**(§9-Q1 결정 대상, 권고 = 무종속).
6. **fail-open** — 판정 예외는 현행 유지. fail-closed 는 P0-1 유령 키가 두 전략을 전 기간
   체결 0건으로 만든 그 방향이다.

### 3-4 술어 실행값 [실측]

같은 로직을 1분 간격 1,440분 × 5날짜로 실행했다.

| 날짜 | 컷 구간 |
|---|---|
| 2026-09-15 | **15:30~16:00** |
| 2026-09-16 | **15:30~16:00** |
| 2026-11-19 | **15:30~16:00** |
| 2026-12-01 | **15:30~16:00** |
| 2026-09-11 (K6 미적용) | 🔴 **15:30~20:00 (4시간 30분)** |

세그먼트(09-15): `00:00 no_session / 08:00 pre_nxt_keep / 09:00 krx_sendable /
15:30 market_rest / 16:00 krx_sendable / 20:00 no_session`.

⇒ 사용자 지시 구간과 **정확히 일치**한다. 정상 매매 구간(프리장·정규장·KRX 애프터)은
하나도 걸리지 않는다.

⇒ 🔴 K6(`effective_from=2026-09-14`) 가 표에서 사라지면 컷이 **4시간 30분**으로 벌어진다.
가드 G-E5(컷 길이 ≤ 30분)와 **테스트 날짜를 2026-09-14 이상으로 pin** 하는 것이 필수다.

### 3-5 게이트를 거는 자리 — 발사점 3곳, 취소는 성질별로 가른다

**① `execute_sell`** — 자리 = `target_exchange` 산출(:1198/:1200) **직후**, 재시도 루프
(`for attempt in range(1, SELL_MAX_RETRIES+1)`, :1303) **앞**.

```python
blocked, why = _market_rest_now(now_kst)
if blocked:
    <마커 1회/(ticker,"sell")/일>
    self._selling.discard(ticker)
    self._selling_since.pop(ticker, None)
    return
```

그 자리인 이유 — (a) 루프 밖 1회 판정이라 주 `place_order`(:1305)와 시장가 거부 폴백
`place_order`(:1645)를 **한 번에** 덮는다. 게이트를 `place_order` 호출부마다 걸면 "1차는
나가고 폴백만 막히는" 반쪽 상태가 생긴다. (b) 포지션 실재가 확인된 뒤라 마커가 의미
있다. (c) 기존 진입 게이트 3종의 `self._selling.discard(ticker); return` 관례(:1169/:1175/:1181)
를 그대로 답습한다.

남는 누수 = 15:29:57 에 진입한 호출이 백오프(1s·2s)로 15:30:0x 를 넘기는 **최대 ~3초**.
허용한다 — 그 3초를 얻으려고 게이트를 루프 안으로 옮기면 반쪽 상태가 생겨 더 나쁘다.

🔴 **하지 말아야 할 것 4** (전부 계약의 핵심):
- `SellRejectionTracker.register_*` 를 부르지 않는다 — **거부가 없었다.**
- `_pending_next_day_clear` 로 전환하지 않는다 — 16:00 KRX 애프터가 열리므로 익일까지
  미룰 이유가 없다.
- 포지션·`high_since_buy`·재시도 카운터를 손대지 않는다.
- `_selling` 을 **유지하지 않는다** — 유지하면 그것이 곧 stale `_selling` 좀비(= 손절
  마비). 09-08 필옵틱스 161580 이 6시간 45분 26초 잠겼던 그 기전이다.

**회복 경로** = 16:00 KRX 애프터 개장 → `H0STCNT0` 연속 체결 프레임 → `risk.on_tick` 재평가
→ cycle287 의 `44`/`41` 경로로 발사. 컷은 **취소가 아니라 최대 20분 유예**다.
⚠️ `risk.py` 에 "그날 이미 청산 신호를 냈다" 류의 일일 래치는 **없다**
(`grep -n "_exit_signaled|_exit_latch|sold_today|_stop_loss_sent|_exit_emitted" src/engine/risk.py`
= 무결과) [실측]. 그래도 재발사 실증은 §5 통합 테스트 T10 의 몫이다.

**② `execute_buy`** — 자리 = 중복매수 가드 직후, `get_buyable` **앞**, 거래소 해석(:790) 앞.
🔴 A-ATOMIC 구간(`calc_buy_quantity`:741 ~ `pending_buys.add`:781-783, await 0건)을 **byte
동일**로 남기려면 그 구간 밖이어야 한다. 그 창의 매수는 현재 구조적 0(LTV 운영 DB
`tradable_boards=["main","pre_nxt"]`)이라 **순수 방어선**이다. 착수 여부는 §9-Q5.

**③ `_cancel_and_reorder` — 🔴 쌍으로 판정한다(취소도 하지 않는다).**

취소 3경로 중 이것만 다르다. `_cancel_after_wait`·`cancel_remaining` 은 **순수 취소**라
노출 축소이므로 무접촉이다. 그러나 `_cancel_and_reorder`(:2420-2515)는
`await asyncio.sleep(PARTIAL_FILL_WAIT=30)` → `cancel_order` → `place_order`(:2505) 의
**atomic replace** 이고, 유일 호출자가 `is_stop_loss=True`(:2340)다.

절반만 막으면 결과는 "주문을 안 낸 것" 이 아니라 **"호가창에 있던 손절을 우리가 빼고
아무것도 안 넣은 것"** 이다. 재현(전부 오늘 성립하는 구간):
15:45 손절 시장가 → NXT AFTER_MARKET 가 `'01'` 미지원 → 거부 → `step_down(현재가,5)`
지정가 `'00'` 폴백 접수(NXT AFTER_MARKET 는 `'00'` 을 받는다 [실측]) → 부분 체결 →
15:45:30 `_cancel_and_reorder` → 취소 성공 → 재주문 컷 → **잔여가 15분 무주문**.

⇒ 컷이면 **취소도 하지 않고** 작동 중인 주문을 그대로 둔다. 16:00 이후 `cancel_remaining`
또는 `risk.on_tick` 재평가에 위임한다. 이 비대칭을 G-295-9(행위)로 봉인하지 않으면 다음
사람이 "취소는 안 막는다" 한 줄만 보고 세 경로를 같게 만든다.

⚠️ 경계 누수 — 15:29:50 부분체결 → 15:30:20 재주문, 15:59:50 → 16:00:20. 전자는 컷에
걸리고 후자는 안 걸린다(정상).

### 3-6 관측 — 마커 2종

🔴 **지금 그 구간의 라우팅 판정은 로그에 한 글자도 안 남는다.** `_apply_clock`(:372)과
`_strategy_exchange_async`(:639)의 emit 게이트가 `if routed != base or reason == "probe_error":`
인데 `krx_unsupported_keep`·`both_unsupported_keep` 은 `routed == base` 다 [실측].
`[order_channel]` 이 구조적으로 발화하지 않는다. 그래서 오늘 실측에서 "그 구간에 주문이
몇 건 나갔나"를 `[order_channel]` 로는 잴 수 없다(§8-1 은 주문 로그·`trade_history` 를 본다).

| 마커 | cap | 내용 |
|---|---|---|
| `[market_rest_blocked] side= ticker= strategy= base= reason=` | 1회/(ticker,side)/일 | 이 사이클이 무엇을 잃는지의 **유일한 분모** |
| `[market_rest_window] start= end= source=market_table` | 1회/일 | 카나리아 — 주문 0건인 날에도 배선 생존 확인. start/end 는 리터럴이 아니라 표에서 역산 |

둘 다 `KstDailyEmitCap` + `observer_trace`, never-raise, **행위는 cap 밖**.
cap 없는 마커가 틱당 1행이 되는 사고는 cycle237(donchian 하루 1만 행)·cycle293
(`tick_channel_flip`) 두 번 있었다. 게다가 컷은 거부를 만들지 않으므로
`SellRejectionTracker` 의 폭주 억제가 걸리지 않는다 — **오늘은 거부가 억제기인데 컷이
그것을 없앤다.**

### 3-7 (a)·(b) 기각 근거

**(a) `nxt_only_continuous_window()` 를 남기고 W2/W3 만 제거** — 기각.
사용자가 지목한 것은 "변수와 그 변수를 케어하는 로직 … 시스템 복잡도" 다. 그 함수 46행 +
전용 헬퍼 22행이 그 복잡도의 **본체**다. 제거량이 ~173행 → ~105행으로 줄면서 **남는 쪽이
이해하기 어려운 쪽**이다. 남겨도 프로덕션 소비자는 `routes/realtime.py:909`(GET 표시 필드)
하나뿐이 된다. 결정적으로 (a) 는 사용자의 규칙을 표현하지 못한다 — "NXT 단독 연속 구간" 은
시세 채널의 개념이지 주문의 개념이 아니다.

**(b) order_engine 전용 시각 판정 신설** — 기각.
같은 경계를 두 곳에서 계산하면 표가 바뀌는 날 둘이 갈린다. 그리고 `market_state` 표 순회
로직이 8영역 파일 안으로 새로 들어온다(지금은 `get_market_state` 공개 API 호출뿐).

**(c′) 가 이기는 한 줄** = 새 계산을 0개 만들면서, 지우려는 계산 68행을 지울 수 있게 하고,
사용자가 말한 규칙("프리장은 NXT, 나머지는 전부 KRX")을 코드가 그대로 읽히게 쓴다.

---

## §4 잃는 것 — 정량

### 4-1 구조

잃는 것 = **15:40~16:00(20분) NXT 애프터마켓 청산 참여**.
얻는 것(순이득) = **15:30~15:40(10분) 의 헛 왕복과 TTL 래치 제거**.

브리프의 "15:30~15:40 은 이미 어디로도 안 나간다" 는 정확히는 **"나가서 거부된다"** 이다.
그 구간 라우터 결과는 `(base, both_unsupported_keep)` = SOR/NXT 이고 주문은 나간다. NXT 는
AFTER_SINGLE(단일가, `order_divisions=()`)이라 KIS 가 거부한다. 그리고 그 거부가
`is_market_closed_rejection` 에 걸리면 `register_market_closed(..., in_krx_main_hours=
_exit_capable_krx_window(now))` 를 부르는데, 15:35 의 KRX phase 는 `AFTER_CLOSE_FIXED` 이고
`_EXIT_CAPABLE_KRX_PHASES = {REGULAR, CLOSE_AUCTION, AFTER_MARKET}` 에 **없다** →
`False` → **NXT 시간대 TTL = 다음 KST 09:00**. 즉 15:3x 거부 한 건이 그 종목의
**16:00~20:00 KRX 애프터 청산 4시간을 통째로 잠근다.** [코드 확인 — 거부 msg_cd 가 실제로
APBK0918 인지는 §9-Q4 미실측]

### 4-2 09-14 제도 변경이 비용을 1/12 로 줄였다

| 세계 | 컷의 실질 비용 |
|---|---|
| 09-14 **이전** | 15:40~20:00 NXT 애프터가 **유일한** 저녁 체결처 ⇒ 컷하면 익일 09:00 까지 = **오버나이트 갭 노출** |
| 09-14 **이후 (지금)** | 16:00~20:00 KRX 애프터가 실시간 연속 체결이고 cycle287 이 44/41 로 열었다 ⇒ **최대 20분 유예**뿐 |

⇒ 사용자 결정이 실행 가능해진 것은 09-14 제도 변경 덕분이다. 09-14 이전이었다면 같은
결정이 매일 밤 오버나이트 갭 노출을 새로 만들었을 것이다.

### 4-3 크기

- 구간 길이 20분 = 청산 가능 시간(≈11시간)의 **3.0%**
- 그 구간의 청산 트리거는 **WS 틱 단독** — REST 폴은 `SWING_REST_POLL_WINDOW_END=15:20`
  (`scheduler.py:140`)에 끝난다
- **매수 노출 0** — `post_nxt` 보드를 가진 전략이 LTV 뿐인데 운영 DB
  `tradable_boards=["main","pre_nxt"]`
- 15:20 `_force_clear_main_only` 가 MAIN 보드를 이미 정리한 뒤라 그 창에 남는 것은
  익일청산·스윙 보유뿐

### 4-4 알려진 실사례 — 정확히 1건, 그리고 그 성격

2026-09-08 15:45:45 필옵틱스(161580, momentum) 실현손익 **+2,000원**. [2차 출처 —
`_workspace/analysis/2026-09-10_161580_root_cause.md:136-142`]

사건 재구성:
```
15:45:40.355 [selling_reconcile] stale _selling 해제: 161580   ← 09:00 부터 6시간 45분 잠겨 있던 것이 풀림
15:45:45.570 익일 즉시 청산: 필옵틱스(161580) 갭률 4.4%
15:45:45.715 APBK3013 [애프터마켓]지정가 및 최유리/최우선지정가 주문만 가능  ← 시장가 거부
15:45:45.943 지정가 5호가 폴백 @35,000 → 주문 0001611100
15:45:45.949 전량 체결 @35,250, 실현손익 +2,000원
```

⚠️ 이것은 "손절이 15:45 에 살아났다" 가 아니라 **"6시간 45분 좌초돼 있던 익일청산이 그제야
풀려 나간 것"** 이다. 성격이 다르고, 그 좌초의 근본 원인은 cycle273b(F-1/F-2)가 이미 시정했다.

리포가 인용하는 저녁 체결 3건 중 **컷 창에 드는 것은 이 1건뿐**이다(08-18 17:06 kojiro ·
09-01 18:09 donchian 은 16:00 이후라 무영향).

### 4-5 [미실측] 빈도 — 착수 전 필수 측정

"알려진 1건" 은 테스트 docstring·포렌식 인용이라 2차 출처다. 착수 전에 1차 출처로 바꾼다:

```sql
SELECT date_trunc('day', timestamp) AS d, count(*)
FROM trade_history
WHERE trade_type='SELL' AND status IN ('COMPLETED','PARTIAL')
  AND timestamp::time >= '15:30' AND timestamp::time < '16:00'
GROUP BY 1 ORDER BY 1;
```
그 수가 곧 사용자가 수용한 비용의 크기다.

### 4-6 🔴 특별 개장일 — 컷이 「연속체결 중인 정규장」에 발화할 수 있다

`market_state.py` 는 **날짜 범위(`effective_from`/`effective_to`)만** 보는 고정 벽시계다.
거래일·특별 개장일(지연 개장) 입력이 **한 곳도 없다** — `is_trading_day` 는
`src/api/condition.py` 와 라우트 2개에만 있고 `market_state` 소비자 어디도 그것을 넘기지
않는다. 실행 확인: 임의 미래일(2026-11-19)과 2026-09-15 의 스윕이 **완전히 동일**하다. [실측]

재현 — KRX 정규장이 1시간 지연되는 날(수능일이 표준 사례. 정규장 10:00~16:30):
- 15:35 실제 = KRX 연속체결 중, 유동성 정상
- 우리 표 = `AFTER_CLOSE_FIXED ('06',)` → `_SENDABLE_DIVISIONS` 교집합 ∅ → **컷 발화**
- ⇒ 보유 종목 손절이 **30분 무음 차단**

🔴 **오늘의 동작과 부호가 반대다.** 같은 순간 현행은 base(NXT/SOR)로 보내고 NXT 가 함께
지연 운영되면 실제로 체결된다 — "경로는 틀렸는데 작동하는" 상태다. 컷은 그것을 **무주문**
으로 바꾼다. 컷이 없애는 것이 '거부' 가 아니라 '체결' 인 유일한 케이스다.

정직한 한계 — 2026 수능일자와 NXT 의 그날 운영시간은 리포에서 확인할 수 없다. 확실한 것은
**구조적 사실**뿐이다: 표는 특별일을 모르고, 컷은 표만 읽는다.

**권고(§9-Q2 결정 대상)** — 컷을 표 단독 판정으로 두지 말고 **현실 관측과 AND** 한다.
컷 창 안에서 그 종목의 `scanner.ticker_last_tick` 이 최근 N초 내 갱신되고 있으면 컷을
해제(fail-open)하고 `[market_rest_reality_mismatch]` CRITICAL 1행. 컷의 전제("그 구간엔
프레임이 오지 않는다")가 곧 해제 조건이므로 **새 규칙이 생기지 않는다**.
최소한 이 절의 내용을 §4 에 명시한다.

### 4-7 🔴 `POST /api/trading/manual-sell` 은 컷에 닿지 않는다

`src/routes/trading.py:126-134` 의 `place_order` 는 `_route_exchange_by_clock` 도
`_apply_clock` 도 `execute_sell` 도 거치지 않는다. 거래소는
`str(strategy.config.params.get("exchange","KRX")).upper()`(:123-125) — 운영 DB 7전략이 전부
`SOR` 이라 결과는 SOR 이다. 프론트 `BalanceTable.tsx` 에 버튼이 걸려 있다. [실측]

재현: 15:45 에 운영자가 대시보드에서 '매도' 를 누른다 → `place_order(exchange="SOR",
price=0)` → NXT AFTER_MARKET leg 로 **체결된다**. 15:30~16:00 완전 휴식이 코드로 성립하지
않는다.

⚠️ 이것은 이 사이클이 만든 문제가 아니라 **cycle287 이 이미 놓친 구멍**이다 — 16:05 에
같은 버튼을 누르면 KRX 애프터 호가유형(44/41) 변환도 KRX 라우팅도 없이 시장가가 SOR 로
나가 APBK3013 로 거부된다. 그리고 `engine._selling.add(req.ticker)`(:143) 만 하고 실패
경로에 `discard` 가 없어 거부 시 stale `_selling` 이 남는다(F-7 계열).

처분은 §9-Q3. **아무것도 안 적으면** 다음 사람이 "15:30~16:00 주문 0건" 판독을 하다가
이 한 건에 걸려 게이트가 고장났다고 오진한다.

---

## §5 회귀 가드

### 5-1 (A) 축 — 제거가 되돌아오는 것을 막는 4종 (전부 양성 대조군 동반)

cycle292 교훈 = **본체가 떠나면 "0건" 부정 단언이 전부 참이 되어 조용히 공허해진다.**

| 가드 | 부정 단언 | 🔵 양성 대조군 |
|---|---|---|
| **G-D1** 전환 창 라벨 | `switch_windows(DAY, offset_secs=300)` 라벨 == `["pre_to_krx"]` **정확히** | 1원소 단언이 `return []` 뮤테이션도 죽인다 + 그 창이 비지 않음(`start < end`) + `active_switch_window(switch_at)` 가 그 창을 돌려줌 |
| **G-D2** `priority` 무차별 | `clock_channel(now, priority="HIGH")` == `priority="LOW"` 를 하루 1,440분 전부 | 같은 스윕에서 프리 창 = NXT, 정규장 = KRX 가 **실제로** 나온다(퇴화 구현 사살) |
| **G-D3** 식별자 소멸 | `src/**/*.py` 전수에 `nxt_only_continuous_window`·`in_nxt_gap`·`gap_hold_enabled`·`krx_to_nxt_gap`·`nxt_gap_to_krx`·`REASON_NXT_GAP_WINDOW`·`tick_channel_gap_hold_enabled` 0건 | 같은 스캔에서 `switch_windows`·`pre_to_krx`·`clock_channel`·`REASON_KRX_WINDOW`·`tick_channel_switch_enabled` 는 **존재**(스캐너가 파일을 못 읽어도 붉어진다) |
| **G-D4** 라우트 표면 | GET 응답에 `gap_hold_enabled`·`gap_config_key`·`nxt_gap_window` 없음 · PUT 에 `{"gap_hold_enabled": true}` 를 실어도 **아무 상태도 안 바뀐다** | 같은 응답에 `mode`·`switch_enabled`·`switch_windows` 는 여전히 있다 |

⚠️ G-D3 스코프는 `src/**` 로 한정 — `docs/HARNESS_CHANGELOG.md`·`_workspace/**` 는 verbatim
역사라 스캔 대상이 아니다(cycle257 `_LIVE_DOCS` 관례).

⚠️ G-D4 의 네 필드는 **현재 테스트 0건**이다(cycle293 이 지적한 "킬스위치 라우트 테스트
0건" 의 재현). 지우면서 처음 테스트가 생긴다.

🔴 **필드 삭제의 실패 모드는 422 가 아니라 무음이다** [실측 — pydantic 2.11.2]:
`TickChannelModeRequest` 는 `model_config` 를 두지 않고 기본이 `extra="ignore"` 다.
`gap_hold_enabled` 필드를 뺀 모델에 `{'mode':'enforce','gap_hold_enabled':False}` 를 넣으면
**검증을 통과**하고 그 키는 조용히 버려진다. 즉 `src/realtime/CLAUDE.md:315` 의 런북 curl 이
사고 중에 **HTTP 200 / success:true** 를 돌려주며 아무 일도 안 한다.

⇒ **422 로 바꾸지 않는다**(같은 요청의 `mode` 킬스위치까지 막힌다 — 사고 중에 반드시
눌려야 한다). **무시로 두되 런북을 같은 커밋에서 지운다**(§6-1). G-D4 가 그 무시를 못박아
운영자가 "껐다" 고 오해하지 않게 한다.

### 5-2 (B) 축 — Red 테스트 (freezegun · **모든 케이스 `now=` 명시 주입** · **날짜 ≥ 2026-09-14 pin**)

| # | 입력 | 기대 |
|---|---|---|
| T1 | 15:35 | `(True, "market_rest")` |
| T2 | 15:45 · 15:55 | `(True, "market_rest")` |
| T3 | 15:25 · 16:05 · 19:00 · 10:00 | `(False, ...)` |
| T4 🔴 | 08:05 · 08:30 · 08:45 · **08:55** | `(False, "pre_nxt_keep")` — 과잉 차단 방지의 핵심 봉인 |
| T5 | 02:00 · 22:00 | `(False, "no_session")` — 야간 가드 |
| T6 🔴 | `nxt_tradable=False` 로 KRX 다운그레이드된 종목 @15:45 | **컷** — §3-2 구멍 부재 봉인 |
| T7 | `order_exchange_clock_mode ∈ {off, sell_only}` × side∈{buy,sell} 6조합 @15:45 | 전부 컷(§9-Q1 권고안일 때) |
| T8 | `execute_sell` 컷 | `place_order` 0회 ∧ `ticker not in _selling` ∧ 포지션 보존 ∧ `_sell_rejection.is_blocked(ticker, 16:05)` **False** ∧ `_pending_next_day_clear` 미전환 |
| T9 | `_cancel_after_wait`·`cancel_remaining` @15:45 (`_order_exchange` 매핑 **없음**) | `cancel_order` 1회 ∧ exchange 비어 있지 않음 |
| T10 🔴 | `_cancel_and_reorder` @15:45:30 | `cancel_order` **0회** ∧ `place_order` **0회**(쌍 게이트) |
| T11 🔴 | 통합: 15:45 컷 → 16:05 `risk.on_tick` 재평가 | 주문 **발사** — §3-5 회복 경로 실증 |
| T12 | 컷 창 길이 | ≤ **30분** ∧ 시작이 KRX 연속 종료(15:30)와 일치 |
| T13 | 같은 종목 `execute_sell` 20회 @15:45 | `[market_rest_blocked]` **1행** |

### 5-3 뮤테이션 대조표 (전부 KILLED · ESCAPED 0 목표)

| # | 뮤테이션 | 잡는 가드 |
|---|---|---|
| M1 | `switch_windows` 에 W2/W3 재삽입 | G-D1 |
| M2 | `switch_windows` 본체 `return []` | G-D1(1원소) |
| M3 | `clock_channel` 에 `priority` 분기 재삽입 | G-D2 |
| M4 | `clock_channel` 이 항상 KRX(아침 전환 소멸) | G-D2 양성 대조군 |
| M5 | 컷을 `mode=="off"` 판정 뒤로 이동(롤백 다이얼이 컷을 품) | T7 |
| M6 | 컷이 `base="KRX"` 를 비껴감 | T6 |
| M7 | 컷을 "보내고 거부받기" 로 구현 | T8 (②③이 뒤집힌다) |
| M8 | 컷 뒤 `_selling.discard` 누락 | T8 |
| M9 | 컷 마커 무cap | T13 |
| M10 | 컷을 벽시계 리터럴(`now.hour == 15`)로 | G-C1 (§5-4) |
| M11 | 컷 창 무한 확장(표 회귀·K6 미적용) | T12 |
| M12 | 판정은 지웠는데 라우트·DB 게터만 잔존 | G-D3 · G-D4 |
| M13 | `execute_sell` 만 고치고 `_cancel_and_reorder` 누락 | T10 |
| M14 | 프리장 예외를 `market_state` NXT phase 로 판정 | T4 (08:55) |
| M15 | `except` 를 `return True` 로(fail-closed 전환) | fail-open 케이스 |
| M16 | `_cancel_after_wait`·`cancel_remaining` 도 함께 막음 | T9 |

검증 방법 = 각 뮤테이션을 워킹트리에 넣고 해당 가드 파일만 돌려 **RED 확인 → 되돌림**.
가드가 못 잡는 뮤테이션이 남으면 그것이 곧 추가할 테스트다(cycle292 가 이 절차로
`bypass_limit` ESCAPE 를 잡았다).

### 5-4 🔴 "시각 리터럴 0건" 가드는 지금 이름보다 약하다

cycle294 A5 의 정규식 3종(`time(H,M)` 호출 · `"HH:MM"` 문자열 · `datetime.combine(..., time(H,M))`)을
`order_engine.py` 에 그대로 이식하면 **오늘 0건으로 통과한다** [실측]. 그런데 이 파일에는
`_compute_next_market_open_kst` 의 `now.replace(hour=9, minute=0, ...)` 이 **2곳**(:207,:213)
있다. 즉 이름이 거짓이 되고, 구현자가 컷을 `now.hour == 15 and now.minute >= 30` 이나
`now.replace(hour=16)` 로 짜도 가드는 조용히 초록이다.

- **G-C1** — A5 3종 + `replace(hour=`/`replace(minute=` 키워드 + `Compare` 노드에서 한쪽이
  `Attribute(attr ∈ {hour,minute})` 이고 다른 쪽이 `Constant(int)` 인 비교를 함께 금지.
  **명시 allowlist 는 정확히 1건**(`_compute_next_market_open_kst`)이고, 그 allowlist 는
  함수명 문자열이 아니라 **AST 함수 노드 범위**로 좁힌다(문자열 매칭이면 주석에 함수명을
  쓰는 것만으로 면제가 새 나간다 — cycle292 가 `/sync-docs` 부분문자열 매치에서 겪은 결함).
- **G-C2**(양성 대조군) — allowlist 대상 함수가 **실제로 존재하고 실제로 `replace(hour=` 를
  쓴다**. 그 함수가 사라지면 allowlist 가 죽은 면제로 남고, 같은 이름의 새 함수가 생기면
  면제가 부활한다.
- **G-C3** — `_market_rest_now` 가 `get_market_state` 를 **이름으로** 참조한다
  (`_names_used`). 표를 안 읽는 컷은 정의상 리터럴 컷이다.

### 5-5 깨질 기존 테스트 — 「정상 파괴」와 「계약 신호」를 가른다

기준선 [실측] = 관련 4파일 **401 passed / 0 failed**.

**[정상 파괴 — 기대값 갱신, 삭제 금지]**
- `test_cycle287_exchange_routing.py::test_r1`/`test_r1b` 의 `(15,40,0)`·`(15,59,59)` 행 × 2 = **4건**.
  이 격자가 컷의 새 정본이 되므로 행을 지우지 말고 기대값만 바꾼다.
- `test_r6_sell_exchange_plumbing[_F_1545]` = **1건**. `place_order` 1회 → 0회.
- `test_k3b_1530_to_1600_keeps_today_path[_F_1545]` = **1건**. docstring 은 G-B2 대로 재서술.
- `test_cycle294b::test_n2`·`test_n3`·`test_n5`·`test_n7` = **4건** → 반대 단언으로 대체.

**[⚠️ 계약을 잘못 건드린 신호]**
- `test_cycle290::test_g290_23`, 날짜 `2026-09-11` × {16:30,19:30} × base{NXT,SOR} × side{buy,sell}
  = **8건**. 🔴 이 8건이 붉어진다는 것은 **"K6 가 없는 날 컷이 4시간 30분"** 이라는 뜻이다
  (§3-4 실측). 기대값을 덮어 초록으로 만들면 그 사실이 은폐된다 → **T12(길이 ≤ 30분)를
  먼저 세우고** 테스트 날짜를 2026-09-14 이상으로 re-pin 해 **원래 값 그대로 초록**이 되게
  하는 것이 옳은 처분이다.
- `test_cycle287_krx_after_exit.py::test_k11d` = **1건**. 계약(원주문·취소 거래소 불일치
  방지)은 살아 있고 픽스처 시각만 불가능해졌다. **삭제 금지** — 경계쌍을
  `15:25(KRX) → 15:35(컷)` 또는 `08:55(pre) → 09:05(KRX)` 로 재앵커한다.

**[존치 — 감시자]**
- `test_cycle294b::test_n1`(표 사실) · `test_n4`(경계 KRX) · `test_n6`(속성축 우선)은
  **그대로 통과**하므로 존치한다. 특히 `test_n1` 은 "표가 바뀌어 KRX 가 15:45 에 연속체결을
  갖게 되면 이 판단의 전제가 사라진다" 를 재는 유일한 감시자다. docstring 에
  **"전제가 사라지면 컷을 재검토하라(제거하라가 아니다)"** 를 명시한다.

### 5-6 되돌림 방지 3중 장치

cycle294 CRITICAL-1 은 **틀리지 않았다**. 그래서 다음 사람이 그 문장만 읽고 되돌릴 위험이
가장 크다. 관례상 "지우지 말고 왜 뒤집었는지 덧붙인다"(cycle288 이 `App.tsx` 나브 폭
주석에서 쓴 방식)를 따른다.

1. **컷 함수 docstring** — §3-3 의 (가)사실 → (나)cycle294 판단(여전히 참) → (다)사용자 결정
   세 문장을 **순서대로**. "결함이 아니라 결정" 은 세 번째 문장에서만 성립하므로 분리하지 않는다.
2. **테스트 docstring** — 같은 3문장 요약 + "이 테스트가 붉어졌다면 먼저
   `_workspace/00_URGENT_WORKLIST.md` 의 2026-09-15 결정을 확인하라. **표가 바뀌어서인지
   결정이 바뀌어서인지를 가르기 전에는 기대값을 고치지 마라.**"
3. **G-B2** — `test_k3b` docstring 을 지우지 말고 재서술: "cycle287 자문의 (다) 기각은
   여전히 유효하다 — 단 그것은 *거부를 받는* 컷이고, cycle295 의 컷은 *보내지 않는* 컷이라
   `register_market_closed` 의 다음-09:00 래치 경로를 통과하지 않는다."
   (G-B1 행위 단언이 T8 이다.)

---

## §6 문서 동기화

### 6-1 🔴 `src/realtime/CLAUDE.md` — 문서인데 8영역이고, 정리는 **회피 불가**

`_EIGHT_AREAS` 가 `"src/realtime"` **디렉터리 글롭**이라 `.md` 도 잡힌다
(`tests/unit/ast/test_cycle222a3_ast_followup_fixes.py:430-439`).

**고칠 곳 [실측]** — :170(킬스위치 서술) · :197-198(전환 창 3개 라벨) · :306(다이얼 표 행) ·
:315(런북 curl `gap_hold_enabled:false`) · :327-328(선택 필드 + GET `nxt_gap_window`) +
CRITICAL-1 절(§6-4 대로 재서술).

:315 의 런북 삭제는 **§5-1 의 무음 no-op 때문에 회피 불가**하다.

**sha 핀 4곳** (넷 다 **같은 값**이어야 한다 — lockstep):
```
현재 sha = 12bf914da7c13cfb13ed6caaa0825f7cfe77dff7b95c72260f439171c054480a
tests/unit/ast/test_cycle222a3_ast_followup_fixes.py:494
tests/unit/ast/test_cycle223_ast_donchian_exit_fix.py:476
tests/unit/ast/test_cycle223f_ast_manual_apply_safeguard.py:387
tests/unit/engine/strategies/test_cycle226_zero_breakout_defense.py:1180
```
`tests/unit/ast/test_cycle223g3_ast_guard_sees_staged.py:268-282` 의 `_PIN_GUARD_FILES`(4개)가
"핀은 항상 4곳" 을 기계로 강제한다. 하나만 갱신하면 7 failed 다(cycle263 선례).

이름만 등재된 스코프 집합 2곳(`test_cycle276::_APPROVED_EIGHT_AREA_PINS:927` ·
`test_cycle264_scope_and_pins.py:54`)은 sha 가 없어 **갱신 불필요**.

⚠️ 내용 단언 1곳 — `test_cycle257_ast_dead_code_removed.py:333-366` 이 `_DEAD_DOC_TOKENS`
5종 부재 + `"cycle257"` 문자열 **존재**를 단언한다. 갱신하면서 cycle257 문단을 갈아엎지 않는다.

**절차** (가드 자신이 요구하는 순서):
1. 문서 수정 → `git diff HEAD -- src/realtime/CLAUDE.md` 를 **눈으로 읽는다**
2. 승인 범위 밖 변경이 섞였는지 확인
3. 없을 때만 `shasum -a 256` 재산출 → 4곳 **동일 값** 치환
4. `grep -rn "<구 sha>" tests/` **0건** 확인

⚠️ **워킹트리 상태 정정** — 초안은 그 문서가 `M`(미커밋 수정) 상태라고 적었으나,
`git status --porcelain` = `?? _workspace/red/cycle295_market_rest_window_spec.md` 뿐이다.
**워킹트리는 깨끗하다** [실측]. 핀은 커밋 뒤에는 조회되지 않고 자기소멸한다 — 두 상태를
혼동하면 "코드 무변경인데 깨짐" 으로 오진한다.

### 6-2 `src/engine/order_engine.py` sha 핀 9곳 — (B) 축

```
현재 sha = 84e84a972774cd2fbf8ceb70e5569f7760d43a228c2be21d2a1b90f48fd4ce75
tests/unit/ast/test_cycle222a3_ast_followup_fixes.py:474
tests/unit/ast/test_cycle223_ast_donchian_exit_fix.py:456
tests/unit/ast/test_cycle223f_ast_manual_apply_safeguard.py:365
tests/unit/ast/test_cycle274_ast_llm_gate.py:563
tests/unit/ast/test_cycle278_ast_catalog_guards.py:205
tests/unit/ast/test_cycle282_ast_purity.py:380
tests/unit/ast/test_cycle290_ast_scope.py:102
tests/unit/ast/test_cycle294_ast_stage3.py:277
tests/unit/engine/strategies/test_cycle226_zero_breakout_defense.py:1158
```

### 6-3 핀 비용 실측 [실측 — 임시 1줄 추가 → 테스트 → `git checkout --` 복원]

| 건드린 것 | `pytest tests/unit/ast` |
|---|---|
| 4파일(`tick_channel_clock`·`tick_channel_mode`·`db/system_config`·`routes/realtime`) 동시 | **1 failed**(`test_cycle287_ast_scope.py::test_s1b` 트리 digest) |
| + `src/realtime/CLAUDE.md` | **+7**(222a3 / 223 / 223f / 223g3×3 / 276) |
| + `src/engine/order_engine.py` | **+12**(위 7 + 274 / 278 / 282 / 290 / 294) |

⇒ (A) 커밋은 "핀 1건" 이 아니라 **「트리 digest 1 + realtime 문서 sha 4 + 승인 집합 2」**
로 계획한다. 문서 정리를 분리하면 산술적으로는 1건이지만 리포가 **틀린 런북을 들고 있는**
상태가 되므로 권고하지 않는다(사용자 메모리 「충돌하는 과거 이력은 제거하고 진행」).

⚠️ `_SRC_TREE_FILES = 152` 는 **불변**이다(파일 삭제가 아니라 함수 삭제).
`_PINNED_DIRS` 에 `src/engine` 이 통째로 들어 있어 `_SRC_TREE_DIGEST` 만 확정적으로 붉어진다.

### 6-4 이력은 지우지 않는다 — 철회 문장을 덧붙인다

메모리 「충돌하는 과거 이력은 제거하고 진행」은 *방향이 다른 서술이 둘 남는 것*을 금지하는
것이지 이력 말소를 요구하지 않는다. **폐기 표시가 그 요구를 만족한다.**
지우면 다음 사람이 같은 CRITICAL 을 다시 발견해 다시 승인 없이 넣는다 — 이 사이클이
고치는 바로 그 사고의 재현 경로다.

| 문서 | 조치 |
|---|---|
| 루트 `CLAUDE.md:90` cycle294 행 | 행 끝에 append: "⚠️ ①(15:40~16:00 갭 홀드)은 cycle295(2026-09-15)에서 **철회**됐다 — 그 시정은 사용자 결정 「전환 1회」를 승인 없이 뒤집은 것이었고, 사용자가 '청산측으로도 참여하지 않는다(15:30~16:00 완전 휴식)' 로 결정했다. **나머지 CRITICAL ②~⑧ 은 유효하다.**" + 표 맨 위에 cycle295 행 추가 + 가장 오래된 1행 제거(15행 유지) |
| 루트 `CLAUDE.md` 운영 가이드 | 배포 창 표 갱신(§8-3) |
| `src/realtime/CLAUDE.md` CRITICAL-1 절 | **삭제하지 않는다.** 절 머리에 "이 절의 *시정*은 cycle295 에서 철회됐다. *사실*(15:40~16:00 은 NXT 만 연속)은 그대로다." |
| `src/engine/CLAUDE.md` | `tick_channel_clock`·`tick_channel_switch` 절의 갭 서술 제거 + `order_engine.py` cycle287 절에 컷 추가 + "장중 킬스위치 없음"(§9-Q1) |
| `src/db/CLAUDE.md:145` | 다이얼 **5키 → 4키** + §2-4 의 재사용 금지 1행 |
| `src/routes/CLAUDE.md:79-80` | GET/PUT 필드 갱신 + "`gap_hold_enabled` 를 보내면 **조용히 무시**된다" |
| `docs/HARNESS_CHANGELOG.md` | cycle295 절 **append**(cycle294 절은 verbatim 보존) |
| `_workspace/red/cycle294_stage3_time_axis_spec.md` | **고치지 않는다**(그 시점의 기록) |
| `_workspace/00_URGENT_WORKLIST.md:80` | "15:40~16:00 갭 홀드 — nxt_true 보유만 NXT 추종" → "휴식(cycle295) — 주문·평가 모두 없음" |
| `_workspace/00_URGENT_WORKLIST.md:141` | 🔴 §6-5 |
| `README.md` | 해당 서술 정합 |

### 6-5 🔴 워크리스트 141행은 의미가 **반전**된다 — 배포 전후 판독 합산 금지

현행: "⚠️ '주문 0건' 이 정상이라는 뜻이 아니다 — cycle287 은 15:40~16:00 의 NXT 애프터
실체결 경로를 **의도적으로 보존**했다. 그 구간에 NXT 매도가 나가는 것은 **정상**이고,
여기서 0 이어야 하는 것은 KRX 로 재라우팅된 흔적뿐이다."

cycle295 착지 뒤 **정확히 반대**가 된다:
- **성공 서명** = `[market_rest_window]` 1행 ∧ 그 구간 주문 흔적(`place_order`·`trade_history`) **0건**
- **실패 서명** = 주문 흔적이 있거나, `[market_rest_window]` 가 0행(배선 죽음)

리포 관례(cycle252/263/276/293 계열)대로 **"배포 전후 grep 합산 금지"** 를 명시한다.

### 6-6 사라지는 관측 — 정확히 4필드 (초안 서술 정정)

`[tick_channel_clock]` 의 `nxt_gap=`·`gap_hold=` + `[tick_channel_mode]` 의
`gap_hold=`·`gap_persisted=`. **마커 이름은 전부 유지**되므로
`test_cycle294_ast_stage3.py::A23`(`_NEW_MARKERS` 12종 존재)는 무접촉 통과다.

⚠️ 초안이 "`[tick_buy_gate]` 의 구간 라벨에서 `nxt_gap_window` 가 빠진다" 고 적었는데
**그 라벨은 애초에 나온 적이 없다** [실측] — `scanner._clock_phase`(:1149-1152)는
`clock_channel(now, offset_secs=...)` 을 **`priority` 없이** 부르고 기본값이 `"LOW"` 라
갭 분기(`... and priority == "HIGH"`)에 구조적으로 도달 못 한다. 15:40~16:00 에도
`krx_window` 를 돌려준다. 명세가 없던 변화를 적으면 D+1 판독자가 시간을 버린다.

⚠️ `emit_clock_config` 와 `_nxt_gap_window_repr` 는 **둘 다 never-raise** 라 안 고치고
배포하면 예외 없이 **카나리아만 조용히 죽는다**(가장 나쁜 실패 모드 — "오늘 전환이 몇 시로
잡혔는가" 를 사후에 알 방법이 없어진다). 두 필드만 빼고 나머지 4필드는 남긴다.

### 6-7 `/sync-docs` 실행 주체

`report-writer` 에이전트(2026-09-11 사용자 결정). 메인 세션은 꾸러미만 만들어 위임한다.
⚠️ 전용 `CLAUDE.md` 가 없는 `src/services/`·`src/middleware/`·`tools/`·`e2e/` 가 누락 반복 지점.

---

## §7 승인이 필요한 것 — 사용자에게 물을 문장 그대로

### 7-1 (A) 축 — 문서 1건

> **승인 요청 (A)** — 갭 홀드 코드 제거는 `tick_channel_clock.py`·`tick_channel_mode.py`·
> `db/system_config.py`·`routes/realtime.py` 넷을 접촉하며 **전부 8영역 밖**입니다
> (`scheduler.py` 무접촉 3,726L, `scanner.py`·`risk.py`·`tick_channel_switch.py` diff 0).
> 다만 **`src/realtime/CLAUDE.md` 는 문서인데도 8영역입니다**(`_EIGHT_AREAS` 가
> `"src/realtime"` 디렉터리 글롭이라 `.md` 도 잡힙니다). 그 파일의 갭 서술 6곳을 고쳐야
> 하고 — 특히 :315 의 런북 curl 은 제거 후 **HTTP 200 을 돌려주며 아무 일도 안 하는**
> 무음 no-op 이 되므로 정리가 불가피합니다 — 이 파일 하나를 승인 범위에 넣어 주십시오.
> 행위 영향: 다이얼이 이미 꺼져 있으므로 정상 상태에서는 변화가 없고, **재기동 후 최대
> 120초 동안 갭 홀드가 재무장되던 잔여 경로**가 구조적으로 0 이 됩니다.

### 7-2 (B) 축 — `order_engine.py` 1파일

> **승인 요청 (B)** — 이 변경은 8영역 중 **`src/engine/order_engine.py` 한 파일**을
> 접촉합니다. 내용은 ① 순수·never-raise 술어 `_market_rest_now` 신설(`market_state` 파생,
> 시각 리터럴 0건) ② `execute_sell` 발사점 게이트 1블록(`_selling.discard` + 마커 + `return`)
> ③ `execute_buy` 대칭 블록 ④ `_cancel_and_reorder` 쌍 게이트 ⑤ 관측 마커 2종입니다.
> `_route_exchange_by_clock` 의 7절과 `_apply_clock`, 순수 취소 2경로
> (`_cancel_after_wait`·`cancel_remaining`)는 **byte 동일**입니다. A-ATOMIC 구간
> (`calc_buy_quantity` ~ `pending_buys.add`) 무접촉. 나머지 8영역 4파일과
> `src/api/order.py`·`src/auth/**`·`scheduler.py`·전략 7파일·`strategy_base` 는 무접촉이고
> `DEFAULT_PARAMS` 키를 **신설하지 않습니다**(다이얼 제거가 이 사이클의 목적이므로).
>
> 매매 행위 변경은 **「15:30~16:00 청산·매수 참여 중단」 하나**이며, 2026-09-15 사용자
> 직접 지시(행위 축소)입니다. 잃는 것은 §4 에 정량화했습니다 — 15:40~16:00 의 20분
> (청산 가능 시간의 3.0%), 알려진 실체결 표본 1건(09-08 필옵틱스 +2,000원, 그마저도
> 6시간 45분 좌초돼 있던 익일청산이 풀린 사례), 16:00 KRX 애프터 재개까지 **최대 20분
> 유예**. 15:30~15:40 은 오히려 **순이득**입니다(헛 왕복과 다음-09:00 TTL 래치 제거).

### 7-2b (C)(D) 축 — 2026-09-15 승인 완료

사용자가 **"즉시 조치하자. 그리고 사이클 295에도 포함시키자. 손절 잔여 재주문 매핑 누락까지
한 사이클에 넣어서 진행하자"** 로 셋을 한 번에 승인했다. 따라서:

- **(C)** `src/db/system_config.py` — 8영역 밖. 즉시 조치(DB boolean 교체)는 **실행 완료**,
  코드 시정은 이 사이클에 포함.
- **(D)** `src/engine/order_engine.py` — (B) 와 같은 파일이므로 **같은 커밋**에 넣는다.
  sha 핀 9곳을 한 번만 갱신하면 된다.

(D) 를 (B) 와 묶는 것이 핀 비용 면에서 유리하지만, **행위 축이 다르다** — (B) 는 주문을 막고
(D) 는 매핑을 채운다. 커밋 메시지에서 두 의도를 분명히 가른다. 회귀도 각각 독립으로 세운다.

### 7-3 `domain-consult` 선행 — 면제

사용자가 직접 지시한 **행위 축소**(참여 구간 제거)라 재자문 대상이 아니다. §4 의 정량화를
싣는 것으로 그 자리를 대신한다.

### 7-4 여전히 사용자 결정이 필요한 것

§9 의 Q1~Q6. 특히 **Q3(manual-sell)** 과 **Q5(execute_buy)** 는 승인 카드로 올린다.

### 7-5 자동 감시자

`test_cycle222a3::test_ga3_6_eight_areas_touched_are_only_...` 가
`git diff HEAD --name-only -- <8영역>` 을 재므로 별도 신설 불필요.

---

## §8 실행 순서와 배포 창

### 8-1 🔴 선결 — 오늘(2026-09-15) 15:38~16:04 실측

브리프의 전제 "다이얼만으로 실질 휴식은 이미 성립한다 — 시세가 KRX(그 구간 프레임 ≈0)면
`risk.on_tick` 이 안 불린다" 는 **표와 맞지 않는다.** KRX `AFTER_CLOSE_FIXED`(15:30~16:00)는
`match_kind="fixed_price"` 지만 **체결이 일어나는 세션**이고, `clock_channel` 은
`krx_continuous_end`(=20:00) 이전이라 그 구간 내내 KRX 전용 채널 구독을 유지한다.
`H0STCNT0` 이 시간외 종가 체결을 프레임으로 싣는지는 **[미실측]** 이다 — cycle294 명세
부록 A 도 그 칸을 "K5 시간외 종가 — 미지" 로 남겼다.

| # | 시각 | 잴 것 | 전제가 참이면 |
|---|---|---|---|
| 1 | 15:30~16:00 | `scanner.ticker_last_tick` 갱신 종목 수 / `[tick_*]` 계열 | 🔴 **가장 중요** — 0 이면 컷은 "미래 방어", 비영이면 **오늘도 돌고 있는 참여를 끊는 즉시 시정** |
| 2 | 15:30~16:00 | 주문 로그 · `trade_history` 실적 | ⚠️ `[order_channel]` 은 §3-6 대로 **구조적 0행**이라 판독 불가 |
| 3 | 아침 | `[tick_channel_clock] … nxt_gap=15:40:00~16:00:00 gap_hold=0` 1행 | 다이얼 off 가 실제로 먹었다는 카나리아 |
| 4 | 15:40~16:00 · 16:00~16:04 | `[tick_channel_flip]` · `krx_to_nxt_gap` · `nxt_gap_to_krx` | **0행**(W2·W3 미발화) |
| 5 | 15:30~16:10 | `[kis_rejection] APBK0918`/`APBK3013` | 있으면 §4-1 의 다음-09:00 래치가 실증된다 |
| 6 | 하루 1행 | `[tick_channel_switch_window_missed] pending=N` | 그날 15:40~16:00 에 NXT 프레임을 받을 수 있는 종목 수의 **상한** |
| 7 | 그날 | `[tick_channel_auto_revert]` ERROR | 발화했으면 `day_reverted` 래치로 전 종목이 종일 NXT 였다(§8-2) |

⚠️ **프로브 주의** — "NXT 채널이 그 구간에 프레임을 주는가" 를 `POST /api/realtime/channel-probe`
로 재려는 유혹이 있는데, 핸들러(`handler.py:400`)에는 프로브 분기가 없어 프레임이 그대로
`_on_tick` 으로 흐른다. **프로브 대상은 보유·익일청산 종목을 피한다** — 실측이 곧 주문을
유발한다.

### 8-2 [미실측] 남는 세 경로 — 컷이 "미래 방어" 가 아닌 이유

다이얼을 꺼도 그 구간에 프레임이 오는 경로가 셋 남는다. 컷은 이 셋 전부와 무관하게 성립한다
(컷 판정은 채널·모드·구독 사실을 **보지 않는다** — cycle293 이 매수 게이트에서 배운 교훈).

1. **`day_reverted` 하루 래치** — `clock_channel` 의 **첫** 검사(`tick_channel_clock.py:320`).
   09:03 자동 원복 프로브가 발화하면 그날 전 종목(HIGH·LOW 무관)이 `H0NXCNT0` 에 앉고,
   NXT AFTER_MARKET 15:40~20:00 은 continuous 다. 갭 홀드를 지워도 **무접촉으로 남는다**.
   fail-safe 라 끌 수도 없다.
2. **채널 모드 하강** — `scanner._mode_scoped_desired`(:804-818)가 `off`·`observe`·
   `enforce_low`×HIGH 세 경우에 통합 `H0UNCNT0` 을 돌려준다. 그리고
   `DEFAULT_MODE = MODE_OBSERVE`(`tick_channel_mode.py:74`) — DB 에 `enforce` 가 없으면
   부팅 기본값이 통합이다. 통합 채널은 `nxt_tradable=True` 종목의 NXT 프레임을 **보낸다**.
   `enforce_low` 는 더 나쁘다 — HIGH 만 통합에 남기므로 정확히 청산이 필요한 종목만 살아난다.
3. **전환 실패 잔여** — `tick_channel_switch.py` 모듈 docstring 이 직접 적어 뒀다:
   "못 옮겨도 blind 가 아니다 — 미전환 잔여는 NXT 에 남고 NXT 는 정규장·**애프터**에
   체결을 싣는다."

⇒ 브리프의 전제는 **mode=enforce ∧ 원복 미발화 ∧ 미전환 0 ∧ 프로브 없음** 이라는 네 조건의
곱에서만 참이다.

### 8-3 배포 창 — 현행 서술은 낡았다

루트 `CLAUDE.md` 의 "장외 배포 창 = **15:30~19:55** · 21:35~익일 07:45" 는 09-14 부터 낡았다.
16:00~20:00 이 KRX 애프터 실시간 연속체결이고 cycle287 이 그 창의 청산 경로를 열었으므로
그 4시간은 D6 와 **같은 성질**이다.

| 구간 | 가부 | 근거 |
|---|---|---|
| 07:45~08:00 | ✗ | `TIME_AUTO_START` 7:45 · `TIME_BOOT` 7:55 · `TIME_PRESUBSCRIBE` 7:59 |
| 08:00~09:00 | ✗ | NXT 프리장 — LTV 매수 · 익일청산 · GTP |
| 09:00~15:20 | ✗ **D6** | KRX 정규장 |
| 15:20~15:30 | ✗ | `_force_clear_main_only` 15:20 · 종가단일가 청산 주문 |
| **15:30~16:00** | ⭕ **(B) 착지 후 신규 안전창 30분** | 주문 0 · KRX 연속체결 0 · REST 폴 15:20 종료. 🔴 **cycle295 자신은 이 창을 쓸 수 없다**(그 창은 이 사이클이 *만드는* 것이다). 그리고 §1-5 대로 **(A) 착지 전에도 쓰면 안 된다**(갭 홀드 ~120초 재무장) |
| 16:00~20:00 | ✗ 보유 시 | KRX 애프터 실시간 + 16:10 basics · 16:15 purge · 16:20 funnel · 16:30 master · 16:40 재무 · 19:00 토큰 · 19:50 매수중단 |
| 20:00~21:35 | ✗✗ **절대 금지 D8** | 20:00 자문+`unsubscribe_all`+`TIME_SESSION_START_CUTOFF` · 20:00:05 유니버스 · 20:05 metrics · 20:30 일봉 · 21:30 정산+리포트+retention+`_reset_daily_state`. 그 창의 재기동은 20:00 컷오프에 **거부**되어 저녁 블록 전체를 잃는다 |
| **21:35~07:45** | ⭕ | |
| **주말·공휴일 종일** | ⭕ | |

⚠️ cycle248 단서 — 이 금지는 backend 가 재생성되는 push(**full** 모드)에만 실질 적용된다.
모드가 불확실하면 **full 로 간주**한다.

⇒ **cycle295 의 배포 창 = 21:35~07:45 또는 주말.**

### 8-4 순서

```
[0] 오늘 15:38~16:04 실측 (§8-1)          ← 착수 전제
[1] trade_history 15:30~16:00 빈도 질의 (§4-5)
[2] 사용자 결정 회신 — §9 Q1~Q6 + (A)(B) 승인 (§7)
[3] (A) 갭 홀드 제거 커밋
      → Red(G-D1~D4) → Green → 뮤테이션 M1~M4·M12
      → 문서 동기화(§6-1·§6-4) + sha 핀 4곳 lockstep + 트리 digest
      → 백엔드 전량 + TZ=UTC + --log-level=DEBUG 재실행
      → 21:35 이후 배포
[4] D+1 판독 — switch_windows 1창 · 카나리아 4필드 · [tick_channel_flip] 정상
[5] (B) 주문 컷 커밋 (승인 후)
      → Red(T1~T13) → Green → 뮤테이션 M5~M16
      → order_engine sha 핀 9곳 + 문서(§6-4·§6-5)
      → 21:35 이후 배포
[6] D+1 판독 — [market_rest_window] 1행 ∧ 그 구간 주문 0건
```

⚠️ `[0]` 결과가 "15:30~16:00 에 프레임이 오고 주문도 나갔다" 면 **(B)가 즉시 시정으로
승격**되어 [3]과 [5]의 우선순위가 뒤집힌다.

### 8-5 롤백 — 🔴 "1커밋 revert" 가 아니다

| 축 | 비용 |
|---|---|
| 코드 | 프로덕션 6파일 ~173행 복원. 그 사이 `tick_channel_clock.py`·`routes/realtime.py` 를 건드린 사이클이 있으면 수동 병합(둘 다 최근 3사이클 연속 접촉) |
| **DB** | 🔴 `false` 행이 남아 있어 revert 만으로는 **행위가 안 돌아온다**. 복구는 **2단계** — ① revert + 배포 ② `PUT ... {"gap_hold_enabled": true}`. ①만 하면 조용히 OFF 이고 되돌린 사람이 "revert 가 실패했다" 고 오진한다 |
| 테스트 | G-D1~D4 의 "0건" 부정 단언 + 라벨 1개 단언을 다시 뒤집는다 |
| 핀·문서 | 트리 digest 1 + realtime sha 4 + 승인 집합 2 + 문서 14곳 재역전 |
| (B) 동반 시 | 커밋 2개 + **8영역 재승인** |
| **배포 창** | 🔴 되살리려는 이유가 "그 20분의 손절이 필요하다" 인데 그 시각대(16:00~20:00)를 금지하는 **명문 규칙은 없다** — D6 은 09:00~15:30, D8 은 20:00~21:35 다. 다만 2026-09-14 부터 그 구간이 KRX 애프터마켓 **실시간 연속체결**이라 재시작이 tick blind 를 만든다(D6 의 취지가 그대로 적용되는데 경계가 아직 그것을 반영하지 못했다 — §9-8 별건). 실효 복구는 그날 21:35 이후 또는 익일 07:45 전 |

⇒ **긴급 완화 수단은 코드가 아니라 사람**이다 — 그 구간 보유를 15:20 전에 정리하거나
익일청산으로 넘기는 운영 판단. 되살릴 필요가 생기는 트리거는 실질적으로 둘뿐(표가 바뀌어
KRX 가 15:40~16:00 에 연속체결을 갖거나, 사용자 결정이 바뀌거나)이고 전자의 감시자가
`test_cycle294b::test_n1` 이므로 **그 가드 존치가 되살리기 비용을 낮추는 유일한 구조적 장치**다.

---

## §9 열린 질문 — 사용자가 정해야 하는 것

### Q1 — 컷을 `order_exchange_clock_mode` 에 종속시킬 것인가
`_market_rest_now` 는 라우터 밖이므로 그 다이얼과 **무관**하게 만들 수 있다.
**권고 = 무종속.** 사용자가 없애자고 한 것이 다이얼인데, 롤백 다이얼 하나가 방금 없앤
참여를 조용히 되살리면 자기모순이다. 대가 = **장중 킬스위치가 없다**(롤백 수단은 1커밋
revert 뿐이고 그 재배포가 16:00~20:00 에는 실질적으로 막힌다(명문 금지가 아니라 **실시간 체결 중 재시작**이라는 D6 의 취지 — 경계 미반영은 §9-8 별건) — cycle287 이 이미 같은 제약을 안고
착지했다). 종속시키면 `mode="off"` 로 즉시 해제되지만 44/41 KRX 애프터 청산 변환도 함께
꺼지고, 그 다이얼은 **전략별**이라 보유 전략마다 PUT 해야 한다.

### Q2 — 특별 개장일 fail-open(§4-6)을 이 사이클에 넣을 것인가
표가 특별일을 모르므로 지연 개장일 15:30~16:00 은 **연속체결 중인 정규장**인데 컷이 30분
무음 차단한다. **권고 = 넣는다** — `ticker_last_tick` 최근 갱신 AND + `[market_rest_reality_mismatch]`
CRITICAL. 컷의 전제가 곧 해제 조건이라 새 규칙이 아니다. 빼면 §4 에 "연 1회 특별 개장일에
30분 실거래 차단" 을 명시해야 한다.

### Q3 — `POST /api/trading/manual-sell`(§4-7) 처분
① 게이트를 이 라우트에도 건다(운영자 수동 조작을 막는 것이 옳은지는 사용자 판단) /
② 명시 면제 + 응답 message 에 "휴식 구간" 경고 / ③ `execute_sell` 위임으로 전환
(cycle287 구멍 — 애프터 호가유형 미변환 + 실패 시 stale `_selling` — 까지 한 번에 닫히지만
8영역 diff 와 행위 반경이 커진다).
**권고 = ②를 이 사이클, ③을 별도 카드.** 어느 쪽이든 §6-5 판독표에 명시가 **필수**다.

### Q4 — [미실측] 15:30~15:40 거부의 msg_cd
NXT AFTER_SINGLE 거부가 실제로 `is_market_closed_rejection`(APBK0918)에 걸리는지 로그로
확인하지 못했다. 다른 코드면 §4-1 의 "다음-09:00 래치" 부분은 성립하지 않고 "헛 왕복 3회"
만 남는다. 어느 쪽이든 컷이 이득인 방향은 같지만 **크기가 다르다**. §8-1 #5 로 답한다.

### Q5 — `execute_buy` 대칭 블록을 이 사이클에 넣을 것인가
그 구간 매수는 구조적 0(LTV `tradable_boards` 에 `post_nxt` 없음)이라 실효가 없고, 넣으면
8영역 diff 가 커지며 A-ATOMIC 가드 반경에 가까워진다. "미래 변경(post_nxt 재투입)에 대한
구조적 방어" 라는 목적에는 부합한다. **권고 = 넣는다**(자리가 A-ATOMIC 밖이고, 빼면
사용자가 말한 "완전 휴식" 이 매도 축에만 적용된다).

### Q6 — `clock_channel` 의 `priority` 를 남길 것인가
**권고 = 남긴다**(승인 파일 1개 절약 > 인자 1개 위생, §2-3). 사용자가 `scanner.py` 접촉을
열어 준다면 깨끗이 지우는 쪽이 낫다.

### Q8 — 배포 금지 창의 경계가 애프터마켓을 반영하지 못한다 (별건, 이 사이클 범위 밖)

루트 `CLAUDE.md` 운영 가이드는 **D6 = 보유 중 09:00~15:30** · **D8 = 20:00~21:35** 이고
장외 배포 창을 "15:30~19:55 · 21:35~익일 07:45" 로 적는다. 그런데 2026-09-14 부터
**16:00~20:00 이 KRX 애프터마켓 실시간 연속체결**이라 그 창의 재시작은 D6 이 막으려던 것과
같은 tick blind 를 만든다. 즉 **"15:30~19:55" 서술이 낡았다.**

실측 기준 실제 공백 = **15:30~16:00**(이 사이클이 만드는 휴식 구간과 정확히 일치) 과
**21:35~익일 07:45**. 그 둘만 안전하다.

D6 의 경계를 고치는 것은 운영 규약 변경이라 사용자 결정 사항이고 이 사이클에 넣지 않는다.
다만 §8 배포 창 표는 이 사실을 반영해 적었다.

### Q7 — 보조 레버 (이 사이클 **범위 밖**, 후속 카드)
`scheduler.py:62` `TIME_POST_NXT_OPEN = time(15, 40)` 을 **16:00** 으로 옮기면 보드 축에서도
같은 규칙이 성립한다(POST_NXT 보드 = KRX 애프터와 정확히 일치). 지금은 LTV 운영 DB 에
`post_nxt` 가 없어 실효 0 이지만, 누군가 그 값을 되돌리는 날 보드 축이 컷과 어긋난다.
`scheduler.py` 접촉(승인) + 보드 의미 변경이라 **이 사이클에 넣지 않기를 권고**한다.

---

## 부록 A — 착수 전 체크리스트

- [ ] §8-1 실측 7항목
- [ ] §4-5 `trade_history` 15:30~16:00 빈도 질의
- [ ] §9 Q1~Q6 사용자 회신
- [ ] §7-1 (A) 승인 · §7-2 (B) 승인
- [ ] `git status --porcelain` 깨끗 확인(핀 갱신 전)
- [ ] `test_cycle276::_APPROVED_EIGHT_AREA_PINS` 의 cycle293/294 잔여 항목이 죽은 값인지
      `git diff HEAD --name-only -- src/realtime src/engine/risk.py src/engine/scanner.py` 로 확인
- [ ] `TZ=UTC` · `--log-level=DEBUG` 재실행 계획(메모리 「CI 환경 차이 교훈 2건」)
- [ ] 모든 시각 고정 테스트의 날짜 ≥ **2026-09-14** pin (§3-4 · §5-5)
