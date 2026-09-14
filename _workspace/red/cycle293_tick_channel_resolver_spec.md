# cycle293 — 시세 채널 분리 **2단계(속성축 배관)** 명세

> ## 🔴 2026-09-14 전제 정정 — 이 문서를 읽기 전에
>
> **종착지는 이미 정해져 있다: 통합 채널 `H0UNCNT0` 폐기, KRX 전용(`H0STCNT0`) + NXT 전용
> (`H0NXCNT0`) 2채널만 쓴다.** 근거 = 2026-09-07 사용자 결정
> (`_workspace/consult/2026-09-07_channel_split_by_session.md` 「프리장=NXT / KRX장=KRX,
> 통합 채널 폐기」) + 2026-09-14 사용자 재확인("H0UNCNT0는 아예 쓸 생각이 없어").
> **이 방향은 재론 대상이 아니다.**
>
> 이 문서의 초안은 낡은 워크리스트 항목(속성축 리졸버 + `H0UNCNT0` 존치)을 전제로 작성돼
> **측정 결과에 따라 작업이 불필요해질 수 있다는 분기**를 담고 있었다. 그 분기는 폐기한다.
> 실측이 정하는 것은 **세부방향**뿐이다 — 어느 구간을 어느 전용 채널에 배치하는가,
> 전환 시각, 전환 중 커버리지.
>
> **이 문서가 명세하는 것은 자문 §5 의 2단계다** — `tick_tr_id_for(ticker, now)` 를 도입하되
> `now` 는 시그니처에만 두고 **전환을 넣지 않는다**. 목적은 종착지 도달이 아니라
> **9파일 25+ 사이트의 split-brain 부채를 전환 위험 0 으로 먼저 갚는 것**이다.
> 3단계(시간축 전환)가 그 위에 구간 배치를 채우면 `H0UNCNT0` 은 코드에서 사라진다.
>
> 그래서 아래 §3-D 의 "fail-open = `H0UNCNT0` 현행 유지" 는 **2단계 한정 과도기 장치**다.
> 영구 기본값이 아니며, 3단계에서 그 폴백 대상이 KRX/NXT 전용 채널 중 하나로 바뀐다.


| | |
|---|---|
| 상태 | **명세만.** 프로덕션 코드·테스트 변경 0 |
| 작성 | 2026-09-14 (KRX 애프터마켓 시행 첫날) — 병렬 조사 4갈래 종합 |
| 선행 완료 | cycle252(A · no_feed churn 중단, 배포) · cycle253(프로브 라우트, 배포) · cycle257(시각 분기 dead code 삭제) · cycle272(REST 시가 단일 출처) · cycle286 C4-a(거부 사후 보강 창 축소) · cycle287(애프터 청산 **수단** 개통) · 09-07~09 프로브 실측 |
| 착수 | cycle292(장운영 구독 leaf 분리) 착지 후 |
| 배포 게이트 | **오늘 저녁 16:00~20:00 측정 #1 판독 뒤.** 측정은 애프터 구간을 어느 전용 채널에 배치할지(**세부방향**)를 정한다 — 통합 채널 존치 여부를 되묻는 것이 아니다 |
| 승인 | 8영역 **5파일** 접촉 = 사용자 승인 완료(2026-09-14) — `scanner.py`·`websocket.py`·`websocket_pool.py`·`order_engine.py` (1차) + **`risk.py`**(2차, 14:2x). `risk.py` 는 §3-E **매수 축 skip 게이트**의 유일한 위치다 — `risk.on_tick` 의 전략 루프 안이어야 WS 틱 경로만 막고 `_swing_buy_poll_loop`(=`check_buy_signal` 직접 호출, `scheduler.py:2701`)의 donchian·kojiro 정상 매수(30일 11건)를 살린다. `strategy_base.py` 에 두면 그 REST 폴 매수까지 죽고, `handler.py` 도 미승인 8영역이다. 변경은 순증 52줄·기존 줄 수정 0·fail-open(예외→매수 유지)이고 **되돌리기는 호출 1줄 삭제**다. ⚠️ **§3-E 의 매수 행위 변경(B-2)은 그 승인에 포함되지 않는다** — 별도 승인 + `domain-consult` 선행 |
| 정본 상위 | `_workspace/00_URGENT_WORKLIST.md` 「🔴 P1-7」 · 「🔴 09-14 발견 ②」 · 「09-14 이후 첫 영업일에 재야 할 것」 |
| 줄번호 기준 | 워크트리(cycle292 진행 중). `scheduler.py` 는 cycle292 diff 가 `:3172` 이후만 건드리므로 이 문서가 인용하는 `scheduler.py` 줄번호(전부 ≤2922)는 HEAD(`adabbdf`)와 동일하다. 나머지 파일은 HEAD 무변경 |

---

## §0 네 조사의 합류점과 갈린 곳

이 문서는 병렬 조사 4갈래(채널배관 · 풀분배/한도 · 죽은코드/플리커 · 애프터마켓상호작용)를 하나로 합친 것이다. **어긋난 지점은 아래에서 택한 쪽과 근거를 먼저 밝힌다.**

| # | 쟁점 | 조사들의 입장 | **채택** + 근거 |
|---|---|---|---|
| C-1 | `_ticker_to_session` 을 `(tr_id, tr_key)` 로 재키잉할 것인가 | 풀분배 = 재키잉 말고 **병행 dict** `_ticker_to_tr_id` 추가 / 죽은코드 = 재키잉 or 원자 전환 leaf 중 **택일해 명시하라** / 애프터마켓 = 재키잉 금지, 단일 채널 교체 | **재키잉 안 한다 + 병행 dict `_ticker_to_tr_id` 를 둔다.** 단일 키가 곧 "이중 채널 금지" 의 구조적 강제 장치이고(§5), 재키잉하면 `unsubscribe`·`unsubscribe_all`·`unsubscribe_in_pool`·`get_subscriptions_by_session`·`disable_quote_session`·`remove_session` + routes 고아 판정 3헬퍼 + cycle221 VI 주석 규약이 **동시에** 무너진다. 병행 dict 는 "이 종목은 어느 채널인가" 만 풀에 알려 §5 함정 A·B 를 최소 diff 로 닫는다 |
| C-2 | 플리커 debounce 를 **시간 창**으로 할 것인가 | 애프터마켓 = 동일 종목 재전환 최소 간격 1일 권고 / 죽은코드 = **숫자를 지어내지 말고 출처(provenance) 검사로 바꿔라**, 진짜 전환은 장 종료 후 착지하므로 hold-down 이 필요 없다 / 풀분배 = **첫 구독 시점 1회 판정**이면 플리커가 구조적으로 0 | **출처 검사(§6-C 1안) + 첫 구독 시점 1회 판정을 주 수단으로, "같은 날 재전환 금지"를 값싼 백스톱으로.** 시간 창 리터럴은 두지 않는다 — 오염 창의 양끝(07:45~08:08)이 일정 파생값이고 그 일정은 이미 두 번 움직였다(일봉 16:00→18:10→20:30, basics 16:10 vs 부팅 07:53) |
| C-3 | 워크리스트가 지시한 "사이클 26 죽은 코드 처분" | 죽은코드 = **이미 cycle257 이 삭제했다.** 라인 예산 기여 0 / 나머지 조사 = 언급 없음 | **워크리스트 B 항목의 그 문장은 완료된 과거다.** 구현자가 없는 코드를 찾지 않게 §11-7 에 폐기 표시. cycle257 인계 잔여는 주석 1줄(`handler.py:81`)뿐 |
| C-4 | 파싱 변경이 딸려 오는가 | 채널배관 = **딸려 오지 않는다.** 세 채널 Response Body **47필드 인덱스 전부 동일**(정본 `:1310`/`:2456`/`:2670` 대조), 우리가 읽는 0·1·2·7·8·13·24·27·34·43 전부 일치. 유일 차이는 index 21 필드명(`CCLD_DVSN`↔`CNTG_CLS_CODE`)이고 우리는 안 읽는다 / 애프터마켓 = `MARKET_CLS_CODE` 신규 index 미지 → 밀림 위험 | **리졸버에는 파싱 변경이 없다**(C-4 전반). `MARKET_CLS_CODE` 밀림은 **리졸버와 독립된 위험**이고 채널을 안 바꿔도 오늘 저녁에 일어날 수 있다 — §12-2 로 분리 |
| C-5 | 7전략 `params.exchange` 현황 | 죽은코드 = 운영 DB 실측 **전부 `"NXT"`**, `[nxt_downgrade]` 도 09-14 부터 `from=NXT` / 루트 `CLAUDE.md` cycle286 절 = "전부 SOR" | **실측(NXT)을 채택.** 루트 `CLAUDE.md` 의 "7전략 exchange 전부 SOR" 서술은 낡았다 — §12-7 후속 문서 시정 항목. 리졸버 설계에는 영향 없지만 cycle286 C4-a 의 거래소 레그가 **이제 충족된다**(§6-B W3) |

---

## §1 왜 — 사실과 비용

### 1-A 결함

통합 채널 `H0UNCNT0` 은 `stock_master.nxt_tradable=False`(KRX 단독 = NXT 비대상) 종목의 체결 프레임을 **보내지 않는다.** SUBSCRIBE 는 SUCCESS ACK 를 받으므로 구독은 살아 있는 것처럼 보이고, 프레임만 영구 0 이다.

- 포렌식 `_workspace/forensics/stale_candidates_0904.md` — 나흘 × ~200종목 **예외 0**, 유동주 포함, 최소 2026-07-24 부터 만성
- 064550 자연 실험(양방향) — 09-01 `nxt_true` 일 때 `H0UNCNT0` 프레임 **32,806건**(12:08~19:59) → **09-02 16:06 `nxt_false` 전환 → 프레임 0**(SEND 219건). 그리고 **09-14 07:59:09 다시 `True`(NXT 재편입)**. 우리 코드는 양쪽 전환에 대해 **로그 0줄**을 남겼다
- 마스터 전체 분포(실 DB) — `nxt_tradable` **False 2,981 / True 602 / NULL 0** ⇒ **83.2% 가 KRX 단독**

### 1-B 오늘(09-14) 실측

| 측정 | 값 | 출처 |
|---|---|---|
| `[tick_coverage]` 09:56 | `subscribed=146 fresh=82 stale=64 **ratio=56.2%**` (stale ≈44%, 워크리스트 헤드라인 33%보다 악화) | system_logs |
| `stale_sample` 15종목 | **15/15 전부 `nxt_tradable=False`** (001440·003470·003490·004090·004310·004710·005935·009830·010170·012210·014950·014990·017900·024060·032820) | system_logs ⋈ stock_master |
| `[stale_watcher_summary]` 09:55 | `checks=2 stale_total=125 **no_feed_skipped=124**` ⇒ 체크당 no_feed ≈**62종목** = 구독 146 중 **42%** | system_logs |
| 보유 12종목 중 `nxt_false` | **4** — 003470 유안타증권·003490 대한항공(kojiro) / 036540 SFA반도체·204270 제이앤티씨(donchian_swing) | positions ⋈ stock_master |
| `[no_feed_held]` 07:59:49 | `tickers=['003470','003490','032820','036540']` (1회/일 cap = 07:59 스냅샷. 032820 은 이후 매도, 204270 은 이후 매수) | system_logs |

### 1-C 비용 — 두 갈래

1. **손절 커버리지** — 그 종목들의 청산 평가가 REST 폴(09:00:30~15:20)에만 의존한다. 🔴 그리고 **REST 폴은 전 전략을 덮지 않는다**(부록 A 주3): `held_set` 은 `_SWING_POLL_STRATEGIES = ("donchian_swing", "kojiro")`(`scheduler.py:145`) 두 전략의 positions 합집합으로만 만들어진다(`scheduler.py:2789-2794`). **BFB/VCP 가 `nxt_false` 를 하나라도 잡으면 그 종목은 종일 손절 평가 0** 이다(둘은 멀티데이 보유인데 폴 대상이 아니고 WS 는 무송출). 오늘 4종목이 전부 kojiro·donchian 인 것은 **우연**이다.
2. **구조적 매수 배제** — tick 전략 매수 35일 60건이 **100% `nxt_true`**. 시총 1,000억 이상 유니버스의 64% 가 5전략의 매수 평가에서 구조적으로 빠져 있다(§3-E).

