# cycle359 — `H0UNMKO0` 필드 한 칸 밀림 (검토 메모 F-B) 조사

- 작성: tester · 2026-09-25 (휴장일) · 범위 = 조사 + Red 테스트 + 수정안. `src/` 무수정, 운영 읽기만, 커밋 없음
- 출발점: `_workspace/reports/2026-09-25_daily_and_advice_review.md` §4 F-B · §5 P1

## 결론 (쉬운 말)

1. **결함 확정.** 장운영정보(`H0UNMKO0`) 실제 프레임은 첫 칸이 종목코드인데, 우리 파서는 첫 칸을 「거래정지 여부」로 읽는다. 그래서 모든 칸이 한 칸씩 밀린다.
2. 밀린 결과, 종목상태 「신용가능(55) · 증거금100%(57)」이 **VI 발동**으로 읽힌다. 이 값은 하루 종일 안 바뀌므로 VI 가 **한 번도 풀리지 않았다**(3일간 발동 7건 · 해제 0건). 거래정지는 반대로 **절대 잡히지 않는다**.
3. 이 채널은 **보유 종목만** 구독하므로, 가짜 VI 에 걸린 7종목은 전부 보유 종목이었다. 그 종목들은 그날 밤까지 시세 재구독 안전망에서 빠졌다(258회, 1회 빼고 전부 15:30~20:00).
4. 이번 3일에 **실제로 놓친 손절의 증거는 없다** — 그 시간대 stale 은 애프터장 거래가 뜸해서였고, 재구독을 계속한 다른 보유 종목도 똑같이 stale 이었다. 그러나 애프터장에는 REST 백업 폴이 없어서 **시세가 진짜로 끊겼다면 고칠 장치가 없던** 상태다.
5. 🔴 **칸만 고치면 안 된다.** 칸을 바로 읽으면 55/57 이 이번엔 「종목상태 이상 = 거래정지」로 읽혀 같은 skip 이 이름만 바꿔 남는다. 파서와 종목상태 판정을 **함께** 고쳐야 한다.

---

## 1. 정본 스펙 대조

| 출처 | `H0UNMKO0`(통합) | `H0STMKO0`(KRX) | `H0NXMKO0`(NXT) |
|---|---|---|---|
| `docs/kis/domestic-stock-realtime.md` | 192행 절 · 218행 표 **10칸, [0]=`TRHT_YN`** (종목코드 없음) | 1116행 절 · 1181행 표 **11칸, [0]=`MKSC_SHRN_ISCD`** · 예시 1236행 `396300^N^(null)^^311^^^55^N^N` (실제 10칸) | 3478행 절 **11칸, [0]=`MKSC_SHRN_ISCD`** |
| KIS MCP 공식 샘플 (`read_source_code`, 2026-09-25) | `market_status_total.py` columns **10개, `TRHT_YN` 부터** | `market_status_krx.py` **11개, `mksc_shrn_iscd` 부터** | `market_status_nxt.py` **11개, `MKSC_SHRN_ISCD` 부터** |
| **라이브 프레임 (EC2 실측 17건)** | **10칸, [0]=종목코드** — KRX/NXT 와 같은 배치, 끝의 `EXCH_CLS_CODE` 는 오지 않음 | (구독 안 함) | (구독 안 함) |

- 문서 캐시와 KIS MCP 가 **같은 내용**(통합만 종목코드 칸 누락)이므로 캐시가 낡은 것이 아니라 **KIS 명세 자체가 라이브와 다르다.** 같은 문서의 다른 통합 실시간 TR 표(264행 등)는 전부 `MKSC_SHRN_ISCD` 로 시작한다 — 통합 장운영 표만 빠진 누락으로 읽힌다.
- 참고: KIS 공식 `kis_auth.py`(examples_llm)는 `pd.read_csv(sep="^", names=columns)` 로 읽는다. 10칸 프레임에 10개 이름을 주면 **KIS 샘플도 똑같이 한 칸 밀린다**(로컬 재현: `TRHT_YN=100840`, `VI_CLS_CODE=55`). 11칸이 오면 pandas 가 첫 칸을 인덱스로 삼아 우연히 맞는다.

