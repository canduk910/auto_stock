# cycle294 — 시세 채널 **3단계(시간축 전환) · 통합 채널 소멸** 명세

| | |
|---|---|
| 상태 | **명세만.** 프로덕션 코드·테스트 변경 0 |
| 작성 | 2026-09-14 17:0x (KRX 애프터마켓 시행 첫날 저녁) |
| 선행 | cycle292(장운영 구독 leaf) + **cycle293(2단계 속성축 배관)** — 둘 다 **미커밋 워크트리**. 이 문서의 모든 줄번호·sha·API 는 **현재 워크트리** 기준 |
| 목표 | **`H0UNCNT0` 구독을 0으로 만든다.** 09-15 07:45 부팅부터 `H0STCNT0`(KRX 전용) + `H0NXCNT0`(NXT 전용) 2채널 |
| 근거 | 2026-09-07 사용자 결정(`_workspace/consult/2026-09-07_channel_split_by_session.md`) + 2026-09-14 재확인 + **09-14 16:39~16:41 라이브 실측**(cycle293 §7-C). **재론 대상 아님** |
| 승인 | 8영역 5파일 = `scanner.py`·`websocket.py`·`websocket_pool.py`·`order_engine.py`·`risk.py`(2026-09-14). 이 명세는 그중 **4파일만** 쓴다 — `order_engine.py` 는 **diff 0**(§10-A) |
| 무접촉 | `scheduler.py`(**3,726L**) · 전략 7파일 · `strategy_base.py` · `market_state.py`(**읽기만**) · `handler.py` · `session.py` · `strategy_registry.py` · `api/order.py` · `auth/**` |
| 배포 | 커밋·push 금지. 창 = **21:35 이후**(20:00~21:35 금지 = D8). 배포 전 §14-A 게이트 3건 |

---

## §0 이 문서가 정하는 것 / 이미 정해진 것

**이미 정해진 것(재론 금지)** — 통합 채널 폐기 · 구간표(아래) · 전환 1회.

```
08:00~08:50  프리장        → H0NXCNT0   (그 시각 NXT 만 열려 있다)
08:50~09:00  전환 창        → 주문 0건 · cycle241 시장 침묵 ⇒ 전환 비용 ≈ 0
09:00~20:00  정규장+애프터  → H0STCNT0   (전환 0회, 연속)
```

자문 §7-④ 의 **15:34 NXT 애프터 전환은 넣지 않는다** — cycle287 이 애프터 주문을 KRX 로 보내므로(`_route_exchange_by_clock` 애프터 → `krx_by_clock`) 그 구간에 KRX 가격을 보는 것이 정합이다(평가 가격 = 체결 가격).

**이 문서가 정하는 것** — §1 시각축의 코드 계약 / §2 프리장 `nxt_false` 처분 / §3 새 fail-open / §4 전환 규약 / §5 자동 원복 / §6 🔴 매수 축 게이트 재정의 / §7 통합 채널의 마지막 두 구독 / §8 부팅·20:00 이후 / §9 롤백 / §14 못 하는 것.

**표기** — 측정하지 않은 것은 전부 **[추론]** 으로 표시한다.

---

## §1 구간표를 코드 계약으로 (질문 1)

### 1-A 무엇을 읽는가 — `get_market_table(on_date)` **공개 API**

`market_state.py` 는 `test_cycle293_ast::test_a1`(sha `7cef2efe…`)·`test_cycle287_ast_scope`·`test_cycle290`·`test_cycle291` 에 핀돼 있다. **읽기만 한다.**

읽는 것은 `MARKET_TABLE` **직접**이 아니라 **`get_market_table(on_date) -> tuple[ResolvedRow, ...]`** 다. 이유:

* `MARKET_TABLE` 을 직접 순회하면 `effective_from`/`effective_to` 를 스스로 해석해야 한다. `K6`(애프터마켓)은 `effective_from=2026-09-14`, `K7`(시간외 단일가)은 `effective_to=2026-09-12` 다 — 날짜 해석을 빠뜨리면 09-13 이전 날짜에서 20:00 이 나오고 그건 거짓이다.
* `market_state._is_effective` 는 **private** 이다. 공개 API 가 그 일을 이미 한다(`get_market_table` docstring: "**날짜는 이 표의 계약이다**").
* `ResolvedRow` 는 우리가 쓰는 네 필드를 전부 갖는다 — `market` · `start` · `end` · `phase` · `match_kind`.

### 1-B 세 경계값 — 전부 표에서 파생

| 이름 | 정의(질의) | 09-15 값 | 출처 행 |
|---|---|---|---|
| `nxt_pre_end` | `max(r.end for r in rows if r.market=="NXT" and r.phase is MarketPhase.PRE_MARKET)` | **08:50** | N1 |
| `krx_regular_open` | `min(r.start for r in rows if r.market=="KRX" and r.phase is MarketPhase.REGULAR)` | **09:00** | K3 |
| `krx_continuous_end` | `max(r.end for r in rows if r.market=="KRX" and r.match_kind=="continuous")` | **20:00** | K3(15:20)·**K6(20:00)** |

⚠️ `krx_continuous_end` 는 `match_kind=="continuous"` 로 고른다 — `phase` 로 고르면 `REGULAR`(15:20)와 `AFTER_MARKET`(20:00)을 **둘 다 열거**해야 하고, 다음에 KRX 가 연속 구간을 하나 더 신설하면 그 열거가 조용히 낡는다. `match_kind` 는 "실시간 접속매매인가" 라는 성질이라 신설 구간을 자동으로 흡수한다.

⚠️ `K7`(시간외 단일가, `match_kind="periodic_auction"`)은 이 질의에 걸리지 않는다 — 걸렸다면 09-12 이전 날짜에서 18:00 이 섞였을 것이다. `effective_to` 해석과 `match_kind` 필터가 **이중으로** 막는다.

### 1-C 전환 시각 = **파라미터**(시각 리터럴 0건)

```
span      = (krx_regular_open − nxt_pre_end) 초                     # 09-15 = 600
offset    = clamp(tick_channel_switch_offset_secs, 0, span)         # 기본 300
switch_at = nxt_pre_end + offset                                    # 09-15 = 08:55
전환 창    = [switch_at, krx_regular_open)                           # 09-15 = 08:55~09:00
```

* 기본값 **300초(= 08:55)** 권고. 근거 = 전환 창 5분이 120초 루프 2~3사이클을 담고(§4-B), 09:00 개장 전에 반드시 끝난다.
* `span <= 0`(표가 바뀌어 프리장 종료 ≥ 정규장 개장)이면 전환 창이 **빈 구간**이 되어 전환이 0건이다 — fail-safe. 예외를 던지지 않는다.
* **시각 리터럴 0건 강제** = `test_a15`(cycle293)와 같은 방식의 AST 가드를 신규 leaf 2파일에 확장한다(§12 G-294-1). `time(8, 55)` 류 호출·`"08:55"` 류 문자열이 소스에 0건이어야 한다. 주석의 `08:55` 도 **상수명 인용**(`nxt_pre_end + offset`)으로 쓴다 — cycle285 선례.

### 1-D 시각축 판정 함수 (신규 leaf, 순수)

```python
# src/engine/tick_channel_clock.py  — 신규 leaf (8영역 밖). 순수·never-raise.
#   market_state 는 **읽기만** 한다. await/DB/HTTP 0.

def _windows(on_date):
    """(krx_regular_open, nxt_pre_end, krx_continuous_end) — 없으면 None."""
    from src.engine.market_state import MarketPhase, get_market_table
    rows = get_market_table(on_date)
    krx_open = min((r.start for r in rows
                    if r.market == "KRX" and r.phase is MarketPhase.REGULAR), default=None)
    nxt_end  = max((r.end   for r in rows
                    if r.market == "NXT" and r.phase is MarketPhase.PRE_MARKET), default=None)
    krx_end  = max((r.end   for r in rows
                    if r.market == "KRX" and r.match_kind == "continuous"), default=None)
    return krx_open, nxt_end, krx_end


def clock_channel(now, *, offset_secs) -> tuple[str, str]:
    """(tr_id, reason). 🔴 통합 채널(`TICK_TR_ID`)을 **절대 반환하지 않는다**."""
    from src.engine.scanner import TICK_TR_ID_KRX, TICK_TR_ID_NXT
    try:
        if day_reverted(now):                       # §5 자동 원복 래치
            return TICK_TR_ID_NXT, "day_reverted"
        krx_open, nxt_end, krx_end = _windows(now.date())
        if krx_open is None or krx_end is None:
            return TICK_TR_ID_KRX, "table_incomplete"     # §3 fail-open
        sw = switch_at(now.date(), offset_secs=offset_secs) or krx_open
        if now.time() < sw:
            return TICK_TR_ID_NXT, "pre_window"
        if now.time() < krx_end:
            return TICK_TR_ID_KRX, "krx_window"
        return TICK_TR_ID_KRX, "post_close"         # 20:00 이후 = 구독 자체가 없다
    except Exception:
        return TICK_TR_ID_KRX, "clock_error"        # §3 fail-open
```

### 1-E 합성 — 시각축 × 속성축

```python
# src/engine/scanner.py — cycle293 `_classify_channel` 을 **그대로 재사용**한다.
def _resolve_channel(ticker, now, *, offset_secs) -> tuple[str, str]:
    chan, why = tick_channel_clock.clock_channel(now, offset_secs=offset_secs)
    if chan == TICK_TR_ID_KRX:
        return TICK_TR_ID_KRX, why                  # KRX 창 — 속성축을 보지 않는다
    # 프리 창(또는 day_reverted) — NXT 에서 거래되지 않는 종목만 KRX 로 내린다
    desired, attr_reason, decided = _classify_channel(ticker)
    if decided and desired == TICK_TR_ID_KRX:       # = no_feed 확정 ∧ 출처 권위
        return TICK_TR_ID_KRX, f"{why}|{attr_reason}"
    return TICK_TR_ID_NXT, f"{why}|{attr_reason}"   # 미지·출처미확인·nxt_feed → NXT
```

🔴 **`_classify_channel` 의 `TICK_TR_ID`(통합) 반환이 여기서 전부 NXT 로 흡수된다** — 그것이 규칙 1(통합 반환 0)의 구조적 보증이다. `_classify_channel` 자체는 **byte 동일**로 남긴다(cycle293 의 출처 검사·극성·fail-open 근거를 재작성하지 않는다).

**소비 지점 4곳**(cycle293 이 만든 자리 그대로, `now` 인자만 추가):

| 함수 | 성질 | 3단계 변경 |
|---|---|---|
| `tick_tr_id_for(ticker, *, priority, now=None)` | 적용형(이력 변이 O) | 내부 `_classify_channel` → `_resolve_channel` |
| `desired_tick_tr_id(ticker, *, priority, now=None)` | **순수** | 동일 |
| `subscribed_tick_tr_id(ticker, *, priority, now=None)` | 구독 사실 우선 | 폴백만 `desired_tick_tr_id` |
| `emit_tick_channel_config(tickers)` | 카나리아 | 집계 라벨 3분할(§11) |

`now=None` 은 `datetime.now(KST_TZ)` — **기본 인자에 `datetime.now()` 를 넣지 않는다**(모듈 로드 시각 동결).

---

## §2 프리장(08:00~08:50)의 `nxt_false` 종목 (질문 2)