### 1-D 🔴 오늘부터 새로 생긴 비용 — 16:00~20:00

`check_exit_signal` 호출 경로는 **정확히 둘**이고 `RiskManager.on_tick` 호출자도 **정확히 둘**이다(전수 grep 2026-09-14):

| # | 경로 | 코드 | 시각 가드 |
|---|---|---|---|
| A | WS 틱 | `handler.py:631 await _on_tick(...)` ← 등록 `scheduler.py:601 register_tick_handler(self.risk_manager.on_tick)` → `risk.py:604 strategy.check_exit_signal(...)` | **없다.** 프레임이 오면 평가한다(예외 = 프리장 청산 평가 보류, 부록 A 주1) |
| B | REST 폴 | `scheduler.py:2856 if ticker in held_set:` → `:2858 await self.risk_manager.on_tick(...)` → `risk.py:604` | `SWING_REST_POLL_EARLY_START=09:00:30` ~ `SWING_REST_POLL_WINDOW_END=15:20`(`scheduler.py:138,140`, 판정 `:2907`) |

⇒ **16:00~20:00 에 손절을 평가할 수 있는 주체는 WS 틱(A) 단독**이고, 그 창에 프레임이 오지 않는 종목은 손절 평가가 **0** 이다. cycle287 이 확보한 것은 청산 **수단**(KRX 애프터 `44`→`41`)이고 **방아쇠**가 아니다 — `execute_sell` 은 신호가 와야 불린다.

**새로 드러난 부수 공백**: **15:20~15:30 도 공백**이다. REST 폴이 `now_t > time(15,20)` 으로 끝나고 그 구간은 KRX 장마감 동시호가라 WS 프레임도 ≈0. 종전 워크리스트는 16:00~20:00 만 지적했다. 전 구간 경계표 = **부록 A**.

---

## §2 선행 조건 — 증명된 것과 아직 아닌 것

### 2-A 증명된 것

| # | 사실 | 증거 |
|---|---|---|
| P-1 | `H0STCNT0` 으로 구독하면 **진짜 KRX 개장가**가 온다(통합 채널의 NXT 프리장 오염 없이) | cycle253 프로브 09-09 `010170 oprc_hour=090009` · 09-10 `100840 oprc_hour=090023` · 09-08 `002990 received=True` |
| P-2 | `H0STCNT0` 은 **보조 세션에 놓을 수 있다** | 풀의 유일한 tr_id 화이트리스트는 `_EXECUTION_NOTICE_TR_IDS = frozenset({"H0STCNI0","H0STCNI9"})`(`websocket_pool.py:59`) 이고 `H0STCNT0` 은 그 밖. 프로브 3건이 실제로 보조 세션(`71513056`·`gold`·`44606571`)에서 프레임을 받았다 |
| P-3 | **수신 경로는 손댈 필요가 없다** | `handler.py:400 if tr_id in ("H0STCNT0","H0UNCNT0","H0NXCNT0"): await _handle_tick(payload)` — 세 채널이 이미 한 파서로 간다 |
| P-4 | **파싱 비용 0** | 정본 Response Body 47필드 인덱스 전부 동일(C-4). AES 키 격리도 안전 — `websocket.py:752` 가 `is_main ∧ tr_id ∈ 체결통보` 이중 가드라 보조 세션의 `H0STCNT0` SUCCESS 는 전역 AES 키를 덮지 않는다 |
| P-5 | **구독은 16:00~20:00 동안 살아 있다** | ① 15:30 블록이 아무것도 해제하지 않는다("구독은 유지(POST_NXT 종목 시세 필요)", `scheduler.py:862-863`) ② `_scan_loop` 이 죽어 있으면 재생성(`:872-874`) ③ 해제는 **20:00 단 한 지점** `TIME_NXT_POST_CLOSE` → `_scan_task.cancel()` → `unsubscribe_all()`(`:884-888`) ④ 실측 — 09-01 donchian `192820` **18:09:50 매도**. 그 시각 청산을 발화시킬 수 있는 경로는 WS 틱뿐(REST 는 15:20 종료, `_force_clear_main_only` 는 VB/LTV, 익일청산은 09:00) |
| P-6 | **41 슬롯은 여유가 크다** | 09-14 09:56 실측 — main **14/41**(TICK 12 + `H0STCNI0` + `H0UNMKO0`/005930), 보조 7 합 **146/287**, 풀 합 **160/328**, 잔여 **168**. 62종목을 "등록 먼저 → 해제 나중" 으로 한 사이클에 전부 옮겨도 222/328, 세션 최악 ISA 21→30/41. 오늘 `[priority_drop]`·`[ws_subscribe_reject]`·OPSP0008 **전부 0건** |
| P-7 | **VTS 에서 오히려 살아난다** | `H0UNCNT0`/`H0NXCNT0` 는 모의 미지원, `H0STCNT0` 은 모의 TR_ID 도 `H0STCNT0`(정본 `docs/kis/domestic-stock-realtime.md:1247`) |

⇒ **공백은 구독이 끊겨서가 아니라 프레임이 오지 않아서**다(P-5). 배관을 새로 깔 필요는 없고 **채널만 고르면 된다** — 그것이 리졸버다. 그리고 제약은 41-cap 이 아니라(P-6) 전부 **정합성**이다(§5).

### 2-B 아직 아닌 것 (배포 게이트)

| # | 미지 | 막히는 것 |
|---|---|---|
| U-1 | 🔴 **16:00~20:00 에 `nxt_false` 종목 프레임이 어느 채널로 오는가** | §7 분기 선택 = **배포 게이트** |
| U-2 | `MARKET_CLS_CODE`(신규, 1프리/2정규/3애프터/5종가) 의 payload index | `fields[8]/[13]/[27]` 밀림. **리졸버와 독립** |
| U-3 | `H0STCNT0` 의 `ACML_VOL` 스코프가 `H0UNCNT0` 과 같은가 | §3-E B-2(매수 축) 착수 게이트 |
| U-4 | KIS 재등록(UNSUB→SUB) 지연 상한 | 현재 유일 표본 = 프로브 `100840` **≤4초**(09-10 09:01:04 start → 09:01:08 first_tick). §3-C 설계를 택하면 무력화된다 |
| U-5 | REST(FHKST01010100)가 애프터 시세를 주는가 | §7-D REST 폴 확장의 **성립 조건** |
| U-6 | 시간외 전용 3채널(`H0STOUP0`·`H0STOAA0`·`H0STOAC0`) 거동 | `docs/kis/` 경고문 확정. **리졸버 무영향**(§11-8) |

---

## §3 설계 — `tick_tr_id_for(ticker)`

### 3-A 위치와 시그니처

```python
# src/engine/scanner.py — TICK_TR_ID / _KRX / _NXT 상수 바로 아래
def tick_tr_id_for(ticker: str) -> str:
    """이 종목의 체결 시세를 받을 TICK 채널 TR_ID 를 고른다.

    순수 함수 — await/DB/HTTP 없음. 입력은 이미 적재된 no_feed 레지스트리 스냅샷뿐.
    판정 불가(미지 ticker·레지스트리 미적재·예외)는 전부 현행 유지 = TICK_TR_ID.
    """
```

**왜 `scanner.py` 인가** — 세 상수(`TICK_TR_ID` / `TICK_TR_ID_KRX` / `TICK_TR_ID_NXT`)가 이미 거기 있고, cycle257 이 시각 분기를 삭제할 때 KRX/NXT 2줄을 **"P1-7 B 리졸버 `tick_tr_id_for(ticker)` 의 반환값 자리"로 명시 보존**했다(`scanner.py:498-504` 주석). `tests/unit/ast/test_cycle257_ast_dead_code_removed.py:63-67` 의 `_PRESERVED_TICK_CONSTS` 가 그 세 값을 리터럴로 핀하고 있으므로 **값을 바꾸면 그 가드를 함께 갱신**해야 한다(§10-G1).

⚠️ **`scheduler.py` 에 두지 않는다** — cycle292 와 동시 작업 + 라인 상한(§11-2).

### 3-B 결정 규칙

```
no_feed_registry.is_no_feed(ticker) is True  ∧  출처 권위 확인됨(§6-C)
        → TICK_TR_ID_KRX  ("H0STCNT0")
그 밖 (False · 미지 · 미적재 · 예외 · 출처 미확인)
        → TICK_TR_ID      ("H0UNCNT0")   ← fail-open = 현행 유지
```

- **소스는 `no_feed_registry` 단일**(`src/engine/no_feed_registry.py`, cycle252). `stock_master` 를 직접 조회하지 않는다 — 두 번째 소스를 만들면 두 판정이 갈리고, 갈린 순간 "구독은 A 채널 해제는 B 채널" 이 된다. 레지스트리는 이미 `is_no_feed(ticker)`(`:114`)·`snapshot()`(`:119`)·`ensure_fresh(tickers, ttl_secs=600)`(`:54`) 를 갖고 있고, 의존이 stdlib + `src.db.stock_master` lazy 뿐이며 `AST G-252-1` 이 그것을 봉인한다. **`src/engine/CLAUDE.md` 의 `no_feed_registry` 절이 이미 "채널 리졸버(B) 착지 시 같은 집합이 `tick_tr_id_for` 의 소스가 된다" 고 예고해 두었다.**
- 레지스트리 극성이 **이미 옳다** — `None`(마스터 부재)은 no_feed 가 아니다(`no_feed_registry.py:12-14` "모르면 막지 않는다").

### 3-C 🔴 판정 시점 — **첫 구독 시점 1회** (⚠️ **2단계 한정 규약**)

**살아 있는 구독의 채널을 바꾸는 경로를 아예 만들지 않는다.**

> 🔴 **이 규약은 3단계로 승계되지 않는다.** 3단계(시간축)는 정의상 세션 경계
> (권고 08:55 / 15:34)에서 **살아 있는 구독을 바꾼다** — "바꾸는 경로를 만들지 않는다" 와
> 정면으로 배치된다. 2단계가 이 규약을 택하는 이유는 종착지가 그래서가 아니라,
> **전환 위험을 뒤로 미뤄 두고 배관부터 깔기 위해서**다. 3단계 착수 시 이 절은 자문 §7-⑤
> **HIGH make-before-break**(생략하면 자문이 기각으로 바뀐다) + 전환 창 REST 백스톱 +
> 자동 원복 트리거로 **대체된다**. 이 문장을 지우지 말 것 — 다음 사람이 3-C 를 영구
> 규칙으로 읽으면 3단계가 시작조차 못 한다.

- 근거 = 이 규약 하나가 (a) 전환 블라인드 창 (b) 채널 플리커 (c) 이중 채널 (d) U-4 미지를 **구조적으로 0** 으로 만든다.
- `scanner.subscribe_filtered_stocks` 의 `already` / `already_in_pool` 스킵이 이미 그 성질을 갖고 있다 — 리졸버는 "새로 구독하는 종목" 에만 물린다.
- 재채널이 필요한 경우(진짜 `nxt_tradable` 뒤집힘)는 **다음 `_boot`/재구독 사이클**에서 자연히 반영된다. 진짜 전환은 16:0x~16:3x basics_refresh 에 착지하므로(§6-B W1) **장 종료 후**다 — 064550 이 09-02 16:06 에 즉시 전환하지 않아 잃은 것이 없다(다음 08:00 까지 실을 틱이 없다).
- 그래도 장중 전환이 불가피하면 **§5-C 4단 순서 + §6-D 백스톱**을 지킨다. **HIGH(보유·익일청산) 종목은 장중 채널 전환 금지.**

### 3-D fail-open 방향 — 반드시 "현행 유지" (⚠️ **2단계 한정 과도기 장치**)

