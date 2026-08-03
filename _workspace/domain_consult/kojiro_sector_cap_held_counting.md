# 자문 — kojiro 섹터/테마 동시보유 캡의 "전일 보유 미집계" 결함 수정 방향

## 질문 요약

kojiro 섹터 캡(`max_positions_per_sector=2`)이 **전일부터 보유한 종목을 동일섹터 카운트에 못 넣는** 잠복 결함. 사용자 "제대로 고치기, 지금 착수" 결정. 도메인 관점 (1) 수정 방향의 매매 타당성, (2) 설계 지뢰, (3) 라이브·FREEZE·N=1 관찰창 타이밍 평가.

정독 완료: `kojiro.py` 전체 + `boot_manager.py` boot 순서 + `scheduler.py`(recompute 호출부 2281 / 장중 재-prepare 701~709 / swing buy poll 2626~) + `order_engine.py` pending/positions 등록 시점 + `git show 37c6ed9`.

---

## 트레이더 시각

### 캡의 의도 (Q1 확정) — "포트폴리오 누적 섹터 노출 상한 (전일 보유 포함)"

도입 커밋 목표가 명문화한다: **"대순환은 섹터 단위 정렬 → 5종목 한 섹터 집중 → 테마 붕괴 시 동시 청산불가(±30% 하한가 락)."** 이 위험은 **보유 시점과 무관**하다. 전일 산 3종목 + 오늘 산 2종목이 같은 섹터면, 테마가 무너질 때 5종목 전부가 동시에 하한가로 락아웃돼 손절이 물리적으로 불가능하다. 따라서 캡이 방어하려는 것은 **당일 아침 몰빵**이 아니라 **포트폴리오에 누적된 섹터 총노출**이다.

지금 코드가 "당일 신선 후보끼리만" 세는 것은 **의도의 축소판(버그)**이지 다른 정책이 아니다. 반증: 전일 같은 섹터 4종목을 이미 들고 있고 오늘 1종목이 그 섹터에서 트리거되면, 현행 로직은 `same=0`(held 미집계) → 5번째를 통과시켜 **한 섹터 5종목** 완성 = 커밋이 막으려던 바로 그 시나리오를 캡이 무력하게 허용한다. 전일 보유를 세는 것이 유일하게 정합적인 해석이다.

### 대순환 알파와 충돌하는가 — 아니오, "의도된 트레이드오프의 집행"이다

대순환 알파 = **강섹터를 며칠~몇 주 지속적으로 올라타기**. 강섹터에선 자연히 여러 종목이 동시에 스테이지1(6→1 신선) 트리거 → 후보가 한 섹터에 몰린다. 여기서 캡은 "이미 그 섹터에 2유닛 노출됐으면 3번째는 참아라"라고 말한다.

- **캡이 알파를 훼손하지 않는 논거**: 강섹터 2종목을 이미 탄 상태 = 이미 그 테마의 상승을 포착 중이다. 3번째 추가는 상승 여력이 아니라 **꼬리위험(테마 역전 시 동시 락)**을 늘린다. KR ±30% 환경에서 동시 청산불가는 계좌를 한 방에 훼손한다. 커밋이 명시적으로 수용한 트레이드오프다.
- **반례(캡이 손해 보는 시나리오)**: 무너지지 않고 3~4주 지속되는 진짜 강한 대순환에서 한 섹터 4~5종목을 들었다면 수익이 극대화됐을 것이다. 이 경우 cap=2 는 최강 테마의 상단을 스스로 자른다. **그러나 이건 "카운팅을 고칠지"가 아니라 "cap 값을 올릴지(2→3)"의 문제다.** 전일 보유를 세는 것 자체는 명백히 옳고, 노출 깊이를 더 허용하고 싶으면 레버는 **cap 값**이지 **카운팅 로직의 버그**가 아니다. (스코프 Q6 참조)

### 라이브 실증과 근본 원인 (관측 5종목 전부 부재의 진짜 이유)

team-lead 가 지목한 held-refill(361~367) sector 누락은 **원인의 일부**일 뿐이다. 코드를 파보니 held 가 `_candidates` 에서 **완전 부재**하는 경로가 더 지배적이다:

1. **ATR 밴드 이탈**: prepare 루프에서 band 필터(332~340, ATR/종가 ∉[1%,6%])가 held-refill(361)보다 **앞**에 있어 `continue` 로 탈락 → held-refill 도달 못 함. 대순환 보유주는 "질서정연한 저변동 추세"라 며칠 홀딩하면 변동성이 압축돼 **ATR/종가 < 1%** 로 자주 떨어진다 → held 소멸. (kojiro 의 알파 자체가 저변동 추세라 이 경로가 흔하다)
2. **유니버스 컷 이탈**: `_scan_universe` 의 `list_by_filter(min_market_cap/min_trade_amount)` 는 **held 를 보호하지 않는다**(`_apply_price_filter`/`_apply_master_block` 만 보유 보호). 보유주 거래대금이 컷 아래로 마르면 유니버스에서 통째로 빠짐 → `_candidates` 부재.
3. **stage None**(EMA 동가, 346~350)도 held-refill 앞에서 탈락.
4. held-refill 이 발화해도 sector 미저장(team-lead 지적).

