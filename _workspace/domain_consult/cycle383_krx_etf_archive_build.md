# cycle383 — KRX ETF 5년치 일별 시세 수집 (도구 확장 + 실행 시도 기록)

작업 지시 = 「ETF 전략 A1 — KRX ETF 5년치 수집 권고대로」(사용자 결정 2026-09-27) + 설계 문서
`_workspace/design/2026-09-27_etf_trend_strategy.md` §8.1(S0). 읽기 전용 데이터 수집이다.
매매 코드·DB 쓰기·주문 없음. `src/` 무접촉·8영역 무접촉·git 커밋 없음(메인 세션 판단).

**표기**: **[실측]** = 이번에 직접 확인한 사실 · **[추정]** = 근거를 적은 판단.

---

## 쉬운 말 요약

1. **도구는 다 만들었고 테스트도 통과했다.** 기존 주식 5년 보관소 도구(`tools/archive/krx_daily_archive.py`, cycle362)에 ETF 전용 기능을 더했다. 단위 테스트 16개가 전부 통과한다.
2. **하지만 실제 수집은 한 콜도 못 했다.** KRX Open API 의 ETF 전용 카테고리(ETP)가 이 계정에 **아직 승인되지 않아** 모든 호출이 401(권한 없음)로 막힌다. 이건 코드 문제가 아니라 **사람이 KRX 개발자 포털에 로그인해서 신청 버튼을 눌러야 하는** 절차다.
3. **그래서 4단계(수집 실행)와 5단계(검증)는 진행하지 못했다.** 승인이 나면 이미 만들어 둔 명령 3개(`stream_etf` → `normalize_etf_jsonl` → `merge_jsonl`/`validate`/`export_dump`)를 그대로 돌리면 된다 — 아래 「재개 방법」에 정확한 명령을 적어 뒀다.
4. **응답 필드 이름도 아직 못 봤다.** 401 이라 KRX 가 실제로 어떤 이름으로 데이터를 주는지 한 번도 보지 못했다. 그래서 필드를 다루는 코드는 "아마 이럴 것이다"라는 가설로 짜되, 가설이 틀리면 **조용히 이상한 숫자를 만드는 대신 바로 에러를 내도록** 만들었다.

---

## 1. 확인한 것 — 엔드포인트는 맞다, 승인이 없다

**[실측]** 엔드포인트 경로 = `/etp/etf_bydd_trd` (KRX Open API 「ETF 일별매매정보」).

- 검증 방법은 cycle115 가 기존 4개 endpoint 를 확정할 때 쓴 것과 같다 — 외부 정본 2건 교차 확인.
  - `raccoonyy/pykrx-openapi`(`src/pykrx_openapi/constants.py`)에 `CATEGORY_ETP="etp"`,
    `ENDPOINTS["etf_bydd_trd"] = ("etp", "ETF 일별매매정보")`로 명시돼 있다. 이 라이브러리는
    `src/api/krx.py` 가 인용하는 것과 같은 계열(GET + `AUTH_KEY` query parameter + `basDd` +
    `OutBlock_1` 응답)이다.
  - 설계 문서 §8.1 의 사전 추정(`/etp/etf_bydd_trd` [확인 필요])과 정확히 일치한다.
- **[실측] 운영 컨테이너에서 직접 호출**(2026-09-27) — 응답이 **404 가 아니라 401**이다:
  ```
  {"respMsg":"Unauthorized API Call","respCode":"401"}
  ```
  경로 자체는 존재한다는 뜻이다. 404 였다면 경로가 틀렸다는 신호였을 텐데, 그게 아니다.
- **[실측] 카테고리 전체가 막혀 있다** — 같은 방식으로 `/etp/etn_bydd_trd`, `/etp/elw_bydd_trd`
  도 시도했고 셋 다 동일한 401 이 났다. 반면 기존 4개(`/sto/stk_bydd_trd` 등)는 정상 응답한다.
  즉 이 KRX 계정은 **sto/idx 카테고리만 승인**돼 있고 **etp(ETF/ETN/ELW) 카테고리는 미승인**
  이다 (`docs/krx-openapi.md` 「3. API 이용 신청」 절차 — 서비스별로 별도 신청·승인이 필요).