## 2. 코드 — 어디가 몇 칸 밀리나

`src/realtime/websocket.py:955-962` 은 `tr_key = payload.split("^")[0]` 로 **첫 칸을 종목코드로 쓴다.** 그 값이 운영 로그의 `ticker=100840` 이다. 같은 칸을 파서가 다시 `TRHT_YN` 으로 읽는 것이 모순이다.

| 라이브 칸 | 실제 의미 | 실측 값 | `parse_market_op_payload`(`src/api/market_operation.py:84-93`) 가 넣는 곳 |
|---|---|---|---|
| [0] | 종목코드 | `100840` | `trht_yn` → `"100840".upper()=="Y"` 는 영원히 거짓 = **거래정지 탐지 불능** |
| [1] | TRHT_YN | `N` | `tr_susp_reas_cntt` |
| [2] | TR_SUSP_REAS_CNTT | `(null)` | `mkop_cls_code` |
| [3] | MKOP_CLS_CODE | `AB1` | `antc_mkop_cls_code` |
| [4] | ANTC_MKOP_CLS_CODE | `112`/`311` | `mrkt_trtm_cls_code` |
| [5]·[6] | MRKT_TRTM · DIVI_APP | 빈칸 | `divi_app_cls_code` · `iscd_stat_cls_code` |
| [7] | ISCD_STAT_CLS_CODE | `55`/`57` | `vi_cls_code` → **가짜 VI** |
| [8] | VI_CLS_CODE | `N`(16건)/`Y`(1건) | `ovtm_vi_cls_code` |
| [9] | OVTM_VI_CLS_CODE | 빈칸 | `exch_cls_code` |

값 범위로도 확인된다 — [7]의 55/57 은 `ISCD_STAT_CLS_CODE` 값 표(51~59, 00)에 있고 [8]의 Y/N 은 `VI_CLS_CODE` 값 표(Y/N)다. 지금 배치로는 `vi_cls_code=55`(범위 밖) · `mrkt_trtm_cls_code=112`(범위 1~6 밖)가 된다.

소비 지점:

| 위치 | 무엇을 읽나 | 결과 |
|---|---|---|
| `market_operation_monitor.py:66` | `vi_cls_code`(=55) · `ovtm_vi_cls_code`(=진짜 VI) | 55 는 `_is_code_active` 가 참 → `_vi_active_tickers` 추가 · `[market_op_vi_active]`. 55 는 안 바뀌므로 **해제 없음** |
| `market_operation_monitor.py:80-83` | `trht_yn`(=종목코드) · `iscd_stat_cls_code`(=DIVI_APP, 보통 빈칸) | 거래정지 판정 사실상 항상 거짓 |
| `market_operation_monitor.py:110-116` `is_ticker_stale_excluded` | VI ∪ halt | 가짜 VI 종목 = 참 |
| `stale_watcher_core.py:410-455` K watcher(120s) · `:768-785` 5분 우선 재구독 | `_market_op_skip(t)` | **HIGH(보유) 종목에도 적용**된다 → 재구독 대상에서 빠짐 · `[stale_skip_market_op]` |
| `handler.py:746` (8영역) | `fields[2]` = `(null)` | `_on_board` → `session.on_h0nxmko0` 의 `_last_nxt_mkop_code="(null)"`. `is_call_auction_now`(`session.py:219-224`)는 `110`/`121` 만 보는데 라이브 코드는 `AB1` 이라 **고쳐도 분기가 같다 = 행위 영향 0**. 운영 로그 `mkop_cls_code=(null)` 만 틀린다 |
| `is_event_blocking` | — | 프로덕션 소비처 0 (문서·테스트만) |
| `routes/realtime.py:655-680` RealtimeHealth 카드 | 위 상태 | 가짜 VI 가 대시보드에 「VI 활성」으로 표시됨 |

