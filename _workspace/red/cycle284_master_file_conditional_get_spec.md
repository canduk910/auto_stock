# cycle284 — 종목마스터 파일 **조건부 GET 게이트** (시계 기반 → 내용 기반)

> 상태: **명세만. 착수는 cycle283 병합 뒤.** 두 사이클 모두 `src/engine/scanner.py`(8영역)를
> 건드려 동시 진행 시 충돌 + sha 핀 churn 이 난다.
> 발의 = 2026-09-11 사용자 질문 "거래소에서 익일정보를 전부 한국투자증권에 보내서 반영됐는지
> 확인하는 방법은 없나?" → 있음이 실측으로 확인됨 → "별도 사이클로 올리자".

---

## 1. 발단 — 우리는 매일 **전날 판** 마스터를 쓰고 있다

KIS 종목마스터 파일(`kospi_code.mst.zip` / `kosdaq_code.mst.zip`)은 URL 에 날짜 파라미터가 없다.
KIS 가 "현재" 파일 하나를 주기적으로 재생성한다. 그 재생성 시각을 우리는 본 적이 없었다.

**2026-09-11(금) 23:0x 실측:**

| 측정 | 결과 |
|---|---|
| `last-modified` (양쪽 URL 동일) | `Fri, 11 Sep 2026 09:55:03 GMT` = **KST 18:55:03** |
| `If-Modified-Since: 2026-09-11 18:55` | **HTTP 304 · 0 bytes** |
| `If-Modified-Since: 2026-09-10 00:00` | HTTP 200 · 119,567 bytes |
| 우리 적재 시각 | `TIME_STOCK_MASTER_MASTER_LOAD = time(16, 30)` (`scheduler.py:68`) |

⇒ **갱신 2시간 25분 전에 받는다.** 16:30 적재가 가져오는 것은 *전날 18:55 판*이고,
그 값이 다음 영업일 매수 판정(`scanner._is_master_blocked_for_entry` 1단계 차단 7건)에 쓰인다.

### 오늘 기준 실제 손해는 0이었다 (1일 표본)

DB(09-11 16:30 적재분) vs 18:55 판, **3,549종목 전수 대조**:

| 플래그 | 불일치 |
|---|---|
| `trht_yn` 거래정지 | 0 |
| `mang_issu_yn` 관리종목 | 0 |
| `sltr_yn` 정리매매 | 0 |
| `mrkt_alrm_cls_code` 시장경고 | 0 |
| `ssts_hot_yn` 공매도과열 | 0 |
| `stange_runup_yn` 이상급등 | 0 |

**1일 표본이다.** "오늘은 차이가 없었다" 까지만 말할 수 있다. 지정·해제가 실제로 난 날엔
하루 늦게 반영된다. 이 사이클의 효과 크기는 §6 관측으로 사후 측정한다.

### 익일 상장 종목은 이 사이클로도 못 얻는다

같은 22:51 판(= 18:55 생성분)에 **상장일이 오늘 이후인 종목 0건**(KOSPI 2,580 / KOSDAQ 1,823 전수).
가장 최근 상장일이 09-10 이다. 즉 마스터 파일은 **상장일 당일부터** 그 종목을 담는다.
적재 시각을 어디로 옮겨도 익일 상장 종목은 안 들어온다 — 이 사이클의 목표가 아니다.

⚠️ **미확인**: 거래소가 심야·새벽에 익일 기준 마스터를 내려주고 KIS 가 **2차 갱신**을 하는지는
모른다. 23:02 까지는 18:55 판 그대로였다. §6 의 `last-modified` 기록이 이 질문을 자동으로 답한다.

---

## 2. 지금 구조의 문제 — 두 게이트가 **둘 다 시계 기반**이다

```
TIME_STOCK_MASTER_MASTER_LOAD = time(16, 30)          # scheduler.py:68
initial_delay_secs            = 720                   # data_load_tasks.py:177
immediate_skip_if_fresh_hours = IMMEDIATE_FRESH_SKIP_HOURS(=20.0)  # :178
```