### 2-A 사실 — 그 구간에 그 종목의 시장이 **없다**

| 시장 | 08:00~08:20 | 08:20~08:50 |
|---|---|---|
| NXT | N1 프리마켓 **연속 체결** | N1 연속 체결 |
| KRX | 행 없음(K1 은 08:20 시작) | K1 **시가 단일가** — 09:00 일괄 체결, 그 전 체결 0 |

`nxt_tradable=False` 종목은 NXT 에서 거래되지 않고, KRX 는 단일가라 체결이 없다 ⇒ **어느 채널을 골라도 08:00~08:50 프레임은 0**이다. 이건 결함이 아니라 시장 사실이다.

⇒ **판단 기준이 "손절 커버리지" 가 아니라 "전환 비용" 으로 바뀐다.** 세 선택지의 커버리지는 **동일하게 0**이다.

### 2-B 선택지 비용

| | 08:00~08:50 커버리지 | 09:00 개장 시 | 전환 | 그 밖의 비용 |
|---|---|---|---|---|
| **(가) `H0STCNT0` 유지** | 0 (시장 없음) | 이미 KRX 채널 — **개장 첫 틱 즉시 수신** | **0회** | KRX 시가단일가 예상체결 프레임이 온다면 프리장 왜곡 틱 노출(§2-D) |
| (나) 그 구간 미구독 | 0 | 09:00 에 **신규 구독 ~120건 폭주** + 첫 틱 지연(U-4 ≤4초 표본 1건) | 0회 | 🔴 "구독을 안 한다" = **P0-1 재현 방향**(절대 규칙 1 위반). 41 슬롯 예산이 시각에 따라 흔들려 `[priority_drop]` 판독이 깨진다 |
| (다) NXT 로 보냈다가 08:55 전환 | 0 | 전환 성공에 의존 | **1회** | 전환 폭이 ~120종목 늘어 §4 실패 노출이 커진다. 이득 0 |

### 2-C 채택 — **(가)**

§1-E 합성 규칙이 그대로 (가) 다: 프리 창에서 `no_feed 확정 ∧ 출처 권위` 인 종목만 `H0STCNT0` 에 남긴다.

* **전환 대상이 줄어든다** — 08:55 전환 대상 = 구독 종목 중 NXT 에 앉은 것(= `nxt_true` + 출처 미확인). 09-14 실측(구독 146 중 `nxt_false` ≈62, 보유 12 중 4)으로 보면 전환 폭이 **약 40% 줄어든다**. 전환은 이 사이클의 유일한 새 위험이므로 폭을 줄이는 것이 곧 위험을 줄이는 것이다.
* **보유 중인 `nxt_false` 의 08:00~09:00 손절 커버리지**(질문의 판단 기준) = 세 선택지 모두 **0**이고, 그 0 은 시장이 없어서 생긴 0 이다. (가)는 그 위에 **09:00:00 첫 체결을 전환 없이** 받는다 — 세 선택지 중 09:00~09:00:30(REST 폴 시작 전, 부록 A 의 기존 사각)을 가장 먼저 닫는다.

### 2-D 딸려 오는 새 노출 — [추론] + D+1 관측

`H0STCNT0` 이 08:20~09:00 KRX 시가 단일가 구간에 프레임을 보내는가?

* **[추론, 확신 ≈80%] 보내지 않는다** — `H0STCNT0` 은 **체결가** 채널이고 단일가 구간에는 체결이 없다. 예상체결가는 별도 TR(`H0STANC0` 계열)이다.
* 만약 보낸다면: 그 프레임이 `risk.on_tick` → `check_exit_signal` 로 들어간다. 다만 **08:00~09:00 은 `PRE_NXT ∈ active ∧ MAIN ∉ active`** 라 `risk._defers_pre_market_exit`(`risk.py:203`)가 LTV 외 6전략의 청산 평가를 이미 보류한다. 노출은 **LTV 보유 `nxt_false` 종목** 한정.
* **행위를 바꾸지 않는다.** 관측만 넣는다 — `[tick_channel_pre_krx_frame] ticker= n= first_at=` 1회/일(`KstDailyEmitCap`). D+1 에 `n=0` 이면 추론이 맞았고, `n>0` 이면 별도 결정 카드로 올린다(게이트 추가 = 매매 행위 변경이라 승인 대상).

---

## §3 새 fail-open 대상 (질문 3)

### 3-A 왜 다시 정해야 하는가

cycle293 §3-D 의 "판정 실패 → `TICK_TR_ID` 현행 유지" 는 **2단계 한정 과도기 장치**라고 그 문서가 스스로 못박았다. 3단계는 통합을 반환 경로에서 지우므로 그 폴백이 **성립하지 않는다.**

### 3-B 실패 층위 3개 — 층마다 답이 다르다

| 층 | 실패 사례 | 폴백 | 근거 |
|---|---|---|---|
| **L1 시각축** | `get_market_table` 예외 · 표 행 부재 · `now` 없음 | **`H0STCNT0`(KRX)** | ① 09-14 16:39 실측이 `H0STCNT0` 의 **종목 속성 무관 수신**을 확정했다(§0) ② 하루 구독 수명 07:59~20:00 **12시간 1분** 중 KRX 창이 **11시간 5분 = 92%** — NXT 가 유일 출처인 구간은 08:00~08:50 **50분**뿐이다 ③ `H0STCNT0` 은 **모의(VTS) 지원** TR_ID 다(`H0UNCNT0`/`H0NXCNT0` 는 미지원 — cycle293 P-7). 폴백이 KRX 여야 VTS 환경이 산다 |
| **L2 속성축** | `no_feed_registry` 미적재·예외·출처 미확인 | **프리 창에서 `H0NXCNT0`(NXT)** | 🔴 **비대칭이 방향을 정한다.** 모르는 종목을 KRX 로 보내면 진짜 `nxt_true` 의 프리장 체결을 **새로 잃는다**(INV-1 위반 — 오늘은 통합 채널이 그것을 준다). NXT 로 보내면 진짜 `nxt_false` 가 프레임 0 이 되는데 **그 구간엔 그 종목의 시장이 없어 잃을 것이 0** 이다(§2-A). ⇒ **잃을 수 있는 쪽을 보존한다.** KRX 창에서는 속성축을 아예 보지 않으므로 이 층이 존재하지 않는다 |
| **L3 킬스위치** | `tick_channel_resolver_mode == "off"` | **`TICK_TR_ID`(통합)** | 유일한 통합 반환 경로. "오늘 배포 전과 동일" 이 `off` 의 정의다(절대 규칙 8). 상수 `TICK_TR_ID` 는 `test_cycle257::_PRESERVED_TICK_CONSTS` 가 리터럴 핀하므로 **삭제하지 않는다** — 반환 경로에서만 사라진다 |

### 3-C "시각도 모를 때"

`now` 를 못 얻는 경우(`datetime.now` 예외 = 사실상 불가) 또는 `now` 가 tz-naive 로 들어온 경우 → **L1 = `H0STCNT0`**. 그 이유는 3-B ②③ 그대로다. **"구독을 안 한다" 로는 절대 가지 않는다**(절대 규칙 1 · P0-1 재현 방향).

### 3-D 🔴 L2 fail-open 이 W2 오염을 **자동으로 무해화한다** (cycle293 §6-C 재해석)

cycle293 이 출처(provenance) 검사를 만든 이유는 "07:59 사전 구독 시각에 `nxt_tradable` 을 그대로 읽으면 **진짜 NXT 종목 ≈420개를 KRX 채널로 보낸다**" 였다(`_full_universe_load_krx_primary` 의 `nxt_tradable=False` 도장, 07:45~08:08 창, 07:59 에 2,344/3,583 = 65.4% 오염).

3단계에서는 **프리 창의 미판정 폴백이 NXT** 이므로, 출처 검사가 실패한 그 420종목은 **정답인 NXT 로 간다.** 즉 출처 검사의 실패 비용이 2단계에서는 "KRX 오배치" 였는데 3단계에서는 **0** 이다.

⇒ 출처 검사를 **없애지는 않는다**(프리 창에서 `nxt_false` 를 KRX 로 **내리는** 판단에는 여전히 권위가 필요하다 — §2-C 의 전환 폭 축소 이득이 거기서 나온다). 그러나 **W2 오염 창이 3단계의 위험 목록에서 빠진다.** 이 사실을 `_resolve_channel` docstring 에 적는다.

---

## §4 전환 규약 (질문 4)

### 4-A 언제 — 창 안에서만, 창 밖은 **전환 금지**

```
전환 실행 창 = [switch_at, krx_regular_open)      # 09-15 = 08:55~09:00
```

🔴 **창 밖에서는 어떤 경로도 살아 있는 구독의 채널을 바꾸지 않는다.** cycle293 §3-C("살아 있는 구독을 바꾸는 경로를 만들지 않는다")는 3단계에서 **폐기가 아니라 창 밖으로 축소**된다.

왜 창을 벗어나면 안 하는가 — 세 가지가 동시에 성립한다:

1. **그 창에만 프레임이 구조적으로 0 이다.** NXT N2 휴장 + KRX K1 단일가 ⇒ 이중 채널 구간(§4-C)에 프레임이 흐르지 않는다 ⇒ `tick_volume.record_acml_vol` 의 last-write-wins 비결정론(cycle293 §5-A 2)이 **노출되지 않는다**. 정규장 중에 전환하면 두 채널이 동시에 프레임을 주고 BFB/VCP 거래량 게이트가 도착 순서에 좌우된다.
2. **그 창에 주문이 0 건이다**(설계 · cycle241 시장 침묵 실측 — 30일 522건 중 491건(94%)이 08:50~09:00·15:20 이후 전원 동시 발화, **09:00~15:20 정규장 0건**).
3. **못 옮겨도 blind 가 아니다.** 미전환 잔여는 `H0NXCNT0` 에 남고, NXT 는 09:00:30~15:20 정규장(N3)·15:40~20:00 애프터(N6)에 체결을 싣는다 ⇒ 프레임이 계속 온다. **"늦으면 안 옮긴다" 의 비용은 'KRX 가격 대신 NXT 가격을 본다' 뿐이다.**
   ⚠️ 단 `nxt_false` 종목은 애초에 프리 창에서도 KRX 에 있으므로(§2-C) 이 잔여 집합에 들어오지 않는다.

미전환 잔여가 있는 채로 창을 지나치면 `[tick_channel_switch_window_missed] n= sample= reason=` **WARNING 1회/일**.

### 4-B 누가 트리거하는가 — `stale_watcher_core` (120초)

`scheduler.py` 무접촉이므로 기존 주기 루프 중 하나에 얹어야 한다. 후보 비교:

| 루프 | 주기 | 08:55 에 도는가 | 판정 |
|---|---|---|---|
| `_stale_watcher_loop` → `stale_watcher_core.check_and_resubscribe_stale` | **120초** | ✅ `start()` 에서 생성(`scheduler.py:649`), 07:45~ 종일 | **채택** |
| `_scan_loop` → `scanner.subscribe_filtered_stocks` | 300초 | ❌ **`TIME_SCAN_START`(09:30) 에 생성**(`scheduler.py:846`) — 08:00~09:30 에 존재하지 않는다 | 09:30 지각 백스톱으로만 |
| `_session_loop` | 60초 | ✅ | `scheduler.py` 안이라 접촉 불가 |
| `_session_health_loop` | 300초 | ✅ | 주기가 창(5분)과 같아 0~1회 — 불안정 |

