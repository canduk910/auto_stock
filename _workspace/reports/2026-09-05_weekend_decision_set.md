# 09-05(토) 주말 결정 세트 처리 보고 — 아침 리포트 D1~D11 의 처리 (09-05 04:30 ~ 12:04 KST)

> 사용자 지시(09-05 09:0x): "D8 진행 / D3 자문 / D4 월요일 별도 작업 / D5 dkstock.cloud / D11 진행 / 나머지 권고안대로" + 후속 "커밋·푸시·장외 배포 포함, D8 은 EC2 cron 자동 실행, 서브도메인 auto.dkstock.cloud".
> 이 문서는 아침 리포트(`_workspace/reports/2026-09-05_night_autonomous_work.md`)의 **후속**이다. 새벽 구간의 발견·수치는 그 문서가 정본이고, 여기서는 반복하지 않는다.
> 집계 창 = 커밋 `157f3a8..c6c95e9`(아침 리포트 커밋 직후 04:30 ~ 12:04). 초안은 `..540e2d9` 로 끊었으나 사실 대조 검토가 지적한 대로 540e2d9 의 CI 실패 → 핫픽스 → 12:10 배포가 창 밖으로 빠져 **c6c95e9 까지 넓혔다**(부록 B F-3). 마지막 배포 = 12:10(c6c95e9, 호출자 EC2 확인 완료).

## 0. 한눈에

| 항목 | 결과 |
|---|---|
| 커밋 | **19건**(04:30~12:04) = 코드 7 · 테스트 5 · 문서 7(하네스 정의 3건 포함). 분류 매핑 = `feat/fix/refactor` → 코드, `test` → 테스트, `docs/harness` → 문서(변경 파일 전부 `.claude/`·`CLAUDE.md`·`_workspace/`) |
| 배포 | **재시작 또는 화면 갱신을 동반한 배포 6건**(06:39 · 08:00 · 08:38 · 09:15 · 10:59 · 12:10) — backend 재시작 5회 + frontend 전용 1회(08:38, backend 무접촉). 전부 토요일 = 장외. 그 밖에 `none` 모드(빌드·재시작 없음, 마커만 전진) 배포 2회(06:46 · 07:05)는 문서 커밋을 pull 만 했다(§2) |
| CI | 실패 **3회(창 안)** — 06:31 db0f063 · 08:22 4a70ed7 · 11:56 540e2d9. 전부 테스트/가드 결함, 구현 무결함, 즉시 핫픽스(§2). 하루 합계는 c6c95e9 커밋 메시지가 "4건" 으로 센다(새벽 04f070d 계열 = 아침 리포트 참조). 재발 방지 = c6c95e9 tdd-engineer 가드 설계 금기 6조 |
| 결정 세트 D1~D11 처리 | D8 ✅ cron 등록 · D9 ✅ 배포 · D3 ✅ 자문 완료(→ 결정 대기) · D4 명세 초안(→ 월 승인 대기) · D5 ✅ TLS 1단계 배포(→ 사용자 DNS 대기) · D10 명세 초안(→ 주중) · D11 ✅ 카드 10장 전부 처리·배포(→ DailyReportTab 서식 결정 대기) · D1·D2·D6·D7 변경 없음(권고대로) |
| 사고 | 장중 서버 중단 0 · 매매 사고 0 · 기동 오류 0(배포 6건 기준) |
| 새로 답할 것 | **6건**(§4) — 급한 순 = ① D5 DNS A 레코드(사용자 행동, 오늘) ② D4 월요일 `order_engine.py` 1곳 승인(월 아침) ③ D3 권고 B 채택(월 확인 후, 미리 정해도 됨) ④ DailyReportTab 시각 서식(시점 자유) ⑤ D10 착수 시점 ⑥ D8 후속 채널 리졸버(월 09:30 프로브 결과 후) |

## 1. 집계 창 커밋 목록 (신→구, 19건, `git log --date=format:%H:%M 157f3a8..c6c95e9`)

| 커밋 | 시각 | 분류 | 제목(요약) |
|---|---|---|---|
| c6c95e9 | 12:04 | 문서(하네스) | harness: tdd-engineer 가드 설계 금기 6조 — ast.dump 핀·git grep 스캔·bare git diff HEAD·caplog 레벨·프론트 읽는 백엔드 가드·vitest 동적 import(09-05 CI 실패 4건에서 확정) |
| cd8b8e2 | 12:03 | 테스트 | test: cycle259 게이트 스냅샷 가드 미사용 subprocess import 제거 |
| 9f96fe7 | 12:03 | 테스트 | test: cycle259 가드 2건 CI 정합 — S4a 핀 ast.dump → 소스 세그먼트 sha(파이썬 3.12/3.13 차이), S4b git grep → AST 호출 스캔(540e2d9 CI 핫픽스) |
| 540e2d9 | 11:56 | 코드 | refactor: `get_gate_snapshot()` 단일 소유자 + `log_analysis_engine` 수집/집계 분할 (cycle259, 카드 ⑥⑦, D11 마지막) |
| 2b2e6f2 | 10:51 | 코드 | refactor: 관측 배관 표준화 — `KstDailyEmitCap` + `observer_trace.trace_observer_failure` (cycle258, 카드 ④⑤) |
| 1b30dd6 | 09:09 | 테스트 | test: cycle257 승인 sha 핀 4 dict 비움(자기소멸) |
| 4cf479a | 09:08 | 코드 | refactor: 사이클 26 시간대별 채널 전환 죽은 코드 삭제 + 문서 정정 (cycle257, 카드 ⑧, 8영역 scanner·scheduler 승인 D11) |
| 4fdeee2 | 08:30 | 테스트 | test: cycle251 프론트 계약 가드 재조준 (4a70ed7 CI 핫픽스) + 오케스트레이터 규칙 1줄 |
| 4a70ed7 | 08:22 | 코드 | refactor(frontend): KST 포맷 유틸 단일화 + `AccountGate.level` 유니온 정정 (cycle256, 카드 ⑨⑩) |
| 06673f7 | 07:52 | 코드 | feat: HTTPS(TLS) 1단계 준비 — auto.dkstock.cloud (cycle255, D5) |
| 4ab6984 | 06:58 | 문서 | docs: D8 프로브 cron 등록 완료 기록 |
| 579fe54 | 06:57 | 코드 | fix: `channel_probe.sh` cron 기본값 00:30 UTC(=09:30 KST) 정정 + 로그 시각 KST 고정 |
| 475f741 | 06:41 | 문서 | docs: D3 자문 결과 — 권고 B(`min` 합성, K_ρ 유지) |
| ad23fe7 | 06:39 | 문서(하네스) | harness: report-writer 2차 — 드라이런 모호 지시 16건 반영 |
| cda21fd | 06:32 | 테스트 | test: `channel_probe.sh` 가드 — 주석 줄 제외 (db0f063 CI 핫픽스) |
| db0f063 | 06:31 | 코드 | feat: D8 채널 프로브 자동 실행 스크립트 + D9 REST 폴 조기 시작 09:00:30 + D4/D10 착수 명세 |
| 6146ee9 | 06:31 | 문서(하네스) | harness: report-writer 에이전트 + cycle-report 스킬 + 자율 진행·승인 빈도 계약(코드 변경 0) |
| 7e20520 | 05:21 | 문서 | docs: 아침 리포트 사실 대조 정정 |
| cf46167 | 04:30 | 문서 | docs: 아침 리포트 §0 결정 항목 범위 정정 |