- 파일이 언제 바뀌는지와 **무관하게** 16:30 에 받는다 → 항상 전날 판.
- 20시간 신선도 게이트는 *우리가 언제 받았는지*만 보고 *파일이 바뀌었는지*는 안 본다.
  그래서 **요일 비대칭**이 생긴다(부팅 07:55 + 720s = 08:07 기준):

| 요일 | 마지막 성공 → 08:07 | 판정 |
|---|---|---|
| 월 | 금 16:3x → 63.6h | 20h 초과 → immediate **실행** |
| 화~금 | 전일 16:3x → 15.6h | 20h 미만 → **skip** |

게이트의 원래 목적(cycle193)은 **프리마켓 burst 회피**다 — master 는 멱등 없이 매 run 전량
재작성이라 4분이 걸린다. 그 목적은 조건부 GET 이 **더 잘** 달성한다(안 바뀌었으면 0바이트).

---

## 3. 설계 — 내용 기반 게이트

### 3.1 핵심

```
적재 직전:  If-Modified-Since: <마지막으로 소비한 last-modified>
   304  →  skip (0 bytes). 마커 유지.
   200  →  적재. 응답의 last-modified 를 마커에 저장.
```

이러면 "몇 시에 받을까"가 **덜 중요해진다** — 아무 때나 물어도 공짜고, 바뀌었을 때만 4분이 돈다.

### 3.2 그래도 시각은 옮겨야 한다

조건부 GET 만으로는 부족하다. **16:30 에만 물으면 영원히 전날 판이다**(18:55 갱신을 지나치지
못한다). 갱신 이후에 최소 한 번은 물어야 한다.

**제안 = 16:30 → 20:40.** cycle283 이후 저녁 일정에서 이 자리가 비어 있다:

| 시각 | 작업 |
|---|---|
| 19:00~19:08 | 보조 토큰 강제 재발급 (7계정 × 61s) |
| 19:50 | NXT 애프터 매수 중단 |
| 20:00 | 거래 종료 · unsubscribe_all · AI 자문(~20:03) · **세션 기동 거부 경계**(cycle283) |
| 20:00:05 | 전체 유니버스 적재 |
| 20:05 | metrics 1차 저장 (cycle283) |
| 20:30~20:32 | 일봉 적재 (cycle283) |
| **20:40** | **← 마스터 적재 (이 사이클)** |
| 21:30 | 정산 (cycle283) |

18:55 갱신 뒤 1시간 45분, 일봉 적재 뒤, 정산 50분 전. 4분 소요라 20:44 종료.

⚠️ **18:55 가 규칙적이라는 근거는 1일 표본뿐이다.** 20:40 은 그 표본 기준 여유 1시간 45분이고,
설령 갱신이 늦어져도 조건부 GET 이 304 를 받아 **그날 skip 할 뿐 깨지지 않는다**(다음 날 아침
08:07 immediate 가 200 을 받아 따라잡는다 — 그게 아래 3.3 이다).

### 3.3 아침 immediate 는 살린다 (게이트 완화)

`immediate_skip_if_fresh_hours` 를 master task 에서 **제거**한다(또는 크게 완화).
근거 = 조건부 GET 이 그 자리를 대신한다.

- 아침 08:07: 조건부 GET → 전날 20:40 에 이미 받았으면 **304 · 0바이트 · skip**
- 20:40 이 어떤 이유로 실패했으면 → 200 → 아침에 따라잡는다 (**자기 치유**)
- 화~금 요일 비대칭이 자연히 사라진다

즉 프리마켓 burst 는 **평시 0**, 전날 실패한 날에만 4분. cycle193 의 목적을 더 정확히 달성한다.

---

## 4. 구현 계약 (초안 — 착수 시 domain-consult 로 확정)

- **M1** `src/api/kis_master.py::download_master_zip(url)` →
  `download_master_zip(url, *, if_modified_since: str | None = None) -> tuple[bytes | None, str | None]`.
  304 → `(None, None)`. 200 → `(zip_bytes, last_modified_header)`.
  기본값 `None` = **현행 무조건 다운로드와 byte 동일**(옵트인).
  SSL verify=True → ConnectError 폴백(cycle129 옵션 C)은 **불변**.
