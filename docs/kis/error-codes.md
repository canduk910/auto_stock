# KIS OpenAPI 오류 코드 통합

> KIS OpenAPI에서 내려오는 오류 코드 표(서버 영역별) + 본 프로젝트가 운영에서 실측한 비즈니스 거부 코드(APBK 계열) + 거부 분류·후속 조치 매핑.
>
> 분류 헬퍼 단일 소스: `src/api/balance.py`
> 거부 영구 저장: `src/api/base.py::_request` → `system_logs (category 메시지 prefix `[kis_rejection]`)`
> 매수 폴백: `src/engine/order_engine.py::execute_buy` (지정가 5호가 폴백 1회)

---

## 1. EGW 게이트웨이 (인증/세션/Rate Limit)

| 코드 | 메시지 |
|------|--------|
| EGW00001 | 일시적 오류가 발생했습니다. |
| EGW00002 | 서버 에러가 발생했습니다. |
| EGW00003 | 접근이 거부되었습니다. |
| EGW00004 | 권한을 부여받지 않은 고객입니다. |
| EGW00101 | 유효하지 않은 요청입니다. |
| EGW00102 | AppKey는 필수입니다. |
| EGW00103 | 유효하지 않은 AppKey입니다. |
| EGW00104 | AppSecret은 필수입니다. |
| EGW00105 | 유효하지 않은 AppSecret입니다. |
| EGW00106 | redirect_uri는 필수입니다. |
| EGW00107 | 유효하지 않은 redirect_uri입니다. |
| EGW00108 | 유효하지 않은 서비스구분(service)입니다. |
| EGW00109 | scope는 필수입니다. |
| EGW00110 | 유효하지 않은 scope 입니다. |
| EGW00111 | 유효하지 않은 state 입니다. |
| EGW00112 | 유효하지 않은 grant 입니다. |
| EGW00113 | 응답구분(response_type)은 필수입니다. |
| EGW00114 | 지원하지 않는 응답구분(response_type)입니다. |
| EGW00115 | 권한부여 타입(grant_type)은 필수입니다. |
| EGW00116 | 지원하지 않는 권한부여 타입(grant_type)입니다. |
| EGW00117 | 지원하지 않는 토큰 타입(token_type)입니다. |
| EGW00118 | 유효하지 않은 code 입니다. |
| EGW00119 | code를 찾을 수 없습니다. |
| EGW00120 | 기간이 만료된 code 입니다. ⚠️ **본 프로젝트에선 예수금 부족 변형 msg_cd로도 활용 — `is_insufficient_cash` 화이트리스트** |
| EGW00121 | 유효하지 않은 token 입니다. |
| EGW00122 | token을 찾을 수 없습니다. |
| EGW00123 | 기간이 만료된 token 입니다. |
| EGW00124 | 유효하지 않은 session_key 입니다. |
| EGW00125 | session_key를 찾을 수 없습니다. |
| EGW00126 | 기간이 만료된 session_key 입니다. |
| EGW00127 | 제휴사번호(corpno)는 필수입니다. |
| EGW00128 | 계좌번호(acctno)는 필수입니다. |
| EGW00129 | HTS_ID는 필수입니다. |
| EGW00130 | 유효하지 않은 유저(user)입니다. |
| EGW00131 | 유효하지 않은 hashkey입니다. |
| EGW00132 | Content-Type이 유효하지 않습니다. |
| EGW00201 | 초당 거래건수를 초과하였습니다. ⚠️ **Rate Limit 초과 — `_semaphore`(초당 20건) 위반 시 발생** |
| EGW00202 | GW라우팅 중 오류가 발생했습니다. |
| EGW00203 | OPS라우팅 중 오류가 발생했습니다. |
| EGW00204 | Internal Gateway 인스턴스를 잘못 입력했습니다. |
| EGW00205 | credentials_type이 유효하지 않습니다.(Bearer) |
| EGW00206 | API 사용 권한이 없습니다. |
| EGW00207 | IP 주소가 없거나 유효하지 않습니다. |
| EGW00208 | 고객유형(custtype)이 유효하지 않습니다. |
| EGW00209 | 일련번호(seq_no)가 유효하지 않습니다. |
| EGW00210 | 법인고객의 경우 모의투자를 이용할 수 없습니다. |
| EGW00211 | 고객명(personalname)은 필수 입니다. |
| EGW00212 | 휴대전화번호(personalphone)는 필수 입니다. |
| EGW00213 | 제휴사명(corpname)은 필수 입니다. / 모의투자 tr이 아닙니다. *(중복 코드)* |
| EGW00300 | Gateway 라우팅 오류가 발생했습니다. |
| EGW00301 | 연결 시간이 초과되었습니다. 직전 거래를 반드시 확인하세요. |
| EGW00302 | 거래시간이 초과되었습니다. 직전 거래를 반드시 확인하세요. |
| EGW00303 | 법인고객에게 허용되지 않은 IP접근입니다. |
| EGW00304 | 고객식별키(법인 personalSeckey, 개인 appSecret)가 유효하지 않습니다. |