- **[실측] ETF 는 기존 승인된 엔드포인트에 섞여 있지도 않다** — `stk_bydd_trd`(유가증권 일별매매
  정보)로 2026-09-23 자를 조회(942행)했을 때 KODEX 200(069500)이 나오지 않았다. ETF 데이터는
  정말로 별도 카테고리에만 있고, 우회 경로가 없다.

**결론 — 이건 코드로 풀 수 있는 문제가 아니다.** KRX 개발자 포털(openapi.krx.co.kr)에 그
계정으로 로그인해서 「서비스 이용 → ETP → API 이용신청」을 눌러야 한다. 기존 4개 endpoint 도
같은 절차로 승인된 것으로 보인다(cycle112/115 기록에 "서비스 승인" 언급). 문서상 보통 승인까지
하루 이내로 걸린다(같은 포털의 "인증키 신청" 절 기준 — ETP 서비스 신청도 비슷할 것으로
**[추정]**, 정확한 소요는 실측하지 않았다).

---

## 2. 만든 것 — `tools/archive/krx_daily_archive.py` 확장 (같은 파일에 추가)

새 파일을 만들지 않고 기존 파일에 「ETF (cycle383)」 절을 더했다 — 날짜 순회·저녁 창 회피·숫자
파싱·조정계수 계산·validate/export_dump 가 전부 필드명과 무관하게 이미 범용이라 재사용이 더
간단했다.

**컨테이너 안 (운영 backend, 실물 KRX 호출)**
- `probe_etf <basDd>` — 단일 날짜 스모크 테스트. 승인이 나면 **가장 먼저 돌려서 실제
  필드 이름을 확인하는** 용도.
- `stream_etf <start> <end> [--sleep S]` — 날짜별 ETF raw 를 stdout 에 JSONL 로 흘려보낸다.
  **주식과 다른 점**: 필드를 전혀 가공하지 않고 KRX 가 준 dict 를 그대로 담는다 — 실제 필드를
  모르는 채로 짤 수 있는 가장 안전한 형태다(추측이 전혀 필요 없다). 실패한 날짜는 최대 2회
  재시도 후에도 안 되면 기록만 하고 다음 날짜로 넘어간다(전체 재시작 없이 이어받기 가능).
  KOSPI/KOSDAQ 분리가 없는 단일 엔드포인트라 **날짜당 1콜**(주식의 절반).

**로컬 (pandas 만, KRX 호출 없음)**
- `normalize_etf_jsonl <raw_jsonl> <out_jsonl>` — `stream_etf` 가 받은 원본을 기존 주식
  보관소가 읽는 12칸 모양으로 바꾼다. **이 단계에서만** 필드 이름 가설(`_extract_etf_row`)을
  쓴다. 가설이 맞으면 정상 변환되고, 핵심 값(종목코드·종가)을 찾을 후보 키가 하나도 없으면
  그 자리에서 즉시 에러를 내고 멈춘다 — 절반만 맞은 5년치 파일을 만들지 않는다.
- 그 다음은 **기존 함수를 그대로 재사용**한다 — `merge_jsonl`(조정계수 계산 + 연도별 parquet)
  · `validate`(KIS 대조) · `export_dump`(S0 덤프 모양). ETF 전용 merge/validate 함수는
  따로 만들지 않았다 — 출력 디렉터리만 `data/archive/krx_etf_daily/`로 다르게 주면 된다.

### 수정가 보정 규칙 (ETF 분배금 조정) — 결정과 근거

**결정: 새 로직을 만들지 않고 기존 `_adjust_one` 을 그대로 쓴다.**

