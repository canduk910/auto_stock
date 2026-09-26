# cycle369 — 관리종목(51)·단기과열(59) 보유 청산 + 신규 매수 차단 자문

- 작성: domain-expert · 2026-09-26(토, 휴장) 02:xx KST · 범위 = 설계 자문. `src/` 무수정 · 운영 DB/로그 읽기 전용 · KIS 는 시세 조회(FHKST01010100) 20건만 · 커밋 없음
- 출발점: 사용자 결정 원문(2026-09-25 21:5x) 「거래정지 판정은 58만 봐, 대신 관리종목51과 단기과열59가 발동했는데 해당 종목을 보유하고 있으면 시장가로 청산하게 하고 재구독 중지등으로 신규매수를 중단하자.」 · 질문지 = 세션 scratchpad `e3_consult_brief.md` · 배경 = `cycle359_mkop_field_offset.md` · 직전 커밋 `b8b06d7`(cycle368)

---

## 0. 결론 (쉬운 말)

1. **사용자 결정대로 「바로 시장가 청산」으로 간다. 관측만 하는 1단계는 두지 않는다.** 판정 근거인 KIS 전용 플래그를 오늘 실제로 불러 모양을 확인했고(§2.3), 판정 규칙이 단순하며, 이 사건은 드물어서 관측만 하는 기간을 둬도 배울 것이 거의 없다. 대신 **확인 두 번 · 거래 가능 시간 제한 · 킬스위치**로 잘못 파는 경우를 막는다.
2. **판정은 실시간 프레임(`H0UNMKO0`)이 아니라 REST `FHKST01010100` 의 전용 플래그로 한다** — `mang_issu_cls_code=="Y"`(관리) · `short_over_yn=="Y"`(단기과열 지정·연장). 이유: ① 프레임은 VI 같은 사건이 있을 때만 온다(10거래일 31건, 전부 55/57). ② 종목상태 칸은 값을 **하나만** 담아서, 관리종목 207개 중 51 로 보이는 것은 **100개뿐**이다(나머지는 58·00·59 로 가려진다).
3. **파는 시간은 KRX 정규장 09:00:30~15:28 로 한정한다.** 그 밖에서 감지하면 「대기」로 걸어 두고 다음 정규장에 판다. 🔴 **16:00~20:00 KRX 애프터마켓은 단기과열종목을 거래 대상에서 뺀다**(KRX 규정 페이지). 관리종목도 빠진다고 보도됐다. 이 시간대에 주문을 내면 거부된다 → 포기 래치가 걸리고 CRITICAL 이 나온다.
4. **단기과열 종목은 30분마다 한 번씩만 체결된다**(09:00·09:30·…·15:00·15:30 단일가). 시장가를 내도 다음 체결 시점까지 최대 30분 기다린다. 기존 매도 경로(`_selling` 유지 · `selling_reconcile` 의 열린 주문 보존)가 이 대기를 이미 견딘다.
5. **거래정지(58·임시정지)와 겹치면 팔 수 없다** — 기다렸다가 정지가 풀리는 첫 조회에서 판다. 주문을 반복해서 넣지 않는다.
6. **「재구독 중지」는 글자 그대로 구현하지 않는다.** 보유 종목의 시세를 끊으면 청산 주문이 거부됐을 때 손절이 눈을 감는다. 원문이 노린 「신규 매수 중단」은 이미 있는 두 장치가 맡는다 — 판 당일은 `is_sold_today`(전 전략 공통), 다음 날부터는 진입 필터(`_is_master_blocked_for_entry`). 체결 뒤 구독 해제도 이미 `_unsubscribe_if_no_other_strategy` 가 한다.
7. 🔴 **남는 빈틈 하나 — 보유하지 않은 후보가 지정 첫날(T+1) 사는 것**은 지금 막지 못한다. 지정은 T일 장 마감 뒤 공시되고 효력은 T+1 부터인데, 진입 필터가 보는 `stock_master` 는 T일 16:10 에 갱신된 값이다. 이 부분은 사용자에게 범위를 다시 물어야 한다(§8).
8. **8영역 접촉 0.** 새 leaf `src/engine/status_exit_watch.py` 가 보유 종목을 조회하고, 공개 메서드 `order_engine.execute_sell(ticker, Signal.STATUS_EXIT, strategy_id)` 만 부른다. `scheduler.py` 는 task 1줄 + 이름 3곳만 바뀐다(3,812줄 → 약 3,813줄. 승인 대상). `strategy_base.Signal` 에 `STATUS_EXIT` 1줄을 더한다.
9. **청산 사유 이름 = `Signal.STATUS_EXIT` 하나.** 51·59 구분은 마커의 `reason=managed|overheat` 에 적는다. `trade_history` 에는 사유 칸이 없고 `system_logs` 에는 `[market_op_*]` 가 한 줄도 없다(§2.2). 그래서 발사 기록은 **`write_log` 로 `system_logs` 에 남겨야** 나중에 추적할 수 있다.
10. **급할 이유는 없다.** 2026-09-26 02:19 KST 에 보유 12종목을 전부 조회했더니 해당 종목이 0개였다(§2.3). 09-28 07:45 기한 때문에 검증(전체 스위트·돌연변이)을 줄일 필요는 없다. 다만 09-28 효력 지정이 이 조회값에 이미 반영됐는지는 모른다.

---

## 1. 질문 요약

질문지 7개를 이 문서가 답하는 자리로 이었다: ① 무엇을 발동으로 보나 → §4(a) · ② 언제 확인하나 → §4(a) · ③ 어떻게 파나 → §4(b) · ④ 전략별 예외·사유 이름 → §4(e)·§6 · ⑤ 신규 매수 차단 범위·「재구독 중지」 → §4(c)(d) · ⑥ 크리티컬 분기 → §5 · ⑦ 8영역 최소 설계·관측 1단계 필요성 → §4(f)·§0-1