즉 라이브 5종목 전부 부재는 (1)(2)가 주범이다. **이것이 수정안 선택의 결정타**: held-refill 에 sector 만 채워 넣는 방식(안 B)은 held 가 `_candidates` 에 **존재할 때만** 작동하므로 (1)(2)를 못 고친다. **held 를 `_candidates` 와 독립된 영속 맵에 기록**해야만 밴드/유니버스 이탈 held 까지 집계된다.

---

## 정량 권고 — 3안 정렬

### 안 A (채택 권고) — `_position_sectors` 영속 맵 (team-lead 제안 + 보강)

신규 `self._position_sectors: dict[str, str]` — `_candidates` 와이프에서 **독립**, 포지션 수명 동안 생존.

**stamp 3지점 (전부 kojiro 내부 — order_engine 무접촉):**
1. `recompute_held_atr` (657 인근, 이미 `_fetch_sector` 호출 중): `self._position_sectors[ticker] = <sector>` 추가. **전일 보유(재시작 후)의 정본 소스** — recompute 는 `self.state.positions.keys()` 전수를 돌아 band/유니버스 무관하게 stamp → (1)(2) 케이스 해결.
2. `check_buy_signal` **BUY 반환 직전**(739 인근, NONE 반환 경로 아님): `self._position_sectors[ticker] = cand_sector`. 당일 매수분을 재-prepare 와이프에도 견디게 영속화.
3. `on_position_closed` (810~811): `self._position_sectors.pop(ticker, None)` — `_held_stage3`/`_stop_floor` 와 동일 패턴.

**카운트 수정 (708~709 인근, 최소 diff):**
```
sect_t = (self._candidates.get(t) or {}).get("sector") or self._position_sectors.get(t)
same = sum(1 for t in held_pending if sect_t_of(t) == cand_sector)
```
`_candidates` 우선 → 부재/sector-없음 시 `_position_sectors` 폴백. cap=0/미분류/fail-open 가드(704·706) **불변**.

**반례/한계**: recompute 가 특정 held 에 fail-open(일봉 fetch 실패)이면 그 종목 `_position_sectors` 미기록 → 그날 undercount. 단 이는 **현행 fail-open 과 동일 방향**(매수 허용 쪽)이라 회귀 아님. 완화: prepare held-refill 에서도 `_position_sectors` 있으면 `_candidates` 로 역채움(대시보드 표시 겸용, 선택).

### 안 B — held-refill + prepare 에 sector 저장 (맵 없이 `_candidates` 강화)

prepare held-refill(361~367)에 `"sector": await self._fetch_sector(ticker)` 추가. 신규 맵 없음, 표면 최소.

**반례(치명적·기각 사유)**: held 가 ATR 밴드/유니버스 이탈로 `_candidates` 에서 **완전 부재**할 때 무력 — 이게 라이브 5종목 전부 부재의 실제 원인이다. 저변동 대순환 보유주가 ATR<1% 로 압축되면 정확히 이 케이스에 빠져 캡이 여전히 held 를 못 센다. **관측된 결함을 못 고침.** 표시 개선용 부분 조치로만 가치 있음.

### 안 C — 캡 키를 `bstp_kor_isnm`(표시 소스)로 전환 + held 는 잔고 기반 집계

후보·held 섹터를 모두 `bstp_kor_isnm`(사이클 I 후속, 전 종목 채워짐)에서 산출 → 소스 대칭, 결측 없음.

**반례(기각 사유)**: `bstp_kor_isnm`(KIS 업종 한글명 "유통"/"금융")은 `_kojiro_sector_key`(KRX 산업지수 플래그=**프로그램 basket=실 상관구조**)보다 **훨씬 넓다**. "유통" 한 바구니에 서로 안 움직이는 종목이 섞여 **과잉 클러스터(위양성)** → 실제 동조하지 않는 종목의 매수를 차단 → 캡의 리스크 시맨틱이 "동시 락 위험"에서 "느슨한 업종 분류"로 변질. FREEZE 관찰창에 진입 행위를 크게 바꾼다. 커밋이 의도적으로 고른 상관구조 근거를 폐기. → **소스 비대칭(Q3)의 올바른 해법은 held·후보를 같은 `_fetch_sector` 로 통일하는 것**(안 A 가 이미 달성)이지, 키를 넓히는 것이 아니다.