> 🔴 3단계에서 `H0UNCNT0` 은 코드에서 사라진다. 아래 규약은 전환을 넣지 않는 2단계 동안
> "판정 실패 시 오늘과 똑같이 동작한다" 를 보장하기 위한 것이고, **영구 기본값이 아니다.**
> 3단계 착수 시 이 절의 폴백 대상을 KRX/NXT 전용 채널 중 하나로 바꾸는 것이 계약이다.


판정 실패는 전부 `TICK_TR_ID`(H0UNCNT0) 다. **구독을 안 하는 방향으로 가지 않는다** — 그것은 P0-1(유령 키 `acml_vol` 이 두 전략을 전 기간 체결 0건으로 만든 사고)의 재현 방향이다. cycle252 의 `no_feed_registry` fail-open 관례(집합 ∅·조회 예외·미지 ticker 면 현행 byte 동일)를 그대로 승계한다.

⚠️ **반론이 성립한다** — 이 방향은 "모르면 blind 유지" 라서 보수적이지 않다. 보유 종목에서 판정이 실패하면 그 종목은 계속 blind 다. 그래서 **판정 실패 + 보유 = `[no_feed_held]` WARNING 과 함께 사람에게 올린다**(결정 카드 D-3).

### 3-E 🔴 리졸버의 숨은 얼굴 — 이것은 **매수 행위 변경**이다

원안(2026-09-05)은 리졸버를 "stale 33% 시정 = 관측·손절 복구" 로만 서술한다. **그것은 절반이다.** `nxt_false` 종목은 지금 프레임이 0 이라 `risk.on_tick` 이 아예 불리지 않는다:

| 전략 | 지금 | 리졸버 후 |
|---|---|---|
| `bull_flag_breakout` · `vcp_breakout` | 거래량 게이트가 `tick_volume.get_observed_acml_vol()` → `None` → **`vol_gate_no_data` fail-closed**(`bull_flag_breakout.py:1052-1067`, `vcp_breakout.py:1122-1136`) ⇒ 매수 불가 | 실측 `acml_vol` 이 들어와 게이트가 **열린다** |
| `momentum` | 틱 구동 매수 평가 0 | 열린다 |
| `volatility_breakout` · `long_tail_volatility` | 틱 구동 돌파 판정 0 (목표가 기준가는 이미 REST 단독 — cycle272) | 열린다 |
| `donchian_swing` · `kojiro` | 무영향 — `_TICK_BUY_EVAL_SKIP_STRATEGIES`(`risk.py:88`) 가 틱 매수 평가를 이미 skip | 무영향 |

⇒ **리졸버는 시총 1,000억 이상 유니버스의 64% 를 5전략의 매수 평가에 새로 노출시킨다.** 루트 `CLAUDE.md` 의 "매매 행위를 바꾸는 코드 변경은 파일 위치와 무관하게 승인 + `domain-consult` 선행" 에 정면 해당한다.

**구현을 두 단계로 쪼갠다:**

| 단계 | 내용 | 승인 |
|---|---|---|
| **B-1 (청산 축 단독)** | 리졸버를 넣되 **매수 평가는 열지 않는다.** 수단 = `risk.on_tick` 의 매수 분기 앞에 **종목 축** skip 게이트(기존 `_TICK_BUY_EVAL_SKIP_STRATEGIES` 는 전략 축이라 그대로 쓸 수 없다 — 같은 자리 `risk.py:653` 부근에 하나 더 둔다). 청산 분기는 그 **앞**이라 무접촉 | 8영역 승인(완료). 매수 행위 변경 **0** |
| **B-2 (매수 축 개방)** | B-1 의 종목 축 게이트를 걷는다 | **별도 승인 + `domain-consult` 선행** + U-3 대조 1일 선행 |

B-1 을 건너뛰면 "손절을 고치려던 배포" 가 그날 밤 새 종목을 사기 시작한다. 되돌릴 수 없다.

**부수 — `ACML_VOL` 스코프(U-3)**: `H0UNCNT0`(통합)과 `H0STCNT0`(KRX 단독)의 `fields[13]` 이 같은 값인지 모른다. `nxt_false` 종목은 NXT 거래가 없으니 원칙적으로 같아야 하지만 **그건 추론이다.** BFB/VCP 게이트는 `observed >= threshold`(일봉 기반)를 재므로 스코프가 좁아지면 게이트가 조용히 더 엄격해진다. B-1 에서는 매수가 닫혀 행위 영향 0, B-2 전에 **`H0STCNT0` `acml_vol` vs 일봉 `acml_vol` 대조 1일**을 반드시 넣는다.

---

## §4 접촉 파일과 변경 의도

### 4-A 8영역 4파일 (승인 완료)

| 파일 | 변경 의도 | 비고 |
|---|---|---|
| `src/engine/scanner.py` | ① `tick_tr_id_for()` 신설(`:504` 아래) ② 구독 5곳이 리졸버 경유 — `:1003`(HIGH positions) `:1011`(HIGH next_day_clear) `:1069`(LOW pass-1) `:1099`(LOW pass-2) `:1136`(`priority_groups is None` 평탄 폴백, 풀 미경유) ③ `:1173` `unsubscribe_all` 잔여 정리 필터를 등가 비교 → **집합** | 원안의 "`TICK_TR_ID` 직접 사용처 전부 경유" |
| `src/realtime/websocket.py` | ① `get_subscribed_tickers()` `:503` · `get_acked_tickers()` `:513` · F1 재검증 대상 추출 `:565` 를 등가 비교 → **집합** ② `_send_subscribe` 재전송 `:588` 은 `_subscriptions` 튜플을 그대로 쓰므로 채널 안전(확인만) | 🔴 §5-B 누수 차단 필수 |
| `src/realtime/websocket_pool.py` | ① 풀 `get_subscribed_tickers()` `:494` · `get_acked_tickers()` `:505` · `get_session_status()` `:542`,`:545` 를 등가 비교 → **집합** ② **병행 dict `_ticker_to_tr_id: dict[str,str]` 신설**(§5-C) ③ `subscribe()` 중복 분기(`:309-329`)가 "같은 종목 + 다른 채널" 을 **무음 통과시키지 않게** 한다 ④ `:387` 주석(“tr_id 는 TICK_TR_ID 가정”)을 코드 실제(tr_key 매칭 전수, `:383-389`)와 맞춘다 | `_ticker_to_session` 키는 **건드리지 않는다**(C-1) |
| `src/engine/order_engine.py` | `_unsubscribe_if_no_other_strategy` 의 `:1949-1951` `from src.engine.scanner import TICK_TR_ID` → `tick_tr_id_for(ticker)`. 호출자 = `_handle_sell_fill`(`:2332`), 매도 전량 체결 직후 3중 게이트 통과 시 | ⚠️ **원안이 적은 `order_engine.py:1104` 는 2026-09-05 줄번호다.** HEAD 에서 그 자리는 cycle276 LLM 평가 배선(`:1080-1110`) — 구현자가 엉뚱한 곳을 고치지 않게 이 행을 근거로 삼는다 |

### 4-B 8영역 밖 — 같이 고쳐야 하는 것 (승인 불요, 그러나 빠뜨리면 누수)

| 파일:행 | 무엇 | 빠뜨리면 |
|---|---|---|
| `stale_watcher_core.py:217` | grace 판정 키 `ack_map.get((TICK_TR_ID, t))` → 리졸버 경유 | `_subscribed_at` 은 `(tr_id, tr_key)` 키(`websocket.py:186`)라 `H0STCNT0` ACK 은 `("H0STCNT0", t)` 에 심긴다. 조회 키를 안 바꾸면 `_is_within_grace` 영구 miss → **180초 구독 grace 가 nxt_false 종목에만 사라진다** → 구독 직후 stale 판정 → 즉시 강제 재등록 = **cycle252 가 없앤 SEND 폭주의 조용한 부활** |
| `stale_watcher_core.py:184` | `no_feed_registry.ensure_fresh(subscribed)` 의 인자를 **채널 무관 집합**으로 | §5-D 자기 강화 플리커 |
| `stale_watcher_core.py:408`·`411`·`439`·`442`·`676`·`684` | force_retry / r=1~5 / 5분 priority 재구독의 unsub+sub 쌍 | 틀린 채널로 해제 → `OPSP0003 UNSUBSCRIBE ERROR not found!` 스팸(cycle215~218 이 잡은 그 ERROR) |
| `stale_universe_guard.py:161` | 저유동 축출 unsubscribe | 동일 |
| `stale_session_recovery.py:419-427` | `delta_unsubscribe_dropped` 의 `current` 원천 | 🔴 유니버스에서 빠진 종목이 **영원히 해제되지 않는다 = 실제 슬롯 누수** |
| `routes/realtime.py:406` | 대시보드 판독 | 세션 20종목이 `sub=0/41` 로 표시 = 운영자 슬롯 판독 붕괴 |
| `routes/realtime.py:556` | `POST /api/realtime/resubscribe-stale` 수동 재구독 | 틀린 채널로 재구독 |
| `routes/realtime.py:400` | **미사용 import `TICK_TR_ID`** — 제거 | (정리) |
| `handler.py:81` | 주석이 cycle257 이 삭제한 `scanner._TIME_KRX_MAIN_END` 를 인용한다. 같은 줄의 `scheduler.TIME_KRX_MAIN_CLOSE = 15:30`(실재) 인용만 남긴다 | cycle257 F-3 이 "realtime 무접촉 제약으로 P1-7 B 인계" 로 명시한 유일한 잔여 항목 |

### 4-C 🔴 풀을 우회하는 직접 구독 2곳 — **별도 승인 필요**

| 파일:행 | 무엇 | 문제 |
|---|---|---|
| `scheduler.py:1382` | 익일청산 대상 시가 수신용 `kis_ws.subscribe(TICK_TR_ID, ticker)` — 풀 미경유 + **bypass 없음**(메인 41 만석이면 조용히 drop) | 리졸버가 그 종목을 `H0STCNT0` 로 옮겨 놨으면 이 줄이 **같은 종목 이중 채널**을 만든다 |
| `scheduler.py:2728` | `_swing_buy_poll_loop` 매수 성공 직후 `kis_ws.subscribe(TICK_TR_ID, ticker, bypass_limit=True)` | 동일 |

⇒ **`scheduler.py` 는 8영역이 아니지만 별도 승인 대상**이다(라인 상한 + cycle292 충돌). **이 사이클의 기본 설계는 `scheduler.py` 무접촉**이고(§11-2), 그러면 위 두 줄은 여전히 `H0UNCNT0` 로 구독한다 — **§5-C 병행 dict 가 그 이중 구독을 무음으로 두지 않고 `[tick_channel_dual_detected]` WARNING 으로 드러내는 것**이 이 사이클의 처분이다. 실제 시정은 cycle292 착지(= `scheduler.py` 3,897 → **3,726L**, 여유 ≈174줄) 뒤 별도 승인으로 미룬다.

### 4-D sha 핀 갱신 목록

- `tests/unit/ast/test_cycle257_ast_dead_code_removed.py` — `_PRESERVED_TICK_CONSTS`(세 상수 리터럴), `_TICK_FILTER_LITERALS`
- cycle252 의 `no_feed_registry` / `stale_watcher_core` 관련 핀(차분 기준 sha `8b146ff`) — `ensure_fresh` 인자 변경으로 재핀
- `websocket.py` / `websocket_pool.py` / `scanner.py` / `order_engine.py` 세그먼트 sha 핀이 걸린 가드 전수(구현 시 `grep -rn "sha" tests/unit/ast | grep -E "websocket|scanner|order_engine"` 로 확정)
- ⚠️ **핀은 `ast.dump` 가 아니라 소스 세그먼트 sha** 로 둔다(3.12 vs 3.13 차이, 메모리 교훈)

---

## §5 동일 종목 이중 채널 금지 — 무엇으로 강제하는가

### 5-A 왜 금지인가 — 네 갈래 근거