질문지에서 사실과 다른 곳 넷 (설계에 영향이 있어 먼저 바로잡는다):
- `inquire_ccnl` 은 `FHKST01010**300**`(체결)이다. `FHKST01010**100**`(현재가 시세)을 쓰는 클라이언트는 `quotation.inquire_acml_vol` · `condition.fetch_stock_detail` · `condition.inquire_stock_basics` 다.
- `ssts_hot_yn` 은 **공매도과열**이다. 단기과열이 아니다. 단기과열은 마스터 파일 `short_over_cls_code`(0 해당없음 · 1 예고 · 2 지정 · 3 연장)와 FHKST `short_over_yn` 이다.
- 진입 필터가 보는 것은 master `mang_issu_yn` · master `ssts_hot_yn` · FHKST raw `short_over_yn` 이다. raw `iscd_stat_cls_code` 는 cycle203 에서 기준에서 뺐다.
- FHKST `mang_issu_cls_code` 는 `stock_master.raw` 에 **저장되지 않는다**(`_FHKST_MERGE_KEYS` 에 없음. 3,583행 전부 NULL). 관리 여부는 CTPF1002R `admn_item_yn`(= master `mang_issu_yn`, 207/207 일치)으로만 저장된다.

---

## 2. 실측

### 2.1 코드 (읽기 전용, HEAD `b8b06d7`)

| 무엇 | 사실 | 위치 |
|---|---|---|
| 51·59 를 판정·소비하는 곳 | **없다.** `ISCD_STAT_BLOCKING={"58"}` 이고 51·59 는 표시 집합 `_ISCD_STAT_DISPLAY_CODES` 에만 있다 | `src/api/market_operation.py` · `src/engine/market_operation_monitor.py` |
| `H0UNMKO0` 구독 대상 | 보유 + 익일청산(HIGH)만 | `market_op_subscribe.py:33-35` |
| 진입 필터 | master 7건 + FHKST raw 4건. **보유·익일청산은 무조건 통과**(`protected_tickers`). 5전략은 `apply_master_block_filter`, momentum 은 `scan_stocks` 안에서 거른다 | `scanner.py:3578-3706`, `:1280-1293` |
| `stock_master` 갱신 | raw(CTPF+FHKST) 는 매일 **16:10~16:24** 에 전 종목 3,583행을 갱신한다. `master_raw` 는 **16:30** 에 마스터 파일로 갱신한다. 둘 다 저녁 1회다 | DB `refreshed_at` 09-23 07:10~07:24 UTC · `master_raw_updated_at` 07:30 UTC |
| FHKST 를 이미 부르는 주기 경로 | `_run_swing_rest_poll_once`(60초, **donchian·kojiro 한정**, 09:05/09:30~15:20)가 `fetch_stock_detail` 로 **전체 output**(전용 플래그 포함)을 받는다. 다른 5전략의 보유 종목은 주기 조회가 없다 | `scheduler.py:2835-2946`, `:145` |
| `fetch_stock_detail` | 5초 TTL 캐시 + 단일 비행. 시세 풀 경유. 전체 output dict 를 반환한다 | `condition.py:465-535` |
| `execute_sell(ticker, signal, strategy_id, *, limit_price=0)` | `_selling` 중복 차단 → 거부 추적기 게이트 → 거래소 결정(09:00~20:00 은 NXT/SOR 기반도 `krx_by_clock` 으로 **KRX**) → 15:30~16:00 휴식 게이트 → 프리장 지정가 사전 변환 → 애프터 44/41 변환(실전) → 3회 재시도 · APBK1943 지정가 5호가 폴백 · APBK0918 포지션 보존. `signal` 은 **로그 문자열로만** 쓰인다 | `order_engine.py:1619-2322` · `risk.py:702` |
| 외부 호출 선례 | `scheduler._drain_pending_next_day_clear`(`Signal.NEXT_DAY_CLEAR`) · `_force_clear_main_only`(`Signal.FORCE_CLEAR`)가 `execute_sell` 을 직접 부른다 | `scheduler.py:1580`, `:2039` |
| 매수 통합 차단 | 보유 ∨ 매수 주문 중 ∨ **당일 매도** 중 하나면 차단(전 전략 순회) | `strategy_registry.py:86-98` |
| 매도 체결 뒤 구독 정리 | 다른 전략 보유·익일청산 대기·다른 전략 스캔 후보가 모두 없을 때만 구독을 해제한다 | `order_engine.py:2440-2480` |
| stale `_selling` 정리 | 보유 잔존 ∧ **열린 매도 주문 없음** ∧ 180초 경과일 때만 해제한다. 열린 주문이 있으면 유지 = 30분 단일가 대기와 충돌 없음 | `selling_reconcile.py:90-148` |

### 2.2 운영 DB·로그 (EC2 컨테이너 asyncpg, 읽기 전용)

**종목상태 분포 — `stock_master` 스냅샷 09-23 16:10~16:30 KST, 3,583행**

| 항목 | 값 |
|---|---|
| 관리종목(`mang_issu_yn=Y` = `admn_item_yn=Y`) | **207** (두 소스 207/207 일치) |
| 그 207 의 `iscd_stat_cls_code` | **51: 100 · 58: 82 · 00: 24 · 59: 1** → 51 만 보면 관리의 **48%만** 잡힌다 |
| `iscd=51` 전체 | 100 — **전부 관리종목**(51 에는 오탐이 없다) |
| 단기과열 master `short_over_cls_code` | 0: 3,552 · **1(예고): 21** · 2(지정): 1 · 3(연장): 9 |
| FHKST `short_over_yn=Y` | **10** = 코드 2·3 과 10/10 일치 = `iscd=59` 10/10 일치. 예고(1) 21건은 전부 `N` |
| 공매도과열 `ssts_hot_yn=Y` | 8 (단기과열과 별개) |

**과거 보유 종목** — `trade_history` 체결 698행 · 203종목 · 2026-04-22~09-23

- 09-23 스냅샷 기준으로 관리 0 · 단기과열 지정·연장 0 · **단기과열 예고 3**(356680 엑스게이트 BFB·momentum ~09-23 · 032820 우리기술 donchian 09-10~14 · 072950 빛샘전자 momentum 05-07~08) · 투자경고(53) 4(078350 한양디지텍 LTV 09-21 등) · 투자주의(54) 2.
- ⚠️ **「보유 중에 51·59 로 지정된 적이 있는가」는 알 수 없다.** 종목상태 이력 테이블이 없고 스냅샷만 있다. `system_logs`(08-24~09-25, 34,306행)에 「단기과열」·「관리종목」 문자열이 0행이고, `[market_op_*]` 접두도 0행이다. 장운영 마커는 파일 로그에만 있다.
- 간접 증거 — 우리 전략은 이 사건이 나는 종목군을 산다. 032820 우리기술은 2024-05-23 에 단기과열로 지정된 이력이 있다(KIND 공시 검색 결과). 지금은 예고 상태이고 우리가 09-10~14 에 보유했다.

