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