구독 대상은 `market_op_subscribe.py:33-35` 대로 **보유 + 익일청산(HIGH) 뿐**이다. 즉 가짜 VI 는 구조적으로 **보유 종목에만** 걸린다.

## 3. 운영 증거

### 3.1 라이브 프레임 원문 17건 (EC2 `~/auto_stock/logs/auto_stock.log.2026-09-2{1,2,3}`, `src.realtime.handler` INFO)

⚠️ 파일 로그는 곧 회전되므로 원문을 여기 보존한다. 전부 10칸, 첫 칸 = `tr_key`.

```
2026-09-21 09:40:16 [H0UNMKO0] tr_key=003160, mkop_cls_code=(null), payload=003160^N^(null)^AB1^112^^^55^N^
2026-09-21 09:40:51 [H0UNMKO0] tr_key=003160, mkop_cls_code=(null), payload=003160^N^(null)^AB1^311^^^55^Y^
2026-09-21 09:41:34 [H0UNMKO0] tr_key=078350, mkop_cls_code=(null), payload=078350^N^(null)^AB1^112^^^55^N^
2026-09-21 09:42:16 [H0UNMKO0] tr_key=003160, mkop_cls_code=(null), payload=003160^N^(null)^AB1^112^^^55^N^
2026-09-21 09:43:19 [H0UNMKO0] tr_key=003160, mkop_cls_code=(null), payload=003160^N^(null)^AB1^311^^^55^N^
2026-09-21 09:43:44 [H0UNMKO0] tr_key=078350, mkop_cls_code=(null), payload=078350^N^(null)^AB1^311^^^55^N^
2026-09-21 09:45:54 [H0UNMKO0] tr_key=078350, mkop_cls_code=(null), payload=078350^N^(null)^AB1^112^^^55^N^
2026-09-21 09:47:54 [H0UNMKO0] tr_key=078350, mkop_cls_code=(null), payload=078350^N^(null)^AB1^311^^^55^N^
2026-09-21 10:52:04 [H0UNMKO0] tr_key=036540, mkop_cls_code=(null), payload=036540^N^(null)^AB1^311^^^57^N^
2026-09-21 10:54:11 [H0UNMKO0] tr_key=036540, mkop_cls_code=(null), payload=036540^N^(null)^AB1^311^^^57^N^
2026-09-22 11:13:06 [H0UNMKO0] tr_key=100840, mkop_cls_code=(null), payload=100840^N^(null)^AB1^112^^^55^N^
2026-09-22 11:15:06 [H0UNMKO0] tr_key=100840, mkop_cls_code=(null), payload=100840^N^(null)^AB1^112^^^55^N^
2026-09-23 10:55:21 [H0UNMKO0] tr_key=004020, mkop_cls_code=(null), payload=004020^N^(null)^AB1^112^^^55^N^
2026-09-23 10:56:32 [H0UNMKO0] tr_key=011170, mkop_cls_code=(null), payload=011170^N^(null)^AB1^112^^^57^N^
2026-09-23 10:58:51 [H0UNMKO0] tr_key=011170, mkop_cls_code=(null), payload=011170^N^(null)^AB1^311^^^57^N^
2026-09-23 12:51:21 [H0UNMKO0] tr_key=000520, mkop_cls_code=(null), payload=000520^N^(null)^AB1^112^^^57^N^
2026-09-23 12:53:48 [H0UNMKO0] tr_key=000520, mkop_cls_code=(null), payload=000520^N^(null)^AB1^311^^^57^N^
```

- 09-20 · 09-24 파일은 0건. 대표 종목 005930 은 3일간 0건 — 이 채널은 장 전환 코드(110/121)를 보내지 않고 **종목 이벤트 때만** 온다.
- 같은 종목의 프레임이 **2분~2분 30초 간격 쌍**으로 온다(100840 11:13:06→11:15:06, 011170 10:56:32→10:58:51, 000520 12:51:21→12:53:48) — VI 2분 단일가 + 랜덤 종료와 시각이 맞는다. 그런데 VI 칸 [8] 이 `Y` 인 것은 **17건 중 1건**(003160 09:40:51)뿐이다. 이 쌍이 무엇을 뜻하는지는 확정하지 못했다(§7 ③).