창 시작점 157f3a8(04:29, 아침 리포트 본 커밋)은 창 밖이다.

## 2. 배포 이력 (호출자 검증 — EC2 SSH: git HEAD == `.deployed_sha` 마커 · `docker ps` created 시각 · startup 로그 · 오류 grep · 루프백 API 200; gh run 로그로 시각·모드 재대조)

| 시각(KST) | 커밋 | 내용 | 모드 | 백엔드 | 확인 |
|---|---|---|---|---|---|
| 06:39 | ad23fe7 | 하네스 1·2차 + D8 프로브 스크립트(db0f063 원본, cron 기본값 09:30 오기) + D9(`SWING_REST_POLL_EARLY_START` 09:05→09:00:30, scheduler.py 상수 1줄) 누적 | full | 재시작 | 마커·startup |
| 08:00 | 06673f7 | cycle255 TLS 1단계 준비 | full | 재시작 | ACME 경로 무자격 404 · 루트 401 · `certbot-www` ubuntu 소유 |
| 08:38 | 4fdeee2 | cycle256(+CI 핫픽스) — frontend 전용 | frontend | **무접촉**(08:00 기동 유지) | 마커·401 |
| 09:15 | 1b30dd6 | cycle257 죽은 코드 삭제 | full | 재시작 | 오류 0 · 이미지 안 scheduler 3,864L · API 200 |
| 10:59 | 2b2e6f2 | cycle258 관측 배관 표준화 | full | 재시작 | 오류 0 · `observer_trace` import · API 200 |
| 12:10 | c6c95e9 | cycle259 게이트 스냅샷 단일화 + 엔진 분할(540e2d9) + CI 핫픽스 2(9f96fe7·cd8b8e2) + tdd-engineer 가드 금기(c6c95e9) 누적 | full | 재시작(12:10) | EC2 HEAD·마커 c6c95e9 · 기동 오류 0 · `/api/portfolio/risk` 계좌 게이트 9키 실측 · collector 재export 동일 객체 · API 200 |

- **CI 실패 3회(창 안), 전부 가드 결함·구현 무결함**: ① 06:31 db0f063 — `channel_probe.sh` 가드가 주석 줄의 토큰을 위반으로 오탐 → cda21fd(주석 제외) ② 08:22 4a70ed7 — frontend 전용 커밋인데 백엔드 가드(`test_cycle251_report_account_gate.py`)가 프론트 파일을 읽어 실패 → 4fdeee2(가드 재조준 + 오케스트레이터에 "프론트 전용 사이클도 `grep -rl frontend/ tests/unit` 가드 실행" 규칙) ③ 11:56 540e2d9 — 새 가드 2건이 CI 에서만 실패(S4a `ast.dump` 핀은 파이썬 3.12/3.13 출력이 달라 로컬과 CI 가 불일치, S4b `git grep` 은 미추적 파일을 못 보고 주석까지 잡음) → 9f96fe7(소스 세그먼트 sha 핀 + AST 호출 스캔)·cd8b8e2(미사용 import 제거). 540e2d9 의 Deploy 는 CI 실패로 skipped(12:01) 였고 **배포가 진행 중이었던 적은 없다** — 핫픽스 CI 성공 뒤 12:10 full 배포로 c6c95e9 가 올라갔다. 재발 방지 = c6c95e9 가 tdd-engineer 정의에 가드 설계 금기 6조를 넣었다(ast.dump 핀·git grep 스캔·bare `git diff HEAD`·caplog 레벨·프론트 읽는 백엔드 가드·vitest 동적 import).
- **문서 전용 커밋 4건의 배포**: 475f741(06:41)·4ab6984(06:58)는 CI 가 뜨지 않았지만(`paths-ignore`) **앞 커밋의 CI 완료가 띄운 Deploy 가 최신 main 을 pull** 했다 — 06:46 `mode=none prev=ad23fe7 head=475f741` · 07:05 `mode=none prev=475f741 head=4ab6984`(빌드·재시작 없음, 컨테이너 Running 유지, 마커만 전진). cf46167·7e20520(04:30·05:21)은 배포 없음. 부수: 코드 커밋 579fe54(cron 기본값 정정)는 07:05 none 배포로 EC2 에 갔고, 06:39 full 배포에 실린 스크립트는 db0f063 원본(기본값 09:30 오기)이었다. EC2 cron 은 06:57 에 손으로 정확한 값(`30 0 7 9 *`)을 등록했으므로 운영 영향 0. 스크립트는 호스트 도구라 pull 만으로 반영된다.
- 하네스 정의 3건: 6146ee9 는 db0f063 과 같은 분에 푸시돼 CI 는 푸시 head 인 db0f063 에만 떴다(자체 CI run 없음). ad23fe7 은 자체 CI 성공 → 06:39 full 배포에 실렸다. c6c95e9 는 12:10 배포의 head.
- 모든 재시작은 토요일 = 장외. `market_blind_secs` 는 월요일 부팅 로그에서 0 이어야 한다.

## 3. 결정 세트 처리 상세

### 3.1 D8 — 채널 프로브 자동 실행 (완료, 월 09:30 자동)
- `tools/ops/channel_probe.sh`(db0f063 + 579fe54): 후보를 순서대로 POST 해 2개 수락까지 시도(409 = 다음 후보) → 5분 간격 상태 3회 → 전부 DELETE → 로그. 기본 후보 12종목(포렌식 4일 공통 no_feed 유동주 + KRX 단독 ETF 예비, 부적격은 엔드포인트가 409 로 거른다). 안전 = 프로브 창 ≤15분 · `in_desired_now=true` 관측 시 즉시 해제 · 종료 시 무조건 DELETE · 자기 cron 항목 제거.
- EC2 cron 등록 완료(09-05 06:57): `30 0 7 9 *` = **월 09-07 00:30 UTC = 09:30 KST**. ⚠️ 호스트 crontab 은 UTC(실측 `date` 가 UTC) — 처음 09:30 으로 적었던 기본값을 579fe54 에서 정정.
- 결과 위치 = `~/auto_stock/logs/channel_probe_20260907.log` + 시스템 로그 `[krx_channel_probe]`(20:20 일일 루틴이 읽는다).
- 판정 = `received=true` 면 가설 확정(KRX 전용 채널이 nxt_false 종목 시세를 보낸다) → D8 후속 = 채널 리졸버(아침 리포트의 "근본 해결", 8영역 4파일) 착수 여부 결정. 15분간 미수신이면 반증 → KIS 문의.