* `stale_watcher_core.py` 는 **8영역 밖**이다(8영역 = `src/engine/{risk,order_engine,session,scanner,strategy_registry}.py` · `src/api/order.py` · `src/realtime/**` · `src/auth/**`). 승인 불요.
* 호출 자리 = `check_and_resubscribe_stale` 의 `await no_feed_registry.ensure_fresh(_classify_targets)` **직후**, stale 판정 루프 **앞**. 레지스트리가 더워진 뒤여야 §1-E 합성이 성립하고, stale 판정 전이어야 전환 직후 종목이 같은 사이클에서 stale 로 오인되지 않는다.
* **never-raise** — 전환 실패가 4중 안전망의 한 축(120초 stale watcher)을 끊으면 안 된다. cycle252/293 의 `try/except + logger.debug` 관례 그대로.
* 창 5분 ÷ 120초 = **2~3 사이클**. 사이클당 예산(§4-E)이 그 안에 전량을 담는다.

### 4-C HIGH make-before-break — 정확한 단계 순서

🔴 **절대 규칙 2. 생략하면 자문이 기각으로 바뀐다.**

```
switch_high(ticker, new_tr_id):
  S0  old = pool._ticker_to_tr_id.get(ticker)
      if old is None or old == new_tr_id:  return "noop"        # 예산 소모 0
  S1  session = pool._ticker_to_session.get(ticker)             # 🔴 세션 재추첨 금지
      if session is None:  return "no_route"                    #    (§4-D 근거)
  S2  await session.subscribe(new_tr_id, ticker, bypass_limit=True)   # ← 등록 먼저
  S3  ACK 확인 — 0.2초 간격 폴링, 상한 tick_channel_switch_ack_timeout_secs(기본 5.0)
        확인 술어 = (new_tr_id, ticker) in session._subscriptions
                  ∧ (new_tr_id, ticker) in session._subscriptions_acked
  S4  ACK 실패 →  await session.unsubscribe(new_tr_id, ticker)  # 고아 튜플 즉시 회수
                  [tick_channel_switch_failed] WARNING
                  그날 그 종목 전환 포기(_switch_giveup_today.add)
                  🔴 _channel_flipped_today 는 **소모하지 않는다** — 실패가 예산을
                     먹으면 그날 재시도가 막힌다(cycle293 §6-D 는 성공 전환만 센다)
                  return "ack_timeout"                          # 구 채널 그대로 = blind 0
  S5  ACK 성공 →  await session.unsubscribe(old, ticker)        # ← 이제 해제
  S6  pool._ticker_to_tr_id[ticker] = new_tr_id                 # 병행 dict 갱신
      scanner._channel_applied[ticker] = new_tr_id
      scanner._channel_flipped_today[ticker] = True
      [tick_channel_switch] INFO 1행
```

**LOW 는 break-before-make**(cycle293 §5-C 4단 순서 그대로): `unsubscribe(old)` → 라우팅 pop 확인 → `subscribe(new)` → 튜플 실재 확인. 근거 = LOW 는 후보이고 그 창에 프레임이 0 이라 잃을 것이 없다. 슬롯·SEND 를 아끼고 실패해도 다음 120초 사이클이 재시도한다.

### 4-D 🔴 왜 **같은 세션**을 강제하는가

`pool.unsubscribe` 는 `_ticker_to_session.pop(tr_key)` 로 찾은 **한 세션**만 본다(`websocket_pool.py:528-557`). make-before-break 에서 신규 구독을 라운드로빈으로 **다른** 세션에 떨어뜨리면:

* `_ticker_to_session[ticker]` 가 새 세션으로 덮이고 → S5 의 해제가 **새 세션에서** `(old, ticker)` 를 찾는다 → 없다 → 구 세션의 `(old, ticker)` 가 **영구 고아**로 41 슬롯을 잠식한다(cycle253 이 프로브에서 같은 함정을 밟아 `_unsubscribe_probe_everywhere()` + `_release_routing_if_orphaned()` 두 헬퍼를 만든 그 이유, `routes/realtime.py:144-192`).

⇒ 전환은 **세션 안 채널 교체**다. 세션은 건드리지 않는다. HIGH 는 정의상 메인 세션 + `bypass_limit=True` 이므로 슬롯 부족이 구조적으로 없다. LOW 가 세션 만석이면 S2/재구독이 drop 되고 다음 사이클이 재시도한다.

⚠️ **`_ticker_to_session` 재키잉 금지**(cycle293 C-1)는 그대로다. 이중 채널 창 1~5초 동안 `_ticker_to_session[ticker]` 는 **같은 세션**을 가리키므로 값이 바뀌지 않는다 — 재키잉이 필요 없는 유일한 이유가 §4-D 의 세션 고정이다.

### 4-E 예산·순서·관측

| 항목 | 값 | 근거 |
|---|---|---|
| 처리 순서 | **HIGH(positions ∪ next_day_clear) 전부 → LOW** | 손절 커버리지 우선 |
| 사이클당 상한 | `tick_channel_switch_max_per_cycle` 기본 **80** | 3사이클 × 80 = 240 ≥ 실측 구독 146 |
| 사이클 소요 상한 | `tick_channel_switch_budget_secs` 기본 **90초** | 120초 루프를 굶기지 않는다. 초과 시 중단 후 다음 사이클 |
| 종목 간 간격 | `asyncio.sleep(0.05)` | 기존 stale 재구독 관례와 동일 |
| **순간 최대 이중 튜플** | **1** | 종목 단위 완료 후 다음(순차 계약). 실측 풀 잔여 168 슬롯 대비 무해 |
| `detect_dual_tick_channels()` 오탐 | 전환 중 종목을 `_switch_in_flight` 집합으로 제외 | 그 대조는 `subscribe_filtered_stocks`(09:30~)에서만 돌아 08:55 창과 겹치지 않지만, 방어적으로 제외한다 |

### 4-F 실패 시 롤백

| 실패 | 처분 |
|---|---|
| S3 ACK 타임아웃 | S4 — 신 채널 즉시 해제, 구 채널 유지, 그날 그 종목 포기. **blind 0** |
| S5 해제 실패 | 신 채널은 살아 있다(프레임 정상). `_ticker_to_tr_id` 는 **신 채널로 갱신**하고 `[tick_channel_switch_orphan] ticker= old=` WARNING. 구 튜플은 20:00 `unsubscribe_all()` 이 회수한다(`websocket_pool.py:559-577` 이 세 채널 전부를 훑는다) |
| LOW break 후 make 실패 | 그 종목 미구독 상태. 다음 120초 사이클의 stale watcher 가 재등록(구독 사실 기준이라 신 채널로) |
| 사이클 전체 예외 | never-raise 흡수 + `logger.debug`. 다음 사이클 재시도 |
| 창을 지나침 | §4-A — 전환 중단, `[tick_channel_switch_window_missed]` WARNING, 다음 영업일 07:59 신규 구독부터 정상화 |

### 4-G 전환 창 REST 백스톱 (절대 규칙 3) — **정직한 답**

요구는 "전환 도중 보유 종목 가격 갱신이 끊기지 않게 한다" 다. 조사 결과:

* 전환 창(08:55~09:00)은 **NXT 휴장 + KRX 시가 단일가**라 WS 로도 REST 로도 **새 체결가가 존재하지 않는다.** REST `FHKST01010100` 의 `stck_prpr` 는 그 구간에 전일 종가 또는 예상체결가를 준다 — 손절 판정에 넣으면 **없는 가격으로 청산을 평가**하는 것이고 그건 프리장 왜곡 틱 문제(2026-08-06 사용자 결정)의 재현이다.
* `open_price_rest`(cycle272)는 VB/LTV `_targets` 후보만 훑는다(`_pending_main_tickers`) — **보유 종목 백스톱이 아니다.**
* `_swing_rest_poll_loop` 는 `SWING_REST_POLL_EARLY_START=09:00:30` 부터다.

⇒ **백스톱은 REST 호출이 아니라 다음 셋의 조합으로 구현한다.** KIS 호출 증가 **0**.

1. **HIGH make-before-break**(§4-C) — 보유 종목의 blind 구간이 **구조적으로 0**이다. 신 채널 ACK 을 받은 뒤에야 구 채널을 끊는다.
2. **창 밖 전환 금지**(§4-A) — 09:00 이후로 밀린 종목은 아예 옮기지 않는다. 구 채널(NXT)이 정규장 체결을 계속 싣는다.
3. **미전환 잔여 관측**(§4-A `window_missed`) — 사람이 다음 아침에 본다.

🔴 이 절의 결론을 **완화가 아니라 사실**로 적는다: 절대 규칙 3 이 막으려는 "전환 때문에 생기는 가격 공백" 은 위 셋으로 0 이 된다. 그 창에 원래 가격이 없다는 것은 전환이 만든 것이 아니다.

---

## §5 자동 원복 트리거 (질문 5 · 절대 규칙 4)

### 5-A 무엇을, 언제, 얼마 동안 보는가

| | |
|---|---|
| **표본** | 그날 KRX 로 전환에 **성공한 HIGH 종목**(`_switched_high_today`) |
| **측정 시점** | `krx_regular_open + tick_channel_revert_probe_secs`(기본 **180초**) ⇒ 09-15 = **09:03** |
| **왜 개장 후인가** | 08:55~09:00 은 시장이 없어 프레임 0 이 정상이다. 거기서 재면 **100% 오탐** |
| **왜 180초인가** | 새 숫자를 만들지 않는다 — **`stale_diagnostics.SUBSCRIBE_GRACE_SECS = 180`**(구독 ACK grace, 사이클 135 사용자 결정 Q2=180s)의 **재사용**이다. "구독이 살아났다고 인정하기까지 주는 시간" 이라는 의미가 같다. 🔴 **재정의 금지** — 사이클 135 의 `G-AST-CONST`(단일 정의처)가 그 상수의 두 번째 정의를 RED 로 잡는다. 파라미터 기본값은 그 상수를 **import 해서** 쓴다(`_DEFAULT_REVERT_PROBE_SECS = SUBSCRIBE_GRACE_SECS`) |
| **판정 술어** | 표본의 **전원**이 `ticker_last_tick.get(t)` 부재 또는 `< krx_regular_open` |
| **최소 표본** | **2** — 미만이면 원복하지 않는다(cycle241 선례: 판정 가능 세션 < 2 면 fail-open). 저유동 1종목이 시스템 전체를 되돌리면 안 된다 |
| **교차 확인** | 같은 순간 **미전환 코호트**(프리 창부터 KRX 였던 `nxt_false` 또는 LOW) 중 **≥2 가 fresh** 여야 한다. 전체가 침묵이면 채널 문제가 아니라 세션·시장 문제다 ⇒ 원복 대신 `[tick_channel_revert_skipped] reason=market_wide` INFO. 기존 `_detect_silent_inactive_sessions` 경로가 그쪽을 담당한다 |

### 5-B 되돌리는 동작