### 3.2 가짜 VI → 재구독 skip 연결 고리

| 날짜 | `[market_op_vi_active]` (지금 파서 기준 `vi_code`) | `[market_op_vi_release]` | `[stale_skip_market_op]` 줄 수 · 첫~끝 | 시간대 분포 |
|---|---|---|---|---|
| 09-21 | 003160(55) 09:40:16 · 078350(55) 09:41:34 · 036540(57) 10:52:04 | 0 | 118 · 09:41:59~19:59:00 | 09시 1 · 15시 13 · 16~19시 104 |
| 09-22 | 100840(55) 11:13:06 | 0 | 36 · 15:31:50~19:40:23 | 15~19시 전부 |
| 09-23 | 004020(55) 10:55:21 · 011170(57) 10:56:32 · 000520(57) 12:51:21 | 0 | 104 · 15:31:20~19:55:42 (`['011170','004020']` 14 + `['011170']` 90) | 15~19시 전부 |

- 3일 합계: 가짜 VI **7종목(전부 보유)** · 해제 **0** · skip **258줄**. 장중(09:00~15:20) skip 은 09-21 09:41:59 **1건뿐**이고, 그것은 유일한 진짜 VI(`Y` 09:40:51 → `N` 09:42:16) 창 안이었다.
- 장중에 skip 이 거의 없는 이유 = skip 판정은 **stale 인 종목에만** 걸린다(`stale_watcher_core.py:450-455`, `and` 단락평가). 장중에는 그 종목들에 체결이 계속 와서 stale 이 아니었다. 애프터장(16:00~20:00)은 체결이 뜸해 stale 이 되고, 그때 skip 이 발동했다.
- `[stale_watcher_detail]` 에서 가짜 VI 종목은 `r=0,@-`(재구독 0회)로 찍히고, 같은 시각 다른 보유 종목은 `r=6`(반복 재구독)이다(예: 09-22 15:43:02 `(100840,r=0,@-)` vs `(011170,r=6,@15:40:53)`). 5분 우선 재구독의 HIGH 목록에서도 빠졌다(09-22 15:45:16 `count=10` 에 100840 없음).

### 3.3 실제로 손절을 놓쳤나 — 증거 없음

- **011170**: 가짜 VI 가 없던 09-22 에도 애프터장 내내 stale 이었다(재구독 `r=6` 반복에도 회복 안 됨) → stale 원인은 끊긴 시세가 아니라 **체결이 없는 것**. 09-23 skip 이 빼앗은 재구독은 09-22 에도 아무것도 고치지 못했다.
- **100840**: 09-22 15:30~20:00 main 세션 `[stale_watcher_detail]` 108줄 중 38줄에만 stale 로 찍혔다 — 나머지 시각에는 체결이 들어와 fresh 였다 = 시세 구독은 살아 있었다.
- 한계: 애프터장 틱 이력이 저장되지 않아 「그 시간에 손절선을 건드린 체결이 없었다」를 직접 증명할 수는 없다. 말할 수 있는 것은 「재구독 안전망이 꺼져 있었고, 그것이 필요했던 순간(구독이 진짜로 끊긴 순간)의 흔적은 없다」까지다.

## 4. 영향