이것은 편의 규칙이 아니다. **ticker 단독 키 자료구조 4개**의 구조적 귀결이다.

| 구조 | 위치 | 키 | 다채널 안전? |
|---|---|---|---|
| `_subscriptions` / `_subscriptions_acked` / `_subscribed_at` / `_opsp_backoff_until` | `websocket.py:121,124,186` | **`(tr_id, tr_key)`** | ✅ |
| **`_ticker_to_session`** | **`websocket_pool.py:95`** | **`tr_key` 단독** | ❌ |
| `ticker_last_tick` | `scanner`(쓰기 `risk.py:513`) | `ticker` | ❌ |
| `ticker_prices` | `scanner` | `ticker` | ❌ |
| `_market_op_subs` | `scheduler:3268,3298` | `ticker` | 별도 dict 로 **회피**(선례) |

1. **`_ticker_to_session` 덮어쓰기 = 무음 실패.** `subscribe()` 중복 분기(`websocket_pool.py:309-329`)는 `tr_id` 를 보지 않는다 — 이미 구독 중인 종목에 다른 채널로 subscribe 하면 `return "main"`/`return label` 로 **SEND 없이** 빠져나가고 호출자는 성공으로 읽는다. cycle221 이 종목별 VI 구독에서 정확히 이 함정을 밟아 "**실질 noop**" 이 됐다(`scheduler.py:3186-3189`). cycle253 프로브가 `_PROBE_ALLOWED_TR_IDS` 에서 `H0UNCNT0` 를 **배제한 이유도 이것**이다(`routes/realtime.py:78-83` 주석).
2. **`tick_volume` 비결정론.** `record_acml_vol` 은 **last-write-wins**(`tick_volume.py:41-58`). 두 채널이 같은 종목 프레임을 주면 KRX 단독 값과 통합 값이 번갈아 기록되고 **BFB/VCP 게이트 판정이 프레임 도착 순서에 좌우된다.** `handler.py:400` 이 세 TR_ID 를 분기 없이 같은 파서로 보내므로 출처를 구분할 수단도 없다. ⇒ **원안이 적은 근거(슬롯 절약)보다 강한 근거가 여기 있다.**
3. **`ticker_last_tick` 혼합 = 증상 은폐.** `risk.py:513` 이 채널 무관 같은 키를 갱신하므로 두 채널 중 하나만 프레임을 줘도 "fresh" 다 ⇒ **H0STCNT0 전환이 실패했는데도 stale 로 안 잡힌다.** 고치려는 증상을 은폐하는 방향.
4. **슬롯 · UNSUBSCRIBE 짝.** 41 은 `(tr_id, tr_key)` 튜플 수다(`websocket.py:468` — 단일 적용 지점). 이중이면 슬롯 2칸. 그리고 해제 6곳이 전부 단일 tr_id 를 가정한다.
5. **사후 구분 불가.** `_handle_tick(payload)` 는 **tr_id 를 넘겨받지 않는다** ⇒ 그 아래 전 경로(`risk.on_tick` → `check_exit_signal`/`check_buy_signal`, `ticker_last_tick`, `ticker_prices`)가 채널 출처를 **전혀 모른다**. cycle272 가 `on_open_price_confirmed(..., source=)` 로 출처 게이트를 만든 것과 정반대 상태다.

### 5-B 🔴 집계 필터 집합화 — 이 사이클의 실질 작업량

등록/해제는 리졸버 한 줄 치환이지만, **`tr_id == TICK_TR_ID` 등가 비교 8곳** 중 하나라도 놓치면 `H0STCNT0` 로 옮긴 종목이 `get_subscribed_tickers()` 에서 **조용히 사라진다.**

등가 비교 전수: `websocket.py:503`·`513`·`565` · `websocket_pool.py:494`·`505`·`542`·`545` · `scanner.py:1173`.

그 집합은 다음의 **공통 원천**이다 — `scanner.py:996`(already_in_pool) · `scanner.py:643`/`650`(get_scan_status) · `stale_watcher_core.py:177`/`661` · `stale_session_recovery.py:419` · `scheduler.py:3249`/`3472`(tick_coverage) · `routes/realtime.py:225`/`406`/`542`/`655`. 빠지면:

- K stale watcher 가 그 종목을 **영원히 못 본다**
- `delta_unsubscribe_dropped` 도 못 봐 유니버스 이탈 종목이 **영구 슬롯 점유**
- 다음 `subscribe_filtered_stocks` 가 `already_in_pool` 에 없다고 판단해 **매 5분 재SEND** = cycle252 가 없앤 churn 의 부활, 이번엔 **은폐된 형태로**
- `[tick_coverage] subscribed=` 분모가 줄어 **숫자가 좋아진다** = cycle252 "은폐 금지" 계약 위반(§9-B)

**재사용할 집합이 이미 있다** — `stale_diagnostics.py:76 _TICK_TR_IDS = frozenset({"H0UNCNT0","H0STCNT0","H0NXCNT0"})` 가 올바른 형태로 존재하고 `:115` 에서 `tr_id in _TICK_TR_IDS` 로 쓰인다. ⚠️ **다만 그것은 함수 지역 변수다** — 승격 = 모듈 레벨(또는 리졸버와 같은 leaf)로 올려 **단일 정본**으로 만들고 소비처 8곳이 그것을 import 한다. **두 번째 집합을 새로 만들면 갈린다.**

### 5-C 강제 수단 — 병행 dict + 4단 순서

**(1) 병행 dict** `websocket_pool._ticker_to_tr_id: dict[str, str]` — `_ticker_to_session` 과 **같은 시점에** 쓰고 pop 한다.

- `subscribe()` 중복 분기에서 `_ticker_to_tr_id.get(tr_key)` 가 **요청 tr_id 와 다르면** 무음 반환하지 않고 `[tick_channel_dual_detected]` WARNING 1행 + **거부**(현행 채널 유지). 이것이 §4-C 의 `scheduler.py` 우회 2곳을 드러내는 수단이다.
- `unsubscribe`/`unsubscribe_all`/`unsubscribe_in_pool`/`remove_session`/`disable_quote_session` 이 `_ticker_to_session` 을 pop 하는 모든 자리에서 동행 pop.
- `_ticker_to_session` **키는 바꾸지 않는다**(C-1).

**(2) 채널 전환 4단 순서** (장중 전환이 불가피할 때만 — §3-C 기본 설계는 전환 자체가 없다)

```
1. unsubscribe(old_tr_id, ticker)                 ← 전 세션 순회 방식
2. _ticker_to_session / _ticker_to_tr_id pop 확인
3. subscribe(new_tr_id, ticker)
4. (new_tr_id, ticker) ∈ 세션 _subscriptions 확인  ← 튜플 실재 검증
```

- **순서는 "해제 → 등록"** 이다. "등록 → 해제" 는 함정 1(무음 no-op)에 걸려 **아무 일도 일어나지 않는다.**
- 해제는 `pool.unsubscribe` 단독으로 부족하다 — 그것은 `_ticker_to_session.pop(tr_key)` 로 찾은 **한 세션**만 본다(`websocket_pool.py:374-380`). 신규 구독이 라운드로빈으로 다른 세션에 떨어진 뒤라면 구 세션의 `(H0UNCNT0, t)` 가 **영구 고아 튜플**로 남아 41 을 잠식한다. ⇒ cycle253 이 같은 이유로 만든 두 헬퍼의 규약을 **그대로 재사용**한다: `_unsubscribe_probe_everywhere()`(전 세션 순회) + `_release_routing_if_orphaned()`(고아 판정) — `routes/realtime.py:144-192`. 그 docstring 이 함정 둘을 명시한다: `unsubscribe_in_pool` 은 (a) 고아를 못 지우고 (b) 승격된 라이브 종목의 라우팅을 pop 해 버린다.
- 4단의 튜플 실재 검증은 프로브의 `_probe_tuple_present()`/409 패턴과 같다(`routes/realtime.py:139-142`, `:706-716`).

**전환 블라인드 창** — 유일 표본 ≤4초(U-4). **그런데 이 사이클의 대상 코호트에는 블라인드 창이 존재하지 않는다**: 전환 대상은 정의상 `H0UNCNT0` 프레임이 하루 0건인 종목이라 **잃을 프레임이 없다.** 창이 실제 위험이 되는 경우는 딱 하나 — **분류가 틀렸거나 플리커할 때**(§6).

### 5-D 이중 채널을 허용하려면 (이 사이클의 범위 밖)

`_ticker_to_session` 을 `(tr_id, tr_key)` 로 재키잉해야 하고 파급은 `subscribe`/`unsubscribe`/`unsubscribe_all`/`resend_subscribe_for_ticker`/`unsubscribe_in_pool`/`disable_quote_session`/`get_subscriptions_by_session`/`remove_session` 8개 메서드 + routes 고아 판정 3헬퍼 + cycle221 VI 주석 규약(`scheduler.py:3266-3269` 가 `kis_ws_pool.unsubscribe` 를 **명시 금지**한다) 전부다. **§7 분기 ② 가 나올 때만 재검토하고, 그때도 §5-A 2번(`tick_volume` 비결정론)을 먼저 닫는다.**

---

## §6 편출 / 플리커 debounce

### 6-A 원안이 지목한 위험은 실재한다 — 다만 원인이 달랐다

`nxt_tradable` 이 뒤집히면 리졸버 답이 뒤집혀 채널이 갈아탄다. 조사가 쓰기 경로를 전수로 재고 **주요 원인이 목록에 없던 네 번째**임을 밝혔다.

### 6-B 쓰기 경로 4갈래 — 실측

| | 경로 | 빈도(실측) |
|---|---|---|
| **W1** | **16:10 basics_refresh** — `scanner._stock_master_basics_refresh_once` → `upsert_one`(`scanner.py:2719`). **진실 설정자** | 매일 1회. `total=3583 updated=3583 skipped=0 failed=0`, elapsed **856s(14.3분)**. 09-10 16:24 · 09-11 16:32 · **09-14 07:53:49→08:08:05**(부팅 catch-up) |
| **W2** | 🔴 **`_full_universe_load_krx_primary`** — `scanner.py:1833` 이 `nxt_tradable=False` 를 **하드코딩**("KRX 영역은 NXT 정보 부재 — 보수적 False")하고 `upsert_one` 의 `ON CONFLICT (ticker) DO UPDATE SET nxt_tradable = EXCLUDED.nxt_tradable`(`src/db/stock_master.py:96`)이 **진실을 덮는다.** 게이트는 `is_stale(ticker, 24h)` 뿐 | **>24h 갭이 있을 때만.** 09-14(월) 07:46:13 `fetched=2674 skipped_ttl=11`. 화~금 아침·20:00:05 은 `fetched=0 skipped_ttl=2685`. 백엔드 재시작도 트리거(09-11 16:10 `fetched=172`) |
| **W3** | `order_engine.py:1408` 거부 사후 보강 (cycle286 C4-a 게이트 = `target_exchange ∈ (NXT,SOR) ∧ 08:00≤now<08:50`) | **0건.** `[nxt_post_reinforce]` = system_logs 48h 0 · 30일 0 · **EC2 파일 로그 전량(08-12~현재) 0.** 한 번도 발화 안 함 |
| **W4** | 마스터 파일 적재 `upsert_master_raw`(`stock_master.py:177`) — 신규 ticker INSERT 때만 False. `ON CONFLICT DO UPDATE SET` 절이 `nxt_tradable` 을 **의도적으로 제외**(`:189`) | **0건.** `stock_master_history.change_type='INSERT'` 30일 0 |
| (읽기) | `[nxt_downgrade]`(`order_engine.py:598`, WARNING·영구·1회/ticker/일) | 30일 **35행**, 1~4건/일, 전부 09:00:1x~09:40. 최신 `09-14 09:05:00 [nxt_downgrade] 204270 strategy=donchian_swing from=NXT to=KRX` |

### 6-C 🔴 W2 가 만드는 오염 창 — 이것이 debounce 설계의 유일한 실측 입력

09-14(월) 부팅 타임라인(system_logs):