### 채택 = **안 A**. TDD 로 인계.

---

## 설계 지뢰 (Q2 a~d 답)

- **(a) 재시작 후 boot 갭**: 부팅 순서 = `prepare`(positions 복구 *전* → held-refill 미발화, held 는 `_candidates` 미포함) → positions 복구 → `_eager_refresh_stock_master_for_held_positions` 내 `recompute_held_atr`(boot 종료 시점, ~07:50). 매수는 buy poll(09:05~09:30)/on_tick 에서만 발화 → **recompute 가 매수 창 전에 완료** = 갭 무해. 다만 recompute 가 held 에 fail-open 하면 그 종목만 미stamp(현행 fail-open 동일). **권고: recompute 를 `_position_sectors` 의 정본 갱신점으로 삼아 매 boot 최신 sector 로 덮어쓰기**(일간 재분류 Q4 흡수).
- **(b) `_reset_daily_state` 절대 clear 금지 — 확인 완료**: kojiro 는 `_reset_daily_state` **override 없음**(grep 0) → base no-op 상속. scheduler 20:10 정산이 registry 순회로 호출해도 no-op → `_position_sectors` **자동 보존**. ★ 안 A 구현 시 kojiro 에 `_reset_daily_state` override 를 **추가하지 말 것**(추가하면 멀티데이 held 의 섹터가 밤에 소멸). `_bought_today.clear()` 는 prepare 내부라 무관.
- **(c) 재진입 쿨다운 상호작용**: kojiro 는 BFB/VCP/LTV 와 달리 `_cooldown_until`/`register_cooldown_after_exit` **미보유**(grep 0). 재진입 차단은 `registry.is_ticker_blocked_for_buy`(보유/주문중/당일매도) + `_bought_today` 만. `_position_sectors` 는 **포지션 존재 동안만** 유효(on_position_closed pop)하므로 쿨다운과 독립 — 청산된 종목은 held_pending 에서 빠져 카운트 대상도 아님. 상호작용 없음.
- **(d) stamp 정확 시점**: order_engine(`_handle_buy_fill` positions 등록)은 **8영역이라 접촉 불가**. execute_buy 는 `pending_buys`/`pending_buy_amounts` 를 place_order 응답 직후 **동기** 등록(313~315), positions 는 체결통보(1023)에서 등록. 캡 카운트는 `positions ∪ pending_buys` 를 세므로 **stamp 는 `check_buy_signal` 의 BUY 반환 시점**이 정답 — 그 순간 후보 sector(`cand_sector`)가 확실히 존재하고, 직후 execute_buy 가 pending_buys 에 넣어 같은/다음 폴 사이클에서 즉시 집계 가능. BUY 반환 전(캡 체크 위치)이 아니라 **최종 BUY 반환 직전**에 stamp(시간창/갭/붕괴로 NONE 되는 경로엔 미stamp — 유령 엔트리 방지). BUY 후 execute_buy 가 거부돼도 held_pending 비회원이라 카운트 무영향(무해한 잔존).

---

## 소스 선택 (Q3 미분류 / Q4 일간 재분류)

- **Q3 미분류 held — fail-open 유지가 맞다**: 미분류-{ticker}는 종목별 유니크 키 → 서로/후보와 절대 매칭 안 됨 → 자연히 클러스터 미포함(독립). 캡의 목적이 **상관 동조 위험**이므로, 상관구조를 못 읽는 종목(master_raw 결측)은 세지 않는 편이 위양성 차단에 옳다. 표시용 `bstp_kor_isnm`(유통/금융)과 캡 키(미분류)의 비대칭은 **역할이 달라서 정상** — 표시=사람 판독, 캡=상관 basket. **캡 키를 표시 소스로 바꾸지 말 것**(안 C 기각).
- **Q4 일간 재분류 — 단일 소스 강제로 흡수**: held·후보 모두 `_fetch_sector`→`_kojiro_sector_key(get_master_raw)` 로 통일(안 A 가 보장). KRX 산업지수 플래그/업종 대분류는 지수 리밸런싱 외엔 거의 불변이라 일간 드리프트 희귀. recompute 가 매 boot `_position_sectors` 를 최신 master_raw 로 덮어쓰면 드리프트 자동 반영. **후보 sector(prepare `_fetch_sector`)와 held sector(recompute `_fetch_sector`)가 동일 함수** → 소스 어긋남 원천 차단.

---

## 타이밍 (Q5) — FREEZE·N=1 관찰창 오염 최소화