---

## 2. OPSQ 조회 서버 (REST 조회 응답)

| 코드 | 메시지 |
|------|--------|
| OPSQ0001 | 호출 전처리 오류 입니다. |
| OPSQ0002 | 없는 서비스 코드 입니다. |
| OPSQ0003 | 호출 오류 입니다. |
| OPSQ0004 | 호출 후처리 오류 입니다. |
| OPSQ0005 | 호출 후처리 오류 입니다. |
| OPSQ0006 | 호출 후처리 오류 입니다. |
| OPSQ0007 | 호출 후처리(헤더설정) 오류 입니다. |
| OPSQ0008 | 호출 후처리(MCI전송) 오류 입니다. |
| OPSQ0009 | 호출 후처리(MCI수신) 오류 입니다. |
| OPSQ0010 | 호출 결과처리(리소스 부족) 오류 입니다. |
| OPSQ0011 | 호출 결과처리(리소스 부족) 오류 입니다. |
| OPSQ1002 | 세션 연결 오류 |
| OPSQ2000 | ERROR : INPUT INVALID_CHECK_ACNO |
| OPSQ2001 | ERROR : INPUT INVALID_CHECK_MRKT_DIV_CODE |
| OPSQ2002 | ERROR : INPUT INVALID_CHECK_FIELD_LENGTH |
| OPSQ2003 | ERROR : SET_MCI_SEND_DATA |
| OPSQ3001 | ERROR : RESPONSE_ADDITEMTOOBJECT |
| OPSQ3002 | ERROR : GET_CALL_PARAM_MCI_SEND_DATA_LEN |
| OPSQ3004 | ERROR : OUT_STRING_ARRAY ALLOC FAILED |
| OPSQ9995 | JSON PARSING ERROR : body not found |
| OPSQ9996 | JSON PARSING ERROR : header not found |
| OPSQ9997 | JSON PARSING ERROR : invalid json format |
| OPSQ9998 | JSON PARSING ERROR : seq_no not found |
| OPSQ9999 | JSON PARSING ERROR : tr_id not found |

---

## 3. OPSP 실시간 서버 (WebSocket 구독)