기존 방식은 "그날 기준가(=종가−전일대비)가 전일 종가와 다르면 그 비율만큼 과거 가격을
누적 조정한다"는 규칙이다. 이 규칙은 **왜 기준가가 바뀌었는지 몰라도 동작한다** — 배당락이든
분배락이든 액면분할이든, KRX 가 그날 기준가를 조정해서 내려주는 이상 같은 신호로 잡힌다.
cycle362 실측에서도 "조정계수 발생 다수가 12월 마지막 거래일 배당락"이라고 확인된 바로 그
메커니즘이며, ETF 의 분배락도 원리상 같은 방식으로 기준가에 반영될 것으로 **[추정]**한다
(직접 확인은 못 했다 — §8.2 필드 미확인과 같은 이유). 그래서 ETF 전용 조정 함수를 새로
만드는 대신 `_adjust_one` 을 재사용하도록 설계했고, 그 근거를 함수 docstring 에 남겼다.

미실측 한계 (cycle362 README 의 한계와 동일한 성격) — 감자·합병처럼 KRX 기준가 보정법이
드물게 다르게 나오는 사건이 있다면 이 방식이 못 잡을 수 있다. 실물 데이터를 받기 전에는
확인할 수 없다.

---

## 3. 테스트 — `tests/unit/tools/test_cycle383_krx_etf_daily_archive.py` (신규 디렉터리)

16개 테스트, 전부 순수 함수 대상(파일 I/O 는 `tmp_path` 로 격리, KRX·DB·KIS 호출 0건):

- `_first_present`(후보 키 우선순위) 3건
- `_extract_etf_row`(정상 변환 · fallback 키 · 부가 필드 결측 시 0 · **핵심 키 없으면
  ValueError**) 6건 — 마지막 항목이 "가설이 틀렸을 때 시끄럽게 실패한다"는 설계 불변식의
  실제 검증 대상이다.
- `normalize_etf_jsonl`(왕복 변환 · 빈 줄 스킵 · 잘못된 행이 섞이면 전체가 멈춘다) 3건
- `_adjust_one`(평탄한 시계열은 조정계수 1.0 · 분배락 흉내 이벤트가 과거 가격을 소급 조정 ·
  범위 밖 비율은 1.0 으로 방어) 3건
- 엔드포인트 경로 상수 핀 1건

**[실측] 결과**:
```
16 passed in 0.37s
```

**[실측] 회귀 확인**:
- `tests/unit/deploy` 전체 254건 중 253 통과, 1건 실패 —
  `test_cycle318_impact_index_freshness.py::test_backend_index_is_fresh`. 실패 사유로
  나온 "바뀐 모듈 125개"는 전부 `src/api/*` 등 **`src/` 경로**이고, 이번에 건드린
  `tools/archive/krx_daily_archive.py`·`tests/unit/tools/*` 는 그 목록에 없다(직접 grep 확인).
  이 세션에서 동시에 `src/` 를 고치는 다른 작업이 있다는 사전 안내와 일치하는, **이 작업과
  무관한 기존 드리프트**로 판단해 인덱스를 재생성하지 않았다(`python tools/test_impact/build_index.py`
  는 지시대로 이번 작업에서 실행하지 않음 — src/ 변경 중인 다른 에이전트의 미완성 상태를
  인덱스에 박제할 위험이 있어서다).
- `tests/unit/ast/test_cycle322_image_excluded_paths.py` · `test_cycle248_deploy_pipeline.py`
  29건 전부 통과 — 배포 분류에 영향 없음 확인(`tools/archive/`는 backend 재빌드 트리거 목록
  밖이라 이 변경은 배포 모드 `none`).

---

## 4. 못 한 것 (블로커 때문에)

- **수집 실행(4번째 요청 항목)**: 0 콜. 401 로 전량 막혀 실행 자체를 시도하지 않았다(빈 실패
  기록만 쌓일 뿐 의미가 없어서). 레이트리밋·재시도·이어받기 로직은 코드에 있지만 아직 실전
  검증은 못 했다.
- **검증(5번째 요청 항목)**: ETF 원장 데이터가 0건이라 종목 수·상장폐지 포함 여부·일자 수·
  `stock_master_daily` 401종 겹침 대조 전부 수행 불가.