1. `tick_channel_clock.set_day_revert()` — 그날 나머지 시간 동안 `clock_channel` 이 **`day_reverted`** 를 반환한다(§1-D). 그러면 `_resolve_channel` 이 **프리 창 규칙**을 종일 쓴다 ⇒ `nxt_true` → NXT · `nxt_false` → **KRX 유지**.
   🔴 이 설계가 중요하다. 단순히 "전원 NXT" 로 되돌리면 `nxt_false` 종목이 NXT 에서 프레임 0 이 되어 **원복이 새 blind 를 만든다.** 속성축을 존중해야 원복이 안전하다.
2. `_switched_high_today` 의 종목을 `H0NXCNT0` 로 **break-before-make** 되돌린다.
   * make-before-break 이 아닌 이유 = **원복 트리거의 전제가 "그 채널에 프레임이 0" 이다.** 잃을 프레임이 없는데 이중 채널 창(정규장 중 = 두 채널 다 프레임 있음 = `tick_volume` 비결정론)을 여는 것은 순손실이다.
3. `_reverted_today = True` — 그날 **전환도 원복도 더 이상 하지 않는다.**
4. `[tick_channel_auto_revert] n= sample= probe_secs= cross_fresh= reason=no_frame_after_open` **ERROR 1행**.
   * 레벨이 ERROR 인 이유 = 되돌렸다는 것은 §0 의 설계 가정(`H0STCNT0` 가 종목 속성 무관 수신)이 틀렸다는 뜻이다. `log_metrics_collector.pattern_by_level` 이 WARNING 이상을 21:30 리포트 `top_patterns` 에 넣으므로 INFO 로 두면 리포트에 한 글자도 안 뜬다(cycle245 `[ratio_cap_config]` 함정, cycle293 이 `[tick_channel_config]` 를 WARNING 으로 올린 그 이유).

### 5-C 되돌린 뒤 재시도

**그날은 없다.** 다음 영업일 07:59 신규 구독부터 자연 재시도한다(프로세스 상태는 `_sync_channel_day` 가 KST 날짜 경계에서 비운다).

근거 = 재시도가 왕복을 만든다. KIS 공지 「비정상 케이스 2: 무한 등록/해제」가 정확히 그것이고, cycle293 §6-D 가 "같은 날 재전환 금지" 백스톱을 둔 것과 같은 판단이다.

원복 **자체가 실패**하면 그 종목은 KRX 에 남는다 + ERROR 1행. 그다음은 기존 안전망이 받는다 — stale watcher 가 그 종목을 stale 로 잡아 **구독 사실 기준으로** 재등록한다(KRX 로). 최종 수단은 운영자의 `off`(§9).

---

## §6 🔴 매수 축 게이트 재정의 (질문 6 · 절대 규칙 5)

### 6-A 문제 — cycle293 의 술어가 3단계에서 뒤집힌다

cycle293 `risk._tick_buy_eval_blocked_by_channel` 의 술어는 **"이 종목이 전용 채널에 구독돼 있는가"** 다(`applied in DEDICATED_TICK_TR_IDS`). 3단계는 **모든** 종목을 전용 채널로 보낸다 ⇒ 전 종목 참 ⇒ `momentum` · `volatility_breakout` · `long_tail_volatility` · `bull_flag_breakout` · `vcp_breakout` **5전략의 틱 매수가 통째로 죽는다.**

`donchian_swing`/`kojiro` 는 `_TICK_BUY_EVAL_SKIP_STRATEGIES`(전략 축)로 이미 skip 이고 `_swing_buy_poll_loop`(REST)가 매수를 담당하므로 무영향이다. 즉 **5전략은 틱이 유일 매수 경로**이고, 이 축을 틀리면 **내일 아침 전 전략 매수 0** 이다.

### 6-B 술어의 원래 의도 = 채널이 아니라 **코호트**

cycle293 §3-E 가 막으려던 것은 "오늘까지 통합 채널에서 프레임이 **0건**이던 종목에 프레임이 새로 들어와 5전략의 매수 평가가 유니버스 64% 를 새로 잡는 것" 이다. 그 코호트는 **`nxt_tradable=False` ∧ 출처 권위 확인** 이다.

`nxt_true` 종목은 **어제도 통합 채널에서 프레임을 받았고** 5전략의 매수 평가를 이미 받고 있었다 ⇒ 3단계는 그들에게 **채널만 바꾼다** ⇒ 매수 평가가 **계속돼야 한다**.

### 6-C 구독 시점 **코호트 스탬프** — 코드 레벨

매 틱 레지스트리를 재조회하지 않는다(cycle293 적대 검증 CRITICAL: 판정과 구독 사실이 갈리면 게이트만 풀린다). **구독을 발사하는 시점에 코호트를 스탬프하고, 게이트는 그 스탬프만 읽는다.**

```python
# ── src/engine/scanner.py ──────────────────────────────────────────────────
#: ticker → 오늘 이 종목이 **통합 채널 무송출 코호트**인가 (구독 시점 확정).
#: `_sync_channel_day()` 가 KST 날짜 경계에서 `_channel_applied` 와 함께 비운다.
_channel_cohort: dict[str, bool] = {}


def _stamp_cohort(ticker: str) -> None:
    """cycle294 §6-C — 구독 발사 시점에 코호트를 **확신할 때만** 심는다.

    🔴 심지 않는 경우(= 스탬프 부재)는 게이트에서 **열린다**(fail-open). 그
    방향의 근거는 §6-D 비대칭이다. 스탬프가 부재하는 상황을 구조적으로 0 에
    가깝게 만든 것은 cycle293 이 `subscribe_filtered_stocks` 안에서 리졸버보다
    **먼저** `no_feed_registry.ensure_fresh(_channel_probe)` 를 부르게 한 덕이다
    (적대 검증 H1) — 구독되는 종목은 그 시점에 전부 분류돼 있다.
    """
    try:
        if not no_feed_registry.is_classified(ticker):
            return                                  # 미분류 → 스탬프 없음
        nf = bool(no_feed_registry.is_no_feed(ticker))
        if nf and not no_feed_registry.is_provenance_ok(ticker):
            return                                  # 출처 미확인 → 스탬프 없음
        # 🔴 하루 단방향(닫힘 우세) 래치 — 매수를 **여는** 방향의 하루 중 변화는
        #    다음 날로 미룬다. 닫는 방향(True)만 즉시 반영한다. 매일 리셋되므로
        #    cycle293 §6-D 가 금지한 '영구 좌초 래치' 와 다르다(그건 채널 축이고
        #    이건 매수 축이며 수명이 하루다).
        _channel_cohort[ticker] = bool(_channel_cohort.get(ticker, False) or nf)
    except Exception:                               # pragma: no cover — never-raise
        return


def tick_buy_cohort_blocked(ticker: str) -> bool:
    """오늘 이 종목이 무송출 코호트로 **확정**됐는가 — 읽기 전용·순수.

    상태를 변이하지 않는다(`_sync_channel_day` 의 날짜 리셋은 예외 — 그것은
    관측이 아니라 날짜 경계 자기 정리다). `risk.on_tick` 이 틱마다 부른다.
    """
    try:
        _sync_channel_day()
        return bool(_channel_cohort.get(ticker, False))
    except Exception:                               # pragma: no cover — never-raise
        return False
```

`_stamp_cohort(ticker)` 호출 자리 = `tick_tr_id_for()` 안, `_apply_channel_decision` **직전** 한 곳. 구독을 발사하는 유일한 적용형 진입점이라 스탬프가 구독과 1:1 이 된다.

```python
# ── src/engine/risk.py :: _tick_buy_eval_blocked_by_channel (본문 교체) ────
def _tick_buy_eval_blocked_by_channel(ticker: str) -> bool:
    """cycle294 §6 — **코호트 축** WS 틱 매수 평가 skip 판정.

    cycle293 은 술어를 「전용 채널에 구독돼 있는가」로 두었다. 3단계는 **모든**
    종목을 전용 채널로 보내므로 그 술어는 전 종목 참이 되어 momentum·VB·LTV·
    BFB·VCP 5전략의 틱 매수가 통째로 죽는다(그 5전략은 틱이 유일 매수 경로다).
    술어의 의도는 채널이 아니라 **코호트**였다 — 「통합 채널에서 프레임이 0건
    이던 종목에 프레임이 새로 들어오는가」.

    🔴 모드를 **보지 않는다.** cycle293 적대 검증이 찾은 함정 —
    킬스위치 `off` 는 이미 전용 채널에 올라간 구독을 되돌리지 않으므로(§9-B),
    모드를 보면 「사고 중에 누르는 안전 조치가 5전략의 매수를 그 코호트에
    열어 준다」. 스탬프는 모드와 무관하게 구독 사실을 따른다.

    B-2(매수 개방)는 이 함수 호출 1줄을 걷는 것이고 **별도 승인 +
    `domain-consult` + `ACML_VOL` 스코프 대조 1일**(U-3)이 선행 조건이다.
    """
    try:
        from src.engine.scanner import tick_buy_cohort_blocked

        return bool(tick_buy_cohort_blocked(ticker))
    except Exception:                               # pragma: no cover — never-raise
        return False
```

호출부(`risk.py:621` `chan_buy_blocked = _tick_buy_eval_blocked_by_channel(ticker)` · `:741` `if chan_buy_blocked: continue`)는 **byte 동일**이다. 순증 = 함수 본문 교체뿐.

### 6-D 왜 스탬프 부재를 **열어 두는가** (fail-open 방향)

| 방향 | 틀렸을 때 | 되돌릴 수 있나 |
|---|---|---|
| **열림 오류**(`nxt_false` 를 허용) | 승인 없는 매수 행위 변경. 유니버스 64% 신규 노출 | ❌ 체결은 취소되지 않는다 |
| **닫힘 오류**(`nxt_true` 를 skip) | 5전략 매수 기회 상실. 극단에서 **전 전략 매수 0** | ✅ 다음 사이클·다음 날 |

되돌릴 수 없는 쪽이 더 나쁘므로 원칙은 "닫는다" 여야 하지만, **절대 규칙 5 가 이 사이클의 최대 위험으로 지목한 것이 닫힘 오류의 극단**(전 전략 매수 0)이다. 그리고 닫힘 오류는 **레지스트리 전체 실패 한 번**으로 전 종목에 동시에 일어난다(상관된 실패) — 열림 오류는 종목별로 독립이다.

⇒ **스탬프 부재 = 열어 둔다(오늘과 동일)** + 그 상태를 **시끄럽게** 만든다:

* `[tick_buy_gate] stamped_no_feed=N stamped_feed=M unstamped=K` — 하루 1행 **WARNING**(리포트 진입). `K` 가 크면 스탬프 배선이 깨진 것이다.
* `unstamped` 가 구조적으로 0 에 가까운 근거 = cycle293 `test_a22_registry_is_warmed_before_the_resolver_runs` 가 "리졸버 호출 전에 `ensure_fresh`" 를 AST 로 잠갔다. 그 가드가 붉어지면 이 fail-open 의 전제가 무너진다 — **두 가드를 서로 인용**한다.

### 6-E `nxt_true` 가 매수 평가를 계속 받는다는 **증명 테스트**