| 축 | 영향 |
|---|---|
| **손절 커버리지** | VI 이벤트를 한 번이라도 받은 **보유 종목**은 그날 21:30 `_reset_daily_state`(`scheduler.py:3749-3752` → `reset_market_op_state`)까지 K watcher · 5분 우선 재구독 **둘 다에서** 제외된다. 시세 구독이 조용히 끊겨도 복구 경로가 없다 |
| REST 백업 | `_swing_rest_poll_loop` 는 **donchian·kojiro 한정**(`scheduler.py:145` `_SWING_POLL_STRATEGIES`) · **09:05~15:20 한정**. 애프터장에는 어느 전략도 REST 백업이 없고, BFB(100840·003160)는 장중에도 없다. 즉 이 결함이 켜지는 시간대(애프터장)에는 WS 재구독이 **유일한** 안전망이었다 |
| 누가 잘 걸리나 | VI 는 급등 직후에 난다 — 돌파 매수 직후 종목(100840 은 11:11 구독 배치 = 매수 직후, 11:13 첫 프레임)이 걸리기 쉽다 |
| 거래정지 탐지 | `trht_yn` 에 종목코드가 들어가 **영원히 거짓**. 보유 종목이 정지돼도 halt set 에 안 들어가고 서킷브레이커 휴리스틱(`get_circuit_breaker_state`)도 못 본다 (둘 다 표시 전용) |
| 대시보드 | RealtimeHealth 5번째 카드에 가짜 VI 가 「VI 활성」으로 뜬다 |
| 보드 전환(`_on_board`) | 행위 영향 0 — 위 §2 표 |
| 매수·수량·주문 | 영향 없음 (`risk.on_tick`·`order_engine` 은 이 상태를 읽지 않는다) |

## 5. Red 테스트

파일: `tests/unit/realtime/test_cycle359_mkop_field_offset.py` — 현재 코드 결과 **4 passed · 13 xfailed**.

| 묶음 | 테스트 | 현재 | 무엇을 막나 |
|---|---|---|---|
| A 증거 고정 | A1 websocket 이 첫 칸을 `tr_key` 로 씀 · A2 라이브 프레임 모양(10칸·첫 칸 6자리·[7]∈{55,57}·[8]∈{Y,N}) | 초록 | 전제가 바뀌면 붉어진다 |
| B 파서 칸 | B1 `trht_yn=="N"` · B2 10칸 전체 배치 · B3 `vi_cls_code∈{Y,N}` | xfail | 칸 밀림 |
| C 최종 행위 | C1 55/57 프레임 → stale 회피 아님 · C2 `Y`→`N` 프레임으로 VI 해제 · C3 거래정지 프레임(합성)은 halt 로 · C4 `00/55/57` 이벤트는 halt 아님 · **C5 대조군** `58` 은 회피 대상(초록) | xfail / C5 초록 | 칸 밀림 **+ 두 번째 덫** |
| D 끝에서 끝 | D1 raw `0\|H0UNMKO0\|001\|…` → websocket → handler → monitor · D2 `_on_board` 에 `AB1` 전달 | xfail | D2 는 8영역(`handler.py:746`) |
| E 안전망 | **E1 대조군** 프레임 없으면 보유 stale 종목 HIGH 재구독(초록) · E2 09-22 100840 재현 — 프레임 1건 뒤에도 재구독돼야 | E1 초록 / E2 xfail | 운영 사고 자체 |

모든 xfail 은 `strict=True, raises=AssertionError` — 하네스 오류는 xfail 로 삼키지 않고, 수정이 착지하면 XPASS 로 붉어진다.

**수정안 시뮬레이션**(scratch 플러그인이 monkeypatch 로 후보 수정을 입힘, `src/` 무수정):

| 입힌 수정 | 새 파일 결과 | 기존 장운영 테스트 9파일(86건) |
|---|---|---|
| 칸만 고침 | B1·B2·B3·C3 만 XPASS, **C1·C2·C4·D1·E2 여전히 실패** → 두 번째 덫 실증 | — |
| 칸 + 종목상태 화이트리스트 `{58}` + handler mkop | **13건 전부 XPASS** · 대조군 4건 초록 | 85 통과 · **1 실패** = `test_cycle149_market_operation.py::test_G_A2[N-0-0-1-True]`(가상 코드 `"1"` 을 종목상태 이상으로 단언 — 값 표에 없는 코드, 고쳐야 할 테스트) |

⚠️ 새 테스트 파일 때문에 `tests/unit/deploy/test_cycle318_impact_index_freshness.py::test_backend_index_is_fresh` 가 붉다(파일을 빼면 초록 — 확인함). 커밋할 때 `python tools/test_impact/build_index.py` → `node tools/test_impact/build_index_frontend.mjs` 순서로 재생성해야 한다. 이 조사에서는 인덱스를 건드리지 않았다.

