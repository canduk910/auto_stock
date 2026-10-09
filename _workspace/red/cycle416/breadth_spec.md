# cycle416 「매크로 화면 시장 등락 통계」 — 도메인 명세

작성: domain-expert (2026-10-09 KST) · 브랜치 `feat/market-breadth` · 기준 `main 3d6f7b52`
사용자 요청 원문: 10-07 「전일까지 최근 20영업일의 일별 상장종목 중 상승/하락/상한가/하한가 종목수를 통계를 내는 화면을 매크로에 넣고 싶은데」 → 10-09 「시장등락 통계 만들자」
메인 세션 기본값(사용자가 고르지 않은 것): 시장 = 코스피·코스닥 각각 + 합계 · 보합 종목 수와 상승 비율도 보여 준다.

이 문서는 tdd-engineer(Red) · backend-dev · frontend-dev 가 그대로 옮길 수 있게 **결정만** 적는다. 고를 것이 남은 곳은 없다.

---

## 0. 결정 한눈에

| # | 항목 | 결정 |
|---|---|---|
| 1 | 날짜 창 | 오늘(KST) 제외, 어제부터 평일을 거꾸로. 빈 응답 평일 = 휴장(칸 안 씀). 단 **가장 최근 평일이 비었고 지금이 그 다음 평일 10:00 KST 전**이면 「아직 없음」(`pending_date`). 거슬러 보는 한도 = `max(40, 2 × days)` 달력일 |
| 2 | 종목 분류 | 거래량 0 → 「거래 없음」(먼저 뺀다). 나머지는 `CMPPREVDD_PRC` 부호로 상승·하락·보합. 상·하한가 = **(가) KRX 가격제한폭 계산값과 종가가 같고, 그날 고가·저가가 제한폭 안**. (나) 등락률 29.5% 규칙은 쓰지 않는다 |
| 3 | 집계 | 날짜마다 시장별 `{rows, traded, up, down, flat, limit_up, limit_down, no_trade, out_of_band, unparsed, up_ratio}`. 합계 = 코스피+코스닥 합. 요약 ADR = Σ상승 ÷ Σ하락 × 100. 기준선 75·120 (판정 문구 없음) |
| 4 | API | `GET /api/market/breadth?days=20` (1~60). 실패도 **HTTP 200 + `success=false`**, 인자 위반만 422 (cycle387 `stock_chart` 관례) |
| 5 | 계산 위치·캐시 | 순수 leaf `src/engine/market_breadth.py` + 라우트 `src/routes/market_breadth.py`. 캐시 = 프로세스 메모리 `(시장, 날짜)` → 집계값. 동시 4 · 전체 45초 · 같은 키 중복 호출 합치기 · 하루 KRX 호출 상한 1,000 |
| 6 | 화면 | 매크로 화면 6번째 섹션 「시장 등락 통계」 — 시장 토글 · 상승(빨강, 위)/하락(파랑, 아래) 막대 · 상승 비율 선 · 상·하한가 숫자 · 요약 칩 · 날짜별 표 |
| 7 | 검증 | 10-08 실측 숫자를 그대로 재현하는 합성 픽스처 + 실제 KRX 과거 사례로 만든 경계 픽스처 11건 |

---

## 1. 트레이더 시각 — 왜 이 화면이 필요한가