### 3.2 D9 — 스윙 REST 폴 조기 시작 (배포 완료 06:39)
- `SWING_REST_POLL_EARLY_START` 09:05 → **09:00:30**(scheduler.py 상수 1줄, 라인 수 불변, 테스트 갱신). 보유 종목(held_only) 60초 폴이 시가 직후부터 돈다.
- D+1 정상 표시 = 09:00:3x 부터 `[swing_rest_poll_summary]` held_only.

### 3.3 D3 — 터틀 1주 폴백 랏의 ρ 잔여 노출(F-9) 자문 (완료, 결정 대기)
정본 = `_workspace/domain_consult/cycle254_turtle_fallback_rho_exposure.md`(409줄, domain-expert, 읽기 전용 자문).

- **권고 B = `min` 합성 채택, K_ρ 2.5 유지, 파라미터·DB·전략 파일 변경 0.** `_apply_ratio_notional_cap` 의 "K축이 심사하면 즉시 return" 조기탈출 **한 조건만** 좁히고 `probe_error` fail-open 은 남긴다. 동반 개정(자문 §6) = 조건 1개 + 테스트 2건 + docstring 2곳(`_apply_budget_limit`·`_emit_ratio_cap_config`) + 정본 3곳(루트 `CLAUDE.md` · `00_leader_trading_rules.md` · cycle245 스펙).
- **전제 = 라이브 `sizing_mode == turtle`.** F-9 는 두 전략이 실제로 터틀 사이징으로 돌 때만 실재한다. 아래 수치는 그 전제 아래의 **구조적 천장**이고, 실제 여부는 월 09-07 `[ratio_cap_config]` 판독으로 확정한다(선결, 아래).
- **잔여 노출의 정체 = 관측된 랏이 아니라 구조적 천장.** donchian 예산 390,300원(자문 §2.1 표; 검산 2,602,038 × 0.15 ≈ 390,306) 전부를 1주에 넣을 수 있다 = 순자산 **15.0%**, ρ배수 5.00. kojiro 는 `price_filter_max` 500,000원(시스템 설정, 전 전략 공통 종목 풀 필터)에 막혀 = 순자산 **19.2%**, ρ배수 3.86. 즉 "한 종목 20%, 최대 5종목" 분산 계약(donchian `position_ratio 0.20 × max_positions 5`)을 1주 폴백이 100% 로 깬다. 아침 리포트의 "설계 금액의 최대 5배" 와 같은 뜻이다 — 설계 금액이 예산의 20% 이므로 5배 = 예산 전부.
- **왜 K축이 못 막나** — K축은 유닛 축(`cap_qty = floor(K×B×r÷ATR)`)이라 ATR 이 작을수록 상한이 커지고 명목 천장이 없다. `min` 합성이 실제로 행위를 바꾸는 창 = **ATR% < 2.00%(donchian) / 2.41%(kojiro)**, 계좌 크기 무관. "고가주 문제"가 아니라 "저변동 고가주 문제".
- **손절이 못 막는다** — 폴백 랏은 `_entry_atr` 미스탬프라 고정%손절(donchian 라이브 DB −6.0%). 390,300원 랏의 정상 손절 손실 **−23,418원(순자산 0.90%)** = 설계 유닛 리스크 1,952원(0.075%)의 **12배**. −30% 갭이면 순자산 4.50%(donchian) / 5.76%(kojiro).
- **비용 실측 0** — cycle242 자문의 120영업일 터틀 1주 폴백 **실측 11랏 중 결과가 바뀌는 랏 0건**(관측 최저 ATR% donchian 3.1 · kojiro 3.3 = 창 밖). 격자 **1,728 조합** 차분 = 차이 122건 **전부 1주 폴백 랏·전부 축소·수량 증가 0**. cycle242 테스트 97 passed / 0 failed(무손상). 실패로 바뀌는 테스트 = `test_f245_7b` 1건(결정 ⑦ 재확인 단언) + 라벨 `backstop→on` 채택 시 1건.
- **채택 후 컷오프**(순자산 2,602,038 기준) = donchian **195,150원**(7.5%) · kojiro **323,952원**(12.4%). kojiro 가 큰 이유는 K_ρ 가 아니라 weight 0.30 — 별건(F-2 계열, 아래 ④).
- **선결 확인(이것부터)** — 월 09-07 `[ratio_cap_config]` donchian·kojiro 행의 `cap=` 판독: `cap=backstop` = 터틀 활성 = F-9 실재 → B 진행 / `cap=on` = ρ축이 이미 전량 심사 → **변경 불필요**(워크리스트 "터틀 전환 시 선결" 로 재분류). 전략별로 갈릴 수 있다. 판독 주체 = 메인 세션.
- 병행 권고 F-1 = `price_filter_max` 500,000 → 250,000(DB 1줄, 코드 0) — 잔여를 독립적으로 절반 닫지만 전일종가 판정이라 갭업 추격에서 샌다. **시스템 설정이라 7전략 전부의 종목 풀에 걸린다**(다른 5전략도 25만 원 초과 종목이 후보에서 빠진다). B 와 배타가 아니라 보완.
- 사람이 결정할 것(자문 §10) = ① 결정 ⑦ 반전 여부 ② 라벨 `backstop→on` ③ F-1 병행 ④ kojiro weight 0.30 재검토(별건) ⑤ 배포 창(`src/**` = full 재시작 → 보유 중이면 15:30 이후).
- 매매 행위 코드 변경이라 **사용자 결정 후 착수**(사이클 254 후보).