```
07:45:45  [stock_master_eager] 보유+익일청산 11종목 갱신 완료   ← 이 11개가 skipped_ttl=11
07:45:49~07:46:13  full_universe_load → 2,674종목에 nxt_tradable=False 도장
07:53:49  [stock_master_basics_refresh_begin] candidates=3583
07:59:01  사전 구독 146종목                             ← TIME_PRESUBSCRIBE = 07:59
07:59:49  [no_feed_held] tickers=['003470','003490','032820','036540']
08:08:05  [stock_master_basics_refresh_summary] updated=3583   ← 진실 복원 완료
```

**종목별 오염 지속 = 7~22분. `TIME_PRESUBSCRIBE`(07:59) 가 그 안에 있다.**

| 측정 | 값 |
|---|---|
| 07:59:01(사전 구독 발화 순간) 아직 도장 상태로 남은 행 | **2,344 / 3,583 (65.4%)** |
| 그중 실제로는 `nxt_tradable=True` 인 것 | **420** |
| 08:00 경계 동일 측정 | 2,098 / 378 |
| **NXT 지정 유니버스(602) 중 07:59 에 `False` 로 읽히던 비율** | **420/602 = 69.8%** |
| `stock_master_history` 교차검증 — seq0/seq1 쌍 3,552 중 seq1 raw 에 `cptt_trad_tr_psbl_yn` 키 **없음**(= W2 도장 흔적) | **2,674** (= `fetched` 와 정확히 일치), 그중 현재 True 파생 **593**. 모든 `changed_at` 이 07:45~08:08 안 |
| 현재 정합성 | `col_ne_raw = 0` — 3,583행 전부 컬럼 = raw 파생값 일치 |

**이 측정이 포렌식 열린 질문 ③ 을 닫는다.** `stale_candidates_0904.md:105`/`:157` 의 "08-31 07:52 064550 False → 08:05 True 플리커 1건 관측(**원인 미확인**)" 은 eager refresh 도, KIS 응답 결측도 아니다 — **W2 도장 → W1 복원**이다. 오늘 파일 로그가 직접 증거다:

```
2026-09-14 07:46:05 [DEBUG] src.db.stock_master — stock_master upsert: 064550 (nxt_tradable=False)
2026-09-14 07:59:09 [DEBUG] src.db.stock_master — stock_master upsert: 064550 (nxt_tradable=True)
```

**리졸버에 주는 위협**: 07:59 에 `nxt_tradable` 을 그대로 읽으면 **진짜 NXT 종목 ≈420개를 `H0STCNT0` 로 보낸다** = NXT 프리장(08:00~09:00) 체결을 실을 수 없는 채널. LTV `tradable_boards` 운영 DB 실측 = `["main","pre_nxt"]` 이므로 **오늘 시세가 살아 있는 유일한 보드에 새 사각을 만든다.** 사전 구독 146 중 약 59개가 걸릴 것으로 **추정**된다(09:56 `fresh=82` 로 nxt_true≈84 를 잡고 69.8% 비례 — **측정값 아님**).

**⇒ 판별자 — 시간 창이 아니라 출처(provenance) 검사 (1안 채택)**

```
그 행의 raw 에 KIS CTPF1002R 키 'cptt_trad_tr_psbl_yn' 이 존재할 때만
nxt_tradable 값을 권위 있는 것으로 취급한다. 없으면 '모른다' = fail-open(H0UNCNT0).
```

- 근거 = W2 도장은 KRX raw 를 쓰므로 이 키가 **없다**(2,674/2,674 정확 일치)
- **시각 리터럴 0개**, 일정 변경에 면역(일봉 16:00→18:10→20:30, basics 16:10 vs 07:53 로 이미 두 번 움직였다)
- 구현 자리 = **`get_nxt_tradable_map` 읽는 쪽 또는 `no_feed_registry` 안.** 🔴 리졸버 본체에 두면 안 된다 — 레지스트리 **TTL 600s** 가 W2 도장 스냅샷을 복원 뒤 최대 10분 더 캐시한다
- 대안 2안(오늘자 basics_refresh 완료 증거가 있을 때만 채널 이동 허용 — `routes/market_ops.py` 의 `_evidence_after_schedule` 패턴)은 백업. 3안(단순 hold-down 타이머)은 **가장 약하다**

### 6-D 백스톱과 금기

- **백스톱** = 동일 종목 **같은 날 재전환 금지**(KST 날짜 키). 값싸고, 출처 검사가 놓친 경로를 막는다. **시간 창 리터럴은 두지 않는다**(C-2).
- **🔴 래치 금지** — "한 번 no_feed 면 영구 `H0STCNT0`" 로 만들면 064550 처럼 **NXT 재편입한 종목을 NXT 체결 못 받는 채널에 영구 좌초**시킨다(09-14 07:59:09 재편입이 양방향임을 증명). 이동은 **양방향**이어야 한다.
- **보유 종목 특례는 불필요하다** — 07:45:45 eager refresh 가 보유·익일청산 11종목에 권위 있는 값을 W2 **전에** 준다(그래서 `skipped_ttl=11`) ⇒ 출처 검사가 그들에게는 즉시 통과한다. **특례를 추가하는 대신 이 이유를 코드 주석에 적는다.**
- **debounce 입력으로 쓰면 안 되는 것** = `[nxt_downgrade]`(읽기 측 + 1/ticker/일 cap → 전환을 셀 수 없다) · `[nxt_post_reinforce]`(30일 + 전체 파일 로그 0건).
- **cycle286 C4-a 는 이 리졸버의 전제다.** 그것이 없으면 애프터 구간의 KRX 주문 거부 하나가 종목을 `nxt_false` 로 낙인찍고 그 오염이 ≈24h 지속되며, 리졸버가 그 오염을 **시세 채널까지** 전파한다(자기 강화 래치).
- **측정 불가로 남는 것** — `stock_master_history` 는 `raw` 만 추적하고 `seq ∈ {0,1}`(최신+직전 1본)만 보존한다(migration 036) ⇒ **`nxt_tradable` 전환 빈도를 과거로 소급 측정할 수 없다.** 현재 가진 근거는 "집합 크기는 602(09-05 포렌식) = 602(09-14) 로 평평한데 **멤버십은 움직였다**(064550)" + NXT 정기변경 650→610(2026-02 → 07) ≈ 40명/분기 ≈ **0.6/영업일** 뿐이다. **그래서 hold-down 창 길이를 정하지 않는다.**

### 6-E 자기 강화 플리커 (함정 D) — 반드시 같이 닫는다

`no_feed_registry.ensure_fresh()` 는 호출자가 준 집합만 조회하고 `_no_feed` 를 **통째로 교체**한다(`no_feed_registry.py:90-92`). 유일한 호출자는 `stale_watcher_core.py:184` 이고 인자가 `kis_ws_pool.get_subscribed_tickers()`(= H0UNCNT0 필터, §5-B) 다.

⇒ 리졸버가 62종목을 `H0STCNT0` 로 옮기면 → 다음 `ensure_fresh` 인자에서 그 62개가 빠짐 → `_no_feed` 에서 탈락 → `is_no_feed()` 가 **False** → 리졸버가 다시 `H0UNCNT0` 로 판정 → **600s TTL 마다 채널 왕복.** KIS 공지의 "비정상 케이스 2(무한 등록/해제)" 그 자체다.

**시정(둘 다 한다)**: ① `ensure_fresh` 인자를 **채널 무관 집합**(desired ∪ 보유)으로 ② §3-C "첫 구독 시점 1회 판정" 으로 살아 있는 구독을 재채널하지 않는다.

---

## §7 🔴 애프터마켓 커버리지 (16:00~20:00) — **측정 #1 전까지 미확정**

### 7-A 정본이 말하는 것

`docs/kis/domestic-stock-realtime.md:3640-3644`(공지 2026-09-09 반영분):

> 🔴 [공지 2026-09-09 · 시행 2026-09-14(월)] 시간외단일가 폐지 — 이 채널의 대상 시장이 사라진다.
> KRX 는 2026-09-14 부터 16:00~20:00 **애프터마켓**(연속 실시간 체결)을 신설하고 **시간외단일가를 폐지**했다.
> 애프터마켓 체결·호가는 이 시간외 전용 채널이 아니라 **기존 정규 채널**로 온다 —
> `H0STCNT0`/`H0UNCNT0`/`H0NXCNT0`(체결가)·`H0STASP0`(호가)에 `MARKET_CLS_CODE=3`(애프터)으로 실린다.

세 체결 채널 필드 표에 `MARKET_CLS_CODE`(1프리/2정규/3애프터/5종가)가 신규로 들어갔다(`:1355`/`:2504`/`:2720`). ⇒ **제도 축에서는 `H0UNCNT0` 도 KRX 애프터를 나르는 채널로 적혀 있다.**

### 7-B 정본이 말하지 않는 것

| 미지 | 왜 치명적인가 |
|---|---|
| **무송출 결함이 애프터 구간에도 적용되는가** | 공지는 "어느 채널이 어느 시장을 나르나" 만 말한다. "`nxt_false` 종목에는 프레임을 안 보낸다" 는 **우리가 실측으로만 아는 결함**이다. 제도가 바뀌어도 결함이 저절로 낫지는 않는다. 확신도 ≈90% 로 여전히 무송출이라고 본다 |
| `MARKET_CLS_CODE` 의 payload index | 공지는 "추가됩니다" 만 밝혔고 `docs/kis` 3개 표 모두 "위치 미명시 — 첫 프레임 실측으로 확정" 이라고 적는다. 중간 삽입이면 `fields[8] STCK_HGPR`·`fields[13] ACML_VOL`·`fields[27] HGPR_HOUR` 가 전부 밀린다. `_parse_day_high` 는 밀려도 **예외도 로그도 없이 0 반환**(`handler.py:519-522`), `_parse_acml_vol` 은 `-1` sentinel 로 조용히 빠진다(`:556`). **무음 열화** |
| `H0STCNT0` 이 16:00~20:00 에 프레임을 주는가 | 09-07~09 프로브는 **정규장 시간대** 실측이다. 저녁 구간 실측은 0 |

**⚠️ `docs/kis/*.md` 를 이 축에서 단독 근거로 쓰지 말 것.** 그 파일은 2026-09-11 03:00 워크북 스냅샷이고 09-14 사실은 손으로 넣은 「제도 변경 공지 반영」 절과 각 필드 자리에만 있다. cycle280 자문이 이 함정에 빠져 존재하지 않는 「저녁 시세 공백」 CRITICAL 을 냈다.

### 7-C ✅ **측정 완료 (2026-09-14 16:39~16:41 라이브)** — 분기 ① 확정

**분기표는 끝났다.** cycle253 프로브 실측:

| 종목 | 속성 | 채널 | 결과 |
|---|---|---|---|
| 000815 삼성화재우 | `nxt_false` | `H0STCNT0` | **수신** — 구독 5초 뒤 첫 틱 · 419,000원 · `acml_vol=6,075` |
| 005385 현대차우 | `nxt_false` | `H0STCNT0` | **수신** — 구독 1초 뒤 첫 틱 · 178,500원 · `acml_vol=62,067` |
| 000660 SK하이닉스 | **`nxt_true`** | `H0STCNT0` | **수신** — `age=0` · 1,692,000원 · `acml_vol=3,773,544` |
| 005945 NH투자증권우 | `nxt_false` | `H0STCNT0` | 미수신(저유동, 그 시각 체결 없음) — 판정에 쓰지 않는다 |

⇒ **`H0STCNT0` 는 종목 속성과 무관하게 KRX 애프터마켓(16:00~20:00) 체결을 싣는다.**
`nxt_false`(통합 채널에서 하루 종일 프레임 0건인 코호트)도, `nxt_true` 도 정상 수신된다.

**따라오는 설계 단순화 — 자문이 가정한 전환 2회가 1회로 줄었다**

