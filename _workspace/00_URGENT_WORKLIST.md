# 🟡 09-08(화) 대기열 — 주간 사용량 소진, 09-10(목) 오후 재개까지 새 작업 보류

> **다음 세션(09-10 목 오후 이후)은 이 절부터 읽는다.** 09-07(월) 저녁~심야 작업 직후
> 사용량이 바닥나 새 작업을 벌이지 않고 여기 쌓아만 둔다. 아래 순서대로 착수한다.
> 배경 보고서 2건(같은 날, 서로 다른 구간) — 낮:
> https://claude.ai/code/artifact/45724d37-e89e-46f9-99d3-efe3240e1e76 (07:45~16:40) ·
> 저녁: https://claude.ai/code/artifact/919f8759-7673-49ca-92d5-4d2f03b8cdce (16:40~04:25).
> 원문은 `_workspace/reports/2026-09-07_weekday_verification.md` ·
> `_workspace/reports/2026-09-07_evening_four_defects.md`.

## ✅ TLS 2단계 가동 완료 (09-08 05:44)

사용자 지시 "보안접속 가동 바로 해보자" — `ROUTINE_HTTPS_CONFIRMED=1 bash tools/ops/tls_stage2_enable.sh`
실행, 사후 검증 전부 통과(80→301·ACME→404·443→401+HSTS). cycle267 정규식 시정이 정확히 작동함을
실전에서 확인. 후속 ① 두 루틴(일일 20:20·주간 20:30) 프롬프트의 http 예비 주소 제거 완료
(일일은 09-07 밤에 이미, 주간은 이번에 신규 시정 — `/api/health`→`/health` 404 버그 동반 시정).
**아직 안 한 것** = ② `bash tools/ops/rotate_basic_auth.sh`(Basic 자격 회전) — 사용자 결정 대기.

## ✅ 관측 자동화 완료 — EC2 크론 등록, 사람 개입 없이 자동 실행

사용자 지시 2·4번 — "관측기록 뽑아서 로컬에 저장, 목요일 사용" / "수요일·목요일도 추가 기록,
많을수록 좋다". 세션 없이도 데이터가 쌓이도록 EC2(UTC) 크론 등록(`~/auto_stock/_observation_dumps/`).

⚠️ **설계가 두 번 바뀌었다 — 사용자가 두 번 다 잡아냈다.**
1차: "임의 대형주 15종목을 H0STCNT0 하나로만" → 사용자 "NXT 채널로는 프로브 안 해?" →
자문 정본의 P-1/P-2/P-3 설계(`_workspace/consult/2026-09-07_channel_split_by_session.md`
"cycle253 프로브로 무엇을 어떻게 재는가" 절)로 재설계. 이 과정에서 **결정적 함정 발견**
— `[open_scope_observe]` 캡이 **종목 단위**(`_open_scope_observe_cap.should_emit(ticker)`,
`handler.py`, 채널 무관)라 같은 종목을 나중에 다른 채널로 재구독해도 마커가 **또 안 찍힌다**
(그날 첫 틱에서 이미 소모). 자문이 이를 예견해 지시한 "측정의 이중화 — 정본은 EC2 host DEBUG
로그의 원문 프레임" 을 실측 확인(`~/auto_stock/logs/auto_stock.log` 에 `< TEXT '0|H0STCNT0|...'`
형태로 **캡 없이** 남음) — 채널 간 비교는 이 원문 로그로만 가능하다.
2차: "09:30~10:30 이 굳이 장 시작 후일 필요가 있나" → "08:40-08:55 NXT 구독 → 5분 전환 →
09:00-09:15 KRX 로 비교하자" — **이게 발의(채널 분리)가 실제 운영될 방식 그대로를 재현하는
가장 직접적인 실험**이라 그대로 채택. 다만 09-08 당일은 이미 09:11 이라 08:40~08:55 창을
놓쳐 (가) 오늘은 최선 시도(즉시 수동 실행) (나) 09-09(수)에 정확한 설계로 재실행, 이원화했다.

### (가) 09-08(화) — 최선 시도, 09:12 수동 실행 완료

`activate_probe.sh` 를 크론이 아니라 **즉시 수동 실행**(09:30 대신 09:12, 이유 = 이미 09:05
매수창을 지나 자문의 유일한 회피 조건은 충족했고, 일찍 구독할수록 그 종목의 본장 체결을
놓칠 확률이 줄어 유리하다는 사용자 지적을 반영). P-1=002990(금호건설) · P-2=100840 둘 다
**즉시 첫 틱 수신 확인**(P-1 이 무송출 결함에도 H0STCNT0 프레임을 받은 것 자체가 이미 답 하나).

| 크론(UTC) | KST | 스크립트 | 하는 일 |
|---|---|---|---|
| (수동 실행 완료) | 09-08 09:12 | `activate_probe.sh` | P-1(무송출 후보 9종목)·P-2(어제 프리장 체결 확인 105종목 후보) 를 H0STCNT0 로 순서대로 시도, 409 는 건너뛴다 — **완료, 결과는 위 참조** |
| `0 1 8 9 *` | 09-08 10:00 | `switch_to_p3.sh` | P-2 종목의 H0STCNT0 구독을 해제하고 같은 종목을 H0NXCNT0 로 재등록 = P-3 |
| `30 1 8 9 *` | 09-08 10:30 | `deactivate_and_dump_probe.sh` | `[open_scope_observe]` 마커 + 원문 프레임 로그 덤프 → 전부 해제 |

### (나) 09-09(수) 08:40~09:15 — 정확한 설계(전환 경계 재현)

| 크론(UTC) | KST | 스크립트 | 하는 일 |
|---|---|---|---|
| `40 23 8 9 *` | 수 08:40 | `wed_activate_nxt_and_p1.sh` | P-1 은 H0STCNT0 로, **P-2 는 H0NXCNT0 로**(프리장 관측) 구독 시작 |
| `55 23 8 9 *` | 수 08:55 | `wed_switch_p2_to_krx.sh` | P-2 를 H0NXCNT0 에서 **해제 후 H0STCNT0 로 재등록**(장 시작 직전 전환) |
| `15 0 9 9 *` | 수 09:15 | `wed_dump_and_cleanup.sh` | 원문 프레임 로그(NXT 구간+KRX 구간 나란히 비교) + 마커 덤프 → 전부 해제 |

### 공통

| 크론(UTC) | KST | 스크립트 | 하는 일 |
|---|---|---|---|
| `0 11 * * *` | **매일** 20:00 | `dump_daily_observations.sh` | `[kojiro_gap_observe]`·`[open_scope_observe]`·`[open_source_compare]`·`[breakout_open_confirm]` 4마커를 그날치 JSON 으로 저장(48시간 시한 대응) |

- **사전 검증 완료**: GET 인증 200 · POST/DELETE/로그검색 흐름 전부 확인. 여섯 스크립트 `bash -n` 문법 통과.
  실 API 호출로 409(already_tick_subscribed) 분기·200 성공 경로 둘 다 실측.
- **⚠️ 이 데이터는 EC2 디스크(`_observation_dumps/`)에 쌓인다 — "로컬"(이 Mac)이 아니다.**
  목요일 세션 재개 시 최우선으로 `scp -i auto-stock.pem ubuntu@3.38.228.74:~/auto_stock/_observation_dumps/'*'  <로컬경로>` 로 끌어와야 한다. 프로브 성공 종목은
  `active_tickers.txt` 에 남는다(다음 세션이 재확인할 근거).
- **⚠️ 목요일 이후 정리 필수** — 이 프로브 작업 이전에 EC2 에 다른 크론 작업이 **전혀 없었다**
  (09-08 착수 전 `crontab -l` 확인 = 공백). 아래 크론은 전부 `_observation_dumps/` 아래 스크립트만
  가리키므로 **경로 문자열로 정확히 걸러 지운다** — 사용자가 우려한 "다른 크론까지 지워버리는"
  사고를 막는다.

  **1단계(읽기 전용 — 먼저 실행해 뭐가 남는지 확인)**:
  ```bash
  crontab -l | grep -v "_observation_dumps/" | grep -v "관측 자동화\|전환 경계 프로브"
  ```
  이 출력이 **비어 있어야 정상**이다(=프로브 관련 항목이 전부이고 남길 다른 작업이 없었다는 뜻).
  09-08 실측으로 정확히 8줄(주석 2 + 실행 6)이 이 필터에 걸리고 그게 크론 전체 줄 수와 일치함을
  확인했다. 만약 이 시점에 다른 작업이 추가돼 있어서 출력에 뭔가 보이면 **2단계로 넘어가지 말고
  먼저 그 내용을 확인**한다.

  **2단계(실제 삭제 — 1단계 확인 후)**:
  ```bash
  (crontab -l | grep -v "_observation_dumps/" | grep -v "관측 자동화\|전환 경계 프로브") | crontab -
  ```
  적용 후 `crontab -l` 로 빈 크론탭인지 재확인한다. `crontab -r`(전체 삭제) 나 `crontab -e` 로
  손으로 줄을 고르는 방식은 **쓰지 않는다** — 위 필터 명령이 실수 없는 유일한 정본이다.

  daily dump 스크립트(`dump_daily_observations.sh`) 는 반복 실행에 안전(파일 덮어쓰기, 부작용
  없음)하나 방치하면 디스크만 쌓이므로 위 정리에 포함해 반드시 함께 지운다.
- 프로브 판정 기준은 여전히 비대칭이다(아래 3번 참조).

## 🔵 결정 대기 — 사용자 답 필요 (재개 시 순서대로)

1. **cycle265(시가 오염 근본 시정 — VB·LTV 목표가 기준을 KRX 조회값으로 교체) 시기·방향 리포트**
   — 사용자가 요청함. **오늘 09:30~10:30 프로브 결과(EC2 에 쌓임, 위 참조)를 먼저 scp 로 끌어와
   판독한 뒤** 작성한다. 판정 = `oprc_hour` 가 `09xxxx` 나오면 발의(채널 분리)에 긍정 증거
   (단, **3종목 표본일 뿐 전 종목 긍정 아님** — 자문 정본 명시), `08xxxx` 면 발의 기각 및
   cycle265 단독 진행. 자문 정본 = `_workspace/consult/2026-09-07_channel_split_by_session.md`.
2. **09:05 `[swing_poll] execute_buy 실패` 오탐 시정** — 사용자가 "고치자" 승인했으나
   `src/engine/order_engine.py` 가 8영역이라 **아직 착수 안 함**. 원인 = 체결통보가
   `insert_trade` await 도중 착지하는 race(기존 가드는 "검사 전 도달" 만 덮는다). 매수·DB 는
   정상(UNIQUE 인덱스가 이미 방어), 실손실은 `cached_buyable_at` 캐시 미무효화 1건뿐 → 위험 LOW.
3. **F-3(고지로 갭 판정 오염 실제 시정 — `risk.py:646` skip 목록에 kojiro 추가)** — 관측(cycle268)
   만 배포됐고 시정은 **행위 변경**이라 별도 승인 필요. **목요일에 대기 작업으로 올려 둔다**
   (사용자 지시 5번) — 화~목 쌓인 관측(위 자동화)을 먼저 판독한 뒤 착수 여부 판단.
4. **F-3b(momentum·LTV 익일청산 갭률 동일 오염, 방향은 반대로 손실 확대가 아니라 기대수익 훼손)**
   — 워크리스트에 등재만 하고 미착수. 착수 여부 결정 안 됨.
5. **Basic 자격 회전(`rotate_basic_auth.sh`)** — TLS 2단계 가동 후속 절차, 미실행.
6. **오늘 판독 문서 2건 커밋 여부** — 09-08 새벽 커밋 `1863e32` 로 이미 커밋·푸시 완료
   (`_workspace/reports/2026-09-07_evening_four_defects.md` 포함). **해소됨.**
7. ~~**cycle269(보조 시세계정 토큰 매일 장중 재발급 드리프트 시정)**~~ — **✅ 09-08 22:xx
   커밋·푸시 완료.** 구현·검증(백엔드 7,533 passed·`scheduler.py` 3,898/3,900L·8영역 diff 0) +
   루트 `CLAUDE.md` 하네스 표 갱신(15행 유지) + `docs/HARNESS_CHANGELOG.md` append 전부 반영.
   신규 파일 `src/engine/quote_token_refresh.py`(매일 15:45 KST 강제 재발급). **D+1(09-09 수)
   확인 사항** — 배포 첫날은 옛 앵커(14:48) 탓에 장중 자연 재발급이 한 번 더 날 수 있다(예상,
   미실측). `[quote_token_refresh] scheduled at=15:45` 배선 카나리아가 09-09 15:45 대에
   찍히는지, D+2(09-10 목)부터 장중 자연 재발급이 완전히 사라지는지 확인할 것.
8. **고지로 밴드폭(`band_width` = EMA 중기-장기 너비) 을 순위뿐 아니라 최저치 필터로도 적용**
   — 사용자 발의(2026-09-08). 현재 `kojiro_indicators.py` 의 `band_width = |ema_m - ema_l|`
   는 **후보 순위 매김 가중치**(`rank_w_band=0.3`)로만 쓰이고, 매수 관문 필터로는 안 쓰인다.
   스테이지1(정배열)이어도 세 선 간격이 좁으면 사실상 횡보에 가까운데 지금 구조로는 못 거른다.
   제안 = 순위 가중치는 그대로 두고 **최소 너비 미달 시 매수 후보에서 원천 제외**하는 관문
   추가. **매매 진입 임계를 바꾸는 전략 정체성 영역이라 착수 전 `domain-consult` 필수**
   (해당 파라미터가 `PARAM_RANGES` 제외 정체성 상수인지 확인 후 임계값·검증 방법 자문).
9. **필옵틱스(161580) 09:00 매도 미체결·중복 COMPLETED 기록 — 근본 원인 시정**
   — 09-08 09:00 익일청산 매도(주문 0000267100, 지정가 38,800원)가 실제로는 체결되지 않았는데
   `trade_history` 엔 15:45 진짜 체결(주문 0001611100, 35,250원)과 완전히 같은 값으로 중복
   COMPLETED 기록됐다. 그 사이 6시간 45분 동안 `_selling`(매도중) 플래그가 안 풀려 손절·트레일링
   재평가가 막혀 있었다(15:45:40 stale watcher 가 뒤늦게 해제). 오늘 밤 20:10 정산 전 응급 조치로
   `0000267100` 행을 `CANCELLED` 로 정정(사용자 "지금 처리하자" 승인, 실행 상태는 이 세션 마지막
   메시지 확인) — **다음 세션은 이 정정이 실제로 반영됐는지(상태=CANCELLED, 20:10 정산에
   161580 이 2,000원으로만 잡혔는지) 먼저 확인**. 근본 원인(체결 미확인 매도 주문이 몇 시간이고
   방치되는 경로, 그리고 그 주문이 왜 COMPLETED 로 잘못 기록됐는지)은 **목요일 과제로 승인**
   (사용자 "근본 원인은 목요일에"). `src/engine/order_engine.py` 8영역 — 조사 후 시정은 승인 필요.

## 📌 09-08 새벽 확인 필요 (부팅 후)

- **07:45 부팅** — 포지션 12종목 복구 확인 · cycle263(일봉 껍데기 시정) 두 prepare 수렴 재확인
  (09-07 에 이미 확인됐으므로 이번엔 회귀 확인만).
- **20:20 루틴** — 모델 `claude-opus-5` 로 바뀜, 첫 시도 성공 여부 확인.
- **20:30 주간 자문 루틴(화요일 전용)** — 09-08 05:44 에 http 예비 주소 제거 + `/health` 시정
  완료. 오늘 밤 정상 작동 여부 확인(TLS 2단계 가동 이후 최초 실행).

## 📋 09-07 저녁~심야 완료분 요약 (배포·검증 완료, 재작업 불요)

| 커밋 | 사이클 | 내용 |
|---|---|---|
| `4d7a580` | cycle266 | 종목마스터 일봉 탭 흰 화면 시정(라우트 직렬화 + 프론트 방어) |
| `8d8f8d1` | cycle267 | TLS 2단계 HSTS 검사식 CRLF 결함 시정 |
| `a77f9c3` | cycle268 | 고지로 갭 판정 오염 관측(행위 변경 0) |
| `f4952bc` | — | 09-07 조사·자문·보고서 + 판독 정본 정정 |
| `1438e24` | — | cycle268 후속 정리(sha 핀 4곳 비움 — `test_g3_8` skip 되던 활성 피해 해소) |

배포 마커 `1438e24`, EC2 재기동 09-07 22:55, ERROR 0. 일봉 탭은 운영 API 로 `change_rate`
가 float 로 오는 것을 실측 확인함(배포 전 문자열 → 흰 화면).

## 🔴 절대 건드리지 말 것 (승인 없이는)
- `src/db/stock_master_daily.py::get_recent_daily` — 6전략 prepare + 터틀 사이징 `get_atr`
  + `get_donchian_high` + 수정주가 락 게이트 공유. 예외를 삼키는 결함이 있으나 여기서 고치면
  매매 행위 변경.
- `src/engine/risk.py`·`src/engine/order_engine.py`·`src/engine/scheduler.py` 등 8영역 전부.

---

# 🔴 최우선 과제 — BFB·VCP 매수 전면 차단 (2026-08-25 확정)

> **이 파일이 현재 최우선 작업 지시서다.** 새 세션은 다른 작업을 시작하기 전에 이 문서를 먼저 읽는다.
> 근거 보고서: https://claude.ai/code/artifact/75081207-15a8-4d43-9574-2352dae049b2
> 작성 시점 상태 = 미푸시 커밋 0 · 워킹트리에 미커밋 cycle221 잔류.
>
> **✅ P0-1 종결 (2026-08-28 사이클 228 게이트 전환 — 커밋 A `4e7b302` + B, 배포 대기)**
> 사이클 227 배포(a7245af) → 이틀 관측 would_pass 0/5 → 래치 선행 확정 → 사이클 228 이
> 게이트를 tick_volume 실측 + 충족 래치 + 추격 상한으로 전환(**매수 개방**, 비중 현행).
> 228-B = `_effective_setup` 구조 레벨 stamp 우선 복원(별도 커밋, D+1 귀인 분리).
> 다음 액션 = **15:30 NXT 애프터 이후 푸시**(KRX 장중 자제) → D+1 관찰(첫 체결·청산 경로
> 첫 실가동·`latch_age_sec`·`[setup_structure_conflict]`·진입 임계 재튜닝 금지 N=10).
> ⚠️ `[*_vol_gate_observe]` 마커 은퇴 — 08-28 전후 로그 같은 grep 합산 금지.
> tester 조건부 GO(`_workspace/test_report_cycle228.md`, 결함 6) → 228-C 로 D-1(C-6 가드
> 공허화, 뮤테이션 실증)·D-2(죽은 필드+invariant 경고 1회/일 cap)·D-3(release cap reason 축)
> 시정 완료. **이관 잔여**: D-4(read 예외 debug 단독 — no_data WARNING 동반이라 LOW 수용) ·
> D-5(대시보드 래치 상태 미노출 — 후속 사이클 후보, `get_targets_status` 키 추가만으로 가능).


---

## ✅ cycle266 — 종목마스터 "일봉 (30일)" 탭 결함 3건 시정 (2026-09-07, 매매 행위 변경 0 · 커밋 대기)

> 운영 EC2·운영 DB 실측(2026-09-07) 확정 — 흰 화면(Decimal→JSON 문자열 직렬화 + `ErrorBoundary`
> 부재) + "일봉 데이터 조회 실패" 오류 문구 오판(실제론 49.5% 미적재가 정상) + 라우트 fail-silent
> (`except Exception: rows=[]` 가 진짜 DB 장애를 404 로 은폐) 3건 시정. 도입 = `dc66026`(사이클
> 124, 2026-06-13) — 이 탭은 그날부터 오늘까지 한 번도 정상 동작한 적이 없었다. 상세 =
> `docs/HARNESS_CHANGELOG.md` 2026-09-07 행, `src/routes/CLAUDE.md`/`frontend/CLAUDE.md` 갱신분.
> 8영역·`scheduler.py`·전략 7파일·`src/db/stock_master_daily.py` diff 0. 검증 = 백엔드 7,321
> PASS(+5)·`tsc -b` 0·vitest 599(+7)·Playwright 34×4연속·뮤테이션 13/13 KILLED.

### 열린 후속 (이번 사이클 범위 밖 — 등재만)

- **F-1** `src/db/stock_master_daily.py::get_recent_daily` 가 DB 예외를 **자신이** 삼켜 `[]` 를
  반환한다(280~287행). 그래서 이번 사이클이 만든 라우트 500 경로는 오늘 **실질 도달 불가**이고,
  진짜 DB 장애도 여전히 404("적재 대상 아님")로 도착한다. 근본 시정은 그 db 모듈인데
  **6 전략 전부의 `prepare()`** + `get_atr`(터틀 사이징 ATR) + `get_donchian_high` +
  `_row_has_lock`(수정주가 락 게이트) + `market_regime.compute_etf_stage_signal` 이 공유 ⇒
  **사용자 승인 + `domain-consult` 선행** 대상.
- **B-4** `StockMaster` 페이지 전체가 여전히 `ErrorBoundary` 무방비다(이번 사이클은 일봉 탭
  렌더만 방어했다 — `toSafeNumber`/`formatSafeCount`/`formatSafeChangeRate`). 프로젝트 전체에서
  `ErrorBoundary` 를 갖춘 곳은 `components/DailyReportTab.tsx` 한 곳뿐이라, 같은 계열(값 타입
  오판 → 미검증 값에 `toFixed`/`toLocaleString` 직접 호출)의 결함이 다른 탭·다른 페이지에도
  잠재해 있을 가능성이 있다.
- **D-4** `src/routes/stock_master.py` 가 이번 시정으로 **338L**(상한 340L)까지 찼다 — 여유
  2행. 다음 이 파일에 손댈 사이클은 분리·리팩터부터 검토해야 한다.
- **D-5** 일봉 미적재 종목(운영 DB 실측 49.5%)에도 프론트가 60초 `refetchInterval` 폴링을
  계속한다(코드 사실 — `useQuery` 옵션에 조건부 중단 없음). 폴링이 실제로 지속되는지는
  이번 사이클에서 실측하지 않았다.

---

## ✅ cycle264 — 시가 `[7] STCK_OPRC` 스코프 **shadow 관측** (2026-09-06~07, **커밋·배포 대기** · 행위 변경 0)

> 사용자 승인(09-06) = **"전부 승인할게 진행시작하자"** — `src/realtime/**`·`scheduler.py` 접촉 포함.
> 자문 정본 = `_workspace/consult/2026-09-07_open_price_scope_filter.md`(§1.1 전제 반전 · §7.1 마커 설계 ·
> §8.1 배포 시점) · 조사 정본 = `_workspace/analysis/entry_price_0900_20260906/{code_trace.md,forensic.md}`.
> **변경 파일 = `src/realtime/handler.py` + `src/engine/scheduler.py` + 신규 leaf
> `src/engine/open_price_observe.py` 셋**(8영역 타 파일 · 전략 7파일 · `src/realtime/` 타 파일 diff 0).
>
> ### 🔴 이 사이클은 **관측만**이다. 시정이 아니다.
> `_parse_tick_prices` 는 **byte 동일**(소스 세그먼트 sha 핀)이고 `[7]` 에는 **여전히 스코프 필터가
> 없다.** 근본 시정 = **cycle265(후속 F-2), 다음 주말** — 아래 "🔴 열린 채로 남는 것" 절.

### 무엇을 했나 — 마커 3 (전부 INFO, 전부 never-raise)

| 마커 | 위치 | cap | 무엇을 재나 |
|---|---|---|---|
| `[open_scope_observe]` | `handler.py` (`_handle_tick`, `parsed` 성공 뒤) | 1회/ticker/일 | `[24] OPRC_HOUR`·`[27]`·`[34]`·`[43]` **원문** + `tick_open`(= `[7]` 파싱값) + `in_main_window` |
| `[open_source_compare]` | leaf `open_price_observe.py` (**09:05:30** 백그라운드 task) | 1회/(전략,종목)/일 | VB·LTV `main` 확정 종목의 `used_open` ↔ KRX REST `stck_oprc` + `delta_bp`·`target_used`·`target_if_rest`·`used_src`·`reason` |
| `[breakout_open_confirm]` | `scheduler.py` (기존 마커에 **추가**) | 기존과 동일 | `truth_confirmed`/`truth_total`(= `_open_confirmed` 직접 계수, 분모는 `_targets`) |

- **게이트와 라벨은 다른 축이다** — 게이트는 `[1] STCK_CNTG_HOUR` 가 MAIN 창(090000~153000) 안일
  때만 cap 을 태우고(프리장 틱이 cap 을 먹으면 코호트 **분모**가 죽는다), 라벨 `in_main_window` 는
  `[24]` 의 창 안/밖을 **모두** 남긴다(분모가 있어야 오염 **비율**이 나온다 — `[day_high_scope_skip]`
  은 skip 만 남겨 분모가 없었고 그래서 "93/287" 이 지금도 추정이다).
- **`[24]` 는 정규화 없이 원문 그대로** 남긴다(부재 `"?"`, 빈 문자열 `""` 는 서로 다른 사실).
- `[open_source_compare]` 가 **09:05:30** 인 이유 = KRX 시가는 프린트되면 종일 불변이라 언제 읽어도
  같고, 09:00~09:01:30 은 cycle262 보류 창 + 매수 주문 구간이라 전역 20건/초를 매수와 다투며,
  09:05 **정각**은 `_swing_buy_poll_loop` `BUY_WINDOW_START` 와 겹친다. throttle 5건/초.
- `target_if_rest` 는 `rest_oprc + target_offset` **산술**이다 — `on_open_price_confirmed()` 로
  계산하면 그 순간 보드 목표가가 REST 시가로 갈아끼워져 **행위 변경 = 제1 계약 위반**이다.

### ⚠️ 자문이 조사 정본의 전제 하나를 뒤집었다 (§1.1) — 판독 전에 반드시 읽을 것

`[breakout_open_confirm] confirmed=0 empty=55~65` 는 **"09:00:05 경로 무동작" 이 아니라 표시 버그**였다.
`_emit_breakout_open_confirm`(`scheduler.py:1676`)이 `_open_confirmed` 를 직접 세지 않고
`strategy.get_targets_status()` 를 거치는데, 그 함수가 `session_tracker.active ∩ tradable_boards` 로
보드를 가린다(`volatility_breakout.py:708-719`). 09:00:05~09:00:2x 에는 세션 트래커가 30초 주기 stale
캐시라 `active={PRE_NXT}` 이고 VB 는 `tradable_boards=["main"]` ⇒ **교집합 ∅** → `open_price: 0`.
같은 함수 **바로 앞줄의 비필터 로그**는 09-03 VB **51/65**, 09-04 VB **46/55** 확정을 말한다.

⇒ **REST 폴백은 고장이 아니다. 오염된 WS 캐시가 먼저 이겨 차례가 오지 않을 뿐이다.**
cycle265 의 (B) 는 새 배관을 까는 일이 아니라 **우선순위를 뒤집는 일**이다.
조사의 **결론(기준가가 KRX 09:00 시가가 아니다)은 그대로 유효**하고 증거가 하나 늘었다 — 09-03 LTV
프리장 보드 시가와 메인 보드 시가가 **4/4 동일**(000720 111,600 · 000880 123,000 · 001450 52,900 ·
003670 177,400). 단 이 표는 "09:00:19 값 = pre_nxt 보드 값" 이라는 **코드 모델 기반 해석**에 의존하므로
하드 증거가 아니라 **강한 정황**이다. 조사 두 문서에는 **정정 주석**을 달았다(원문 보존).

### 📋 D+1 판독 (월 2026-09-07 장중~장후) — 이 사이클의 유일한 산출물

1. **`[open_scope_observe]` 총 행 수를 먼저 센다.** 그 수가 오염 비율의 **분모**다.
   ⚠️ 분모로 "구독 슬롯 ~287" 을 쓰지 마라 — 그것은 **용량**이고 실사용 `[tick_coverage] subscribed=`
   는 09-03/09-04 기준 **107~148** 이다. 반대로 `_scan_loop` 5분 delta 가 구독을 회전시켜 하루 동안
   관측된 서로 다른 ticker 수는 슬롯 수보다 클 수도 있다. **~300행을 크게 넘으면 볼륨 재평가.**
2. **`[24] OPRC_HOUR` 분포** — 이 프로젝트가 이 필드를 보는 **첫날**이다(그 전까지 파싱 0건 =
   *한 번도 관측된 적이 없다*). 세 갈래로 갈라서 센다:
   (i) `08xxxx` = 프리장 시각 = **진짜 오염** (ii) `000000`/빈 문자열 = 무체결·부재
   (iii) 비숫자·파싱 실패. ⚠️ **`in_main_window=false` 를 그대로 오염으로 세지 마라** — 그 라벨은
   셋을 한 값으로 합친다. 원문 `oprc_hour` 가 보존돼 있으니 반드시 갈라서 본다.
3. **`[open_source_compare]` 3자 대조** — `used_open`(사용값) ↔ `rest_oprc`(KRX REST) ↔
   `stock_master_daily` 그날 KRX 시가(cycle263 배포로 16:00 적재가 살아났는지도 같이 확인).
   - ⚠️ **`delta_bp≈0` 을 그대로 "오염 없음" 으로 세지 마라.** `used_src=rest` 행은 09:00:05 폴백이
     이미 REST 시가를 심은 종목이라 대조가 REST↔REST 이고 `delta_bp=0.0` 이 **산술적으로 보장**된다.
     오염 판정은 **`used_src=ws` 행에서만** 성립한다.
   - ⚠️ `reason` 이 `ok` 가 아닌 행(`rest_zero`/`rest_error`)은 대조가 성립하지 않은 행이다 —
     "REST 가 전부 일치했다" 와 "REST 가 N 종목에서 아무것도 못 줬다" 를 **반드시 구분**해서 보고한다.
     그 구분이 cycle265 REST 폴백 배선의 성패다(09:05 무체결 저유동 종목이야말로 오염 확률이 가장
     높은 코호트라 **결측이 무작위가 아니다**).
   - `[open_source_compare] skipped reason=no_confirmed_target` 이 보이면 그날 대조는 **0행**이다
     (09:05:30 이후 재시작 등). 침묵이 아니라 이 한 줄로 드러나게 해 뒀다.