| 코드 | 메시지 |
|------|--------|
| OPSP0000 | SUBSCRIBE SUCCESS |
| OPSP0001 | UNSUBSCRIBE SUCCESS |
| OPSP0002 | ALREADY IN SUBSCRIBE |
| OPSP0003 | UNSUBSCRIBE ERROR (not found!) |
| OPSP0007 | SUBSCRIBE INTERNAL ERROR |
| OPSP0008 | MAX SUBSCRIBE OVER |
| OPSP0009 | SUBSCRIBE ERROR : mci send failed |
| OPSP0010 | SUBSCRIBE WARNING : invalid appkey |
| OPSP0011 | invalid approval(appkey) : NOT FOUND |
| OPSP8991 | SUBSCRIBE ERROR : invalid tr_id |
| OPSP8992 | SUBSCRIBE ERROR : invalid tr_key |
| OPSP8993 | JSON PARSING ERROR : invalid tr_key |
| OPSP8994 | JSON PARSING ERROR : personalseckey not found |
| OPSP8995 | JSON PARSING ERROR : appsecret not found |
| OPSP8996 | ALREADY IN USE appkey |
| OPSP8997 | JSON PARSING ERROR : invalid tr_type |
| OPSP8998 | JSON PARSING ERROR : invalid custtype |
| OPSP8999 | resource not available (ALLOC_CALL_PARAM) |
| OPSP9990 | JSON PARSING ERROR : tr_key not found |
| OPSP9991 | JSON PARSING ERROR : input not found |
| OPSP9992 | JSON PARSING ERROR : body not found |
| OPSP9993 | JSON PARSING ERROR : internal error |
| OPSP9994 | JSON PARSING ERROR : INVALID appkey |
| OPSP9995 | JSON PARSING ERROR : resource not available |
| OPSP9996 | JSON PARSING ERROR : appkey |
| OPSP9997 | JSON PARSING ERROR : custtype not found |
| OPSP9998 | JSON PARSING ERROR : header not found |
| OPSP9999 | JSON PARSING ERROR : invalid json format |

---

## 4. 비즈니스 거부 (APBK 계열) — 본 프로젝트 실측

본 프로젝트가 운영에서 실제로 마주친 거부 코드와 분류·후속 조치 매핑. 새 사례가 발생하면 `system_logs`에서 prefix `[kis_rejection]` 행을 회수해 본 표에 추가한다.

| msg_cd | 의미 | 분류 헬퍼 (`src/api/balance.py`) | 후속 동작 (`src/engine/order_engine.py` 등) |
|--------|------|--------------------------------|----------------------------------------------|
| **APBK0918** | 장시간외 / 보유부족 / 자금부족 **공용** | `is_market_closed_rejection` 또는 `is_insufficient_cash` 또는 `is_insufficient_quantity` (msg1 키워드로 분기) | 시간외: `positions` 보존 + 재시도 중단 / 자금부족: `block_buy(900s)` / 보유부족: 매도 즉시 break |
| **APBK0919** | 예수금 부족(명시) | `is_insufficient_cash` | `block_buy(900s)` — 다음 잔고 sync에서 해제 |
| **APBK1234** | 보유수량 부족(명시) | `is_insufficient_quantity` | 매도 break + DB positions 정리 |
| **APBK0400** | "주문 가능한 수량을 초과했습니다" — 요청 수량 > 매도 가능 수량 (**부분 보유 내재** — cycle236, 실측 2026-08-28 257720 TTTC0011U ×3) | `is_sell_qty_exceeded` (msg_cd ∧ "수량"·"초과" 동시) — `is_insufficient_quantity` **흡수 금지** | `execute_sell` #1.5 잔고 재대조: 오염(held<positions)=held 로 보정+재시도 / 잠김(sellable<held)=보존+중단(`_selling` 유지) / 실보유 0=insufficient 경로 |
| **EGW00120** | 예수금 부족 변형(게이트웨이 영역) | `is_insufficient_cash` | `block_buy(900s)` |
| **(msg_cd 미확정)** | 시장가매매불가 (msg1 키워드 기반) | `is_market_order_disallowed` | **지정가 5호가 위 폴백 1회 시도**, 폴백 실패 시 `block_low_funds(ticker, 900s)` |

### 4-1. APBK0918 msg1 분기 규칙

같은 `APBK0918`이 시간외/보유부족/자금부족 모두에 쓰이기 때문에 msg1 키워드로 분리한다(`src/api/balance.py:_MARKET_CLOSED_KEYWORDS`):

- **시간외**: `장운영시간` / `매매 불가 시간` / `매매불가시간` / `운영시간이 아` / `거래시간 외` / `거래시간외` / `장시간 외` / `장시간외` 포함
- **자금부족**: `부족` AND (`주문가능금액` OR `예수금` OR `현금`) 포함
- **보유부족**: `부족` AND (`매도가능` OR `보유수량` OR `잔고`) 포함