## 6. 수정안

### M (권장 최소안) — 8영역 밖

1. `src/api/market_operation.py` (sha 핀 0곳)
   - 칸 기준점: `off = 0 if fields and fields[0] in ("Y", "N") else 1` 후 `_f(i) = fields[i + off]`. 첫 칸이 `Y/N` 이면 문서 모양(종목코드 없음), 아니면 라이브 모양. 기존 합성 테스트(`"N^^110^…"`, `"Y^임시중단^…"`)도 그대로 통과한다(시뮬레이션 확인). `tr_key == fields[0]` 로 판별하지 않는다 — websocket 이 `tr_key` 를 `fields[0]` 에서 뽑으므로 항상 참이라 판별력이 없다.
   - 종목상태 판정 분리: `ISCD_STAT_BLOCKING = frozenset({"58"})` + `is_iscd_stat_blocking(code)`. `is_event_blocking` 의 종목상태 줄을 이것으로 바꾼다. VI·시간외VI 는 값 범위가 Y/N 이라 기존 `_is_code_active` 그대로 둔다.
2. `src/engine/market_operation_monitor.py` (sha 핀 1곳 = `tests/unit/ast/test_cycle292_ast_market_op_leaf.py::_BASE_SHA`)
   - `:80-83` halt 판정의 `_is_code_active(event.iscd_stat_cls_code)` → `is_iscd_stat_blocking(...)`.
   - `get_market_op_state_summary` 의 `iscd_stat_active_count` 도 `_is_code_active` 라 고치면 **55·57·00 전부를 셀** 것이다. 표시용 집합(예: 51·52·53·54·58·59 — 시장경고·관리·정지·단기과열)으로 따로 센다. cycle186 테스트(51 을 1 이상으로 셈)는 그대로 초록.
3. 같이 고칠 테스트: 새 파일 xfail 마커 12개 제거(D2 는 아래 보류) · `test_G_A2` 의 `"1"` 케이스를 `"58"→True`, `"55"/"57"/"00"→False` 로 · `_BASE_SHA` 핀 갱신 · 영향 인덱스 재생성.
4. 문서(`/sync-docs`, report-writer): `src/api/CLAUDE.md` 245~246행 · `src/engine/CLAUDE.md` 76행(「KIS 10컬럼 전수 파싱」) · `docs/kis/domestic-stock-realtime.md` 통합 절에 「라이브는 첫 칸 종목코드(실측 2026-09-21~23 17건)」 주석(재생성 시 다시 넣도록 `docs/kis/README.md` 에도).

- 배포 모드 = **full**(`src/` 변경 → backend 재시작). 09-25~27 휴장이라 창은 종일 열려 있다. 09-28 장 전 반영하려면 09-27 까지 결정.
- 롤백 = 커밋 1개 revert(DB·설정 변경 없음, 상태는 매일 21:30 초기화).
- 매매 행위 영향 = **재구독 안전망이 원래 설계대로 돌아온다**(보유 종목이 가짜 VI 로 빠지지 않음). 진입·청산·수량·주문 경로는 무접촉. 추가 비용 = 애프터장에 체결 없는 보유 종목의 재구독 SEND 가 되살아난다 — 09-22 의 011170 과 같은 수준이고 기존 cap(시간당 6회·r>5 쿨다운)이 묶는다.

### D2 (보류 권장) — `handler.py:746` mkop 칸

- **8영역 + sha 핀 15파일**(`handler.py` 현재 sha 가 `tests/unit/ast/` 15개 파일에 박혀 있다). 고쳐도 `AB1` 이 110/121 이 아니므로 **행위 차이 0**, 운영 로그 `mkop_cls_code=` 만 바로잡힌다. 다음에 승인된 8영역 사이클에 묶는다. 그때 방법 = 파싱된 `event.mkop_cls_code` 를 콜백에 넘기기(칸 계산을 한 곳으로). 그 전까지 D2 는 xfail 로 남는다.