4. **`truth_confirmed` vs 기존 `confirmed`** — 09:00:0x 행에서 두 수가 갈라지면 §1.1 의 표시 버그가
   재현된 것이고(예상: `confirmed=0` 인데 `truth_confirmed≈46~51`), 09:35 행에서는 둘이 **같아야**
   한다(그때는 트래커가 MAIN 이라 마스킹이 없다). 이것이 정정의 자기 검증이다.
   `truth_total` 분모는 `_open_confirmed` 가 아니라 **`_targets`**(= 후보 전체)다.
5. 판독 결과는 **cycle265 착수 전에** `_workspace/analysis/` 에 기록한다. 로그는
   `system_logs` 에만 남고 전략 INFO 는 최근 며칠분만 잔존한다(cycle262 F-1 과 같은 만료 시한).

### 🔴 열린 채로 남는 것 — 근본 시정은 **cycle265**(후속 F-2)

`[7]` 오염은 전 시간대 공통이고(09:01:30 이후에도 53/93 = 57% 위반) **이 사이클은 아무것도 고치지
않았다.** 시정 방향(자문 §0 권고) = **소스에서 `[7]` 을 0 으로 강등하는 fail-closed 는 금지** —
`[7]` 은 VB 목표가 말고도 08:00 익일청산 갭 판정 · LTV 프리장 보드 목표가 · kojiro 갭스킵/시가아래
가드 · momentum 익일청산 갭률까지 **여섯 소비처**가 공유하고, 0 이면 *가드가 조용히 꺼지고*(kojiro)
*강제 청산으로 뒤집히고*(momentum) *프리장 매매가 통째로 죽는다*(LTV·익일청산). 권고는 **`[7]` 을
그대로 두고 `board="main"` 목표가의 기준가만 KRX REST(`stck_oprc`, `J`)로 갈아 끼우는** 방향이다.

- **선결** = 위 D+1 판독. **행위 영향** = VB 진입 추정 **−27.6%** ⇒ `src/realtime/**` 8영역 승인 +
  `domain-consult` 선행 + 킬스위치 `open_price_scope_mode`(`off`/`enforce`, **키 부재 = off**,
  `PARAM_RANGES`/`INT_PARAMS` 편입 금지, 배포 전 DB 선반영 금지 = 무음 실패) — 자문 §7.2/§8.2.
- cycle265 가 심을 마커 = `[open_scope_substituted]`(무엇으로 대체했다) ·
  `[open_scope_unresolved]`(**커버리지 손실 정본** — 0 이 아니면 "고치려다 매수를 잃고 있다") ·
  `[open_scope_config]`(카나리아, 1회/(전략,**값**)/일).
- ⚠️ **`scheduler.py` 여유가 3행뿐이다**(3,896L / 상한 3,900L) — **cycle265 는 leaf 위임을 전제로
  설계한다.**

### 적대 검증 15건 (HIGH 3 = 동일 사안 3렌즈 · MEDIUM 8 · LOW 4) — **전건 수용, 불수용 0**

- **HIGH — `scheduler.py` 3,979L 이 cycle257 영구 가드(<3,900)를 깬다.** 리포의 실제 예산은 계약서에
  적힌 4,000 이 아니라 **3,900** 이었고(cycle257 `test_cycle257_ast_dead_code_removed.py::
  TestA4SchedulerLineCount::test_line_count_below_3900`), cycle264 **자체 가드가 4,000 을 재는 바람에
  위반이 초록으로 덮이고 있었다**(실측 `1 failed / 7,276 passed`). ⇒ 관측 본체를 leaf
  `src/engine/open_price_observe.py`(327L, 신규)로 분리(cycle233 `account_risk_watcher` ·
  cycle259 `log_metrics_collector` 패턴 답습). **scheduler 3,864 → 3,896L**(HEAD 대비 +32).
  자체 상한을 `< 3900` 으로 조이고 **cycle257 리터럴과 자동 대조**하는 가드를 신설해 "느슨한 자체
  가드가 위반을 덮는" 재발을 구조로 막았다.
  - ⚠️ **파생 결정 2**: ① C7 접촉 범위가 **2 → 3 파일**로 확대됐다(8영역·전략 7파일·realtime 타 파일은
    여전히 diff 0, 신규 leaf 는 8영역이 아니다) ② **cycle265 는 여유 3행 위에서 설계해야 한다.**
- **MEDIUM 주요** — ① 좀비 task: `_open_source_compare_task` 를 `stop()`·finally **세 목록 전부**에
  등재(초안의 `_*_task_handle` 명은 cycle79 가드의 수집 패턴 `endswith("_task")` 에도 안 잡혀 조용히
  빠져 있었다. 종목당 0.2초 throttle 로 최대 ~28초를 도는 루프라 cancel 누락 시 `stop()` 이 REST
  버스트를 못 끊는다) + 본체가 `_running` 을 매 종목 확인해 즉시 이탈 ② 09:05:30 **이후** 재시작이면
  `main` 보드 시가가 아직 0 이라 전 종목 skip → 그날 **0행**: 2초 간격 최대 90초 준비 폴링 + 타임아웃
  시 `skipped reason=no_confirmed_target` 을 **침묵하지 않고** 남긴다(cycle224 교훈).
- **선재 결함 1건 동반 시정(테스트 전용)** — `tests/unit/engine/test_cycle252_stale_watcher_no_feed.py`
  가 모듈 전역 `stale_watcher_core._no_feed_held_logged` 리셋 훅 없이 `freeze_time("2026-09-07")` 을
  써, **실제 KST 날짜가 2026-09-07 인 날에만** 앞선 테스트가 소비한 날짜 키와 충돌해 붉어지는
  시한폭탄이었다(HEAD 에서 `git stash` 후 동일 재현 = cycle264 무관). autouse fixture 로 cap 을 새
  인스턴스로 갈아 끼워 날짜 의존을 제거했다(소스 무변경).

### 게이트 / 산출물

- 신규 가드 **3파일 70 테스트 함수** — AST `tests/unit/ast/test_cycle264_scope_and_pins.py` **8**
  (C7 접촉 범위 · 라인 상한 3,900 · cycle257 리터럴 대조 · `create_task`↔cancel 정합 · task 등재 ·
  C4 전략 진입 메서드 핀 · 마커 2파일 한정 · **킬스위치 파라미터 미도입**) · leaf
  `tests/unit/engine/test_cycle264_open_source_compare.py` **34** · handler
  `tests/unit/realtime/test_cycle264_open_scope_observe.py` **28**.
- 행위 불변(C4) = `_parse_tick_prices` 소스 세그먼트 sha 핀 + `_handle_tick` 의 `on_tick` 6-튜플
  골든 12케이스 + 전략 진입 메서드 3종 반환 핀.
- 8영역 sha 자매 가드 **4곳**(222a3 `_APPROVED_CONTENT_SHA` · 223 · 223f · 226)에
  `src/realtime/handler.py` 승인 항목 등재.

### 🔴 cycle268 (`a77f9c3`) — 커밋 직후 정리 + **48시간 시한**

**⏱ 시한부 — 이 마커는 스스로 영속되지 않는다.** `[kojiro_gap_observe]` 는 INFO 라
(a) `system_logs` 도달은 하지만 (b) **20:10 리포트에는 안 들어가고**
(`log_metrics_collector.pattern_by_level` 이 WARNING+ 만 담는다 — INFO 는 `level_counts` 숫자 하나뿐)
(c) **이틀 뒤 삭제된다**(`system_logs.INFO_RETENTION_DAYS = 2`, 20:10 `purge_old_logs()`).
⇒ **D+1(화 09-08) 판독을 48시간 안에 수행하거나 첫날 행을 별도 파일로 덤프한다.**
cycle245 `[ratio_notional_blocked]` 후속 F-12 · cycle262 후속 F-1 과 **동일 계열**이다.
⚠️ 레벨 승격(INFO→WARNING)으로 때우지 마라 — 하루 30~70행이 리포트 `top_patterns` 를 오염시킨다.

**커밋 직후 정리 2건**

1. **in-flight sha 핀 4곳 비우기** — 키 `"src/engine/strategies/kojiro.py"` + 그 위 cycle268 주석 블록을 함께 삭제.
   값 = `4414ff9ef03a3cc3c395c540f28fea0ecd002e2500160b04d9078929556fdfb3`.
   `test_cycle223_ast_donchian_exit_fix.py::_CYCLE228_STRATEGY_CONTENT_SHA`(:552) ·
   같은 파일 `::_PREEXISTING_CONTENT_SHA`(:447) ·
   `test_cycle223f_ast_manual_apply_safeguard.py::_PREEXISTING_CONTENT_SHA`(:348) ·
   `test_cycle222a3_ast_followup_fixes.py::_APPROVED_CONTENT_SHA`(:459).
   선례 = `0c878ec`(cycle263) · `29b67ff`(cycle264) 둘 다 별도 후속 커밋. **넷 중 하나만 빠져도 다른 가드가 붉어진다.**
2. **사이클 한정 가드 2건 은퇴** — `test_cycle268_ast_gap_observe.py::test_g268_14*` + `CYCLE_SCOPED_DELETE_AFTER_COMMIT`.
   `git diff HEAD` 기반이라 커밋된 지금 공허하게 통과하고, 반대로 **D4(`order_engine.py`)·cycle265(`src/realtime/**`)가
   워킹트리를 만지면 cycle268 과 무관하게 붉어진다** = 오탐 발생기.

**판독 함정 3 (tester 적대 검토 실측 — 명세 §1/§5 정본에 반영 완료)**

- 🔴 **경로 B(`caller=on_tick`) 행의 `ws_*` 4필드는 동어반복이다.** `risk.on_tick` 이 `check_buy_signal` 호출
  **전에** `ticker_prices[t]["open_price"] = open_price` 를 덮으므로(`risk.py:495`) `ws_cmp=ws_eq` 가 **산술적으로 보장**된다.
  `ws_ne` 건수를 오염 지표로 세면 **경로 B 전체가 "일치" 로 잡혀 결론이 뒤집힌다**(cycle264 `used_src=rest` 함정과 동형).
  경로 B 오염 판정 = `stock_master_daily` 오프라인 조인**만**.
- **`verdict=candidate` 는 시간창 게이트 앞이라 창 밖에서도 발화한다.** 경로 A/B 비율은 로그 타임스탬프
  `[09:05, 09:30]` 로 **먼저 거르고** 세라. 판정 5종은 창 안 전용이 맞다.
- **grep 앵커 필수.** `verdict=` 는 `ws_verdict=` 의 접미이고 두 필드는 서식상 인접하지 않는다 —
  앵커 없는 grep 은 실측 1행짜리를 **4행**으로 부풀리고, 한 패턴 grep 은 **0행**을 낸다.
  정본 = `grep ' verdict=skip_up ' | grep ' ws_verdict=pass'`.

**구조적 실측 (조사 §1.3 확증)** — `_build_priority_groups`(`scheduler.py:1909`)가 `"swing": []` 을 고정 반환해
**kojiro 후보는 WS 구독 대상이 아니다**. 경로 B 노출은 `kojiro 후보 ∩ (breakout ∪ momentum)` 교집합뿐이고,
momentum 몫은 09:30 이후 첫 틱이라 매수 창 밖이다.

### ✅ 커밋 **직후** 정리 체크리스트

1. 자매 가드 **4곳**의 `src/realtime/handler.py` 항목을 **함께 비운다**(각 파일 TODO 주석 참조).
   커밋 후 그 sha 는 죽은 값이 되고, 남겨 두면 다음에 handler 를 정당하게 건드리는 사이클이
   오해 소지 있는 실패 메시지를 받는다.
2. `test_cycle264_scope_and_pins.py::test_c7_working_tree_touches_only_allowed_files` 는 `git diff`
   워킹트리 기반이라 커밋 직후 **공허 통과**한다 — 8영역의 **영구** 가드는
   `tests/unit/ast/test_cycle222a3_ast_followup_fixes.py::test_ga3_6_*` 다(cycle262 선례와 동일).
3. sha 핀은 **커밋 직전 마지막 단계**에 `shasum -a 256` 으로 재산출한다.
4. 배포 = **full 모드**(`src/**` 변경 ⇒ backend 재생성). 장외 창 **월 07:45 이전**에 push
   (07:55 `_boot` 전 재생성 여유 1~5분). 09:00~15:30 은 D6 로 금지.

---

## ✅ cycle263 — 일봉 적재 껍데기 봉 시정 (라) = (가) 신선도 게이트 + (다) 오늘봉 시각 필터 (2026-09-06, **커밋·배포 대기**)

> 사용자 결정(09-06) = 카드 ④ "승인" — `src/engine/scanner.py` **8영역 접촉 포함**.
> 자문 정본 = `_workspace/consult/2026-09-06_daily_load_stub_bar.md`(본문 + 부록 A) ·
> 명세 = `_workspace/specs/cycle263_daily_load_stub_fix.md` ·
> 선행 실행 = 09-06 15:16 금요일 일봉 보정(963종목·6,916행, 09-04 스텁 1,015→120 — 이 파일 아래
> "2026-09-06 15:16" 절). **변경 파일 = `src/engine/data_load_tasks.py` + `src/engine/scanner.py`
> 둘뿐**(C9 — `scheduler.py`·전략 7파일·`src/db/**`·`src/realtime/**`·`src/auth/**`·
> `src/api/order.py`·frontend·migrations diff 0).

### 결함 (실측 확증)

멱등 규칙 `latest >= today` skip + 기동 직후 1회 실행(`immediate_first_run=True`,
`initial_delay_secs=240`)이 결합해, 아침 07:56 immediate 가 장 전 KIS 로부터 **오늘 날짜 껍데기 봉**
(O=H=L=C=전일종가·거래량 0)을 받아 먼저 쓰고 `max_bas_dd == today` 를 만든다 ⇒ **그날 16:00 정기
실행이 전 종목 skip**.

```
09-03 07:57 fetched=982  skipped_fresh=0   |  09-03 16:00 fetched=0 skipped_fresh=982
09-04 07:57 fetched=1015 skipped_fresh=0   |  09-04 16:04 fetched=1 skipped_fresh=1015
```

**오염 경로는 "오늘 스텁" 이 아니라 "어제 스텁" 이다** — 전략 7종은 `prev_idx` 가드로 오늘 봉을 이미
잘라내는데, `_boot` 의 `prepare()` 가 적재보다 **4분 먼저**(07:51 vs 07:56) 돌아 그 시점 테이블
헤드가 *어제* 날짜 껍데기이고 `bas_dd != today` 라 가드를 그냥 통과한다. 같은 아침 두 prepare 실측 =
LTV 09-03 `10/90 → 90/90` · 09-04 `5/32 → 32/32` · donchian `1/111 → 4/111` · BFB `42/595 → 25/596` ·
kojiro `32/662 → 14/663` — **BFB·kojiro 는 오염 쪽이 더 많다**(거짓 후보 생성 + 진짜 후보 죽임 =
양방향). donchian 은 오염 상태에서 신고가·거래대금 게이트가 **수학적으로 통과 불가**(P0-1 계열
구조적 차단). 이 손상을 매일 지워온 08:02 재-prepare 는 설계가 아니라 `evening_funnel_capture`
immediate run(boot+600s)의 **우연**이고, 적재가 360초를 넘기면 그 우연이 깨진다.

### 시정 — 두 축을 **함께** 넣는다

- **(가) `src/engine/data_load_tasks.py`(8영역 밖)** — `stock_master_daily_load_task_loop` 의
  `run_periodic_task_loop` 호출에 `immediate_skip_if_fresh_hours=IMMEDIATE_FRESH_SKIP_HOURS`(20.0)
  추가 + `:110` 의 "미적용" 주석 정정. 사이클 193 이 daily_load 만 게이트를 뺀 근거가
  "`max_bas_dd` 멱등을 믿어서" 인데 **지금 깨진 것이 정확히 그 멱등**이라, 게이트 투입은 사이클 193
  의 전제를 되살리는 방향이다. 메커니즘은 이미 프로덕션 검증됨(basics/master/financial 3 task 마커가
  D-1 16:2x~16:4x 로 살아 있고 익일 07:55 에 15.5h < 20h 로 실제 skip 중). 마커는 `once()` **성공
  시에만** 갱신되므로 16:00 실패·프로세스 다운·주말·공휴일 전부 다음 아침 immediate 가 자동
  부활한다(사이클 106 lifecycle race 안전망 보존).
- **(다) `src/engine/scanner.py`(8영역, 승인 완료)** — `fetched += 1` **뒤** · `upsert_batch` **앞**
  에서 `_drop_today_bars(candles, now_kst=load_now_kst, today=today)` 로 확정 전 오늘봉을 폐기한다.
  그 자리가 유일하게 안전하다(두 fetch 분기의 **합류점** + `fetched`/`failed` 카운터 의미 보존).
  커트오프 `_DAILY_LOAD_TODAY_BAR_CUTOFF = time(15, 40)` 는 **scanner 전용 상수**다 — 값이 같아
  보여도 매매/보드 시각 상수를 재사용하지 않는다(매수 보드 시각 변경이 적재 규약을 딸려 바꾸는
  커플링 차단). `load_now_kst = datetime.now(KST_TZ)` 는 **함수 진입 시 1회**(`stock_master.list_all`
  페이징 *앞*, `today_kst()` 보다 **먼저**) 읽는다. 판정은 **시각 단독**이고, 예외는 **fail-open**
  (전량 upsert 유지 + `[daily_load_today_filter_skipped]` WARNING 실행당 1행).
- **왜 데이터 기준(거래량 0 ∧ OHLC 평탄)이면 안 되나** — (a) 장중 재시작이 만드는 부분봉은
  거래량>0·비평탄이라 확정봉인 척 통과한다(껍데기보다 **나쁘다** — 평탄하지 않아 눈에 안 띈다)
  (b) 거래정지 종목의 **진짜 평탄 확정봉**(하루 1~8건)을 16:00 에 죽여 그 날짜 행을 영영 못 갖게
  한다. 시각 기준은 진짜 무거래봉을 **정의상 100% 보존**한다.
- **왜 (가) 단독이면 안 되나** — 마커 D-1 16:0x + 20h = D 12:0x 만료 ⇒ 12:0x~15:30 재시작이면
  immediate 가 다시 떠서 부분봉을 확정봉처럼 박고 그날 16:00 이 skip 된다(실측 = 최근 30일 full
  모드 커밋 5건: 13:25·13:45·13:49·14:01·14:30 = 주 1회 이상). (다)가 그 구멍을 닫는다.

### 게이트 (2026-09-06 로컬 실측)

- 신규·연관 가드 **158 PASS** — `tests/unit/engine/test_cycle263_daily_load_stub_filter.py` **40**
  (A 게이트/마커 8 · B `_drop_today_bars` 순수 10 · C 통합·시각 계약 6 · D 마커 서식 3 ·
  E fail-open·backfill 분기 3 · I `force` 경로 4 · F 상수·naive 금지 3 · G 구멍 폐쇄·3일 수렴 2 ·
  H 전략 `prev_idx` 가드 전제 1) + `test_cycle263_scope_guard.py` 1 +
  `test_cycle193_ast_fresh_gate.py` 5(게이트 대상 3 task 로 갱신) +
  `test_cycle193_immediate_fresh_gate.py` 10 + `test_cycle223g3_ast_guard_sees_staged.py` **17**
  (`test_g3_9a/9b` 신설 포함) + `test_cycle222a3` 23 + `test_cycle223` 18 + `test_cycle223f` 9 +
  `test_cycle226` 35.
- sha 핀 대조 — 네 파일 전부 `fa4f7f2f49cbe8d363bee6a972e96fdfc95e787abf341ea35edfd0149b44bc11`
  이고 `shasum -a 256 src/engine/scanner.py` 실측과 **일치** 확인.
- **백엔드 전체 = 7,186 passed / 11 skipped / 328 xfailed / 13 xpassed (3분 47초). 회귀 0.**
  (cycle262 커밋 시점 7,145 대비 +41 = 신규 41 − 삭제된 cycle262 `test_c12_*` 2 + 신설 `test_g3_9a/9b` 2.)
- ⚠️ 로컬 Python 3.13 초록은 게이트가 아니다 — CI 는 3.12 다. push 후 `gh run list` 확인 의무.
- 적대 검증 3렌즈 18건 전건 처리 = 수용 16 · 부분 수용 1 · 불수용 1. **구현을 약화시킨 곳 0.**
  HIGH 3 = ① sha 핀 자매 4곳 중 한 곳만 등록해 전체 회귀 **7 failed**(223·223f·226 + 메타 가드
  `test_g3_7` 2건 + 고아 cycle262 `test_c12_*` 2건) → 네 곳 동일 값 등록 + 재발 방지 `test_g3_9a/9b`
  (**영구**) 신설 ② 커밋된 cycle262 `test_c12_1/2` + `_ALLOWED_SRC_PY`/`_FORBIDDEN_PATHS` 가 고아로
  남아 cycle263 diff 를 재고 있었음 → 삭제 ③ `src/engine/CLAUDE.md` 의 게이트 대상 서술이 이
  사이클이 뒤집은 정책을 반대로 기술 → 정정. **뮤테이션 ESCAPED 6건 전부 KILL**(M29 backfill 분기
  우회 → `test_E3` / M30 `isinstance(candle, dict)` 제거 → `test_E2` 강화 / M21·M13
  `dropped_rows`↔`tickers_affected` 상호 치환 → `test_D3` / M31 `load_now_kst` 위치 → `test_C6` /
  M35 증분 창 7→1·2일 → `test_G2` 보정 창 단언).

### 배포

- 모드 **full**(`src/**` 변경 = backend 재생성). 일요일 장외는 승인된 창(주말 종일), 20:00~20:15 만
  회피. 주말에는 스케줄러가 월 07:45 까지 대기라 매매 무영향.
- ~~**효과의 절반은 월 09-07 16:00 부터, 아침 prepare 정상화는 화 09-08 07:51 부터**다.~~ → **둘 다 월 09-07 에 확인됐다**(16:00 `skipped_fresh` 1,000→0 · 아침 prepare 붕괴 소멸). 실측 시각은 07:51 이 아니라 **07:45**.
- 롤백 = 다음 커밋으로 원복 + 재시작(코드 경로라 **즉시** 반영). 보유 중 장중(09:00~15:30)은 D6 로
  불가 — 15:30 이후 또는 익일 07:45 전.

### D+1 확인 항목 (월 09-07 · 화 09-08)

| 시점 | 확인할 것 | 기대 |
|---|---|---|
| 월 07:56 | `[daily_load_today_bar_filter]` **1행** | 마커가 아직 **부재**(게이트가 daily_load 에 적용된 적 없어 기록이 없다)라 immediate 는 **실행된다**. `mode=drop` · `cutoff=15:40` · `dropped_rows≈1,000` · `tickers_affected≈1,000` · `filter_errors=0` |
| 월 07:56 | 09-07 스텁이 **생기지 않는다** | `SELECT count(*) FROM stock_master_daily WHERE bas_dd='20260907' AND volume=0 AND high_price=low_price AND (updated_at AT TIME ZONE 'Asia/Seoul')::date = bas_dd` = **0** |
| 월 16:00 | `[stock_master_daily_load_summary]` | `fetched≈total` · **`skipped_fresh≈0`** · `upserted_rows` 수천 = 16:00 이 **처음으로 일을 한다**(09-07 실봉 기록) |
| 월 16:00 직후 | `system_config.task_last_success_stock_master_daily_load` | **최초 기록**(그전까지 부재) |
| 화~금 07:56 | `[stock_master_daily_load] immediate run skip — fresh last_success=…` INFO 1행 | 마커 ≈15.9h < 20h ⇒ 아침 immediate **skip**. 이게 매일 보이면 껍데기 생성 주체가 사라진 것 |
| ~~화 09-08 07:51 / 08:02~~ → **✅ 월 09-07 확인 완료** | **두 prepare 카운트 수렴 = 핵심 성공 서명** | ⚠️ **시각이 낡았다** — 실측 부팅 prepare **07:45**, 적재 **07:49~07:51**, 재-prepare **07:56**(상대 순서·4분 간격은 서술과 동일, 절대 시각만 다름). 09-07 실측 = **LTV 99/99 → 92/92**(시정 전 10/90 → 90/90 붕괴 소멸) · **BFB 27/548 → 25/596**(거짓 후보 격차 17 → 2) · VB 63/63 → 68/68 · donchian 2/102 → 1/110 · VCP 0/651 → 0/689 · kojiro 13/647 → 13/683. 잔여 소폭 차이는 껍데기 봉이 아니라 07:53 `stock_master_basics_refresh` 의 유니버스 증가로 설명된다(BFB 분모 548→596). **정본 = `_workspace/analysis/2026-09-07_open_scope_dplus1_readout.md` §5** |
| 월 07:51 | (참고) 이미 대체로 정상 | 09-06 15:16 보정으로 09-04 실봉이 963종목 채워져 있다 — 시정 배포 여부와 **무관**하게 성립한다. 잔여 120종목은 `stock_master` 유니버스 밖이라 보정 범위 밖 |
| 상시 | 신규 상장·유니버스 진입 종목 backfill **≈8시간 지연** | 아침 → 같은 날 16:00 으로 이동. 그 사이 `get_recent_daily_normalized` 는 `reason="miss"` KIS 폴백(데이터는 더 정확, 장중 KIS 호출은 증가). 규모 관측(09-04 실측 16:04 `fetched=1` / 18:45 재시작 `fetched=66`) |
| 상시 | UI "마지막 일봉 적재" | 낮 동안 **어제 날짜** = **정상**(의미상 "마지막으로 확정된 일봉"이 어제인 것이 맞다) |

- ⚠️ **의미 반전** — 16:00 실행의 `skipped_fresh` 가 **~1,000 → ~0** 이 된다. **배포 전후 로그를 같은
  grep 으로 합산하지 말 것**(사이클 228 `[*_vol_gate_observe]` `would_pass` 반전 때 세운 규약과 동형).
  부수적으로 `upserted_rows` 총량이 하루 ~7,900 → ~15,800, KIS 일봉 호출이 ~1,015 → ~2,030 이 되는데
  이건 결함이 아니라 16:00 이 비로소 일을 하는 것이다.
- ⚠️ **`[daily_load_today_bar_filter]` 가 안 보이면** 코드 미배포로 단정하기 전에
  `[stock_master_daily_load_begin] candidates=` 를 먼저 본다 — `stock_master.list_all` 이 전 페이지
  실패하거나 빈 결과면 조기 return 이라 마커가 0행이다(그 경로엔 `stock_master 빈 영역 — 적재 skip`
  WARNING 도 남는다).
- ⚠️ **`[prepare_db_fallback] reason=stale` 은 체크리스트에서 뺀다** — 자문 본문 §6-5 가 성공 서명으로
  제시했으나 그 emit 은 `logger.debug`(`src/db/stock_master_daily.py::_kis_fallback`)라 `system_logs`(INFO+)에
  **애초에 안 들어간다**(자문 §A-4 정정 2). 굳이 보려면 EC2 컨테이너 로그(`docker logs`) 기준으로만.
- `filter_errors > 0` 이면 fail-open 이 발생한 것이다 — `[daily_load_today_filter_skipped]` WARNING 과
  대조한다. 이 필드가 없으면 `dropped_rows=0` 이 "버릴 오늘봉이 없었다" 와 "필터가 전량 죽어 시정 전
  행위로 되돌아갔다" 를 구분하지 못한다.

### ✅ 커밋 **직후** 정리 체크리스트

1. `scanner.py` sha 핀을 **네 곳 동시에 비운다** — `tests/unit/ast/test_cycle222a3_ast_followup_fixes.py::_APPROVED_CONTENT_SHA` ·
   `tests/unit/ast/test_cycle223_ast_donchian_exit_fix.py::_PREEXISTING_CONTENT_SHA` ·
   `tests/unit/ast/test_cycle223f_ast_manual_apply_safeguard.py::_PREEXISTING_CONTENT_SHA` ·
   `tests/unit/engine/strategies/test_cycle226_zero_breakout_defense.py::_ALLOWED_CONTENT_SHA`.
   ⚠️ **한 곳만 등록/삭제하면 나머지가 붉어지는데 그 실패 문구가 "핀을 먼저 재산출하지 마라 — 실제
   변경을 되돌려라" 라서 승인된 8영역 변경을 되돌리도록 오도한다**(cycle263 이 실제로 그 사고를 냈다).
   순서는 **소스 확정 → `shasum -a 256` 재산출 → 4곳 동시 갱신** 이고, `scanner.py` 를 1 byte 라도
   더 고치면 네 핀이 전부 무효다. 재발 방지 가드 = `test_cycle223g3_ast_guard_sees_staged.py::test_g3_9a/9b`(**영구**).
2. `tests/unit/engine/test_cycle263_scope_guard.py` **삭제**(`_skip_if_cycle_committed` 가 커밋 후
   자기 은퇴시키므로 잊어도 다음 사이클을 막지는 않는다 — cycle253 패턴).
3. (이 사이클에서 이미 처리) 커밋된 cycle262 의 `test_c12_1`/`test_c12_2` +
   `_ALLOWED_SRC_PY`/`_FORBIDDEN_PATHS` 삭제 완료 — cycle240 A11b · cycle252 G-252-5b 선례.

### 별건으로 남는 것 (이 사이클에서 **손대지 않았다**)