상호 배타가 보장되도록 `is_market_closed_rejection`이 True면 `is_insufficient_*`가 모두 False로 떨어지는 가드가 코드에 들어 있다. 회귀 테스트: `tests/unit/api/test_insufficient_classification.py`.

### 4-2. "시장가매매불가" 거부 (msg_cd 미확정)

2026-05-11 계양전기(012200) 매수 시 KIS로부터 "시장가매매불가" 사유로 거부됨. 종목 자체 규제는 없음. SOR 라우팅 도입(`ef2993b`, 2026-05-08) 직후 첫 영업일 발생.

**현재 분류**: msg1 키워드 기반 (`_MARKET_ORDER_DISALLOWED_KEYWORDS`):
- `시장가매매불가` / `시장가 매매 불가` / `시장가 주문 불가` / `시장가 호가 불가`

**후속 동작**: `execute_buy`에서 `is_market_order_disallowed(err)` 진입 시 `step_up(current_price, steps=5)` 가격으로 지정가(LIMIT) 1회 폴백. 매핑 동기 등록 + 체결통보 선행 race 가드는 시장가 경로와 동일 규약 유지. 폴백도 거부되면 `block_low_funds(ticker, 900s)` cooldown.

**미확정 사항**:
- 정확한 `msg_cd` — Phase A1 영구 로깅이 다음 거부에서 자동 캡처 예정. 회수 후 화이트리스트 추가
- 진짜 원인(NXT 미상장 종목 + SOR / NXT 운영시간 미스매치 / 일시 호가 차단 / 기타 KIS 정책) — 추가 운영 trace로 확정

---

## 5. SOR / NXT / 거래소ID 운영 메모

본 프로젝트의 `place_order`는 `EXCG_ID_DVSN_CD` body 필드로 거래소를 지정한다(`src/api/order.py:25-67`).

| 값 | 의미 | 모의(VTS) | 실전(real) | 시장가 호환 |
|----|------|----------|-----------|------------|
| `KRX` | 한국거래소(기본) | ✓ | ✓ | ✓ 시장가/지정가 모두 |
| `NXT` | 넥스트레이드 | ✗ | ✓ | 시간대/종목별 제약 — 미확정 |
| `SOR` | Smart Order Routing (KRX/NXT 자동 분배) | ✗ | ✓ | **KIS 공식 「최선집행기준 설명서」에 SOR + 시장가가 NXT로 분배되는 정상 케이스 예시 있음** — 조합 자체가 거부되는 건 아님 |

### 5-1. SOR + 시장가 거부 가능성 (검증 중)

KIS 공식 문서에 SOR + 시장가가 NXT로 분배되어 미체결 시 NXT 애프터마켓까지 유지된다는 예시가 있어 조합 자체가 차단되는 정책은 **아닌 것으로 추정**. 그러나 2026-05-11 계양전기 거부 발생 시점이 SOR 도입 직후라 정황 상관관계는 강함. 검증 후보:
- NXT 미상장 종목에 SOR을 적용했을 때 KIS의 분배 정책
- NXT 운영시간 외(또는 일별 점검) 분배 시 거부
- 특정 시점 단발 호가 차단(동시호가/VI/일별 점검)
- 그 외 KIS 정책 (Developers Q&A 직접 문의 필요)

진단을 위해 Phase A1에서 거부 응답을 `system_logs`에 영구 저장 중. 다음 거부 발생 시 정확한 `msg_cd`/`msg1`/요청 body가 캡처되면 즉시 원인 확정 가능.

### 5-2. 모의투자(VTS) 제약

`SOR`/`NXT`는 실전(real) 한정. VTS에서 `EXCG_ID_DVSN_CD=SOR` 또는 `=NXT`로 호출하면 KIS가 거부할 수 있어, 프론트엔드 Settings는 환경 인식 후 라디오를 disabled 처리한다(`frontend/src/components/Settings/ExchangeBoardRow.tsx`, `ef2993b` 커밋).