- **M2** `download_kospi_master()` / `download_kosdaq_master()` 에 같은 옵트인 전달.
- **M3** `src/engine/scanner.py::_stock_master_master_load_once` — **8영역, 승인 필요**.
  마커 조회 → 조건부 GET → 304 면 skip(+마커 유지) / 200 이면 현행 적재 경로 + 마커 갱신.
  **KOSPI·KOSDAQ 마커를 따로 둔다**(한쪽만 바뀔 수 있다).
  `force=True`(수동 `POST /api/stock-master/refresh-universe` 계열)는 **조건부 GET 을 건너뛴다**
  — 운영자의 수동 복구 경로를 캐시가 막으면 안 된다.
- **M4** 마커 저장 = `system_config` 신규 키 2개
  (`master_file_last_modified_kospi` / `_kosdaq`). `set_task_last_success` 인프라와 **별개**
  (그건 "언제 성공했나", 이건 "무엇을 소비했나").
- **M5** `scheduler.TIME_STOCK_MASTER_MASTER_LOAD` 16:30 → **20:40**.
- **M6** `data_load_tasks.stock_master_master_load_task_loop` 의
  `immediate_skip_if_fresh_hours` 제거(또는 완화). `initial_delay_secs=720` 은 재검토
  (20:40 로 옮기면 stagger 근거였던 "basics 16:10 후 20분"이 무의미).
- **M7** fail-open — 헤더 파싱 실패·마커 손상·304 오판 의심은 전부 **현행 동작(무조건 다운로드)**
  으로 낙하한다. 캐시가 적재를 막는 방향의 실패는 금지(P0-1 유령 키 계열).

---

## 5. 제약

- **8영역 = `scanner.py` 단독** → 사용자 승인 필요. sha 핀 4곳 동시 갱신 의무
  (`test_cycle222a3_ast_followup_fixes.py` · `test_cycle223_ast_donchian_exit_fix.py` ·
  `test_cycle223f_ast_manual_apply_safeguard.py` · `test_cycle226_zero_breakout_defense.py`).
- **cycle283 병합 뒤 착수** — 같은 파일을 건드린다.
- `scheduler.py` 라인 상한 < 4,000L.
- 매매 행위 영향 = **간접**. 마스터가 하루 빨라지면 `_is_master_blocked_for_entry` 의 1단계 차단
  7건이 하루 일찍 걸린다 ⇒ **매수가 줄어드는 방향**. `domain-consult` 선행 대상이다.

---

## 6. 이 사이클의 부수 효과 = 측정기

관측 마커에 `last_modified` 를 **매일 기록**한다:

```
[master_file_check] kospi_modified=Y|N kosdaq_modified=Y|N
                    kospi_last_modified=<헤더> kosdaq_last_modified=<헤더>
                    action=load|skip elapsed_ms=
```

이 한 줄이 **미해결 질문 둘을 자동으로 답한다**:

1. **18:55 가 규칙적인가** — 며칠치 헤더를 모으면 바로 보인다.
2. **심야·새벽 2차 갱신이 있는가** — 아침 08:07 조건부 GET 이 200 을 받으면 그게 증거다
   (20:40 에 이미 받았는데 아침에 또 바뀌었다면 = 야간에 재생성됐다는 뜻).
   2차 갱신이 실재하고 거기에 **익일 상장 종목**이 들어온다면, §1 의 "못 얻는다" 결론이
   뒤집힌다. 그때는 별도 사이클로 아침 적재를 정식 배선한다.

---

## 7. 범위 밖

- **익일 상장 종목 사전 확보** — `HHKDB669107C0`(상장정보일정)은 추가상장 중심이고,
  `HHKDB669108C0`(공모주청약일정)은 `list_dt` 가 비고 `sht_cd` 가 임시 코드다(실측 확인).
  상장 전에 정규 6자리 코드 + 상장일을 확정적으로 주는 KIS 경로는 확인되지 않았다.
  실효도 낮다 — 7전략 중 6개가 prepare 에서 일봉 22~100일을 요구해 신규 상장 종목은
  구조적으로 후보가 못 된다(momentum 만 일봉 0건이나 상장일엔 전일종가가 없다).
- `basics`(16:10) · `financial`(16:40) 의 시각·게이트 — 이 사이클은 master 만 다룬다.