수정은 **매수 진입 행위를 바꾼다**(전엔 통과하던 3번째 동일섹터를 차단). 그러나:
- 이건 **신규 정책이 아니라 잠복 버그의 정정** — 캡은 처음부터 held 를 세도록 설계됐다(커밋 목표). **리스크 축소 방향**(과집중 방지)이라 FREEZE 취지(수익성 목적 파라미터 튜닝 동결)와 상충하지 않는다. FREEZE 는 리스크 결함 수정을 막지 않는다.
- **바인딩 빈도**: Phase 1 측정 활성일 ~17% + `is_max_positions` 만차일엔 캡 평가 자체 안 됨(690 선반환). 오늘(5/5 만보유)도 캡 미평가. 실제 행위 변화는 **부분보유 + 클러스터 섹터**에서만 발생 = 저빈도.
- **오염 최소화 권고**: cap 값(2)·진입 4조건·청산 전부 **불변**, 카운팅만 정정. 기존 `[kojiro_sector_cap]` INFO 로그가 이미 held 포함 카운트(`same`)와 cand_sector 를 찍으므로 **별도 shadow 로그 불필요** — 실제 차단 발화를 그대로 관찰하면 된다. DB 토글 불필요(정정이지 신기능 아님). 1~2주 바인딩 빈도 관찰 후 cap 값 재고는 별건.

---

## 스코프 (Q6) — cap=2 강화 vs cap 값 재고

**cap=2 유지 + "전일 보유 포함"(안 A) 채택.** cap 값 차등(신선 2 / 누적 3)은 기각:
- 캡의 시맨틱은 **포트폴리오 누적 섹터 노출**(테마 붕괴는 언제 샀든 모든 held 에 동시 작용). 신선/누적 이원화는 복잡도만 늘리고 "동시 락 위험"이라는 단일 리스크 정의를 흐린다.
- held 포함 카운팅이 **명백히 옳은 정정**이므로 먼저 고치고, 만약 정정 후 바인딩 빈도가 과해(대순환 알파 손실 체감) cap=2 가 너무 타이트하면 **cap 값을 2→3 으로 올리는 별도 파라미터 결정**으로 대응. 카운팅(버그)과 cap 값(튜닝)은 분리. 정정 → 1~2주 관찰 → 필요 시 cap 값 재고 순서.

---

## 현 코드와의 정합성

- **CLAUDE.md 안전 8영역 무접촉 확인**: 수정은 `kojiro.py` 단독(`_position_sectors` 필드 + recompute/check_buy/on_position_closed 3지점 + 카운트 1줄). `check_exit_signal`·손절·트레일링·체결통보·멱등 가드 **불변**. 캡은 매수 게이트 전용(700~713)이라 청산 경로 무관. order_engine/risk/realtime/auth/scheduler diff 0.
- **충돌 항목**: 없음. `_reset_daily_state` override 부재 유지가 **영속 의무**(위 2b) — 구현자가 실수로 추가하면 회귀.
- **fail-open 보존**: cap=0 비활성 / 미분류 미차단 / sector 결측 미차단 전부 유지.

---

## 후속 검증 권고 (tdd-engineer)

Red 테스트 시나리오 (합성 상태 주입, 결정적):
1. **전일 보유 집계 (핵심 RED)**: `positions` 에 동일섹터 2종목 주입(전일 buy_date) + `_candidates` 에서 **제거**(밴드 이탈 재현) + `_position_sectors` 에 sector 2건 주입 → 같은 섹터 후보 check_buy_signal → `Signal.NONE`(차단). 수정 전엔 `same=0` 로 BUY 통과(RED).
2. **재-prepare 와이프 견딤**: `_position_sectors` stamp 후 `prepare()`(또는 `_candidates={}`) → `_position_sectors` 생존 + 카운트 유지.
3. **recompute stamp**: `state.positions` 에 held 주입 → `recompute_held_atr` → `_position_sectors[held]==<KRX플래그 섹터>`.
4. **on_position_closed pop**: 청산 → `_position_sectors` 에서 제거 → 재진입 후보 미집계.
5. **미분류 fail-open**: held 가 미분류 → 후보 카운트 0(차단 안 됨).
6. **`_reset_daily_state` 미소거 (AST/행위)**: 20:10 정산 시뮬 후 `_position_sectors` 보존. kojiro 에 `_reset_daily_state` override 부재 AST 가드.
7. **당일 매수 영속**: check_buy_signal BUY 반환 → `_position_sectors[t]` stamp → 직후 재-prepare 에도 다음 후보 카운트에 반영.
8. **8영역 diff 0 SAFETY**: `git diff` risk/order_engine/realtime/auth/scheduler == 0 + `check_exit_signal` 토큰 무주입 AST.

KIS 스펙 무관(순수 메모리 상태 로직) — respx 불요, freezegun 은 buy poll 시간창(09:05~09:30) 재현에만.