### 5-3. NXT 거래가능 사전 조회 — CTPF1002R (Phase G, 2026-05-11)

종목별 NXT 등록/정지 여부를 사전 조회할 수 있는 단건 API. KIS MCP 4질의 결과(2026-05-11) 확정.

| 항목 | 값 |
|------|-----|
| TR_ID | `CTPF1002R` (모의/실전 동일 — 첫 글자 `C` 접두사) |
| Path | `/uapi/domestic-stock/v1/quotations/search-stock-info` |
| 본 프로젝트 함수 | `src/api/condition.py::inquire_stock_basics(pdno) -> StockBasics` |
| Pydantic 모델 | `src/models/stock.py::StockBasics` |
| 캐시 테이블 | `stock_master` (24h TTL, `src/db/stock_master.py`) |

**NXT 사전 판별 핵심 필드 매핑 (50여 개 응답 컬럼 중 6개 사용):**

| KIS 응답 키 | 의미 | 본 프로젝트 사용 |
|-------------|------|----------------|
| `pdno` | 종목코드 | `StockBasics.ticker` |
| `prdt_abrv_name` | 종목약명 | `StockBasics.name` |
| `excg_dvsn_cd` | 거래소구분코드 (02 KOSPI / 03 KOSDAQ 등) | `StockBasics.excg_dvsn_cd` |
| `cptt_trad_tr_psbl_yn` | NXT 거래종목여부 (Y/N) | `nxt_tradable` 파생 |
| `nxt_tr_stop_yn` | NXT 거래정지여부 (Y/N) | `nxt_tradable` 파생 |
| `tr_stop_yn` | KRX 거래정지여부 (Y/N) | `krx_halted` |
| `admn_item_yn` | 관리종목여부 (Y/N) | `admin_item` |

**파생 규칙:** `nxt_tradable = (cptt_trad_tr_psbl_yn == "Y") AND (nxt_tr_stop_yn == "N")`

**MCP 4질의 결과 (B안 채택):**
- (Q1) 종목별 NXT 등록 사전 조회 API 존재? — 존재 (CTPF1002R)
- (Q2) CTPF1002R / CTPF1604R 응답에 NXT 필드? — **CTPF1002R에만 있음**. CTPF1604R(상품기본조회)는 12개 필드뿐
- (Q3) NXT 마스터 일괄 다운로드 REST API? — **없음**. 종목별 단건 조회만 → 24h 캐시 운영
- (Q4) 단일 종목 멀티 거래소(KRX/NXT/SOR) 필드? — 단일 필드 없음. 위 두 필드 조합으로 추론

**호출 경로 (3종):**
1. **거래소 라우팅 사전 다운그레이드** — `OrderEngine._strategy_exchange_async(strategy_id, ticker=...)` → stock_master miss 시 KIS 호출 후 upsert → `nxt_tradable=False`면 NXT/SOR → KRX 강제 + `[nxt_downgrade]` 로그 1행
2. **익일 청산 분기 사전 차단** — `scheduler._execute_next_day_clear`: `stock_master.get(ticker).nxt_tradable=False`이면 시가 폴링/안정화 거치지 않고 즉시 `_pending_next_day_clear` 등록 → 09:00 KRX 시장가 청산
3. **거부 응답 사후 보강** — `execute_sell`이 `is_market_closed_rejection`으로 NXT 거부 받으면 `stock_master.upsert_one(ticker, nxt_tradable=False)` 즉시 반영 (NXT 시간대 한정: 08:00~09:00, 15:30~20:00). 다음 사이클부터 자동 KRX 다운그레이드

**fallback 정책:** stock_master miss + KIS 호출 실패 등 모든 예외 경로는 **전략 기본 exchange 그대로** (보수적 fallback). 시가 수신 휴리스틱은 stock_master 의 2순위 보조 신호로만 유지.

### 5-4. APBK1943 "시장가호가불가" — 매수/매도 양방 거부 (Phase C, 2026-05-11)