- **지수는 거짓말을 한다, 종목 수는 덜 한다.** 코스피는 삼성전자·SK하이닉스 두 종목이 시총의 상당 부분이라 지수가 올라도 대부분 종목이 빠지는 날이 흔하다. 장 끝난 뒤 「오늘 시장 체력」 을 보는 가장 단순한 잣대가 상승·하락 종목 수와 상승 비율이다. 지수 +1% 인데 상승 비율 30%대면 「대형주 쏠림 · 중소형 체력 고갈」 로 읽는다.
- **상한가 수 = 투기 온도, 하한가 수 = 패닉 온도.** 2023-01-25 ~ 2025-10-02(659일) KRX 원자료로 잰 값: 하루·시장당 상한가 평균 **2.7개**, 최대 **16개**(2024-12-10·11 코스닥). 하한가 평균 **0.26개** — 하한가가 여러 개 나오는 날은 드물고 그 자체가 사건이다(2023-04-24 코스피 5개 = SG증권발 반대매매, 2024-05-17 코스닥 7개).
- **20일 등락비율(ADR)** 은 하루 노이즈를 걷은 체력 지표다. 업계 통상 기준선은 **120 이상 과열권 · 75 이하 바닥(침체)권**(일부 자료는 70)이다 — 출처: [브릿지경제 2025-05-19](https://www.viva100.com/article/20250519500805) · [에너지경제 2023-10-24](https://www.ekn.kr/web/view.php?key=20231024010006195) · [미우트리 「ADR 지표로 지수바닥을 확인할 수 있다?」](https://blog.miutree.com/11).
- **100 은 중립이 아니다.** 이 문서의 집계 방식(우선주·스팩·리츠 포함, 거래 없음 제외)으로 KRX 보관소(2020-10-05 ~ 2025-10-02, 20일 창 1,210개)를 잰 분포:

  | 시장 | p5 | p25 | 중앙값 | p75 | p95 | 75 미만 비율 | 70 미만 | 120 초과 |
  |---|---|---|---|---|---|---|---|---|
  | 코스피 | 67.9 | 80.4 | **91.9** | 105.5 | 127.2 | 14.3% | 6.8% | 9.4% |
  | 코스닥 | 66.7 | 77.6 | **88.1** | 98.2 | 118.1 | 18.8% | 9.2% | 4.0% |
  | 합계 | 67.6 | 78.7 | **89.4** | 100.1 | 121.2 | 16.0% | 7.5% | 5.3% |

  하락 종목이 구조적으로 더 많다(소형주 감가). 화면은 기준선만 그리고, 이 중앙값은 각주 한 줄로만 둔다(§6.4).
- **이 화면은 관찰 전용이다.** 매매 엔진·전략·매수 가드 어디에서도 읽지 않는다(매크로 레짐이 관찰 지표인 것과 같은 자리). 매매 행위 변경 0.

---

## 2. 날짜 창 (task 항목 1)

### 2.1 정의

```
today   = src.db._kst.today_kst()            # 오늘(KST). 언제나 제외한다 — 「전일까지」
now     = datetime.now(KST)
L       = max(40, 2 * days)                  # 거슬러 보는 한도(달력일). days=20 → 40, days=60 → 120
후보    = [today-1, today-2, ..., today-L] 중 평일(월~금)만, 최신 먼저
```

후보 날짜 d 하나를 KRX 두 시장에 물어 아래 넷 중 하나로 판정한다.

| 판정 | 조건 | 창의 칸을 쓰나 | 응답에 남는 자리 |
|---|---|---|---|
| `TRADING` | 두 시장 모두 「유효 행」 ≥ 1 | 쓴다 | `days[]` |
| `EMPTY` | 두 시장 모두 유효 행 0 (빈 배열, 또는 행은 있으나 전부 판독 불가) | 안 쓴다 | `pending_date` 또는 `empty_dates[]` |
| `MISSING` | 한 시장이라도 호출 실패(재시도 뒤)·시간 초과·호출 상한, 또는 한 시장만 비고 다른 시장은 유효 | **쓴다** | `missing_dates[]` |
| (조회 안 함) | 주말 | — | — |

- **칸 채우기**: 최신 후보부터 `TRADING`·`MISSING` 을 칸으로 세어 `days` 개가 되면 멈춘다. 한도 `L` 안에서 다 못 채우면 있는 만큼 돌려주고 `window.complete=false`.
- `MISSING` 이 칸을 쓰는 이유 — 평일에 응답이 「실패」 한 것은 휴장의 증거가 아니다. 칸을 안 쓰면 창이 하루 더 과거로 밀려 「최근 20영업일」 이 조용히 바뀐다. 구멍은 구멍으로 보여 준다.
- 「유효 행」 = §3.1 의 `unparsed` 가 아닌 행. 행이 1개 이상인데 유효 행이 0 이면 `EMPTY` 로 보고 `[market_breadth_all_unparsed]` WARNING 을 남긴다(KRX ETF API 는 휴장일에 가격 칸이 빈 종목 목록을 준 전례가 있다 — `_workspace/domain_consult/cycle383_krx_etf_archive_build.md`).

### 2.2 「아직 없음」 과 「휴장」 의 구분 — 정의 하나

KRX 공개 API 는 그날 자료를 **다음 날 오전 8시** 에 올린다고 안내한다([KRX OPEN API 서비스 목록](https://openapi.krx.co.kr/contents/OPP/INFO/service/OPPINFO004.cmd)). 리포의 `scanner._full_universe_load_krx_primary` 주석은 「~16:00 가용」 이라고 적어 두 출처가 어긋난다. 아래 정의는 둘 중 무엇이 맞아도 틀리지 않게 잡았다.

```
d1 = 후보의 첫 평일(= 오늘 이전 가장 최근 평일)
NW(d) = d 다음의 첫 평일
pending ⇔ d == d1  ∧  판정(d) == EMPTY  ∧  now < NW(d1) 10:00 KST
```

- pending 이면 `pending_date = d1`, 아니면 `EMPTY` 평일은 전부 휴장으로 `empty_dates[]` 에 넣는다.
- **칸 계산은 이 구분과 무관하다** — pending 도 휴장도 칸을 쓰지 않는다. 구분은 화면 안내문 하나에만 쓰인다. 그래서 휴장을 pending 으로(또는 반대로) 잘못 붙여도 숫자는 틀리지 않는다.
- 10:00 = KRX 안내 08:00 + 여유 2시간.
- 주말 예: 오늘 일요일, d1 = 금요일이 비었으면 NW = 월요일 → 월요일 10:00 까지 pending. 금요일이 실제 휴장이었다면 주말 내내 「아직 없음(미게시 또는 휴장)」 으로 보인다 — 안내문을 그렇게 쓴다(§6.3).
- 빈 응답 캐시는 짧게 둔다(§5.3) — 늦게 올라온 자료는 다음 조회에서 저절로 들어온다.

### 2.3 예시 (테스트 W1 과 같은 꼴 — 휴장일은 합성)

오늘 = 2026-10-09(금) 11:00, 가짜 KRX 가 `10-05 · 09-25 · 09-24` 만 빈 배열을 준다고 하면:
칸 = 10-08, 10-07, 10-06, 10-02, 10-01, 09-30, 09-29, 09-28, 09-23, 09-22, 09-21, 09-18, 09-17, 09-16, 09-15, 09-14, 09-11, 09-10, 09-09, **09-08** → `window.from=2026-09-08`, `to=2026-10-08`, `empty_dates=[2026-10-05, 2026-09-25, 2026-09-24]`, `pending_date=null`.
실제 휴장 판정은 **KRX 응답으로만** 한다(휴장 달력 하드코딩 금지 — 대체공휴일·임시공휴일이 해마다 바뀐다).

---

## 3. 종목 분류 (task 항목 2)

### 3.1 숫자 읽기

`parse_krx_int(v)`: `None`·`""`·`"-"`·공백 → `None`. 그 밖에는 앞뒤 공백 제거 → 쉼표 제거 → `Decimal` → 정수가 아니면 `None`, 정수면 `int`. 예: `"1,234,500"` → `1234500`, `"-1,500"` → `-1500`, `"12.5"` → `None`.

행에서 쓰는 키: `TDD_CLSPRC` · `CMPPREVDD_PRC` · `ACC_TRDVOL` · `TDD_HGPRC` · `TDD_LWPRC` (+ 교차확인용 `FLUC_RT`).

- **`unparsed`**(집계에서 뺀다): `TDD_CLSPRC` 가 `None` 또는 ≤ 0 · `CMPPREVDD_PRC` 가 `None` · `ACC_TRDVOL` 이 `None` 또는 < 0.
- `CMPPREVDD_PRC` 는 **부호가 있는 값**이다 — KRX 보관소 원자료에 음수가 그대로 있다(예: CJ 2010-01-04 `-500`). 테스트 `tests/unit/engine/scanner/test_cycle119_krx_kis_key_mapping.py` 도 `"-1,500"` 을 쓴다.

### 3.2 분류 순서 (위에서부터 처음 맞는 것)

| 순서 | 조건 | 분류 |
|---|---|---|
| 1 | §3.1 판독 불가 | `unparsed` (어디에도 안 센다) |
| 2 | `ACC_TRDVOL == 0` | `no_trade` (상승·하락·보합에서 뺀다) |
| 3 | `CMPPREVDD_PRC > 0` | `up` |
| 4 | `CMPPREVDD_PRC < 0` | `down` |
| 5 | `CMPPREVDD_PRC == 0` | `flat` |

- 2번이 3~5번보다 **먼저**다. 근거: 2023-01-25 ~ 2025-10-02 거래량 0 행 62,693개 중 **47개는 전일대비가 0 이 아니다**(예: 하이트진로홀딩스우 2023-09-08 거래량 0 · 전일대비 `-10`). 체결 없이 기준가만 바뀐 날(배당락·권리락)이다 — 이것을 「하락」 으로 세면 안 된다.
- 거래 없음 행의 모양(보관소 실측): 시가·고가·저가 `0`, 종가 = 기준가. 하루 평균 코스피 **16개** · 코스닥 **77개**.

### 3.3 상한가·하한가 — (가) 를 고른다

상·하한은 `up`·`down` 의 **부분집합**이다(`limit_up` ⊂ `up`, `limit_down` ⊂ `down`).

**정의 (가′ = (가) + 제한폭 안 확인)** — 정수 산술만 쓴다.

```
base = TDD_CLSPRC − CMPPREVDD_PRC                       # 그날 기준가 (권리락·배당락 반영된 값)
tick(p): p < 2,000 → 1 · < 5,000 → 5 · < 20,000 → 10 · < 50,000 → 50
         < 200,000 → 100 · < 500,000 → 500 · 그 이상 → 1,000      # 2023-01-25 호가가격단위 (코스피·코스닥 공통)
w      = ((base * 30) // 100) // tick(base) * tick(base)  # 제한폭 = 기준가 30%, 기준가의 호가단위 미만 절사
upper  = (base + w) // tick(base + w) * tick(base + w)    # 상한가: 그 가격대의 호가단위로 한 번 더 절사
lower  = base − w                                         # 하한가: 추가 절사 없음
in_band = (TDD_LWPRC >= lower) and (TDD_HGPRC <= upper)   # 그날이 ±30% 제한폭이 걸린 보통의 날이었나

limit_up   ⇔ kind == up   ∧ in_band ∧ TDD_CLSPRC == upper
limit_down ⇔ kind == down ∧ in_band ∧ TDD_CLSPRC == lower
out_of_band ⇔ kind ∈ {up, down, flat} ∧ base > 0 ∧ TDD_HGPRC > 0 ∧ TDD_LWPRC > 0 ∧ not in_band
```

- `base ≤ 0` 이거나 거래가 있는데 고가·저가가 0 인 행(보관소 659일에 3개)은 상·하한 판정을 건너뛴다(방향 분류는 그대로).
- `out_of_band` 는 「그날 제한폭이 ±30% 가 아니었던 종목」(신규상장일 60~400%, 정리매매 무제한, 변경상장 등) 수다. 상승·하락에는 그대로 들어가고 상·하한가에는 들어가지 않는다. 하루·시장당 평균 0.3개, 최대 5개.

**왜 상한과 하한의 절사가 다른가** — 보관소 실측으로 확정했다(아래 표). 상한가는 위쪽 호가대로 넘어가면 그 호가단위로 다시 깎이고(기준가 15,800 → 20,540 이 아니라 **20,500**), 하한가는 기준가 호가단위로만 깎인다(기준가 244,000 → 170,800 이 아니라 **171,000** — 2023-04-26 삼천리, 시고저종이 모두 171,000 인 잠긴 하한가).

**실측 비교 (KRX 보관소 2023-01-25 ~ 2025-10-02, 659일, 거래 있는 1,766,929행 중)**

| 규칙 | 상한가 | 하한가 | 비고 |
|---|---|---|---|
| (가′) 위 정의 | 3,594 | 337 | |
| (나) 등락률 ≥ +29.5% ∧ 종가 = 고가 (하한 대칭) | 3,617 | 399 | |
| (나) 만 맞다고 한 것 | 29 | 65 | 전부 (나) 의 오판: ① 한도 1~3호가 **아래**에서 고가로 끝난 날 12건(덕성 2023-08-07 11,900 — 상한가 11,930) ② 신규상장일·정리매매 17건(시큐레터 상장일 +102.5% · 에코바이브 정리매매 −97.7%) · 하한 쪽 60건이 정리매매 류 |
| (가′) 만 맞다고 한 것 | 6 | 3 | 상한 6 = 동전주의 진짜 상한가(골든센츄리 82 → 106 = +29.27% — 1원 단위 절사 때문에 29.5% 에 못 미친다), 하한 3 = 정리매매 동전주가 계산 하한가와 우연히 같은 값 |

→ (나) 는 20일 창마다 평균 약 3건을 잘못 세고(특히 정리매매 폭락을 하한가로), (가′) 는 1년에 몇 건 수준이다. **(가′) 로 정한다.**

**(가′) 의 한계 (알고 받아들이는 것)**
- 신규상장일(2023-06-26 이후 공모가 기준 60~400%)의 진짜 상한가(「따따블」, 예: DS단석 2023-12-22 +300%)는 `out_of_band` 로 가고 상한가로 세지 않는다. 1년에 몇 건.
- 정리매매 동전주가 계산 하한가 값에 우연히 닫히면 하한가로 센다(659일에 3건).
- 호가가격단위표가 바뀌면 `tick()` 을 바꿔야 한다. 상수 이름에 시행일을 박는다: `KRX_TICK_TABLE_20230125`.
- ETF·ETN·코넥스는 `stk_bydd_trd`/`ksq_bydd_trd` 응답에 없다 — 이 통계 밖이다. 우선주·스팩·리츠·외국주권은 들어 있다(사용자 원문 「상장종목 중」 그대로 — 따로 거르지 않는다).

### 3.4 부호 교차확인 (행위 무변경, 로그만)

`FLUC_RT` 가 읽히는 행에서 `sign(CMPPREVDD_PRC) != sign(FLUC_RT)` 인 수를 센다. 0 보다 크면 시장·날짜마다 `[market_breadth_sign_mismatch] market= date= n=` WARNING 한 줄. 분류는 바꾸지 않는다(KRX 가 대비 부호를 빼고 보내기 시작하는 식의 응답 모양 변화를 잡는 덫이다).

---

## 4. 집계 (task 항목 3)

### 4.1 하루·시장 하나 (`DayStats`)

| 키 | 뜻 |
|---|---|
| `rows` | 유효 행 수 = `up + down + flat + no_trade` (`unparsed` 제외) |
| `traded` | `up + down + flat` |
| `up` · `down` · `flat` | §3.2 |
| `limit_up` · `limit_down` | §3.3 (각각 `up`·`down` 의 부분집합) |
| `no_trade` | 거래량 0 |
| `out_of_band` | §3.3 (참고값) |
| `unparsed` | 판독 불가 행 (보통 0 — 0 이 아니면 응답 모양을 의심한다) |
| `up_ratio` | `up / traded`, 4자리 반올림(`round(x, 4)`), `traded == 0` 이면 `null` |

합계(`total`) = 코스피와 코스닥의 정수 키를 더한 뒤 `up_ratio` 를 **합계 숫자로 다시 계산**한다(두 비율의 평균이 아니다).

### 4.2 요약 (`summary.kospi|kosdaq|total`)

| 키 | 뜻 |
|---|---|
| `n_days` | `days[]` 에 들어간 날 수 (`MISSING` 제외) |
| `up` · `down` · `flat` · `limit_up` · `limit_down` · `no_trade` | 그 날들의 합 |
| `up_ratio` | `Σup / Σtraded`, 4자리 |
| `adr` | `Σup / Σdown × 100`, 1자리 반올림, `Σdown == 0` 이면 `null` |

- ADR 은 「n_days 일 ADR」 이다. `n_days < requested` 면 화면이 「ADR(18일)」 처럼 일수를 붙인다.
- 기준선은 상수 `ADR_REFERENCE = {"oversold": 75, "overheated": 120}` 로 leaf 에 두고 응답에 실어 보낸다(화면이 숫자를 따로 갖지 않게). 판정 문구(「과열입니다」 등)는 어디에도 쓰지 않는다.

---

## 5. API · 계산 위치 · 캐시 (task 항목 4·5)

### 5.1 순수 leaf — `src/engine/market_breadth.py`

`await`·DB·HTTP·`asyncio`·`logging` 없음. import 는 표준 라이브러리(`dataclasses`·`datetime`·`decimal`·`typing`)만.

| 이름 | 하는 일 |
|---|---|
| `KRX_TICK_TABLE_20230125` · `PRICE_LIMIT_PCT = 30` · `ADR_REFERENCE` | 상수 |
| `DEFAULT_DAYS = 20` · `MIN_DAYS = 1` · `MAX_DAYS = 60` · `MIN_LOOKBACK_CALENDAR_DAYS = 40` · `PUBLISH_PENDING_CUTOFF = time(10, 0)` | 상수 |
| `tick_size(price) -> int` | §3.3 |
| `price_limits(base) -> tuple[int, int]` | `(upper, lower)` |
| `parse_krx_int(v) -> int | None` | §3.1 |
| `classify_row(row) -> RowClass` | `kind` ∈ {`unparsed`,`no_trade`,`up`,`down`,`flat`} + `limit_up`·`limit_down`·`out_of_band`·`sign_mismatch` (bool) |
| `aggregate_rows(rows) -> DayStats` | §4.1 + `sign_mismatch` 수(응답에는 안 싣는다) |
| `merge_stats(a, b) -> DayStats` | 합계 |
| `summarize(days) -> SummaryStats` | §4.2 |
| `lookback_calendar_days(days) -> int` | `max(40, 2 * days)` |
| `candidate_weekdays(today, days) -> list[date]` | §2.1, 최신 먼저 |
| `next_weekday(d) -> date` · `is_publish_pending(d, d1, now) -> bool` | §2.2 |
| `classify_day(kospi, kosdaq) -> DayStatus` | §2.1 표 (`TRADING`/`EMPTY`/`MISSING`) |
| `stats_to_dict(...)` | 응답 dict 직렬화 (키 이름 = §5.4) |

### 5.2 라우트 — `src/routes/market_breadth.py`

- `router = APIRouter(prefix="/api/market", tags=["market-breadth"])`, `GET /breadth`, `days: int = Query(20, ge=1, le=60)`. `src/main.py` 에 `include_router` 한 줄.
- 🔴 경로를 `/api/macro/...` 아래에 두지 않는다 — nginx `location /api/macro/` 와 vite 프록시가 그 접두사를 **macro 컨테이너**로 보낸다. `/api/market/breadth` 는 `location /api/` → backend 로 간다(기존 `/api/market-state`·`/api/market-ops`·`/api/market-regime` 와 접두사가 겹치지 않는다).
- KRX 호출은 **모듈 참조**로 한다: `from src.api import krx` → `krx.fetch_stk_bydd_trd(ymd)` · `krx.fetch_ksq_bydd_trd(ymd)` (테스트가 `src.api.krx.fetch_*` 를 갈아끼우는 seam — cycle387 `stock_chart` 와 같은 꼴). `src/api/krx.py` 는 한 글자도 고치지 않는다.
- 설정 사전 확인: 첫 KRX 호출 전에 `system_config.get_krx_open_api_config()` 를 한 번 읽어 `enabled=False` 또는 `key` 빈 값이면 KRX 를 부르지 않고 `success=false`(§5.5). 키 값은 변수에만 머문다 — 로그·응답·예외 메시지에 넣지 않는다.

상수(라우트 모듈):

| 상수 | 값 | 이유 |
|---|---|---|
| `_KRX_CONCURRENCY` | 4 | KRX 동시 호출 상한(전역 `asyncio.Semaphore`) |
| `_REQUEST_DEADLINE_SECS` | 45.0 | nginx `location /api/` 기본 `proxy_read_timeout` 60초 안 |
| `_RETRY_DELAY_SECS` | 1.0 | 호출 실패 시 1회 재시도 전 대기 |
| `_EMPTY_TTL_SECS` | 600 | 최근 빈 응답 캐시 수명 (§5.3) |
| `_EMPTY_PERMANENT_AFTER_DAYS` | 7 | `d < today − 7` 인 빈 응답은 영구 캐시 |
| `_DAILY_CALL_BUDGET` | 1,000 | 이 라우트의 KST 하루 KRX 호출 상한 (§5.3) |
| `_CACHE_MAX_ENTRIES` | 512 | 넘으면 날짜가 가장 오래된 것부터 버린다 |

### 5.3 캐시·동시성·한도

- **캐시 키** = `(market, "YYYYMMDD")`, 값 = `("ok", DayStats)` 또는 `("empty", None)`. 원자료 행은 담지 않는다(집계값만 — 수백 바이트).
  - `ok` → 영구(지난 날짜의 일별 매매정보는 바뀌지 않는다).
  - `empty` → `d < today − 7` 이면 영구, 그보다 최근이면 600초.
  - 실패(`KrxApiError`·기타 예외·시간 초과·한도) → **캐시하지 않는다**(다음 조회에서 다시 시도).
  - 프로세스 메모리라 재시작·배포 때 비워진다. 규칙을 바꾼 배포가 옛 집계를 들고 있을 일이 없다.
- **같은 키 중복 호출 합치기**: 진행 중 표 `dict[(market, ymd)] -> asyncio.Task`. 같은 키를 원하는 요청은 새로 부르지 않고 그 태스크를 `asyncio.shield` 로 기다린다. 끝나면 표에서 뺀다.
- **호출 한 건** = 세마포어 안에서 `krx.fetch_*` → 실패면 1초 뒤 1회 재시도 → 그래도 실패면 `[market_breadth_fetch_error] market=<kospi|kosdaq> date=<YYYY-MM-DD> err=<예외 클래스 이름>` WARNING. 예외 메시지 본문은 응답에 싣지 않는다.
- **전체 45초**: 요청 시작부터 잰다. 시간 안에 안 끝난 날짜는 `MISSING`(사유 `timeout`)으로 응답하되, **진행 중 태스크는 취소하지 않는다** — 끝까지 돌아 캐시를 채우므로 다음 조회가 빨라진다.
- **배치로 부른다**: 후보 전체를 한꺼번에 부르지 않는다. 첫 배치 = 남은 칸 수 + 2개 평일, 칸이 덜 차면 다음 배치(남은 칸 + 2). 한 배치 안은 최신 날짜부터 세마포어에 넣는다.
- **하루 호출 상한 1,000**: 실제 KRX 호출(재시도 포함)마다 KST 날짜별 카운터를 올린다. 상한에 닿으면 새 호출 없이 그 날짜는 `MISSING`(사유 `budget`), `[market_breadth_budget_exhausted]` WARNING 은 하루 1번.
  - 이유: 같은 KRX 키를 `scanner._full_universe_load_krx_primary`(전 종목 유니버스 적재)가 쓴다. 키의 하루 한도 10,000 이 마르면 유니버스 적재가 KIS 폴백으로 밀려 **매매 후보가 줄어든다**(2026-08-08 3,577→60 사고와 같은 경로). 이 화면이 매매를 해치지 않게 키 한도의 10% 로 묶는다. 카운터는 프로세스 메모리라 재시작 때 0 이 된다 — 한 프로세스 안의 폭주(캐시 결함·반복 호출)를 막는 것이 목적이다.
- **끝 로그**: `[market_breadth_done] days=<요청> n_days=<채운 날> missing=<n> pending=<YYYY-MM-DD|-> calls=<이번 요청의 새 호출 수> elapsed_ms=<n>` INFO.

**첫 호출 예상 시간** — 근거: 보관소 수집이 EC2 backend 컨테이너에서 2,622콜을 호출 간 0.7초 쉼 포함 60.8분에 마쳤다 → 호출당 약 **0.7초**.

| 상황 | 새 호출 수 | 예상 |
|---|---|---|
| 재시작 뒤 첫 `days=20` | 약 44~56 | 동시 4 → 약 **10~20초** |
| 재시작 뒤 첫 `days=60` | 약 130~170 | 약 25~60초 → 45초에 걸리면 일부 `timeout` 으로 먼저 보이고, 다시 열면 캐시로 채워진다 |
| 캐시가 찬 뒤 | 0~6 (최근 빈 날 재확인 + 새로 올라온 전일) | 1~5초 |

메모리: 코스닥 응답 1건 ≈ 1,800행 × 15키 — 파싱 중 수 MB, 동시 4건이라도 수십 MB 안. 집계가 끝나면 원자료는 버린다.

### 5.4 응답 모양 (`ApiResponse{success, data, message}` 의 `data`)

```json
{
  "asof_kst": "2026-10-09T11:00:03+09:00",
  "window": {
    "from": "2026-09-08", "to": "2026-10-08",
    "n_days": 20, "requested": 20, "complete": true,
    "lookback_from": "2026-08-30"
  },
  "days": [
    {
      "date": "2026-10-08",
      "kospi":  {"rows": 942, "traded": 927, "up": 252, "down": 625, "flat": 50,
                 "limit_up": 3, "limit_down": 0, "no_trade": 15,
                 "out_of_band": 0, "unparsed": 0, "up_ratio": 0.2718},
      "kosdaq": {"...": "같은 키"},
      "total":  {"...": "같은 키"}
    }
  ],
  "summary": {
    "kospi":  {"n_days": 20, "up": 0, "down": 0, "flat": 0, "limit_up": 0, "limit_down": 0,
               "no_trade": 0, "up_ratio": 0.0, "adr": 0.0},
    "kosdaq": {"...": "같은 키"},
    "total":  {"...": "같은 키"}
  },
  "adr_reference": {"oversold": 75, "overheated": 120},
  "source": "KRX 공개 API 일별 매매정보(유가증권·코스닥)",
  "missing_dates": ["2026-09-30"],
  "empty_dates": ["2026-10-05"],
  "pending_date": null
}
```

- `days[]` = **최신 날짜 먼저**. `date` 는 `YYYY-MM-DD`(KST 날짜 그대로). `asof_kst` 는 `+09:00` 붙은 ISO.
- `window.from`/`to` = `days[]` 와 `missing_dates[]` 를 합친 칸의 가장 오래된·최신 날짜. 칸이 0 이면 둘 다 `null`.
- `window.complete` = `n_days == requested`(빠진 날이 있거나 한도 안에서 못 채우면 `false`).
- `window.lookback_from` = `today − L` (거슬러 본 끝).
- `missing_dates[]` 는 날짜 문자열만 담는다(사유는 로그에). 최신 먼저.
- `empty_dates[]` = 휴장으로 본 평일, 최신 먼저.

### 5.5 실패·부분 성공 (HTTP 상태 = 200 고정, 인자 위반만 422)

관례 근거: `src/routes/stock_chart.py`(cycle387) — 외부 조회 실패는 HTTP 200 + `success=false`, 쿼리 범위 위반만 FastAPI 422. 프론트는 `frontend/src/api/stock-chart.ts` 처럼 `success=false` 를 `Error(message)` 로 바꾼다.

| 상황 | success | data | message (그대로 화면에 나간다) |
|---|---|---|---|
| KRX 공개 API 꺼짐 | false | null | 「KRX 공개 API 가 꺼져 있어 시장 등락 통계를 만들 수 없습니다 — 설정 화면의 외부 연동에서 켤 수 있습니다」 |
| 키 없음 | false | null | 「KRX 공개 API 키가 등록돼 있지 않아 시장 등락 통계를 만들 수 없습니다」 |
| 설정 읽기 실패(DB 예외) | false | null | 「KRX 연동 설정을 읽지 못했습니다 — 서버 로그 [market_breadth_error] 확인」 |
| 칸이 1개 이상 있는데 `n_days == 0` (전부 실패) | false | null | 「KRX 에서 자료를 받지 못했습니다 — 잠시 후 다시 시도하세요」 |
| 한도에 걸려 `n_days == 0` | false | null | 「오늘 이 화면의 KRX 조회 한도를 다 썼습니다 — 내일 다시 볼 수 있습니다」 |
| 한도 안에 평일 자료가 하나도 없음(전부 빈 응답) | false | null | 「최근 {L}일 안에 KRX 자료가 없습니다」 |
| 정상 | true | §5.4 | 「최근 {n}영업일 ({from}~{to})」 |
| 일부 빠짐 | true | §5.4 | 「최근 {n}영업일 ({from}~{to}) — {k}일은 KRX 응답이 없어 비었습니다」 |

- 예외는 라우트 밖으로 새지 않는다(`except Exception` → `[market_breadth_error] stage=<…> err=<클래스>` WARNING + 위 표의 문장). 500 을 내지 않는다.

---

## 6. 화면 (task 항목 6)

### 6.1 파일

| 파일 | 내용 |
|---|---|
| `frontend/src/types/market-breadth.ts` | `BreadthMarketKey = 'kospi' \| 'kosdaq' \| 'total'` · `BreadthDayStats` · `BreadthSummary` · `BreadthDay` · `MarketBreadthData` (키 이름 = §5.4 그대로) |
| `frontend/src/api/market-breadth.ts` | `getMarketBreadth(days = 20)` — `apiClient.get<ApiResponse<MarketBreadthData \| null>>('/market/breadth', { params: { days }, timeout: 60_000 })`, `success=false` 면 `throw new Error(message)`. 🔴 `timeout` 을 빼면 `apiClient` 기본 10초에 첫 조회가 잘린다 |
| `frontend/src/macro/hooks/useMarketBreadth.ts` | `useAsyncState` 꼴 그대로 (`useMacro.ts` 는 원본 이식 파일이라 손대지 않는다) |
| `frontend/src/macro/components/MarketBreadthSection.tsx` | 섹션 본체 |
| `frontend/src/macro/MacroPage.tsx` | 원자재 다음에 6번째로 넣고 mount 때 `load()`. 「5개 섹션 순서는 원본과 동일」 주석 옆에 「6번째는 우리 것(cycle416)」 한 줄 |

차트 = `recharts`(이미 의존성, `CreditSpreadSection`·`YieldCurveSection` 이 `ComposedChart` 사용). 새 의존성 0. 색은 기존 매크로 섹션처럼 CSS 변수: 상승 `var(--color-red-500)` · 하락 `var(--color-blue-500)` · 상승 비율 선 `var(--color-gray-700)` · 기준선 `var(--color-gray-400)`.

### 6.2 구성 (위에서 아래로)

1. **제목** 「시장 등락 통계」 + 작은 글씨 「{from}~{to} · {n_days}영업일 · KRX · 기준 {asof}」. `asof` 표시는 `formatKstDateTime(asof_kst)`(`src/utils/kst.ts`). 날짜 `YYYY-MM-DD` 는 서버가 준 KST 날짜라 `MM-DD` 는 **문자열 자르기**로 만든다(`new Date(...)`·새 `Intl.DateTimeFormat` 금지).
2. **시장 토글** 버튼 셋: 코스피 · 코스닥 · 합계. 기본 = **합계**. 칩·차트·표가 모두 이 선택을 따른다.
3. **요약 칩** (선택 시장의 `summary`):
   - 「ADR {adr}」 — `n_days < requested` 면 「ADR({n_days}일) {adr}」, `null` 이면 「—」. 숫자에 색·판정 문구를 붙이지 않는다.
   - 「상승 {up} · 하락 {down}」 (상승 빨강 · 하락 파랑 글자)
   - 「상한가 {limit_up}」 · 「하한가 {limit_down}」
   - 「상승 비율 {up_ratio×100, 소수 1자리}%」
4. **차트** (높이 240px, `ResponsiveContainer` 폭 100%) — `ComposedChart`, x축 = 날짜 **오래된 것 → 최신**(응답 `days[]` 를 뒤집어 쓴다), 눈금 `MM-DD`.
   - 왼쪽 축: 상승 막대(+값, 빨강) · 하락 막대(**음수로 바꿔** 그린다, 파랑) — 0 을 가운데에 둔 마주 보는 막대. 축 범위는 대칭 `[-M, M]`(M = 창 안 `max(up, down)` 를 보기 좋은 수로 올림)이라 위아래 길이를 그대로 비교할 수 있다. 눈금 표시는 절댓값.
   - 상한가·하한가: `limit_up > 0` 이면 상승 막대 위에, `limit_down > 0` 이면 하락 막대 아래에 숫자(10px, 각각 빨강·파랑 진한 색)를 `LabelList` 로 단다. 0 이면 아무것도 안 그린다.
   - 오른쪽 축: 상승 비율 선(0~100%). 왼쪽 축이 대칭이라 오른쪽 50% 와 왼쪽 0 이 같은 높이다 — 50% 에 점선 `ReferenceLine` 하나.
   - 툴팁: 날짜 · 상승 n(상한가 m) · 하락 n(하한가 m) · 보합 · 거래 없음 · 상승 비율 %.
   - 범례: 상승 · 하락 · 상승 비율.
5. **각주 한 줄** (작은 회색): 「ADR = 기간 상승 종목 수 합 ÷ 하락 종목 수 합 × 100. 업계 통상 기준선 75 이하 침체권 · 120 이상 과열권. 이 화면 방식의 과거 20일 ADR 중앙값(2020-10~2025-10): 코스피 92 · 코스닥 88 · 합계 89. 상한가·하한가는 그날 ±30% 가격제한폭 값에 닫힌 종목(신규상장일·정리매매 제외), 거래 없음은 거래량 0 종목.」 기준선 숫자는 응답 `adr_reference` 에서 읽는다(중앙값은 정적 문구).
6. **날짜별 표** — 열: 날짜 · 상승 · 하락 · 보합 · 상한가 · 하한가 · 거래 없음 · 상승 비율. 행 = 최신 먼저(응답 순서). 상승·상한가 숫자 빨강, 하락·하한가 숫자 파랑. 마지막 줄 = 「{n_days}일 합계」(요약값, 상승 비율 = `summary.up_ratio`). 숫자는 `toLocaleString()` 천 단위 쉼표.
   - 표는 `overflow-x-auto` 상자로 감싸고 표에 `min-w-[560px]` — 400px 폭에서 가로로 민다. 행이 최대 60개라 세로 높이 상한(`ScrollPane`)은 쓰지 않는다.

### 6.3 상태

| 상태 | 화면 |
|---|---|
| 불러오는 중 | `LoadingSpinner` + 「KRX 에서 최근 {days}영업일 전 종목 시세를 받는 중입니다 — 서버가 다시 켜진 뒤 첫 조회는 20~45초 걸릴 수 있습니다」. 다른 5섹션은 이 섹션을 기다리지 않는다(훅이 따로다) |
| 실패 (`success=false`·네트워크·422) | `ErrorAlert` 에 서버 `message` 그대로(네트워크 오류면 「시장 등락 통계를 불러오지 못했습니다」) |
| 일부 빠짐 (`missing_dates` 있음) | 차트 위 노란 상자: 「{k}일 자료를 받지 못했습니다: {MM-DD, …} — 잠시 뒤 새로 고치면 채워질 수 있습니다」 |
| 창 부족 (`complete=false` 이고 `missing_dates` 없음) | 회색 한 줄: 「최근 {lookback} 안에 영업일이 {n_days}일뿐입니다」 |
| 아직 없음 (`pending_date`) | 회색 한 줄: 「{MM-DD} 자료는 아직 KRX 에 올라오지 않았습니다(보통 다음 날 아침 8시쯤 — 휴장일이었다면 그대로 빠집니다)」 |
| 빈 날 (`empty_dates`) | 따로 표시하지 않는다(휴장은 정상) |

`data-testid`: 섹션 `macro-section-market-breadth` · 토글 `breadth-market-{kospi|kosdaq|total}` · 표 `breadth-table` · 노란 상자 `breadth-missing` · 아직 없음 `breadth-pending`.

---

## 7. 검증 기준 (task 항목 7)

### 7.1 10-08 재현 픽스처 (합성 행, 실제 KRX 키 이름 15개 전부, 값은 문자열, 일부에 쉼표)

메인 세션이 10-08 원자료에서 잰 숫자: 코스피 942행(`FLUC_RT` > 0 252 · < 0 625 · = 0 65 · ≥ 29.5 3) · 코스닥 1,823행(618 · 1,031 · 174 · ≥ 29.5 13 · ≤ −29.5 1).

픽스처 구성 (거래 없음 쪼개기는 합성이다 — 실제 10-08 의 보합/거래 없음 비율은 모른다. 보관소 평균에 가깝게 잡았다):

| 시장 | 상승 | 그중 상한가(정확히 `upper`, 고가=종가) | 하락 | 그중 하한가 | 보합(거래 있음) | 거래 없음(거래량·시고저 `"0"`, 대비 `"0"`) |
|---|---|---|---|---|---|---|
| 코스피 | 252 | 3 | 625 | 0 | 50 | 15 |
| 코스닥 | 618 | 13 | 1,031 | 1 | 99 | 75 |

- 상·하한가 행은 호가대가 다른 기준가로 만든다(예: 1,500 → 1,950 · 15,800 → **20,500** · 244,000 → 하한 **171,000**). 이 행들의 `FLUC_RT` 는 ≥ 29.5 / ≤ −29.5 여야 한다.
- 나머지 행의 `FLUC_RT` 는 대비 부호와 같게(예: ±1.00, 0.00).

기대값:

| | rows | traded | up | down | flat | limit_up | limit_down | no_trade | up_ratio | 하루 ADR |
|---|---|---|---|---|---|---|---|---|---|---|
| 코스피 | 942 | 927 | 252 | 625 | 50 | 3 | 0 | 15 | 0.2718 | 40.3 |
| 코스닥 | 1,823 | 1,748 | 618 | 1,031 | 99 | 13 | 1 | 75 | 0.3535 | 59.9 |
| 합계 | 2,765 | 2,675 | 870 | 1,656 | 149 | 16 | 1 | 90 | 0.3252 | 52.5 |

- **교차 단언**: 같은 픽스처에서 「`FLUC_RT` 부호·29.5 문턱으로 센 값」 이 메인 세션 실측(252/625/65/3 · 618/1,031/174/13/1)과 정확히 같아야 한다 — 픽스처가 실측과 같은 원자료 모양이라는 증거다. 보합+거래 없음 = 65 · 174.

### 7.2 경계 픽스처 — 실제 KRX 과거 사례 (KRX 보관소 원자료 값)

| ID | 사례 | 행 값 (기준가 = 종가 − 대비) | 기대 |
|---|---|---|---|
| E1 | 덕성 2023-08-07 | 고 11,900 · 저 9,180 · 종 11,900 · 대비 +2,720 (기준 9,180, +29.63%) | `up`, **상한가 아님**(`upper`=11,930) |
| E2 | 골든센츄리 2023-12-27 | 고 106 · 저 81 · 종 106 · 대비 +24 (기준 82, +29.27%) | `up` + **상한가** |
| E3 | 유유제약2우B 2023-12-07 | 고 20,500 · 저 15,800 · 종 20,500 · 대비 +4,700 (기준 15,800) | **상한가** — `upper`=20,500 (20,540 아님) |
| E4 | 삼천리 2023-04-26 | 시고저종 171,000 · 대비 −73,000 (기준 244,000) | **하한가** — `lower`=171,000 (170,800 아님) |
| E5 | DS단석 2023-12-22 (신규상장) | 고 400,000 · 저 350,500 · 종 400,000 · 대비 +300,000 | `up`, `out_of_band`, 상한가 아님 |
| E6 | 에코바이브 2023-10-27 (정리매매) | 고 300 · 저 150 · 종 150 · 대비 −6,260 | `down`, `out_of_band`, 하한가 아님 |
| E7 | 하이트진로홀딩스우 2023-09-08 | 시고저 0 · 종 12,240 · 대비 −10 · 거래량 0 | `no_trade` (하락 아님) |
| E8 | 엑스페릭스 2023-06-28 | 고 26,400 · 저 17,910 · 종 17,910 · 대비 −7,640 (기준 25,550) | `down`, **하한가 아님**(`lower`=17,900) |
| E9 | 엘에스스팩1호 2025-07-22 (상장일) | 고 5,040 · 저 2,545 · 종 2,600 · 대비 +600 (기준 2,000, 정확히 +30%) | `up`, `out_of_band`, 상한가 아님 |
| E10 | 쉼표·부호 | `TDD_CLSPRC="1,234,500"`, `CMPPREVDD_PRC="-1,500"` | `down`, 파싱 성공 |
| E11 | 판독 불가 | `TDD_CLSPRC=""` / `"-"` / `CMPPREVDD_PRC=None` | `unparsed`, 어디에도 안 셈 |

`tick_size` 경계 단언: 1,999→1 · 2,000→5 · 4,999→5 · 5,000→10 · 19,999→10 · 20,000→50 · 49,999→50 · 50,000→100 · 199,999→100 · 200,000→500 · 499,999→500 · 500,000→1,000.

### 7.3 날짜 창·캐시·라우트 (가짜 KRX = `src.api.krx.fetch_*` monkeypatch, 시각 = freezegun)

| ID | 상황 | 기대 |
|---|---|---|
| W1 | §2.3 예시 그대로 | `from=2026-09-08` · `to=2026-10-08` · `n_days=20` · `empty_dates` 3개 · `pending_date=null` |
| W2 | 오늘 2026-10-08(목) 09:30, 10-07 두 시장 빈 배열 | `pending_date=2026-10-07`, `to=2026-10-06`, 10-07 은 `empty_dates` 에 없음 |
| W3 | W2 를 10:30 에 | `pending_date=null`, `empty_dates` 에 10-07 |
| W4 | 오늘 2026-10-11(일) 15:00, 10-09(금) 빈 배열 | `pending_date=2026-10-09` (다음 평일 10-12 10:00 전) |
| W5 | 한 날짜의 코스닥만 두 번 연속 `KrxApiError` | 그 날짜 `missing_dates` · 칸 차지 · `days` 19개 · `summary.*.n_days=19` · `window.complete=false` · 그 시장·날짜로 호출 정확히 2번 |
| W6 | 한 날짜에 코스피만 빈 배열, 코스닥 유효 | 그 날짜 `MISSING`(부분) |
| W7 | 40일 안에 유효 날짜 5개뿐 | `n_days=5` · `complete=false` · 호출 날짜는 모두 `today−40` 이후 |
| W8 | `days=60` | 거슬러 보는 한도 120일 |
| W9 | 가짜 KRX 가 느려 전체 시한 초과(시한 상수를 작게 monkeypatch) | 끝난 날만 `days`, 나머지 `missing_dates` · 응답 뒤에도 남은 태스크가 끝나 캐시가 차고, 다시 부르면 새 호출 0 으로 전부 나온다 |
| W10 | 같은 요청 둘을 동시에 | 각 `(시장, 날짜)` 호출 1번 |
| W11 | 동시 호출 관측 | 가짜 KRX 안에서 잰 최대 동시 실행 ≤ 4 |
| W12 | 캐시: 유효 날짜 두 번째 조회 | 새 호출 0. 최근(7일 안) 빈 날은 601초 뒤 다시 호출, 8일 이전 빈 날은 다시 안 부름 |
| W13 | 설정 꺼짐 / 키 빈 값 | `success=false`, §5.5 문장, KRX 호출 0 |
| W14 | 전부 실패 | `success=false`, HTTP 200 |
| W15 | 호출 상한을 작게 monkeypatch | 상한 뒤 새 호출 0 · `missing_dates` · `[market_breadth_budget_exhausted]` WARNING 1번 |
| W16 | `days=0` · `days=61` | 422 |
| W17 | 키 노출 | 설정에 가짜 표지 문자열(실제 키 아님)을 넣고 실패 경로까지 돌려도 응답 본문·caplog 어디에도 그 문자열 없음 |
| W18 | 부호 어긋남 행 1개 | 분류는 `CMPPREVDD_PRC` 기준 그대로 · `[market_breadth_sign_mismatch]` WARNING |

caplog 단언은 WARNING 이상 + 접두어로만 한다(CI 로그 수준 차이 교훈).

### 7.4 구조 가드 (AST)

- `src/engine/market_breadth.py`: `Await`·`async def` 0 · import 는 표준 라이브러리만(`src.*`·`httpx`·`asyncio`·`logging` 금지).
- `src/routes/market_breadth.py`: KIS 모듈(`src.api.base`·`src.api.order`·`kis_*`) import 0 · `src.engine.scheduler` 및 8영역 모듈 import 0 · KRX 호출은 `krx.fetch_stk_bydd_trd`·`krx.fetch_ksq_bydd_trd` 두 이름만 · `logger.*` 인자에 설정의 `key` 0.
- `src/api/krx.py` 무변경 — 기존 가드 `tests/unit/ast/test_cycle115_krx_endpoint_urls.py` · `test_cycle115_krx_no_plaintext_key.py` · `tests/unit/api/test_cycle112_krx_client.py` · `test_cycle115_krx_endpoints.py` 가 그대로 초록.

### 7.5 프론트

- MSW 핸들러는 §5.4 의 **실제 키 이름** 그대로(`limit_up`·`no_trade`·`up_ratio`·`pending_date`·`missing_dates`…). `MacroPage.test.tsx` 핸들러 목록에도 `/api/market/breadth` 를 더한다.
- 단언: 기본 합계 → 코스닥 토글 시 칩·표 숫자 바뀜 · 표 행 수 = `days.length` + 합계 1줄 · 상승 숫자 빨강/하락 파랑 클래스 · `missing_dates` 있으면 `breadth-missing` · `pending_date` 있으면 `breadth-pending` · `success=false` → `ErrorAlert` 에 서버 문장 · 요청 `timeout` 60,000.

---

## 8. 현 코드와의 정합성

| 항목 | 상태 |
|---|---|
| 8영역·`scheduler.py` | 무접촉 |
| KIS 호출 | 추가 0 (KRX 공개 API 만) |
| `src/api/krx.py` | 무변경 — 공개 함수 두 개를 모듈 참조로 부를 뿐 |
| DB | 마이그레이션 0 · 읽기 = `system_config` KRX 설정 1회/요청(그리고 `fetch_krx_open_api` 가 호출마다 같은 설정을 다시 읽는다 — 기존 동작) |
| 매매 행위 | 무변경. 엔진·전략이 이 모듈을 import 하지 않는다 |
| KRX 키 한도 | 라우트 상한 1,000/일로 유니버스 적재 몫(하루 수~수십 콜)을 지킨다 |
| 인증 | 새 경로도 `ApiAuthMiddleware` 가 자동 보호(GET 이라 리포터 키로도 읽힌다 — 관찰 데이터라 무해) |
| 배포 | `src/` 변경이라 **full**(backend 재시작) — 장외 창(15:30~16:00 · 21:35~07:45 · 주말·공휴일)만 |
| 문서 동기화(Phase 4.8) | `src/routes/CLAUDE.md` 엔드포인트 표 한 행 · `src/engine/CLAUDE.md` 모듈 맵에 `market_breadth.py`(순수 leaf, 매매 무관) · `frontend/CLAUDE.md` 매크로 화면 섹션 목록 · 루트 `CLAUDE.md` 「외부 통합」 의 KRX 키 공유 사실은 `src/api/CLAUDE.md` KRX 절의 Rate Limit 문단에 소비처 한 줄 |

충돌 항목 없음.

---

## 9. 반례 / 한계

- **신규상장일 따따블**은 상한가로 안 센다(`out_of_band`). 1년에 몇 건.
- **정리매매 동전주**가 계산 하한가 값에 우연히 닫히면 하한가로 센다(659일에 3건).
- **2026-09-14 KRX 애프터마켓(16:00~20:00) 신설 뒤 `ACC_TRDVOL` 에 애프터 체결이 들어가는지 미확인**이다. 들어간다면 정규장에 한 주도 안 거래되고 애프터에서만 거래된 종목이 「거래 없음」 이 아니라 「보합」(또는 애프터 가격이 종가를 바꾸지 않으면 그대로 보합)으로 셀 수 있다. 숫자 영향은 하루 수 건 수준으로 보인다 — 운영 배포 뒤 대조(§10)에서 함께 본다.
- KRX 게시 시각 두 출처(익일 08:00 vs 당일 ~16:00)가 어긋난다. §2.2 정의는 어느 쪽이어도 칸 계산을 틀리지 않는다.
- 호가가격단위표·가격제한폭(±30%)이 바뀌면 상수를 바꿔야 한다.
- 우선주·스팩·리츠가 들어 있어 지수 기준 종목 수(§10)와 숫자가 다르다 — 결함이 아니라 모집단 차이다.
- 프로세스 메모리 캐시라 재시작 직후 첫 조회는 느리다(§5.3 표).

---

## 10. 후속 검증 — 메인 세션 메모 (운영 배포 뒤, 코드 아님)

KIS 업종 지수 TR 의 종목 수와 같은 날짜를 대조한다.

- **TR 이름 확인**: 작업 지시는 「업종 현재지수(FHPUP02140000)」 로 적었으나 로컬 정본 `docs/kis/domestic-stock-industry.md` 에서는 `FHPUP02100000` = 국내업종 현재지수, `FHPUP02140000` = 국내업종 구분별전체시세다. 둘 다 `ascn_issu_cnt`(상승) · `uplm_issu_cnt`(상한) · `stnr_issu_cnt`(보합) · `down_issu_cnt`(하락) · `lslm_issu_cnt`(하한) 을 준다. 업종코드 코스피 `0001` · 코스닥 `1001`.
- 대조 시각: 그날 15:40 이후 KIS 값 ↔ 다음 아침 이 화면의 그날 값.
- 차이가 날 자리(결함으로 보기 전에 확인할 것):
  1. **모집단** — KIS 지수 종목 수는 지수 구성 종목 기준일 수 있다(코스피 지수는 보통주만으로 알려져 있어 우선주가 빠질 수 있음). 이 화면은 KRX 일별 매매정보의 전 행이다.
  2. **상한 포함 여부** — KIS 가 상한·상승·보합·하락·하한을 서로 겹치지 않게 나누면 `ascn + uplm` 을 우리 `up` 과, `down + lslm` 을 우리 `down` 과 비교한다(KIS 문서 예시 코스닥: 상승 828 · 상한 5 · 보합 94 · 하락 716 · 하한 1).
  3. **보합에 거래 없음 포함 여부** — `stnr` 를 우리 `flat + no_trade` 와도 비교한다.
  4. **상·하한 판정** — 두 숫자가 다르면 그날 `limit_up` 종목 목록을 KRX 원자료로 뽑아 `out_of_band`·동전주 여부부터 본다.