**진입 필터 차단 표본** — `strategy_funnel_snapshots.excluded_sample`(종목당 상한 20이라 하한값)

- 단기과열(`short_over_yn`) **7종목**(08-12~09-23) · 관리(`mang_issu_yn`) **4종목** · 공매도과열(`ssts_hot_yn`) **96종목**(보유 중인 035760 CJ ENM 포함).

**`H0UNMKO0` 프레임** — EC2 `~/auto_stock/logs/auto_stock.log.2026-09-10`~`09-24` + 현재 파일, `grep "MKO0\] tr_key="`

- **31건, 종목상태 칸 55×21 · 57×10. 51·58·59 는 0건.** 51·59 가 프레임으로 온 적이 이 기간에 한 번도 없다. 그래서 프레임이 지정을 알려 주는지는 실측된 적이 없다.

**보유 기간 중앙값**(매수→다음 매도 근사): VB 0.25일 · LTV 0.18 · momentum 0.97 · donchian 3.0 · BFB 3.0 · **kojiro 13.5**(최대 33). 노출이 가장 긴 것은 kojiro 이지만 대형주라 단기과열 확률은 낮다. 확률이 높은 것은 momentum·BFB·LTV(급등 소형주)다.

### 2.3 라이브 FHKST01010100 확인 (2026-09-26 02:1x KST, 컨테이너 안 `kis_get`, 메인 토큰 유효 확인 뒤 발급 없이 20건)

| 종목 | 기대 | `iscd` | `mang_issu_cls_code` | `short_over_yn` | `temp_stop_yn` |
|---|---|---|---|---|---|
| 294140 | 관리 | 51 | **Y** | N | N |
| 016790 | 관리+정지 | **58** | **Y** | N | N |
| 043090 | 관리(iscd 00) | 00 | **None** (다른 칸도 None, 현재가 0) | N | N |
| 005160 | 단기과열 지정 | 59 | N | **Y** | N |
| 000545 | 단기과열 연장 | 59 | N | **Y** | N |
| 356680 | 단기과열 **예고** | 57 | N | **N** | N |
| 005930 | 정상 | 55 | N | N | N |
| 보유 12종목 전부 | — | 54·55·57 | N | N | N |

→ 플래그는 `Y`/`N` 대문자 한 글자다. 예고는 `N` 이다. 거래정지가 겹쳐도 관리 플래그는 살아 있다. **응답 칸이 `None` 으로 오는 종목이 있다** — 이것은 「모름」이지 「해당 없음」이 아니다.

### 2.4 마스터 파일 갱신 시각 (같은 시각, HEAD 요청 + 파싱 대조)

- `kospi_code.mst.zip`·`kosdaq_code.mst.zip` Last-Modified = **2026-09-25 18:55 KST**(휴장일에도 저녁에 다시 만든다).
- 파일 내용은 DB 09-23 16:30 적재분과 4플래그 모두 **차이 0**(대조 3,545종목).
- 즉 우리 16:30 적재는 **전날 저녁 파일**을 받는다. 그 파일이 「다음 거래일 상태」를 담는지는 이번에 판별하지 못했다(§9 후속 ③).

### 2.5 제도 (외부 — KRX 규정/KIND 원문, `insane-search`)