**발생 사례 (운영 사고):** 2026-05-11 09:00:21 계양전기(012200) 매도 ×3 실패 → 09:24:46 / 10:05:26 수동 매도 재시도 모두 실패. KRX 메인 시작 직후 발생, NXT 시간대 무관. 동일 msg1이 매수 측에도 발생 가능(4-2절과 동일 거부 사유).

| 항목 | 값 |
|------|-----|
| msg_cd | `APBK1943` |
| msg1 (실측) | "시장가호가불가로 주문이 불가합니다." (띄어쓰기 없음) |
| 발생 시각 | 09:00:21 KST (KRX 메인 시작 16초 후) |
| 거래소 | KRX (NXT 시간대 아님 — 5-3 NXT 사후 보강과 분리) |
| 분류 | `is_market_order_disallowed(err)` True — 키워드 `시장가호가불가` 매칭 |

**msg1 키워드 변형 (`_MARKET_ORDER_DISALLOWED_KEYWORDS` 전체):**
- "시장가매매불가" / "시장가 매매 불가" / "시장가 주문 불가" / "시장가 호가 불가"
- **"시장가호가불가"** ← Phase C 추가 (2026-05-11 계양전기 사고 원문)
- **"최유리/최우선지정가 주문만"** / **"지정가 및 최유리"** ← Phase H1 추가 (2026-05-11 NXT 애프터 APBK3013, 아래 변형 코드 참조)

**변형 코드: APBK3013 — NXT 애프터마켓 시간대 매도 거부 (Phase H1, 2026-05-11)**

| 항목 | 값 |
|------|-----|
| msg_cd | `APBK3013` |
| msg1 (실측) | "[애프터마켓]지정가 및 최유리/최우선지정가 주문만 가능합니다." |
| 발생 시각 | 2026-05-11 16:05:59 / 16:10:45 / 16:28:50 KST (NXT 애프터 시간대) ×3 |
| 거래소 | NXT 애프터 (15:30~20:00) |
| 분류 | `is_market_order_disallowed(err)` True — 키워드 `최유리/최우선지정가 주문만` 매칭 |
| 처리 | APBK1943과 동일 — `execute_sell`이 `step_down(current_price, 5)` 지정가 폴백 1회 자동 작동 |

APBK1943(KRX 메인 거부)과 사유는 다르지만(NXT 애프터는 정책상 지정가만 받음) 후속 동작은 동일 — 시장가→지정가 전환이 정확히 KIS가 요구하는 형태. H1 작업은 **키워드 확장만**이며 폴백 로직 변경 없음. H2(NXT 애프터 시간대 시장가 사전 차단)는 별도 단계.

키워드 선정 안전 가드:
- "지정가" 단독 (X) — 정상 안내 메시지("지정가 주문이 정상 접수")와 충돌
- "애프터마켓" 단독 (X) — 거부 외 메시지에도 출현
- "최유리/최우선지정가 주문만" / "지정가 및 최유리" (O) — 특이성 높음, false positive 없음

**후속 동작 (매수와 매도 대칭, 호가 방향만 반대):**

| 경로 | 폴백 가격 | 호가 방향 | cooldown |
|------|----------|----------|---------|
| `execute_buy` (4-2 / Phase B) | `step_up(current_price, 5)` | 매수호가 ↑ (체결률 ↑) | 폴백 실패 시 `block_low_funds(ticker, 900s)` |
| `execute_sell` (Phase C, 2026-05-11) | `step_down(current_price, 5)` | 매도호가 ↓ (체결률 ↑) | **등록 안 함** — 매도는 청산 의무, 다음 사이클 자연 재트리거 |