- **응답 필드 확인**: `probe_etf` 가 401 이라 실제 `OutBlock_1` 키를 한 번도 못 봤다.
  `_extract_etf_row` 의 필드명은 여전히 **미확인 가설**이다.

---

## 5. 재개 방법 — 승인이 난 뒤 순서대로

전제: 사람이 openapi.krx.co.kr 에 로그인해서 ETP(ETF 일별매매정보) 서비스를 신청하고
승인을 받는다. (선택) ETN·ELW 도 같이 신청해 두면 나중에 따로 신청할 필요가 없다.

```bash
# 0) 승인 확인 — 실제 필드를 처음 보는 순간
cat tools/archive/krx_daily_archive.py | ssh auto-stock \
  "cd ~/auto_stock && docker compose -f docker-compose.prod.yml exec -T backend python3 - probe_etf 20260924"
# rows>0 이고 KrxApiError 가 안 나오면 승인된 것. sample keys 를 _extract_etf_row 의 후보
# 키(_ETF_*_KEYS)와 대조 — 다르면 그 목록만 고치면 된다(로직 변경 없음).

# 1) 본 수집 — 기간은 cycle362 주식 보관소와 동일(§8.1 "cycle362 보관소와 같다" 명시,
#    1,311 평일 → 실제 영업일 약 1,229일 → 날짜당 1콜 ≈ 1,230콜, 약 15분 @0.7s).
#    🔴 20:00~21:35 KST 는 자동으로 피한다(코드 내장). 장외 창(주말·공휴일·21:35~익일 07:45)
#    권장. 다른 에이전트가 src/ 를 고치는 중이면 배포 창(15:30~16:00 등)도 피한다(안전 여유).
cat tools/archive/krx_daily_archive.py | ssh auto-stock \
  "cd ~/auto_stock && docker compose -f docker-compose.prod.yml exec -T backend python3 - \
   stream_etf 2020-10-01 2025-10-09 --sleep 0.7" > data/archive/krx_etf_daily/raw_2020_2025.jsonl

# 참고 — 범위를 다르게 잡고 싶다면: 이 작업을 지시한 문서(cycle383 위임 프롬프트)는
# "2020-10~2026-09 전체"(약 1,230콜)라고 적었지만, 그 범위(2020-10-01~2026-09-25)는 실제로
# 약 1,560 평일(약 1,460 영업일)이라 "약 1,230콜"과 안 맞는다. 반면 설계 문서 §8.1 이 명시한
# "cycle362 보관소와 같은 기간"(2020-10-01~2025-10-09)은 정확히 1,230콜에 맞아떨어진다.
# 그래서 위 명령은 설계 문서 §8.1 기준으로 뒀다 — 2025-10-10 이후는 운영 stock_master_daily
# 가 이미 덮는다(§8.1 "그 뒤는 운영 stock_master_daily 로 잇는다"). 더 최근까지 이 archive
# 자체로 직접 갖고 싶으면 end 를 오늘 이전 영업일로 늘려서 한 번 더 이어 돌리면 된다(예:
# `stream_etf 2025-10-10 2026-09-25 --sleep 0.7 >> raw_2020_2025.jsonl` 로 이어붙이기).

# 2) 실패 날짜가 있으면 stderr 의 error_dates 목록만 좁혀 재수집 후 로컬에서 이어붙인다.

# 3) 정규화 → 병합 → 검증 → 덤프 (전부 로컬, pandas 만)
python tools/archive/krx_daily_archive.py normalize_etf_jsonl \
  data/archive/krx_etf_daily/raw_2020_2025.jsonl data/archive/krx_etf_daily/normalized.jsonl
python tools/archive/krx_daily_archive.py merge_jsonl \
  data/archive/krx_etf_daily/normalized.jsonl data/archive/krx_etf_daily/parquet

# 검증용 KIS 겹침 덤프(운영 DB 읽기 전용, stock_master_daily 의 ETF 401종)
cat tools/archive/krx_daily_archive.py | ssh auto-stock \
  "cd ~/auto_stock && docker compose -f docker-compose.prod.yml exec -T backend python3 - \
   dump_kis_overlap 2025-10-10 2026-09-25 /tmp/etf_kis_overlap.json.gz" \
  # (dump_kis_overlap 은 컨테이너 안에서 파일로 쓰므로, stream 처럼 stdout 스트리밍으로
  #  바꾸거나 컨테이너 안에서 만든 뒤 `docker compose cp` 로 꺼내야 한다 — cycle362 는 이
  #  함수를 컨테이너 로컬에 쓴 뒤 별도로 받았다. 재현 시 그 순서를 그대로 따른다.)

python tools/archive/krx_daily_archive.py validate \
  data/archive/krx_etf_daily/parquet <로컬로_받은_kis_overlap.json.gz>
python tools/archive/krx_daily_archive.py export_dump \
  data/archive/krx_etf_daily/parquet data/archive/krx_etf_daily/krx_etf_dump.json.gz
```