### 3.4 D4 — `_bought_today` 선기록(F-10) (명세 초안, 월요일 승인 대기)
정본 = `_workspace/specs/cycle_next_D4_bought_today_after_fill.md`.
- 사실: 4전략이 `check_buy_signal` 안에서 주문 전에 `_bought_today.add` — BFB(`bull_flag_breakout.py:1093`) · VCP(`vcp_breakout.py:1160`) · donchian(`donchian_swing.py:1644` 돌파 확정 분기, `:1619` 갭 스킵 분기는 의도적 표식이라 대상 아님 — **HEAD c6c95e9 기준**, 명세 파일의 1726/1701 은 db0f063 시점 값이라 월요일 착수 시 갱신) · kojiro(`kojiro.py:853/857/864`). 관문(cycle242 K축·cycle245 ρ축)에서 수량 0 이 되거나 잔고 부족·KIS 거부면 주문은 안 나가는데 표식은 남아 그날 재시도 불가 → BFB·VCP(비중 합 25%) 당일 표본 영구 소실.
- 권고 A = `StrategyBase.on_buy_order_placed(ticker, order_no, qty)` 기본 no-op 훅 + `order_engine.execute_buy` 가 `place_order` 성공 직후(주문번호 매핑과 같은 동기 영역, `await insert_trade` 전) 호출. 접촉 = `strategy_base.py` + 전략 4파일 + **`order_engine.py` 1곳(8영역 승인)**. `scheduler.py`·`risk.py` 무접촉. 도메인 자문 불필요(표식 시점 정정).
- D+1 정상 표시 = `[bought_today_marked] reason=order_placed` INFO 1회/종목/일.
- 착수 순서 = 사용자 승인 → 명세 확정 → Red → Green → Verify(주문 성공 경로 byte 동일) → 장외 배포(15:30 이후) → D+1.

### 3.5 D5 — TLS 1단계 (cycle255 배포 완료 08:00, 사용자 DNS 대기)
- 배포 내용 = HTTP 템플릿에 ACME 챌린지 location 1블록(`auth_basic off` 없이 토큰만 무자격 200) · 443 은 **별도 템플릿 + compose 오버레이** `docker-compose.tls.yml`(인증서 없이 443 을 켜면 nginx 가 80 까지 안 뜬다 — 실측) · 호스트 마커 `.tls_enabled` 가 있을 때만 배포 스크립트가 오버레이를 붙임 · `tools/ops/tls_enable.sh`(dig → 웹루트 권한 → ACME 200 확인 → certbot webroot 발급 + reload 훅 → `fullchain.pem` 확인 뒤에만 마커 → frontend 단독 up → **사후 검증 폴링, 실패 시 자동 원복** → `renew --dry-run`). backend·`.env`·Dockerfile diff 0. 검증 = 실 nginx 변형 30여 건 실측, 가드 33+14+22(뮤테이션 14/14).
- 현재 상태 = 80 그대로, 아무것도 안 바뀜. 배포 확인 = ACME 경로 무자격 404(파일 부재가 정상) · 루트 401 · `certbot-www` ubuntu 소유.
- **사용자 할 일 = ① DNS A 레코드 `auto.dkstock.cloud → 3.38.228.74` 등록.** 그 뒤 ② EC2 `sudo snap install certbot --classic` ③ `LE_EMAIL=… bash tools/ops/tls_enable.sh` ④ 루틴 2개 BASE `https://auto.dkstock.cloud` + 클라우드 환경 허용 도메인 추가 는 **메인 세션이 수행**(호출자 꾸러미 "등록되면 제가 `tls_enable.sh` 실행"). 전환은 frontend 단독이라 장중에도 가능(backend 무접촉, D6 미적용). ⑤ 1주 안정 후 2단계(리다이렉트·HSTS·자격 회전).

### 3.6 D10 — asyncpg 풀 `acquire()` 타임아웃 (명세 초안, 주중)
정본 = `_workspace/specs/cycle_next_D10_pg_acquire_timeout.md`.
- `src/db/pg.py` 5곳(`fetch/fetchrow/fetchval/execute/executemany`)의 `acquire()` 에 타임아웃이 없다 — 풀 고갈 시 모든 DB 호출 무한 대기(cycle250 이 300s 로 막은 hang 의 공통 뿌리). 설계 = `_ACQUIRE_TIMEOUT_SECS = 30.0` + `[pg_acquire_timeout]` WARNING 1회/일 + 풀 사용량 metrics 병기. 재시도 예외 집합에는 넣지 않음(풀 고갈은 재시도로 안 풀린다).
- 본체 = 호출자 전수 3분류((a) 흡수 (b) 상위 전파 — 태스크 생존 (c) 트랜잭션 순서). 8영역 호출자(`order_engine` `insert_trade` 등)는 동작 변경 0 이지만 실패 모드가 바뀌므로 승인 대상.
- 착수 조건 = 8영역 호출자 목록 승인 → 주중 장외 배포 → D+1 `[pg_acquire_timeout]` 0건.

### 3.7 D11 — 리팩토링 카드 10장 (전부 처리·배포)
①②③ 새벽 처리(아침 리포트). 이번 창 = ⑨⑩ cycle256 · ⑧ cycle257 · ④⑤ cycle258 · ⑥⑦ cycle259.