```python
# tests/unit/engine/test_cycle294_buy_axis_cohort.py

def test_g294_b1_nxt_true_keeps_buy_eval_on_dedicated_channel():
    """🔴 절대 규칙 5 의 정면 증명 — 전용 채널인데 매수는 열려 있다."""
    # given: nxt_true(분류 성공 · no_feed=False) + 시각 09:30(KRX 창) + mode=enforce
    #        → tick_tr_id_for() == "H0STCNT0"  (전용 채널)  AND  스탬프 = False
    # when : risk.on_tick(ticker, price)
    # then : 5전략 전부 check_buy_signal 호출됨 (호출 수 == enabled 5)
    #        donchian/kojiro 는 전략 축 skip 이라 0 (기존 계약 불변)

def test_g294_b2_nxt_false_buy_eval_blocked():
    # is_no_feed=True ∧ provenance_ok=True → 스탬프 True → check_buy_signal 0회
    # 청산(check_exit_signal)은 **호출됨** — 이 게이트는 매수에만 영향한다

def test_g294_b3_all_dedicated_does_not_kill_all_buys():
    """🔴 이 사이클 최대 위험의 직접 재현 테스트."""
    # given: 100종목 전원 전용 채널. nxt_true 60 / nxt_false 40
    # then : check_buy_signal 이 불린 종목 집합 == nxt_true 60종목 (정확히)
    # 🔴 뮤테이션: 술어를 cycle293 것(`applied in DEDICATED_TICK_TR_IDS`)으로
    #    되돌리면 **0종목** → RED. 이 한 케이스가 회귀를 영구 봉인한다.

def test_g294_b4_unstamped_is_open():
    # is_classified=False → 스탬프 부재 → blocked=False (오늘과 동일)

def test_g294_b5_provenance_unknown_is_open():
    # is_no_feed=True ∧ provenance_ok=False → 스탬프 부재 → blocked=False

def test_g294_b6_kill_switch_off_does_not_open_the_cohort():
    """`off` 가 매수를 열지 않는다 — cycle293 적대 검증 CRITICAL 의 승계."""
    # given: 스탬프 True 로 확정된 종목. 그 뒤 mode → "off"
    # then : blocked 여전히 True (스탬프는 모드와 무관)

def test_g294_b7_stamp_latch_is_one_way_within_a_day():
    # True 로 심긴 뒤 레지스트리가 no_feed=False 로 뒤집혀도 그날은 True 유지
    # 날짜 경계(_sync_channel_day) 후에는 새로 심긴다

def test_g294_b8_gate_does_not_mutate_switch_budget():
    # 1,000회 호출 후 _channel_flipped_today / _channel_applied byte 동일
```

**AST 가드**(cycle293 `test_a18` 을 **대체**한다 — §12 G-294-6): 게이트 본문에 `tick_tr_id_for(` 0건 · `DEDICATED_TICK_TR_IDS` **0건**(3단계에서 그 술어는 틀렸다) · `tick_buy_cohort_blocked` 1건 · `current_mode` 0건.

⚠️ `test_a18` 을 **삭제하지 말고 본문을 교체**하고, 구 단언이 왜 틀리게 됐는지를 그 docstring 에 남긴다. 지우면 다음 사람이 "구독 사실을 읽어라" 를 되살려 5전략 매수를 다시 죽인다.

---

## §7 통합 채널의 마지막 두 구독 — `scheduler.py` 우회 (절대 규칙 1·7의 충돌)

### 7-A 사실

`scheduler.py` 무접촉 제약 때문에 두 줄이 계속 `TICK_TR_ID`(통합)로 **풀을 우회해** 직접 구독한다:

| 줄 | 무엇 | 빈도(실측) |
|---|---|---|
| `scheduler.py:1382` `await kis_ws.subscribe(TICK_TR_ID, ticker)` | 익일청산 대상 시가 수신. **bypass 없음** — 메인 41 만석이면 조용히 drop | 0~수 건/일 |
| `scheduler.py:2728` `await _kis_ws.subscribe(_TICK_TR_ID, t, bypass_limit=True)` | `_swing_buy_poll_loop` 매수 성공 직후 | 30일 11건 ≈ **0.4/일** |

⇒ 이 둘을 그대로 두면 **"통합 채널 구독 0" 이 성립하지 않는다.** cycle293 은 이것을 "고치지 않고 드러낸다"(`[tick_channel_dual_detected]`)로 처분했지만, 3단계의 목표는 소멸이다.

### 7-B 처분 — `KisWebSocket.subscribe` 에서 **레거시 재라우팅**

`websocket.py` 는 **접촉 허용 5파일 중 하나**다. `scheduler.py` diff 0 을 지키면서 통합 구독을 0 으로 만드는 유일한 자리다.

```python
# ── src/realtime/websocket.py :: KisWebSocket.subscribe 첫 문장 ────────────
tr_id = _reroute_legacy_unified(tr_id, tr_key)


def _reroute_legacy_unified(tr_id: str, tr_key: str) -> str:
    """cycle294 §7 — 통합 채널 요청을 전용 채널로 되돌린다(레거시 호출자 구제).

    🔴 재라우팅 조건은 **`tr_id` 가 정확히 통합일 때** 하나뿐이다. 3단계에서
    통합은 아무도 의도적으로 고르지 않는 값이므로, 통합 요청 = 「리졸버를 안
    거친 호출」 의 확실한 신호다. 전용 채널·체결통보(`H0STCNI0/9`)·장운영정보
    (`H0UNMKO0`) 요청은 이 함수를 **byte 동일**로 통과한다.

    풀의 세션들도 이 메서드를 쓰지만, 풀은 이미 리졸버가 고른 전용 채널을
    넘기므로 첫 조건에서 빠져나간다(멱등).
    """
    try:
        from src.engine import tick_channel_mode
        from src.engine.scanner import TICK_TR_ID, subscribed_tick_tr_id

        if tr_id != TICK_TR_ID:
            return tr_id
        if tick_channel_mode.current_mode() in (
            tick_channel_mode.MODE_OFF, tick_channel_mode.MODE_OBSERVE,
        ):
            return tr_id                     # 롤백·다크런치는 오늘과 byte 동일
        routed = subscribed_tick_tr_id(tr_key)     # 풀 `_ticker_to_tr_id` 우선
        if routed == tr_id:
            return tr_id
        _emit_legacy_reroute(tr_key, tr_id, routed)
        return routed
    except Exception:                        # pragma: no cover — never-raise
        return tr_id                         # 재라우팅 실패가 구독을 막지 않는다
```

* `subscribed_tick_tr_id` 가 풀의 `_ticker_to_tr_id` 를 1순위로 읽으므로, **이미 풀에 구독된 종목이면 같은 채널이 나온다** ⇒ 이중 채널을 만들지 않는다.
* lazy import 는 선례가 있다 — `websocket.py:585`/`:598`/`:646` 이 이미 `from src.engine.scanner import TICK_TR_IDS` 를 함수 안에서 한다.
* 관측 `[tick_channel_legacy_reroute] ticker= from=H0UNCNT0 to= caller=` 1회/(ticker)/일. 이 마커가 **`scheduler.py` 두 줄의 실제 발화 빈도**를 처음으로 잰다.
* ⚠️ 이것은 **증상 차단**이다. 근본 시정(그 두 줄을 리졸버 경유로) = `scheduler.py` 2줄 치환(라인 순증 0)이고 **별도 승인** 대상이다 — §15 결정 카드 D-4.

### 7-C 통합 구독 0 의 검증

배포 D+1 판독 = `[tick_channel_config] resolved_unified=` 가 **0**, `[tick_channel_legacy_reroute]` 건수 = 그날 익일청산·스윙 매수 건수와 일치, `[tick_channel_dual_detected]` **0건**.

---

## §8 20:00 이후 ~ 다음날 08:00 / 부팅 첫 구독 (질문 7)

### 8-A 수명

| 시각 | 사건 | 채널 상태 |
|---|---|---|
| 20:00 `TIME_NXT_POST_CLOSE` | `_scan_task.cancel()` → `scanner.unsubscribe_all()`(`scheduler.py:884-888`) | 구독 0. `scanner.unsubscribe_all` 의 필터가 `tr_id in TICK_TR_IDS`(`scanner.py:1660`)라 **세 채널 전부** 정리된다 ✅ |
| | `websocket_pool.unsubscribe_all()` 가 `_ticker_to_session` · `_ticker_to_tr_id` **둘 다 clear**(`:577`) | cycle293 이 이미 동행 clear ✅ |
| 20:00~익일 07:45 | `run_daily` 대기 | 구독 0. `_channel_applied`/`_channel_cohort`/`_channel_flipped_today` 는 메모리에 남고 `_sync_channel_day` 가 KST 날짜 경계에서 비운다 |
| 07:45 `TIME_AUTO_START` | `_boot` + `_stale_watcher_loop` 생성 | 구독 0. 전환 루틴은 창 밖이라 0건 |
| **07:59 `TIME_PRESUBSCRIBE`** | `subscribe_filtered_stocks([], extra_tickers=presub, …)` | 🔴 **첫 구독** |
| 08:00 `TIME_PRE_NXT_OPEN` | NXT 프리 진입 | 프레임 시작 |

### 8-B 🔴 부팅 첫 구독은 어느 채널인가

`07:59 < switch_at(08:55)` ⇒ 시각축 = **프리 창** ⇒ §1-E 합성:

| 코호트 | 07:59 채널 | 근거 |
|---|---|---|
| `nxt_true`(출처 권위) | **`H0NXCNT0`** | 08:00 NXT 프리장 체결의 유일 출처 |
| `nxt_false`(출처 권위) | **`H0STCNT0`** | §2-C — 전환 0회 |
| 출처 미확인 · 미분류 | **`H0NXCNT0`** | §3-B L2 fail-open. W2 도장 창(07:45~08:08)에 걸린 ≈420종목이 **정답인 NXT 로 간다**(§3-D) |

⇒ 부팅 첫 구독은 **두 채널로 갈려 나간다.** 41 슬롯 총량은 불변(튜플 수 동일). `[priority_drop]`·`[ws_subscribe_reject]` 판독도 불변.

⚠️ **`TIME_PRESUBSCRIBE`(07:59)가 프리장(08:00) 전인 것은 유리하다** — 구독이 시장보다 먼저 서 있어야 08:00 첫 틱을 놓치지 않는다. 3단계는 그 성질을 **바꾸지 않는다**(구독 시각 무변경, 채널만 갈라짐).

⚠️ **VTS(모의)** — `H0NXCNT0` 은 모의 미지원(`H0UNCNT0` 도 미지원, `H0STCNT0` 만 지원 · cycle293 P-7). 모의 환경에서 프리 창 NXT 구독은 실패한다. **현행보다 나쁘지 않다**(오늘도 통합이 미지원이라 모의에서는 시세가 없다) — 오히려 `nxt_false` 코호트와 09:00 이후 전 종목이 모의에서 **처음으로 산다**. 명시만 하고 별도 조치하지 않는다.

---

## §9 롤백 시나리오 (질문 8)

### 9-A 킬스위치는 기존 것에 태운다 (절대 규칙 8)

`system_config.tick_channel_resolver_mode` ∈ `off` / `observe` / `enforce_low` / `enforce`. 즉시 반영 = `PUT /api/realtime/tick-channel-mode`(cycle293 `routes/realtime.py:914`) + 재조회 배선 2곳(`scanner.subscribe_filtered_stocks` 5분 · `stale_watcher_core` **120초**). **재시작 불요** 유지.