- **단기과열종목**([KRX 규정 — 단기과열완화제도](https://regulation.krx.co.kr/contents/RGL/03/03010408/RGL03010408.jsp)):
  - 예고 뒤 10거래일 안에 요건을 **종가 기준**으로 다시 충족하면 **그 다음 매매거래일부터** 지정한다.
  - 지정되면 **3거래일간 정규시장이 30분 단위 단일가**가 된다(09:00 부터 30분마다 체결).
  - 넣을 수 있는 호가는 **지정가·시장가·경쟁대량만**이다. IOC·FOK 는 금지다.
  - 🔴 **「애프터마켓 거래대상종목에서 제외」.**
  - 종료일 종가가 지정일 전일 대비 20% 이상 오르면 3거래일 연장(1회)한다. 종류주식 괴리율 요건이면 반복 연장한다.
- KIND 공시 예시([지정](https://kind.krx.co.kr/external/2025/12/24/000881/20251224002194/70725.htm)): 2025-12-24 공시 → **지정일 2025-12-26**(다음 거래일) · 「지정일 포함 3거래일」 · 「단일가매매 기간 중 거래정지시 정지일수도 기간에 포함」 · 「지정기간 종료시 별도의 시장안내는 없음」. [예고](https://kind.krx.co.kr/external/2025/04/07/001039/20250407002301/99427.htm): 「투자경고·투자위험(익일 지정예정 포함) 종목은 요건 미적용」.
- **관리종목**([찾기쉬운 생활법령 — 관리종목 지정](https://easylaw.go.kr/CSP/CnpClsMain.laf?popMenu=ov&csmSeq=1701&ccfNo=1&cciNo=2&cnpClsNo=2)):
  - 사유는 정기보고서 미제출·감사의견·자본잠식 50%·회생절차개시신청·공시벌점 등이다.
  - 지정되면 **「매매거래가 정지될 수 있다」**(상장규정 제153조). 신용거래·대용증권은 금지된다.
  - 단일가 전환 규정은 **찾지 못했다** → 정규장 **접속매매**로 본다(추정).
- 애프터마켓(16:00~20:00, 09-14 시행) 제외 대상에 「관리·투자경고·초저유동성·정리매매」가 들어 있다고 보도됐다([국제뉴스](https://www.gukjenews.com/news/articleView.html?idxno=3693609)). 관리 제외는 **보도 수준**이고 1차 원문은 확인하지 못했다.

---

## 3. 트레이더 시각

**시장 가설.**
- 단기과열 지정은 40일 평균 대비 +30% 급등 · 회전율 6배 · 변동성 1.5배가 **두 번** 겹쳐야 나온다. 추세의 끝물 신호에 가깝다.
- 지정되면 연속매매가 사라진다. 그래서 데이트레이더와 알고리즘이 빠지고, NXT·애프터 유동성도 빠진다.
- 우리 전략의 손절·트레일링은 **틱 기반**이다. 30분 단일가에서는 신호가 30분마다 한 번 뜨고, 체결은 **그다음 30분 뒤**에 난다. 손절이 사실상 두 박자 늦는다. 그래서 보유를 이어 가는 것이 청산보다 나쁘다.
- 관리종목은 신용이 금지돼 기존 신용 물량의 반대매매가 나오고, 기관 편입도 불가해진다. 상폐 경로의 입구다.
- → 둘 다 **「가설이 깨진 종목」** 이다. 사용자 결정은 현장 본능과 같다.

**위험 시나리오.**
1. 거래 재개 첫 단일가에 시장가로 던지면 **그날 최악 가격**(하한가 근처)에 체결될 수 있다. 관리 지정은 회생신청처럼 정지(58)와 함께 오는 경우가 많다.
   - 우리 랏은 1~10주, 수십만 원이다. 가격 손해는 작고, 「내일 더 떨어질」 꼬리 위험을 끊는 편이 낫다.
   - 하한가 매도잔량에 막혀 체결이 안 되면 주문은 호가에 남는다. 그다음은 `selling_reconcile` 이 유지하거나 다음 날 다시 판다.
2. 단기과열 지정 첫날(T+1)의 09:00 시가 단일가를 놓치면 09:30 단일가까지 30분을 더 들고 간다(§4(b) 표 아래 「선택지」).
3. 연속 상한가를 타는 LTV 보유가 지정되면 「상한가 추종」을 포기하게 된다(§6 반례). 다만 연속 상한가 종목은 보통 **투자경고**가 먼저 걸리고, 투자경고 종목에는 단기과열 요건이 적용되지 않는다(KIND 예고 원문). 그래서 겹치는 경우는 적다.

---

## 4. 설계 권고

### (a) 감지 소스와 시점

- **판정 소스 = REST `FHKST01010100` 한 개**(`condition.fetch_stock_detail`, 시세 풀·5초 캐시). 규칙은 아래와 같다.
  ```
  managed  = mang_issu_cls_code == "Y"  or iscd_stat_cls_code == "51"
  overheat = short_over_yn      == "Y"  or iscd_stat_cls_code == "59"
  halted   = iscd_stat_cls_code == "58" or temp_stop_yn == "Y"
  unknown  = 응답 실패 · output 비어 있음 · stck_prpr 가 0/비숫자 · 전용 플래그 둘 다 None
  ```
  - 정확일치만 인정한다(`.strip().upper()` 뒤 `== "Y"`). 규칙에 없는 값은 **무시하고** `[status_exit_unknown_value]` 를 남긴다.
  - `iscd` 51/59 를 OR 로 넣는 근거: 실측에서 51→관리 100/100, 59↔`short_over_yn=Y` 10/10 이라 새 오탐이 없다. 전용 플래그가 None 일 때 대신 쓸 수 있다.
- **소스로 쓰지 않는 것**:
  - `ssts_hot_yn`(공매도과열).
  - master `short_over_cls_code == "1"`(예고).
  - `stock_master.raw`/`master_raw` DB 값 — 하루 늦는다. 해제된 종목을 팔 수 있다.
  - `H0UNMKO0` 프레임 단독.
- **프레임은 힌트로만 쓴다.** 조회 때 `market_operation_monitor.get_last_event(t)` 를 **읽기만** 해서 51/59 면 `[status_exit_frame_hint]` 를 남긴다. 프레임이 지정을 실어 오는지는 한 번도 실측된 적이 없어서 이 로그로 배운다. `market_operation_monitor` 에 리스너를 다는 수정은 하지 않는다(sha 핀 1곳 + 파서가 어제 고쳐졌다).
- **대상 = `registry.all()` 의 모든 전략 `state.positions`**(꺼진 전략 포함). `risk.on_tick` 은 켜진 전략만 돌아서 꺼진 전략의 보유는 아무도 안 본다. 51·59 청산은 위험을 줄이는 방향이라 포함한다.
- **조회 일정**:
  - **08:45**: 1회. 대기 등록(arm)과 로그만 한다.
  - **09:00:30 정각**: 1회. 첫 발사 기회다.
  - **그 뒤 300초마다 15:28 까지**.
  - 재시작하면 즉시 1회 돌고 일정에 합류한다.
  - 비용 ≈ 보유 12 × 약 79회 ≈ **하루 950콜**. donchian·kojiro 60초 폴의 일부와 5초 캐시로 겹친다.
- **확인 두 번**: 발사는 **09:00:30 이후 창 안에서 읽은 값**으로만 한다. 08:45 조회나 프레임으로 걸린 대기 항목은 창 안에서 다시 읽어 여전히 해당될 때만 판다.
  - 장 전 KIS 상태가 전날 값일 수 있다. 그러면 해제일 아침에 팔거나 지정일 아침에 놓칠 수 있다. 이 가능성을 양방향으로 막는다.
  - 다시 읽었더니 풀렸으면 `[status_exit_disarmed]` 를 남긴다.

### (b) 청산 방법 — 시간대별

| KST | 51 관리(접속매매) | 59 단기과열(30분 단일가) | 조치 |
|---|---|---|---|
| 07:45~09:00:30 (NXT 프리 · KRX 시가단일가) | arm | arm | **주문 안 냄.** 이유 셋. ① `execute_sell` 이 NXT 거래 종목을 프리장 NXT 지정가 `step_down(5)` 로 바꾼다. ② NXT 가 단일가 지정 종목을 받는지 모른다. ③ 프리 지정가 미체결이 `_selling` 을 붙잡던 이력이 있다(scheduler Tier 1 주석) |
| 09:00:30~15:20 | 시장가 → 즉시 체결 | 시장가 → **다음 :00/:30 단일가에 체결**(최대 30분) | **발사** `execute_sell(t, Signal.STATUS_EXIT, sid)` (지정가 인자 없음 = 시장가, KRX) |
| 15:20~15:28 | 시장가 → 15:30 종가단일가 | 같음 | 발사 |
| 15:28~16:00 | — | — | arm. 15:30~16:00 은 `_market_rest_gate` 가 어차피 막는다 |
| 16:00~20:00 (KRX 애프터) | 🔴 애프터 제외(보도) | 🔴 **애프터 제외(KRX 원문)** | **주문 안 냄** → 다음 영업일 09:00:30. 내면 44/41 거부 → `_after_exit_fails` → 포기 래치 + CRITICAL |
| 20:00~ | — | — | 루프 종료 |
| 정지(58·임시정지)와 겹침 | 대기 | 대기 | `[status_exit_wait_halt]` 1회/일. 다음 조회에서 풀리면 발사 |

- **APBK1943(시장가 불가)** → 기존 지정가 5호가 폴백. 단일가에서도 지정가는 허용된다.
- **APBK0918(장운영시간 외)** → 기존 5분 TTL. 다음 조회에서 다시 쏜다(아래 상한 안에서).
- **발사 상한**: 종목당 하루 **3회**. 조회 간격(≥300초)이 자연 간격이다. 초과하면 `[status_exit_giveup]` CRITICAL 1회/일을 남기고 다음 날 다시 시작한다. 카운터를 `(ticker, 날짜)` 로 두면 `_reset_daily_state` 에 손댈 필요가 없다.
- 이미 `order_engine._selling` 에 있으면 발사를 건너뛴다(읽기만. `execute_sell` 도 스스로 막지만 로그를 깨끗하게 하려는 것이다).
- **선택지(이번 범위 밖)** — 59 지정일에 **09:00 시가 단일가로 파는 것**. 이렇게 하면 30분을 줄인다. 필요한 것은 ① 08:5x KRX 시가단일가에 시장가를 넣는 경로(NXT 기반 종목은 지금 라우터가 프리장에서 NXT 로 보낸다) ② 장 전 FHKST 가 그날 상태를 보여 준다는 실측(§9 ②). 둘이 확인되면 별도 사이클로 한다.

### (c) 신규 매수 차단 — 범위와 기간

| 대상 | 기간 | 장치 | 새 코드 |
|---|---|---|---|
| 판 종목(보유했던 51/59) · 청산 주문 대기 중 | 주문~체결 | `has_position` | 없음 |
| 판 종목 · 당일 | 체결~21:30 | `is_sold_today` (전 전략) | 없음 |
| 판 종목 · 다음 날부터 | 59: 지정 해제 **+1일** · 51: 해제까지 | 진입 필터. 59 = raw `short_over_yn`(16:10 갱신) · 51 = master `mang_issu_yn`(16:30) | 없음 |
| 🔴 **보유하지 않은 후보 · 지정 첫날(T+1)** | T+1 하루 | **없음** — T일 16:10 raw 는 아직 지정 전이라 T+1 아침 준비를 통과한다 | §8 질문 |

- 새 차단 목록(TTL·DB)은 두지 않는다. 이미 있는 두 장치가 하루도 빈틈 없이 이어진다. 단, 지정 해제 뒤 하루 더 막히는 것은 보수적이라 괜찮다.
- 첫날 빈틈의 부작용: 후보가 T+1 에 매수되면 다음 조회에서 이 기능이 곧바로 판다(30분 단일가 두 번 = 왕복 비용). **그 사건은 `[status_exit_fire] ... bought_today=1` 로 보이게 한다**. 몇 번 나는지부터 세고 나서 B/C 를 고르는 것이 순서다.

### (d) 「재구독 중지」 해석

- **보유 종목의 구독은 절대 건드리지 않는다.** 청산 주문이 거부·만료되면 그 포지션은 다시 손절이 필요하다. 끊으면 WS 로는 안 보인다(donchian·kojiro 만 REST 폴이 있다). HIGH 구독 보호(`bypass_limit`)를 우회하는 코드 자체를 만들지 않는다.
- 체결 뒤 해제는 **이미 있다**(`_unsubscribe_if_no_other_strategy`). 다른 전략의 스캔 후보면 남지만 `is_sold_today` 때문에 못 산다. 슬롯 하나를 쓸 뿐이다.
- 청산을 기다리는 동안(최대 30분) 59 종목은 체결이 30분마다라 **stale 로 보인다**. 그래서 K watcher·5분 우선 재구독이 HIGH 재등록 SEND 를 낸다. 이미 있는 상한(시간당 6회)이 묶는다. cycle359 §7-4 의 권고(「59 를 stale skip 에 넣지 않음」)를 **그대로 유지**한다. 보유 보호가 우선이다.
- 사용자에게 할 설명: 「재구독을 끊는 것으로는 매수가 멈추지 않는다(스윙 두 전략은 REST 로 사고, 5분 스캔이 후보를 다시 구독한다). 매수를 멈추는 것은 당일 매도 차단과 진입 필터다. 그리고 보유 중에 끊으면 손절이 눈을 감는다.」

### (e) 청산 사유 이름

| 안 | 내용 | 평가 |
|---|---|---|
| **(가) `Signal.STATUS_EXIT` 하나 + 마커 `reason=managed\|overheat\|managed+overheat`** ← 권고 | 「종목상태(ISCD_STAT)」 원인. cycle367 카드 4-1 의 `TIME_EXIT`·`TAKE_PROFIT`·`TREND_EXIT` 와 같은 `<원인>_EXIT` 모양 | 이 사이클에서 `scheduler.py` 를 건드리므로 `_BASE_SHA`(8영역·scheduler·strategy_base·전략 7파일을 묶은 sha) 재핀이 어차피 생긴다 → 추가 비용 ≈ 0. E7(cycle367 세 이름)은 그 뒤에 이어 붙인다(append-only) |
| (나) `MANAGED_EXIT`·`OVERHEAT_EXIT` 두 값 | 로그만 봐도 원인이 보인다 | enum 이 늘고 cycle367 원칙(원인당 하나)보다 잘다 |
| (다) 기존 `FORCE_CLEAR` 재사용 | 재핀 회피 | 재핀 회피 효과 없음(위 이유) + cycle367 이 고치는 「표기 ≠ 실제」 를 새로 만든다 → 기각 |

`signal.value` 는 로그에만 쓰인다(`order_engine.py:1852`·`:2320`). `trade_history` 에는 사유 칸이 없다. 그래서 **발사 사실은 (h) 마커로 `system_logs` 에 남기는 것이 유일한 영속 기록**이다.

### (f) 8영역 접촉 최소화

| 파일 | 변경 | 분류 |
|---|---|---|
| `src/engine/status_exit_watch.py` (신규 leaf) | 분류 순수함수 · 창 판정 · 조회 루프 `task_loop(sched)` · 발사 | 비8영역. `test_cycle287_ast_scope.py::test_s1b` 의 `_SRC_TREE_FILES`·`_SRC_TREE_DIGEST` 갱신 |
| `src/engine/strategy_base.py` | `Signal.STATUS_EXIT = "STATUS_EXIT"` 1줄 | 비8영역. `_BASE_SHA` 계열 재핀 |
| `src/engine/scheduler.py` | `start()` 에 `self._status_exit_task = asyncio.create_task(status_exit_watch.task_loop(self))` 1줄 + task 이름 3개 튜플(`:1039`·`:1166`·`:1202` 자리) | **승인 대상**(라인 상한 규칙). 3,812 → 약 3,813 |
| `src/db/system_config.py` | `get_status_exit_mode()` | 비8영역 |
| `src/routes/system_integrations.py` | `GET/PUT .../status-exit` (`/buy-block` 모양) | 비8영역. 킬스위치를 즉시 반영하려면 필요 |
| `order_engine.py` · `risk.py` · `strategy_registry.py` · `session.py` · `scanner.py` · `src/realtime/**` · `src/auth/**` · `market_operation_monitor.py` · `market_operation.py` | **0** | — |

- leaf 가 `sched` 에서 읽는 것: `registry` · `order_engine`(공개 메서드 `execute_sell` + `_selling` 읽기) · `_running` · `_wait_until`. 선례는 `open_price_rest.main_rest_basis_task_loop(sched)` 다.
- 기각한 대안 — `boot_manager` 에서 task 를 만드는 것. `run_daily` 가 영업일마다 `start()` 를 다시 부르므로 cancel 목록 밖의 task 가 하루 하나씩 쌓인다(G-AST2 task_attrs 규약 위반).
- 매매 행위를 바꾸는 변경이라 **파일 위치와 무관하게 승인 대상**이다(루트 CLAUDE.md 「여전히 승인이 필요한 것」). 사용자 결정은 이미 있다. 이 명세(§4)를 승인받는 형식으로 진행한다.

### (g) 킬스위치

- `system_config.status_exit_mode` ∈ `enforce` | `observe` | `off`. **매 조회마다 읽는다**(PUT 은 즉시 반영, SQL UPDATE 도 다음 조회에 반영).
  - **키 없음 → `enforce`**. 사용자가 결정했다. ρ축 「키 부재=OFF」와 반대인데, 그쪽은 매수를 **막는** 통제이고 이쪽은 위험 종목을 **파는** 통제라서다.
  - **알 수 없는 값 → `observe`**. 팔지 않고 `[status_exit_would_fire]` 만 남긴다.
  - **DB 조회 실패 → 직전 값 유지**. 처음이면 `enforce`.
- `observe` 는 「판정만 찍고 안 판다」, `off` 는 「조회도 안 한다」 이다.
- 롤백 = PUT `observe`/`off`(재시작 없음) · 코드 롤백 = 커밋 revert(full 배포).

### (h) 관측 마커

| 마커 | 레벨·경로 | 상한 | 필드 |
|---|---|---|---|
| `[status_exit_armed]` | INFO logger | 종목·사유별 1회/일 | `ticker= strategy= reason= iscd= mang= short_over= src=rest\|frame at=` |
| `[status_exit_disarmed]` | INFO | 1회/일 | 창 안 재조회에서 풀림 |
| `[status_exit_fire]` | **WARNING `write_log`**(system_logs 영속) | 발사마다(하루 최대 3) | `ticker= strategy= reason= iscd= mang= short_over= qty= mode=enforce attempt=n bought_today=0\|1` |
| `[status_exit_would_fire]` | WARNING `write_log` | 1회/일 | observe 모드 |
| `[status_exit_wait_halt]` | INFO | 1회/일 | `iscd=58\|temp_stop` |
| `[status_exit_unknown]` · `[status_exit_unknown_value]` | INFO | 1회/일 | 응답 None · 규칙 밖 값 원문 |
| `[status_exit_frame_hint]` | INFO | 1회/일 | 마지막 `H0UNMKO0` 이벤트의 종목상태 51/59 |
| `[status_exit_giveup]` | CRITICAL `write_log` | 1회/일 | `fires=3` |
| `[status_exit_summary]` | INFO | 조회마다 | `held= checked= flagged= fired= halted= unknown= fetch_fail= mode=` |

`DailyEmitCap`(`src/engine/daily_emit_cap.py`) 재사용. 관측 실패는 흡수하고 발사 결정에 영향을 주지 않는다.

### (i) 테스트 시나리오 (tdd-engineer 에게)

**A. 분류 (순수함수, §2.3 실측 응답을 그대로 픽스처로)**
- A1 294140 → managed · A2 016790 → managed + halted(발사 금지) · A3 005160·000545 → overheat
- A4 356680 예고 → 없음 · A5 043090 None 응답 → unknown(없음 처리 금지·발사 금지)
- A6 `ssts_hot_yn=Y` 만 있는 합성 응답 → 없음 · A7 iscd 52/53/54/55/57/00 → 없음
- A8 `"y"`·`" Y "` 정규화 → Y · A9 규칙 밖 값(`"1"`) → 무시 + unknown_value · A10 managed+overheat 동시 → reason 합성

**B. 시각 창 (freezegun, 경계 양쪽 — `feedback_time_window_gate_tests`)**
- B1 08:59:59 해당 → execute_sell 0회, armed 1
- B2 09:00:29 → 0회 / 09:00:30 창 안 재조회 → 1회
- B3 15:27:59 → 1회 / 15:28:00 → 0회
- B4 16:30(`is_production=True`) → 0회 · B5 07:50·20:30 → 0회

**C. 확인 두 번**
- C1 08:45 해당 → 09:00:30 재조회 해제 → 0회 + disarmed
- C2 프레임 59 인데 REST `N` → 0회 · C3 REST 예외 → 0회, 다음 조회에서 재시도

**D. 발사 계약**
- D1 인자 = `(ticker, Signal.STATUS_EXIT, strategy_id)` 이고 `limit_price` 없음(시장가)
- D2 꺼진 전략 보유도 대상 · D3 포지션 없음 → skip · D4 `_selling` 안 → skip
- D5 하루 3회 상한 → 4번째 조회 0회 + giveup CRITICAL 1회 · D6 날짜 바뀌면 카운터 새로
- D7 halted → 0회 + wait_halt, 다음 조회에서 풀리면 1회

**E. 모드**
- E1 off → FHKST 0콜 · E2 observe → would_fire, execute_sell 0회
- E3 알 수 없는 값 → observe · E4 DB 예외 → 직전 값 · E5 키 없음 → enforce

**F. 비간섭 (AST/구조)**
- F1 leaf 가 `src.realtime`·unsubscribe 계열을 import·호출하지 않음
- F2 leaf 가 `order_engine` 에서 부르는 것은 `execute_sell` 과 `_selling` 읽기뿐
- F3 8영역 sha 불변 · F4 DB 쓰기는 `write_log` 뿐
- F5 **양성 대조군** — 분류가 managed 를 내는 픽스처에서 발사가 실제로 일어남(부정 단언만 있으면 본체가 사라져도 초록)

**G. 통합 (실제 `execute_sell` + place_order 모의)**
- G1 10:05 59 종목 → ORD_DVSN `01` · 거래소 KRX(NXT 기반 종목 포함, `krx_by_clock`)
- G2 APBK1943 → 지정가 5호가 폴백 1회 · G3 APBK0918 → 포지션 보존, 다음 조회에서 재발사(상한 안)

**H. 재매수 (회귀)**
- H1 체결 뒤 같은 날 `is_ticker_blocked_for_buy` True
- H2 다음 날 prepare 에서 raw `short_over_yn=Y` 종목 제외 · master `mang_issu_yn=Y` 종목 제외(기존 테스트 존재 확인, 없으면 추가)

**I. 돌연변이 (최소)**
- 창 경계 한 칸 이동 · `== "Y"` → `!= "N"`(None 오탐) · 예고 포함(`short_over_cls_code != "0"`) · `ssts_hot_yn` 포함 · halt 무시 · 재조회 생략 → 전부 죽어야 한다

---

## 5. 크리티컬 분기 (오탐 매도 · 원문 충돌 · 시간대 함정)

| # | 분기 | 틀리면 | 막는 것 |
|---|---|---|---|
| K1 | 🔴 **공매도과열(`ssts_hot_yn`)을 단기과열로 읽음** — 질문지가 그렇게 적었다 | 공매도 1일 금지일 뿐인 종목을 시장가로 던진다. 표본만 96종목이고, **보유 중인 035760 CJ ENM(kojiro)** 도 차단 이력이 있다 | (a) 규칙에서 제외 + 돌연변이 I |
| K2 | 🔴 **단기과열 예고(코드 1)를 지정으로 읽음** | 09-23 기준 예고 21 > 지정 10. 우리가 거래한 3종목(356680·032820·072950)이 예고다 | `short_over_yn`(예고=N 실측) 사용, master 코드 금지 |
| K3 | 🔴 **종목상태 51 단독 판정** | 관리 207 중 107을 놓친다(58·00·59 로 가려짐) — 관리+정지 종목이 풀리는 날 못 판다 | 전용 플래그 `mang_issu_cls_code` 우선 |
| K4 | 🔴 **애프터마켓(16:00~20:00)에 발사** | 59 는 애프터 거래대상 제외(KRX 원문), 관리도 제외(보도) → 44·41 연속 거부 → `_after_exit_fails` 포기 래치 + CRITICAL + 익일청산 큐 오염 | 창 09:00:30~15:28 한정 |
| K5 | **장 전(07:45~09:00) 값으로 발사** | 전날 상태로 해제일에 팔거나, 프리장 NXT 지정가 변환으로 미체결 | arm 만, 창 안 재조회로 발사 |
| K6 | **REST `None` 을 「해당 없음」 또는 「해제」로 읽음** | 043090 실측처럼 칸이 비어 오는 종목 — 판정 오류·대기 항목 조기 해제 | unknown 3상태 분리 |
| K7 | **「재구독 중지」 를 보유 종목에 적용** | 청산 거부 시 손절 무감시(WS blind) | 보유·HIGH 구독 무접촉(F1) |
| K8 | **정지(58)와 겹쳐 반복 발사** | 3회 재시도 × 조회마다 → CRITICAL 「매도 주문 최종 실패」 폭주 | halted 대기 + 하루 3회 상한 |
| K9 | **30분 단일가 대기를 「실패」로 오판하는 새 타이머 추가** | 대기 주문을 취소·재주문하면 우선순위만 잃는다 | 새 취소 타이머 금지. 기존 `selling_reconcile` 열린 주문 보존에 맡긴다 |
| K10 | **DB 값(`stock_master`)으로 판정** | 16:10 스냅샷이라 하루 늦다 — 해제된 종목을 판다 | 판정 소스는 라이브 REST 만 |
| K11 | **원문 「바로」 와의 차이** — 저녁·장 전 감지는 다음 정규장, 59 는 체결까지 최대 30분 | 사용자가 「바로 안 팔렸다」로 볼 수 있다 | 제도상 강제(애프터 제외·단일가)라 설계로 못 없앤다 → 보고 때 명시 |
| K12 | **원문 「재구독 중지등으로 신규매수를 중단」 과의 차이** — 수단이 다르다 | 사용자가 구독 해제를 기대할 수 있다 | (d) 설명 + 확인 질문 |

---

## 6. 현 코드와의 정합성 · 전략별 예외

- **충돌 없음**: `DEFAULT_PARAMS` · `tradable_boards` · 15:20 일괄청산 · NXT 좀비 차단 · 체결통보 구독 · 주문번호 매핑 · 접수 후 재발사 금지 — 전부 `execute_sell` 안의 기존 규약을 그대로 탄다. 새 코드는 「언제 부를지」만 정한다.
- **VB**: 당일 청산이라 지정(다음 날 효력)과 겹칠 일이 거의 없다. 15:20 강제청산과 같은 틱에 겹치면 `_selling` 이 하나로 합친다.
- **LTV** — 🔴 **`tradable_boards`·프리장 평가 보류 화이트리스트와 무관**(이 기능은 창을 09:00:30 이후로 잡아 프리장 평가를 건드리지 않는다).
  - 반례: 연속 상한가를 타는 「상한가 모드」 보유가 59 로 지정되면 추종을 포기한다. 원문에 전략 예외가 없으므로 **예외를 두지 않는다**.
  - 08:00 `_execute_next_day_clear` 가 트레일링 모드로 둔 종목도 09:00:30 에 판다.
- **kojiro**: 스테이지3 `TRAILING_STOP`(익일 아침)과 같은 아침에 겹치면 먼저 도착한 쪽이 판다. 다른 쪽은 `_selling`/포지션 없음으로 빠진다. 표기는 먼저 쏜 쪽 이름이 된다.
- **donchian·kojiro 60초 REST 폴**: 59 종목에서는 직전 단일가 가격이 반복된다. 손절 평가가 늦어지지만 이 기능이 먼저 판다.
- **익일청산 대기(`_pending_next_day_clear`)와 겹침**: 09:00 drain 과 09:00:30 발사가 같은 종목이면 `_selling` 이 합친다. `_pending_next_day_clear` 를 **재사용하지 않는 이유**: 그 경로는 `Signal.NEXT_DAY_CLEAR` 라벨·DB 영속 테이블·HIGH 구독·거부 분류가 딸려 온다. 또 한 번 쏘면 결과와 무관하게 항목을 지운다(`scheduler.py:1590` `finally` 의 `discard`) — 정지 대기·재시도 규칙이 맞지 않는다.
- **꺼진 전략 보유**: 포함한다(§4(a)). 「보유 전략을 끄지 않는다」 금기의 사각을 조금 줄인다.

---

## 7. 반례 · 한계

- **추세 연장 손실**: 단기과열 지정 뒤에도 오르는 주도주가 있다. 그 꼬리 수익을 포기한다. 우리 표본으로는 크기를 잴 수 없다(지정 이력 없음).
- **거래 재개 단일가 최악가**: 관리 지정 + 정지 뒤 재개 첫 체결은 하한가 근처일 수 있다. 소액 랏이라 받아들인다. 이 규칙은 「가격」이 아니라 「보유를 끊는 것」이 목적이다.
- **「보유 중 지정된 적이 있나」 미해결**: 상태 이력 테이블이 없어 과거 빈도를 모른다. 첫 한 달의 `[status_exit_fire]`·`[status_exit_armed]` 건수가 첫 표본이다.
- **프레임 미실측**: 51·59 가 `H0UNMKO0` 로 온 적이 없다. 그래서 힌트 경로가 쓸모 있는지 모른다(`[status_exit_frame_hint]` 로 잰다).
- **관리종목 애프터 제외는 보도 수준**이다. 어느 쪽이든 애프터에는 쏘지 않으므로 설계는 같다.
- **59 NXT 거래 여부 모름**: 프리장에 쏘지 않으므로 영향 없음. 다만 LTV 의 기존 프리장 청산 평가는 이 종목에서 거부될 수 있다(기존 동작, 이 사이클 범위 밖).

---

## 8. 사용자에게 다시 물을 것

1. **(신규 매수 범위) 보유하지 않은 후보가 지정 첫날 사는 것도 막을까?** 지금 설계는 「판 종목」은 빈틈 없이 막지만, 후보는 지정 둘째 날부터만 막힌다.
   - **A. 지금은 두고 센다** ← 권고. `bought_today=1` 발사 건수를 세고, 한 달 뒤 B/C 를 고른다. 비용 0.
   - **B. 아침 마스터 파일 재적재**(파일 2개로 전 종목 한 번에). 전제 = 전날 저녁 파일이 다음 날 상태를 담는다는 실측(§9 ③). 8영역 무접촉.
   - **C. 매수 직전 REST 확인**. 정확하지만 매수 경로(8영역, 원자성 A-ATOMIC 제약)에 들어간다. 비용이 가장 크다.
2. **(「재구독 중지」 해석) 구독 해제 대신 당일 매도 차단 + 진입 필터로 매수를 막는 것에 동의하는가.** 보유 중 구독 해제는 손절을 끊어서 권하지 않는다(K7).
3. (확인만) **저녁·장 전 감지는 다음 정규장 09:00:30, 59 는 체결까지 최대 30분** — 제도상 강제라는 설명을 보고에 적는다(K11). 되묻기보다는 알림이다.

---

## 9. 후속 검증 권고

| # | 누가 | 무엇 | 언제 |
|---|---|---|---|
| ① | tdd-engineer | §4(i) A~I. 픽스처는 §2.3 실측 응답 원문 | 구현 전 Red |
| ② | tester (읽기 전용) | 첫 거래일에 새로 지정된 종목(KIND 「단기과열종목 지정」 공시) 1개를 골라 **08:00·08:45·09:00:30** 에 FHKST 를 조회한다 → 장 전에 그날 상태가 보이는지 | 첫 지정 사건일 |
| ③ | tester (읽기 전용) | 거래일 **19:00** 에 마스터 파일을 받아 다음 날 09:05 FHKST 와 대조한다(새 예고·지정 종목) → 전날 저녁 파일이 다음 날 상태를 담는지. §8-1 B 의 전제 | 평일 1회 |
| ④ | 운영 | 배포 첫 주 `[status_exit_summary]` 에서 `unknown`·`fetch_fail` 비율. 0 에 가까워야 한다 | D+1~D+5 |
| ⑤ | report-writer | `/sync-docs` — `src/engine/CLAUDE.md` 새 leaf 절 · `strategies/CLAUDE.md` 청산 표 각주 · 루트 CLAUDE.md 안전 규칙 한 줄(「51·59 청산은 KRX 정규장 창만, 보유 구독 무접촉」) · `src/api/CLAUDE.md:264` 「51·59 … 이 모듈에 없다(별도 사이클)」 의 참조를 새 leaf 로 | 커밋 전 |

- 배포 = `src/` 변경이라 **full**(backend 재시작). 창 = 주말 종일 · 평일 21:35~07:45. 보유가 있으면 장중 push 는 금지다(D6).
- 새 파일이 생기므로 영향 인덱스를 다시 만든다(`build_index.py` → `build_index_frontend.mjs`). sha 핀 재핀 뒤에는 **전체 스위트를 다시 돌린다**.

---

## 출처

- 한국거래소 규정/제도 — [단기과열완화제도(유가증권)](https://regulation.krx.co.kr/contents/RGL/03/03010408/RGL03010408.jsp), 2026-09-26 수집
- KIND — [단기과열종목 지정 공시 예](https://kind.krx.co.kr/external/2025/12/24/000881/20251224002194/70725.htm) · [지정예고 공시 예](https://kind.krx.co.kr/external/2025/04/07/001039/20250407002301/99427.htm)
- 찾기쉬운 생활법령정보 — [관리종목 지정 및 상장폐지](https://easylaw.go.kr/CSP/CnpClsMain.laf?popMenu=ov&csmSeq=1701&ccfNo=1&cciNo=2&cnpClsNo=2)
- 국제뉴스 — [애프터마켓 거래대상 종목](https://www.gukjenews.com/news/articleView.html?idxno=3693609) (관리종목 제외는 보도 수준)
- 운영 실측 스크립트(읽기 전용) — 세션 scratchpad `c369/probe1~6.py`