| # | 항목 | 상태 |
|---|---|---|
| **D-4** | `DAILY_STALENESS_DAYS`(현 4) | **무변경.** 2026-02 이후 144회 거래일 전이 중 간격 ≥5 는 1회(02-19 설, 간격 6). **다음 발화 예정 = 추석(9월 하순)** — 발화하면 1,000종목 250~300초 prepare 지연이지만 폴백 데이터가 더 정확하므로 위험이 아니라 비용이다. 상향은 "D-1 미적재 감지" 목적을 무디게 하므로 별도 결정 |
| **D-5** | VB `k_period=15` vs 하드코딩 `min_required=22` | **VB 는 DB 일봉을 한 번도 쓴 적이 없다**(17 < 22 ⇒ 매 prepare 종목당 KIS 1회 폴백). 고치면 VB 가 처음 DB 경로에 들어오므로 별도 검증 사이클 |
| **D-6** | `stock_master_daily.get_atr()` 오늘봉 가드 부재 | VCP ATR **평균 6.3% 과소**(중앙 6.3% · 최악 29.3% · 1,805 중 272종목이 10%+). VCP 의 ±10% 교차검증 문턱 **아래**라 `[vcp_atr_mismatch]` 가 3개월간 무발화. (다) 로 증상은 사라지지만 **가드 자체는 없다** — `market_regime._compute_single_etf_stage` · VB RS/RSI 훅도 동일. ⚠️ **G-7(VCP/BFB 터틀 sizing 전환)은 이 시정 D+1 확인 뒤로**(6.3% 낮은 ATR = 전 유닛 6.7% 과대) |
| **D-9** | `TIME_STOCK_MASTER_DAILY_LOAD` 16:00 → **18:10** | (라) 가 잃는 **유일한 것**(헤드 봉의 시간외 단일가 16:00~18:00 물량이 하루 늦게 반영)을 완전 해소한다. 16:10 basics·16:15 purge·16:20 funnel 과 무충돌, 16:20 funnel 이 읽는 헤드는 이동 전후 동일. **이 시정 D+1 확인 후 별건** |
| **D-11** | 사용자 제안 05:00(·23:00) 기동 | **보류 — 구조적 불가.** task loop 이 `while scheduler._running` 인데 `scheduler.py:1035` 가 20:10 정산 직후 `_running=False` 를 세우고 `run_daily` 가 익일 07:45 까지 sleep 한다 ⇒ 그 시각엔 루프가 존재하지 않아 발화하지 않는다. 하려면 task 를 uvicorn lifespan 으로 빼는 재설계 선행 |
| **D-12** | 락 게이트를 안 타는 `get_recent_daily` 직접 호출 3곳 | `get_atr`(VCP 14일) · `market_regime._compute_single_etf_stage`(90일) · VB RS/RSI 훅(30일). VCP 는 ±10% 교차검증이 방어 중(30일 2건 발화), 나머지 2곳은 관찰 전용 |
| — | **액면분할 미조정 26,844행 / 242종목** | 60일 락 발생 271종목 중. KIS 는 소급 재조정하지만(210980 실증: `4,445 × (1−0.3196) = 3,024 ≈ 3,054`) **T-7 창이 회수하지 못한다** — 하루 두 번을 돌든 한 번을 돌든 창이 7일이라 결과가 같다. 실제 방어는 prepare 시점 **락 게이트**라 적재 빈도와 **독립**이고, 아침 실행 skip 과 무관하다. **이번 사이클 무조정** |
| — | **prepare↔적재 순서 규약 2건** | ① 자문 안 (E) `_boot` 의 prepare 를 daily load **뒤로** 옮기는 순서 시정 — 근본 방향이나 `scheduler.py`(라인 상한) + `boot_manager.py` 를 건드리고 07:59 사전 구독까지의 14분 예산에 119초 적재를 끼워 넣게 되어 이번 범위 밖. (다) 를 넣으면 아침 prepare 가 읽는 헤드가 이미 정확해져 순서 변경이 **불필요**해진다 ② 16:00 이 실패한 다음날에는 08:02 `evening_funnel_capture` 재-prepare 가 다시 **유일한** 보정이 된다 — 우연 의존이 완전히 사라지지는 않는다. 새 전략이 `prev_idx` 오늘봉 가드를 빠뜨리면 이 전제가 깨지므로 `test_H1`(영구)이 7 전략의 가드 존재를 잠근다 |

---

## ✅ cycle262 — VB·LTV 09:00 직후 진입 보류 `open_entry_hold_secs` (2026-09-06, **커밋·푸시 완료 `92bc140`** — 배포는 push 자동 full, CI 확인 의무)

> 사용자 결정(09-06) = 카드 ② "조사와 임시 매수 보류 함께" · 범위 **VB + LTV 둘 다**(자문 권고 b) ·
> 배포 **오늘 일요일 장외**(월 09:00 개장부터 발효). 자문 정본 =
> `_workspace/consult/2026-09-06_open_entry_hold.md` · 조사 근거 =
> `_workspace/analysis/entry_price_0900_20260906/{code_trace.md,forensic.md}`.
> **변경 파일 = `src/engine/strategies/{volatility_breakout,long_tail_volatility}.py` 둘뿐**
> (8영역·`scheduler.py`·타 전략 5파일 diff 0 = C12).

### 무엇을 했나
KRX 개장 후 기본 **90초**(창 = KST `[09:00:00, 09:01:30)`) 동안 **신규 매수 신호만** 보류한다.
청산·손절·트레일링·익일청산·15:20 강제청산은 무접촉. 보드 무관 — **시간창 단독 판정**.
LTV 의 08:00~09:00 진짜 프리장 매수는 창 밖이라 무접촉.

### ⚠️ 이건 지혈이다 (근본 시정 아님)
목표가의 기준 시가가 KRX 09:00 시가가 아니라 통합 채널 `H0UNCNT0` `fields[7]`(= **세션 시가**,
프리장 체결이 있었으면 프리장 시가)다. 09:00~09:01:30 코호트는 "체결가 ≥ KRX시가+offset" 을
**20/20 전부 위반**(이후 구간 53/93 = 57%), Fisher p=6.4e-5. **오염된 `[7]` 은 일-스코프 상수라
90초 뒤에도 값이 그대로다** — 보류는 통계적으로 최악인 구간만 피할 뿐 오염을 고치지 않는다.

### 🔴 근본 시정은 **열린 채로 남는다** — 이 사이클이 그 항목을 닫지 않는다
`[7]` 오염은 **전 시간대 공통**이다(09:01:30 이후에도 53/93 = 57.0% 위반). 보류가 회수하는 것은
**건수의 17%(20/113)** 이고 손실의 39% 다. 근본 시정 = `[7]` 에 **`[24] OPRC_HOUR` 스코프 필터**를
거는 것 — 형제 필드 `[8] 고가`가 cycle222-a2 에서 `[27] HGPR_HOUR` 로 받은 것과 **대칭**이고,
`[24]` 는 지금 **전 소스 파싱 0건**이다. `src/realtime/**` = **8영역** + 진입 목표가 = **매매 행위
변경**이라 **사용자 승인 + `domain-consult` 선행**이 필요하다 ⇒ 아래 **F-2**
(**관측 단계만 cycle264 로 착수 — 시정은 여전히 미착수, cycle265**).
⚠️ **고가와 달리 시가는 fail-closed(0 강등)를 쓸 수 없다** — 0 이면 VB 매수가 통째로 멈춘다.
방향 설계(0 강등 vs REST `stck_oprc` 폴백 vs 보류)가 별도 쟁점이다.
> 자문 §4.1 원문: **"⚠️ 이 보류가 워크리스트에서 근본 시정 항목을 닫으면 안 된다. 지혈은 지혈로만 기록한다."**

### 판독 (월 09-07 09:00~09:05)
- `[open_entry_hold_config] strategy=… hold_secs=90 until=09:01:30 source=default` — **전략당 1행**
  (cap 은 정확히는 1회/**(전략, 값)**/일 — 장중 PUT 롤백 시에만 2행). 0행이면 보류가 안 걸렸거나
  그날 평가 자체가 없었다는 뜻이므로 즉시 확인.
  ⚠️ `source` 는 **출처가 아니라 값 동등성 추론**이다(`PUT` 으로 90 을 재확정해도 `default`).
- `[open_entry_hold_blocked] ticker=… current_price=… target=… board_open=… elapsed_secs=…` —
  **would_buy 정본**, 1회/(ticker,전략)/일. 이 사이클의 **핵심 산출물**이다.
- 롤백(장중) = `PUT /api/strategies/{id}/params {"open_entry_hold_secs": 0}` — **즉시** 반영.
  `strategy_config` SQL UPDATE 는 **다음 백엔드 재시작에서만**(cycle232 D6 로 보유 중 장중
  재시작 금지 ⇒ **장중 실효 수단은 PUT 뿐**). 키가 전략별이라 VB 90 유지 + LTV 만 끄기 가능.
- ⚠️ **배포 전 DB 선반영 금지** — `_load_strategy_config`·`PUT /params` 둘 다 "코드에 이미 있는
  키만 덮는" 오버레이라 배포 전 PUT 은 **무음 실패**하고 `params` JSONB 를 통째로 덮는다.

### 🕒 증거 만료 시한 (후속 F-1 이 닫히기 전까지 유효)
`[open_entry_hold_blocked]` 는 지금 **`system_logs` 에만** 남는다. 자문 §4.2 실측상 전략 INFO 는
최근 며칠분만 잔존하므로, **자문 ⑨ 의 재검토 트리거(2주 연속 관찰)가 닫히기 전에 로그가 purge 될 수
있다.** F-1 이 배선되기 전까지는 **주 1회 이상 수동 추출**(`system_logs` grep → 별도 보관)로 버틴다.

### 후속 티켓 (자문 §8 ⑩ 우선순위 — ①~④ 가 그 정본 순서)

| 우선 | # | 티켓 | 범위 | 왜 |
|---|---|---|---|---|
| **①** | **F-7** | `stock_master_daily` **16:00 적재 복구** | **✅ cycle263 구현 완료 — 커밋·배포 대기** (이 파일 최상단 절 · 명세 `_workspace/specs/cycle263_daily_load_stub_fix.md`, 09-06 카드 ④ "승인" — `scanner.py` 8영역 접촉 포함) | 자문 §4.3 **단계 1**(매일 09:35 `[breakout_open_confirm]` 스탬프 vs `stock_master_daily` 그날 KRX 시가 대조 — 8영역 무접촉·코드 0줄)의 **선결 조건**이다. 스텁이면 대조 자체가 불가능하다. 09-06 15:16 금요일 보정으로 09-04 스텁 1,015→120 은 해소됐지만 **매일 아침 07:5x 스텁이 `max_bas_dd==오늘` idempotency 를 다시 거는 구조**는 시정 배포 전까지 그대로다 |
| **②** | **F-2** | `[24] OPRC_HOUR` 프로브 → **근본 시정** | **프로브 = ✅ cycle264 구현 완료(관측만, 커밋·배포 대기)** · **시정 = 🔴 열린 채 — cycle265, 다음 주말** (`src/realtime/**` = **8영역** — 사용자 승인 + `domain-consult` 선행 필수) | `[7]` 이 세션 시가라는 **오염 자체**를 고친다. `[24]` 는 이 리포에서 **한 번도 관측된 적이 없어**(파싱 0건) "그 값이 08:00 프리장 시가다" 는 여전히 **추론**이다 — cycle264 의 `[open_scope_observe]`·`[open_source_compare]` 가 월 09-07 하루치 분포와 3자 대조를 만든다(이 파일 최상단 절의 **D+1 판독** 5항목). 자문 §8.1 = **월요일에는 행위를 바꾸지 않는다**(시정하면 VB 진입 −27.6% 라 cycle262·263 의 첫 실전 검증과 귀인이 섞인다). 시정 방향은 자문 §0 = `[7]` **0 강등 금지**(여섯 소비처 공유), `board="main"` 기준가만 KRX REST 로 교체 + 킬스위치 `open_price_scope_mode` |
| ~~③~~ | **F-8** | 09:00:05 `[breakout_open_confirm]` **`confirmed=0 empty=55~65`** 원인 | **✅ 원인 규명 완료 — 자문 §1.1(2026-09-06). 표시 시정은 cycle264 C3 에 동봉(커밋·배포 대기)** | **`confirmed=0` 은 표시 버그였다.** `_emit_breakout_open_confirm` 이 `_open_confirmed` 를 직접 세지 않고 `get_targets_status()` 를 거치는데 그 함수가 `session_tracker.active ∩ tradable_boards` 로 보드를 가린다 — 09:00:0x 트래커는 30초 stale 캐시라 `active={PRE_NXT}` 이고 VB 는 `["main"]` ⇒ 교집합 ∅ → 전 종목 `open_price: 0`. 같은 함수 바로 앞줄 비필터 로그는 **VB 51/65(09-03)·46/55(09-04) 확정**. ⇒ ~~"주 경로 무동작"~~ 은 **반증**됐고 **REST 폴백은 고장이 아니라 오염된 WS 캐시에 차례를 뺏긴 것**이다 = F-2 는 새 배관이 아니라 **우선순위 뒤집기**. cycle264 가 `truth_confirmed`/`truth_total` 을 **추가**(기존 필드 보존)해 재발을 막는다 |
| **④** | **F-3** | **kojiro 갭스킵 오염** — 조사 ✅ 완료(2026-09-07) · **관측 = cycle266 착수** | 조사 정본 `_workspace/consult/2026-09-07_kojiro_gap_contamination.md` · 관측 명세 `_workspace/specs/cycle268_kojiro_gap_observe.md`(`src/engine/kojiro_gap_observe.py` 신규 leaf + `kojiro.py` 호출 6행, **행위 변경 0**) · **시정(조사 1안 = `risk.py:646` 에 kojiro 추가)은 8영역 승인 대기 — 열린 채** | kojiro 는 매수 창이 09:05~09:30 이라 이번 보류 **밖**이지만, 갭업/갭다운 스킵이 **같은 오염된 `open_price`** 로 갭률을 잰다. 프리장 시가 ≈ 전일종가면 `gap_rate ≈ 0` 이 되어 **스킵해야 할 갭업 종목을 스킵하지 않는다** = 방향이 **위험 증가** 쪽. 자문 §7-9 가 "별도 티켓으로 반드시 등재" 라고 못박았다. **09-07 실측으로 확정** — 오염 경로는 `risk.on_tick`(`risk.py:646` skip 목록에 `donchian_swing` 만 있고 kojiro 가 **없다**)이고, 주 경로 `_swing_buy_poll_loop` 는 KRX REST(`J`)라 깨끗하다. WS 시가 ≠ KRX 시가 **98/103(95.1%)**, 갭률 오차 최대 **6.77%p**, kojiro 임계 적용 시 전이 **`pass→skip_up` 8건 / 반대 0건 = 진짜 갭업 8건 전부 미탐**. 스킵만 `_bought_today` 당일 영구 래치라 **래치 구조가 오염을 위험 증가 쪽으로 정류**한다. 오늘 노출 = kojiro 후보 14 중 **1(004020)** — 실제 매수 2건은 둘 다 09:05 REST(깨끗) |
| **⏱ 시한부** | **F-1** | `[open_entry_hold_blocked]` **일일 추출 적재** (would_buy 보존) | `src/engine/log_metrics_collector.py`(20:10) 또는 `GET /api/log-reports/bundle`(20:20) — **cycle262 C12 범위 밖이라 별도 사이클** | 사용자 결정 ⑥ 은 "`system_logs` 만" 이 아니라 **일일 추출 적재**로 확정됐다. would_buy 정본이 평가 창이 닫히기 전에 사라지면 **지혈의 근거를 지혈이 스스로 지운다**. ⚠️ 우선순위 ①~④ 와 달리 **로그 retention 이 시계를 돌린다** — 배선 전까지는 주 1회 이상 수동 추출로 버틴다 |
| 그 밖 | **F-4** | `[open_entry_hold_release]` (자문 §2.6 선택 마커, **이번 범위 미구현**) | VB·LTV | "막고 나서 더 좋은 값에 샀나" 를 로그 단독으로 판정 가능하게 한다. 없으면 자문 ⑨ 재검토 트리거는 `trade_history` 조인으로만 복원되고 **"못 샀다" vs "더 좋은 값에 샀다" 가 구분되지 않는다** |
| 그 밖 | **F-6** | 계좌 게이트 활성일 **LTV config 카나리아 0행** | `long_tail_volatility.py` + `tests/unit/ast/test_cycle233_ast_account_risk.py`(계약 자체 변경 = 승인 사안) | 적대 검증이 "카나리아를 게이트 앞으로" 권고했으나 그 이동은 cycle233 M6(게이트 = `check_buy_signal` 첫 문장, `GATE_FIRST_FILES`)를 **RED 로 만든다**(실측 확인 = **불수용** 사유). 두 계약을 어떻게 화해시킬지는 별도 결정 — 그때까지 비대칭은 **문서화된 한계**이고 `test_c7_8` 이 그 현상을 고정한다 |
| 그 밖 | **F-5** | `source` 필드 **진짜 출처 판정** | `scheduler._load_strategy_config` + `routes/strategies.update_params`(둘 다 C12 범위 밖) | 현재는 값 동등성 추론이라 `PUT 90` 을 `default` 로 보고한다. 출처 흔적을 남기려면 오버레이 지점이 기록해야 한다 |
| 그 밖 | **F-3b** | **momentum·LTV 익일청산 갭률의 동일 시가 오염** (등재만 — 이번 사이클에서 고치지 않는다) | `momentum.check_exit_signal:177`(갭률 `:209`) · `long_tail_volatility.check_exit_signal:913`(갭률 `:938`) — 둘 다 `risk.on_tick` 경로 | F-3 조사 §6.1 이 찾았고 **현재 어느 목록에도 없었다**. 같은 오염된 `open_price`(통합 채널 `[7]`, 일-스코프 상수)로 `gap_rate = (open_price − buy_price)/buy_price` 를 재는데, **방향이 kojiro 와 반대**다 — 프리장 시가가 KRX 시가보다 낮으면(09-07 실측 64/98) 갭률이 **과소 측정**돼 트레일링으로 갈 종목이 **즉시 청산**된다 = 손실 확대가 아니라 **기대수익 훼손**. 임계가 10.0%(momentum)로 높아 뒤집힘 빈도는 kojiro(5.0%)보다 낮을 것으로 보이나 **미측정**이다. ⚠️ **08:00 `_execute_next_day_clear` 경로는 오염이 아니다** — 그 시각의 `[7]` 은 그 시점 최신 프리장 시가이고 08:00 익일청산의 설계 의도 자체가 "NXT 프리 시가 기준 갭 판정" 이다. 문제는 **MAIN 구간 `on_tick` 이 같은 낡은 값을 계속 읽는 것**. cycle265(F-2)가 `check_*_signal` 호출 인자 byte 동일을 검증 항목으로 못박았으므로 **cycle265 로도 닫히지 않는다** |