| 모드 | 3단계에서의 의미 |
|---|---|
| `off` | 리졸버가 전 종목 `TICK_TR_ID` 반환 · 전환 루틴 0건 · `_reroute_legacy_unified` 통과 · `stale_watcher_core` 의 cycle252 churn skip 복원(cycle293 이 이미 `_resolver_off` 로 구현). **= 배포 전과 동일** |
| `observe` | 시각축·속성축 판정을 로그로만. 반환은 통합. 전환 0건. 재라우팅 0건. **행위 0**(다크런치) |
| `enforce_low` | LOW 만 시각축 적용 · **HIGH(보유·익일청산)는 통합 유지** · 전환은 LOW 만 |
| `enforce` | 전면 |

### 9-B 🔴 `off` 를 눌렀을 때 이미 전용 채널에 올라간 구독은?

**되돌리지 않는다.** 그대로 남는다. 이것은 cycle293 §8-B 의 ⚠️ 절과 같고, 3단계에서 **규모가 146종목 전체**로 커진다.

왜 되돌림 전환을 붙이지 않는가:

1. `off` 를 누르는 상황은 "뭔가 크게 잘못됐다" 다. 그 순간 **장중에 146종목 대량 전환**을 실행하는 것이 더 위험하다(§4-A 의 세 근거가 전부 깨진 시각에 전환하는 셈).
2. 되돌림 대상이 통합 채널인데, **`nxt_false` 종목에게 통합은 프레임 0** 이다 — `off` 의 되돌림이 그들을 blind 로 만든다. `off` 가 손절 커버리지를 악화시키면 그건 킬스위치가 아니다.
3. 남아 있는 전용 채널 구독은 **정상 동작한다**(§0 실측). `off` 가 막는 것은 **새 판정·새 전환·레거시 재라우팅**이고, 그것으로 충분히 "더 나빠지지 않는다" 가 성립한다.

⇒ **완전 복귀는 다음 `_boot`(익일 07:45)** 다. 장중 즉시 완전 복귀는 재시작이 필요하고 D6 가 막는다. **이 사실을 운영 문서(`src/realtime/CLAUDE.md`)에 적는다.**

### 9-C cycle293 이 찾은 함정("`off` 가 매수를 연다")은 3단계에서 어떻게 달라지는가

| | cycle293(2단계) | **cycle294(3단계)** |
|---|---|---|
| 함정의 형태 | 게이트가 리졸버를 매 틱 재호출 → `off` 가 통합을 반환 → 게이트 False → 구독은 전용 채널에 남아 프레임이 오는데 **매수가 열린다** | **구조적으로 소멸**한다 |
| 왜 소멸하는가 | — | 술어가 **채널 → 코호트**로 바뀌었다(§6-C). 코호트 스탬프는 **모드를 보지 않는다** — `off` 를 눌러도 스탬프는 그대로 True 이고 게이트는 닫힌 채 유지된다 |
| 남는 위험 | — | ⚠️ 반대 방향 하나: `off` 이후 **신규** 구독은 통합으로 나가고 그 종목은 `_stamp_cohort` 를 여전히 거친다(리졸버 진입점이 같다) ⇒ 통합 채널에 있는 `nxt_false` 종목이 매수 skip 된다. **행위상 무해**하다 — 통합에서 그 종목은 프레임이 0 이라 `on_tick` 자체가 안 불린다 |

### 9-D 3단계 전용 다이얼 — **전환만 끈다**

모드 enum 을 늘리지 않는다(절대 규칙 8). 대신 `system_config` 축에 **불리언 키 1개**를 더 둔다.

| 키 | 기본 | 뜻 |
|---|---|---|
| `tick_channel_switch_enabled` | `true` | `false` 면 **살아 있는 구독의 전환만** 멈춘다. 신규 구독의 시각축 판정은 유지 |

* 필요한 이유 = 「채널이 문제다」와 「전환이 문제다」는 **다른 결정**이고, 하나의 enum 에 태우면 운영자가 후자만 끌 수 없다. 전환만 끄면 종목은 첫 구독 채널에 머물고(`nxt_true` → NXT 종일 = NXT 정규장·애프터 프레임 수신 = **blind 아님**) 위험이 즉시 동결된다.
* 이것이 §5 자동 원복의 **수동 대응물**이다.
* 라우트는 **신설하지 않는다** — `PUT /api/realtime/tick-channel-mode` 바디에 선택 필드로 붙인다(`{"mode": "...", "switch_enabled": false}`). 신규 엔드포인트 0.

### 9-E 파라미터 전량 (5개, 전부 `system_config`)

| 키 | 기본 | 범위 | 읽는 곳 |
|---|---|---|---|
| `tick_channel_resolver_mode` | `observe` | enum 4 | cycle293 그대로 |
| `tick_channel_switch_enabled` | `true` | bool | `tick_channel_switch` |
| `tick_channel_switch_offset_secs` | `300` | `[0, span]` 클램프 | `tick_channel_clock` |
| `tick_channel_switch_ack_timeout_secs` | `5.0` | `[1.0, 30.0]` 클램프 | `tick_channel_switch` |
| `tick_channel_revert_probe_secs` | `SUBSCRIBE_GRACE_SECS`(=180) | `[60, 900]` 클램프 | `tick_channel_switch` |

* 🔴 **전략 `DEFAULT_PARAMS` 에 넣지 않는다** — 리졸버는 인프라 축이고 7전략에 넣으면 7곳이 갈린다(cycle293 §8-B). `param_catalog`·`PARAM_RANGES`·`INT_PARAMS` **편입 금지**.
* 조회 실패·키 부재·범위 밖 = **현재 값 유지**(기본값 되돌림 금지 — cycle293 `tick_channel_mode.refresh_mode` 관례 승계) + `[tick_channel_param_invalid] key= stored=` WARNING 1회/일.
* `max_per_cycle`·`budget_secs`(§4-E)는 **모듈 상수**로 둔다(운영자가 만질 축이 아니다).

---

## §10 접촉 파일 · 라인 · sha 핀

### 10-A 파일

| 파일 | 8영역 | 변경 | 예상 순증 |
|---|---|---|---|
| **`src/engine/tick_channel_clock.py`** | 신규 leaf | §1-D 시각축 판정 + `day_revert` 래치. 순수·never-raise·**시각 리터럴 0** | +130 |
| **`src/engine/tick_channel_switch.py`** | 신규 leaf | §4 전환 실행 + §5 자동 원복. never-raise | +260 |
| `src/engine/scanner.py` | ✅ | `_resolve_channel` 합성(§1-E) · `now=None` 인자 3함수 · `_channel_cohort`/`_stamp_cohort`/`tick_buy_cohort_blocked`(§6-C) · `_sync_channel_day` 에 코호트 clear 1줄 · `emit_tick_channel_config` 라벨 3분할 | +95 |
| `src/engine/risk.py` | ✅ | `_tick_buy_eval_blocked_by_channel` **본문 교체**(§6-C). 호출부 2곳 byte 동일 | ≈ −30(순감) |
| `src/realtime/websocket.py` | ✅ | `_reroute_legacy_unified`(§7-B) + `subscribe` 첫 문장 1줄 | +45 |
| `src/realtime/websocket_pool.py` | ✅ | `session_of(ticker)` 읽기 전용 접근자 + `switch_channel_same_session()`(§4-C S1~S6 의 풀 측 구현) | +80 |
| **`src/engine/order_engine.py`** | ✅ | **diff 0** — 해제가 이미 `subscribed_tick_tr_id`(구독 사실)를 쓴다(`:1952-1954`). 승인은 받았지만 쓰지 않는다 | 0 |
| `src/engine/stale_watcher_core.py` | ✖ | `run_switch_cycle` 호출 1블록(§4-B) | +12 |
| `src/engine/tick_channel_mode.py` | ✖ | 신규 키 4개 읽기·클램프 | +70 |
| `src/db/system_config.py` | ✖ | getter 4개 | +40 |
| `src/routes/realtime.py` | ✖ | `PUT` 바디 선택 필드 `switch_enabled`(§9-D) | +18 |

**`scheduler.py` diff 0**(3,726L) · 전략 7파일 · `strategy_base.py` · `market_state.py` · `handler.py` · `tick_volume.py` · `session.py` · `strategy_registry.py` · `api/order.py` · `auth/**` **전부 diff 0**.

### 10-B sha 핀 갱신

1. `tests/unit/ast/test_cycle293_ast_channel_resolver.py::_BASE_SHA` — `market_state.py`(`7cef2efe…`)·`tick_volume.py`(`457bd43d…`)는 **불변이어야 한다**(붉어지면 핀을 옮기지 말고 변경을 되돌린다). `risk.py` 의 `_PIN_PENDING_APPROVAL` 은 §6-C 로 **새 값**으로 옮긴다 — 그 이동의 승인 근거를 docstring 에 적는다.
2. `_SCHEDULER_LINES = 3726` **불변**.
3. `test_cycle257_ast_dead_code_removed.py::_PRESERVED_TICK_CONSTS` — 세 상수 값 **불변**(`TICK_TR_ID` 는 반환 경로에서만 사라진다, 삭제 금지).
4. `test_cycle287_ast_scope`/`test_cycle290`/`test_cycle291` 의 `market_state.py` 핀 **불변**.
5. 신규 `tests/unit/ast/test_cycle294_ast_time_axis.py` 가 자체 `_BASE_SHA` 를 세운다 — **현재 워크트리 값으로 산출**하고 cycle292/293 변경을 되돌리지 않는다.
6. ⚠️ 핀은 `ast.dump` 가 아니라 **소스 세그먼트 sha**(3.12 vs 3.13, 메모리 교훈).

---

## §11 관측 마커

### 11-A 신규

| 마커 | 레벨 | 필드 | cap |
|---|---|---|---|
| `[tick_channel_clock]` | WARNING | `switch_at= krx_open= krx_end= offset_secs= source=market_table` | 부팅 1행 — **표 파생값 카나리아** |
| `[tick_channel_switch]` | INFO | `ticker= from= to= mode=high\|low elapsed_ms= ack_ms=` | 전환 성공 시(창 안이라 상한이 구조적) |
| `[tick_channel_switch_summary]` | WARNING | `cycle= high_ok= high_fail= low_ok= low_fail= remaining= elapsed_s=` | 전환 사이클마다(창 안 2~3행/일) |
| `[tick_channel_switch_failed]` | WARNING | `ticker= stage=ack_timeout\|unsub\|sub old= new=` | 1회/(ticker)/일 |
| `[tick_channel_switch_orphan]` | WARNING | `ticker= old= session=` | 1회/(ticker)/일 — S5 해제 실패 |
| `[tick_channel_switch_window_missed]` | WARNING | `n= sample= reason=` | 1회/일 |
| `[tick_channel_auto_revert]` | **ERROR** | `n= sample= probe_secs= cross_fresh= reason=` | 1회/일 (§5-B) |
| `[tick_channel_revert_skipped]` | INFO | `reason=market_wide\|sample_too_small n= cross_fresh=` | 1회/일 |
| `[tick_channel_legacy_reroute]` | WARNING | `ticker= from=H0UNCNT0 to= caller=` | 1회/(ticker)/일 (§7-B) |
| `[tick_buy_gate]` | WARNING | `stamped_no_feed= stamped_feed= unstamped=` | 1회/일 (§6-D) |
| `[tick_channel_pre_krx_frame]` | INFO | `ticker= n= first_at=` | 1회/일 (§2-D) |
| `[tick_channel_param_invalid]` | WARNING | `key= stored=` | 1회/(key)/일 |