```
08:00~08:50  프리장        → H0NXCNT0 (NXT 전용)   ※ 그 시각 NXT 만 열려 있다
08:50~09:00  전환 창        → 주문 0건 구간(설계 · 워크리스트 판독표) + cycle241 시장 침묵
09:00~20:00  정규장+애프터  → H0STCNT0 (KRX 전용)   ※ 전환 0회, 연속
```

- 자문 §7-④ 가 권고한 **15:34 NXT 애프터 전환은 불필요하다.** cycle287 이 애프터 주문을
  KRX 로 보내기로 확정했으므로(`_route_exchange_by_clock` 애프터 → KRX), 그 구간에 KRX
  가격을 보는 것이 오히려 정합이다 — **평가 가격 = 체결 가격**.
- 전환이 **하루 1회**, 그것도 주문이 구조적으로 0인 창에 놓인다 ⇒ 자문 §2.2 가 시간축을
  2등으로 판정하며 들었던 근거("유일하게 손절 사각을 신설한다")의 크기가 크게 줄었다.
  **없어진 것은 아니다** — make-before-break·REST 백스톱·자동 원복은 여전히 필수다(§7-⑤).

**미측정으로 남는 것** — ① `H0NXCNT0` 의 프리장 커버리지(08:00~08:50)는 09-08~09 프로브가
간접 확인했으나 09-14 제도 변경 이후 재측정은 없다 ② `H0STCNT0` 의 KRX 시가단일가
(08:20~09:00) 체결 송출 여부 — 전환 시각을 09:00 보다 앞당길지의 입력이고, 전환을 08:55 에
두면 이 값을 몰라도 성립한다 ③ `ACML_VOL` 스코프 동일성(U-3) — B-2(매수 개방) 선결 조건.

### 7-D 🔴 불변식 — 보유 종목의 손절 커버리지는 리졸버 전보다 **나빠지지 않는다**

어느 분기에서든 다음을 만족해야 배포한다. 회귀 가드가 이 넷을 잠근다(§10-G4).

```
INV-1  보유(HIGH) 종목이 리졸버 후 어느 시각 구간에서도
       "리졸버 전에는 프레임이 왔는데 후에는 안 온다" 가 되지 않는다.
INV-2  HIGH 경로(positions · _pending_next_day_clear)의 bypass_limit=True 보장은 byte 동일.
INV-3  REST 폴 커버리지(donchian·kojiro, 09:00:30~15:20)는 무접촉.
INV-4  판정 실패는 항상 현행 유지(H0UNCNT0)이고, 보유 종목 판정 실패는 WARNING 으로 노출된다.
```

**비대칭이 이 절의 근거다** — 리졸버가 **틀렸을 때 잃는 것**은 그 종목의 손절 커버리지이고 되돌릴 수 없다(체결은 취소되지 않는다). 리졸버가 **없을 때 잃는 것**은 지금 이미 잃고 있는 것(변화 0). ⇒ **불확실한 채로 배포하지 않는다.** `nxt_false` 보유 0 인 상태에서 배포하는 것이 최선이고, 보유 중이라면 §8 킬스위치가 반드시 있어야 한다.

### 7-E REST 폴 창 확장(대안 1)과의 관계 — 이 사이클의 범위 밖, 그러나 중복이 아니다

| 축 | 대안 1 (REST 창 확장) | 대안 2 (채널 리졸버 = 이 사이클) |
|---|---|---|
| 고치는 축 | **시각** — 15:20 이후 평가 주체 부재 | **채널** — 특정 종목의 프레임 부재 |
| 해상도 | 60초 | 체결 단위 |
| 커버 범위 | `_SWING_POLL_STRATEGIES` 2전략 보유만 | 전 전략의 `nxt_false` 전부 |
| 저녁 공백 | (REST 가 애프터 시세를 준다면) **측정 결과 무관하게** 닫는다 | 분기 ②·④ 에서는 닫지 못한다 |
| 접촉 | `scheduler.py` | 8영역 4파일 |

⇒ **1이 있으면 2가 실패해도 폴이 받고, 2가 있으면 1의 60초보다 촘촘하다.** ①번 결과에서도 대안 1을 **2선으로 남긴다.**

확장 시 부작용 전수 점검(소스 = `_run_swing_rest_poll_once` `scheduler.py:2755-2877` · `_swing_rest_poll_loop` `:2879-2920`):

| 점검 | 결과 |
|---|---|
| 매수가 열리는가 | **아니다 — 3중으로 닫혀 있다.** ① `on_tick` 은 `if ticker in held_set:` 안에서만(`:2856`) ② 보유 중이라 `registry.is_ticker_blocked_for_buy` 가 `has_position` 으로 전 전략 차단(`strategy_registry.py:86-98`) ③ 16:00~20:00 활성 보드 POST_NXT 를 통과하는 전략은 LTV 뿐인데(`session.py:79-82`) 그 LTV 도 ②에 막힌다 ⇒ 매수 행위 변경 **0** |
| 🔴 `_last_tick` 오염 | **확장 시 반드시 `preserve_last_tick=True`.** 현행대로면 `_early = now_t < 09:30` 이 False 라 REST 가 `ticker_last_tick` 을 찍어 **blind 종목이 `[tick_coverage]` 에 "신선" 으로 보인다** = 유일한 증상 신호 소멸(cycle222-a F3 와 같은 함정, cycle252 은폐 금지 위반) |
| `day_high` 채택 | 16:00~20:00 은 MAIN 이 아니라 `_adopts_day_high()` False → 미채택(`risk.py:270-290`). 애프터 고가가 트레일링 앵커를 오염시키지 않는다 — **현행 그대로가 정답** |
| KIS 호출량 | `held_only` 라 보유 12 × 60초 → 시간당 720, 4시간 2,880. `SWING_REST_POLL_TICKER_SLEEP_SECS=0.05` ⇒ 20/s 한도 무해. 단 19:00 토큰 재발급 창(문턱 18:50)과 겹쳐 실패 폭주 관측 필요 |
| 라인 예산 | HEAD 3,897L / 상한 3,900 = 여유 **3줄**. **cycle292 착지 후 3,726L = 여유 ≈174줄**(diff `+3/−174`, 제거 구간 `:3172` 이후) ⇒ 확장은 cycle292 착지가 선행 |
| 성립 조건 | **U-5 미측정** — `fetch_stock_detail`(FHKST01010100)이 16:00~20:00 에 애프터 체결가를 `stck_prpr` 로 주는지 모른다. 주지 않으면 대안 1 은 무효 |

### 7-F 시간외 전용 3채널 — 후보에 넣지 않는다

`H0STOUP0`·`H0STOAA0`·`H0STOAC0` 세 채널 정본 머리에 같은 🔴 경고가 들어가 있다("시간외단일가 폐지 — 이 채널의 대상 시장이 사라진다", `docs/kis/domestic-stock-realtime.md:496`·`:668`·`:3640`). **폐지 여부는 공지가 명시하지 않았다.** `src/`·`tools/` 전수 grep 결과 세 TR_ID 는 **어디에도 없다**(구독·파서 분기·상수 전부 0). ⇒ **리졸버 영향 0.** 반환값 후보는 `scanner.py:502-504` 세 상수뿐이다. 그래도 재는 이유 = ① 폐지 확정 시 `docs/kis/` 3곳 경고문을 확정형으로 ② 살아 있는데 프레임이 오면 제4 후보(가능성 낮음 — 단일가 전용 필드 구조).

### 7-G 부수 발견 — `_parse_day_high` 창이 애프터를 통째로 버린다 (리졸버와 독립)

`_HGPR_HOUR_MAIN_START=90000` / `_HGPR_HOUR_MAIN_END=153000`(`handler.py:113-114`). 이 창은 "통합 채널의 NXT 프리장 오염" 을 막으려 만든 것인데(000250 실측), `HGPR_HOUR ∈ 16:00~20:00` 인 애프터 고가를 `return 0` 으로 강등한다. `_maybe_log_open_scope_observe` 도 같은 창으로 게이트돼(`:346`) **애프터 틱은 관측조차 안 남는다**.

**U-2(`MARKET_CLS_CODE` index)가 확정되면 그 시각창을 시장 코드 필터로 교체할 수 있고**, 그러면 (a) 애프터 고가 강등과 (b) cycle222-a3 F-E(프리장 고가가 종일 0으로 강등되는 잔여 사각, `handler.py:456-472`)가 **한 번에 닫힌다.** 리졸버보다 값이 클 수 있고 **리졸버 없이도 독립 착지 가능**하다 — §12-2 로 분리해 별도 사이클 후보로 남긴다.

**또 하나 (채널 무관 기존 결함)**: `websocket.py:776` 이 `_count` 를 `_` 로 버리고 `_handle_tick` 은 `payload.split("^")` 앞 47개만 읽는다. 정본(`:1284-1286`)은 `0|H0STCNT0|004|...` = 체결 4건이 한 프레임에 온다고 명시한다 ⇒ **페이징 프레임의 2~4번째 체결은 지금도 조용히 버려진다.** 채널을 바꾸면 페이징 빈도가 달라질 수 있으므로 배포 뒤 **틱 건수 자체**를 비교해야 드러난다(`[dispatch_drop_summary]` 로는 안 잡힌다).

---

## §8 단계 · 킬스위치 · 롤백

### 8-A 3단계

| 단계 | 내용 | 관측 | 진행 게이트 |
|---|---|---|---|
| **S0 다크런치 (행위 0)** | 리졸버 함수 + 집합화 + 병행 dict 만 넣고 **모드 `observe`** — 판정 결과를 로그로만 남기고 구독은 전원 `H0UNCNT0` | `[tick_channel_config] mode=observe resolved_krx=N resolved_unified=M` 부팅 1행(카나리아) · `[tick_channel_resolve] ... would=H0STCNT0` | `resolved_krx` 가 0이 아니고, `[tick_coverage]`·`[stale_watcher_summary] no_feed_skipped=`·`[priority_drop]` 이 **전부 불변**(= 행위 0 증명) |
| **S1 부분 적용** | **보유·익일청산(HIGH) 제외**, LOW 후보 `nxt_false` 만 `H0STCNT0`. 모드 `enforce_low` | `[tick_channel_resolve]` 실제 발화 · `fresh` 증가 · `[ws_ack_orphan]`·`[stale_force_retry]` 감소 · `[tick_channel_dual_detected]` **0건** | 1영업일 — INV-1~4 위반 0 · `[bfb_vol_gate_no_data]`/`[vcp_vol_gate_no_data]` **불변**(B-1 이면 매수가 닫혀 있어야 한다) |
| **S2 전면** | HIGH 포함(단 장중 전환 금지 — `_boot`/재구독 시점만). 모드 `enforce` | 위 + `nxt_false` 보유 종목의 `ticker_last_tick` 갱신 · 16:00~20:00 프레임 수신 | — |

**HIGH 를 나중에 넣는 이유** — 가설이 어떤 보유 종목에 대해 틀렸을 때 잃는 것이 **손절 커버리지**다(cycle252 가 `no_feed` skip 에서 HIGH 를 byte 동일로 남긴 것과 같은 판단).

### 8-B 킬스위치 — 🔴 파라미터 1개, 장중에 닿아야 한다

| | |
|---|---|
| 키 | `system_config.tick_channel_resolver_mode` ∈ `observe` / `enforce_low` / `enforce` / **`off`** |
| 왜 `system_config` 인가 | 리졸버는 전략별 설정이 아니라 **인프라 축**이다(7전략 `DEFAULT_PARAMS` 에 넣으면 7곳이 갈릴 수 있다) |
| 🔴 **cycle287 의 실패를 반복하지 않는다** | cycle287 은 킬스위치 2개를 `param_catalog` 미등재로 만들어 **`PUT /api/strategies/{id}/params` 가 `unknown_key` 422** = 장중에 끌 수 없었다. ⇒ **`off` 가 즉시 닿는 경로를 같은 커밋에 넣는다** — `system_config` 축이면 `PUT /api/settings` 경로 + **in-memory 반영 지점**을 명세·코드에 함께 적는다(`_load_strategy_config` 의 `_config_loaded` 처럼 "다음 재시작에만 반영" 이 되면 킬스위치가 아니다) |
| 롤백 | `off` → 다음 재구독 사이클에 전원 `H0UNCNT0` 복귀. **코드 revert 불필요**(1커밋 revert 는 재배포 = 재시작이고 D6·D8 이 막는다) |
| ⚠️ 롤백이 즉시가 아닌 지점 | §3-C/§6-D 의 "장중 전환 금지" 때문에 이미 `H0STCNT0` 에 있는 **보유 종목은 다음 `_boot` 까지 그 채널에 남는다.** 이 사실을 운영 문서에 적는다 |