---

## 6. 변경 파일

- `tools/archive/krx_daily_archive.py` — ETF 절 추가(모듈 docstring 갱신, `_ENDPOINT_ETF_BYDD_TRD`
  · `probe_etf` · `stream_etf` · `_first_present` · `_extract_etf_row` · `normalize_etf_jsonl`
  · `_adjust_one` docstring 보강 · CLI dispatch 3종 추가). 기존 함수 동작 변경 없음(순수 추가).
- `tests/unit/tools/__init__.py` — 신규 디렉터리 마커(빈 파일).
- `tests/unit/tools/test_cycle383_krx_etf_daily_archive.py` — 신규, 16 테스트.
- `.gitignore` — `data/archive/krx_etf_daily/` 등록(cycle362 의 `krx_daily/` 패턴 답습).

커밋은 하지 않았다(메인 세션 판단 대상).

---

## 7. 한계 및 확인 필요 목록

- **응답 필드명 미확인** — 승인 전에는 확정 불가. `_extract_etf_row` 의 후보 키가 틀리면
  `probe_etf` 결과를 보고 후보 목록만 고치면 된다(구조 변경 불필요).
- **호출 범위 불일치** — 위임 프롬프트의 "2020-10~2026-09·약 1,230콜"과 설계 문서 §8.1 의
  "2020-10-01~2025-10-09·1,229 영업일"이 수치상 맞지 않는다(§5 재개 방법에서 해소 방안 기술).
  실제 실행 시 사람이 최종 범위를 확정하는 것을 권한다.
- **ETF 분배락 조정 가설 미검증** — §2 "수정가 보정 규칙" 절 참조. 실물 데이터를 받은 뒤
  `validate` 결과(KIS 겹침 대조 일치율)로 간접 확인 가능.
- **상장폐지 ETF 분류(§8.2, 이번 작업 범위 밖)** — 이 문서는 수집 도구까지만 다룬다. 상장폐지
  분류·문턱 판정(§8.3)은 데이터 확보 후 별도 작업이다.

## 9. 메인 세션 확정 (2026-09-27)

- **신청 상태** — 사용자가 openapi.krx.co.kr 에서 ETF 일별매매정보 이용을 신청했다(2026-09-27). 승인 대기.
- **ETN·ELW 는 신청하지 않는다** — 사용자 확인(2026-09-27). ETF 전략(A1~8)은 국내 주식형 1배 ETF 만 대상이고,
  기존 전략의 ETF·ETN 제외(cycle380)는 `stock_master` 증권그룹코드로 판정해 이 API 와 무관하다. §5 의 「(선택) ETN·ELW 도 같이 신청」은 적용하지 않는다.
- **수집 범위** — `2020-10-01` ~ 승인 시점의 가장 최근 거래일. 위 §5·§8 의 범위 불일치는 이것으로 닫는다
  (앞 구간은 cycle362 보관소와 같은 시작일, 뒤 구간은 최근 장세를 포함해야 문턱 T1~T6 재측정이 의미가 있다).