전부 `KstDailyEmitCap` + `observer_trace.trace_observer_failure` 관례(cycle258 표준 `emit_once(key, logger.<level>, "<marker>…")`)를 따른다. **관측 실패가 판정·전환을 막지 않는다.**

### 11-B 기존 마커의 의미 전환 — 🔴 배포 전후 grep 합산 금지

| 마커 | cycle293 의미 | **cycle294 이후** |
|---|---|---|
| `[tick_channel_config] resolved_krx=/resolved_unified=` | 속성축 판정 수 | 라벨을 **3분할**한다 — `clock_krx=` `clock_nxt=` `cohort_no_feed=`. `resolved_unified` 는 **0 이 정상**이고 0 이 아니면 `off`/`observe` 이거나 결함이다 |
| `[tick_channel_resolve] would=` | 속성축 희망 채널 | 시각축이 섞인다. `reason=` 이 `pre_window\|krx_window\|…` 로 바뀐다 |
| `[tick_coverage] stale` | cycle293 = 줄어드는 것이 성공 | **분모 불변 + `fresh` 증가가 성공 서명**. 채널 이동으로 분모가 줄면 cycle252 은폐 금지 위반 |
| `[no_feed_held]` | "보유 종목이 WS blind" 매일 알림 | **0 이 되어야 정상**. 0 이 아니면 전환 실패 |
| `[stale_watcher_summary] no_feed_skipped=` | 재등록 skip 정상 | **0 에 수렴해야 한다**(전 종목이 전용 채널 = skip 조건 거짓) |
| `[tick_channel_dual_detected]` | `scheduler.py` 우회 2곳을 드러냄 | **0 이 정상**(§7-B 재라우팅이 그 두 줄을 흡수) |

---

## §12 회귀 가드

| # | 잠글 것 | 방식 |
|---|---|---|
| **G-294-1** | 신규 leaf 2파일 + `scanner` 리졸버 구역에 **시각 리터럴 0건** | cycle293 `test_a15` 확장 — `time(H,M)` 호출·`"HH:MM"` 문자열·`datetime.combine` 리터럴 0건. `market_state` 를 읽는 호출이 **있는지**도 함께 단언 |
| **G-294-2** | 정상 경로 반환 도메인 = `{H0STCNT0, H0NXCNT0}` | `clock_channel`/`_resolve_channel` 을 24시간 × 1분 격자로 전수 호출 — `TICK_TR_ID` 반환 **0건**(단 `mode=off` 제외) |
| **G-294-3** | fail-open 3층(§3-B) | 파라미터화 — 표 예외 → KRX / 레지스트리 예외 → 프리 창 NXT / `off` → 통합. **뮤테이션**: L2 를 KRX 로 뒤집으면 RED |
| **G-294-4** | **전환은 창 안에서만** | 창 밖 시각 6종(07:59·08:30·09:01·12:00·16:30·19:59)에서 `run_switch_cycle` → 전환 호출 **0건** |
| **G-294-5** | **HIGH make-before-break 순서** | 호출 순서 기록 대역 — `subscribe(new)` 가 `unsubscribe(old)` **앞**. ACK 미도달 시 `unsubscribe(old)` **0건** ∧ `unsubscribe(new)` 1건. 🔴 순서를 뒤집는 뮤테이션이 RED |
| **G-294-6** | 🔴 **매수 축 코호트**(§6-E 8케이스) | 특히 `test_g294_b3` — 전원 전용 채널에서 `nxt_true` 매수가 살아 있다. cycle293 `test_a18` 은 **본문 교체**(삭제 금지) |
| **G-294-7** | 세션 고정 | 전환 전후 `_ticker_to_session[ticker]` **동일 객체**. 라운드로빈 재추첨 0건 |
| **G-294-8** | 병행 dict 정합 | 전환 후 `_ticker_to_tr_id[t]` == 전 세션 `_subscriptions` 안의 실제 tr_id. 이중 튜플 0(전환 중 `_switch_in_flight` 제외) |
| **G-294-9** | 자동 원복 | 표본<2 → 원복 0 / 교차 fresh≥2 없음 → 원복 0 / 전원 침묵 ∧ 교차 fresh≥2 → 원복 1 + `day_reverted` ∧ 그 뒤 전환 0건 |
| **G-294-10** | `day_reverted` 가 **속성축을 존중** | 원복 후 `nxt_false` 종목의 `_resolve_channel` 이 **KRX** 를 유지한다(NXT 로 떨어지면 새 blind) |
| **G-294-11** | 레거시 재라우팅 스코프 | `H0STCNI0`·`H0STCNI9`·`H0UNMKO0`·전용 2채널 요청이 **byte 동일** 통과. 통합만 재라우팅. `off`/`observe` 는 통과 |
| **G-294-12** | `scheduler.py` diff 0 · 3,726L · `tick_tr_id_for` 0건 | cycle293 `test_a2`/`test_a16` 그대로 |
| **G-294-13** | 금지 파일 byte 동일 | §10-B — `market_state.py`·`tick_volume.py`·`handler.py`·`session.py`·전략 7파일·`strategy_base.py` |
| **G-294-14** | 순수성 | 신규 leaf 2파일 + `scanner` 신규 헬퍼에 `await`/DB/HTTP 0(전환 실행부 `tick_channel_switch.run_switch_cycle` 제외 — 그것은 명시적 async) |
| **G-294-15** | 킬스위치 즉시성 | `refresh_mode` 가 once-latch 없이 반복 호출 가능(cycle293 `test_a14b` 확장) + 신규 4키도 재조회된다 |

**뮤테이션 대상(ESCAPED 0 요구)**: 전환 순서 뒤집기 · L2 폴백 KRX 로 · 창 게이트 제거 · 코호트 술어를 cycle293 것으로 · `min`↔`max`(§1-B 세 질의) · 원복 표본 하한 제거 · ACK 술어에서 `_subscriptions_acked` 제거.

**검증 기준선**(cycle293 착지 후) — `tests/unit/ast` 1,536P/4S/26xf · `tests/unit/engine` 5,858P/1S/129xf/4xp · 나머지 2,762P/7S/174xf/8xp = **10,156 passed / 0 failed**. ⚠️ **세 덩어리로 나눠 실행**한다(전체 한 번은 하네스가 끊는다).

---

## §13 금기

1. **정상 경로에서 `TICK_TR_ID` 반환 금지.** 유일 예외 = `mode == "off"`. 상수 자체는 **삭제하지 않는다**(`_PRESERVED_TICK_CONSTS` 리터럴 핀).
2. **"구독을 안 한다" 방향 금지** — 어떤 판정 실패도 구독 skip 으로 귀결하지 않는다(P0-1 재현).
3. **HIGH make-before-break 생략 금지**(절대 규칙 2 — 생략하면 자문이 기각).
4. **전환 창 밖 전환 금지**(§4-A). 신규 구독은 전환이 아니다.
5. **`_ticker_to_session` 재키잉 금지**(cycle293 C-1) · **전환 시 세션 재추첨 금지**(§4-D).
6. **`market_state.py` 쓰기 금지** — 읽기만(`get_market_table` 공개 API). sha 핀 4곳.
7. **`scheduler.py` 무접촉**(3,726L). `:1382`/`:2728` 근본 시정은 §15 D-4.
8. **전략 7파일·`strategy_base`·`handler.py`·`tick_volume.py` 무접촉.** 킬스위치는 `system_config` 축.
9. **매수 축 게이트에서 모드를 읽지 말 것**(§6-C) — `off` 가 매수를 여는 경로를 되살린다.
10. **stale 을 집계에서 빼서 숫자를 좋게 만들기 금지**(cycle252 은폐 금지 계약).
11. **`_SWING_POLL_STRATEGIES` 에 BFB/VCP 추가 금지**(매수 행위 변경 — cycle293 §11-9).
12. **자동 원복을 그날 재시도하지 말 것**(§5-C) — 왕복 = KIS 「비정상 케이스 2」.
13. **새 숫자를 짓지 말 것** — 180초는 `SUBSCRIBE_GRACE_SECS` 재사용, 경계 3개는 표 파생, 전환 시각은 파라미터.

---

## §14 🔴 못 하는 것 / 배포 게이트 (질문 9)

### 14-A 오늘 밤(≤21:35) 안에 **닫을 수 있는** 게이트 3건

| # | 무엇 | 방법 | 못 닫으면 |
|---|---|---|---|
| **G-A** | 🔴 **`H0NXCNT0` 라이브 프레임 1건 실증** | cycle253 프로브(`POST /api/realtime/channel-probe`, `_PROBE_ALLOWED_TR_IDS` 에 이미 있다). **지금(17:0x) NXT 애프터 N6(15:40~20:00)가 열려 있다** — 유동 `nxt_true` 종목 2~3개(예: `000660`·`005930`)로 구독 → 첫 틱 수신 확인 | **3단계 배포 금지.** 프리장 전체를 검증 0 인 채널에 건다 |
| **G-B** | `H0STCNT0` 애프터 프레임 **원문 47필드 덤프 1건** (U-2 `MARKET_CLS_CODE` 밀림) | 같은 창에서 프레임 원문 1건을 `fields[8]/[13]/[24]/[27]/[34]/[43]` 까지 대조 | `_parse_day_high`(밀리면 **예외도 로그도 없이 0**)·`_parse_acml_vol`(**−1 sentinel 무음**) 무음 열화. 16:39 프로브가 `acml_vol` 을 정상 읽은 것은 **강한 정황**이지만 전 필드 대조는 아니다 |
| **G-C** | 08:50~09:00 프레임 ≈0 재확인 | 오늘(09-14) `system_logs` 의 08:50~09:00 `ticker_last_tick` 갱신 수 집계 | §4-A 근거 1(이중 채널 창에 프레임 0)의 실측 뒷받침이 없다 |

### 14-B 🔴 오늘 밤 안에 **닫을 수 없는 것** — "2단계만 배포" 판단의 근거