### 8-C 배포 창

- 배포 자체 = 장외 창 **15:30~19:55 · 21:35~익일 07:45**(20:00~21:35 금지 — cycle283 D8). 보유 중 장중 push 금지(D6).
- 🔴 **그리고 §7 측정 #1 판독 뒤.** 오늘 저녁(16:00~20:00)은 **측정 시간**이므로 그 창에 배포하지 않는다.

---

## §9 관측 마커

### 9-A 신규

| 마커 | 레벨 | 필드 | cap |
|---|---|---|---|
| `[tick_channel_config]` | INFO | `mode= resolved_krx=N resolved_unified=M provenance_ok=P provenance_unknown=Q` | 부팅 1행 = **카나리아**(배포 반영 확인) |
| `[tick_channel_resolve]` | INFO | `ticker= nxt=false channel=H0STCNT0 reason=no_feed provenance=cptt_key` | 1회/(ticker,channel)/일, `KstDailyEmitCap` |
| `[tick_channel_flip]` | WARNING | `ticker= from= to= reason= same_day_blocked=0\|1` | 발화 시(백스톱 §6-D) |
| `[tick_channel_dual_detected]` | WARNING | `ticker= existing= requested= caller=` | 1회/(ticker)/일 — §4-C 풀 우회 2곳을 드러내는 유일한 수단 |
| `[tick_channel_provenance_unknown]` | WARNING | `n= sample=[…]` | 1회/일 — W2 오염 창에 걸린 판정 수 |

### 9-B 🔴 기존 마커의 **의미 전환** — 배포 전후 grep 합산 금지

| 마커 | cycle252 계약 | cycle293 이후 |
|---|---|---|
| `[tick_coverage] stale` | **불변이 정상**(현상 은폐 금지) | **줄어드는 것이 성공 서명.** ⚠️ 단 **채널 이동만으로 분모가 줄어서는 안 된다** — §5-B 집합화가 분모를 유지하고, 성공은 `stale` 감소가 아니라 **`fresh` 증가**로 먼저 나타나야 한다 |
| `[stale_watcher_summary] no_feed_skipped=` | 재등록 skip 이 정상(회복 가치 0) | **회복 가치가 생긴다** ⇒ skip 을 그대로 두면 새 채널의 진짜 stale 을 못 고친다. cycle252 의 skip 조건을 "`H0UNCNT0` 구독 중인 LOW no_feed" 로 좁힌다 |
| `[no_feed_held]` | "보유 종목이 WS blind, 손절은 REST 폴만" 을 매일 알림 | **0 이 되어야 정상**(S2 뒤). 0 이 아니면 판정 실패 or 전환 실패 |
| `[stale_force_retry]` / `[ws_ack_orphan]` | 하루 ≈14,600 SEND / 7,120 orphan | 감소 |

**두 사이클의 `stale` 수치를 합산하거나 나란히 놓지 말 것.** 09-14 배포 전후 로그는 서로 다른 것을 재는 계기다.

---

## §10 회귀 가드

| # | 잠글 것 | 방식 |
|---|---|---|
| **G1** | 상수 3개 값 불변 + 리졸버 반환값이 그 3개 중 하나 | `test_cycle257_ast_dead_code_removed.py::_PRESERVED_TICK_CONSTS` 갱신 + 리졸버 반환 도메인 단언 |
| **G2 (fail-open 방향)** | 미지 ticker · 레지스트리 미적재 · 조회 예외 · `None` · 출처 미확인 → **전부 `H0UNCNT0`** | 파라미터화 테스트 5케이스 + 뮤테이션(반환을 `_KRX` 로 뒤집으면 RED) |
| **G3 (이중 채널 금지)** | 같은 ticker 에 서로 다른 TICK tr_id 구독이 동시에 존재하지 않는다 | 런타임 불변식 테스트(`_ticker_to_tr_id` vs 전 세션 `_subscriptions` 튜플 교차) + `subscribe()` 가 다른 채널 요청을 **무음 통과시키지 않는다**는 단언 |
| **G4 (보유 커버리지 불변식)** | INV-1~4 | HIGH 경로 `bypass_limit=True` byte 동일(AST) · REST 폴 경로 diff 0(AST) · HIGH 장중 전환 0건 · 판정 실패 + 보유 → WARNING 발화 |
| **G5 (집합화 전수)** | `tr_id == TICK_TR_ID` **등가 비교가 소스에 0건**(리졸버 정의부 제외) | AST/텍스트 가드 — 새 등가 비교가 들어오면 RED. 소비처 8곳이 **단일 정본 집합**을 import 하는지도 단언(두 번째 집합 정의 0건) |
| **G6 (grace 키 정합)** | `stale_watcher_core` 의 ACK 조회 키가 그 종목의 실제 구독 tr_id 와 같다 | 키 불일치 시 grace 무력화 → SEND 폭주 재현 회귀 테스트 |
| **G7 (플리커)** | ① `ensure_fresh` 인자가 채널 무관 집합 ② 출처 미확인 값으로는 채널을 옮기지 않는다 ③ 같은 날 재전환 0 ④ **래치 없음**(True 로 돌아온 종목은 `H0UNCNT0` 로 되돌아간다) | 시퀀스 테스트(W2 도장 → presubscribe → W1 복원 재현) |
| **G8 (해제 정합)** | 해제 6곳 전부 리졸버 경유 + 전 세션 순회 + 고아 0 | `OPSP0003` 재현 테스트 + 고아 튜플 0 단언 |
| **G9 (매수 축 차단, B-1)** | `nxt_false` 종목의 틱 **매수** 평가가 0 | 종목 축 skip 게이트 테스트 + `[*_vol_gate_no_data]` 불변 단언 |
| **G10 (파싱 무변경)** | `handler.py` 의 tick 파싱 인덱스·`dispatch_message` 분기 **byte 동일** | 세그먼트 sha 핀 |

---

## §11 금기

1. **8영역 4파일 밖의 8영역 파일 무접촉** — `risk.py`(B-1 종목 축 게이트는 승인 범위 확인 필요) · `session.py` · `strategy_registry.py` · `api/order.py` · `auth/**`.
2. **`scheduler.py` 무접촉** — cycle292 동시 작업 + 라인 상한(HEAD 3,897 / 상한 3,900 = 여유 3줄). §4-C 풀 우회 2곳은 **관측으로만 드러내고** 시정은 cycle292 착지 뒤 별도 승인.
3. **전략 7파일(`DEFAULT_PARAMS` 포함) 무접촉** — 킬스위치는 `system_config` 축.
4. **stale 수를 집계에서 빼서 숫자를 좋게 만들기 금지** — 채널을 옮긴 종목을 분모에서 제외하는 순간 cycle252 의 은폐 금지 계약이 깨진다(§5-B, §9-B).
5. **fail-closed 금지** — 판정 실패 시 구독을 건너뛰거나 `H0STCNT0` 로 강제하지 않는다(P0-1 재현 방향).
6. **`_ticker_to_session` 재키잉 금지**(이 사이클) — §5-D.
7. **"사이클 26 시간대별 전환 죽은 코드 처분" 을 찾지 말 것** — `get_active_tick_tr_ids`·`_board_transition_loop`·`_atomic_board_transition`·`TIME_*_PRESUBSCRIBE` 는 **cycle257(`4cf479a`+`1b30dd6`)이 이미 삭제**했고 `src/` 프로덕션 참조 0건이다. 남은 언급은 되살림 차단 AST 가드(`_DEAD_FUNCS_SCANNER`/`_DEAD_FUNCS_SCHEDULER`)와 이력 문서뿐. **라인 예산 기여 0** — 워크리스트 B 항목의 그 문장은 폐기한다.
8. **시간외 전용 3채널을 리졸버 후보에 넣지 않는다** — §7-F.
9. **`_SWING_POLL_STRATEGIES` 에 BFB/VCP 추가 금지** — 그 상수는 매수 폴루프·구독 대상도 겸해 매수 행위가 바뀐다(`boot_manager.py:444`, `bull_flag_breakout.py:1450`).
10. **애프터 거부 `msg1` 분류 분기 추가 금지** — cycle287 이 의도적으로 분류에 의존하지 않게 만들었다.
11. **배포는 §7 측정 판독 뒤.** 정규장 축 근거만으로 먼저 배포하지 않는다(§7-D 비대칭).

---

## §12 미해결 · 후속

| # | 항목 | 상태 |
|---|---|---|
| 1 | **U-1** 16:00~20:00 채널별 프레임 수신 | 🔴 **배포 게이트.** 오늘 저녁 프로브 + 라이브 대조. 유동 `nxt_false` 종목 동반. 실체결 0건이면 "미판정" |
| 2 | **U-2** `MARKET_CLS_CODE` payload index | 리졸버와 **독립된 위험**. 확정되면 §7-G(애프터·프리장 고가 강등 2건)를 한 번에 닫는 별도 사이클 후보 |
| 3 | **U-3** `H0STCNT0` `ACML_VOL` 스코프 | B-2(매수 개방) 착수 게이트. 1일 수집 후 일봉 대조 |
| 4 | **U-4** KIS 재등록 지연 상한 | 표본 1건(≤4초). §3-C 채택 시 무력화 |
| 5 | **U-5** REST 가 애프터 시세를 주는가 | §7-E 대안 1 의 성립 조건 |
| 6 | **U-6** 시간외 전용 3채널 거동 | `docs/kis/` 경고문 확정용. 리졸버 무영향 |
| 7 | **`H0STCNT0` 프레임 필드가 정말 같은가 — 실측 미완** | 정본 표 3개는 47필드 인덱스 동일(C-4)이고 cycle253 프로브 3건이 `oprc_hour` 를 정상 파싱했다. **그러나 전 필드 대조 실측은 없다.** S0 다크런치에서 `H0STCNT0` 프레임 원문 1건을 덤프해 `fields[8]/[13]/[24]/[27]/[34]/[43]` 를 대조하는 것을 **S1 진행 게이트에 넣는다.** 다르면 `handler.py` 변경이 딸려 오고 그것은 이 명세의 전제를 바꾼다 |
| 8 | 문서 시정 3건 (별도, 코드 0) | ① `src/realtime/CLAUDE.md:93` — `get_subscribed_tickers` 를 "합집합" 이라 서술하지만 **구현은 단일 등가 비교**다(코드 docstring `websocket.py:496` 은 정직하다). 집합화 후에야 그 서술이 참이 된다 ② 같은 파일 `:248-250` 구독 종류 표에 **무송출 사실이 없다**(`src/realtime/CLAUDE.md` 전체에 `no_feed`/무송출 0회 등장 — realtime 문서만 읽는 사람은 `H0UNCNT0` 가 완전하다고 결론 낸다). `H0STCNT0` 의 "호환성 유지" 표기도 시정 ③ 루트 `CLAUDE.md` cycle286 절의 "7전략 `exchange` 전부 SOR" → 운영 DB 실측 **전부 `NXT`**(C-5) |
| 9 | `data_load_tasks` / `_market_op_subs` 선례 | `_market_op_subs`(`scheduler.py:3268,3298`)가 "제2 라우팅 dict" 선례다 — `_ticker_to_tr_id` 설계의 근거로 인용 가능 |

---

## §13 결정 카드 (사용자)