| 사이클 | 카드 | 내용 | 검증 |
|---|---|---|---|
| 256 (4a70ed7+4fdeee2, 08:38 frontend) | ⑨⑩ | `utils/kst.ts` 신설(`formatKstHHMM`·`formatKstDateTime`·`kstTodayISO`, 잘못된 입력 `'—'`) + `PortfolioRiskCard` 1사이트 위임 + `GateLevel = 'ok'|'warn'|'block'|'error'`(`| string` 이 유니온을 삼키던 결함) + `eval_timeouts_today?` 선반영. ⑨ 는 점진 원칙대로 1사이트 한정 — **DailyReportTab 서식 전환(`2026. 9. 7. 9시 5분 0초` → `2026-09-07 09:05:00`)은 사용자 가시 변경이라 결정 대기.** 기존 13 KST 사이트 점진 이관 후속 | 뮤테이션 10/10 · vitest 521 PASS · `tsc -b` 0 · 'garbage' 입력이 HEAD 에선 카드 전체 크래시(`RangeError`)였던 것을 `'—'` 로 개선 |
| 257 (4cf479a+1b30dd6, 09:15 full) | ⑧ | 사이클 26 시간대별 채널 전환 죽은 코드 삭제 — `get_active_tick_tr_ids`·`_TIME_*` 7상수(scanner −61L), `_board_transition_loop`·`_atomic_board_transition`·`TIME_*_PRESUBSCRIBE`(scheduler 3,999→3,864L). f7f0766(2026-05-20) 이후 **108일간 src 호출 0**. 시간대에 따라 통합 채널↔KRX 전용 채널을 바꾸려던 옛 설계이고, 월요일 채널 프로브(D8)와는 별개 — 근본 해결 자리 `TICK_TR_ID_KRX/NXT` 2줄은 보존(리졸버 자리). 문서 5곳(README·architecture·realtime/engine CLAUDE)이 "동작 중"으로 서술하던 것 정정 — 09-05 포렌식이 오도될 뻔. 8영역 승인 = D11, sha 핀 한시 등록 후 1b30dd6 에서 비움. 인계 = `handler.py:78` 주석(realtime 무접촉 제약, 리졸버 사이클) | ast 776 · engine 3,838 · realtime 338 · routes 169 · db 622 PASS · 되살림 뮤테이션 → AST A1 FAIL 확증 |
| 258 (2b2e6f2, 10:59 full) | ④⑤ | `KstDailyEmitCap`(KST 날짜 경계 자기 리셋 + `emit_once`) + `observer_trace.trace_observer_failure`(debug 항상 + WARNING 1회/(marker,key)/일, never-raise). 날짜 키 리셋 손 복제 22곳·관측기 실패 처리 4방언 통일. strategy_base 11 헬퍼 day 필드 5개 제거, donchian 7 cap + 50L 메서드 삭제(옛 B 형태는 debug 로거 사망 시 `check_exit_signal` 400/400 RAISED 실측 → 무전파). 8영역·scheduler·kojiro diff 0 | 차분 **13,340건 비교**(조합 5,000 · KST 롤오버 콜 5,040 · 로거 사망 1,500 · 틱 1,800)에서 수량·게이트·신호 차이 0 — 차이는 설계된 것뿐(전일 stale 키 제거 · 삼켜지던 관측 실패 747건의 debug 노출) · 뮤테이션 27/27 · 6,413 PASS. ⚠️ 의미 전환 — 실패 흔적 서식이 `observer_failed` 공통 토큰(옛 서식 grep 합산 금지). 잔존(8영역 권고) = `risk.py:244,419`·`scanner.py:388`·`kojiro.py:987` |
| 259 (540e2d9 → 핫픽스 9f96fe7·cd8b8e2 → c6c95e9, **12:10 full 배포 완료**) | ⑥⑦ | ⑥ 20:10 리포트(9키)와 `/api/portfolio/risk`(8키)가 같은 계좌 위험 감시 상태를 다른 형상으로 내던 것을 `get_gate_snapshot()`(8키 + `eval_timeouts_today`) 하나로 통일. ⑦ `log_analysis_engine.py` 922→293L, 수집/집계 12함수 + 정규식 6 을 `log_metrics_collector.py`(690L)로 byte 동일 이동, 재export(`__all__`) — 이관 2단계(OpenAI 은퇴, D2) 삭제 범위가 파일 하나가 된다. CI 실패 1회(가드 2건 = 파이썬 버전 의존 핀 + git grep 스캔, 구현 무결함) → 핫픽스 → 배포 | 고정 입력 JSON sha256 3자 일치(8,085B) · bundle byte 동일 · 라우트는 키 1개 추가 외 동일 · 뮤테이션 10/10 · engine 3,925 · routes 169 · ast 776 · db 622 PASS. 배포 확인(호출자) = 재시작 12:10 · 기동 오류 0 · `/api/portfolio/risk` 계좌 게이트 9키 실측 · collector 재export 동일 객체 · API 200. D+1 = 20:10 리포트 정상 + `account_gate` 9키 + 카드 정상 |

D11 잔존 = 8영역 권고 4곳(관측 배관, 위 표) · DailyReportTab 서식 결정 · `handler.py:78` 주석(리졸버 사이클).

### 3.8 D1 · D2 · D6 · D7 — 변경 없음(권고대로)
D1 리포터 비밀번호 유지 · D2 OpenAI 경로 09-19 까지 병행 후 결정 · D6 주간 자문 정본 위치 09-08 첫 산출물 후 · D7 리포트 판독 채널 유지.

### 3.9 하네스 — report-writer 에이전트 + cycle-report 스킬 + tdd-engineer 가드 금기 (6146ee9 → ad23fe7 → c6c95e9)
- 사용자 결정(09-05 아침) "리포트 에이전트를 새로 만들고, 승인을 너무 자주 요구하지 말고 긴 작업 주기의 끝에 같은 보고서를 만들자".
- 1차(6146ee9, 코드 변경 0) = 에이전트 정의 · 스킬(트리거 4, 2렌즈 검토) · `template.html` · 기준 예시 · CLAUDE.md "자율 진행과 승인 빈도" 절(사전 승인 범위 = 8영역·scheduler 무접촉 ∧ 장외 창(20:00~20:15 금지) ∧ 원복 가능 — 셋 모두; 매매 행위 코드 변경은 위치 무관 승인 + domain-consult). 적대 검토 확증 16건 반영.
- 2차(ad23fe7) = 사이클 250~252 초안 드라이런에서 나온 모호 지시 16건 반영(draft 산출 위치·스킬 로드 시점·마지막 메시지·창 밖 항목·표 생략·M 정의·반올림 대응표·커밋 분류·종목명 출처·미배포 pill·60자 규칙·'제가' 주체·검증 방법 필수·정의 재로드). 정의 파일 수정은 **새 세션**에서 반영(드라이런 실측).
- 3차(c6c95e9, tdd-engineer) = 09-05 CI 실패 4건에서 확정한 가드 설계 금기 6조 — ① `ast.dump` 핀(파이썬 버전 의존) ② `git grep` 스캔(미추적 파일 누락·주석 오탐) ③ bare `git diff HEAD` 동결 가드 ④ caplog 레벨 조작 ⑤ 프론트 파일을 읽는 백엔드 가드 ⑥ vitest 동적 import.
- 이 보고서가 report-writer 의 첫 실전 산출물이다.

## 4. 결정 대기 (급한 순, 6건)

| # | 항목 | 답해 주실 것 | 제안 |
|---|---|---|---|
| 1 | **D5 DNS A 레코드** `auto.dkstock.cloud → 3.38.228.74` 등록(사용자 행동, 도메인 관리 화면) — **오늘** | "등록했어" | 등록 즉시 메인 세션이 certbot 설치 → `tls_enable.sh` → 루틴 2개 주소 갱신. 장중 가능(frontend 단독). 실패 시 스크립트 자동 원복 |
| 2 | **D4 월요일 착수 승인** — 8영역 `order_engine.py` 1곳(주문 접수 뒤 `_bought_today`) — **월 아침** | 월 아침 "D4 착수해" | 권고 A, 자문 생략, 배포 15:30 이후 |
| 3 | **D3 권고 B 채택** — 결정 ⑦(두 캡 상호배타) 반전. 선결 = 월 `[ratio_cap_config]` donchian·kojiro `cap=` 판독(메인 세션) — **월 확인 후, 미리 정해도 됨** | "터틀이 켜져 있으면 진행해" / "보고 듣고 다시 물어봐". F-1(`price_filter_max` 25만, 7전략 공통) 병행 여부도 | 자문 권고 = B 채택 + 라벨 `on` + F-1 병행. `cap=on` 이면 변경 불필요. 채택 시 배포 full → 보유 중이면 15:30 이후 |
| 4 | **DailyReportTab 시각 서식** `2026. 9. 7. 9시 5분 0초` → `2026-09-07 09:05:00` — **시점 자유** | "바꿔" / "그대로" | 바꿈(대시보드 다른 카드와 통일). frontend 전용 = 무재시작 |
| 5 | **D10 착수 시점** — 호출자 전수 + 8영역 호출자 목록 승인 | 요일 하나 | 화~목 중 장외, 명세 §3 목록을 먼저 보여 드린 뒤 착수 |
| 6 | **D8 후속 — 채널 리졸버 착수** — 월 09:30 프로브 결과가 정한다(자동 실행, 승인 완료) | 지금은 없음 | 월 결과 보고 후 8영역 4파일 승인 요청 |