### H1 (선택 · 결정 필요) — VI 상태 수명

수정 뒤에도 「VI=`Y` 를 받고 해제 프레임을 못 받으면 그날 끝까지 skip」은 **드물게** 남는다(3일 17건 중 `Y` 1건 · 해제 프레임이 늘 온다는 보장 없음). 방법 둘:
- (a) VI 활성에 수명을 준다(예: 마지막 `Y` 뒤 10분 지나면 자동 해제) — 채널의 목적(진짜 VI 동안 재구독 헛발질 방지)을 유지.
- (b) 보유(HIGH) 종목은 장운영 skip 을 받지 않는다 — 가장 단순하지만, 이 채널은 **보유 종목만** 구독하므로 사실상 채널의 매매 쪽 쓰임새가 없어진다(표시 전용이 됨).

## 7. 크리티컬 분기

1. 🔴 **칸만 고치는 수정은 결함을 없애지 못한다** — 55/57/00 이 「종목상태 이상」으로 읽혀 가짜 VI 가 가짜 거래정지로 바뀔 뿐이다(시뮬레이션 C1·C2·C4·D1·E2 실패). 게다가 한 날 보유 종목 5개 이상이 VI 프레임을 받으면 halt 비율이 100% 가 되어 **가짜 서킷브레이커 의심**(`[market_op_cb_suspected]`, 표시 전용)까지 뜬다. 파서와 종목상태 판정은 한 커밋이어야 한다.
2. **KIS 명세(문서 캐시 = MCP 샘플)가 라이브와 다르다.** 「MCP 가 정본」 규칙을 그대로 따르면 틀린다. 칸 판별을 값(`Y/N`)으로 하면 두 모양을 다 받는다.
3. **2분 간격 프레임 쌍의 의미 미확정** — 시각은 VI 발동·해제와 맞는데 VI 칸은 대부분 `N` 이다. 수정 뒤 VI 판정은 거의 켜지지 않을 것이다(재구독이 더 자주 도는 쪽 = 안전 방향). VI 를 `ANTC_MKOP_CLS_CODE`(311=예상시작·112=예상종료)나 `AB1` 로 읽어야 하는지는 추가 실측이 필요하다 — 이번 수정 범위에 넣지 않는다.
4. **종목상태 51(관리)·59(단기과열)를 skip 대상에 넣을지** — 59 는 30분 단일가라 시세 공백이 정상이다. 넣으면 그 보유 종목은 3일간 재구독 안전망 밖, 안 넣으면 재구독 헛발질(cap 안). 기본값은 **안 넣음**(보유 종목 보호 쪽)을 권한다. 도메인 판단 항목.
5. `handler.py` 는 8영역이라 D2 는 이번에 못 고친다 — 행위 영향이 없음을 근거로 분리한다(§2 `_on_board` 행).

## 8. 결정이 필요한 것

- **M 적용 여부**(재구독 안전망 행위가 바뀌므로 승인 대상) — 09-28 장 전 반영 희망 시 09-27 까지.
- 종목상태 skip 집합: `{58}` 만(권장) / `{58, 59}` / `{51, 58, 59}`.
- H1: 안 함 / (a) 수명 / (b) 보유 면제.
- D2 를 언제 8영역 사이클에 묶을지.

## 9. 재현

- 테스트: `python -m pytest -q tests/unit/realtime/test_cycle359_mkop_field_offset.py -rxX` → 4 passed, 13 xfailed.
- 라이브 프레임: `ssh ubuntu@3.38.228.74 'grep -a "MKO0\] tr_key=" ~/auto_stock/logs/auto_stock.log.2026-09-2*'`
- skip 집계: 같은 파일에서 `grep -a stale_skip_market_op | cut -c12-13 | sort | uniq -c`
- KIS MCP: `search_domestic_stock_api(subcategory="실시간시세", api_name="장운영정보")` → `read_source_code(.../market_status_{total,krx,nxt}.py)`