| # | 결정 | 선택지 | 권고 |
|---|---|---|---|
| **D-1** | 구현을 **B-1(청산 축 단독)** 로 쪼갤 것인가 | (가) 쪼갠다 — 종목 축 매수 skip 게이트 동반 / (나) 한 번에 매수까지 연다 | **(가).** (나)는 손절 수리 배포가 그날 밤 새 종목을 사기 시작한다(§3-E, 유니버스 64% 신규 노출) |
| **D-2** | 배포 게이트 | (가) §7 분기 판정 뒤 / (나) 정규장 축 근거만으로 먼저 | **(가).** 16:00~20:00 에 새 blind 를 만들 수 있다(§7-D 비대칭) |
| **D-3** | 판정 실패 시 fail 방향 | (가) `H0UNCNT0` 유지(cycle252 관례) / (나) 보유 종목만 `H0STCNT0` | **(가) 기본** + 보유 중 판정 실패는 `[no_feed_held]` WARNING 과 함께 사람에게 올린다 |
| **D-4** | 저녁 공백을 **오늘 밤**에도 닫을 것인가 | (가) 관측·감시 유지(현 결정) / (나) REST 폴 창 확장을 먼저 넣는다 | 사용자 결정. (나)는 **cycle292 착지 선행**(라인 예산 3줄 → ≈174줄) + `preserve_last_tick=True` 필수 + `domain-consult` |
| **D-5** | `scheduler.py` 풀 우회 2곳(`:1382`·`:2728`) | (가) 이 사이클은 **관측만**(`[tick_channel_dual_detected]`) / (나) 같이 고친다(별도 승인 + 라인 예산) | **(가).** cycle292 와 충돌하고 여유가 3줄뿐이다 |

---

## 부록 A — 손절 신호 경계표 (시각 × 채널 × `nxt_tradable`)

판정 소스: 보드 = `session.py:62-67 BOARD_SCHEDULE` · REST 폴 = `scheduler.py:2907` · 구독 수명 = §2-A P-5 · 프레임 수신 = 포렌식(과거) + 저녁 측정(미래).

| 시각(KST) | 활성 보드 | 시장 실체(09-14 이후) | `nxt_true` 보유 | `nxt_false` 보유 |
|---|---|---|---|---|
| ~07:45 | — | — | 엔진 미가동(`TIME_AUTO_START=07:45`) | 동일 |
| 07:45~07:59 | ∅ | — | 구독 전(`TIME_PRESUBSCRIBE=07:59`) ⇒ 평가 0 | 동일 |
| 07:59~08:00 | ∅ | 거래 없음 | 구독됨·프레임 0 | 동일 |
| **08:00~08:50** | PRE_NXT | NXT 프리마켓 연속(`N1`, GTP 27~29) | 프레임 **있음** / REST —. 단 **LTV 외 6전략은 청산 평가 보류**(주1) | 프레임 **0** ⇒ **평가 0** |
| **08:50~09:00** | PRE_NXT | NXT 휴장(`N2`) + KRX 시가단일가(`K1` 08:20~) | 프레임 ≈0 ⇒ 사실상 0 | 0 ⇒ **평가 0** |
| **09:00~09:00:30** | MAIN | KRX 정규장 개장 | 프레임 있음 / REST 미시작 | 0 / 미시작 ⇒ **평가 0** |
| **09:00:30~09:30** | MAIN | KRX·NXT 정규장 | 프레임 있음 / REST `held_only=True`(주2) | 0 / **REST 60초**(주2·주3) |
| **09:30~15:20** | MAIN | KRX·NXT 정규장 | 프레임 있음 / REST 전체 폴 | 0 / **REST 60초**(주3) |
| **15:20~15:30** | MAIN | KRX 장마감 동시호가 · NXT 휴장(`N4`) | 프레임 ≈0 / **REST 종료**(`> 15:20`) ⇒ ≈0 | 0 / 종료 ⇒ **평가 0** |
| **15:30~15:40** | MAIN | KRX 시간외 종가(`K5`) · NXT 애프터 단일가(`N5`) | 프레임 여부 **미지** | 0 ⇒ **평가 0** |
| **15:40~16:00** | POST_NXT | NXT 애프터 연속(`N6` 15:40~20:00) | 프레임 **있음**(09-08 15:45 필옵틱스 실체결) | 0 ⇒ **평가 0** |
| **🔴 16:00~20:00** | POST_NXT | **KRX 애프터마켓 연속 신설(`K6`, ±30%)** + NXT 애프터(`N6`) | 프레임 **있음**(NXT 축만으로도 성립, P-5) | **0 (확정)** / REST — ⇒ **손절 평가 0** |
| 19:50 | POST_NXT | 동일 | `buy_disabled=True` — 청산 무영향 | 동일 |
| **20:00~** | ∅ | 애프터 종료 | `unsubscribe_all()` + `_scan_task.cancel()`(`scheduler.py:884-888`) | 동일 |

**주1** `risk.py:79 _PRE_MARKET_EXIT_EVAL_STRATEGIES = frozenset({"long_tail_volatility"})`, 판정 `_defers_pre_market_exit`(`risk.py:203`) = `PRE_NXT ∈ active ∧ MAIN ∉ active`. **평가 보류이지 주문 보류가 아니다**(사용자 결정 2026-08-06). `nxt_false` 종목에는 프레임이 없어 무의미.

**주2** `held_only=True, preserve_last_tick=True`(`scheduler.py:2914`). `preserve_last_tick` 은 REST 가 `ticker_last_tick` 을 갱신해 blind 종목을 "신선" 으로 위장하지 않게 한다(cycle222-a F3) ⇒ **REST 가 손절을 구해도 `[tick_coverage] stale` 은 계속 붉다.** 은폐 금지가 계약.

**주3 🔴** `held_set` = `_SWING_POLL_STRATEGIES = ("donchian_swing","kojiro")`(`scheduler.py:145`) 두 전략 positions 합집합(`:2789-2794`). ⇒ **BFB/VCP 가 `nxt_false` 를 잡으면 종일 손절 평가 0**(둘은 멀티데이 보유). `momentum`/VB/LTV 는 틱 청산 0 이지만 15:20 `_force_clear_main_only` / 09:00 익일청산이 시각 구동으로 받는다(손절선 기반 청산은 아니다). **오늘 4종목이 전부 kojiro·donchian 인 것은 우연이다.**

---

## 부록 B — `TICK_TR_ID` 사용처 전수 (2026-09-14)

**(a) 등록 — ticker 를 안다 ⇒ 리졸버 경유 (7곳)**

| 파일:행 | 경로 | priority/bypass |
|---|---|---|
| `scanner.py:1003` | `kis_ws_pool.subscribe` | HIGH / True (positions) |
| `scanner.py:1011` | 동일 | HIGH / True (next_day_clear) |
| `scanner.py:1069` | 동일 | LOW / False (pass-1) |
| `scanner.py:1099` | 동일 | LOW / False (pass-2 overflow) |
| `scanner.py:1136` | **`kis_ws.subscribe`** | 기본 False — 풀 미경유 평탄 폴백 |
| `scheduler.py:1382` | **`kis_ws.subscribe`** | **bypass 없음** — 메인 41 만석이면 조용히 drop |
| `scheduler.py:2728` | **`kis_ws.subscribe`** | bypass=True |

**(b) 해제/재전송 — ticker 를 안다 (9곳)**: `scanner.py:1173` · `order_engine.py:1951` · `stale_universe_guard.py:161` · `stale_session_recovery.py:427` · `stale_watcher_core.py:408,411` · `:439,442` · `:676,684` · `websocket.py:588` · `routes/realtime.py:556`

**(c) 디스패치 — ticker 를 *모른다*, 리졸버 호출 불가 (1곳)**: `handler.py:400`. tr_id 가 **입력**이고 ticker 가 출력(`payload.split("^")[0]`). 리졸버의 결정이 옳았는지 **사후 검증할 수 있는 유일한 지점**이지만 `_handle_tick(payload)` 가 tr_id 를 넘겨받지 않아 그 아래 전 경로가 출처를 모른다.

**(d) 집계·관측 — 집합화 대상 (9곳)**: `websocket.py:503`,`513`,`565` · `websocket_pool.py:494`,`505`,`542`,`545` · `stale_watcher_core.py:217`(ACK 맵 **키**) · `stale_diagnostics.py:76`,`115`(**이미 3채널 대응 완료 — 이것을 정본으로 승격**) · `websocket_pool.py:387`(주석만 낡음, 코드는 tr_key 매칭 전수라 안전)

**미사용**: `routes/realtime.py:400` (import 후 본문에서 안 쓴다 — 제거)

---

## 부록 C — 채널 상수 전수

| TR_ID | 성격 | 정의처 | 현행 |
|---|---|---|---|
| `H0UNCNT0` | 시세 | `scanner.py:502`(`TICK_TR_ID`) | **유일 활성 구독**. 실전 전용 |
| `H0STCNT0` | 시세 | `scanner.py:503` · `market_state.py:128`(`_CH_KRX`) · `routes/realtime.py:81` · `stale_diagnostics.py:76` · `handler.py:400` | 구독 예약 + cycle253 프로브 + 표 표시. **실 구독 0건**. **모의 지원** |
| `H0NXCNT0` | 시세 | `scanner.py:504` · `market_state.py:129`(`_CH_NXT`) · 동상 | 동일 |
| `H0UNMKO0` | 장운영정보(VI/CB/보드) | `api/market_operation.py:35` | 부팅 005930 1건(`scheduler.py:640`) + 보유·익일청산 종목별(`:3298`). 실전 전용. **매매 게이트 미연계**(`:3181-3183`) |
| `H0STMKO0`/`H0NXMKO0` | 장운영정보 | 상수 없음 — `handler.py:405` 분기만 | 구독 0건 |
| `H0STCNI0`/`H0STCNI9` | 체결통보 | `websocket.py:56` · `websocket_pool.py:59`(`_EXECUTION_NOTICE_TR_IDS`) | **메인 세션 단일 강제** + AES 키 저장 유일 허용 |

**가름선** — 시세 3종(`*CNT0`)만 `_handle_tick` → `risk.on_tick` → 매매 판정에 들어간다. `*MKO0` 는 관찰 전용. `*CNI0/9` 는 체결·포지션 등록.

---

## 부록 D — 풀 구독 실측 (2026-09-14 09:56 KST, 개장 중)

```
[pool_start] main=1 quotes=7 total_slots=328                                 (07:45:47)
[tick_coverage] subscribed=146 fresh=82 stale=64 ratio=56.2% last_tick_avg_age=5.5s
[tick_coverage_session] main sub=12/41 | ISA 21 | RIA 18 | fire 18 | gold 20
                        | 44606571 20 | 71513056 19 | 1004 18
[market_op_subscribe_summary] high=12 low_skipped=134 placed=0 released=0
                              skipped_no_slot=0 main_direct=0 sessions=7
                              main_tick=12 main_total=14 main_over=0 cap=60
[priority_drop] 0건 · [ws_subscribe_reject] 0건 · OPSP0008 0건
```

| 세션 | TICK | 비-TICK | 점유/41 | 잔여 |
|---|---|---|---|---|
| main | 12 | 2 (`H0STCNI0` + `H0UNMKO0`/005930) | **14/41** | 27 |
| 보조 7 합 | 134 | 12 (종목별 VI) | **146/287** | 141 |
| **풀 합** | 146 | 14 | **160/328** | **168** |

전환 대상 ≈62종목을 "등록 먼저 → 해제 나중" 으로 한 사이클에 전부 옮겨도 222/328, 세션 최악 ISA 21→30/41. ⇒ **41-cap 은 이 사이클의 제약이 아니다**(§2-A P-6).

**순증 산술** — `순증 = 신 채널 튜플 수 − 실제로 해제된 구 채널 튜플 수`. 이상적 전환 = 0 / 무음 no-op(§5-A 1) = 0 이지만 **채널도 안 바뀜 = 사이클 무효** / 고아·delta 누수(§5-B) = **+1/종목 영구** / "등록 먼저" = 전환 중 일시 +N.