호출자가 넘긴 결정 목록 = 6건(M=6). 정본 워크리스트에 추가 결정은 없다. 순서는 호출자 후보(① DNS ② D3 ③ DailyReportTab ④ D4 ⑤ D10 ⑥ 리졸버)에서 **D4 를 앞당겼다**(월요일 착수 승인이 D3 판독보다 시점상 선행) — 작성자 판단.

## 5. 월요일(09-07) 확인 목록 (07:55 부팅 후, 메인 세션이 확인·보고)

아침 리포트 §5 항목은 그대로 유효하다. 이번 창이 추가한 항목:
- [ ] 부팅 정상 · 기동 오류 0 · `[tick_blind_boot] market_blind_secs=0` — cycle257·258·259 의 첫 월요일 부팅
- [ ] **D3 선결**: `[ratio_cap_config] strategy=donchian_swing … cap=` / `strategy=kojiro … cap=` 값 판독(`backstop` = 터틀 활성 → B 필요 / `on` = 불필요). `cutoff_price` 병기. 배포 후 라벨 전환의 유일한 대조군이므로 값을 기록해 둔다
- [ ] cycle257: `[tick_coverage]` 정상 표시 불변(구독 채널 변경 0)
- [ ] cycle258: `observer_failed` WARNING **0건**, 기존 마커 빈도 불변
- [ ] cycle259: 20:10 리포트 정상 생성 + `portfolio_risk_snapshot.account_gate` 9키 + 대시보드 카드 정상
- [ ] D9: 09:00:3x 부터 `[swing_rest_poll_summary]` held_only
- [ ] D8: 09:30 `~/auto_stock/logs/channel_probe_20260907.log` + `[krx_channel_probe] action=start|stop` — `received=true/false`. `in_desired_now=true` 로 즉시 해제된 종목이 있으면 그 사실도
- [ ] `[account_risk_eval_timeout]` 0 · `[no_feed_held] tickers=[000815, 003490]` 1행(보유 4종목 중 2 — 09-05 현재 positions 4; 아침 리포트의 9 는 09-04 포렌식 시점) · `[stale_force_retry]` 09:05~15:20 ≈0
- [ ] 20:20 Claude 일일 루틴 첫 자동 실행(`ext_provider=claude-routine` 행 + Notion + 대시보드 "Claude 분석")

## 6. 승인 시 절차 (주체 명시)
- **D5** — 사용자: DNS A 레코드 등록. 메인 세션: ① `dig` 확인 ② EC2 certbot 설치 ③ `LE_EMAIL=… bash tools/ops/tls_enable.sh`(사후 검증 폴링 http 401 ∧ https 401 ∧ running, 실패 시 자동 원복) ④ 루틴 2개 BASE·허용 도메인 갱신 ⑤ 1주 뒤 2단계 제안.
- **D4** — 사용자: 월 아침 승인. 메인 세션: team-leader 명세 확정 → tdd-engineer Red(수량 0 → 표식 없음 → 재평가 가능 / 주문 성공 → 표식 / 거부 → 없음 / donchian 갭 스킵 유지 / 동기 영역 await 0 AST / 8영역 sha 핀) → backend-dev Green → tester(주문 성공 경로 byte 동일) → 15:30 이후 배포 → D+1 `[bought_today_marked]`.
- **D3** — 메인 세션: 월 07:55 후 `cap=` 판독 → 보고. 사용자: B 채택 여부. 채택 시 메인 세션: 조건 1개 좁힘 + `test_f245_7b`·라벨 테스트 개정 + docstring 2곳 + 정본 3곳(`CLAUDE.md`·`00_leader_trading_rules.md`·cycle245 스펙) 개정 + 회귀 F-9a~e + 뮤테이션 4표적 → 15:30 이후 full 배포 → D+1 정상 표시 7종(`system_logs` 직접 조회, 20:10 리포트 미도달).
- **DailyReportTab** — 사용자: "바꿔". 메인 세션: frontend 전용 커밋 → frontend 모드 배포(무재시작).
- **D10** — 사용자: 요일. 메인 세션: 호출자 전수 목록 제시 → 8영역 호출자 승인 → 사이클 → 장외 배포.

## 7. 배운 점 · 정정한 사실
- **EC2 호스트 시계는 UTC.** cron 기본값을 09:30 으로 적었다가 실측 후 `30 0` (00:30 UTC) 로 정정(579fe54). 스크립트 로그 시각은 `TZ=Asia/Seoul` 로 고정.
- **프론트 전용 사이클도 백엔드 가드가 프론트 파일을 읽는다**(cycle251 계약 가드) → CI 실패 1회. 오케스트레이터에 규칙 추가(4fdeee2).
- **가드가 주석 토큰에 오탐**(db0f063) → 주석 줄 제외(cda21fd).
- **가드 핀을 `ast.dump` 로 걸면 파이썬 버전에 묶인다**(3.12 로컬 통과 · 3.13 CI 실패), **`git grep` 스캔은 미추적 파일을 못 보고 주석까지 잡는다**(540e2d9) → 소스 세그먼트 sha + AST 호출 스캔(9f96fe7). 하루 4건의 CI 실패를 묶어 tdd-engineer 정의에 가드 설계 금기 6조(c6c95e9).
- **문서가 죽은 코드를 "동작 중"으로 서술하면 다음 조사자가 속는다** — 사이클 26 채널 전환은 108일간 호출 0 이었는데 문서 5곳이 활성으로 적어 09-05 포렌식이 오도될 뻔(cycle257 에서 삭제·정정).
- **인증서 없이 443 을 켜면 80 까지 죽는다**(cycle255 실측) → 마커는 `fullchain.pem` 확인 뒤에만, 스크립트가 순서를 강제. **nginx `map` 중복은 기동 실패가 아니라 조용한 키 소실**(F3) → 텍스트 가드가 유일 방어.
- **문서 전용 push 도 앞 커밋의 Deploy 가 pull 한다** — CI 는 `paths-ignore` 로 안 뜨지만 직전 CI 완료가 띄운 Deploy 가 최신 main 을 `none` 모드로 가져간다(06:46·07:05 실측). "배포 자체 없음" 은 부정확했다(초안 정정).
- **정의 파일 수정은 새 세션에서 반영된다** — 드라이런에서 구판 report-writer 가 실행됐다.