| # | 무엇 | 왜 못 하는가 | 노출 |
|---|---|---|---|
| **N-1** | **프리장(08:00~08:50) `H0NXCNT0` 커버리지** | 내일 08:00 전에는 프리장이 없다. G-A 는 **애프터 구간의 대리 증거**일 뿐 — 같은 채널이지만 다른 구간이다 | 틀리면 **08:00~08:50 `nxt_true` 보유 종목의 손절 평가 0**. 오늘은 통합 채널이 그것을 주고 있다 ⇒ **INV-1 위반**. 완화 = §5 자동 원복은 09:03 에야 돌아 이 구간을 **못 잡는다**. 유일한 실시간 완화는 `[no_feed_held]` 류 관측과 사람의 08:00~08:10 판독 |
| **N-2** | 🔴 **`ACML_VOL` 스코프 이동**(U-3 의 **확장**) | 1일 수집이 필요하다 | cycle293 §3-E 는 "`nxt_false` 를 여는 것" 만 봤다. **3단계는 `nxt_true` 의 채널을 통합→KRX 전용으로 바꾼다** ⇒ 통합의 `ACML_VOL` 이 KRX+NXT 합산이라면[추론] BFB/VCP 의 `tick_volume` 거래량 게이트가 **조용히 더 엄격해진다** = **매수 행위 변경(축소 방향)**. 축소 방향이라 되돌릴 수 있지만 **승인 없이 일어난다**. 완화 = 관측만 — `[tick_vol_scope_shift] ticker= ws_acml= daily_acml= ratio=` 1회/(ticker)/일 + `[*_vol_gate_no_data]` 건수 D+1 대조. **행위는 바꾸지 않는다** |
| **N-3** | `scheduler.py:1382`/`:2728` 근본 시정 | 무접촉 제약 | §7-B 재라우팅은 **증상 차단**이다. 그 두 줄은 여전히 통합을 요청하고, `websocket.py` 의 재라우팅이 예외로 죽으면(never-raise 라 조용히) 통합 구독이 부활한다. `[tick_channel_legacy_reroute]` 가 유일한 신호 |
| **N-4** | `handler._handle_tick` 에 tr_id 전달 | `handler.py` 는 **미승인 8영역** | `tick_volume` last-write-wins 비결정론(cycle293 §5-A 2)의 **근본 시정 불가**. 이중 채널 금지 + 전환 창 프레임 0 으로만 닫는다 |
| **N-5** | VTS(모의) 프리 창 검증 | `H0NXCNT0` 모의 미지원 | 모의에서 프리 창 구독 실패. 현행보다 나쁘지 않다(§8-B) |

### 14-C 🔴 권고

* **G-A 를 오늘 밤 닫을 수 있으면 3단계를 배포한다** — N-1 은 남지만, 같은 채널이 애프터 구간에서 살아 있다는 실증 + §5 자동 원복 + §9-D 전환 스위치 + `off` 4중으로 감싼다.
* **G-A 를 못 닫으면 2단계만 배포한다.** 2단계는 통합 채널을 유지하므로 프리장 커버리지가 오늘과 동일하고(INV-1 자동 충족), 3단계는 내일 08:00~08:50 실측 뒤 착수한다. 잃는 것 = 하루.
* **N-2 는 어느 경우에도 결정 카드로 올린다**(§15 D-2) — 3단계를 배포하면 그날 밤 BFB/VCP 의 매수 문턱이 미측정 폭으로 조여진다.

---

## §15 결정 카드 (사용자)

| # | 결정 | 선택지 | 권고 |
|---|---|---|---|
| **D-1** | 배포 범위 | (가) 3단계 배포(G-A 를 오늘 밤 닫는 조건) / (나) **2단계만** 배포하고 3단계는 내일 프리장 실측 뒤 | **(가) 조건부.** G-A 프로브가 애프터 창(≤20:00)에 성공하면 (가), 실패하면 (나). §14-C |
| **D-2** | 🔴 N-2 (`ACML_VOL` 스코프 이동으로 BFB/VCP 매수 문턱이 조여지는 것) | (가) 관측만 넣고 배포 / (나) 1일 대조 뒤 3단계 / (다) BFB/VCP 를 그날만 `enabled=False` | **(가).** 축소 방향이고 되돌릴 수 있다. (다)는 전략 설정 변경이라 심층 검증 의무가 붙는다 |
| **D-3** | 전환 시각 offset 기본값 | (가) **300초(08:55)** / (나) 180초(08:53) / (다) 420초(08:57) | **(가).** 창 5분 = 120초 루프 2~3사이클. (나)는 프리장 마지막 2분을 잃고, (다)는 개장 전 여유가 1사이클뿐 |
| **D-4** | `scheduler.py:1382`/`:2728` 2줄 치환(라인 순증 0) | (가) 이 사이클에 **포함**(별도 승인) / (나) §7-B 재라우팅으로 흡수하고 후속 | **(가) 권고.** 2줄·순증 0·`tick_tr_id_for` 치환이고, 포함하면 N-3 과 §7-B 45줄이 동시에 사라진다. 다만 `test_a16`(scheduler 무접촉) 가드를 함께 고쳐야 한다 |
| **D-5** | `tick_channel_switch_enabled` 별도 키(§9-D) | (가) 둔다 / (나) 모드 enum 만으로 | **(가).** 「채널이 문제」와 「전환이 문제」는 다른 결정이고, 후자만 끄는 수단이 없으면 사고 중에 쓸 카드가 `off` 하나뿐이다 |

---

## 부록 A — 구간 × 코호트 채널 판정표 (09-15 기준)

| 시각(KST) | 시각축 | `nxt_true`(권위) | `nxt_false`(권위) | 미분류·출처미확인 | 프레임 기대 |
|---|---|---|---|---|---|
| 07:59~08:00 | 프리 창 | `H0NXCNT0` | `H0STCNT0` | `H0NXCNT0` | 0 (시장 없음) |
| **08:00~08:20** | 프리 창 | `H0NXCNT0` | `H0STCNT0` | `H0NXCNT0` | NXT 만 ✅ / KRX 0 |
| 08:20~08:50 | 프리 창 | `H0NXCNT0` | `H0STCNT0` | `H0NXCNT0` | NXT ✅ / KRX 단일가 0[추론 §2-D] |
| **08:50~08:55** | 프리 창 | `H0NXCNT0` | `H0STCNT0` | `H0NXCNT0` | **≈0**(N2 휴장 + K1 단일가) |
| **08:55~09:00** | **전환 창** | NXT → **KRX** | KRX 유지 | NXT → **KRX** | **≈0** ⇒ 이중 채널 노출 0 |
| **09:00~15:20** | KRX 창 | `H0STCNT0` | `H0STCNT0` | `H0STCNT0` | KRX 정규장 ✅ |
| 15:20~15:30 | KRX 창 | `H0STCNT0` | `H0STCNT0` | `H0STCNT0` | ≈0 (K4 종가 단일가) |
| 15:30~15:40 | KRX 창 | `H0STCNT0` | `H0STCNT0` | `H0STCNT0` | K5 시간외 종가 / N5 단일가 — 미지 |
| 15:40~16:00 | KRX 창 | `H0STCNT0` | `H0STCNT0` | `H0STCNT0` | NXT N6 애프터만 열림 ⇒ **KRX 프레임 ≈0**[추론]. NXT 로 전환하지 **않는다**(§0) |
| **16:00~20:00** | KRX 창 | `H0STCNT0` | `H0STCNT0` | `H0STCNT0` | **KRX 애프터 ✅ 실측 확정**(§0 · 000815·005385·000660) |
| 20:00~ | — | `unsubscribe_all()` | 동일 | 동일 | 구독 0 |

⚠️ **15:40~16:00 구간**(20분)은 KRX 에 연속 체결이 없고 NXT 애프터만 열려 있다. 우리는 KRX 채널을 유지한다 — 그 20분에 NXT 로 갔다 16:00 에 돌아오는 전환 2회의 비용이 20분 프레임보다 크다. **다만 그 20분은 `nxt_true` 보유 종목의 손절 커버리지가 오늘(통합 채널)보다 나빠진다**[추론 — 통합이 그 구간 NXT 체결을 실었다면]. 크기 = 하루 20분, `_force_clear_main_only`(15:20)가 이미 MAIN 보드 종목을 정리한 뒤다. **D+1 판독 항목으로 올린다.**

---

## 부록 B — 전환 사이클 의사코드 (`tick_channel_switch.run_switch_cycle`)

```python
async def run_switch_cycle(scheduler, pool, *, now) -> dict:
    """120초 stale watcher 안에서 불린다. never-raise. 반환은 관측용 dict."""
    try:
        if mode not in (MODE_ENFORCE, MODE_ENFORCE_LOW):        return {"skip": "mode"}
        if not switch_enabled:                                  return {"skip": "disabled"}
        if _reverted_today(now):                                return {"skip": "reverted"}

        # ── §5 자동 원복 판정이 전환보다 **먼저** ─────────────────────────
        if _revert_probe_due(now):                              # krx_open + 180s
            verdict = _revert_verdict(pool, now)                # 표본≥2 ∧ 전원 침묵
            if verdict.should_revert:                           #        ∧ 교차 fresh≥2
                await _revert_all(pool, now)                    # break-before-make
                return {"reverted": verdict.n}

        krx_open, nxt_end, _ = windows(now.date())
        sw = switch_at(now.date(), offset_secs=offset)
        if not (sw <= now.time() < krx_open):                   # §4-A 창 게이트
            _maybe_emit_window_missed(pool, now)
            return {"skip": "window"}

        high, low = _targets(scheduler, pool, now)               # 목표≠현행만
        t0, done = monotonic(), 0
        for t in high:                                           # HIGH 먼저
            if done >= MAX_PER_CYCLE or monotonic()-t0 > BUDGET: break
            await _switch_high(pool, t, ...)                     # make-before-break
            done += 1; await asyncio.sleep(0.05)
        for t in low:
            if done >= MAX_PER_CYCLE or monotonic()-t0 > BUDGET: break
            await _switch_low(pool, t, ...)                      # break-before-make
            done += 1; await asyncio.sleep(0.05)
        _emit_switch_summary(...)
        return {...}
    except Exception:
        logger.debug("[tick_channel_switch] 사이클 실패 — 다음 120초 재시도", exc_info=True)
        return {"skip": "error"}
```

---

## 부록 C — 구현 순서 권고 (5시간 안에 쓴다면)

| 순 | 작업 | 이유 |
|---|---|---|
| 1 | **G-A 프로브 발사**(§14-A) — 지금 즉시, 애프터 창이 20:00 에 닫힌다 | 배포 가부를 정하는 단 하나의 게이트. 코드 작업과 **병렬** |
| 2 | `tick_channel_clock.py` + G-294-1/2/3 | 나머지 전부의 입력. 순수 함수라 테스트가 빠르다 |
| 3 | `scanner._resolve_channel` 합성 + `now` 인자 3함수 | 신규 구독이 먼저 옳아야 전환이 의미를 갖는다 |
| 4 | 🔴 **§6 매수 축 코호트** + G-294-6(8케이스) | **절대 규칙 5.** 이것을 3번 뒤로 미루면 중간 상태에서 테스트가 전 전략 매수 0 을 통과시킨다 |
| 5 | `websocket_pool.switch_channel_same_session` + `tick_channel_switch.py` + G-294-4/5/7/8 | 전환 본체 |
| 6 | §5 자동 원복 + G-294-9/10 | 전환의 안전망 |
| 7 | §7-B 레거시 재라우팅 + G-294-11 (D-4 가 (가)면 대신 `scheduler.py` 2줄) | 통합 구독 0 의 마지막 조각 |
| 8 | 파라미터 4키 + 라우트 필드 + G-294-15 | 킬스위치 |
| 9 | sha 핀 갱신 + 3덩어리 전체 검증 | |

**2~4 까지만 끝나면 그것만으로 배포 가치가 있다** — 신규 구독이 시각축을 따르고(전환 없음 = 위험 0), 매수 축이 안전하고, 부팅 첫 구독부터 통합이 사라진다. 전환(5~6)은 "이미 구독된 종목을 옮기는" 축이고 미전환 잔여는 blind 가 아니다(§4-A 근거 3). 🔴 **시간이 모자라면 5~6 을 빼고 배포하는 것이 "2단계만 배포" 보다 낫다** — 그 경우 `tick_channel_switch_enabled=false` 로 켜서 배포하고 전환은 다음 사이클로 미룬다.