### ✅ 커밋 **직후** 정리 체크리스트 (누락 시 다음 사이클이 오해한다) — **1·2 모두 처리 완료**
1. **[완료 `d292805`]** `tests/unit/ast/test_cycle223_ast_donchian_exit_fix.py::_CYCLE228_STRATEGY_CONTENT_SHA` 의
   **두 항목을 삭제하고 dict 를 다시 비운다**. 커밋 후 그 sha 는 죽은 값이 되고, 남겨 두면 다음에
   VB/LTV 를 정당하게 건드리는 사이클이 "사이클228 게이트 전환" 문구가 붙은 **오해 소지 있는**
   실패 메시지를 받는다(2026-09-05 리팩토링 리뷰 카드 #3 이 같은 이유로 이 dict 를 비웠다 — 재발 방지).
2. **[완료 — cycle263 이 삭제]** `test_cycle262_open_entry_hold.py::test_c12_1` / `test_c12_2` **삭제**. 둘 다 `git diff` 워킹트리
   기반이라 커밋 직후 `changed == []` 로 **공허 통과**한다 — 남겨 두면 "가드가 지켜준다"고 오해하게 된다.
   8영역의 **영구** 가드는 `tests/unit/ast/test_cycle222a3_ast_followup_fixes.py::test_ga3_6_*` 다.
3. sha 핀은 **커밋 직전 마지막 단계**에 `shasum -a 256` 으로 재산출한다(검토 중 파일이 여러 번
   재기록되므로 대화 중간의 어떤 값도 쓰지 않는다).

### 게이트 (2026-09-06 로컬 실측)
- 신규 가드 **132 PASS** — 행위 `tests/unit/engine/strategies/test_cycle262_open_entry_hold.py` **104**
  (C1 키 · C2 fail-open 격자/클램프 · C3 창 경계(09:00:00 포함 / `+hold` 배타 / naive 무차단) ·
  C4 배치(계좌 게이트 선행 · 최상단 아님) · C5 보드 무관 + LTV 프리장 무접촉 + 09:00 이전 무마커 ·
  C6 baseline 갱신 지속 + 해제 후 거짓 돌파 없음 + 진짜 재돌파는 매수 + 청산 무접촉 ·
  C7 config 8 · C8 blocked 6 · C10 흡수기 4 · C11 `PARAM_RANGES` 배제 · C12 범위) +
  AST `tests/unit/ast/test_cycle262_ast_open_entry_hold.py` **28**(G-262-1a/1b·2·3a/3b·4·5·6a/6b·7a~7e·8·9).
- `test_cycle223_ast_donchian_exit_fix.py` **18 PASS**(sha 재핀) — 합계 **150 PASS**.
- `tests/unit/ast` + `tests/unit/engine/strategies` = **2,252 passed** / 3 skipped / 50 xfailed / 3 xpassed.
- 백엔드 전체 = **7,145 passed** / 11 skipped / 328 xfailed / 13 xpassed (3분 47초). 회귀 0.
- sha 핀 대조(문서 개정 시점) — VB `0ac6a7f0…`, LTV `8eddbae2…` 로 **파일 실제 sha 와 일치** 확인.
- ⚠️ 로컬 Python 3.13 초록은 **게이트가 아니다** — CI 는 3.12 다(`.github/workflows/ci.yml`).
  push 후 `gh run list` 로 CI/Deploy 확인 의무(신규 AST 가드는 `ast.dump` 가 아니라 **파일 내용 sha**
  만 쓰므로 버전 독립이지만, 게이트는 CI 초록으로 잡는다).
- 적대 검증(tester) 전건 처리 — **HIGH 2 수용**(① `int(inf)` `OverflowError` 가 fail-open 계약을
  뚫던 유일한 실제 행위 결함 → bare `except Exception` + `inf`/`-inf`/`nan` 격자, 뮤턴트 M06 KILLED
  ② config 흡수기 미검정 → `test_c10_4` 신설 + AST `g262_7b` 에 bare-except 검사 추가).
  처분 = 수용 12 · 부분 수용 1(C12 범위) · **불수용 1**(LTV 카나리아 게이트 앞 이동 = cycle233 M6
  AST RED, 코드 사실로 반박). **ESCAPED 6건 전부 테스트로 봉인, 구현 약화 0.**

---

## ✅ 비터틀 랏 명목 ρ축 상한 — **cycle245 종결 (2026-09-04, `max_lot_ratio_mult` K_ρ=2.5 · 커밋·배포 대기)**

> cycle242 후속 D 종결. 스펙 `_workspace/red/cycle245_ratio_notional_cap_spec.md` ·
> 자문 `_workspace/domain_consult/cycle245_ratio_notional_cap.md` · 발단 정본 `_workspace/review_0904_intraday.md` §5.
> **8영역·`scheduler.py`·`boot_manager.py`·`turtle_sizing.py`·`portfolio_risk.py` diff 0**,
> src 변경 = `src/engine/strategy_base.py`(+348) + 전략 7파일 `DEFAULT_PARAMS` 각 1줄.

### 실측 (09-04 장중 검토 §5)
cycle242 의 유닛 상한(K축, ATR 척도)이 `sizing_mode == "turtle"` 전략에만 걸려 **비터틀은 캡이 꺼진 채
같은 병리가 실재**했다 — `[fallback_cap_config] strategy=long_tail_volatility sizing_mode=None cap=off
k=2.00 budget=260203 risk_pct=0.0000 atr_max=0`(VB·BFB 동일).

| 날짜 | 전략 | 종목 | notional | ρ상한 | 배수 | 결과 |
|---|---|---|---|---|---|---|
| **09-04** | LTV | 000500 | 220,000 | 52,041 | **4.23** | 08:12 매수 → 09:32 손절 **−11,000원**(순자산 0.42%) = 그날 최대 손실 |
| 08-31 | LTV | 161890 | 171,700 | 52,041 | 3.30 | |
| 08-28 | LTV | 010950 | 144,800 | 52,041 | 2.78 | |
| 09-02 | VB | 108490 | 247,000 | 136,607 | 1.81 | |

현행 레짐(08-19~09-04) 51랏 중 **22건(1.8건/영업일)** ρ초과, 총손실 −122,285원의 **31%** 가 배수 ≥2.11 인 3랏.
⚠️ `[oversized_fallback]` 만 세면 규모를 **1/4 로 과소평가**한다.

### 확증 원인
주 분기(`int(예산×ratio)//price`)와 터틀 분기(`compute_unit_qty_guarded`)는 정의상 ρ상한 이하 ⇒
**무상한 지점은 `_fallback_one_share` 하나뿐**이다. 그리고 1주 폴백은 예외가 아니라 **주 경로**다
(90일 1주 비율 VB **91%** · LTV **79%** · momentum 73%, ρ초과 69랏 중 66건이 qty=1).

### 시정 (결정 13 요약)
- **척도 = ρ축**: `cutoff = int(K_ρ × int(예산 × position_ratio))` · `cap_qty = cutoff // price` · `min` 합성.
  비터틀 3전략은 `risk_pct`·`_entry_atr`·`_candidates` 가 소스에 **0건**이라 ATR 축이 원리적으로 불가.
- **적용 범위 = "K축이 이 랏을 실제로 심사하지 못한 모든 랏"**(백스톱). ⚠️ 자문 원안(`mode != turtle` 게이팅)은
  시뮬레이션 실측에서 **cycle242 테스트 4건**을 깼다 — 백스톱은 그 4건을 무수정 통과시키면서 "터틀인데 ATR 배관이
  끊긴 랏 = 양축 무방비" 사각까지 닫는다(라이브 비용 0).
- **두 캡 상호배타 — `min` 합성 없음**(결정 ⑦ — **cycle254(2026-09-05)에서 폐기**, D3 행 참조). 관문 위치는 `_apply_lot_units_cap` → `[oversized_fallback]` **뒤**·return 앞.
- **차단(0주)이 유일 선택지**(K_ρ≥1 이면 캡은 폴백 경로에서만 바인딩되고 그 수량은 항상 1). 유니버스 가격 상한안 기각.
- **전략별 차등 없음**(진짜 차등은 이미 `weight × position_ratio` 에 있다). **키 부재 = OFF**(fail-closed 는 P0-1 재현).
- K_ρ 는 리스크 정체성 상수 — `PARAM_RANGES`/`INT_PARAMS` 미편입 + 읽는 쪽 `[1.0, 20.0]` 클램프(하한 1.0 이 전제).

### 🚨 배포 전 필수 조치 (체크리스트 — 누락 시 당일부터 완화 실험 표본이 깎인다)
1. **BFB·VCP 만 `max_lot_ratio_mult = 20.0` DB 선반영** — 두 전략은 `check_buy_signal` 안에서 **주문 이전에**
   `_vol_latch.pop` + `_bought_today.add` + `_position_setup[t]=…` 를 실행하므로 캡이 0 을 돌려주면 주문은 안 나가는데
   그 종목은 그날 `Signal.NONE` 으로 **영구 차단** = 당일 표본 영구 소실. 유니버스 913종목 기준 컷오프 초과가
   VCP **10.0%** · BFB **3.5%**(1주 폴백 경로 기준 VCP 36%)이고, 두 전략은 cycle228 이 연 N=10 표본 수집 중이다.
   ```sql
   UPDATE strategy_config
      SET params = jsonb_set(params, '{max_lot_ratio_mult}', '20.0'::jsonb, true)
    WHERE strategy_id IN ('bull_flag_breakout', 'vcp_breakout');
   ```
   ⚠️ **배포 전 경로는 이 SQL 하나뿐** — `PUT /api/strategies/{id}/params` 는 배포 전 무음 실패(미지 키 탈락 + `success=true`)이고
   그 뒤 `save_params` 가 `params` 를 통째 덮어 **먼저 넣은 SQL 값까지 지운다** ⇒ SQL 선반영~배포 사이 두 전략에 **어떤 PUT 도 금지**.
   확인 = `SELECT params->'max_lot_ratio_mult' FROM strategy_config WHERE strategy_id IN (…)`(구코드엔 마커가 없어 로그로는 확인 불가).
2. **배포 창 = 15:30 이후**(`strategy_base.py` 변경 = 백엔드 재시작 동반, cycle232 D6). VB 는 선반영 대상 아님(컷오프 341,515 = 유니버스 2.2%, 90일 차단 0건).
3. 배포 후 확인 = `[ratio_cap_config] … k=20.00`(BFB·VCP) / `cap=on k=2.50`(LTV·VB·momentum·donchian·kojiro — **cycle254 이후 터틀도 `cap=on`**, 터틀 전용 구 라벨은 폐기).

### D+1 판독
| 채널 | 정상 | 이상 |
|---|---|---|
| `[ratio_cap_config]` | 전략마다 1행/일, `cutoff_price` = LTV·VCP 130,100 / VB 341,515 / BFB 243,940 / MOM 81,312 | 비터틀에 `cap=off` = **키가 사라짐** / donchian·kojiro 에 터틀 전용 구 라벨 **잔존**(`cap=on` 아님) = cycle254 미반영(롤백/재배포 확인) |
| `[ratio_notional_blocked]` | LTV 0~1건/일(기대 0.33), **BFB·VCP 0**(선반영) | `capped_qty > 0` = 도달 불가 구간 → R7 조사 |
| `[ratio_cap_skipped]` / `[ratio_cap_clamped]` | **0행** | `k_axis_probe_error`·`exception` ≥1 = 코드 결함, 즉시 조사 |
| cycle242 마커 3종 | donchian·kojiro `[fallback_cap_config] cap=on k=2.00` 존속 | 사라지면 배치 오류 = 즉시 롤백 |

⚠️ **의미 전환 2** — `[oversized_fallback]` = "사려 했던 랏"(0 수렴 아님) · `order_engine` 수량-0 WARNING = "ρ캡 차단 포함"
(**1:N** — 표적 3전략엔 `_bought_today` 가 없어 하루 3~4회 재시도). **배포 전후 같은 grep 합산 금지.**
⚠️ INFO 2마커는 20:10 리포트에 **구조적으로 안 실린다** — 판독은 `system_logs` 직접 조회가 유일 채널.
⚠️ **cycle254 반전 규칙** — 위 표·R7 은 cycle245 단독 배포 시점 서술이다. cycle254(2026-09-05) 이후 라벨은
2종(off/on)으로 통일되고(donchian·kojiro 포함 — 터틀 전용 구 라벨은 폐기), R7 자기검증에 터틀 예외가 없어진다 —
터틀 행에서 `[oversized_fallback] ratio > k` 인데 같은 (전략,ticker,일자)에 `[ratio_notional_blocked]` 도
`[ratio_cap_skipped]` 도 없으면 **캡 우회 = 결함**. 터틀 전용 구 라벨이 보이면 그 자체가 cycle254 미반영 신호다.

### 트리거
R1 LTV 주 3건↑ → K=3.0 / R2 BFB·VCP 1건이라도 차단 = 선반영 누락 **감지** 채널(사후로는 늦다) /
R3 LTV 10영업일 매수 0(⚠️ edge-crossing 이라 스펙 상정보다 쉽게 걸린다) / R4 momentum 차단률 50%↑ →
`weight` 재검토 / R5 20영업일 0 = 자연 무해화(게이트 유지) / R6 캡 마커 없는 수량-0 distinct (전략,ticker) 하루 3 초과 /
**R7 캡 우회 = 즉시 핫픽스**(판정은 리터럴 2.50 이 아니라 그날 그 전략의 `[ratio_cap_config] k=` — cycle254 이후 터틀 행도 예외 없이 대상).
R8 `weight`/`position_ratio`/`cash_usage_ratio` 변경 시 K 재검토(컷오프가 예산에 선형 비례).

### 롤백
해당 전략 `max_lot_ratio_mult = 20.0`. **PUT = 즉시 / SQL UPDATE = 다음 백엔드 재시작에서만**
(`_config_loaded` 프로세스당 1회, 07:55 `_boot` 재호출 no-op) ⇒ cycle232 D6 와 겹쳐 **장중 실효 수단은 PUT 뿐**.

### 후속
F-1 `price_filter_max` 500,000→250,000(사용자 결정, 터틀 2전략 영향 평가 선행) · F-2 VB `position_ratio` 0.35 재검토
(어떤 K 로도 정책선 10% 안에 못 들어온다) · F-3 `order_engine` 수량-0 사유 분기(8영역) · F-4 프리장 한정 더 낮은 K 또는
LTV `tradable_boards` 에서 `pre_nxt` 제거(**사용자 결정**) · F-5 LTV 15:20 청산 누수(`_limit_up_reached` 무영속) ·
F-6 선택 효과 6개월 검정(배수가 높을수록 **수익률**도 나쁘다 = 고가주 자체가 나쁜 매매일 가능성) · F-7 자금 규모 대비 전략 수
(순자산 1,000만이면 자연 소멸) · **F-8 cycle242 후속 D 종결** · **F-9 터틀 1주 폴백 랏의 ρ 잔여 노출 — ✅ 종결(cycle254, 2026-09-05)**
(kojiro 3.86배·donchian 5.00배는 구 결정 ⑦ "상호배타" 폐기로 닫혔다 — 자문 `_workspace/domain_consult/cycle254_turtle_fallback_rho_exposure.md`
권고 B 채택, 상세는 아래 09-05 결정 세트 D3 행) ·
**F-10 BFB/VCP 표본 기록 시점**(주문 확정 전 `_bought_today.add`, 8영역 승인 필요) · **F-11 계좌 SOFT Σ상한 켜기 전 LTV 게이트 위치**
(C233-F1 재현 잠복) · F-12 20:10 리포트 ρ캡 집계 · F-13 차단 마커의 랏 수 관측 공백(LOW, 1회/(전략,ticker)/일) · **F-14 `_quote_5xx_dedupe` 테스트 격리**(모듈 전역 dict 를 리셋하는 픽스처가 없어 앞선 부팅 통합 테스트의 실제 KIS 500 잔재가 `test_cycle76_request_5xx_dedupe::test_g_md4` 를 넘어뜨린다 — 로컬 `.token_cache` 보유 시에만 발화하고 CI 는 캐시가 없어 초록이라 잠복. cycle245 무관, Docs 단계 실측으로 신규 등재).

### 검증
뮤테이션 **53종 중 50 KILLED**(escape 3 = 봉인 3건 신설 + 등가 1) · 차분 5,000×2 조합(cap=OFF 5,000 HEAD 완전 동일 ·
터틀 K축 심사 502 차이 0 · ρ 비초과 4,374 차이 0 · **수량 증가 0**) · 경계 전수 **12,962,313 조합** 불일치 0 ·
신규 회귀 **161**(행위 103 + AST 58) · 백엔드 **6,587 passed / 1 failed**(Docs 단계 최종 실측 원문 `1 failed, 6587 passed, 10 skipped, 329 xfailed, 12 xpassed in 215.85s`). 유일 실패 = `test_cycle76_request_5xx_dedupe::test_g_md4` **환경 결함** — 로컬 `.token_cache` 가 있으면 부팅 통합 테스트가 실제 KIS 호출을 내 모듈 전역 `_quote_5xx_dedupe` 를 오염시킨다(클린 HEAD 사본에 같은 캐시를 복사하면 **동일 재현**, 없으면 통과. CI 는 캐시가 없어 초록. cycle245 무관, 후속 F-14). ⚠️ 이 실행에는 **동시 진행 세션(cycle249)** 산출물이 섞여 있다 — cycle245 단독 기준은 그 파일들 제외 시 **6,479 PASS**.

---

## 🔐 cycle243 · API 인증 (2026-09-03 구현 완료 · 배포 대기) + 후속 F1~F9

> **배포 전 현재 상태 = 인터넷의 누구나 이 계좌의 매매를 조작할 수 있다.**
> 메인 세션 실측: `curl http://3.38.228.74/api/trading/status` → **200(무인증)**.
> 같은 :80 표면에 `POST /api/trading/manual-sell`(임의 종목·수량 시장가 매도) ·
> `POST /api/trading/stop`(보유 전 종목 손절 정지) · `PUT /api/strategies/{id}/params`
> (손절%·`max_positions` 화이트리스트 없이 덮어쓰기) 가 함께 열려 있다.
> 리포 private 전환은 **소스 노출만** 닫았고 런타임 표면은 그대로였다.
> 명세(Red·상세 근거) = `_workspace/red/cycle243_api_auth_spec.md`.

### 배포 (2단계 — 창이 다르다)

| Phase | 내용 | 창 | 선행 조건 |
|---|---|---|---|
| **Phase 1** | nginx Basic Auth(사이트 전체 = SPA + `/api`) + `proxy_set_header X-API-Key` 주입. **프론트 자산만** 건드려 백엔드 이미지·config 해시가 불변 ⇒ backend 무재시작 | **장중 가능**(cycle232 D6 미적용 — 근거는 "재시작 tick blind" 인데 재시작이 없다). ⚠️ 커밋에 `src/**`·`requirements.txt`·backend 블록·`.env` 가 **한 줄이라도** 섞이면 전제 붕괴 | EC2 `secrets/.htpasswd` 선생성(755/644 — uid 101 vs 1000, 700/600 이면 자격 요청 전부 500) |
| **Phase 2** | 백엔드 `X-API-Key` 미들웨어(**fail-closed** · `/health` 만 예외) + CORS `*` 폐지 + 상태변경 Origin 검사 + backend ports `127.0.0.1:8000:8000` | **15:30 이후**(보유 있으면 필수 — 백엔드 재시작 1~5분 tick blind) | `.env` 에 `API_AUTH_KEY` 32자↑ 1줄 존재 증명(`grep -c '^API_AUTH_KEY=.\{32,\}$' .env` → 1). **이 게이트를 건너뛰면 대시보드가 전면 401** |

- **포트마다 필요한 인증이 다르다** — :80(nginx 경유) = `-u <USER>:<PASS>` / EC2 내부
  :8000 직결 = `-H "X-API-Key: …"`(nginx 미경유라 basic auth 무의미). 비상 매도 경로가
  :8000 직결이라 이걸 틀리면 **사고 당일 401 로 손이 묶인다** → `monday_0831_guide.md` 참조.
- **두 Phase 사이가 위험 창(L3)** — Phase 1 만으로는 backend :8000 이 AWS 보안그룹에만
  의존한다. Phase 1 당일 장 종료 직후 Phase 2 배포가 기본, 지연되면 SG 8000 인바운드
  부재를 콘솔에서 재확인한다.
- 401 fail-closed 복구는 `git revert` 왕복이 아니라 **`.env` 키 주입 + `docker compose
  -f docker-compose.prod.yml up -d`**(수십 초, 컨테이너 재생성 동반).

### 남는 위험 (배포해도 사라지지 않는다)

- **L1 · TLS 부재 (최대 잔여 위험)** — Basic Auth 자격과 X-API-Key 가 **평문 HTTP** 로
  오간다. 경로상 관찰자는 자격을 그대로 획득한다. 이번 사이클은 "익명 인터넷 전체 →
  자격 보유자 + 경로 관찰자" 로 줄일 뿐 **없애지 않는다**. → 후속 **F1(HTTPS)**.
- L2 단일 공유 키·단일 계정(주체 식별·감사 추적 없음) / L7 rate limit 없음(무차별 대입
  방어 없음) / L8 인증은 실수 방어가 아니다(`PUT /api/strategies/{id}/params` 는 인증
  후에도 화이트리스트 없음) / L10 대시보드에 401 공통 처리 없음(폴링만 조용히 실패).
- L4 nginx 실기동 자동 가드 부재 — vitest(jsdom)·Playwright(vite dev) 둘 다 nginx 미경유.
  리포에 남는 것은 텍스트·AST 가드뿐이고 실검증은 배포 후 수동 curl.

### 후속 (우선순위 순)

| # | 항목 | 우선도 |
|---|---|---|
| **F1** | **HTTPS 도입**(Caddy 자동 인증서 또는 ALB+ACM) — L1 해소. 도메인 필요 여부 사용자 결정 | **최우선** |
| **F2** | **AWS 보안그룹 80 인바운드를 운영자 IP 로 제한** — 사용자 콘솔 작업(코드 범위 밖), 즉시 가능한 최대 효과 | **즉시 권고** |
| **F3** | `PUT /api/strategies/{id}/params` 파라미터 화이트리스트(cycle223 F2 비대칭 해소, L8) | 높음 |
| **F4** | axios 401 인터셉터 — 재인증 안내/리로드(L10) | 중 |
| **F5** | 키 회전 절차 문서화·스크립트화(회전은 frontend·backend **동시 재시작** 필요 = 장중 불가, L6) | 중 |
| **F6** | `_endpoint_metrics` raw path 키 상한 또는 라우트 템플릿 정규화(L9) | 중 |
| **F7** | 감사 로그 — 상태변경 엔드포인트 호출자·시각·페이로드 요약(L2) | 중 |
| **F8** | nginx `limit_req` — 폴링 18곳(최단 3초) 실측 기반 임계 산정 후 도입(L7) | 낮음 |
| **F9** | `/docs`·`/redoc` 운영 완전 비활성(`docs_url=None`) 여부 결정 — 현재는 인증으로 보호만 | 낮음 |

---

## ✅ 2026-09-05 사용자 결정 세트 (아침 리포트 §4 D1~D11) — 처리 현황

> **주말 보고서(09-05 12:2x 게시)**: https://claude.ai/code/artifact/0c558bf8-4fa8-45d0-8aa4-98ab392ffb46 · 원문 `_workspace/reports/2026-09-05_weekend_decision_set.md`. 남은 사용자 답 = ① DNS A 레코드 등록(오늘) ② D4 월요일 착수 승인 ③ ~~D3 권고 B 채택~~ **09-05 12:5x 채택 → cycle254 구현 완료(배포 대기, D3 행 참조)** ④ DailyReportTab 시각 서식 전환 여부 · 표 = D10 착수 요일 · D8 후속(채널 리졸버, 월 09:30 프로브 결과 후).

| 항목 | 결정 | 처리 |
|---|---|---|
| D8 채널 프로브 | 진행 | ✅ **EC2 cron 등록 완료(09-05 06:57)** `30 0 7 9 *` = 월 09-07 **00:30 UTC = 09:30 KST**(호스트 crontab 은 UTC, 실측 정정) — `tools/ops/channel_probe.sh`(후보 순차 POST → 5분×3 상태 → 전부 DELETE, `in_desired_now` 즉시 해제, 자기 제거). 결과 = `~/auto_stock/logs/channel_probe_20260907.log` + `[krx_channel_probe]` 시스템 로그 → 20:20 일일 루틴이 읽음. 판정 후 B(채널 리졸버) 착수 여부 결정 |
| D3 터틀 1주 폴백 ρ 노출(F-9) | 권고 B 채택 → 구현 완료 | ✅ **cycle254 구현·**배포 완료 09-05 14:08**(마커 92e75f3)** — 선결 확인(09-05 DB 실측 donchian_swing·kojiro `sizing_mode=turtle` = F-9 실재) 후 자문 권고 B(`min` 합성, K_ρ 2.5 유지) 그대로 구현. `_apply_ratio_notional_cap` 조기탈출을 `governs and gov_reason=="probe_error"` 한 조건만 남기고(그 외엔 K축 심사 여부와 무관하게 ρ캡 적용), `[ratio_cap_config]` 라벨 `backstop`→`on` 통일. `strategy_base.py` **단독**, 8영역·scheduler·turtle_sizing·portfolio_risk·전략 7파일 diff 0. 검증 = 뮤테이션 3라운드(15/15·8/8·9/9) 전부 KILLED · 격자 6,458 조합(터틀 4,400 중 차이 624 전부 1주 폴백→0·증가 0) · 전체 회귀 4,722 PASS. 정본 문서 5곳(루트/leader rules/engine·strategies CLAUDE.md/본 워크리스트) 동반 개정. **F-9 종결** — 남은 것은 장외 배포(주말) + D+1(월 09-07) `system_logs` 7서명 확인뿐(상세 `docs/HARNESS_CHANGELOG.md` cycle254 행) |
| D4 `_bought_today` 선기록(F-10) | **월요일 착수 승인(09-05 12:5x)** | 명세 `_workspace/specs/cycle_next_D4_bought_today_after_fill.md` — 권고 A(주문 접수 훅), `order_engine.py` 1곳 승인 완료 → 월 09-07 장외(15:30 이후 또는 07:55 전) 배포 |
| D5 TLS | `auto.dkstock.cloud` | ✅ **완료 09-05 13:06** — DNS 등록(사용자) → certbot 발급(만료 2026-12-04, snap 타이머 + renewal conf `renew_hook` nginx reload) → `.tls_enabled` 마커 → frontend 만 오버레이 재기동(백엔드 무재시작). 외부 실측 https 401·TLS1.2/1.3·http 401 유지·ACME 404. 첫 실행 4/6 거짓 실패(`/etc/letsencrypt/live` root 700) → `sudo test -f` 수정 b46f1f4. 루틴 2개 BASE → https(연결 실패 시 http EC2 예비 + 마지막 메시지에 사용 주소 표기). **남은 사용자 할 일 = 클라우드 환경 '자동매매' 허용 도메인에 `auto.dkstock.cloud` 추가**(월 20:20 루틴이 '예비 주소 사용' 이라고 쓰면 아직 안 된 것). 2단계(HSTS·http→https 리다이렉트)는 루틴 예비 경로 제거 후 |
| D9 REST 폴 조기 시작 | 권고대로 적용 | `SWING_REST_POLL_EARLY_START` 09:05 → **09:00:30** (scheduler.py 상수 1줄, 3,999L 불변, 테스트 갱신). D+1 = 09:00:3x 부터 `[swing_rest_poll_summary]` held_only 폴 |
| D10 pg acquire 타임아웃 | 주중 별도 사이클 | 명세 초안 `_workspace/specs/cycle_next_D10_pg_acquire_timeout.md` — 호출자 전수 + 8영역 승인 동반 |
| D11 리팩토링 카드 | 진행 | ①②③ 완료(새벽) · **⑨⑩ 완료(cycle256, 09-05 08:xx)** — ⑨ 는 PortfolioRiskCard 1사이트 + 유틸 신설로 한정(DailyReportTab 서식 전환 `2026. 9. 7. 9시 5분 0초`→`2026-09-07 09:05:00` 은 09-05 오후 "바꾸자" 로 **cycle256-F 적용 완료**), ⑩ 완료. **⑧ 완료(cycle257, 09-05 09:xx — scheduler 3,999→3,864L, 인계: `handler.py:78` 주석은 B 사이클)**. **④⑤ 완료(cycle258, 09-05 10:xx — 차분 13,000+ 조합 불일치 0, 뮤테이션 27/27)**. **⑥⑦ 완료(cycle259, 09-05 11:xx)** — **D11 10장 전부 처리**. 잔존 = 8영역 권고 4곳(`risk.py:244,419`·`scanner.py:388`·`kojiro.py:987` 관측 배관) · `handler.py:78` 주석(B) |
| D1 리포터 비밀번호 | 유지 | 변경 없음 |
| D2 OpenAI 경로 | 09-19 까지 병행 후 결정 | 변경 없음 |
| D6 주간 자문 정본 위치 | 09-08 첫 산출물 후 | 변경 없음 |
| D7 리포트 판독 채널 | 유지 | 변경 없음 |

## ✅ cycle261 · DK Stock 디자인시스템 v2 적용

> 기록 정정(09-06 00:1x): 폰트 TTF 3파일은 사용자가 스테이징해 둔 상태였고, 3부 보고서 커밋 `340a297`(09-05 22:0x)이 `git commit` 으로 스테이징 전체를 포함하면서 **먼저 들어갔다**(그 커밋이 CI + frontend 모드 배포 1회를 유발 — 백엔드 무접촉). cycle261 커밋 `ad2ffb4` 메시지의 "폰트 3개 커밋" 은 실제로는 `340a297` 이다. 기능 영향 없음.
 (2026-09-05 저녁, 사용자 지시 `dk-stock-design/handoff/` 절차대로 · frontend 전용 · src·8영역 diff 0 — **배포 대기**)

- 가을 팔레트(`index.css` @theme 별칭 재정의로 기존 className 무수정) + Gmarket Sans 3 weight + 손익색/전략 7색 재정의 + 브랜드명 "AutoStock"→"DK Stock". tester 적대 검토가 별칭 재정의 부작용(보드·토글·게이트·체결상태 배지 hex 충돌 4건)과 nginx `/fonts/` 캐시 결손을 찾아 시정 완료. 게이트 전부 PASS(`tsc -b` 0·`npm test` 76/557·`npm run build`·e2e 33·백엔드 frontend 가드 235). 상세 = `docs/HARNESS_CHANGELOG.md` cycle261 행, 명세 = `_workspace/specs/cycle261_dk_stock_design_v2.md`.

## 🔴 P1-7 · 통합 채널 H0UNCNT0 무송출 — KRX 단독(`nxt_tradable=False`) 종목 장중 stale 33% (포렌식 2026-09-05 확정, A=cycle252 야간 진행 · B=8영역 승인 대기)

- **사실**: 09-01~09-04 구독 184~209종목이 `nxt_true ↔ H0UNCNT0 프레임>0` / `nxt_false ↔ 프레임=0` 으로 예외 0 완전 분할(064550 NXT 편출 자연 실험 포함). 유동주(005935 3,538억·035720 등) 포함 = 채널 결함(가설 ≈90%, KIS 문서·MCP 샘플에 대상 범위 무명시). 최소 07-24 부터 만성 — "09-01 이후" 는 INFO 2일 retention 착시. 정본 = `_workspace/forensics/stale_candidates_0904.md`.
- **비용**: K watcher 종목당 ~134회/일 unsub/sub → SEND ≈14,600/일 · `[ws_ack_orphan]` 7,120 · 풀 슬롯 22~24% 낭비. **손절 사각**: 보유 000815·003490(kojiro) WS blind, REST 폴 60s(09:05~15:20)만 — 공백 09:00~09:05 + 15:20~15:30. tick 전략이 nxt_false 를 보유하면(편출 사건) 손절 평가 0. tick 전략 매수 35일 60건 100% nxt_true = KRX 단독(시총≥1,000억의 64%) 구조적 배제.
- **A (cycle252, 비8영역) — ✅ 구현·검증 완료(2026-09-05 03:0x, 뮤테이션 26/26·차분 6,200 조합 0 불일치·회귀 51, 커밋·배포 = 야간 진행)**: LOW no_feed 종목의 K watcher SEND·스탬프·history 만 중단(HIGH byte 동일, `_stale_retry_count` 는 계속 — universe guard 축출 경로 보존), `[no_feed_held]` 1회/일, `[stale_watcher_summary] no_feed_skipped=`. `[tick_coverage] stale` 은 **불변이 정상**(scheduler 무접촉·은폐 금지). D+1 = `[stale_force_retry]` 09:05~15:20 399→≈0, 보조 SUBSCRIBE ≈957→<150.
- **B-0 프로브(cycle253, 2026-09-05 야간 구현·검증 완료, 배포 = 야간 진행)**: `POST/GET/DELETE /api/realtime/channel-probe` — 8영역 무접촉, 기본 OFF. **월 09-07 09:30 실행이 승인 사안**(절차 = `_workspace/morning_0905_report.md` §7). `received=true` → B 착수 / 15분 미수신 → KIS 문의.
- **B (승인 필요)**: 속성 기반 채널 리졸버 `tick_tr_id_for(ticker)`(`nxt_false → H0STCNT0`) — `TICK_TR_ID` 직접 사용처 전부 경유 + 풀 TICK 필터 집합화 + 동일 종목 이중 채널 금지 + 편출/플리커 debounce. **1단계 = 다크런치 프로브**(보조 세션 1개, 005935·035720 H0STCNT0 구독 → 프레임 실측 1시간). 접촉 8영역 = `scanner.py`·`websocket.py`·`websocket_pool.py`·`order_engine.py:1104`. 사이클 26 시간대별 전환(`get_active_tick_tr_ids`·`_board_transition_loop`)은 죽은 코드 — refactor-review 로 처분 + `src/realtime/CLAUDE.md` 전환 서술 정정.
- **C (임시)**: `SWING_REST_POLL_EARLY_START` 09:05 → 09:00:30(held_only) — scheduler 상수 1줄(라인 상한 주의). **D (관측 정정)**: `[stale_watcher_detail] @ts` 는 마지막 재등록 시각(`resub@` 로 정직화), 루틴 리포터 가이드 "stale 35~38 은 A 배포 전까지 예상값 — 재구독·재시작 처방 금지".

## 🔐 cycle249 · 일일 로그 분석 이관 1단계 — 리포터 스코프 + 번들/외부 API (2026-09-05 00:29 배포 완료 2f76490 · W1/W2 종결)

20:10 OpenAI 일일 로그 분석을 **Claude Code 클라우드 루틴**(매일 20:20 KST)으로 이관하는
1단계. `authorize()` 에 리포터 스코프 판정(GET/HEAD 전체 + `POST /api/log-reports/{date}/external`
단 한 경로) + nginx `map $remote_user` 사용자별 키 주입 + `GET /api/log-reports/bundle` +
`POST /api/log-reports/{date}/external` + migration 042(`ext_*` 6컬럼). 8영역 diff 0,
`generate_daily_log_report` 행위 byte 동일(신규 회귀 107 + 기존 47 전부 그린). 상세는
`docs/HARNESS_CHANGELOG.md` 2026-09-04 cycle249 행.

### 후속 처리 현황 (2026-09-05 야간 자율 작업)

| # | 항목 | 비고 |
|---|---|---|
| **W1** | ✅ **완료** — 클라우드 루틴 `trig_01E6XNiNTxaLWNn7jeTXR9qZ` "auto_stock 일일 운영 리포트 (20:20 KST)"(cron `20 11 * * 1-5` UTC, env 자동매매, `claude-fable-5-1`, 커넥터 Notion 만). 자격 = 환경 변수 `REPORTER_BASIC_PASSWORD`(Basic 사용자 `reporter`, htpasswd 는 환경 변수 값 기준으로 09-05 00:41 재생성), 네트워크 = Custom 허용 도메인 `ec2-3-38-228-74.ap-northeast-2.compute.amazonaws.com`. 산출 = `POST /api/log-reports/{date}/external` + Notion 상위 페이지 https://app.notion.com/p/3d1438fa0d268118872bfe83f71fb240 . 수동 백필 = Run now 에 `date=YYYY-MM-DD`. 스모크 1차(00:31) 는 htpasswd 불일치 401 로 실패(루틴이 실패 페이지·푸시 알림 생성 = 설계대로), 2차(00:42) 진행 결과는 아침 리포트 참조 |
| **W2** | ✅ **완료** — 25b6951(frontend 전용): `DailyReportTab` 에 "Claude 분석" 블록(ext_summary·ext_findings 정렬·ext_report_md 접이식 원문)·목록 "Claude" 배지, ext 부재 시 ReportCard DOM 파리티, ext_findings 정규화 + ReportCardBoundary. vitest 479 PASS. 병행 1~2주 관찰 후 OpenAI 경로 off 스위치 도입 여부 결정(→ W4) |
| **W3** | ✅ **생성** — 주간 파라미터 자문 루틴 `trig_01H1TtfhP52CXKuyxwG2KnBW` "auto_stock 주간 파라미터 자문 (화 20:30 KST)"(cron `30 11 * * 2`, 첫 실행 09-08 화 20:32). 프롬프트 = `advisor_prompt_review_20260903.md` §F v2 원칙(목적함수·절대 금지 키·사람 결정·표본 N=10·전략당 최대 3키) 이식, 산출 = PR `_workspace/domain_consult/weekly_advice_YYYY-MM-DD.md`(브랜치 `claude/weekly-advice-*`, 자동 적용 없음) + Notion 상위 https://app.notion.com/p/3d1438fa0d2681ae9502c26d1a2c4ebe . 첫 산출물 검토 후 프롬프트 §4/§5(봉인 키·결정 로그)를 코드 정본(`advisor_policy.py`, 사이클 A)으로 옮길지 결정 |
| **W4** | ⏳ OpenAI 경로 처분 — 20:00 자문(`recommendation_engine`)·20:10 분석(`generate_daily_log_report`)은 병행 비교 기간(~09-19) 동안 유지. 이후 `system_config` 토글로 off(코드 사이클 필요) |

배포 전제(cycle243 규약 승계) = `.env` 에 `API_REPORTER_KEY` 추가는 backend 를 재생성한다
(Phase 2 창, 15:30 이후) + `secrets/.htpasswd` 에 `reporter` 사용자 추가는 호스트 작업(git 밖).

---

## 📋 활성화 게이트 4건 (구 `monday_activation_guide.md` 에서 이전, 2026-09-02)

> 원본은 2026-08-10 대상 가이드라 날짜는 지났으나 **게이트 조건 자체는 날짜 무관**이라
> 삭제 전 여기로 옮긴다. §6(포트폴리오 SOFT 상한)은 cycle233 으로 **완료**되어 제외.

### ▶ G-8. VCP/BFB 브레이크이븐 승격 — ✅ **VCP 는 이미 활성 (2026-09-02 운영 DB 실측)** · BFB 대기

> **09-02 정정** — 사용자 결정 "G-8 진행" 후 운영 DB 를 읽어 보니 `vcp_breakout.params` 에
> **`breakeven_promote_atr: 1.5` 가 이미 들어 있다**(`strategy_config.updated_at` 2026-08-18
> 08:10 UTC 이후 변경 없음 — 사이클 C(07-30) default-off 배포 후 어느 시점에 DB 로 켜진 값).
> BFB 는 `0.0`(비활성, 코드 기본값). 따라서 아래 UPDATE 는 **실행 불필요·실행 금지**(중복
> 적용은 무해하나 "이날 활성화했다"는 오귀인을 만든다). `[vcp_breakeven_promote]` 로그는
> **0건** — 활성 상태지만 VCP 체결이 전 기간 0건이라 발화할 포지션이 없었을 뿐이다.
> **남은 액션** = VCP 첫 체결 후 래치/승격 발화 관찰 → BFB 활성 여부 재평가(NO-GO 시 2.0N).

- **게이트 정의**(원본): donchian `[donchian_breakeven_promote]` **발화** + 이후 whipsaw
  (승격 직후 손절) **부재**. 원본 작성 시점(08-08)엔 "21일간 0발화·SELL 0건"이라 미충족이었다.
- **09-01 실측 = 첫 발화**: `192820` 고점 306,500 ≥ 매수가 273,500 + 1.5×ATR(16,778) →
  손절선 **239,944 → 273,500** 승격. 이후 18:09:50 애프터에 **275,500 원 매도(+2,000)**.
  시장가 거부(APBK3013)를 지정가 폴백이 받아냈다.
- ⚠️ **whipsaw 판정은 사용자 몫**이다. 두 해석이 다 성립한다 —
  (a) **clean**: 승격이 없었으면 손절선이 239,944 라 훨씬 아래까지 끌려갔을 것이고,
      실제로는 **손실 없이(+2,000)** 빠져나왔다 = 플로어가 의도대로 작동.
  (b) **whipsaw 성격**: 고점 306,500 대비 **−10.1% 반납** 후 승격선 부근에서 청산 =
      cycle220 자문이 지적한 "MFE 대비 반납" 패턴의 재현.
  표본이 **N=1** 이라 어느 쪽도 통계적 근거는 아니다.
- ~~**활성화 시(장 마감 후 DB)**~~ — **VCP 는 이미 적용됨(09-02 실측), 실행하지 않는다.**
  BFB 활성화 시에만 아래를 `strategy_id='bull_flag_breakout'` 로 바꿔 사용:
  ```sql
  -- BFB 전용 (VCP 관찰 후 GO 판정 시). VCP 는 이미 1.5 — 재실행 금지
  UPDATE strategy_config SET params = params || '{"breakeven_promote_atr": 1.5}'::jsonb
   WHERE strategy_id='bull_flag_breakout';
  ```
- ⚠️ VCP/BFB 는 **체결 0건**이라 활성 상태여도 당장 검증할 포지션이 없다.
  BFB 는 09-01 래치 첫 무장(`001450`)까지 갔으므로 첫 체결 후 재검토가 순서다.
- 확인 명령(읽기 전용): `SELECT strategy_id, params->>'breakeven_promote_atr' FROM strategy_config
  WHERE strategy_id IN ('vcp_breakout','bull_flag_breakout');` → 기대 `1.5` / `null|0`.

### ▶ G-8′. BFB·VCP 진입 완화 1차 (2026-09-03 07:40 적용, 사용자 결정 "기준을 조금 완화해 매수가 진행되게")

- **근거** = `_workspace/domain_consult/bfb_vcp_entry_relax_20260903.md`(6렌즈 실측 + 적대 비판 18건 반영). 08-31 개방 후 3영업일 체결 0. 병목 실측: **BFB 는 임계가 아니라 시계** — 게이트가 'flag 일평균 × 1.0' 을 요구하는데 관측 창 09:05~13:00 이 하루 누적의 65~70% 라 실효 요구치가 EOD 1.43~1.54배, 그 앞단 retention 1분이 래치 무장까지 차단(감지 4건 중 3건이 1~23초 후퇴 사망). **VCP 는 prepare() 가 후보를 못 만듦** — pullback 상한이 아니라 자(ruler) `min_swing_atr_mult=0.5` 가 미세 진동을 조정으로 세어 회수를 5~6 으로 부풀림. 공통: 후보 20~32% 장중 틱 무수신(파라미터로 못 고침).
- **적용(PUT /api/strategies/{id}/params — `_config_loaded` 가 프로세스당 1회라 SQL 만으론 당일 미실효)**: BFB `entry_end` 13:00→**14:30** + `breakout_retention_minutes` 1→**0** / VCP `min_swing_atr_mult` 0.5→**1.0**. 거래량 배수(1.0/1.2)·추격 상한(5.0/7.5)·손절 **무변경**(품질 임계 불변). 메모리·DB 모두 반영 확인.
- **✅ D+0 결과 (09-03 11:33) — BFB 첫 체결**: `001450` 1주 @ 53,900. 09:26:26 `[bfb_latch_armed]`(retention 0 효과) → 11:33:43 `[bfb_vol_gate_pass] observed=501912 threshold=485973 latch_age_sec=7637`(래치 2시간 7분 유지 = "시계" 가설 확증, 관측/임계 1.033). **`entry_end` 14:30 은 미실효(11:33 < 13:00) — 공로는 retention 0 단독.** ⚠️ **프로토콜 발동 = N=10 왕복까지 BFB 진입 파라미터 전면 동결.** VCP 는 `pullback=1` 여전(`min_swing_atr_mult` 1.0 무효) — 2차 노브 조건(고유 후보 ≥3 × 3일 누적 0건) 미달.
- **기대** = 합계 0.2~0.5건/일(BFB 0.15~0.35 + VCP 0.05~0.15), 3영업일 0.6~1.5건. 개방 규모 만기 645,533원 = NAV 25%, 9포지션 동시 손절 최악 NAV 1.45%.
- **프로토콜** = 최소 5영업일 또는 체결 3건 중 먼저 동결. 체결 1건이라도 나면 N=10 왕복까지 진입 파라미터 전면 동결(cycle228 계약). 2차 노브는 달력이 아니라 **기전 증거**로: 래치 ticker 의 EOD 실봉 acml_vol ÷ flag_avg_volume = R 을 매일 역산 → (래치 ≥5 ∧ R 중앙값 ≥1.2 ∧ pass 0) 이면 시계 가설 확증 → `entry_end` 15:00 / (R 중앙값 <1.0) 이면 진짜 거래량 부족 = 아무 노브도 안 연다. VCP 2차 = 고유 후보 ≥3 종목 3일 누적 0건일 때만 `base_max_days` 45.
- **영구 기각** = `breakout_volume_mult` 0.7(거래량 없이 뚫는 건 안 뚫린 것 — 09-01 실패 돌파 60% 가 그 대역) · `pullback_count_max` 확대(측정 반증: 추가 통과 0/18) · `entry_end` 15:20(종가 단일가 오버나잇 경로).
- **일일 5지표** = `[bfb_latch_armed]`(09:05:0x 첫 틱 아티팩트 분리) · `[*_vol_gate_pass]` 발생 시각 · `reason=extension` · `[stale_watcher_detail]` · `[*_vol_gate_no_data]`. **첫 실패 모드 예상** = 09:05 첫 틱 갭업 체결(retention 0) — 방어는 추격 상한 5.0%·손절 −5%.
- **롤백**(PUT 로 원복: BFB entry_end 13:00·retention 1 / VCP swing 0.5) = 하루 BFB 3건↑ / 누적 5건 승률 ≤1/5 또는 실현손실 NAV 1%↑ / gate_pass 직후 −5% 손절 3연속 / 14:00 이후 체결 편중 전손.
- ⚠️ **운영 주의** = ① retention 0 은 PARAM_RANGES (1,30) 밖이라 20:00 자문이 매일 '교정' 을 제안 — **BFB/VCP pending 자문 수동 apply 금지**, 09-02 pending 2건(비중 감액 + `max_scan_stocks` 500 = 유니버스 87% 축소)은 UI 에서 거절 권고 ② PUT 은 params dict 전체를 DB 에 핀 — 이후 코드 DEFAULT_PARAMS 변경이 두 전략엔 전파되지 않음(기존 breakout_volume_mult 함정과 동형) ③ 매일 07:56~58 `stock_master_daily` placeholder(volume 0) ~970행이 flag_avg_volume 을 희석 — 체결 시 flag 구간 0봉 여부 확인.

### ▶ G-9B4. VB 실패돌파 조기청산 — 백테스트 스윕 대기

`failed_breakout_buffer_pct` / `failed_breakout_confirm_ticks` 외부 MCP 스윕(VB 는 YAML DSL 지원)
→ avg_loss↓·RR↑ 확인 → `failed_breakout_exit_enabled=true` DB 활성 → te_metrics 재측정.
VB 는 사이클 F 실측 **유일 열위**(승률 35%·RR 1.35 < 필요 1.83)라 우선순위가 높다.

### ▶ G-9B5. VB RS/RSI 진입 품질 필터 — 유의성 검정 대기

사이클 G(08-02) 관찰 시작. 고RS/저RSI극단 vs 저RS/고RSI 승률·RR 유의성 검정 → 유의 시
RS(B2) 실배제 우선 활성. ⚠️ 별도 실측(`project_vb_observation_hooks_verdict` 메모리)에서
**1,498 관측 전부 무신호·RS 는 역방향**으로 나와 **무기한 보류** 상태 — 재개는 레짐 전환 후.

### ▶ G-7. VCP/BFB 터틀 sizing — 구조적 봉인

외부 백테스트 스윕이 게이트인데 **VCP/BFB ∈ `_FALLBACK_STRATEGIES`**(recommendation_engine.py)
라 MCP YAML DSL 미지원 ⇒ 스윕 자체가 불가. 대안 = (a) 로컬 백테스트 어댑터 구현 또는
(b) 확대 유니버스로 라이브 체결 축적 후 실측. ⚠️ **터틀 전환 시 `max_lot_units`(K=2.0) 캡이 자동 편입**된다(cycle242 — 캡 게이트가 `sizing_mode == "turtle"` 이라 DB 키를 켜는 순간 두 전략의 모든 랏이 K 유닛 이하로 잘린다). 게이트 통과 판정 시 이 축소 효과를 백테스트 전제에 반영할 것.

---


## ✅ G0 · 1주 폴백 = 진입 시점 과잉 피라미딩 — **cycle242 ⓑ 종결 (2026-09-03, `max_lot_units` K=2.0, 커밋 대기)**

**발단** — 피라미딩 심층 검토(`_workspace/domain_consult/pyramiding_deep_review_20260903.md` §0.0·§1.2·§4.3)가
**사다리를 얹기 전부터 첫 랏이 이미 과대**임을 실측했다. 09-03 아침 리포트 §7 #1 에 대한 사용자 결정 =
**ⓑ 폴백 notional 상한 먼저**(ⓐ "<1주면 스킵"은 donchian 거래 ~79% 감소라 표본 확보 후 재검토).

**실측 (120일 BUY 226건, `_workspace/pyramiding_review_20260903/`)**

| 지표 | 값 |
|---|---|
| 1주 매수 비율 | **170/226 = 75.2%** |
| donchian 실제 1랏의 터틀 유닛 배수 | 평균 **4.94** · 중앙 4.42 · **최대 15.61**(086280 현대글로비스 1주) |
| kojiro 동 배수 | 평균 1.52 |
| 1주 폴백 스택 −30% 시 계좌 손실 | **8.83%** |
| 관측 증거 | cycle233 `[oversized_fallback]` 이 R15 위반을 이미 실측(000815 3.10배·4.11유닛) |

**확증 원인** — 터틀 사이징(`compute_unit_qty_guarded`)이 이론 유닛 <1주를 내면 관문
`StrategyBase._apply_budget_limit` 이 `_fallback_one_share` 로 **1주를 산다**. 그 폴백의 유일한 상한은
"잔여 ≥ 현재가"뿐 — 가격·ATR·유닛 대비 상한이 **전무**했다. 터틀 경로에는 변동성 floor·잔여·notional
3중 상한이 무조건 걸리는데, **그 상한을 통과 못 한 종목이 오히려 무상한 1주로 사는 역전**이다.
구조 항등식: 폴백 ⇔ `P > ρB` ⇒ 유닛 배수 `M1 > (ρ/r)·ATR%` = donchian **40×ATR%**(중앙 6.10% → >2.44).
⚠️ **같은 항등식이 PR 낙하 랏**(터틀 0 → `floor(ρB/P)`주, donchian 최대 3.71유닛)**에도 성립** —
"폴백만" 막는 스코프로는 G0 가 종결되지 않는다(그래서 적용 범위를 터틀 전략의 **모든 랏**으로 잡았다).

**시정 (`src/engine/strategy_base.py` 단독 + 터틀 4전략 `DEFAULT_PARAMS` 각 1줄)** — 관문 안, 폴백/잔여
클램프 **뒤** · `[oversized_fallback]` 관측 **앞**에서 `sizing_mode == "turtle"` 전략의 랏에
`min(final, compute_unit_qty(budget, atr, risk_pct, fraction=K))` 적용, 0 이면 매수하지 않는다.

**결정 12(domain-consult `cycle242_fallback_notional_cap.md` 채택)** — ①`max_lot_units` **2.0** 전 전략 공통
(K 는 `예산×risk_pct` 로 이미 정규화된 무차원 수) ②척도 = **ATR 축**, `compute_unit_qty(fraction=K)` **재사용**
(새 수식 0; ρ 축은 관측으로 **병존**) ③범위 = **터틀 전략의 모든 랏**(고정%손절 5전략은 `position_ratio` 가
이미 리스크 균등이라 범위 밖) ④관문 안·관측 앞 ⑤**시그니처 무변경** — `_resolve_sizing_atr` 이 터틀 분기와
같은 `_candidates[ticker]` 를 read-only 로 읽고 `("atr","atr14")` 두 키 상이 시 불채택 ⑥**fail-open + LOUD**
⑦마커 5종 ⑧`PARAM_RANGES`/`INT_PARAMS` 편입 금지 + 읽는 쪽 `[1.0, 20.0]` 클램프 ⑨래치 신설 금지
⑩기대 효과(아래) ⑪**G0 종료 기준 재정의**(아래) ⑫정본 문서 6종.

**전제 정정 5(코드 재실측, 결론 불변)** — ①진단이 예고한 "기존 테스트 6+ 파손·cycle233 계약 폐기"는
결정 ③ 게이트 아래서 **파손 0**(cycle233 6케이스·A-FALLBACK·Case A/D/E·전략 폴백 3건 전부 게이트 off 경로)
→ 계약은 폐기가 아니라 **docstring 재스코프** ②ATR 축을 택해도 시그니처 불변 ③`[fallback_cap_config]` 는
부팅이 아니라 **첫 관문 평가 시** 1회/전략/일(`boot_manager` 무접촉) ④마커는 `reason=` 6종으로 일반화
⑤"as-was K∈[1.0,2.0] 결과 동일"은 08-18 입금 이전 표본의 성질 — 현행 예산 재정규화에선 K=1 → 7/26,
K=2 → 14/26 으로 **2배 갈린다**.

**기대 효과(현행 예산 재정규화, net 2,582,132)**

| 전략 | BUY 생존 | 최대 랏 | 단일 랏 −30% 꼬리(계좌) |
|---|---|---|---|
| donchian | 14/26 (**−46%**) | 8.66 → **≤2.0유닛** | 3.18% → ≤1.45% |
| kojiro | 18/20 (−10%) | 3.44 → **≤2.0유닛** | 4.71% → ≤2.73% |

**T 경로(정상 터틀 랏 — donchian 7·kojiro 13건 전부 ≤1.68유닛)는 한 건도 안 건드린다.** 보유 8종목 무영향(진입 사이징만).

**관측 마커 5종** — `[fallback_notional_capped]`(INFO, 캡 발동) · `[fallback_cap_skipped]`(WARNING, fail-open
+ `atr=`/`units=` 진단 병기) · `[fallback_cap_config]`(INFO 카나리아 `cap=on|off`·`k`·`atr_max`) ·
`[fallback_cap_clamped]`(WARNING, **키 명시 존재 시에만**) · `[oversized_fallback]`(ρ 축, 꼬리 ` units=` 확장).

**D+1 판독 (배포 = 15:30 이후 또는 익일 07:55 `_boot` 전)**

| 채널 | 정상 서명 | 이상 → 조치 |
|---|---|---|
| `[fallback_cap_config]` | donchian·kojiro 각 1행/일 `sizing_mode=turtle cap=on k=2.00`, `atr_max` ≈ 3,873 / 7,746 | `cap=off` = DB `sizing_mode` 리셋(조용한 꺼짐) → 즉시 DB 확인. `k≠2.00` = PUT 변경 |
| `[fallback_notional_capped]` | donchian ≈0.15건/영업일·kojiro ≈0.03 → **대부분의 날 0행**. 첫 실발화 = G0 ① 실증 | 하루 5건↑ × 5영업일 = R2. `units_after > 2.00` = R3 핫픽스 |
| `[fallback_cap_skipped]` | **0행** | `no_atr`/`ambiguous_atr` ≥1 = 후보 dict ATR 배관 결함(매수는 fail-open 으로 현행대로 나감) · `exception` ≥1 = 코드 결함 |
| `[oversized_fallback] units=` | **비제로가 정상**(⚠️ 의미 반전). `units ≤ 2.00` 전수 = G0 ② | `units > 2.00` 1건 = R3. turtle 전략에서 `units=-` = ATR 결손 |
| order_engine "매수 수량 0 → 900s cooldown" | 캡 마커와 **같은 시각·같은 ticker** 짝 = 오귀인 정상 서명(`_bought_today` 로 종목당 1회/일이라 1:1 성립) | 캡 마커 없이 단독 = 진짜 잔여 부족 |
| donchian 실체결 BUY | 주 ~1건(0.175/일) — R1 카운트 시작 | 15영업일 연속 0 = R1 |

⚠️ **의미 반전 2** — `[oversized_fallback]` 은 "0 이 목표"에서 **"≤K 유닛이면 정상"**(비제로가 정상)으로,
order_engine 수량-0 WARNING 은 "잔고 부족"에서 "캡 스킵 포함"으로. **배포 전후 같은 grep 합산 금지.**

**재검토 트리거 (롤백 = 대상 전략 `strategy_config.params.max_lot_units = 20.0` DB UPDATE 또는
`PUT /api/strategies/{id}/params` — 코드 재배포 불필요. ⚠️ 당일 캡→0 으로 `_bought_today` 가 소진된 종목은
**다음 세션부터만** 되살아난다: `cap_qty` 는 D-1 ATR 기반 일중 상수이고 `recompute_held_atr` 유일 호출자는 부팅 전용)**

| # | 트리거 | 임계 | 조치 |
|---|---|---|---|
| R1 | donchian 매수 정지 | 15영업일 연속 BUY 0(기대 2.6건, P(0)≈7%) | K=2.5 완화 검토(사용자 결정) |
| R2 | 캡이 유니버스 대부분을 자름 | `[fallback_notional_capped]` 5건/일 × 5영업일 | K 완화가 아니라 **유니버스 가격 상한** 또는 weight 재검토 |
| R3 | 캡 불성립 | `units_after > K` 또는 `[oversized_fallback] units > K` **1건** | 즉시 핫픽스 |
| R4 | 파라미터 커플링 | weight / `position_ratio` / `risk_pct` 변경 | K 실효 강도가 예산에 선형 비례 → **K 재검토 의무** |
| R5 | 자연 은퇴 | 6개월 무발화 + `P_max` 중앙값 > 유니버스 90퍼센타일 | 게이트 **유지**(자본이 줄면 다시 필요), 삭제 금지 |
| R6 | 피라미딩 착수(T1) | 피라미딩 다크런치와 동시 | **K → 1.0**(K=2 랏 + 4유닛 사다리 = 8유닛 = R15 재위반) |

**⑪ G0 종료 기준 재정의** — 검토 보고서 §4.3 의 "`[oversized_fallback]` 발화 0"은 K>1 과 **논리적 양립 불가**
(캡을 통과한 랏도 ρ 상한을 계속 넘을 수 있다). 실제 종료 = ①`[fallback_notional_capped]` 실발화 1건 이상 ∧
②배포 후 신규 랏 전수 `units ≤ K`(`[oversized_fallback] units=` **와** PR 경로 fail-open 랏의
`[fallback_cap_skipped] atr=`/`units=` 양쪽으로 검증) ∧ ③회귀 가드 존재.

**⚠️ 문서 정정 2(적대 검증 확증, 코드 무변경)** — ①**"K유닛 = 예산 2.0% 노출"은 `_entry_atr` 스탬프 랏 한정**
이다. 폴백·PR 낙하 랏은 미스탬프라 고정% 손절(-7%)을 타므로 실효 상한은 `cap_qty × price × |stop_loss_rate|`
— donchian 실측 최대 **2.09%**·이론 6.99%(kojiro 는 `_position_atr` 을 항상 스탬프하므로 원 서술 성립.
**두 전략을 한 문장으로 묶은 것 자체가 오류**였다). ②롤백 다이얼의 당일 무효(위 괄호).

**ⓐ("<1주면 스킵") 재검토 조건** — 캡 배포 후 donchian·kojiro 각 **N≥20 왕복** 축적 ∧ 캡 통과 랏의 실현 엣지가
캡 이전 표본 대비 열위가 아님 ∧ R1 미발화. 그 전엔 표본이 −79% 로 잘려 어떤 검정도 불가능하다.

**후속 A~G** — A. 6개월 재검정(K 가 자른 고가·저ATR 종목군의 사후 성과 = 선택 편향 정산) · B. 명시 ATR
kwarg 전달(`sizing_atr=`)로 `_resolve_sizing_atr` 덕타이핑 은퇴 · C. 폴백/PR 랏 `_entry_atr` 미스탬프 ↔
재시작 소급 스탬프 불일치(위 문서 정정 ①이 근거) · D. 고정%손절 5전략의 폴백 명목(ρ) 상한 — **LTV 부터**
(오버나잇 갭 실노출) → **cycle245 로 종결**(2026-09-04, `max_lot_ratio_mult` K_ρ=2.5. 다만 5전략 화이트리스트가 아니라 **"K축이 심사하지 못한 모든 랏"** 백스톱으로 구현 — 아래 항목) · E. `[fallback_cap_config]` 부팅 시점 이관 · F. `risk.py:628` 사전 스킵 비대칭 +
order_engine 900s 오귀인 문구(8영역, 별도 승인) · G. `portfolio_risk.compute_over_cap_positions` 에 `units` 병기.

**산출물** — 스펙 `_workspace/red/cycle242_fallback_notional_cap_spec.md` · 자문
`_workspace/domain_consult/cycle242_fallback_notional_cap.md` · 신규 회귀 2파일 **161 PASS** ·
백엔드 전체 **6,163 PASS** · 8영역 + `scheduler.py`/`boot_manager.py`/`turtle_sizing.py`/`portfolio_risk.py` **diff 0**.

---

## ✅ P1-6 · donchian 프리장 청산 보류 게이트에 **매일 ~30초 구멍** — **cycle238 종결 (2026-09-02, 시정안 A, 커밋 대기)**

**발단** — cycle237(청산 로그 cap) 적대 검증이 "08:00~09:00 68건은 프리장 게이트와 모순"이라
지적 → EC2 실측으로 판별한 결과 **게이트는 작동하지만 08:00 정각에 늦게 걸린다**.

**실측 (09-02)**
```
08:00:00  도치안 시간 기반 청산: 034020 ...          ← 청산 평가 통과 (게이트 미적용)
08:00:00  APBK0918 [프리마켓] 시장가 매매 불가        ← 실제 매도 주문이 나갔다
08:00:00  매도 거부 — positions 보존
08:00:29  [pre_market_exit_deferred] donchian_swing  ← 이제서야 게이트 적용
```
같은 패턴이 08-31(08:00:28) · 09-01(08:00:01) 에도 있다.

**원인 가설** — `risk._defers_pre_market_exit` 는 `MarketBoard.PRE_NXT in session_tracker.active`
를 요구하는데, `_session_loop` 가 **30초 주기**라 08:00:00 시점엔 `active` 가 아직 갱신되지
않았다 ⇒ 게이트가 **fail-open**(판정 불가 시 평가 유지)으로 떨어진다. 08:00 은 익일 청산
task 가 도는 시각이라 tick 이 몰린다.

**위험** — 2026-08-06 에 "프리장 왜곡 틱(전일 상한가 종목 시초 하한가 형성 등)의 허깨비 손절·
트레일링 고점 오염 차단" 목적으로 세운 게이트가 **매일 30초 무력**하다. 09-02 엔
`nxt_tradable=False` 라 APBK0918 로 막혔지만, **NXT 거래가능 종목이었으면 체결**됐을 수 있다.
대상은 donchian·kojiro·VCP·BFB·momentum·VB(= LTV 제외 전 전략)의 **멀티데이 보유 포지션**.

**✅ cycle238 시정 (2026-09-02, 사용자 결정 "P1-6 은 A 로 진행", 8영역 승인 `risk.py` 단독)**
- **원인 확증** = 가설 그대로. `active` 의 유일 기록자는 `SessionTracker.tick()` 이고 `_session_loop`
  가 30초 주기로만 호출(`SESSION_TICK_INTERVAL=30`), H0UNMKO0 는 `_last_nxt_mkop_code` 에만 기록
  (`active` 미관여). 07:55 사전구독 첫 틱이 08:00:00 에 오면 `boards_at(07:59)`=∅ 스냅샷이 살아
  있어 게이트 fail-open. 매수측은 2026-05-15 "결함 A" 가 같은 race 를 `board=` 명시로 우회했지만
  청산측 게이트는 그 우회를 받지 못했다.
- **시정** = `_defers_pre_market_exit` 를 `by_active`(기존) **OR** `by_clock`(`session.boards_at(
  _now_kst().time())` fresh — 08:00/09:00 리터럴 신설 금지, 스케줄 표 단일 소스, `_KST` 명시)로
  전환. 화이트리스트 LTV 최상단·평가 보류(주문 보류 아님)·`tradable_boards` 미독 불변. fail-open
  은 **두 소스 모두** 예외일 때만. `by_active` 가 False 인 **모든** 경우(∅뿐 아니라 MAIN/POST
  stale 포함)에 시각이 PRE 면 보류 — tracker 가 1시간 이상 죽어야 도달하는 안전 방향.
- **09:00 정각 판단(team-leader)** = stale `active`={PRE} 잔존 ≤30초는 OR 라 보류 유지 = 현행 라이브
  동일. 안전 방향 + 한 사이클 한 엣지(D+1 귀인) + 개장 30초 스프레드. `reason=active_stale_hold`
  로 계량하고 clock-primary(09:00:00 정확 해제)는 후속 후보.
- **관측** = `[pre_market_exit_gate_divergence] strategy= reason=clock_fallback|active_stale_hold
  active= clock_kst=` 1회/(전략,사유)/일(날짜 키 `_now_kst` 자기 리셋 + `reset_daily_state` 동행
  + peek→로그→mark). 기존 `[pre_market_exit_deferred]` 서식·cap 무변경.
- **결정성** = 루트 `tests/conftest.py` autouse `_pin_pre_market_clock`(`risk._now_kst` 를 MAIN
  10:30 으로 핀, 옵트아웃 마커 `real_pre_market_clock`). 2026-08-06 의 "wall-clock 아님" 계약은
  폐기(08:00 라이브와 테스트 기본이 둘 다 `active`=∅ 라 벽시계 의존이 불가피).
- **검증** = Red 12 FAIL → Green → 적대 검증 뮤테이션 18종 중 escape 4 → 전부 테스트 보강(F1 active
  사망+clock PRE → True · F2 `boards_at` **호출** AST · F3 일치 시 divergence 0 · F4 화이트리스트
  단락) + T-8 가드 과잉(`.time()` 추출까지 금지해 `timetz().replace` 우회 유발) 정밀화. 차분
  3,000×7 `active` 정상 갱신 시 판정 차이 0. hot path +0.3µs/틱. 8영역 sha 핀 3가드 재핀(cycle235
  죽은 핀 삭제).
- **D+1 판독 채널** = `[pre_market_exit_deferred]` 첫 타임스탬프가 08:00:0x 로 당겨지고 같은 시각
  `reason=clock_fallback` 이 동반되면 구멍이 닫힌 것. `도치안 시간 기반 청산` 첫 발화가 09:00 이전
  이면 여전히 결함. ⚠️ divergence 는 **보유 종목 틱이 있을 때만** 계량 — 부재 ≠ 구멍 없음.
- **남긴 후속** = ① clock-primary 09:00 정확 해제(계량 후 판단) ② `_adopts_day_high` 도 `active`
  단독(stale 30초, fail-closed 라 무해 — docstring 만 정정) ③ 형제 관측기 `_maybe_emit_pre_market_
  defer` 의 mark-before-log(관측 전용, 8영역 재승인 필요) ④ T-8 리터럴 가드는 별칭(`time as _t`)
  미검출(기지 한계).

**시정 후보 (기록 — A 채택 / B·C 기각)**
- (A) `_defers_pre_market_exit` 를 **시각 기반 폴백**과 결합 — `active` 가 비어 있고 현재 KST 가
  08:00~09:00 이면 보류로 판정(fail-**closed** 방향). 게이트 목적이 "왜곡 틱 회피"라 보류가
  안전 방향이다. ⚠️ 8영역(`risk.py`) 이라 승인 필요.
- (B) `_boot()` 말미 또는 08:00 task 진입 직전에 `session_tracker.tick()` 강제 1회 — scheduler
  변경이라 라인 상한 가드 확인 필요.
- (C) 관측만 — 첫 청산 로그 타임스탬프가 09:00 이전이면 WARNING(현행 cap 이 이미 시각을 남김).

**판독 채널** — cycle237 cap 이후에도 `도치안 시간 기반 청산` 의 **첫 발화 시각**이 그대로
남으므로 09:00 이전이면 이 결함의 증거다(버스트 크기는 잃지만 시각은 남는다).

---


## 🔴 월요일(2026-08-31) 아침 최우선 — `257720` VB 주말 오버나잇 (cycle232 자문 부속 발견)

`257720`(실리콘투, VB 2주/51,050원, 08-28 09:15 매수, `status=PARTIAL`)이 **주말 오버나잇 보유 중**.
VB 는 15:20 전량청산 전략이라 **오버나잇 손절 규약이 설계에 없다** = 무통제 포지션(계좌 3.9%).
1차 판단 = cycle229 가 시정한 `[단일가매매]` 미분류 매도 거부(3회 재시도 후 **무기록** 포기)의
시정 **전** 마지막 희생자 — 08-28 15:20 청산 시도가 cycle229 배포(15:40+) 직전이었다.

**사용자 결정(08-29): 월요일 09:00 즉시 청산 — 절차 정본 = `_workspace/monday_0831_guide.md`.**

**⚠️ 08-29(토) 로그 실측으로 자문 §5 가설 반증** — 15:20 강제청산은 정상 발화했고("대상:
['035420','257720']"), 실패 원인은 `[단일가매매]` 가 아니라 **APBK0400 "주문 가능한 수량
초과" ×3 → CRITICAL**. 근본 = BUY `0000411400` 이 **PARTIAL 2주** 체결인데
`positions.quantity=3`(주문수량) 잔존 → 3주 매도 시도 → 실보유 2주라 거부.
**월요일 15:20 자동 재청산도 같은 이유로 재실패 확정** → `manual-sell {"ticker":"257720",
"quantity":2}` (실보유 수량!) 이 유일 확실. 사후 = positions 잔량 1 유령 정리 확인.

**신규 결함 2건**:
- **N1 — ✅ cycle235 시정 완료(08-29, 커밋 대기)**. 근본 = handler 가 체결수량을
  `fields[16]`(ODER_QTY 주문수량)으로 오독(주석이 KIS 정본과 반대) — 단일 전량 체결에선
  잠복, 부분/분할에서 positions 과대. 시정 = ①`fields[9]`(CNTG_QTY) 정본 전환 ②엔진
  overrun 클램프(`[fill_qty_overrun]`, 증분 동반 캡 = 손익 정합) + `quantity<=0` drop
  (`[fill_qty_zero]`) ③강제 UPDATE WHERE PENDING+PARTIAL 포괄(N1-b). 적대 검증 확증 4
  전부 시정. 8영역 승인 = handler·order_engine 한정(sha 핀 4가드, 커밋 시 자기소멸).
  **후속 후보(행위 결정 사안)** = 전량 체결 분기의 잔여취소 타이머 해제 + 1차
  update_trade_status 의 PARTIAL 포괄(C235-V2) · `_completed_orders` 일일 리셋 확인(C235-R3).
- **N2 — ✅ cycle236 시정 완료(08-29, 커밋 대기)**. `is_sell_qty_exceeded`(APBK0400 ∧
  "수량"·"초과") + `execute_sell` #1.5 잔고 재대조 4분기(오염=held 보정 자기 치유 /
  잠김=보존+`_selling` 유지 / 실보유0=insufficient / 실패=graceful). insufficient 흡수
  금지가 계약(부분 보유 감시 이탈 차단). 적대 검증 확증 4 전부 시정(C236-F1 held 대조).
  스펙 `_workspace/red/cycle236_sell_qty_exceeded_spec.md`. **잔여 LOW 후속 후보** =
  대출일별 다중 row 잔고 집계(C236-F4) · manual-sell 라우트 분류 미적용(N2-R5, 수동
  매도는 실보유 지정이라 실위험 낮음).

---

## cycle232 · 리스크 통제 3의제 검토 — ✅ 사용자 결정 완료 (2026-08-29, 구현 대기)

터틀 원전 대사 보고서(https://claude.ai/code/artifact/5cd3fe2d-e405-4911-866c-74f03c1bf3a2)의 액션 1·2·3 을
검토(사실 조사 3축 + domain-consult `_workspace/domain_consult/cycle232_risk_control_review.md`) 후 **전부 자문 권고안 채택**.

| 의제 | 결정 | 구현 |
|---|---|---|
| **G3′ 계좌 통합 통제** | **자문 권고 패키지 착수** — ⓪척도 병기(프록시+실효, 관찰 전용) ①SOFT Σ상한 다크런치(관측 4%/차단 6%, 임계 비활성→2주 후 DB 활성, HARD 금지). Σ상한=순간 게이트/드로다운=일 래칫 **이원 설계**(D1). fail-open+LOUD(D2). 1주 폴백 notional 초과는 **관측만** `[oversized_fallback]`(D3). → **cycle242 가 K 축 행위(`max_lot_units`)로 전환, ρ 축 `[oversized_fallback]` 은 관측 병존** — 두 척도는 대체재가 아니다(ρ = 갭·거래정지 명목 / K = 정상 시장 손절 리스크). 드로다운 3층은 **다음 사이클**(입출금 보정 선행) | **✅ cycle233 구현 완료 (2026-08-29) — 커밋 80f164c·배포 완료(08-29, EC2 반영).** 스펙 `_workspace/red/cycle233_account_risk_spec.md` · 적대 검증 21→확증 6 전부 시정(HIGH 2 = 자기 가드 공허, 뮤테이션 실증) · 백엔드 **5,818 PASS** · 8영역+scheduler diff 0(라인 상한 가드로 감시자를 자기 종료 루프로 설계). 활성화 = 2주 관측 후 DB `account_risk_block_pct=6.0` 한 줄. **✅ cycle239 선결(신선도) 시정 (2026-09-02) — 활성화 게이트 충족**: `is_soft_gated()` 가 `_gate_active` 만 돌려줘 감시 루프(5분) 사멸·hang 시 마지막 판정이 **동결**(block 로 얼면 7전략 신규 매수 영구 차단)되던 결함을 **900s(=3×주기) 초과 stale → fail-open(False) + `[account_risk_gate] released reason=stale` WARNING 1회/일**(cap `gate_stale`, peek→로그→mark) 로 닫았다 — 스펙 `_workspace/red/cycle239_gate_freshness_spec.md`. `get_gate_state` 4키(`stale/age_secs/stale_max_secs/effective_gated`, `level` 은 마지막 평가값 보존 = 동결 서명 `level=block ∧ stale ∧ !effective_gated`) + `ensure_watch_loop` done_callback LOUD(`[account_risk_watch_loop_died]` WARNING / `_loop_exit] reason=running_false` INFO 매일 1건). 적대 검증 확증 10(실질 4) 전부 시정(R1 = 기록자 `was_active` 원시값 환원(매 아침 부팅 거짓 stale WARNING + cap 선소비 차단) · `gate_stale` cap 키 독립 F-8c · G-239-7 전 트리 diff 가드 삭제 · 판정 예외 fail-closed 변조 검출 F-5b) · 뮤테이션 23종 21 검출 + escape 2 → 신규 회귀로 봉인 · 3,000틱 fresh 차분 0 · 신규 회귀 36 · 8영역+scheduler diff 0 · `account_risk_watcher.py` 단독. **활성화 잔여 조건(AND)** = 배포 후 2영업일 `reason=stale` 0 ∧ `loop_exit reason=running_false` 매일 1 ∧ 장중 `GET /api/portfolio/risk` `account_gate.age_secs ≤ 600` ∧ cycle233 2주 관측 창(~09-12) 만료 → 사용자 결정으로 DB 한 줄. 활성화 D+1 첫 확인 = `transition=entered` 시 대시보드 `effective_gated=true`(행위-관측 정합) |
| **G2 역지정가** | **보류 + 대체 조치** — 착수 게이트 3(스탑지정가 `ORD_DVSN` 스펙 확정 · 모의/소액 실주문 검증 · T1 자본) AND 충족 전 도입 금지. 근거 = KIS 는 스탑**지정가**만(`CNDT_PRIC` 정본) — 갭 관통 미체결 = Defect 2 재현 + 다일 잔존 주문의 체결통보 오귀속("momentum" INSERT 경로). 지금 할 것 = tick blind 총시간/일 계측 + 부팅 직후 청산 평가 우선순위 확인 + **D6 운영 규약 승격**(보유 포지션 有 시 09:00~15:30 push 금지) | 대체 조치 진행(08-29): **D6 승격 완료**(CLAUDE.md 운영 가이드) · **청산 우선순위 확인 완료** — 청산 평가는 tick 기반(`risk.on_tick` 첫 tick 즉시)이라 매수 스캔(09:30) 비의존 + 보유는 07:59 HIGH 사전구독 = 현행 충족, 실사각은 재구독 지연의 tick blind 자체 → **✅ ① tick blind 계측 완료(cycle234, 08-29)** — `uptime_monitor.py`(60s 하트비트 + `[tick_blind_boot]` + 20:10 `tick_blind` metrics). **G2 대체 조치 3건 전부 종결.** G2 재검토 = `market_blind_secs_total` 주간 분포 실측 후. 재검토 트리거 = `_pending_next_day_clear` 미집행 실측 1회 |
| **G1 risk_pct 0.5→1.0%** | **보류 — T2 재분류.** 해제 게이트(AND) = net≥500만 ∧ kojiro·donchian 각 N≥20 TE>0 ∧ 상관군 캡 활성(`max_open_risk_pct` 4.5→9 동반 — 로드맵 규칙 4). 근거 = 체결 ~70% 1주 폴백 무관 + 효과 비단조(저가주 편향) + kojiro 동시 유닛 4.5→2.25 반토막 | 코드 변경 0 — 문서 등재만 |

**자문의 전제 정정 3**(보고서 반영 완료): ①"1유닛 고정=R15 초과달성" 불성립(1주 폴백이 4유닛 초과 생성)
②리스크 척도 이원(프록시 60,713 vs 정밀 미측정 — 월요일 장중 `GET /api/portfolio/risk` 실측 필요)
③머신 슬립은 로컬 사건(EC2 사각 과대평가 금지).

**cycle239 후속 등재 (신선도 시정 범위 밖, 2026-09-02 — 스펙 §8)** — ~~**A. 평가 타임아웃(우선순위 1)**~~ **→ cycle250 종결(2026-09-05)**: `run_account_risk_watch_once_guarded`(`asyncio.wait_for` 300s, TimeoutError 만 포착 → fail-open+스탬프+`[account_risk_eval_timeout]` 1회/일) 가 루프·부팅 동기 호출 2곳을 대체. 뮤테이션 31/31 KILLED, 회귀 29. D+1(09-07) = 마커 0건이 정상. stale 규칙은 ≤900s 거짓 차단을 허용하는 완화책이지 hang 자체를 못 푼다. 선행 검토 = cancel 시 KIS `_semaphore`·토큰 락·`pg._pool.acquire()` cancel 안전성 · **B. 재스폰 경로**: `ensure_watch_loop` 2번째 호출 지점(`uptime_monitor.heartbeat_loop` idempotent 호출 또는 done_callback 내 일 cap 3) — hang(done()=False)엔 무력, A 선행 · **C. `uptime_monitor` 동형 결함**: 하트비트 루프도 무감시 태스크 — 동일 done_callback 적용 · **D. `scheduler.py:962-985` cycle146 주석 거짓**: `except` 안 `return` 도 `finally` 를 탄다 → 장중 KIS 5xx 1회 = 전면 teardown → run_daily 60s 재부팅(1~5분 tick blind, cycle234 `[tick_blind_boot]` 로 실측 가능). scheduler 소관 별도 결정 · **E. `pg._pool.acquire()` 타임아웃 미지정**(`db/pg.py:128`) — hang 의 공통 뿌리 · ~~**F. 프론트 `PortfolioRiskCard`** `account_gate` 미표시~~ · ~~**G. 20:10 리포트 `account_gate` 병기**~~ **→ cycle251 종결(2026-09-05)**: 카드 배지(차단 중/경고/정상 + STALE N분 전 + KST HH:mm) + 스냅샷 `account_gate`(+`eval_timeouts_today`) 독립 try 부착, `is_soft_gated` 미호출 AST 봉인. 뮤테이션 19/19.

---

## P0-1 · BFB·VCP 가 존재하지 않는 키를 읽어 매수가 구조적으로 불가능하다

### ✅ 시정 현황 (2026-08-25 사이클 227 — Stage 0 구현 완료·미커밋)

- **결정 (사용자, 2026-08-25)**: ① 방향 **A-raw** + 8영역 승인(handler.py·risk.py 한정)
  ② **Stage 0 관측 우선** — 게이트 행위 변경 0, 배관+`would_pass` 로그만 ③ 비중 현행 유지
  (BFB 0.15/VCP 0.10 — 다크런치는 Σ 정규화 위험 이전이라 반대, 자문) ④ P0-2 동반.
- **자문 판정** (`_workspace/domain_consult/bfb_vcp_acml_vol_gate.md`): 방향 B(전일 확정치)
  **폐기** — 전일은 플래그/베이스 수축 구간이라 통과 확률 ~0 = 결함 재생산. **게이트 전환 시
  P1-3 충족 래치 동반 필수** — 래치 없이 A-raw 만 켜면 BFB 통과율 0% 예상(역선택).
- **구현** (명세 `_workspace/red/cycle227_acml_vol_stage0_spec.md`, 검증
  `_workspace/test_report_cycle227.md` **GO**): handler `fields[13]`(ACML_VOL) 파싱 →
  `on_tick(*, acml_vol=-1)` → 신규 leaf `src/engine/tick_volume.py`(KST 날짜 자기 리셋,
  미관측 None — sentinel 0 금지). BFB/VCP 게이트 **직전** 관측 훅
  `[bfb_vol_gate_observe]`/`[vcp_vol_gate_observe]` (cap 1회/(ticker,outcome)/일 +
  `_scan_stats` 3카운터). **기존 게이트 블록 byte 불변**(AST-2 봉인) — 매수는 여전히 차단.
  백엔드 5,617 PASS/실패 0.
- **게이트 전환 판정 기준** (1~2영업일 관측 후): 주 3건↑ would_pass = 전환 진행 /
  **0건 = P1-3 래치 선행 필수** / 일 10건↑ = 스코프 불일치 등 재조사.
- **✅ 관측 결과 (2026-08-26~27 이틀 실측, 2026-08-27 16:00 판정)**:
  배관 정상 — 게이트 평가 5회 전부 실측 acml_vol 관측(no_obs **0**), `observe_failed` 0, ERROR 0(cycle227 기인분).
  **would_pass = 0/5** ⇒ 판정 기준상 **P1-3 충족 래치 선행 확정**(자문 예측 그대로 — A-raw 단독은 역선택).
  정량 근거 = 관측치/임계 비율: 280360 8%(09:08) · 257720 19%(09:19) · 161890 25%(09:26) ·
  001450 40%(10:00) · **357780 70%(12:25)** — 시각이 늦을수록 임계에 접근 = 래치(완주 후 재평가 유지) 도입 시
  통과 발생이 정량적으로 예고된다. 컨텍스트 = 8/26 돌파 1차 감지 247 vs retention 완주 4(진동이 완주를 깎음 — P1-3 동일 뿌리).
  VCP 는 후보 0(final_prepared=0)이라 관측 0 — 자문 예측 범위("몇 주 무체결 가능"), 관측 계획은 BFB 중심 유지.
  Stage 0 불변식 확인 = BFB·VCP 8/26 이후 체결 **0건**(게이트 byte 불변 정상 작동).
- **전환 사이클 의무**: 은폐 테스트 3파일 손주입 → tick_volume 주입 의미 전환(주석 마커
  11곳) + AST-2 pin 의미 전환 + 8영역 sha 핀 4항목 자기소멸 확인 + 비중/디리스크 재확인.
- 인지된 노이즈원(자문 §B): H0UNCNT0 통합 누적(NXT 프리 포함) vs 일봉 J(KRX 단독) 스코프
  불일치 + 다중 레코드 프레임 첫-레코드 과소 계상 — 정합화는 행위 변경이라 별도 사이클.

### 사실 (직접 재확인 완료)

```python
# src/engine/strategies/bull_flag_breakout.py:846-850
info_price    = ticker_prices.get(ticker, {})
acml_vol      = int(info_price.get("acml_vol", 0) or 0)              # ← 항상 0
vol_threshold = int(info["flag_avg_volume"] * breakout_volume_mult)  # ← 항상 ≥ 1
if acml_vol < vol_threshold:
    return Signal.NONE                                                # ← 무조건 실행
```

`src/engine/strategies/vcp_breakout.py:955-961` 동형.

- `scanner.ticker_prices` 에 값을 넣는 **유일한 대입부**는 `src/engine/risk.py:397` 이고
  **4키만** 쓴다 — `current_price` / `open_price` / `change_rate` / `prdy_ctrt`.
- **`acml_vol` 을 `ticker_prices` 에 쓰는 코드가 전체 소스에 없다.**
  WS 핸들러(`src/realtime/handler.py`)도 체결 payload 의 누적거래량 필드를 파싱하지 않는다.
- `prepare()` 가 `flag_avg_volume > 0` 을 강제하므로 임계는 항상 1 이상
  (2026-08-25 실측 48건 = 12,775 ~ 3,628,183).
- 라이브 API 응답 키 출현: `acml_vol` **0회** vs `current_price` **115회**.

⇒ `0 < threshold` 가 **항상 참** ⇒ `check_buy_signal` 이 **구조적으로 `Signal.BUY` 를 반환할 수 없다.**

### 실측 증거

- 7전략 중 이 키를 읽는 **두 전략만 정확히 전 기간 체결 0건** (BFB 0 / VCP 0, 나머지 31~203).
- 2026-08-25 BFB: 후보 **48건** 준비, retention **21회 이상 완주**, 매수 신호 **0**.
  완주 경로(`:829` pop)가 무로그라 그동안 보이지 않았다.
- `CLAUDE.md` 의 기존 귀인 **"BFB·VCP 체결 0 = 진입 조건 미통과 탓"은 반증됐다.**
  조건은 오늘 하루만 21회 이상 충족됐다.

### ⚠️ 왜 지금까지 안 잡혔나

**회귀 테스트가 결함을 은폐하고 있다.** 아래 테스트들이 `ticker_prices` 에 `acml_vol` 을
**손으로 주입**해서, 테스트는 통과하는데 프로덕션은 절대 매수하지 못한다.

- `tests/unit/engine/strategies/test_bull_flag_breakout.py` (:118-124, :147-150, :196-197, :209-210)
- `tests/unit/engine/strategies/test_bull_flag_breakout_retention.py` (:59-60, :82-83, :109-110)
- `tests/unit/engine/strategies/test_vcp_breakout.py` (:145, :167, :215, :228)

**시정 시 테스트도 반드시 함께 고친다.** 그러지 않으면 시정이 검증되지 않는다.

### 시정 방향 (택1 또는 병행)

**A. 실시간 누적거래량을 흘린다**
핸들러가 체결 payload 의 누적거래량을 파싱해 `on_tick` **키워드 인자**로 전달
(사이클 222-a 의 `day_high` 가 정확히 같은 패턴 — 그 선례를 따르라).

> ⚠️ **`ticker_prices` 에 주입 금지.** `donchian_swing.py` 가 같은 dict 에서 고가 키를 읽고 있어
> (`daily_high = max(stck_hgpr, high_price, current_price, open_price)`),
> 키가 채워지면 `ext_pct` 과열 가드가 켜져 **donchian 매수 행위가 바뀐다.**
> `risk.py` 의 관련 주석과 AST 가드가 이미 이 커플링을 경고하고 있다.

**B. 컷을 전일 확정치 기준으로 재정의**
`stock_master.raw.acml_vol` / `stock_master_daily` 기준. 장중 누적 vs 일평균 비교는
09:05 시점엔 구조적으로 불리하다(하루가 시작도 안 했는데 일평균과 비교).

### 🚨 배포 전 반드시 결정할 것

**이걸 고치면 두 전략(비중 합 25%)이 갑자기 매수를 시작한다.**
실체결 표본이 **전 기간 0건**이라 검증된 적이 없는 전략이 한 번에 열린다.

- 한 번에 열 것인가, **다크런치(비중 극소)로 관찰부터** 할 것인가?
- ⚠️ 비중을 **0 으로 내리지 말 것** — `registry.enabled()` 이탈로 손절 평가가 정지한다
  (`enabled` 축 독트린, 아래 참조).
- 체결 확보 전까지 **진입 임계 재튜닝 금지** — 표본 해상도가 파괴된다.

---

## P0-2 · stale universe 가드가 후보 40%를 당일 영구 축출한다

### ✅ 시정 현황 (2026-08-25 사이클 227 — 구현 완료·미커밋)

안전조건 소스를 진짜 당일 누적으로 교체: ① tick 관측(`tick_volume`) 우선 ② 부재 시
`inquire_acml_vol`(FHKST01010100, 화이트리스트 기존재 — FHKST01010300 응답엔 `acml_vol`
부재 확인) REST 폴백 ③ 둘 다 부재 → **제외 보류**. `[universe_excluded]` 에
`acml_vol=… vol_source=tick|rest` 병기. 임계 10,000·보유/익일청산 절대 보호 불변.
**✅ D+1·D+2 실측 확증 (2026-08-27)**: 축출 **85건(8/25) → 1건(8/26) → 0건(8/27)**.
8/26 유일 1건(004800)은 `vol_source=tick acml_vol=3,442` = 진짜 저유동 — 가드가 설계
의도("거래가 실제로 빈약한 종목만 축출")대로 복원됐다. BFB 후보 구독 상실 축도 소멸
= would_pass 관측이 "게이트 탈락" 단일 축으로 해석 가능해졌다.

### 사실

- 2026-08-25 BFB 후보 48 중 **20건(41.7%) 미구독**.
- 원인은 슬롯 부족이 **아니다**(아래 반증 참조). `_universe_excluded_today` 축출이다.
- `[universe_excluded]` 로그 46건 중 이 20건 전부 매칭 (`reason=stale_6plus_low_volume`, ~10:01,
  `today_volume` 254~6,197).
- 필터링 지점 = `src/engine/scheduler.py:1740-1745`
  (`if excluded: tickers = [t for t in tickers if t not in excluded]`).
- **BFB·VCP 는 `_SWING_POLL_STRATEGIES` 비멤버**라 REST 폴 보강이 없다
  (`scheduler.py:144` = `("donchian_swing", "kojiro")`).
  ⇒ **미구독 = 매수 평가 완전 상실**(donchian/kojiro 는 60초 REST 폴이 받쳐준다).

### 근본 결함

가드의 "거래량 빈약" **안전조건이 실질 무력화**돼 있다.
`today_volume` 이 최근 ~30 체결의 합이라 임계 `UNIVERSE_LOW_VOLUME_THRESHOLD=10_000` 을
사실상 항상 충족한다 ⇒ 가드가 **"스테일 6회 → 무조건 축출"** 로 퇴화했다.

### 시정 방향

안전조건을 **진짜 당일 누적거래량**으로 교체(`stock_master.raw.acml_vol` 또는 `FHKST01010100`).
대량 동시 축출 버스트는 배관 장애 신호로 보고 별도 판단.

---

## P1 · 관측을 가리거나 자원을 낭비함

### P1-3 · BFB retention 진동 — 로그의 42% 점유

- 2026-08-25 2시간 로그 1,753행 중 **738행**이 한 종목(`001450`)의 왕복.
  `BFB 돌파 1차 감지` 374 / `BFB 돌파 후퇴` 364.
- **오늘 실제로 진단을 방해했다** — 로그 상위를 전부 덮었다.
- 원인 셋:
  1. retention 이 **연속 유지** 요구 — 대기 중 한 틱만 `flag_high` 미만이면 즉시 취소
     (`bull_flag_breakout.py:818-822`). 돌파선이 전일종가 근처면 노이즈만으로 무한 재시작
     (001450: `flag_high` 50,800 vs `prev_close` 50,600 = +0.40%).
  2. **완주 후 재무장 불가** — `:829` pop 직후 `_prev_price ≥ flag_high` 라
     `:832` edge-crossing(`prev < flag_high <= current`)이 재성립하지 않는다.
     가격이 돌파선 아래로 내려갔다 와야만 재평가된다.
  3. `_prev_price` 가 `_reset_daily_state`(`:1094-1100`)에서 **청소되지 않아** 일 경계를 넘어 잔존.
- 시정: 완주 후 거래량 탈락 시 `first_seen` 을 pop 하지 말고 **충족 래치**로 유지 +
  `_prev_price` 일일 청소 + 히스테리시스 밴드 검토.

### P1-4 · `silent_inactive` 오판 — 하루 16~24 접속키 낭비 (08-31 포렌식 확정 결함 ⓐ, MEDIUM) — ✅ cycle241 종결 (2026-09-02, 커밋 대기)

> 시정 = `detect_silent_inactive_sessions` **세션 상대 판정**(L1) — 판정 가능 세션(`subscribed >= 5`)이
> **2개 이상이고 그 전부**가 `fresh_ratio < 0.2` 이면 '세션 N개 동시 고장'이 아니라 **시장 침묵**으로 보고
> 그 사이클을 기각 + 판정 가능 전 라벨 `first_seen` pop(누적 후 필터 금지 — 시장 재개 순간 지각 세션이
> 즉발한다). 다른 세션이 하나라도 fresh 면 현행대로 발화(진짜 단독 결함 보존), 판정 가능 세션 < 2 면
> 현행 byte 동일(fail-open) = **결과 집합 ⊆ 현행**. 시간창 리터럴·`session` import·`tradable_boards`
> 미사용(AST G-241-5). `src/engine/stale_session_recovery.py` 단독(+196/-9, 251→438L), 8영역·
> scheduler.py(3,999L)·facade·diagnostics·watcher_core diff 0. 스펙 = `_workspace/red/cycle241_silent_inactive_relative_spec.md`.

- **실측(EC2 read-only, 30일)**: `[silent_inactive_force_reconnect]` **522건 중 491건(94.1%)이 그 시점 세션 풀
  전원 동시 발화**(버스트 크기가 풀 증설 5→7→8 과 일치, 09-01/09-02 는 8행 **동일 timestamp** = 단일 K 이터레이션).
  슬롯 = 장전 동시호가 27.2% / 장후 동시호가 27.2% / 15:30~16:00 22.4% / 16:00~18:00 10.9% / 18:00~ 12.3% —
  **09:00~15:20 정규장 0건**. 일별 = 08-31 **88건**(장애일, cap-skip 632) · 09-01 **24건** · 09-02 8건+.
  재연결의 회복 가치 **0** — 09-01 15:36:35 재연결 → 15:38:46 8세션 여전히 fresh=0 → **15:40:51 8세션 동시 회복**
  = `_BOARD_SCHEDULE` POST_NXT 진입(시장 재개가 원인); 08-31 은 16:02 WS 닫힘 뒤 20:08 까지 재등록 실패 지속,
  익일 07:5x 부팅으로만 회복. 09-02 접속키 발급 53건 중 **27건(50.9%)** 이 silent_inactive 발.
- **원인**: 세션마다 **독립** 판정(`fresh_ratio < 0.2 ∧ subscribed ≥ 5 ∧ 5분`), 세션 간 비교·시장 상태 참조 0 —
  "8세션이 같은 초에 전부 침묵"을 "8개 동시 고장"과 구분할 방법이 코드에 없었다. 재연결마다 접속키 발급 1
  (`token.py:183` 무캐시, `websocket.py:213` 재연결 루프 첫 줄) + 세션 전 구독 재SEND + 60초 F1 재검증, 발화
  시각이 08:57(개장 3분 전)·15:39(NXT 애프터 1분 전)라 보유 종목 시세 공백 동반. 형제 `check_and_resubscribe_stale`
  은 같은 K 루프에서 `is_call_auction_now` 를 보는데 이 함수만 안 봤다 — 그러나 시각 게이트는 **이식하지 않는다**(아래 ⑤).
- **착수 전제 정정 3(3렌즈 실측, 결론 불변)**: ① "동시호가 게이트 이식만으론 4% 해결" → 실측 **54.4%**(284/522).
  그래도 L1 이 필요한 이유 = 잔여 중 15:30~16:00 D 슬롯(117건 22.4%)은 `boards_at` MAIN 갭 마진·`is_call_auction_now`
  창 상한 15:35 어느 쪽도 못 닫고 15:40:33 정각 8세션 동시 회복이 구조적 무틱임을 증명 — **세션 비교만이 닫는다**
  ("400/416 장 마감 후"는 `[silent_inactive_recovery_cap]` 406·632건이 섞인 표본) ② D+1 기대 "24 → 0~수건" →
  **0~3건/일** — main 단독 침묵(sub=8 분해능 × 야간 무거래 우선주)은 타 7세션이 fresh 라 상대 판정을 **통과해 계속
  발화**한다(설계상 옳음, 후속 A) ③ skip 마커는 발화 시각이 아니라 **에피소드 진입 시각** — `entered` ≈08:51~53 ·
  ≈15:21~23(전원 침묵 성립 + `STALE_FRESHNESS_SECS=60`), `exited` ≈09:00~02 · ≈15:40~42. 종전 15:27/15:39 두 발화는
  `force_reconnect_session` 의 pop 이 5분 카운트를 다시 돌린 **인공 분할**이라 L1 아래선 한 에피소드로 병합.
- **설계 결정 8(사용자 위임 — team-leader 권장안, 스펙 §0)**: ① 게이트 위치 = first_seen 누적 **앞**(2-pass, pass 2 는
  사이클 24/29-R2 식 byte 동일; 반환 직전 필터는 재개 순간 즉발) ② 기각 = 판정 가능 전 라벨 pop + `[]`(hold 금지 — F-7 봉인)
  ③ `eligible < 2` 현행 byte 동일(단일 세션 픽스처 15 케이스 무수정 통과) ④ 08-31 형 전 세션 실두절 에스케이프 해치
  **불채택**(회복 가치 0·표본 0, 가시성은 `[tick_coverage] ratio=0.0%` + `persisting` WARNING — 후속 E 트리거만)
  ⑤ 시장 상태 신호(`is_call_auction_now`·`boards_at`·`last_nxt_mkop_code`) 게이트 미사용(운영 8세션에서 L1 단독이 3슬롯
  전부 덮어 시각 게이트는 무효 코드 + Q1 import 표면 불증가) ⑥ 관측 상태 = `_MW_EPISODE` 모듈 전역 날짜 키 자기 리셋
  (StaleTrackerState 7필드 정확 일치 가드 2벌·scheduler 3,999L 이라 유일 위치) ⑦ '본체 동일' **기계 가드 없음** 실측 —
  산문 4곳 + `src/engine/CLAUDE.md` 재스코프 ⑧ 정본 문서 문안. domain-consult 불요(WebSocket 배관, 진입·청산 0).
- **관측**: `[silent_inactive_market_wide_skip] transition=entered|persisting|exited` — entered(INFO 에피소드 1회,
  `sessions= eligible= silent=n/n connected= reset= reconnects=`) · persisting(WARNING ≥1800s 지속 후 1800s 마다,
  정상 최장 15:20→15:40 1,200s × 1.5) · exited(INFO `elapsed_secs= cycles=`). peek→로그→mark, 실패 흔적
  `[silent_inactive_market_wide_skip_failed]` 1회/일, `write_log` 0. 08-31 형 4시간 두절 = entered 1 + persisting ≤8 + exited 1.
  ⚠️ `connected=` 는 "`_ws` 객체 보유"(재연결 대기 stale 포함)이고 `reconnects=` 는 "핸드셰이크 재시도 인덱스 합"
  (`force_reconnect_session` 강제 close 는 `MIN_STABLE_SECONDS=5` 리셋으로 **미반영**) — 둘 다 소켓 생존 확증이 아니다.
  소켓 생존은 `[ws_heartbeat]`(세션별 PINGPONG) + `transition=persisting` 지속 시간으로 읽는다(라운드 2 정정).
- **적대 검증**: 라운드 1 확증 8 → 시정 5(AST 헬퍼 `_resolve` 의 `assign_map.get(name, ())` tuple 기본값 `TypeError`
  = **Red 가드 자기 결함**, 중복 리포트 4건 · `connected=` 오독 위험 · escape M06a/M06b 예외 전파 계약 봉인
  (`test_f241_18*`) · escape M19 기각 pop 범위 봉인(`test_f241_19`)) + 처분 3(§10.2 — "main 구조적 침묵 + 7보조 실제
  동시 결함" 교차 변형은 ④/후속 A 의 승인된 결정이라 코드 변경 0). **라운드 2** = 라운드 1 이 도입한 `reconnects=` 의
  "재연결 폭풍 검출" 주장이 `websocket.py` 실제 카운팅과 **반대**임을 확증(`_receive_loop` 가 `ConnectionClosed` 를
  삼켜 정상 반환, `+= 1` 은 핸드셰이크 except 분기뿐) → docstring 3곳 반전 + F-13b 목적 재정의(코드 행위 0).
  뮤테이션 **26종 중 23 KILLED**, escape 3 은 전부 커버리지 공백(현행 구현 정확) → 회귀 5 로 봉인. 차분 실증
  **2,500 조합** — '전원 침묵(eligible≥2 ∧ silent==eligible)' 1,000 조합에서만 설계대로 차이(`[]` + 현재 세션 라벨 pop),
  나머지 1,500(진부분집합 1,000 + eligible<2 500)은 result·first_seen 상태·`ticker_last_tick.get` 호출 수까지 HEAD 동일,
  결과 집합 ⊆ 현행 위반 0. 표적 218 PASS + 2 xfail(신규 39 = 행위 25 + AST 14).
- **D+1 판독 채널**(⚠️ **의미 반전** — `force_reconnect` **감소가 정상**, skip 마커는 신규, 배포 전후 같은 grep 합산 금지):
  | 채널 | 정상 서명 | 이상 서명 |
  |---|---|---|
  | `[silent_inactive_force_reconnect]` | **0~3건/일**, 전부 16:00 이후 `label=main`(단독 침묵) | 같은 초 8행 버스트 = 시정 미작동 / 09:00~15:20 발화 = 신규(종전 0) → 즉시 조사 |
  | `[silent_inactive_market_wide_skip] transition=entered` | **2~3행/일** ≈08:51~53 · ≈15:21~23 · 간헐 ≈07:59, `sessions=8 eligible=8 silent=8/8` | 정규장에 찍힘 = 전 세션 침묵 사고 → `[tick_coverage]`·`[ws_heartbeat]` 교차 |
  | `… transition=exited` | entered 와 1:1, `elapsed_secs` ≈180~600(아침) · ≈1,000~1,300(15:2x→15:40) · ≤120(07:59) | ≫1,300 = 시장 재개 후에도 침묵 = 두절 |
  | `… transition=persisting`(WARNING) | **0행**(수능일 등 개장 지연일 1~2행 예외) | ≥1 = 30분 이상 전 세션 침묵(08-31 형) → `[tick_coverage] ratio=0.0%`·`[ws_heartbeat]` 교차, 필요 시 `POST /api/trading/restart` |
  | `[silent_inactive_market_wide_skip_failed]` | 0 | ≥1 = 관측기 자기 실패(행위는 수행됨) — 로거/서식 조사 |
  | 접속키 발급(EC2 `접속키 발급 완료`) | 일 53 → **≈26~29**(부팅 8 + 보드 전환 8 + 정기 16:02 8 + 개별 1~5) | 감소 없음 = 발화 잔존 |
  | `[stale_watcher_detail]` 15:40:3x | 8세션 동시 fresh 회복 서명 **불변**(15:36 재연결이 사라져도 회복 시각 동일 = ④ 근거 재확인) | 회복 지연 = 재연결이 기여했었다는 반증 → ④ 재검토 |
  | 보유 종목 시세 | 08:57·15:39 재연결 직후 HIGH `stale` 스파이크 소멸 | 보유 종목 stale 증가 = HIGH 경로 훼손 → **즉시 롤백** |
- **후속(이번 사이클 밖)**: A main 단독 잔여 위양성(sub=8 분해능 × 야간 무거래 우선주 000815·003490·285130 — 후보
  `SILENT_INACTIVE_MIN_SUBSCRIBED` 상향 또는 절대 fresh 하한, **domain-consult 대상**; §10.2 #5 교차 변형도 이 축)
  · B 단일 세션 풀(VTS/개발) 2차 게이트 `is_call_auction_now`(54.4%, 운영 무효) · C `unknown` 라벨 충돌
  (`websocket_pool.py:538-540` realtime 8영역, 운영 8라벨 전부 DB 라벨이라 미발현) · D 접속키 캐시(`token.py:183`
  auth 8영역 — 수요 절반 감소로 우선순위 하락) · E 장중 전 세션 침묵 에스케이프 해치(재검토 트리거 = `entered` 09:00~15:20
  + `exited elapsed ≥ 600` 실측, 현재 표본 0) · F `_MARKET_WIDE_PERSIST_WARN_SECS` 수능일·조기 마감일 실측 후 재조정
  · G 형제 `[stale_skip_call_auction]` 유지(관측 축 상이) · H `reconnects=` 필드 존폐 — team-leader 결정 **유지**
  (값은 "connect-phase backoff 인덱스 합" 보조 진단, 폐기는 다음 이 파일 접촉 사이클에 F-13b 회귀 동반).
- ℹ️ **2026-08-25 KIS 메일 폭주의 원인은 이것이 아니다** — 같은 KIS 계정에 묶인 **다른 계좌 앱키의 외부 배치**였음이
  사용자 확인으로 판명. 이 시스템의 12시간 인증 호출은 토큰 7 + 접속키 17 = **24건**뿐(DB·컨테이너 로그 일치).

### P1-5 · VB 15:30 종가 매수 발사 + APBK3013 [단일가매매] 미분류 — ✅ cycle229 종결 (2026-08-28)

> 시정 = VB·momentum 매수 컷 **15:20**(`BUY_CUTOFF_KST` 모듈 상수·KST 명시·check_buy_signal
> 최상단·상태 무갱신, `[vb_buy_cutoff]`/`[momentum_buy_cutoff]` 1회/일) + `[단일가매매]`
> 변형 `is_market_order_disallowed` 편입(주 실익 = 매도 무기록 포기 경로 → step_down
> 지정가 폴백+TTL). 부수 = 무-freeze 레거시 테스트 6곳 장중 KST 동결(벽시계 독립 확보).
> D+1(월) 확인: `[callback_exception]` 15:30 대 0건(의미 반전 — 있음→없음이 정상) +
> `[selling_reconcile]` 빈도(지정가 매도 미체결 잔존 감시). 상세 자문 = 아래 정정 블록.

- **실측**: 8/20 ×2 · 8/21 ×1 · 8/25 ×4 · 8/27 ×2 — 전부 **15:30:0x~2x**. 체인 =
  VB 매수 신호(예: 8/27 15:30:20 에코프로 086520 "현재가 92,000 ≥ 목표가 90,050") →
  시장가 SOR 1주 매수 → APBK3013 `[단일가매매] 지정가 주문(신규/정정/취소) 및 최유리/최우선
  취소 주문만 가능합니다` → **이 msg1 변형이 `is_market_order_disallowed` 키워드 미매칭**
  (기존 키워드 "지정가 및 최유리"가 중간 "(신규/정정/취소)" 삽입으로 substring 미성립) →
  KisApiError 가 `on_tick` 밖으로 전파 → `[callback_exception]` → **WS 재연결**(G-REJECT-1
  설계상 의도된 전파이나, 15:30 마다 1~4회 재연결 churn + 그 순간 보유 종목 시세 감시 공백).
- **⚠️ cycle227 무관 확증** — 8/20 부터 존재(8/25 발생분은 cycle227 배포 19:30 *이전* 15:30).
  8/26 15:40 `[애프터마켓]` 변형은 기존 키워드에 매칭돼 정상 폴백(무예외) — 변형별 갈림 실증.
- **🚨 단순 키워드 추가 금지 — 시간 가드 선행** (자문 `cycle229_vb_1530_single_price.md`,
  2026-08-28 **전제 정정 포함**): ~~"15:20~15:29 연속매매에서 우연히 K-돌파가 없었다"~~ 는
  **반증** — 그 구간은 KRX **장후 동시호가(종가 단일가)** 다(`session.py::is_call_auction_now`
  사이클 162/182 가 이미 그렇게 판정, 6/17 15:21:48 `fresh=0/10` 실측 = 평가할 틱 자체가
  구조적으로 희박). 15:30:0x~2x 에 몰린 9건은 **랜덤엔드 체결로 확정 종가 1틱이 흐르며
  15:19 마지막 연속체결가 대비 점프 → edge-crossing** 생성이 원인. ⚠️ 종가 단일가는
  **시장가 호가를 접수**한다(15:20 강제청산 시장가 매도가 작동 중인 것이 방증) — 15:2x
  VB 매수는 "거부되는" 게 아니라 **종가로 체결돼 오버나잇**된다(우연한 안전판 없음).
  시정 = (a) VB·momentum 매수 컷 **15:20**(명시 시각 모듈 상수·KST — 보드 결합 금지,
  momentum 종가 확정 틱 +29% 는 "상한가 잠금 실패 마감" 표본이라 원 가설의 반대) +
  (b) `[단일가매매]` 변형 `is_market_order_disallowed` 편입(정당화 축은 **매도** —
  미분류 매도 거부는 3회 재시도 후 무기록 포기(`order_engine:815~828`)라 랜덤엔드 창
  청산 실패가 기록조차 안 됨. 낮은 매도 지정가는 단일가 세션 유효 주문 = 폴백이 정확한
  처방. 잔여 매수 경로는 LTV 야간 다운그레이드→시간외단일가뿐). 8영역 무접촉 달성 가능.
- 부수 미규명 1건: 8/24 09:46:49 `[callback_exception] ticker=377300` — 15:30 패턴과 다른
  시각. 별도 규명 필요(단발).

### P1-7 · 5분 우선 재구독 핑퐁 (08-31 포렌식 확정 결함 ⓑ, MEDIUM) — ✅ cycle240 종결 (2026-09-02, 커밋 대기)

> 시정 = `resubscribe_stale_priority`(`_scan_loop` 5분, cap=10)의 **LOW 후보만** desired 집합
> (breakout `_collect_breakout_tickers()` ∪ momentum `scanner._last_scan_result`)과 교집합.
> HIGH(보유 ∪ 익일청산)는 `low_targets` 에 애초에 없어 필터 경로를 지나지 않는다(구조적 면제)
> + HIGH 수집 예외 시 게이트 off(이중). 활성 게이트 = breakout 비어있지 않음 ∧ HIGH 수집 무예외
> — off 면 **현행 byte 동일(fail-open)**. `src/engine/stale_watcher_core.py` 단독(+61/-4),
> 8영역·scheduler.py(3,999L)·facade diff 0. 스펙 = `_workspace/red/cycle240_resubscribe_desired_filter_spec.md`.

- **실측(EC2 read-only, UTC 저장 +9h)**: 09-02 09:40 `[stale_priority_resubscribe]` 9종목 →
  09:45 `[scan_loop_delta] unsubscribed=` **동일 9** → 10:00 RESUB → 10:05 DELTA … 1:1 무한 페어링.
  `034020` 은 09:00:29 매도 후 **19:59 까지 35회** 재구독. 종목언급/행수 = 09-01 **993/115**,
  09-02 **843/108**. `[scan_loop_delta]` 09-02 **222행**. `cap_exceeded` 0건(HIGH 가 cap 을 넘은 적 없음).
- **원인**: stale 후보 소스가 `scanner.ticker_last_tick.items()` **전수**(`stale_watcher_core.py:449`)
  — 그 dict 는 per-ticker pop/del 이 src 전체 0건, 유일 정리 = 20:10 정산 `_reset_daily_state` 의
  `clear()`. 09:00 에 한 번 tick 받은 종목은 매도·후보 이탈 후에도 20:10 까지 stale 자격 유지.
  형제 `check_and_resubscribe_stale`(120s)은 소스가 `get_subscribed_tickers()`(구독 집합 한정)라
  같은 결함 없음 = **비대칭이 뿌리**. cycle216 LOW throttle 180s < 300s 주기라 구조적으로 못 막고,
  universe 가드 평가 대상이 `new_set` 한정이라 되살아난 종목엔 자동 수렴 경로 0.
  LOW 라 메인 41 하드리밋은 안 깨지지만 구독 슬롯·KIS SEND 낭비 + 로그 오염 +
  `_stale_last_resubscribe_at`(throttle/force_retry 타임스탬프) 오염.
- **설계 결정(사용자 위임 — team-leader 권장안)**: ① desired = `new_set ∪ NDC` 동치 정의(같은
  try 블록·같은 이터레이션 — 필터가 `_scan_loop` 자신이 구독하려는 종목을 자를 수 없다) ②
  `kis_ws_pool.get_subscribed_tickers()` 는 desired **부적격**(cycle215/217 "미구독 split-brain
  종목 재구독" 계약 무력화 — F-12 실증) ③ 스윙 후보 **제외**(넣는 순간 대표 피해자 매도 완료
  donchian/kojiro 가 desired 로 부활) ④ momentum 은 **가산 전용·게이트 불참**(모듈 전역 잔여값이
  기존 LOW 회귀 23파일을 순서 의존으로 깨는 방향 = 덜 허용적, 활성 판정은 scheduler 소유 소스에만)
  ⑤ `ticker_last_tick` 잔존은 이번 무접촉(소비처 8곳, pop 자연 위치 = `order_engine` 8영역 → 후속 A)
  ⑥ 순서 = 분리 → **필터** → cycle216 A(동시호가) → B(throttle) → cap(유령이 cap 10 을 소비 못 함).
- **관측**: `[stale_priority_resubscribe] count=%d tickers=%s desired_low=%d filtered_not_desired=%d
  filtered_sample=%s`(기존 INFO 1행 확장, `count=` 첫 필드 byte 보존, sample ≤10, 신규 마커 0·cap 0
  — 행 빈도 5분 1행 불변). `filtered_not_desired` 는 하루 누적 유령 수(30~80 이 **정상**).
- **부수 시정**: cycle222a `test_a11b_stale_watcher_core_untouched`(bare `git diff HEAD` **영구 동결**
  — 사이클 한정 스코프 가드가 수명을 넘겨 stale watcher 의 모든 후속 시정을 무조건 RED)를 내용 검사
  `test_a11b_stale_watcher_core_no_anchor_coupling`(앵커 토큰 `day_high`/`stck_hgpr`/`high_price` 0)로
  재스코프 + cycle222a3 `_GIT_HELPER_FILES` 목록 동기(`_git` 헬퍼 삭제 반영).
- **적대 검증**: 3렌즈 발견 5 → 실질 1 = F-8 **테스트 픽스처 결함**(`_capture_scheduler_warnings()`
  가 `src.engine.scheduler` 로거 레벨을 WARNING 으로 올려 caplog INFO 를 삼킴 → `IndexError`;
  **구현은 무결함** — 캡처된 `low=1` 이 이미 필터 통과분으로 정확) → caplog 단일 캡처로 교체(src 변경 0).
  뮤테이션 **21종 중 20 KILLED / 1 ESCAPED**(m5a — `resubscribed.append`/`_stale_last_resubscribe_at`
  가 `subscribe` 성공 **전** 스탬프: cycle240 diff **밖** 사이클 28/216 기존 루프 = 기존 커버리지 공백,
  후속 H). 차분 실증 **2,300 조합 0 불일치**(A 게이트 off·desired ⊇ LOW 1,000 조합 HEAD byte 동일 /
  B 무작위 1,000 조합 차이는 desired 밖 종목뿐·HIGH 탈락 0 / C 게이트 off 300 조합 HEAD 동일).
- **D+1 판독 채널**(⚠️ **의미 반전** — `count` **감소가 정상**, 배포 전후 같은 grep 합산 금지):
  | 채널 | 정상 서명 | 이상 서명 |
  |---|---|---|
  | `[stale_priority_resubscribe]` | 장중 `desired_low>0` · `filtered_not_desired≥1` 대부분 사이클 · 종목언급 09-01 993 → **<50/일**, 대부분 `count=0` | 장중 `desired_low=0` 지속 = 게이트 off(4 돌파 전략 후보 0 또는 registry 이상) / `count` 종전 수준 = 필터 미작동 |
  | `[scan_loop_delta] unsubscribed=` | 매도·후보 이탈 시점에만(09-02 222행 → 수십 행), 직전 RESUB 와 1:1 페어링 **0** | 페어링 재출현 = desired 소스 누락(어떤 전략 후보가 desired 밖) |
  | 페어링 SQL | RESUB tickers ∩ 5분 뒤 DELTA tickers = ∅ | ≠ ∅ → 해당 종목 소속(전략·상태) 추적 |
  | `[stale_watcher_detail]` | `stale=`/`r=` 감소(유령의 5분 점유 소멸) | 불변 = 120s 형제 경로 독립 결함(후속 F) |
  | `[stale_priority_resubscribe_cap_exceeded]` | 0 유지 | ≥1 = HIGH>10(필터 무관, 보유 급증) |
  | HIGH 회귀 | `/api/realtime/subscriptions` 보유 종목 fresh 비율 불변 · 매도 후 `[unsubscribe]` 정상 | 보유 종목 stale 증가 = HIGH 경로 훼손 → **즉시 롤백** |
- **후속(이번 사이클 밖)**: A `ticker_last_tick` 매도 시 pop(`order_engine._unsubscribe_if_no_other_strategy`
  8영역 승인 + 소비처 8곳 영향 평가, 이번 시정으로 무해화 = P3) · B `_scan_loop` `new_set` 에 NDC 부재
  (`scheduler.py:2457`, 부팅 복구 창 delta 해제 잠재 — 순증 0 편집 필요) · C 사이클 한정 bare `git diff`
  영구 동결 가드 수명 감사(`test_cycle223f:236`·`test_cycle223:325` 잔존 → sha 핀 자기소멸 또는 내용 검사)
  · D `[scan_loop_delta]` `reason` 축 · E universe 가드 평가 대상 `new_set` 한정(관측) · F K watcher(120s)
  subscribed∖desired 재등록(≤5분 창, `[stale_watcher_detail]` 불변 시 카드) · G `scanner._last_scan_result`
  공개 접근자(8영역) · **H** m5a 순서 보정(`resubscribed.append`/타임스탬프를 `subscribe` 성공 이후로 —
  다음 `stale_watcher_core` 접촉 사이클, tester 사본 테스트 `test_cycle240_tester_m5a_stamp_after_success.py`
  실트리 미추가).

---

## P2 · 정확성 · 잠재 위험

### P2-5 · kojiro `_held_stage3` stale True — ✅ cycle231 종결 (2026-08-29)

> 시정 = 플래그를 `(판정 수행일, bool)` 로 전환, 소비처는 **오늘 판정만** 인정(stale True
> 억제 + `[kojiro_stage3_stale_skip]` age 1=INFO/≥2=WARNING, cap 1회/ticker/일).
> `:649` fail-open 계약을 prepare·소비 축까지 통일한 것 — §1·§2·§4 가 방어. 자문 정정 2 =
> cycle225 게이트는 donchian 것(kojiro recompute 는 전수 순회, 실스테일 경로 = 07:59/16:20
> 재-prepare) + ATR 밴드 **상한** 이탈(급등 종목)이 마킹을 못 받는 경로. 부수 방어 =
> `:685` buy_date 비교 try 밖(cycle226 L-2 동형, 잠복) isinstance 가드. Red 가 추가 실증한
> 현행 결함 = 소비처가 비어 있지 않은 튜플을 전부 참으로 읽음(`(오늘, False)` 도 발화).
> 자문 한계 명시 = 다수 케이스에서 하루 늦은 청산 실비용(kojiro 저승률·고RR 라 유리한
> 교환 — **고승률·저RR 전략에 복사 금지**) + `[kojiro_stage3_exit]` 표본 ~20건 시 §3
> 존재 가치 재검정. 자문 = `cycle231_kojiro_stage3_stale.md`.

`prepare()` 경로는 실패 시 `False` 를 **쓰지 않는다**. ATR 밴드 이탈·스테이지 판별 불가로
중간에 걸리면 **직전 값이 그대로 남는다**(`kojiro.py:393-401` vs `:664-668`, `:701-703`, `:742`).
어제 `True` 였던 종목이 오늘 데이터 열화로 재판정되지 못하면
**가격과 무관하게 즉시 `TRAILING_STOP`** 이 나간다. fail-open 이 아니다.

### P2-6 · BFB 진입창 naive 시각 + 좀비 타이머 — ⚠️ 좀비 타이머 축은 cycle228 부분 종결

> cycle228 이 `_breakout_first_seen` 에 일 경계 스테일 자기 방어(진짜 롤오버 시 clear,
> `_roll_gate_day_if_needed`)를 넣어 "익일 09:05 elapsed 수만 초 → retention 즉시 충족
> 우회" 축은 닫혔다. **잔여 = naive 시각 비대칭**(`:794` `datetime.now().time()` vs
> `:801` KST — 컨테이너 TZ 의존)과 `scheduler.py:2984` 스윙 폴 시간 가드 동형.

- `bull_flag_breakout.py:794` 가 `datetime.now().time()`(naive), 두 줄 뒤 `:801` 은
  `datetime.now(KST)` — **같은 함수 안에서 비대칭**. 컨테이너 `TZ=Asia/Seoul` 에 의존.
- 시간 가드가 retention 블록보다 **앞**이라 12:59:58 등록분이 영구 동결된다.
  익일 09:05 에 `elapsed` 가 수만 초라 retention 이 즉시 "충족" 처리되는 **우회**가 생긴다.
- `scheduler.py:2984-2989` 의 스윙 REST 폴 시간 가드도 동일하게 naive.

### P2-7 · `[day_high_scope_skip]` 문구가 grep 을 모호하게 함

note 본문이 교차 판별자로 `[day_high_adopted]` 를 언급해, 단순 substring grep 이
두 마커를 구분하지 못한다. **2026-08-25 실제로 4건을 114건으로 오집계**했다.
정밀 매칭은 `'[day_high_adopted] strategy='` / `'[day_high_scope_skip] ticker='`.

### P2-8 · F-E 잔여 코호트 관측

2026-08-25 실측: **110종목**이 첫 MAIN 관측 시 당일고가가 프리장(`hgpr_hour=08시대`)에 있었고,
09:47 시점 **3종목만** 전환. 보유 7종 중 4종이 걸렸고 3종 미전환 =
그 시간 동안 사이클 222-a 의 blind 내성이 꺼져 있었다.
며칠 관측해 규모를 확정한 뒤 대응을 정한다(현재는 fail-closed = 안전 방향).

---

## P3 · 사람 결정이 필요함

### P3-9 · `prepare()` 관용 읽기 — 매수를 넓히는 방향

`prepare()` 가 `stck_hgpr` 만 읽어서, `_extract_raw` 가 `raw` 없는 row 를 그대로 반환하면
(`src/db/stock_master_daily.py`) `0` 을 읽는다. `high_price` 도 수용하면 해결되나
**매수를 넓히는 방향**이라 사람 결정 사안으로 남겼다.
현재 **잠복** — 일봉 writer 가 `raw` 를 항상 저장하고 라이브 샘플도 전부 보유였다.
사이클 226 이 안전 방향 3중 방어(후보 거부 · 재도출 자가치유 · 폴백 가시화)만 닫았다.

### P3-10 · cycle221 슬롯 축 — ✅ cycle230 으로 채택·종결 (2026-08-29)

> 재평가 결론(사용자 결정) = **채택·커밋**. "슬롯 부족" 반증(08-25)은 *BFB 미구독 원인*
> 주장만 반증(실원인 = P0-2 축출), 08-19 실사고(메인 45/41 서버 한도·VI 누수·보유 4종목
> tick blind)는 유효. 적대적 리뷰 "주 목적 미달성"은 불완전 지적일 뿐 — 누수 차단·main_over
> 계측·VI 메인 퇴출은 독립적으로 옳고, P0-2 시정+cycle228 매수 개방으로 구독·보유 압력이
> **재증가 추세**(8/28 구독 144 = 8/25 대비 +30%)라 가치 회복. **잔여 후속(신규)** =
> 메인 헤드룸 관리 — LOW tick 후보의 메인 fallback 이 VI 퇴출로 빈 슬롯을 되채우는 축
> (적대적 리뷰의 미달성 지적 그 자체). 관측 = 신규 `main_over` 필드로 실측 후 판단.

- 미커밋 잔류: `src/engine/scheduler.py +135/-46` + 테스트 6파일.
- 적대적 리뷰 **주 목적 미달성** 판정(VI 를 main 에서 빼도 LOW tick 후보가 슬롯을 되채움).
- **⚠️ 2026-08-25 BFB 조사에서 "슬롯 부족" 전제 자체가 반증됐다** —
  라이브 구독 111/328 = **34% 사용**, 217슬롯 유휴, `[priority_drop]` 08-20 이후 **0건**.
  이 사이클을 계속할지부터 재검토하라.

### P3-11 · donchian 라이브 이탈값 재튜닝

`breakout_fail_n_days=2`(코드 5) · `atr_trail_mult=1.8`(코드 2.0).
사이클 223 S1 봉인 후 **복원 경로는 운영자 수동 DB UPDATE 뿐**.
2026-08-25 에 S1·S2·S3 전부 실측 확증됐으므로, 표본이 쌓이면 재튜닝 판단 가능.

---

## 이번 조사에서 반증된 가설 (다시 파지 말 것)

| 가설 | 판정 근거 |
|---|---|
| "retention 을 못 버텨서 매수 0" | **반증** — 2026-08-25 **21회 이상 완주**. 완주 경로가 무로그라 안 보였을 뿐 |
| "구독 슬롯 부족" | **반증** — 111/328 = 34% 사용, 217 유휴, `[priority_drop]` 0건 |
| "후보 48이 과다해 구독 압력" | **반증** — 08-08 확대 이후 **최저치**(08-13 142 / 08-18 146 → 48) |
| "BFB 가 구독 대기열 후순위라 tail 절단" | **반증** — 병합 순서 **최선두**, `BREAKOUT_LOW_CAP` 은 08-08 제거 |
| "같은 dict 를 읽는 donchian 도 동일 결함" | **반증** — donchian 은 `max(...)` 라 **fail-open**. BFB·VCP 만 fail-closed |
| "수량 산출·예산 클램프가 병목" | **반증** — 애초에 BUY 분기에 도달하지 못해 `calc_buy_quantity` 가 호출조차 안 됨 |

---

## 작업 시 지켜야 할 제약

- **8영역 무단 수정 금지** — `risk.py` · `order_engine.py` · `src/realtime/` · `src/auth/` ·
  `api/order.py` · `session.py` · `scanner.py` · `strategy_registry.py`.
  P0-1 방향 A 는 `handler.py`(8영역) 수정이 필요하니 **명시적 승인** 후 진행.
- **워킹트리에 미커밋 cycle221 잔류** — `git checkout` / `stash` / `restore` **절대 금지**.
- **배포 창** — NXT 애프터(15:30~) 또는 익일 07:45 부팅 전. KRX 메인(09:00~15:30)과
  20:00 자문 / 20:10 로그분석 회피.
- **커밋·푸시는 사용자 명시 지시가 있을 때만.** 푸시 후 `gh run list` 로 CI/Deploy 확인 의무.
- **`enabled=False` 금지** — `risk.on_tick` 이 `registry.enabled()` 만 순회해
  보유 포지션의 손절·트레일링이 **전부 정지**한다. 비중 축소는 극소값(0.01)으로.

## 검증에 쓸 명령

```bash
# 유령 키 확인 (대입부는 risk.py:397 하나뿐, acml_vol 없음)
grep -rn "ticker_prices\[" src/ | grep -v CLAUDE.md

# ⚠️ cycle243 이후 :80 은 nginx Basic Auth 뒤에 있다 — `-u <USER>:<PASS>` 없으면 401.
#    (EC2 내부 :8000 직결은 대신 `-H "X-API-Key: …"` — 포트마다 방식이 다르다)

# 라이브 키 출현 대조
curl -s -u "<USER>:<PASS>" "http://3.38.228.74/api/trading/status" | grep -o '"acml_vol"' | wc -l   # → 0

# BFB 상태
curl -s -u "<USER>:<PASS>" "http://3.38.228.74/api/strategies" | python3 -c \
  "import sys,json;r=json.load(sys.stdin)['data']['bull_flag_breakout'];print(r['scan_stats'],r['positions'],r['buy_signals'])"

# 전체 회귀
find . -name __pycache__ -prune -exec rm -rf {} + ; python -m pytest -q
```

## 2026-09-05 오후 사용자 답변(보고서 2부 결정 카드)

| 카드 | 사용자 답(09-05 15:0x) | 처리 |
|---|---|---|
| ① 허용 도메인 `auto.dkstock.cloud` 추가 | "추가완료" | 월 09-07 20:20 자동 리포트 마지막 메시지 "(e) 사용 주소 = https" 로 확인(그 전 수동 실행은 하지 않는다 — 토요일 리포트·Notion 페이지 노이즈) |
| ② 대시보드 '일일 리포트' 탭 시각 표기 | "바꾸자" | **구현 완료(cycle256-F, vitest 537 PASS·`tsc -b` clean) — **배포 완료 09-05 18:32**(full, 마커 f27f55b — 8fe9565 CI 는 rotate 스크립트 주석의 `-stdin` 누락으로 D-15 가드 실패 → f27f55b 핫픽스)** — `DailyReportTab` 을 `utils/kst.ts` `formatKstDateTime` 로 위임(`2026-09-07 09:05:00`), 배포 = frontend 모드 |
| ③ D10 착수 요일 | "화요일" | 09-08(화) 아침 호출자 전수(영향 범위 목록) 제시 → 8영역 승인 → Red→Green → 장외 배포. 명세 `_workspace/specs/cycle_next_D10_pg_acquire_timeout.md` |
| ④ TLS 2단계 시점 | "제안대로" | **준비 완료(cycle260, 신규 가드 168 PASS·백엔드 전체 7,005 PASS)** — 스위치는 여전히 OFF, 가동은 월 09-07 20:20 자동 리포트 https 성공 확인 뒤 `ROUTINE_HTTPS_CONFIRMED=1 bash tools/ops/tls_stage2_enable.sh`(http→https 301 + HSTS 1일 + Basic 자격 회전) — **준비 코드 배포 완료 09-05 18:32**(tls2=off, nginx -t OK, 80/443 응답 1단계와 동일 실측) |

## 2026-09-05 밤 사용자 답변(보고서 3부 결정 카드)

| 카드 | 사용자 답(09-05 23:xx) | 처리 |
|---|---|---|
| ① 월 09-07 20:25~22:00 2단계 가동 자율 구간 | "허용" | **자율 구간 성립**(커밋·푸시·장외 배포·루틴 프롬프트 수정 포함). 절차 = 런북 `_workspace/specs/tls_stage2_activation_runbook_0907.md`. 사용자 직접 행동 = ⑤ 새 비밀번호를 클라우드 환경 `REPORTER_BASIC_PASSWORD` 에 넣기 + 브라우저 재로그인 |
| ② HSTS 기간 상향 | "1주 뒤 올려" | 가동 1주 뒤(**09-14 이후 첫 장외 시간**) `max-age=86400` → `15552000`(180일): 스니펫 2(`tls-srv-hsts.conf`·`tls-loc-hsts.conf`) + `tls_stage2_enable.sh` 검증 정규식 2줄 + G-260 가드 기대값 동시 갱신 → push(frontend 모드) → 헤더 실측. 사전 승인됨 |
| ③ '전략수정 AI자문' 페이지 시각 표기 | "바꿔" | **구현 완료(cycle256-G, vitest 579 PASS·`tsc -b` clean·`npm run build` 성공) — 배포 대기** — `pages/Recommendations.tsx` `formatDateTime` 을 `utils/kst.ts` `formatKstDateTime` 로 위임(KST 강제 + `2026-09-07 09:05:00`, export 추가로 단위 테스트화), 배포 = frontend 모드 |

## 2026-09-06 사용자 결정 — 수수료·세금 비용 반영 사이클

- 사용자(09-06 새벽): "화요일부터 하자". 09-03 결정 항목 9(수수료·세금 관측 배선, 권고안대로)의 착수일 확정 = **화 09-08**(D10 과 같은 날 — D10 아침 승인 뒤 이어서 또는 D10 배포 뒤).
- 1단계(관측): 매도 체결마다 수수료·거래세 **추정액**과 순손익(net)을 기록(`trade_history` 가산형 컬럼 — NULL 허용 ADD COLUMN), 일일 실적·20:10 리포트·대시보드에 gross/net 병기. 손익 계산 지점 `order_engine.py:1389`(8영역) 1곳 = 승인 필요. 비용률 = KIS 계좌 실제 수수료율 확인(잔고/체결 조회 TR 의 수수료 필드 또는 계좌 약정) → 확인 불가 시 설계서 가정(수수료 0.015%/편도, 거래세 0.15% 매도 시). 슬리피지는 비용 모델 밖(관측만).
- 2단계(행위): `daily_loss_limit` 게이트를 net 기준으로 — 관측 며칠 뒤 별도 결정.
- 정본 근거: `_workspace/domain_consult/pyramiding_deep_review_20260903.md` §비용(왕복 0.32~0.53% = 1N 의 5.3~11.5%), 설계 청사진 C-27(미해소), `_workspace/morning_0903_report.md` §7 #9.

## 2026-09-06 VB·LTV 진입 필터 재검토 (사용자 요청 — 상세 리포트)

- 산출: 보고서 `_workspace/reports/2026-09-06_vb_ltv_filter_review.md` + 아티팩트 https://claude.ai/code/artifact/51e4f58f-35a9-4f1d-8a95-d3a3729fae5e · 근거 묶음 `_workspace/analysis/vb_ltv_filter_review_20260906/`(분석·사실지·자문·독립검증·재현 스크립트·집계 CSV).
- **판정: 필터 3종(재무퀀트 F-Score/마법공식 · RS · RSI) 실배제 근거 없음 — 08-18 결정 유지.** 룩어헤드 없는 적격 부분집합(D-1 거래대금 기준, n=1,803)에서 주 대비 8검정 전부 p ≥ 0.215. RSI>85 는 적격 풀 1건(0.06%)이라 규칙 성립 불가.
- ⚠️ **검증이 확증한 HIGH 결함**: 저장된 VB funnel 행은 16:20 저녁 캡처(그날 거래대금으로 걸러진 풀)라 당일 성과에 정렬하면 룩어헤드다(2,284 중 481건 21.1% 부적격). 1차 분석의 풀 수준 수치(+71.2bp·신규 창 유의·RS 부호 반전·레짐 r 0.47)는 그 artifact — **인용 금지**. 정직한 수치는 적격 부분집합 또는 D+1 정렬 재실행(Phase 0-1) 뒤에만.
- **사용자 우려("K 돌파 단독 의존")에 대한 답**: 방향은 맞지만 원인이 다르다. 적격 풀 무조건 시가→종가 +5.8bp(p 0.895, 드리프트 0) → K 조건을 걸면 −67.6bp(n=163, 돌파율 9.0%), 비용 28bp 후 −95.6bp. 필터로 메울 크기가 아니다 — 최악 분위 배제 효과 최대 18.7bp vs 08-18 이후 흑자 필요치 +78bp/왕복. 효과 축은 종목 성질(≤18.7bp)이 아니라 시장 상태(레짐 스프레드 285bp)·시각(09:00 구간 195bp).
- **구조 발견 2건(필터 무관)**: ① 09:00:00~09:01:30 진입 16건 = VB 손실의 39%(−32,400, 승률 18.8%), 진입가가 KRX 시가 기준 목표가보다 중앙 −231.9bp 아래이고 4건은 그날 시가보다도 아래 = **09:00 진입 기준가(시가 필드) 의심** — realtime 조사 사안(시정은 8영역 승인). ② VB 손익비 RR 0.567 vs 손익분기 1.283 → EV=0 에 승률 +16.6%p 또는 avg_win +97% 필요 = 진입 필터가 아니라 청산 규약(익절·트레일링) 문제. LTV 는 오버나잇 3건만 +19,900 인데 당일 모드가 −58,900 을 태움(꼬리 전략이 꼬리를 못 잡는 구조).
- **결정 카드 10장은 보고서 §7**(급한 것 = 비중 처분 A/B/C · Phase 0 재실행 승인 · 09:00 조사 착수 · 임시 매수 보류 여부). 사용자 답변 전까지 코드·설정 변경 0.

## 2026-09-06 사용자 지시 — 필터 배치 재설계(스윙군 3종 / VB·LTV 2종)

- 사용자(09-06): "검증결과 확인 후 별로라면, 필터 3종을 돈치안·고지로·VCP 의 필터에 적용하는 방안도 검토해보자. 대신 VB·LTV 에는 네가 적합하다 추천했던 시장상황·시가갭 필터 2가지를 적용 검토해보는 걸로."
- **진행 1(무조건)**: VB·LTV × 시장 상황(레짐)·시가 갭 검토 — 워크플로 착수(산출 `scratchpad/vbreview/regime_gap/`). 룩어헤드 차단(특징량은 D-1 종가 또는 D 09:00 확정값만), 갭과 09:00 진입 시각의 **교락 분리**가 핵심 과제.
- **진행 2 착수함(조건 충족)**: RS 강세 반사실 = **기각**(아래) → 스윙군(donchian·kojiro·VCP) 3종 필터 검토 워크플로 착수(산출 `scratchpad/vbreview/swing3/`) — 계획서 `_workspace/specs/swing_3filter_review_plan.md`. 훅이 없어 점수는 오프라인 계산, 재무 데이터는 08-12 이후 정지(347종목) 제약.
- 세 갈래 결과는 **하나의 아티팩트 리포트**로 합쳐 보고한다. 모든 단계 코드·DB·설정 변경 0(SELECT 만), 실배제는 별도 사이클 + shadow 선행 + 승인.

### RS 강세 반사실 결과 (2026-09-06, 판정 = 기각)

- 근거 묶음 `_workspace/analysis/vb_ltv_filter_review_20260906/rs_strong/`. 표본 = 적격 1,803 중 RS 보유 **1,083(23 거래일, 08-03~)**.
- **개선폭이 음수이고 유의하다**: 돌파 조건부 일별 상위 25% **−97.9bp(p 0.0046)** = 왕복당 −1,376원 · 상위 50% −46.0(p 0.011) · RS≥0 +1.3(p 0.908, 통과율 77% = 무작동). 흑자 필요치 +78bp 대비 **−126%**.
- **"총손익 개선" 은 편향 통계**: 왕복 기대값이 음수라 아무 필터나 N건 줄이면 +1,382×N 이 생긴다. 동일 유지율 무작위 순열검정(20,000회) 최소 p **0.404**, 5개 중 3개가 무작위보다 **나쁘다**.
- **슬롯 대체·라이브 K 반영 시 손실 2.6~3.5배**(슬롯당 −39.9bp → −113.4~−166.7).
- **메커니즘**: 이 유니버스에서 RS 는 추세 강도가 아니라 **최근 변동성 확대**를 잰다(RS ↔ 시가 대비 목표가 위치 r +0.284). 강세를 고르면 돌파율 37.1%→28.4%, 승률 41.2%→33.3%.
- **지평을 줄여도 악화**: 3일·5일 초과수익 상위 25% −147.6·−153.6bp(p 0.0014·0.0039).
- ⚠️ **이 제안을 지지하던 수치는 전부 룩어헤드였다** — 오염 481건만 보면 +233.1bp(p 0.018), 적격만 보면 −33.7bp. `analysis.md §4.2` 의 "RS 역방향은 우연" 문장은 철회 대상.
- 판정 = **기각**(라이브 배선 금지, shadow 관측조차 미권고). 채택 시 최소 조건 C1~C7 은 `rs_strong/judgement.md`.

### VB·LTV 레짐·갭 필터 검토 결과 (2026-09-06)

근거 = `_workspace/analysis/vb_ltv_filter_review_20260906/regime_gap/`(regime.md · gap.md · design.md · 독립검증 verify_report.md · 컬럼 사전).

- **시가 갭 필터 = 기각.** 갭업 컷은 강한 기각(풀 4셀 중 3셀 음, 상위100 근사 기울기 VB +7.67·LTV +11.84 = 갭이 클수록 낫다, LTV 실체결 −65,603원). 갭다운 컷(<−2% 제외)은 유일하게 4셀 동부호(+4.3~+13.8bp)이나 ① 사전정의 16검정 Bonferroni 통과 0 ② **지수 갭을 통제하면 부호 반전** ③ 실체결 이득 +28,068원은 **슬롯 대체 미반영**이고 보정하면 ≈ −8,333원. 갭 필터가 잡은 것은 종목 갭이 아니라 **그날 시장 갭** = 아래 (h) 의 열등한 프록시.
- **교락 분리 결과가 중요하다** — 09:00~09:01:30 조기 진입 −228.0bp(p 0.047)는 갭을 통제해도 그대로인데, 갭>+2% 효과는 −112.7 → **−8.2bp(p 0.948)로 소멸**한다. 손실의 원인은 갭이 아니라 **진입 시각(기준가 결함)** 이다.
- **시장 상황 필터 = 조건부(shadow 부터).** 살아남은 후보는 단 하나 — **(h) KOSPI200 09:00 지수 갭 ≥ 0 인 날만 매수**(VB 풀 +47.8bp p 0.0070, 거래일 유지 42/80). 강점은 크기가 아니라 일관성(프록시 6종 전부 동부호, 성과 정의 4종 부호 유지, 조기진입 21건 제외해도 유지). 사전 정의 3규칙은 전부 탈락 — MA5>MA20 무신호, 20일 변동성 상위 25% 중단 무신호, **지수 전일수익률 ≥ 0 은 유의하게 역효과(VB −42.3 p 0.014 / LTV −49.1 p 0.005) = 금지**.
- ⚠️ **검증 확증 HIGH 3건** — (1) regime.md 헤드라인 반사실이 09:00 **이전** 체결(LTV 프리장 11건)에 09:00 게이트를 적용했다(문서 자체 서술과 모순) (2) 게이트 후 흑자 +28,988원은 **왕복 2건·거래일 1~2일**에 얹혀 있다(1건 빼면 −15,166, 부트스트랩 음수 확률 38%) (3) 갭 규칙 이득은 슬롯 대체 무시. **"켜면 흑자" 는 성립하지 않는다** — 자본 노출 균등 기준으로는 −84.8 → −35.6bp 로 여전히 적자.
- 매크로(dkstock) 축은 **판정 불가**(스냅샷 12행·전부 defensive·VIX 중앙 18일/최대 73일 stale).
- 결정 항목 10건은 `regime_gap/design.md`. 권고 = **S0(야간 재구성 관측, 코드 0줄·SELECT 만) 즉시 → 20 거래일 뒤 S1(shadow 배선) 재판단**, 실배제는 09:00 기준가 조사 뒤.

### ⚠️ 운영 결함 발견 — 일봉 16:00 적재가 매일 no-op (2026-09-06 실측) — **✅ cycle263 이 시정(커밋·배포 대기)**

> 아래는 **발견 시점 기록**이다. 시정 내용·D+1 확인 항목·별건 목록은 이 파일 최상단 cycle263 절이 정본이다.
> ⚠️ 배포 후 16:00 실행의 `skipped_fresh` 는 ~1,000 → ~0 으로 **의미가 반전**한다 — 아래 실측치와 배포 후 로그를
> 같은 grep 으로 합산하지 말 것.

- `_stock_master_daily_load_once` 의 idempotency 규칙이 **"max_bas_dd 가 오늘이면 skip"** 인데, 07:5x 아침 적재가 KIS 에서 **당일 스텁 봉**(장 전이라 o=h=l=c=전일종가·volume 0)을 받아 오늘 날짜 행을 먼저 만든다 → 16:00 적재가 전 종목을 fresh 로 보고 건너뛴다. 09-04 실측 로그: `16:04 total=1016 fetched=1 upserted_rows=1 skipped_fresh=1015`.
- 결과: **D 의 실봉은 16:00 이 아니라 D+1 07:5x 에 들어온다.** DB 실측 — 09-04 행 1,082 중 실봉 67, 09-03 행의 `updated_at` 이 09-04. 07:55 적재와 `_boot`/`prepare()` 가 겹쳐 **경합**이 생긴다(스윙 전략이 갱신 전 스텁 봉을 읽을 수 있다).
- 부수 관측: 날짜별 종목 수가 07-01 1,801 → 09-03 **1,140(−37%)** 으로 감소(`candidates` 1,015 = `_is_daily_load_universe` 통과 수). 의도된 축소인지 확인 필요.
- 영향권: `stock_master_daily` 를 읽는 donchian(20일 신고가)·VCP(베이스)·kojiro 지표·LTV 연속상한가 판정. **`scanner.py` = 8영역이라 시정은 승인 사안.** 이번 분석·스윙군 분석의 데이터 한계이기도 하다.

### 스윙군(donchian·kojiro·VCP) × 3종 필터 검토 결과 (2026-09-06) — 9칸 전부 기각

근거 = `_workspace/analysis/vb_ltv_filter_review_20260906/swing3/`(rs_rsi.md · quant.md · design.md · verify_report.md · coverage.csv).

- **착수 가설("지평이 맞는 스윙군에서는 신호가 나온다") 기각.** 오히려 VB 보다 무력하다.
- **무발화**: donchian 은 RS<0 관측 **0.0%**(RS≥0 규칙이 아무도 못 거른다) · donchian·kojiro RSI<30 각 **0건**.
- **무신호**: RS·RSI 사전정의 주검정 9건 Holm 후 유의 0 · 재무 퀀트 48셀 중 종목 클러스터 반영 유의 0(우연 기대 2.4), 부호 67%가 가설과 반대.
- 옳은 귀무를 통과한 유일 셀(donchian `RSI>70 배제` 슬롯 +41.7bp, BH q 0.150)은 **실체결에서 반증**(배제 3건 전부 이익 +7,116원, 규칙 기여 −10,867원, 순열 p 0.971). kojiro 최선 셀은 **fail-open 이 표본 최대 승리 거래를 무상 통과**시킨 결과라 재현 불가.
- **VCP 는 검정 자체가 불가** — 전 기간 매수 0건, 최종 후보 40거래일 누적 **2건**(step7 Pullback 에서 13.5→0.8/일 절단). 필터 추가는 표본 생성을 더 막는다.
- 지평 정합은 이름이 아니라 실측 보유기간이 정한다 — **donchian 라이브 보유 중앙 3일**(2~4일 80%). rs20 ↔ 20일 수익률 일내 순위상관 **0.83~0.85** = 기존 게이트가 이미 재는 축.
- 결손 축이 필터 정원 밖: donchian **RR 0.45** vs 손익분기 2.33(필요 avg_win 5.2배) · kojiro 승률 **14.3%** vs 필요 27.8% · VCP 체결 0.
- 결정 9건 = `swing3/design.md`. 권고 = 라이브 배제 미채택, shadow 도 미권고.

### 부수 발견 3건 (2026-09-06, 별도 처분 필요)

1. **RS 벤치마크 069500 이 시장을 대표하지 않는다** — 전종목 중앙 일간수익률 대비 상시 2~3배 증폭, 부호가 어긋나는 날도 있다. **벤치마크 교체 후 재검정 전까지 RS 수준 기반 수치 인용 금지.**
2. **VCP·BFB `max_lot_ratio_mult=20.0` 잔재** — cycle245 배포 직전 표본 보호로 DB 에 넣은 임시값이 그대로다. VCP 진입이 열리면 ρ축 상한이 꺼진 채 첫 랏이 나간다. **최소한 VCP 진입 개방 전 2.5 복원.**
3. **donchian `breakout_fail_n_days` 라이브 2 vs 코드 기본 5** — 라이브가 훨씬 빠른 시간 청산. 보유 중앙 3일의 원인 후보. 재검토 등재.

### 2026-09-06 저녁 사용자 결정 — 일봉 적재 시각 3안의 착지점

사용자가 하루 동안 세 가지를 제안했고 각각 다르게 착지했다. **이 표가 정본이다.**

| 안 | 결론 | 근거 | 정본 |
|---|---|---|---|
| **23:00 / 05:00 이동 (루프 밖 시각)** | **불가** | task loop 이 `while scheduler._running` 인데 `scheduler.py:1035` 가 20:10 정산 직후 `_running=False`, `run_daily` 가 익일 07:45 까지 잠든다. 그 시각엔 루프가 존재하지 않는다 | 자문 부록 A ⑨ (D-11) |
| **05:00 기동 (`TIME_AUTO_START` 이동)** | **보류 — cycle263 D+1 확인 후 재론** | 목표를 달성하지 못한다: immediate 발화가 `기동+240초`이고 멱등 판정이 `today_kst()` 절대 비교라 05:04 에도 껍데기를 그대로 쓰고 그날 16:00 이 또 skip 된다. "하루 한 번" 은 시각이 아니라 신선도 게이트가 만든다 | `_workspace/analysis/wake_0500_20260906/judgement.md` §① |
| **16:00 → 18:10** | **화요일 09-08 cycle263 D+1 확인 후 착수** | 사용자 취지("밤에 한 번, 확정본으로")의 실현 가능한 착지점. `scheduler.py` 상수 1줄, 세션이 ~20:15 까지 살아 있어 재설계 불필요 | 자문 D-9 |

**cycle263 이 실제로 한 것** = 시각 상수 무변경 + 아침 immediate 를 신선도 게이트(20h)로 건너뛰게 함.
⇒ 화~금 **하루 한 번**(16:00 만) · 월요일만 두 번(금요일 마커가 63.9h 라 아침이 뜨지만, 오늘봉 필터가
껍데기를 막아 그날 16:00 도 정상 동작) · 16:00 실패 다음 날엔 아침이 되살아난다(안전망 보존).

**16:00 유지의 유일한 잔여 비용** = 시간외 단일가(16:00~18:00) 물량이 그날 봉에 안 잡히고
**다음날 16:00 의 T-7 재수집이 하루 늦게 보정**한다. 잃지 않고 하루 밀린다. 18:10 이 이걸 없앤다.

**18:10 착수 전 확인 완료(메인 세션 직접)**
- 16:20 저녁 funnel 캡처 — **영향 없음**. 전략이 `prev_idx` 로 오늘 봉을 어차피 잘라내고 전일 봉을
  쓰므로, 18:10 이면 16:20 시점에 오늘 행이 없어도 결과가 같다
- 16:15 purge · 20:00 자문/full_universe · 20:10 정산 — 시각 무충돌
- 18:10 실행의 마커는 익일 07:56 기준 13.7h < 20h ⇒ 아침 건너뛰기 그대로 성립
- ⚠️ **미확인 1건** — 이 일봉에 NXT 애프터(~20:00) 물량까지 잡히는가. 잡힌다면 18:10 도 그 부분은
  다음날 보정에 맡긴다. 월요일 장 마감 후 실측 필요

**화요일 09-08 아침 판정 기준** = 07:51 과 08:02 두 prepare 후보 수 **수렴**
(baseline: LTV 10/90 → 90/90, donchian 1/111 → 4/111, BFB 42/595 → 25/596).
수렴하면 cycle263 이 들은 것이고, 그때 18:10 이동을 올린다.

---

## 2026-09-06 15:16 — 금요일 일봉 보정 실행 (사용자 승인 D-3) + 조사 결론 강화

**실행** — `POST /api/stock-master/daily/refresh` (force 기본값 True), 15:07:39~15:16:00.
963종목 · 6,916행 갱신 · 실패 0. 쓰기는 `ON CONFLICT DO UPDATE` 멱등 경로뿐(DDL·DELETE 0).
초반 6분은 보조 시세 계좌 토큰 워밍업(7계좌 중 5계좌 × KIS `/oauth2/tokenP` 분당 1개 한도)에
묶였고, 15:13:58 이후 2분 만에 완주했다 — **force 재실행 시 토큰 워밍업 시간을 예산에 넣을 것**.

**결과** — 09-04 스텁 **1,015 → 120**. 잔여 120 은 `stock_master` 유니버스에서 빠진 종목
(테이블 행 1,082 − 갱신 대상 963 = 119)이라 이번 보정 범위 밖이다.

**부수 효과 — 카드 ② 조사 결론이 강화됐다.** 09-04 가 스텁이라 못 하던 대조가 가능해졌고,
"역산 기준가가 그날 KRX 정규장 저가보다 낮다"(= KRX 세션에 존재하지 않은 가격) 서명이
**1건 → 3건**으로 늘었다.

| 종목 | 역산 기준가 | KRX 시가 | KRX 저가 | 시가 대비 | 판정 |
|---|---|---|---|---|---|
| 105560 (09-03) | 169,300 | 171,600 | 169,400 | −134bp | **저가 미만** |
| 000270 (09-04) | 128,200 | 132,700 | 125,700 | −339bp | 시가 미만 |
| 078930 (09-04) | 120,000 | 121,600 | 121,600 | −132bp | **저가 미만** |
| 108490 (09-04) | 257,000 | 267,000 | 265,000 | −375bp | **저가 미만** |

**월요일 07:51 첫 prepare 는 이제 진짜 09-04 봉을 전일봉으로 읽는다** — 시정 코드 배포 여부와
무관하게 성립한다(자문 §5). 다만 월 07:56 immediate 가 09-07 스텁을 또 쓰므로, 시정을 같이
배포하지 않으면 그날 16:00 은 여전히 skip 된다.

---

## 2026-09-06 카드 ② 조사 결과 — VB 목표가 기준가가 KRX 09:00 시가가 아니다 (확증)

**결론: 근본 원인 확정.** VB 목표가 `target = open_price + int(int(prev_range × k) × k_value)` 의
`open_price` 는 KRX 09:00 시가가 아니라 통합 채널 `H0UNCNT0` 체결 프레임의 **`fields[7] STCK_OPRC`
= 그 종목의 세션 시가**다. 08:00 NXT 프리장에서 체결이 있었으면 **프리장 시가**가, 없었으면 KRX
09:00 시가가 들어간다. 오염은 전수가 아니라 **프리장 체결이 있었던 종목에 선택적**이다.

**코드 사실 (메인 세션 직접 확인)**
- `src/realtime/handler.py:279` `_parse_tick_prices` = `return int(fields[2]), int(fields[7])` — **스코프 필터 없음**
- 형제 필드 `[8] 고가`는 `_parse_day_high`(`:284`)가 cycle222-a2 에서 **`[27] HGPR_HOUR` 스코프
  필터**를 이미 받았다. 그 docstring 이 "통합 채널 일-스코프 필드는 09:00 에 리셋되지 않는다"를
  명시한다 — 즉 같은 결함을 고가에서만 고치고 시가에는 남겨 뒀다
- 대응 판별자 **`[24] OPRC_HOUR` 는 전 소스에서 파싱 0건**(주석 언급뿐, `grep` 전수 확인)

**증거 4축 (서로 독립)**
1. 코드 — 위 비대칭
2. `[breakout_open_confirm]` 스탬프 vs KRX 일봉 시가 **7/10 불일치**
3. 매수신호 로그 목표가 역산 — K 5/5 소수 4자리 일치로 방법론 검증, 000270 은 두 독립 로그가
   128,200 으로 교차검증. 105560(09-03) 역산 기준가 169,300 은 그날 KRX 정규장 **저가 169,400
   미만** = KRX 세션에 존재하지 않은 가격. 086790 board open 134,900 = 전일 종가와 **정확히 일치**
4. `[day_high_scope_skip]` 오염 시각이 **08시대 100%**(93/93, 71/71) — 같은 채널·같은 세션 지목

**기각된 대안** — ① KRX 09:00 시가(조기 코호트 20/20 이 "체결가 ≥ 목표가" 위반) ② 전일종가 계열
(스탬프가 전일종가와도 **양방향** 이탈. 선행 리뷰의 "전일종가+offset 과 +2.5bp(n=9)" 는 **착시** —
프리장 시가가 전일종가 근처에 자주 놓일 뿐이다)

**⚠️ 사용자 결정 ② 의 전제가 일부 무너졌다** — **"조기 09:00~09:01:30 전용 결함" 은 기각**이다.
대조군(09:01:30 이후)에도 오염이 **39~59 / 96** 존재하고 09-03 의 09:05·09:11 진입도 동일하게
오염됐다. 따라서 90초 임시 매수 보류는 **피해 최대 구간의 지혈**일 뿐 결함을 고치지 못한다.

**근본 시정** = `[7]` 에 `[24] OPRC_HOUR` KRX 정규장 스코프 필터를 거는 것(`[8]` 이 `[27]` 로 한 것과
동형). ⚠️ **`src/realtime/**` = 8영역 + 진입 목표가 = 매매 행위 변경** ⇒ 승인 + `domain-consult` 선행.
고가와 달리 **시가는 fail-closed(0 강등) 를 쓸 수 없다** — 0 이면 VB 매수가 통째로 멈춘다. 방향
설계(0 강등 vs REST `stck_oprc` 폴백 vs 보류)가 별도 쟁점이다.

**파급** — LTV **동형**(`long_tail_volatility.py:609-627, 663-665`) · kojiro 는 갭/"시가 아래" 판정으로
간접 · donchian 은 매수 경로가 REST(KRX)라 **무관**.

**남은 불확실성** — (a) `[24] OPRC_HOUR` 를 실제로 찍어 본 적이 없다(가장 값싼 결정적 실험 =
그 필드 관측 배관 한 줄) (b) NXT 프리장 시가 시계열이 DB 에 없어 역산으로만 확인 (c) 전략 INFO
로그가 08-31 이후만 잔존, `docker logs` 는 backend 재생성으로 소실.

**부수 확인 대상** — 09:00:05 `[breakout_open_confirm]` 이 VB 에 대해 `confirmed=0 empty=55/65`
(09-03·09-04) = 시가 확정 주 경로가 사실상 무동작이고 첫 MAIN 틱이 목표가를 정한다.

산출물 = `_workspace/analysis/entry_price_0900_20260906/{code_trace.md,forensic.md,data/}`

---

## 2026-09-06 사용자 결정 — 진입 필터 종합 리포트 카드 8장 (아티팩트 체크 회신)

| # | 카드 | 사용자 답 | 처리 |
|---|---|---|---|
| ① | VB·LTV 비중 | **C — 구조 조사 먼저** | 비중 값은 손대지 않는다(VB 0.15 / LTV 0.10 유지). 상향·하향 모두 보류하고 ②③④ 착수가 곧 이 답의 이행이다 |
| ② | 9시 기준가 조사 | **조사와 임시 매수 보류 함께** | (a) 조사 = realtime 로그·코드 판독(읽기 전용) (b) 임시 보류 = 09:00:00~09:01:30 매수 보류. **매매 행위 변경이므로 domain-consult 선행 + 이 승인으로 착수**. 월 09:00 개장 전 배포가 목표 |
| ③ | 지수 갭 관측(S0) | **진행해** | 코드 0줄·SELECT 만·주 1회 배치. KOSPI200 09:00 지수 갭과 그날 성과를 기록해 20거래일 축적 |
| ④ | 일봉 16:00 적재 결함 | **승인** | `scanner.py` = 8영역 승인 획득. 아침 스텁 봉이 `max_bas_dd==오늘` idempotency 를 걸어 16:00 적재가 매일 no-op(09-04 `skipped_fresh=1015`). 장외 배포 |
| ⑤ | VCP 처분 | **(b) 조건 감사 후 완화** | 필터 추가는 기각. 진입 게이트(step7 Pullback 13.5→0.8/일 절단 포함) 정의 감사 → 한 축씩 shadow. **domain-consult 선행** |
| ⑥ | VCP·BFB 랏 상한 복원 | **VCP 진입이 열리기 전** | 지금은 손대지 않는다. `max_lot_ratio_mult` 20.0 → 2.5 복원은 **VCP 첫 진입 개방과 같은 사이클에서** 반드시 동반. ⑤ 완화 착수 시 선결 항목으로 못박는다 |
| ⑦ | 필터 3종 최종 처분 | **켜지 않음 확정, 재검토는 기준 지수 교체 후** | 재무퀀트·RS·RSI 를 7전략 어디에도 실배제로 켜지 않는다. 관찰 훅(VB step7/8/9)은 비용 0이라 존치. 재검토 트리거 = RS 벤치마크(069500) 교체 후 재검정 |
| ⑧ | 다음 검증 예산 | **동의** | 순서 = 9시 기준가 → 손익비(청산 규약) → VCP 진입 조건 |

- 착수 순서(오늘 09-06 일요일, 장 마감·주말 자율 구간 안): ② 조사 → ② 임시 보류 사이클 → ④ 일봉 적재 시정 → ③ S0 관측 → ⑤ VCP 감사 자문. 월 09-07 기존 일정(cycle254 D+1 · 09:30 프로브 · D4 · 20:20 루틴 → 20:25 TLS 2단계)과 화 09-08(D10 · 수수료·세금)은 그대로 간다.