## 부록 A. 쉬운 말 리포트(HTML)에서 단순화한 곳 — 정확값 대응표

| HTML 표기 | 정확값(출처) |
|---|---|
| 커밋 19 (코드 7 · 테스트 5 · 문서 7) | §1 표, `git log 157f3a8..c6c95e9` 19건 |
| 서버에 올린 작업 묶음 6 (재시작 5 · 화면만 1) | §2 표 — 재시작 또는 화면 갱신을 동반한 배포만 센다. `none` 모드 2회(06:46·07:05)는 제외 |
| 테스트 서버(CI) 검사 실패 3회 | 창 안 3회(db0f063·4a70ed7·540e2d9). 하루 합계 "4건" 은 c6c95e9 커밋 메시지 기준 |
| 금액 상한(설계 금액의 2.5배) · 상한 배수 2.5 | K_ρ = `max_lot_ratio_mult` 2.5(cycle245, 유지). 설계 금액 = `position_ratio × 전략 예산`. `min` 합성 = K축(유닛)·ρ축(명목) 두 상한 중 작은 수량(자문 §4 권고 B) |
| 약 39만 원(순자산의 15%) | donchian 예산 390,300원(자문 §2.1 표; 검산 2,602,038 × 0.15 ≈ 390,306), 순자산 15.0% |
| 약 50만 원(순자산의 19%) | kojiro `price_filter_max` 500,000원, 순자산 19.2%(자문 §2.1) |
| 약 19만 5천 원 / 약 32만 4천 원 | 채택 후 컷오프 195,150원(7.5%) / 323,952원(12.4%)(자문 §5.2) |
| 정상 손절 약 2만 3천 원(순자산 0.9%) | −23,418원, 0.90%(자문 §2.4) |
| 설계상 한 번 손절에서 잃기로 한 금액 약 2천 원 | 설계 유닛 리스크 1,952원(순자산 0.075%)(자문 §2.4) |
| 설계 리스크의 약 12배 | 23,418 ÷ 1,952 = 12.0(자문 §2.4) |
| 하루 변동폭이 주가의 2% 아래 | ATR% < 2.00%(donchian) / 2.41%(kojiro)(자문 §2.2) |
| 실제 1주 매수 11건 | cycle242 자문 120영업일 터틀 1주 폴백 실측 11랏(자문 §3.4) |
| 약 1,700가지 조합 | 격자 1,728 조합, 차이 122건 전부 1주 폴백·축소(자문 §3.3) |
| 코드 조건 한 줄 | 조기탈출 조건 1개 좁힘 + 테스트 2건 + docstring 2곳 + 정본 3곳(자문 §4·§6) |
| 13,000번 넘는 비교 | 5,000 조합 + 5,040 롤오버 콜 + 1,500 로거 사망 + 1,800틱 = 13,340건(changelog cycle258). "차이 0" 은 수량·게이트·신호 기준이고 설계된 차이(전일 stale 키 제거·실패의 debug 노출)는 있다 |
| 22곳 손 복제 | 날짜 키 자기 리셋 손 복제 22곳(changelog cycle258, 파일 수는 정본 미기재) |
| 108일 | f7f0766(2026-05-20) 이후 src 호출 0(changelog cycle257) |
| 보유 4종목 중 두 종목(삼성화재우 000815 · 대한항공 003490) | 09-05 현재 positions 4 중 2. 아침 리포트 HTML 의 "9종목" 은 09-04 포렌식 시점 값(아침 리포트 부록 B 대응표에 "09-05 현재 4" 명시) |
| 매수 후보 최고 주가 기준 50만 원 → 25만 원 | `system_config.price_filter_max` 500,000 → 250,000(F-1, 자문 §10-3). 시스템 설정이라 7전략 공통 |
| 서버 마지막 상태 12:10 재시작 | c6c95e9 full 배포, 호출자 EC2 확인(§2 표 마지막 행) |

## 부록 B. 검토 반영 — 2렌즈 지적 42건 처리 (쉬운 말 30 · 사실 대조 12)

전부 수용 41 · 참고만 1(F-12, 보고서 오류 아님). 불수용 0.