**매도 폴백 분기 동작 규칙 (`src/engine/order_engine.py::execute_sell`):**
1. `is_market_order_disallowed(err)` True && `order_division == OrderDivision.MARKET` 일 때만 폴백 (지정가 매도는 의미 없으므로 제외 — 기존 3회 재시도 유지)
2. 현재가는 `src.engine.scanner.ticker_prices[ticker]["current_price"]` 캐시 사용. 캐시 miss(`cur_price<=0`)면 폴백 불가, 일반 재시도 흐름으로 폴백 (매도 의무 보존)
3. 폴백 호출 인자: `side=SELL`, `order_division=LIMIT`, `price=step_down(cur_price,5)`, `exchange=원래 라우팅`, `quantity=pos.quantity`
4. 매핑 동기 등록(`_order_qty`/`_order_strategy`/`_order_ticker`) + `_completed_orders` race 가드 + `insert_trade(PENDING, price=fallback_price)`는 시장가 경로·매수 폴백과 동일 동기 순서 (루트 CLAUDE.md 안전 규칙 준수)
5. 폴백 성공 → `return` (`_selling` 은 체결통보에서 해제)
6. 폴백 실패 → `self._selling.discard(ticker)` + `write_log("WARNING", ...)` + `return` (메모리/DB positions **보존**, 다음 사이클 자연 재트리거)
7. **stock_master 사후 보강 없음** — APBK1943은 시장가 호가 자체 불가 사유라 NXT 거래가능 여부와 무관(5-3 NXT 사후 보강은 `is_market_closed_rejection` 분기 전용)

**회귀 테스트:** `tests/unit/engine/test_order_engine_sell_fallback.py` (6 케이스 + H1 APBK3013 폴백 자동 작동 1건: 폴백 성공 / 폴백 실패 보존 / 지정가 미폴백 / 보유부족 미폴백 / 장운영시간 외 미폴백 / 체결통보 선행 race / **APBK3013 NXT 애프터 폴백**) + `tests/unit/api/test_insufficient_classification.py` (키워드 `시장가호가불가` 분류 + APBK1943 실문 분류 + **APBK3013 실문 분류** + **APBK3013 변형 키워드** + **`지정가` 단독 false positive 가드** + 상호 배타).

---

## 6. 운영 가이드

### 6-1. 새 거부 코드 발견 시 절차

1. `system_logs`(또는 `daily_log_reports.metrics.api_metrics`)에서 prefix `[kis_rejection]` 행 검색
2. `msg_cd`/`msg1`/요청 body 컨텍스트를 회수해 본 표 4절에 추가
3. 분류 헬퍼 신설/확장 시 `src/api/balance.py`에 함수/키워드 추가 + 회귀 테스트(`tests/unit/api/test_insufficient_classification.py`) 보강
4. 후속 동작(매수 락/cooldown/지정가 폴백 등)이 필요하면 `src/engine/order_engine.py`에 분기 추가
5. 루트 `CLAUDE.md` 핵심 안전 규칙 + `src/api/CLAUDE.md`에 한 줄 동기화

### 6-2. KIS 측 직접 문의

확정적 답이 필요한 경우 [KIS Developers 포털](https://apiportal.koreainvestment.com/) Q&A 또는 한국투자증권 OpenAPI 고객센터로 `msg_cd` + 요청 body 컨텍스트를 첨부해 문의. 본 표는 우리 실측 경험과 공개 문서를 통합한 자료이며, KIS 공식 답변이 본 표와 어긋나면 KIS 답변을 진실의 원천으로 한다.

### 6-3. 단일 소스 위치

| 항목 | 위치 |
|------|------|
| 거부 분류 헬퍼 | `src/api/balance.py` (`is_market_closed_rejection` / `is_insufficient_cash` / `is_insufficient_quantity` / `is_market_order_disallowed`) |
| 거부 응답 영구 저장 | `src/api/base.py::_request` → `src/db/system_logs.py::write_log("ERROR", "[kis_rejection] ...")` |
| 매수 지정가 폴백 | `src/engine/order_engine.py::execute_buy` (시장가 거부 시 `step_up(price, 5)` 지정가 1회) |
| 호가단위 헬퍼 | `src/engine/util/tick_size.py::step_up` / `step_down` / `get_tick_size` / `round_to_tick` |
| 거래소 라우팅 | `src/engine/order_engine.py::_strategy_exchange(strategy_id)` — 전략 params `exchange`로 분기 |
