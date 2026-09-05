# 09-05(토) 주말 오후 보고 — D5 TLS 전환 · D3 채택 → cycle254 · D4 승인 기록 (12:57 ~ 14:10 KST)

> 이 문서는 주말 1부 보고서(`_workspace/reports/2026-09-05_weekend_decision_set.md`, 아티팩트 https://claude.ai/code/artifact/0c558bf8-4fa8-45d0-8aa4-98ab392ffb46)의 **후속**이다. 1부가 남긴 "결정 대기" 6건 중 3건(D5 DNS · D3 권고 B · D4 월요일 착수)이 이 구간에서 처리됐다. 1부 창의 발견·수치는 그 문서가 정본이고 여기서 반복하지 않는다.
> 집계 창 = 1부 보고서 커밋(7ad5042, 12:32) 이후 첫 커밋 12:57 ~ 14:10(커밋 `7ad5042..17415c9`). 시각은 `git log --date=format:%H:%M 7ad5042..17415c9` 로 셌다. 전부 토요일 = 장 닫힘.
> 사용자 메시지(원문 순서) = "등록했어."(DNS A 레코드) → "내 Gmail 사용"(Let's Encrypt 알림 메일) → "D4 월요일 착수 / D3 권고 B".

## 0. 한눈에

| 항목 | 결과 |
|---|---|
| 커밋 | **4건**(12:57 ~ 14:10) = 코드 2 · 문서 2. 분류 매핑 = `fix` → 코드(b46f1f4 는 운영 스크립트 `tools/ops/tls_enable.sh` 1줄 + 워크리스트, 92e75f3 는 `strategy_base.py` + 테스트 + 정본 문서), `docs` → 문서 |
| 배포 | **3건** — **13:05** `none` 모드(b46f1f4, 커밋 12:57 · gh run Deploy 04:04:48Z~04:05:03Z = KST 13:04:48~13:05:03, 빌드·재시작 없이 마커만 전진, backend Up 유지) · **13:06 TLS 전환**(코드 배포가 아니라 EC2 에서 `tls_enable.sh` 를 실행한 **서버 설정 전환**, frontend 컨테이너만 TLS 오버레이로 재기동, backend 무접촉) · **14:08 full**(92e75f3 cycle254, backend·frontend 재생성). 문서 커밋 2건(13:11 a5b1fc6 · 14:10 17415c9)은 CI `paths-ignore` 로 CI/Deploy 미기동(13:11 은 호출자 확인, 14:10 은 규칙 적용 — 변경 파일이 `CLAUDE.md`·`_workspace/`·`docs/` 뿐) |
| 사이클 | **1회**(cycle254 — 터틀 1주 폴백 랏 ρ축 상한 `min` 합성, F-9 종결) |
| 사용자 결정 처리 | **3건** — D5 완료(TLS 전환 + 루틴 2개 주소 전환) · D3 채택 → cycle254 구현·배포 · D4 월요일 착수 승인 기록(명세 확정) |
| 사고 | 장중 서버 중단 0(토요일) · 매매 사고 0 · 기동 오류 0(14:08 재시작 기준, startup complete·오류 grep 0) |
| 남은 결정 | **4건**(§4, 급한 순) — ① 클라우드 환경 허용 도메인에 `auto.dkstock.cloud` 추가(사용자 행동) ② 대시보드 '일일 리포트' 탭 시각 서식 전환 여부(1부 카드 재게재) ③ D10 착수 요일 ④ TLS 2단계 시점 |

## 1. 집계 창 커밋 목록 (신→구, 4건)

| 커밋 | 시각 | 분류 | 제목(요약) | 변경 파일 |
|---|---|---|---|---|
| 17415c9 | 14:10 | 문서 | cycle254 배포 완료 기록(14:08 full, 마커 92e75f3) + 월 D+1 판독용 배포 전 마커 기준선 | `CLAUDE.md` · `_workspace/00_URGENT_WORKLIST.md` · `_workspace/specs/cycle254_ratio_cap_min_composition.md` · `docs/HARNESS_CHANGELOG.md`(4파일 +5/−3) |
| 92e75f3 | 14:01 | 코드 | fix: 터틀 1주 폴백 랏에 ρ축 상한 min 합성 — 구 결정 ⑦(상호배타) 폐기 (cycle254, F-9 종결, 사용자 결정 D3 권고 B) | `src/engine/strategy_base.py`(86줄 변경 = 추가+삭제, 단독 소스) · 테스트 3파일(신규 `tests/unit/engine/test_cycle254_ratio_cap_min_composition.py` 413줄 · 신규 `tests/unit/ast/test_cycle254_ast_ratio_cap_min.py` 261줄 · `test_cycle245_ratio_notional_cap.py` 2건 개정) · 문서 7 = 기준 문서 5(루트 `CLAUDE.md` · 워크리스트 · `00_leader_trading_rules.md` · `src/engine/CLAUDE.md` · `src/engine/strategies/CLAUDE.md`) + 명세 + changelog. 11파일 +787/−66 |
| a5b1fc6 | 13:11 | 문서 | D5 TLS 전환 완료 기록(auto.dkstock.cloud, 루틴 BASE https 전환) + cycle254 명세 | 워크리스트 · 명세 신규 99줄(2파일 +100/−1) |
| b46f1f4 | 12:57 | 코드(운영 스크립트) | fix: tls_enable.sh 4/6 발급 산출물 확인을 `sudo test -f` 로 — `/etc/letsencrypt/live` 는 root 700 이라 ubuntu 검사가 거짓 실패 + D3 권고 B 채택·D4 월요일 착수 승인 기록 | `tools/ops/tls_enable.sh`(+3/−1) · 워크리스트(2파일 +5/−3) |

## 2. 배포·서버 설정 이력 (호출자 검증 — EC2 마커 `.deployed_sha` · `docker ps` · startup 로그 · 오류 grep · 루프백 API · 외부 curl · gh run)

| 시각 | 무엇을 | 모드 | 확인 |
|---|---|---|---|
| 13:05 | b46f1f4(커밋 12:57) TLS 스크립트 1줄 수정 | `none`(backend Up 유지, 빌드 없음) | 마커 b46f1f4(gh run Deploy 13:04:48~13:05:03 KST), 스크립트 반영 확인 |
| 13:06 | **TLS 전환** — EC2 에서 `LE_EMAIL=<사용자 Gmail> bash tools/ops/tls_enable.sh` 재실행(코드 배포 아님) | frontend 컨테이너만 `docker-compose.tls.yml` 오버레이로 `up -d --no-deps frontend`, backend 무접촉 | 사후 검증 통과(80→401 ∧ 443→401 ∧ `State=running`) · 갱신 경로 검증(reload 훅 1회 실행 성공 + `certbot renew --dry-run` 성공) · 배포 스크립트 dry-run `tls=on` |
| 13:11 | a5b1fc6 문서 | CI 미기동(`paths-ignore`) | — |
| 14:08:26 | 92e75f3 cycle254 | **full**(backend·frontend 재생성, TLS 오버레이 자동 포함) | 마커 92e75f3 · `.attempt` 없음 · `tls=on` · 재시작 오류 0 · startup complete · 실행 이미지에서 새 조건(`governs and gov_reason == "probe_error"`) 1건·`backstop` 0건 · 루프백 `/health` 200 · `/api/strategies` 200 · 외부 https 무자격 401 유지 |
| 14:10 | 17415c9 문서 | CI 미기동(규칙 — 변경 파일 전부 `paths-ignore` 대상, 호출자 확인 없음) | — |

CI = b46f1f4 12:57 push → CI 통과 13:04 → Deploy `none` 13:05 / 92e75f3 14:01 push → CI 통과 14:08 → Deploy full 14:08:26. 창 안 CI 실패 0.

## 3. 처리 상세

### 3.1 D5 — TLS 전환 완료 (13:06) + 루틴 2개 주소 전환 (13:09~13:10)

**순서** — 사용자가 `auto.dkstock.cloud` A 레코드를 등록("등록했어.") → 메인 세션이 EC2 에서 `tls_enable.sh` 실행(알림 메일 = 사용자 Gmail, "내 Gmail 사용").

- **첫 실행 = 4/6 단계 거짓 실패.** 1/6 DNS 확인(dig) · 2/6 ACME 경로 점검(웹루트 권한 보정 포함, 무자격 200) · 3/6 certbot 발급 **성공** → 4/6 "발급 산출물 확인"에서 멈춤. 원인 = `/etc/letsencrypt/live` 가 root 전용(700)이라 ubuntu 권한의 `[ -f fullchain.pem ]` 이 EACCES 로 거짓 "없음"을 냈다. 인증서는 있었다.
- **시정** = 스크립트 한 줄을 `sudo test -f` 로(b46f1f4, 커밋 12:57 · 서버 반영 13:05). 배포 모드 `none` = backend 무재시작(`tools/ops/` 는 이미지 입력이 아니다).
- **재실행** = certbot "갱신 불필요"(재발급 없음, Let's Encrypt 발급 한도 소모 없음) → 4/6 통과 → 마커 `.tls_enabled` 생성 → frontend 만 오버레이로 재기동 → 사후 검증 통과 → 갱신 경로 검증 통과.
- **외부 실측**(13:06 직후) = https 무자격 401 · 발급자 Let's Encrypt, **만료 2026-12-04** · TLS 1.2/1.3 협상 · http 도 401 유지(리다이렉트 없음 = 1단계 설계) · ACME 경로 404(파일 부재가 정상) · `/docs` 401.
- **자동 갱신** = snap certbot 타이머(다음 실행 05:29 UTC = 14:29 KST) + renewal conf 의 `renew_hook` 이 nginx reload. crontab 없음(cycle255 설계대로).
- **배포 스크립트** dry-run `tls=on` — 이후 모든 배포가 오버레이를 자동 포함(모드 판정에는 무관여). 14:08 full 배포가 이를 실증(`tls=on` 로그).
- **대시보드 상태변경 HTTPS 통과 확인** = 백엔드 Origin 검사는 도메인만 비교(스킴 무관). EC2 루프백에서 nginx 헤더를 흉내 낸 POST 가 `Origin: https://auto.dkstock.cloud` 로 404(인증 통과, 경로 부재) · `https://evil.example` 은 401.
- **루틴 2개 주소 전환**(13:09~13:10, Claude 루틴 설정) — 자동 리포트(평일 20:20 KST) · 주간 자문(화 20:30 KST)의 API 베이스를 `https://auto.dkstock.cloud` 로. 시작 시 `/api/health` 200 확인, curl 연결 실패 시 종전 http EC2 호스트로 **자동 예비**, 마지막 메시지에 "어느 주소를 썼는지" 표기(예비 사용 = 허용 도메인 미추가 신호). Notion 연결·모델·스케줄 무변경.
- **남은 것(사용자)** = 클라우드 환경 '자동매매' 의 네트워크 허용 도메인 목록에 `auto.dkstock.cloud` 추가(현재 목록 = EC2 공개 DNS 호스트명뿐). 추가 전에는 루틴이 https 연결에 실패하고 http 예비로 돌아간다 = 리포터 자격이 여전히 평문. **2단계(http→https 리다이렉트 · HSTS · Basic 자격 회전)는 예비 경로 제거 뒤**(§4 ④).

### 3.2 D3 권고 B 채택 → cycle254 구현·배포 (커밋 14:01, 배포 14:08)

정본 = `docs/HARNESS_CHANGELOG.md` 상단 1행(cycle254) · 명세 `_workspace/specs/cycle254_ratio_cap_min_composition.md` · 자문 `_workspace/domain_consult/cycle254_turtle_fallback_rho_exposure.md` §1.

**선결 확인(F-9 실재)** — 자문이 "F-9 는 그 전략의 라이브 `sizing_mode` 가 `turtle` 일 때만 실재"라고 못박아, 09-05 DB `strategy_config` 실측으로 donchian_swing·kojiro 둘 다 `sizing_mode=turtle`(`max_lot_ratio_mult` 키 부재 → DEFAULT 2.5)임을 확인한 뒤 착수. `system_logs` 의 `[ratio_cap_config]` 는 09-04 00:00 이후 **0행**(09-04 야간 cycle245 배포 뒤 주말이라 매수 랏 없음) — 자문 §9 의 "배포 전 `cap=` 두 행" 대조군은 로그가 아니라 DB 값으로 대체.

**"아침 7행" 기록의 정정(메인 세션 실측)** — 명세 §0 첫 문단·자문 §1·메모리가 인용한 "09-05 아침 `[ratio_cap_config]` 7행(donchian·kojiro `cap=backstop`)" 은 근거가 확인되지 않는다. `system_logs`(DB 로그 핸들러가 INFO 이상을 받는다 — 09-04 `[fallback_cap_config]` 4행이 실제로 있음)·파일 로그 `logs/auto_stock.log.2026-09-04`(같은 4행 + `[oversized_fallback]` 1행)·컨테이너 표준출력 어디에도 `[ratio_cap_config]` 는 09-04 이후 0행이다. 즉 cycle245 배포(09-04 밤) 뒤 매수 랏 자체가 없어 그 마커는 한 번도 찍히지 않았다. 메모리 기록은 오기로 정정했고, F-9 실재 확인은 DB `strategy_config` 값으로 했다.

**발단(구조적 천장, 실제 체결 아님)** — cycle245 의 구 결정 ⑦ "두 캡은 상호배타"로 K축(`max_lot_units`, ATR 유닛 캡)이 심사한 랏은 ρ축(`max_lot_ratio_mult`, 비중 명목 캡)을 건너뛰었다. 1주 폴백 랏(주가 > 예산×position_ratio)이 저ATR 고가 종목에서 K축을 통과하면 명목 상한이 없어 **donchian 390,300원**(그 전략 예산 전부, 순자산 15.0%, ρ배수 5.00) · **kojiro 500,000원**(`price_filter_max`, 순자산 19.2%, ρ배수 3.86)까지 허용된 상태였다. 자문 §2.2: `min` 합성이 행위를 바꾸는 창 = ATR% < 2.00%(donchian) / 2.41%(kojiro), 계좌 크기 무관 = "저변동 고가주" 문제. 자문 §2.4: 폴백 랏은 `_entry_atr` 미스탬프라 고정%손절(donchian 라이브 −6.0%) → 390,300원 랏의 정상 손절 손실 −23,418원(순자산 0.90%) = 설계 유닛 리스크 1,952원(0.075%)의 12배. −30% 갭이면 순자산 4.50%/5.76%.

**변경(`strategy_base.py` 단독)** — `_apply_ratio_notional_cap` 의 조기탈출을 `if governs and gov_reason == "probe_error": … return final` 한 조건으로 좁힘(판정기 자체가 실패한 경우만 fail-open, `_lot_units_cap_governs` 호출은 존치 — AST G-245-4 핀 + F-10d 계약). 그 외엔 K축 심사 여부와 무관하게 ρ캡 `cap_qty = int(K_ρ × int(예산 × position_ratio)) // 현재가` 를 통과시킨다. 관문 순서(폴백 → K캡 → `[oversized_fallback]` → ρ캡 → return)·반환 `int` 무변경. `_emit_ratio_cap_config` 라벨 `backstop` 삭제 → `off|on` 2종. 8영역·`scheduler.py`·`turtle_sizing.py`·`portfolio_risk.py`·전략 7파일 diff 0. K_ρ 2.5 유지(파라미터·DB 변경 0).

**항등식(왜 안전한가)** — 사이즈드 터틀 랏·`position_ratio` 낙하 랏은 `compute_unit_qty_guarded` 가 `min(qty, int(예산×position_ratio)//price)` 를 무조건 적용하므로 명목 ≤ 예산×position_ratio ≤ 컷오프 → `final <= cap_qty` 로 항등적 통과, **수량 불변**. 실효는 **1주 폴백 랏뿐** — 주가가 컷오프를 넘으면 `cap_qty=0` → 0주(미매수). **컷오프 = donchian 약 195,150원 · kojiro 약 323,952원**(리포 예산 기준 추정: 순자산 2,602,038 × 라이브 weight 0.15/0.30 = 예산 390,300/780,611 × position_ratio 0.20/0.166 = 설계 금액 78,060/129,581 × K_ρ 2.5. 실제 예산이 몇 원 다르면 195,152 처럼 수 원 차이가 정상이고, 수백 원 이상 차이면 DB 예산·비중이 다른 것. **정본은 로그의 `cutoff_price=` 값** — 자문 §5.2·명세 §6). 자문이 표로 남긴 실제 터틀 1주 폴백 11랏(cycle242 자문, 120영업일) 중 결과가 바뀌는 랏 **0**.

**검증(워크플로 7에이전트, 51분)**
- Red 16케이스 = 10 FAIL(F-9a/c/f[195151]/g · G-254-1a/1b/2a/2b · f245_7b/16b 개정) + 6 PASS(현행 계약 봉인용). Green = 표적 6파일 280 passed, tests/unit/engine+ast 4,716 passed(실패 10 전부 전환, skip/xfail 수치 동일).
- 뮤테이션 3렌즈 = 15/15 · 8/8 · 9/9 KILLED(행위 등가 뮤턴트 1 별도 — `governs` 항 제거는 G-254-2b 만 죽인다). 표적 = 결정 ⑦ 조기탈출 복원 · `==`→`!=` fail-closed 반전 · 경계 `<=`→`<` · 라벨 복원 · 판정기 호출 삭제 · `cutoff//price`→`cap//price` · 반환 `float` 변조 등 15종.
- 차분 격자 **6,458 조합**(HEAD a5b1fc6 git worktree 사본 vs 변경본, 동일 스크립트 = 고치기 전 코드와 고친 코드에 같은 입력을 넣은 **계산 비교**, 실서버 배포 전후 기록 비교가 아니다) = 터틀 1,680(차이 48) + 보충 라이브 2,720(차이 576, 경계 161,972/195,150/323,952 실측) → **터틀 4,400 중 차이 624 전부 1주 폴백 1→0 · 증가 0 · 예측식 불일치 0** / probe_error 패치 1,680 차이 0 / 비터틀 BFB 378 차이 0.
- 스위트 = tests/unit/ast+engine **4,722 passed / 0 failed**(4 skipped · 155 xfailed · 4 xpassed, changelog) · tests/unit **6,455 PASS** · 문서 읽는 테스트 100파일 882 PASS(호출자 꾸러미).
- **적대 검증 발견** = 정본 문서 3파일(`src/engine/CLAUDE.md` · `src/engine/strategies/CLAUDE.md` · 워크리스트)이 구 결정 ⑦("상호배타", `cap=backstop` 정상)을 그대로 서술 → tester 가 시정 + 문서 가드. **메인 세션 결정** = 문서 가드 6건 중 워크리스트 대상 2건 + 범용 구절("행은 정상이다") 1건 삭제(살아 있는 문서 = 오탐 생성기), `backstop` 토큰 가드는 단어 경계로 축소(`turtle_backstop_pct` 정식 파라미터명 오탐 방지). 남은 가드 = `test_g254_4a/4b/4d`(하위 CLAUDE.md 2파일을 감시하는 3건).

**의미 전환 2(배포 전후 같은 grep 합산 금지)** = ① `[ratio_cap_config]` 터틀 행 라벨 `backstop`→`on` ② R7 자기검증 반전 — 터틀 행에서 `[oversized_fallback] ratio>k` 인데 같은 (전략, ticker, 일자)에 `[ratio_notional_blocked]` 도 `[ratio_cap_skipped]` 도 없으면 이제 **캡 우회 = 결함**.

**롤백** = 코드 재배포 없이 해당 전략 `max_lot_ratio_mult=20.0`(`PUT /api/strategies/{id}/params` 즉시 / SQL 은 다음 재시작). 이번 변경은 수량을 늘리지 않는다(`min`). 청산 규약(`check_exit_signal`) diff 0.

**배포** = CI 통과 14:08 → EC2 full 14:08:26(§2 표). 배포 전 기준선(`system_logs`, 14:0x 조회) = 09-03 `[oversized_fallback]` 4 · 09-04 `[oversized_fallback]` 1(별도로 `[fallback_cap_config]` 4 는 설정 알림 = 랏 이벤트와 성격이 다르다) · ρ축 마커 3종(`[ratio_cap_config]`·`[ratio_notional_blocked]`·`[ratio_cap_skipped]`) + 손절 폭 기준(K축) 마커 `[fallback_notional_capped]` 09-01~05 0행. 월 판독 ⑦(`[oversized_fallback]`)의 "배포 전과 동일"은 이 표가 아니라 직전 5영업일 평균(1~4건/일)과 비교하고, ④(`[fallback_notional_capped]`)는 최근 5영업일 0건이었으니 0건 유지가 기준.

### 3.3 D4 — 월요일 착수 승인 기록

사용자 "D4 월요일 착수" → 명세 `_workspace/specs/cycle_next_D4_bought_today_after_fill.md`(권고 A = 주문 접수 훅: `order_engine.execute_buy` 가 `place_order` 성공 직후 전략 훅 호출, 4전략의 `_bought_today.add` 를 훅으로 이동). 8영역 `order_engine.py` **1곳** 승인 포함(착수 시 sha 핀 절차). 월 09-07 착수, 배포는 장외(15:30 이후 또는 07:55 전). 도메인 자문 불필요(표식 시점 정정, 매매 규칙 변경 아님).

## 4. 결정 대기 (급한 순, 4건 = 호출자 목록 전부, M=4)

| # | 항목 | 답해 주실 것 | 제안 |
|---|---|---|---|
| ① | **클라우드 환경 '자동매매' 허용 도메인에 `auto.dkstock.cloud` 추가**(사용자 행동, Claude 클라우드 환경 네트워크 설정) — **가장 급함** | 추가한 뒤 "추가했어". 못 하셔도 월 20:20 루틴 마지막 메시지의 "사용 주소" 로 메인 세션이 판별한다("예비 주소 사용" = 아직 안 된 것) | 추가 전에는 루틴이 http 예비 경로로 돌아가 리포터 자격이 평문으로 오간다. 추가하면 다음 실행부터 https |
| ② | **대시보드 '일일 리포트' 탭(20:10 분석 결과 화면) 시각 서식 전환**(1부 카드 재게재) — 표기 `2026. 9. 7. 9시 5분 0초` → `2026-09-07 09:05:00`. cycle256 이 공용 KST 유틸을 만들고 PortfolioRiskCard 1곳에만 적용했다(출력 byte 동일 = 그 카드는 서식이 바뀌지 않았고 시:분만 보여 준다). 이 탭은 화면 표기가 눈에 띄게 바뀌어 결정 대기 — **시점 자유** | "바꿔" / "그대로" | 바꿈(읽기 쉽고 정렬됨). frontend 전용 = 무재시작, 장중 가능 |
| ③ | **D10 착수 요일** — DB 연결 대기(`asyncpg` 풀 `acquire()`) 타임아웃. 지금은 풀 고갈 시 모든 DB 호출이 무한 대기(cycle250 이 계좌 위험 감시에 300s 타임아웃을 씌워 막은 hang 과 같은 원인). 명세 초안 `_workspace/specs/cycle_next_D10_pg_acquire_timeout.md`(T 후보 30s). 8영역 호출자 승인 동반 | 요일 하나(화~목 권고) | 착수일 아침 명세 §3 호출자 전수 목록을 먼저 보여 드린 뒤 8영역 호출자 승인 → 사이클 → 장외 배포 → D+1 `[pg_acquire_timeout]` 0건 |
| ④ | **TLS 2단계 시점** — http→https 리다이렉트 + HSTS + Basic 자격 회전. HSTS 는 브라우저에 되돌릴 수 없는 상태를 심으므로 예비 경로(http)가 살아 있는 동안은 금지 | "루틴 https 성공 확인되면 진행해" 또는 날짜 | ① 완료 → 월 20:20 루틴 1회 https 성공 확인 → 그 뒤 진행(1부 제안 "안정 1주" 보다 앞당김 = 예비 경로가 있는 동안 자격이 평문이라). 자격 회전은 Claude 루틴 환경 변수와 EC2 `secrets/.htpasswd` 두 곳 동시 |

정본 워크리스트에 추가 결정은 없다. D8 후속(채널 리졸버)은 월 09:30 프로브 결과가 정하므로 지금 답할 것이 없다(1부 §4 ⑥ 그대로). D4 는 이미 승인돼 결정 목록에서 뺐다(§3.3).

## 5. 월요일(09-07) 확인 목록 (07:55 부팅 후, 메인 세션이 확인·보고)

1부 §5 항목은 그대로 유효하다(cycle257·258·259 첫 부팅 · D9 09:00:3x 폴 · D8 09:30 프로브 로그 · `[no_feed_held]` 등). 이번 창이 추가·갱신한 항목:

- [ ] **판독 채널** = `system_logs` 직접 조회가 기본(형식 `[src.engine.strategy_base] [ratio_cap_config] …`), 파일 로그 `logs/auto_stock.log` grep 이 보조(일 단위 회전·30일 보존, 컨테이너 재생성에도 남음). 20:10 리포트는 WARNING↑만 집계해 INFO 마커 미도달.
- [ ] **cycle254 ①②** `[ratio_cap_config] strategy=donchian_swing sizing_mode=turtle cap=on k=2.50 … cutoff_price=약 195150` 1행 / `strategy=kojiro … cap=on … cutoff_price=약 323952` 1행(리포 예산 기준 추정 — 195,152 처럼 수 원 차이는 정상, 수백 원 이상이면 DB 예산·비중 상이). `backstop` 잔존 = 미반영. kojiro 가 **약 390,300** 이면 DB `position_ratio` 0.20 = 08-08 지혈 롤백 의심(명세 §6 — 자문 §5.3 의 387,320 은 산술 오기, 780,611×0.20×2.5=390,305)
- [ ] **③** `[ratio_notional_blocked] strategy=donchian_swing|kojiro path=fallback` **0건** — 나오면 F-9 첫 실측 표본(ticker·price·ATR% 기록, 결함 아님)
- [ ] **④** `[fallback_notional_capped]`(K축 = 손절 폭 기준 한도, cycle242 부터) — 최근 5영업일 0건이었으니 **0건 유지**. 생기면 K축 접촉 = 롤백
- [ ] **⑤** `[ratio_cap_skipped] reason=k_axis_probe_error` 0건
- [ ] **⑥** donchian·kojiro 매수 건수 직전 5영업일 평균 대비 감소 0
- [ ] **⑦** `[oversized_fallback]` 건수 직전 5영업일 수준(1~4건/일) 유지 — ρ캡보다 **앞**에서 발화라 무변이 정상이고, 변해도 롤백 아님. R7 반전: 터틀 행에서 `ratio>k` 인데 같은 (전략, ticker, 일자)에 BLOCKED·RSKIP 미동반이면 결함
- [ ] **20:20 루틴 첫 https 실행** — 마지막 메시지 "사용 주소" 가 `https://auto.dkstock.cloud` 면 ① 완료, "예비 주소 사용" 이면 ① 미완
- [ ] **D4 착수**(승인 완료) — 8영역 `order_engine.py` 1곳 sha 핀 → Red → Green → tester → 장외 배포
- [ ] TLS 자동 갱신 타이머는 매일 도는 것이 정상(만료 12-04 의 30일 전부터 실제 갱신). 이상 시 = `certbot renew --dry-run` 재실행(메인 세션)

## 6. 승인 시 절차 (주체 명시)

- **①** — 사용자: Claude 클라우드 환경 '자동매매' 네트워크 설정에서 허용 도메인에 `auto.dkstock.cloud` 추가. 메인 세션: 월 20:20 루틴 실행 로그(`list_runs` → `get_run_log`)에서 사용 주소 확인 → https 면 ④ 진행 조건 충족을 보고.
- **②** — 사용자: "바꿔". 메인 세션: frontend 전용 커밋(DailyReportTab → `utils/kst.ts` 위임) → frontend 모드 배포(무재시작, 장중 가능) → 화면 확인.
- **③** — 사용자: 요일. 메인 세션: 그날 아침 호출자 전수 목록(`pg.fetch/fetchrow/fetchval/execute/executemany` 호출처 3분류) 제시 → 8영역 호출자 승인 → tdd-engineer Red → backend-dev Green → tester(풀 size=1 통합) → 장외 배포 → D+1 `[pg_acquire_timeout]` 0건.
- **④** — 사용자: 시점. 메인 세션: 루틴 https 1회 성공 확인 → HTTP 템플릿에 301 리다이렉트 + TLS 템플릿에 HSTS(frontend 전용, 무재시작) → Basic 자격 회전(Claude 루틴 환경 변수 + EC2 `secrets/.htpasswd` 동시, 루틴 1회 재검증) → 루틴 예비 경로 제거.
- **D4(승인 완료)** — 메인 세션: 월 착수(§5).

## 7. 함께 만든 것들

- 명세 `_workspace/specs/cycle254_ratio_cap_min_composition.md`(99줄 신규 + 배포 기록 추가) — §0 선결 확인 실측, §1 변경·항등식, §6 D+1 판독 7서명 + 배포 전 기준선, §7 롤백(보유 종목 DB 실측 포함 — 미커밋, 이 보고서와 함께 커밋 예정).
- 테스트 신규 2파일(행위 413줄 · AST 261줄) + cycle245 테스트 2건 개정. 문서 가드 3건(`test_g254_4a/4b/4d`, 하위 CLAUDE.md 2파일 감시).
- 문서 동반 개정 = 기준 문서 5곳(루트 `CLAUDE.md` 핵심 계약 문단 + 하네스 표 · `00_leader_trading_rules.md` · `src/engine/CLAUDE.md` · `src/engine/strategies/CLAUDE.md` · 워크리스트 D3 행) + 명세 + changelog.
- 루틴 2개 주소 전환(https + 예비 경로 + 사용 주소 표기) — 루틴 설정 자체가 정본.
- 참조(창 밖, 1부 창 산출) = 자문 `_workspace/domain_consult/cycle254_turtle_fallback_rho_exposure.md` · D4 명세 `cycle_next_D4_bought_today_after_fill.md` · D10 명세 `cycle_next_D10_pg_acquire_timeout.md`.

## 8. 배운 점 · 정정한 사실

- **관리자 전용 폴더의 파일 존재 확인은 관리자 권한으로 해야 한다.** `/etc/letsencrypt/live` 는 root 700 이라 일반 사용자의 `[ -f ]` 가 "없음"을 낸다(EACCES ≠ 부재). 인증서는 발급됐는데 스크립트가 4/6 에서 멈췄다. 재실행은 certbot 이 "갱신 불필요"로 답해 발급 한도 소모 없이 통과했다 — 스크립트가 순서(산출물 확인 뒤에만 마커)를 강제한 덕에 인증서 없는 443 기동은 없었다.
- **정본 문서는 코드보다 늦게 늙는다.** 결정 ⑦ 을 폐기한 코드가 붙기 전까지 문서 3파일이 "상호배타 · `cap=backstop` 정상" 을 서술했다. tester 의 적대 검증이 드리프트를 찾았고 가드로 봉인했다 — 단 살아 있는 문서(워크리스트)에는 가드를 두지 않는다(오탐 생성기).
- **배포 전 대조군 행 자체가 없다.** `[ratio_cap_config]` 는 cycle245 배포(09-04 밤) 뒤 세 채널(`system_logs`·파일 로그·표준출력) 모두 0행 — 매수 랏이 없었기 때문이다. "배포 전 라벨을 읽어 F-9 실재를 확인하라"는 자문 절차는 DB `strategy_config` 값(donchian_swing·kojiro `sizing_mode=turtle`)으로 대체했다. 월요일 첫 행은 곧바로 `cap=on` 이어야 하고, `backstop` 이 보이면 cycle254 미반영이다.
- **정본 간 불일치 1건(재확인 대상)** — 명세 §7 = 09-05 14:3x DB `positions` 실측 **9**(kojiro 6 · donchian_swing 2 · bull_flag_breakout 1) vs 1부 보고서 §5·부록 A 의 positions **4**. 1부 값은 장중 메모리 상태였을 가능성이 있어 재확인 대상이다. 명세 §7 의 이 수정은 미커밋(이 보고서와 함께 커밋 예정). 이 보고서와 HTML 은 보유 종목 수를 판단 근거로 쓰지 않는다.

## 부록 A. 쉬운 말 리포트(HTML)에서 단순화한 곳 — 정확값 대응표

| HTML 표기 | 정확값(출처) |
|---|---|
| 커밋 4(코드 2 · 문서 2) | §1 표, `git log 7ad5042..17415c9` 4건. b46f1f4 는 운영 스크립트 `fix` 라 코드로 분류 |
| 서버에 반영한 것 3(코드 배포 2 · 암호화 통신 켜기 1) | §2 표 — `none` 1(13:05) · TLS 전환 1(13:06, `tls_enable.sh` 실행) · full 1(14:08). 문서 커밋 2건은 CI 미기동 |
| 표 첫 행 "커밋 12:57 · 서버 반영 13:05" | b46f1f4 커밋 12:57, gh run Deploy 04:04:48Z~04:05:03Z = KST 13:04:48~13:05:03 |
| 표의 13:09 자동 리포트 주소 변경 | Claude 루틴 설정 변경 13:09~13:10 — 서버 배포가 아니라 타일 3건에서 제외 |
| 자동 리포트(평일 20:20) · 주간 자문(화요일 20:30) | Claude 루틴 2개 = 일일 운영 리포트(평일 20:20 KST) · 주간 자문(화 20:30 KST). 대시보드의 '일일 리포트' 탭(20:10 OpenAI 분석 결과 화면)과는 다른 것 |
| 터틀 방식 두 전략 | `sizing_mode="turtle"` = donchian_swing · kojiro(09-05 DB 실측) |
| 1주 매수 | `_fallback_one_share` 1주 폴백 랏(비중 계산 수량 0 → 전략 잔여 자금으로 1주) |
| 종목당 설계 금액 약 7만 8천 원 · 약 13만 원 | `int(전략 예산 × position_ratio)` = donchian 78,060원 · kojiro 129,581원(리포 예산 기준) |
| 컷오프(설계 금액의 2.5배) 약 195,150원 · 약 323,952원 | `int(K_ρ 2.5 × 설계 금액)`, 순자산 2,602,038 · weight 0.15/0.30 · position_ratio 0.20/0.166 기준 추정(자문 §2.1·명세 §1). 정본은 로그 `cutoff_price=` |
| 허용된 최대 39만 원 · 50만 원 | donchian 390,300원(예산 전부, 순자산 15.0%) · kojiro 500,000원(`price_filter_max`, 19.2%) — 구조적 천장이지 실제 체결 아님(자문 §2.1) |
| 정상 손절 약 2만 3천 원 = 설계 리스크(약 2천 원)의 12배 | −23,418원(순자산 0.90%) ÷ 1,952원(0.075%) = 12.0(자문 §2.4). 고정 비율 손절 = donchian 라이브 −6.0% |
| 실제 1주 매수 11건 중 결과가 바뀌는 것 0 | cycle242 자문 120영업일 터틀 1주 폴백 실측 11랏(자문 §1) |
| 약 6,500가지 조합 · 바뀐 624건 전부 축소 | 격자 6,458 조합(HEAD 워크트리 vs 변경본 계산 비교), 터틀 4,400 중 차이 624 = 1주 폴백 1→0 · 증가 0(changelog) |
| 검사 항목 4,700개 넘게 통과 | tests/unit/ast+engine 4,722 passed / 0 failed(changelog). tests/unit 전체는 6,455(꾸러미) |
| 코드를 일부러 15가지로 망가뜨려 전부 잡아냄 | 렌즈1 뮤테이션 15/15 KILLED. 렌즈2 8/8 · 렌즈3 9/9 는 같은 표적군의 반복 검증(행위 등가 뮤턴트 1 별도) |
| 코드 조건 한 곳 | `_apply_ratio_notional_cap` 조기탈출 조건 1개 좁힘 + 라벨 분기 삭제 + docstring(`strategy_base.py` 86줄 변경) |
| 문서 두 곳을 감시하는 검사 3건 | `test_g254_4a/4b/4d`(하위 CLAUDE.md 2파일). 워크리스트 가드는 메인 세션이 제외 |
| 기준 문서 5곳과 설계 문서·변경 이력 | 기준(정본) 문서 5 + 명세 + changelog(§1 92e75f3 행) |
| 인증서 만료 12월 4일 · 90일마다 자동 갱신 | 2026-12-04(외부 실측, 발급 09-05 + 90일). 갱신은 snap 타이머(매일 점검, 다음 05:29 UTC)가 만료 30일 전부터 실제 갱신 + `renew_hook` nginx reload |
| 대시보드 저장·수동매도 확인 | 백엔드 Origin 검사 루프백 실측 — `https://auto.dkstock.cloud` 404(인증 통과) / `https://evil.example` 401 |
| 서버 마지막 상태 14:08 재시작 | 92e75f3 full, 기동 오류 0, 이미지 코드 확인, API 200, https 401(§2 표) |
| 되돌리기 = 컷오프 배수(2.5)를 20 으로 | 해당 전략 `max_lot_ratio_mult=20.0`, PUT 즉시 / SQL 다음 재시작 |
| 월요일 "지난 5영업일 수준(하루 1~4건)" | `[oversized_fallback]` 09-03 4 · 09-04 1 기준(1~4건/일). `[fallback_cap_config]` 09-04 4 는 설정 알림이라 따로 센다. `[fallback_notional_capped]` 는 09-01~05 0행이라 "0건 유지"가 기준 |
| 월요일 기록을 찾는 곳 | `system_logs` 조회 기본 + 파일 로그 grep 보조(§3.2·§5). 20:10 리포트 미도달 |
| 핵심 파일 여덟 곳 | 8영역 = `src/engine/{risk,order_engine,session,scanner,strategy_registry}.py` · `src/api/order.py` · `src/realtime/**` · `src/auth/**`(루트 `CLAUDE.md`) |
| 파일의 원본 지문 | 8영역 승인 시 소스 세그먼트 sha 핀 절차 |