### 쉬운 말 렌즈 (HIGH 3 · MEDIUM 18 · LOW 9)
| # | 심각도 | 지적 | 처리 |
|---|---|---|---|
| P-1 | HIGH | 콜아웃 "답할 것 하나" vs 타일 "결정 카드 4" 시점 모순 | 수용 — 콜아웃을 "오늘 1(DNS) · 월요일 아침까지 3" 으로 나누고 타일 라벨 "오늘 1 · 월요일까지 3, 전체 6개 항목 중" |
| P-2 | HIGH | 계좌 위험 감시 / 계좌 게이트 / 계좌 감시 세 이름 | 수용 — "계좌 위험 감시" 로 통일, 화면 표기 '계좌 게이트' 는 괄호 1회 |
| P-3 | HIGH | D3 "금액 상한 없음" 을 무조건 사실처럼 + 아침 "최대 5배" 와 다리 없음 | 수용 — 증상 상자를 "터틀 방식으로 돌고 있다면" 조건부로 + "5배 = 예산 전부(설계 금액이 예산의 20%)" 한 줄 + 결론 상자 주체 "제가" |
| P-4 | MEDIUM | "자문 담당 에이전트" vs 아침 "매매 자문 기능" | 수용 — 첫 등장 "프로그램 안의 매매 자문 기능(자문 담당 에이전트)", 이후 "매매 자문 기능" |
| P-5 | MEDIUM | 표의 'B' 라벨 | 수용 — "D8 후속" + 아침 리포트의 '근본 해결' 로 연결 |
| P-6 | MEDIUM | 09:15 행 75자 + 채널 프로브와의 관계 미설명 | 수용 — 두 문장 분할 + "월요일 채널 확인과는 별개, 근본 해결 자리는 남겨 둠" |
| P-7 | MEDIUM | '유니버스' 무풀이 + "전 전략에 걸림" 의 결과 없음 | 수용 — "매수 후보 종목 범위(유니버스)" + "7개 전략 모두 … 다른 5개 전략도 25만 원 넘는 종목은 후보에서 빠짐"(`price_filter_max` 가 시스템 설정임을 코드로 확인) |
| P-8 | MEDIUM | '명세' 무풀이 | 수용 — 첫 등장 "작업 계획서(명세)", 이후 "작업 계획서" |
| P-9 | MEDIUM | "붉어졌다" 은어 + 주어 어긋남 | 수용 — 제안 문구대로 |
| P-10 | MEDIUM | '서명 7종' | 수용 — "기록에서 정상 표시 7가지가 찍혔는지 제가 확인" |
| P-11 | MEDIUM | '실패 테스트'·'경로' | 수용 — "고칠 점을 잡아내는 테스트를 먼저 씀 … 정상 주문이 이전과 똑같이 처리되는지 비교" |
| P-12 | MEDIUM | D3 카드 판독·배포 주체 없음 + `(backstop)` 토큰 | 수용 — 제안 문구대로(주체 "제가", 토큰 제거) |
| P-13 | MEDIUM | 4절 "제가 확인" vs "알려 주세요" 주체 모순 | 수용 — "직접 보실 경우," 조건 추가 |
| P-14 | MEDIUM | no_feed_held 전체 대비 없음, 아침 9 vs 현재 4 | 수용 — "보유 4종목 중 두 종목 … 아침의 9종목은 9월 4일 기준" + 부록 A 시점 정정 |
| P-15 | MEDIUM | D1·D2·D6·D7 처분 누락 | 수용 — 콜아웃에 한 줄 |
| P-16 | MEDIUM | 06:39 행 "2차 반영도 함께 올라감" | 수용 — "이 보고서를 쓰는 리포트 에이전트의 규칙 수정도 함께 올림(6절 참조)" + 표 아래에 문서 7 ↔ 문서 전용 4 차이 설명 |
| P-17 | MEDIUM | '관측' 3회 무풀이 | 수용 — "기록 장치" 로 통일(첫 등장 풀이) |
| P-18 | MEDIUM | "손절을 탑니다/손절되면" + 12배 분모 없음 | 수용 — 제안 문구대로 + 부록 A "약 2천 원 ↔ 1,952원" |
| P-19 | MEDIUM | '꼬리'·'반으로 접힘' | 수용 — "최악의 경우 한 종목에 들어가는 돈이 절반(약 39만 → 약 19만 5천 원)" |
| P-20 | MEDIUM | '포트'·'죽습니다' | 수용 — "암호화 접속 통로(포트 443) … 기존 접속 통로(포트 80)까지 함께 멈춤" |
| P-21 | MEDIUM | kojiro 50만 원 근거 없음 | 수용 — "후보 최고 주가 기준인 50만 원" |
| P-22 | LOW | '함수'·'엔진' | 수용 — "공용 부품" / "일일 리포트를 만드는 프로그램" |
| P-23 | LOW | '화면 서버' + 두 뜻 한 문장 | 수용 — "대시보드 쪽만 건드리고 매매 프로그램은 건드리지 않아" 두 문장 |
| P-24 | LOW | 판독/확인 혼용 | 수용 — HTML 은 "확인" 으로 통일(pill "월요일 기록 확인 후"). 원문 md 는 개발자용이라 `cap=` 판독 용어 유지 |
| P-25 | LOW | "D11-⑨" 번호 + 피동 + 주체 | 수용 — "D11 중 화면 2건의 하나 — 일일 리포트 탭의 시각 표기" + "'바꿔'라고 하시면 제가 화면만 고쳐 올립니다" |
| P-26 | LOW | line 156 74자·주체 없음 | 수용 — 제안 문구대로 분할 |
| P-27 | LOW | 피동 잔여 5곳 | 수용 — 전부 능동으로 |
| P-28 | LOW | 제목 '낮 동안' | 수용 — "오전 동안"(창 04:30~12:04) |
| P-29 | LOW | '별도 항목' 위치 없음, '호출' 무풀이 | 수용 — "원문 3.3절에 별도 항목(kojiro 비중 재검토)" / "저장소를 쓰는 곳" |
| P-30 | LOW | 바닥글 해시 노출·'결정 세트'·천장/상한 | 수용 — 해시는 "(내부 참조: …)" 만, "아침에 주신 결정 열한 가지", "금액 상한" 통일 |

### 사실 대조 렌즈 (HIGH 2 · MEDIUM 2 · LOW 8)
| # | 심각도 | 지적 | 처리 |
|---|---|---|---|
| F-1 | HIGH | 540e2d9 "배포 진행 중" 은 사실 아님 — CI 실패 → skipped → 핫픽스 → 12:10 c6c95e9 full 배포 완료 | 수용 — 전부 "12:10 배포 완료" 로. 호출자 EC2 확인(재시작 12:10·오류 0·9키·재export·API 200) 반영. §1 표 마지막 행 시각 12:10, 타일 6건·재시작 5회 |
| F-2 | HIGH | 창 안 CI 실패는 2회가 아니라 3회(540e2d9 포함), 하루 4회 | 수용 — §0·§2·§7·HTML 전부 3회로. 셋째 원인(ast.dump 핀·git grep)과 금기 6조 추가 |
| F-3 | MEDIUM | 창을 540e2d9 에서 끊으면 실패·배포 경로가 창 밖 | 수용 — 창을 `157f3a8..c6c95e9` 로 넓혀 19건(7·5·7), 04:30~12:04 |
| F-4 | MEDIUM | 문서 커밋 "배포 자체 없음" 부정확 — 475f741·4ab6984 는 none 모드 Deploy 가 pull, 579fe54 도 07:05 로 EC2 도달 | 수용 — §2 불릿 정정 + "서버에 올린 작업 묶음" 을 재시작·화면 갱신 동반 배포로 한정 + §7 배운 점 추가 |
| F-5 | LOW | D4 donchian 줄번호 stale(1726/1701 → 1644/1619) | 수용 — HEAD c6c95e9 기준으로 정정(grep 재확인), 명세 갱신은 월요일 착수 시 |
| F-6 | LOW | 390,300 = 순자산 × 0.15 검산 6원 차이 | 수용 — 출처(자문 표)와 검산(≈390,306) 분리 표기 |
| F-7 | LOW | 13,340 단위 혼합 + "불일치 0" 과장 | 수용 — 단위 병기 + "차이는 설계된 것뿐" |
| F-8 | LOW | "22곳/5파일" 의 5파일 근거 없음 | 수용 — "/5파일" 삭제 |
| F-9 | LOW | 자문 §6 "계약 문안 2절" 대응 없음 | 수용 — "docstring 2곳 + 정본 3곳" 으로 §6 과 통일 |
| F-10 | LOW | 6146ee9 자체 CI run 없음 | 수용 — "db0f063 과 함께 푸시돼 그 CI 에 실림, ad23fe7 은 자체 CI" 로 |
| F-11 | LOW | 결정 순서 재배열 근거 미표기 + 타일 시점 | 수용 — §4 각주 "D4 를 앞당김" + 타일 시점 분리(P-1 과 동일 처리) |
| F-12 | LOW | 입력 꾸러미의 "11:40 push" 오기 | 참고 — 보고서는 11:56 으로 바르게 적었다. 호출자 꾸러미 재사용 시 정정 필요 |
