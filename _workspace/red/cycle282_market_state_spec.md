# cycle282 — 장운영상태 함수 + 조회 화면 · Red 명세

- **작업 디렉터리** `/Users/koscom/Projects/auto_stock_wt282` (브랜치 `cycle282-market-state`, base `34f662f`)
- **단계** Red 설계. 이 문서 시점에 **코드·테스트는 하나도 없다**(Green 이 전부 만든다).
- **매매 행위 변경 0.** 읽기 전용 조회 기능이다. 어떤 전략도 이 함수를 아직 호출하지 않는다
  (소비는 후속 주문 사이클이 한다 — 그때 창별 주문유형 매핑의 정본이 이 함수다).
- **무접촉** 8영역(`src/engine/{risk,order_engine,session,scanner,strategy_registry}.py` ·
  `src/api/order.py` · `src/realtime/**` · `src/auth/**`) · `src/engine/scheduler.py` ·
  `src/engine/strategy_base.py` · 전략 7파일.
- **동시 워크트리 주의** `auto_stock_wt280`(시세 전환)과 겹칠 수 있는 파일 = `src/api/condition.py`(추가 1함수) ·
  `src/main.py`(2행) · `frontend/src/App.tsx`(2행) · `frontend/src/test/handlers.ts` ·
  `e2e/fixtures/api-mocks.ts`. 그 외 산출물은 전부 신규 파일이다. **`src/realtime/**` 는 한 글자도 안 건드린다.**

---

## 0. 브리프 대비 정정·추가 (12건) — 값을 바꾼 것이 아니라 *표현할 수 없던 것*을 표현한다

브리프 1절의 표가 정본이다. 값은 하나도 바꾸지 않았다. 아래는 **그 값을 거짓 없이 코드로 옮기려면
반드시 결정해야 하는 것들**이고, 결정마다 근거를 붙였다.

| # | 브리프 | 문제 | 이 명세의 결정 |
|---|---|---|---|
| 정정-1 | K1 유효기간 `09-14~` | 그대로 적용하면 **09-12·09-13 에 KRX 08:20~09:00 행이 사라진다.** 시가 단일가는 수십 년 존재했다. 확신 열이 밝히듯 `09-14~` 는 *행의 신설*이 아니라 **시작 시각 08:20 의 신설 여부**를 가리킨다 | K1 은 `effective_from=None`(상시) · `start=08:20` · `confidence="unconfirmed"` · note 에 "09-14 이전에는 08:30 시작이었을 가능성 — 미확인. 그 경우 이 표는 08:20~08:30 을 과다 표시한다". **13행 유지.** 없애는 거짓(장이 안 열린다고 말함)이 10분 과다 표시보다 크다 |
| 정정-2 | K7 `~09-12` · K6 `09-14~` | 그 사이 **09-13(일) 하루**는 KRX 16:00~20:00 에 행이 0 이다 | 데이터를 넓혀 메우지 **않는다**. 09-13 은 일요일(비거래일)이라 실해가 없고, 넓히면 정본에 없는 값을 지어내는 것이다. `get_market_state(09-13 16:30, KRX)` → `CLOSED` · `row_id=None`. D2·D5 가 이 귀결을 **명시적으로 고정**한다 |
| 정정-3 | "K2·K7 처럼 의도된 중첩" | K6·K7 은 **어떤 날짜에도 공존하지 않는다**(유효기간이 갈린다). 실제 동시 중첩은 **K1 ⊃ K2 하나뿐**이다 | `overlap_ok=True` 는 K2·K7 둘 다에 남기되, 그 의미를 둘로 나눈다 — K2 = *실제* 동시 중첩, K7 = *날짜 무시 검사(B1)에서만* 겹치는 방어 선언. B3 이 "K6·K7 동시 유효 날짜 0" 을 전수로 증명한다 |
| 추가-1 | `MarketPhase` 9종 | N1(NXT 프리마켓, **실시간 접속매매**)을 담을 값이 없다. `REGULAR` 로 두면 08:00~08:50 화면이 "정규장" 톤이 되어 같은 시각 KRX 의 시가 단일가와 모순되고, `AFTER_MARKET` 은 명백히 틀리다 | `PRE_MARKET` **1종 추가 → 10종**. `name_ko` 는 화면 문구, `phase` 는 기계 분류다 |
| 추가-2 | `ORDER_DIVISIONS.exchanges(frozenset)` | frozenset 하나로는 **"미지원"과 "미확인"을 구분할 수 없다** — SOR 의 27~29·41~47 은 미확인인데 빠져 있으면 화면이 "미지원"으로 읽는다. 브리프가 "숨기지 않는다" 고 못박은 바로 그 항목이 조용히 사라진다 | `exchanges_unknown: frozenset[str]` 필드 추가. 화면은 `●`(확정) / `?`(확인 필요) / 빈칸(미지원) 3상태 |
| 추가-3 | `27~29 NXT GTP` · `41~47 KRX 애프터마켓` | **개별 명칭이 정본에 없다** | 지어내지 않는다. `name_ko` = 그룹명, `group_ko` = `"NXT GTP(27~29)"` / `"KRX 애프터마켓(41~47)"`, `confidence="name_unconfirmed"`. 화면은 `코드 + 그룹명 + 확인 필요` |
| 추가-4 | 응답 `markets: {KRX, NXT}` | dict 만 주면 프론트가 `"KRX"`·`"NXT"` 리터럴을 갖게 되어 **M7(하드코딩 0건)과 정면 충돌**한다 | `market_order: ["KRX","NXT"]` 배열 병기. 프론트는 이 배열을 map 한다. dict 는 브리프대로 유지 |
| 추가-5 | "지난 행은 흐리게, 다음 행은 보통" | 지난/현재/다음 판정은 **시각 비교**다. 프론트가 하면 "커서는 서버 판정" 원칙이 그 자리에서 깨진다 | 서버가 행마다 `rel: "past"\|"current"\|"concurrent"\|"upcoming"\|"unknown"` 을 준다. 프론트는 `rel` 로만 스타일링한다 |
| 추가-6 | `is_open` | N5(애프터 단일가)는 **장은 열려 있는데 쓸 주문유형을 모른다**. `is_open = bool(order_divisions)` 로 정의하면 N5 가 "휴장"으로 보인다 | `is_open`(phase 기반: `BREAK`·`CLOSED` 아님)과 `can_order`(`bool(order_divisions)`)를 **분리**. N5 = `is_open=True ∧ can_order=False ∧ confidence="unconfirmed"` |
| 추가-7 | "기존 휴장일 조회 재사용" | `src/api/condition.py:207 is_market_open` 은 **조회 실패 시 True 를 반환**한다(`except: return True`). M10(실패=`null`)을 **구조적으로 만족할 수 없다** | `is_trading_day(target_date) -> bool \| None` **신설**(같은 URL·TR_ID 재사용). `is_market_open`·`next_trading_day` 는 **한 글자도 안 바꾸고** 소스 세그먼트 sha 로 무변경을 증명한다(H5) — 그 둘의 fail-open-True 는 scheduler·strategy_funnel 의 매매 경로 계약이라 이 사이클에서 건드리면 안 된다 |
| 추가-8 | "404/500 규약" | 표가 **코드 상수**라 "데이터 없음" 404 가 원래 성립하지 않는다 | `on_date` preview 파라미터를 넣어 규약을 갈라 정의했다(§3.4). 핵심은 **오늘 표가 비면 200 빈 화면이 아니라 500** 이다 — cycle266 의 `except Exception: rows=[]` fail-silent 재현 차단 |
| 추가-9 | 행 필드 `quote_channel` | 이 표에서 **증거가 가장 약한 필드**다(시장별 상수 가정) | 값은 싣되 `src/realtime/**` 상수와 대조하는 가드를 **두지 않는다**. wt280(시세 전환)이 같은 값을 바꾸는 중이라 그런 가드는 그쪽을 막는다. `evidence="assumed"` 로 표시 |

---

## 1. 산출물 1 — `src/engine/market_state.py` (순수 데이터·함수 leaf)

`src.*` import **0** · I/O **0** · 로깅 **0** · 모듈 로드 시 부작용 **0**. `param_catalog.py` 와 같은 규약이다.

### 1.1 닫힌 어휘 (전부 모듈 상수 tuple — 프론트 가드가 이 목록을 읽는다)

```python
MARKET_ORDER   = ("KRX", "NXT")                                   # 화면 렌더 순서
EXCHANGE_ORDER = ("KRX", "NXT", "SOR")                            # 카탈로그 열 순서
TABLE_VERSION  = "2026-09-11"                                     # 표가 바뀌면 올린다(픽스처가 핀)

class MarketPhase(str, Enum):
    PRE_AUCTION        = "PRE_AUCTION"          # 시가 단일가
    PRE_MARKET         = "PRE_MARKET"           # 프리마켓(연속) — 추가-1
    REGULAR            = "REGULAR"              # 정규장(연속)
    CLOSE_AUCTION      = "CLOSE_AUCTION"        # 종가 단일가
    PRE_CLOSE_FIXED    = "PRE_CLOSE_FIXED"      # 장전 시간외 종가(전일 종가 고정)
    AFTER_CLOSE_FIXED  = "AFTER_CLOSE_FIXED"    # 장후 시간외 종가(당일 종가 고정)
    AFTER_SINGLE       = "AFTER_SINGLE"         # 시간외/애프터 단일가
    AFTER_MARKET       = "AFTER_MARKET"         # 애프터마켓(연속)
    BREAK              = "BREAK"                # 장중 휴장
    CLOSED             = "CLOSED"               # 장 종료(행 없음)

MATCH_KINDS       = ("continuous", "single_auction", "periodic_auction", "fixed_price", "none")
TONES             = ("active", "auction", "fixed", "break", "closed", "unknown")   # 화면 톤
RELS              = ("past", "current", "concurrent", "upcoming", "unknown")       # 표 행 위치
SUPPORT_LEVELS    = ("yes", "unknown", "no")                                       # 카탈로그 셀
CONFIDENCE_LEVELS = ("confirmed", "unconfirmed", "ambiguous")
EVIDENCE_LEVELS   = ("confirmed", "assumed")
```

> **`tone`·`rel`·`support`·`confidence` 는 *표현* 어휘다.** 프론트가 이 네 어휘의 값을 키로 쓰는 것은
> 허용되고(스타일 매핑), **행 id·시각·주문유형 코드·시장명은 허용되지 않는다**(M7). 허용 어휘 목록은
> 프론트에 적지 않고 **픽스처에서 읽는다** — cycle278 `_ast_param_key_hardcode.test.ts` 와 같은 구조다.

### 1.2 행 자료구조

```python
@dataclass(frozen=True, slots=True)
class MarketRow:
    row_id: str                       # "K1".."K7" | "N1".."N6"
    market: str                       # "KRX" | "NXT"
    start: time                       # 반개구간 [start, end) — 끝은 포함하지 않는다
    end: time                         # start < end 필수(자정 넘는 창 없음)
    phase: MarketPhase
    name_ko: str                      # 브리프 "상태" 열 원문
    match_kind: str                   # MATCH_KINDS
    match_ko: str                     # 브리프 "체결" 열 **원문 그대로**
    order_divisions: tuple[str, ...]  # 날짜 해석 **전** 선언 상위집합, 코드 오름차순
    quote_channel: str | None         # 추가-9: evidence="assumed"
    quote_channel_evidence: str       # EVIDENCE_LEVELS
    priority: int                     # 커서 우선순위 — 낮을수록 이김. 10=체인, 20=오버레이
    overlap_ok: bool                  # 다른 행과 겹쳐도 정상
    effective_from: date | None       # None = 상시
    effective_to: date | None         # None = 상시, **그 날짜까지 포함(inclusive)**
    confidence: str                   # CONFIDENCE_LEVELS
    note: str                         # 미확인 사유·경고 원문(화면 배지 툴팁)
```

`ResolvedRow` = `MarketRow` 의 전 필드 + 아래 6 파생(날짜·시각 해석 결과):

| 필드 | 뜻 |
|---|---|
| `order_divisions` (덮어씀) | **그 날짜에 유효한** 코드만. 정렬·중복 없음 |
| `order_divisions_pending` | 선언에는 있으나 **아직** 유효하지 않은 코드(예: 09-12 의 N1 → `("27","28","29")`) |
| `order_divisions_expired` | 선언에는 있으나 **이미** 만료된 코드 |
| `can_order` | `bool(order_divisions)` |
| `market_order_ok` | `"01" in order_divisions` |
| `rel` | `RELS` 중 하나. `get_market_table` 단독 호출 시엔 `"unknown"`, 라우트가 커서와 결합할 때 채운다 |

### 1.3 `MARKET_TABLE` — 13행 전체 값 (브리프 1절 그대로)

**KRX (7행)** — `quote_channel` 전부 `"H0STCNT0"` · `quote_channel_evidence="assumed"`

| row_id | start | end | phase | name_ko | match_kind | match_ko | order_divisions (선언) | pri | overlap_ok | effective_from | effective_to | confidence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `K1` | 08:20 | 09:00 | `PRE_AUCTION` | 시가 단일가 | `single_auction` | `단일가(09:00 일괄)` | `00 01` | 10 | False | **None** (정정-1) | None | `unconfirmed` |
| `K2` | 08:30 | 08:40 | `PRE_CLOSE_FIXED` | 장전 시간외 종가 | `fixed_price` | `전일 종가 고정` | `05` | **20** | **True** | None | None | `confirmed` |
| `K3` | 09:00 | 15:20 | `REGULAR` | 정규장 | `continuous` | `실시간 접속매매` | `00 01 02 03 04 11 12 13 14 15 16 21 22 23 24` | 10 | False | None | None | `confirmed` |
| `K4` | 15:20 | 15:30 | `CLOSE_AUCTION` | 종가 단일가 | `single_auction` | `단일가(15:30 일괄)` | `00 01` | 10 | False | None | None | `confirmed` |
| `K5` | 15:30 | 16:00 | `AFTER_CLOSE_FIXED` | 장후 시간외 종가 | `fixed_price` | `당일 종가 고정` | `06` | 10 | False | None | None | `confirmed` |
| `K6` | 16:00 | 20:00 | `AFTER_MARKET` | 애프터마켓 | `continuous` | `실시간` | `41 42 43 44 45 46 47` | 10 | False | **2026-09-14** | None | `confirmed` |
| `K7` | 16:00 | 18:00 | `AFTER_SINGLE` | 시간외 단일가 | `periodic_auction` | `10분 주기` | `07` | 10 | **True** | None | **2026-09-12** | `confirmed` |

- `K1.note` = `"시작 08:20 이 2026-09-14 개편분인지 미확인(종전 08:30). 09-14 이전 날짜에서는 08:20~08:30 을 과다 표시할 수 있다."`
- `K6.note` = `"2026-09-14 신설(공지). 시장가 없음 — 41~47 만."`
- `K7.note` = `"2026-09-12 폐지. K6 과는 유효기간이 갈려 어떤 날짜에도 공존하지 않는다(B3)."`
- `K2.note` = `"K1(시가 단일가) 안에 들어 있는 의도된 중첩. 08:30~08:40 에는 00·01·05 가 동시에 쓸 수 있다."`

**NXT (6행)** — `quote_channel` 전부 `"H0NXCNT0"` · `quote_channel_evidence="assumed"`

| row_id | start | end | phase | name_ko | match_kind | match_ko | order_divisions (선언) | pri | overlap_ok | eff_from | eff_to | confidence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `N1` | 08:00 | 08:50 | `PRE_MARKET` | 프리마켓 | `continuous` | `실시간` | `00 03 04 11 12 13 14 15 16 21 22 23 24 27 28 29` | 10 | False | None | None | `confirmed` |
| `N2` | 08:50 | 09:00 | `BREAK` | 휴장 | `none` | `—` | (없음) | 10 | False | None | None | `confirmed` |
| `N3` | **09:00:30** | 15:20 | `REGULAR` | 정규장 | `continuous` | `실시간` | `00 03 04 11 12 13 14 15 16 21 22 23 24` | 10 | False | None | None | `unconfirmed` |
| `N4` | 15:20 | 15:30 | `BREAK` | 휴장 | `none` | `—` | (없음) | 10 | False | None | None | `confirmed` |
| `N5` | 15:30 | 15:40 | `AFTER_SINGLE` | 애프터 단일가 | `single_auction` | `단일가` | **(없음 — 미확인)** | 10 | False | None | None | `unconfirmed` |
| `N6` | 15:40 | 20:00 | `AFTER_MARKET` | 애프터마켓 | `continuous` | `실시간` | `00 03 04 11 12 13 14 15 16 21 22 23 24` | 10 | False | None | None | `confirmed` |

- `N1.note` = `"27~29(GTP)는 2026-09-14 부터 유효 — 그 이전 날짜에는 order_divisions_pending 으로 빠진다."`
- `N3.note` = `"시작 09:00:30 미확인. 09:00:00~09:00:29 은 N2(휴장)로 남는다 — 표대로 옮겼을 뿐 실측 근거는 없다."`
- `N5.note` = `"단일가 구간인 것은 확정이나 **쓸 수 있는 주문유형이 미확인**이다. NXT 코드 목록에 단일가 전용 코드가 없다. is_open=True 이지만 can_order=False 다 — 이 구간의 주문 가능 여부를 이 표로 판단하지 말 것."`
- `N2.note` / `N4.note` = `"휴장 — 주문 접수 불가."`

> **09:00:00~09:00:29 의 N2 유지는 의도된 결과다.** N3 의 시작이 미확인이라 표를 그대로 옮기면 30초의
> 휴장 꼬리가 생긴다. 이 30초를 임의로 09:00:00 으로 당기면 *미확인 값을 확정 값으로 바꾸는* 것이다.
> C-f 가 이 30초를 **명시적으로** 고정하고 화면은 그 행에 `확인 필요` 배지를 단다.

### 1.4 `ORDER_DIVISIONS` — 28 코드 전체

`exchanges` = 확정 가용 · `exchanges_unknown` = 미확인. 둘 다 ⊆ `EXCHANGE_ORDER`, 교집합 ∅.

| code | name_ko | group_ko | exchanges | exchanges_unknown | effective_from | effective_to | confidence |
|---|---|---|---|---|---|---|---|
| `00` | 지정가 | — | KRX NXT SOR | — | None | None | confirmed |
| `01` | 시장가 | — | **KRX SOR** | — | None | None | confirmed |
| `02` | 조건부지정가 | — | KRX | — | None | None | confirmed |
| `03` | 최유리지정가 | — | KRX NXT SOR | — | None | None | confirmed |
| `04` | 최우선지정가 | — | KRX NXT SOR | — | None | None | confirmed |
| `05` | 장전시간외 | — | **KRX** | — | None | None | confirmed |
| `06` | 장후시간외 | — | **KRX** | — | None | None | confirmed |
| `07` | 시간외단일가 | — | **KRX** | — | None | **2026-09-12** | confirmed |
| `11` | IOC지정가 | IOC/FOK | KRX NXT SOR | — | None | None | confirmed |
| `12` | FOK지정가 | IOC/FOK | KRX NXT SOR | — | None | None | confirmed |
| `13` | IOC시장가 | IOC/FOK | KRX NXT SOR | — | None | None | confirmed |
| `14` | FOK시장가 | IOC/FOK | KRX NXT SOR | — | None | None | confirmed |
| `15` | IOC최유리 | IOC/FOK | KRX NXT SOR | — | None | None | confirmed |
| `16` | FOK최유리 | IOC/FOK | KRX NXT SOR | — | None | None | confirmed |
| `21` | 중간가 | 중간가/스톱 | KRX NXT | — | None | None | confirmed |
| `22` | 스톱지정가 | 중간가/스톱 | KRX NXT | — | None | None | confirmed |
| `23` | 중간가IOC | 중간가/스톱 | KRX NXT | — | None | None | confirmed |
| `24` | 중간가FOK | 중간가/스톱 | KRX NXT | — | None | None | confirmed |
| `27` | NXT GTP | NXT GTP(27~29) | NXT | **SOR** | **2026-09-14** | None | `name_unconfirmed` |
| `28` | NXT GTP | NXT GTP(27~29) | NXT | **SOR** | **2026-09-14** | None | `name_unconfirmed` |
| `29` | NXT GTP | NXT GTP(27~29) | NXT | **SOR** | **2026-09-14** | None | `name_unconfirmed` |
| `41`~`47` (7행) | KRX 애프터마켓 주문유형 | KRX 애프터마켓(41~47) | KRX | **SOR** | **2026-09-14** | None | `name_unconfirmed` |

`CONFIDENCE_LEVELS` 에 `name_unconfirmed` 를 넣지 않는다 — 코드 카탈로그는 별도 어휘
`DIVISION_CONFIDENCE = ("confirmed", "name_unconfirmed", "unconfirmed")` 를 쓴다(행의 확신과 성질이 다르다:
**존재는 확정, 이름만 모른다**).

### 1.5 표가 드러낸 것 — 응답에 `findings` 로 실어 화면에 그대로 띄운다

```python
FINDINGS = (
  "NXT 에 시장가(01)가 없다. 우리 주문의 1차 유형이 시장가다. 프리장 지정가 사전 변환은 "
  "우회가 아니라 구조적 필연이었다. 대안은 13 IOC시장가 / 14 FOK시장가다.",
  "SOR 에 시간외 코드(05·06·07)가 없다. 현재 전 주문이 SOR 이므로 시간외 구간에는 주문 수단이 없다.",
)
BOARD_VS_MARKET_NOTE = (
  "이 화면은 **거래소의 실제 장 운영 상태**다. 우리 시스템의 매매 보드(PRE_NXT/MAIN/POST_NXT)와는 "
  "경계가 다르다 — 우리 MAIN 보드는 15:39:59 까지지만 KRX 정규장은 15:20 에 끝난다. "
  "보드는 우리 매매 규약이고 이 표는 거래소 사실이다. 둘을 같은 것으로 읽지 말 것."
)
UNCONFIRMED_NOTE = (
  "⚠️ 표시 항목은 아직 KIS 정본으로 확인하지 못했다. 이 사이클은 추측으로 채우지 않고 그대로 드러낸다. "
  "확인 경로 = KIS MCP 스펙 조회 + 2026-09-14 이후 실측."
)
```

### 1.6 중첩과 커서 우선순위 — 이 사이클의 핵심 규칙

**중첩은 두 종류다. 둘을 섞으면 표가 거짓말을 한다.**

| 종류 | 사례 | 성질 | 표현 |
|---|---|---|---|
| **동시 중첩** | K1(08:20~09:00) ⊃ K2(08:30~08:40) | 두 상태가 **같은 순간에 둘 다 살아 있다.** 08:35 에는 00·01(시가 단일가)과 05(장전 시간외)를 **동시에** 쓸 수 있다 | `priority` 로 커서 1개를 고르고, 나머지는 `concurrent_row_ids` 로 남긴다. `order_divisions` 는 **합집합** |
| **날짜 분리 중첩** | K6(16:00~20:00, 09-14~) vs K7(16:00~18:00, ~09-12) | 시각만 보면 겹치지만 **유효기간이 갈려 공존하는 날이 하루도 없다** | `overlap_ok=True` 는 *날짜 무시 검사(B1)* 를 통과시키는 방어 선언일 뿐이고, **날짜 인지 검사(B2·B3)가 실제 공존 0 을 증명**한다 |

**우선순위 규칙 (명문)**

1. 커서 후보 = `market` 이 같고, `on_date` 에 유효하고, `start <= t < end` 인 행 전부.
   **구간은 반개구간 `[start, end)`** — 끝은 포함하지 않는다. 09:00:00 은 K1 이 아니라 K3 다.
2. 정렬 키 = `(priority, start, row_id)`. **첫 원소가 커서**다. 낮은 `priority` 가 이긴다.
3. `priority` 는 **행마다 리터럴로 적는다.** 창 길이·목록 순서·`overlap_ok` 에서 **파생하지 않는다** —
   파생 규칙은 데이터가 바뀌는 날 조용히 뒤집힌다.
   - `10` = **체인 행**(그 시장·그 날짜의 시간축을 나누는 행) — K1·K3·K4·K5·K6·K7·N1~N6
   - `20` = **오버레이 행**(체인 행 안에 얹히는 행) — K2
4. `priority` 동률이 둘 이상이면 **데이터 결함**이다. 커서는 여전히 결정론적으로 고르되
   (`(priority, start, row_id)` 최소), `confidence="ambiguous"` 로 **시끄럽게** 표시한다.
   B2 가 현재 데이터에서 동률이 0 임을 전수로 증명하므로 이 분기는 평시에 도달하지 않는다.
5. 커서가 K1(시가 단일가)이고 K2 가 동시인 08:30~08:40 에서 **`order_divisions` 는 `("00","01","05")` 합집합**이다.
   사용자의 질문("지금 어떤 호가유형을 쓸 수 있나")의 답은 합집합이지 커서 행 단독이 아니다.
   행별 내역은 `order_divisions_by_row` 가 따로 보존한다.

**왜 K1 이 커서이고 K2 가 오버레이인가** — K1 은 09:00 의 시가를 결정하는 KRX 본 세션의 시작이고
K2 는 그 안에서 10분간 열리는 별도 체결 방식이다. 화면의 "지금 장 상태" 는 K1 이어야 하고,
K2 는 "동시에 열려 있는 창" 으로 보여야 한다. 반대로 두면 08:35 에 화면이 "장전 시간외 종가" 라고
말하면서 시장가 주문이 가능하다고 표시하게 된다(모순).

### 1.7 날짜 차원 — `effective_from` / `effective_to`

```python
def _is_effective(row, on_date) -> bool:
    if row.effective_from is not None and on_date < row.effective_from:
        return False
    if row.effective_to is not None and on_date > row.effective_to:   # inclusive
        return False
    return True
```
같은 판정을 `ORDER_DIVISIONS` 에도 **독립으로** 적용한다. **행 유효성과 코드 유효성은 별개의 두 필터이고 둘 다 적용된다.**

```python
def _resolve_divisions(row, on_date) -> tuple[tuple, tuple, tuple]:
    """(유효, pending, expired) — 셋의 합집합이 row.order_divisions 와 같다."""
```

**09-12 · 09-13 · 09-14 · 09-15 경계 동작 (전수)**

| on_date | 요일 | KRX 행 | NXT 행 | 특기 |
|---|---|---|---|---|
| 2026-09-11 (금) | 거래일 | K1 K2 K3 K4 K5 **K7** | N1~N6 | N1 divisions **13개**(27~29 pending). KRX 16:00~18:00 = K7, **18:00~20:00 행 없음(CLOSED)** |
| 2026-09-12 (토) | 비거래일 | K1 K2 K3 K4 K5 **K7** | N1~N6 | K7 의 **마지막 유효일**. 표는 시각만 보므로 행은 그대로 나오고, 라우트의 `is_trading_day=false` 가 화면에 "휴장일" 을 띄운다 |
| 2026-09-13 (일) | 비거래일 | K1 K2 K3 K4 K5 — **K6·K7 둘 다 없음** | N1~N6 | 정정-2. KRX **16:00~20:00 에 행이 0** → 그 시각 `get_market_state` = `CLOSED`·`row_id=None`. 데이터로 메우지 않는다 |
| 2026-09-14 (월) | 거래일 | K1 K2 K3 K4 K5 **K6** | N1~N6 | **전환일.** K6 등장·K7 소멸. N1 divisions **16개**(27~29 유효). KRX 16:00~20:00 = 애프터마켓 |
| 2026-09-15 (화) | 거래일 | 09-14 와 행 id 집합 동일 | 동일 | D4 가 항등을 고정 |

> 라우트가 `on_date` 없이 부르면 표는 **KST 오늘** 기준이다. 자정을 넘긴 순간 표와 커서가 다른 날짜를
> 보면 안 되므로 라우트는 `as_of` 를 **한 번만** 계산해 두 함수에 **같은 값**을 넘긴다(G5·H6).

### 1.8 `get_market_state` — 시그니처와 알고리즘

```python
def get_market_state(now: datetime | None = None, *, market: str = "KRX") -> MarketState:
```

반환 `MarketState` (frozen dataclass):

| 필드 | 타입 | 뜻 | 브리프 |
|---|---|---|---|
| `market` | str | `"KRX"` / `"NXT"` | 추가 |
| `market_label_ko` | str | `"KRX(한국거래소)"` / `"NXT(넥스트레이드)"` | 추가 |
| `as_of` | datetime (KST aware) | **판정에 쓴 그 순간** | 추가 |
| `on_date` | date | `as_of` 의 KST 날짜 = 표 유효일 | 추가 |
| `row_id` | str \| None | **커서.** 행 없으면 None | 브리프 |
| `phase` | MarketPhase | 행 없으면 `CLOSED` | 브리프 |
| `name_ko` | str | 행 없으면 `"장 종료"` | 브리프 |
| `tone` | str | `TONES` — 화면 톤(행 없으면 `closed`) | 추가-5 계열 |
| `window` | (time, time) \| None | 커서 행의 창 | 브리프 |
| `match_kind` / `match_ko` | str | 행 없으면 `"none"` / `"—"` | 추가 |
| `is_open` | bool | `phase not in (BREAK, CLOSED)` | 브리프 |
| `can_order` | bool | `bool(order_divisions)` | 추가-6 |
| `market_order_ok` | bool | **`"01" in order_divisions`** (M6) | 브리프 |
| `order_divisions` | tuple[str,…] | 동시 유효 행 **합집합**, 날짜 해석 후, 코드 오름차순 | 브리프 |
| `order_divisions_by_row` | tuple[(row_id, tuple[str,…]),…] | 행별 내역 | 추가 |
| `concurrent_row_ids` | tuple[str,…] | 커서 제외 동시 유효 행 | 추가 |
| `quote_channel` | str \| None | evidence=assumed | 브리프 |
| `decided_by` | str | **항상 `"time"`** (H4 가 `"code"` 리터럴 0 을 봉인) | 브리프 |
| `code_seen` | str \| None | **항상 None** | 브리프 |
| `confidence` | str | `CONFIDENCE_LEVELS` — 아래 규칙 | 브리프 |
| `confidence_notes` | tuple[str,…] | 확신을 떨어뜨린 행들의 `note` | 추가 |
| `seconds_to_next` | int \| None | 다음 경계까지 **올림(ceil)** 초. 오늘 남은 경계 없으면 None | 브리프 |
| `next_boundary` | time \| None | 그 경계 시각 | 추가 |
| `next_row_id` | str \| None | 그 경계 시각의 커서 row_id (장 종료면 None) | 브리프 |
| `next_phase` | MarketPhase \| None | 그 경계 시각의 phase | 추가 |

`confidence` 규칙 — `ambiguous`(priority 동률) > `unconfirmed`(커서 또는 동시 행 중 하나라도
`unconfirmed`) > `confirmed`. 행이 없는 `CLOSED` 는 **`confirmed`** 다(장이 안 열린 것은 확실하다).

**알고리즘**

```
1. now   = _coerce_kst(now)                # §1.9
2. market= market.upper();  market not in MARKET_ORDER -> ValueError
3. on_date = now.date();  t = now.time()   # tz 제거 후 벽시계
4. rows = [r for r in MARKET_TABLE if r.market == market and _is_effective(r, on_date)]
5. live = sorted([r for r in rows if r.start <= t < r.end], key=(priority, start, row_id))
6. cursor = live[0] if live else None
7. divisions = 정렬(set().union(*(_resolve_divisions(r, on_date)[0] for r in live)))
8. bounds = sorted({r.start for r in rows} | {r.end for r in rows})
9. nb = 첫 b in bounds with b > t        # 없으면 None
10. seconds_to_next = ceil((combine(on_date, nb, KST) - now).total_seconds()) if nb else None
    -> max(0, ...) 클램프. 19:59:59.5 는 **1** 이지 0 이 아니다(C-j)
11. next_* = _resolve_at(nb, market, on_date)  # 헬퍼 재사용, 재귀 아님
```

- **재귀 금지** — `_resolve_at(t, market, on_date) -> MarketRow | None` 를 내부 헬퍼로 두고
  `get_market_state` 가 두 번 부른다(지금 / 다음 경계). `get_market_state` 가 자기를 부르면
  경계마다 한 단계씩 더 파고들어 비용이 커지고 테스트가 어려워진다.
- **20:00 이후** — 남은 경계 없음 → `seconds_to_next=None`·`next_row_id=None`·`next_phase=None`.
  **다음 날로 굴리지 않는다**: 내일이 거래일인지 모르는 순수 함수가 "10시간 뒤 프리마켓" 이라고
  말하면 금요일 밤에 거짓이 된다. 화면은 `"오늘 장 종료"` 로 표시한다.
- **`t` 가 첫 경계보다 이르면**(예: 03:00) `phase=CLOSED`·`row_id=None`·`next_row_id` = 그날 첫 행.

### 1.9 KST 강제 (`_coerce_kst`)

```python
_KST = timezone(timedelta(hours=9))

def _coerce_kst(now: datetime | None) -> datetime:
    if now is None:            return datetime.now(_KST)
    if now.tzinfo is None:     return now.replace(tzinfo=_KST)   # naive = KST 로 간주
    return now.astimezone(_KST)                                   # 다른 tz = 변환
```

- `None` → **KST 현재**. `datetime.now()`(naive 로컬)를 쓰면 컨테이너 TZ 가 바뀌는 날 조용히 틀린다.
- naive → **KST 로 간주**(프로젝트 규약). `datetime.utcnow()` 를 넘기면 9시간 틀리므로,
  **라우트는 반드시 aware KST 를 넘긴다**(H6 이 라우트의 `datetime.now(` 1회 호출을 잠근다).
- 다른 tz aware → `astimezone` 변환. `00:30Z` 는 `09:30 KST` = 정규장이다(E3).
- 반환 `as_of.tzinfo` 는 KST 이고 `on_date` 는 **KST 기준 날짜**다. `23:00Z` 는 KST 익일 08:00 이므로
  `on_date` 가 하루 앞선다(E5).

### 1.10 `get_market_table` — 시그니처

```python
def get_market_table(on_date: date | None = None) -> tuple[ResolvedRow, ...]:
```

- `on_date=None` → **KST 오늘**.
- **두 시장 전부** 반환. 정렬 = `(MARKET_ORDER.index(market), start, priority, row_id)`.
- **날짜 해석을 마친 행**을 돌려준다. 선언 상위집합을 그대로 내보내면 09-12 화면에 27~29 가 떠서
  거짓이 된다. 빠진 코드는 삭제가 아니라 `order_divisions_pending` / `_expired` 로 **보인다**.
- `rel` 은 이 함수 단독 호출 시 `"unknown"` — 커서와 결합하는 것은 라우트의 일이다(§3.2).

---

## 2. 산출물 2 — `src/api/condition.py` 추가 함수 1개 (추가-7)

```python
async def is_trading_day(target_date) -> "bool | None":
    """KIS 휴장일 API(CTCA0903R)로 개장 여부를 **3상태**로 반환한다.

    True  = opnd_yn == "Y"          (확정 개장)
    False = opnd_yn == "N"          (확정 휴장)
    None  = 조회 실패 / 응답에 그 날짜 행 없음 / 예외  ← **모른다**

    `is_market_open()` 과 의도적으로 다르다. 그 함수는 실패 시 **True**(영업일 가정)를 반환하는데,
    그건 매매 경로(scheduler·strategy_funnel)의 fail-open 계약이라 바꾸면 안 된다. 반면 화면은
    "모른다" 를 "개장" 으로 보여주면 안 된다(M10). 그래서 같은 호출을 3상태로 감싼 함수를 새로 만든다.
    """
```

- URL·TR_ID 는 기존 `HOLIDAY_URL` / `"CTCA0903R"` 를 **그대로** 쓴다. 호출은 `kis_get_quote` 경유.
- **`is_market_open` 과 `next_trading_day` 는 한 글자도 안 바꾼다.** H5 가
  `ast.get_source_segment(src, fn)` 의 sha256 으로 무변경을 증명한다
  (⚠️ `ast.dump` 의 sha 는 파이썬 3.12(CI)/3.13(로컬) 출력이 달라 로컬 초록·CI 실패가 난다 — 금기).
- 파싱 루프가 `is_market_open` 과 ~6줄 중복된다. **받아들인 부채**다 — 공통화하려면 기존 함수를
  고쳐야 하고 그게 이 사이클의 무접촉 범위를 매매 경로로 넓힌다. H5 가 그 둘이 같은 URL·TR 을
  쓰는지만 확인한다.

---

## 3. 산출물 3 — 라우트 `GET /api/market-state`

신규 파일 `src/routes/market_state.py` + `src/main.py` `include_router` 1행.
`router = APIRouter(prefix="/api/market-state", tags=["market-state"])`, 핸들러 경로 `""`.

### 3.1 응답 JSON 전체 (ApiResponse `data`)

```jsonc
{
  "table_version": "2026-09-11",
  "as_of_kst": "2026-09-11T13:05:22+09:00",   // 실제 지금 (preview 여도 지금)
  "on_date": "2026-09-11",                     // 표의 유효일
  "preview": false,                            // on_date 가 오늘과 다르면 true
  "cursor_disabled_reason": null,              // preview 면 "preview_other_date"

  "is_trading_day": true,                      // true | false | **null**(확인 불가)
  "trading_day_source": "kis",                 // "kis" | "cache" | "unknown"

  "market_order": ["KRX", "NXT"],              // 추가-4 — 프론트 렌더 순서
  "exchange_order": ["KRX", "NXT", "SOR"],     // 카탈로그 열 순서

  "markets": {                                 // preview 면 **null**
    "KRX": {
      "market": "KRX", "market_label_ko": "KRX(한국거래소)",
      "row_id": "K3", "phase": "REGULAR", "name_ko": "정규장", "tone": "active",
      "window": {"start": "09:00:00", "end": "15:20:00"},
      "match_kind": "continuous", "match_ko": "실시간 접속매매",
      "is_open": true, "can_order": true, "market_order_ok": true,
      "order_divisions": ["00","01","02","03","04","11","12","13","14","15","16","21","22","23","24"],
      "order_divisions_by_row": [{"row_id":"K3","codes":["00","01", "..."]}],
      "concurrent_row_ids": [],
      "quote_channel": "H0STCNT0", "quote_channel_evidence": "assumed",
      "decided_by": "time", "code_seen": null,
      "confidence": "confirmed", "confidence_notes": [],
      "seconds_to_next": 8078, "next_boundary": "15:20:00",
      "next_row_id": "K4", "next_phase": "CLOSE_AUCTION"
    },
    "NXT": { "...": "동일 형태" }
  },

  "table": [                                   // 두 시장 전부, 날짜 해석 완료
    {
      "row_id": "K1", "market": "KRX",
      "start": "08:20:00", "end": "09:00:00",
      "phase": "PRE_AUCTION", "name_ko": "시가 단일가", "tone": "auction",
      "match_kind": "single_auction", "match_ko": "단일가(09:00 일괄)",
      "order_divisions": ["00","01"],
      "order_divisions_pending": [], "order_divisions_expired": [],
      "can_order": true, "market_order_ok": true,
      "quote_channel": "H0STCNT0", "quote_channel_evidence": "assumed",
      "overlap_ok": false, "priority": 10,
      "effective_from": null, "effective_to": null,
      "confidence": "unconfirmed",
      "note": "시작 08:20 이 2026-09-14 개편분인지 미확인(종전 08:30). ...",
      "rel": "past"                            // 서버 판정 (추가-5)
    }
    // ... 그 날짜에 유효한 행 전부
  ],

  "order_divisions": [                         // 28행 카탈로그
    {
      "code": "01", "name_ko": "시장가", "group_ko": null,
      "exchange_support": {"KRX": "yes", "NXT": "no", "SOR": "yes"},
      "effective_from": null, "effective_to": null,
      "confidence": "confirmed", "note": ""
    }
    // ...
  ],

  "phases":  [{"id":"REGULAR","label_ko":"정규장","tone":"active"}, "..."],
  "vocab":   {"tones":[...], "rels":[...], "support_levels":[...],
              "confidences":[...], "division_confidences":[...]},

  "findings":   ["NXT 에 시장가(01)가 없다. ...", "SOR 에 시간외 코드(05·06·07)가 없다. ..."],
  "board_note": "이 화면은 거래소의 실제 장 운영 상태다. ...",
  "unconfirmed_note": "⚠️ 표시 항목은 아직 KIS 정본으로 확인하지 못했다. ..."
}
```

**`exchange_support` 가 `exchanges`/`exchanges_unknown` 을 대신 실어 나른다** — 프론트는
`exchange_order` 를 돌며 `exchange_support[ex]` 를 읽어 `data-support` 에 그대로 박는다.
`"yes"` = ● · `"unknown"` = ? · `"no"` = 빈칸. 프론트에 거래소 이름 리터럴이 필요 없다.

### 3.2 `rel` — 커서와 표의 결합 (M9 의 실행)

라우트가 두 markets 의 커서를 계산한 **뒤** 표의 각 행에 `rel` 을 채운다:

```
row.rel = "current"     if row.row_id == markets[row.market].row_id
        = "concurrent"  if row.row_id in markets[row.market].concurrent_row_ids
        = "past"        if row.end   <= t
        = "upcoming"    if row.start >  t
        = "unknown"     if preview (markets is None)
```
`t` 는 `as_of` 하나에서만 나온다. 그래서 **표와 커서가 갈라질 수 없다** — 이것이 M9 다.
(경계 밖인데 past 도 upcoming 도 아닌 행은 정의상 없다: `start <= t < end` 면 current/concurrent 다.)

### 3.3 휴장일 결합 — 캐시 + fail-open null

```python
_TRADING_DAY_CACHE: dict[date, tuple[float, bool | None]] = {}   # date -> (expires_at, value)
_TRADING_DAY_NEG_TTL = 60.0        # 실패는 60초만 캐시
_TRADING_DAY_MAX = 64              # 상한 초과 시 가장 오래된 키 제거(삽입 순서)
_TRADING_DAY_TIMEOUT = 5.0         # asyncio.wait_for — 화면 폴링이 KIS 지연에 물리지 않게

def invalidate_market_state_cache() -> None: ...   # 리포 관례 invalidate_*
```

- **성공(True/False)은 만료 없이 캐시**한다 — 어떤 날짜가 거래일인지는 바뀌지 않는다.
- **실패(None)는 60초만 캐시**한다. 영구 캐시하면 KIS 가 5분 만에 살아나도 화면이 하루 종일
  "확인 불가" 다. 반대로 캐시를 안 하면 KIS 장애 중 30초 폴링이 매번 5초를 기다린다.
- `trading_day_source` = `"kis"`(이번에 조회) / `"cache"`(캐시 적중) / `"unknown"`(값이 None).
- **임의 True/False 금지**(M10). 타임아웃·예외·행 없음은 전부 `None` 이다.

### 3.4 상태 코드 규약 — 404 는 왜 거의 없는가

표는 **코드 상수**다. "데이터가 없다" 는 상황이 원래 성립하지 않는다. 그래서 404 를 억지로 만들지 않고
아래처럼 갈라 정의한다. 핵심은 **오늘 표가 비면 200 빈 화면이 아니라 500** 이라는 것이다 —
cycle266 의 `except Exception: rows = []` 가 진짜 DB 장애를 404 로 3개월 은폐한 그 실패를 되풀이하지 않는다.

| 상황 | 코드 | 본문 |
|---|---|---|
| 정상 | **200** | 위 §3.1 |
| 휴장일 조회 실패·타임아웃 | **200** | `is_trading_day: null` · `trading_day_source: "unknown"` (M10) |
| `on_date` 형식 오류 | **422** | FastAPI `date` 파싱 |
| `on_date` 가 `[today-365, today+365]` 밖 | **422** | `detail` 에 허용 범위 |
| `on_date` = 다른 날짜, 그 날짜에 유효 행 0(양 시장 합) | **404** | `message="no_effective_rows"` |
| **오늘** 날짜에 유효 행 0 | **500** | `message="market_table_empty"` — 사용자 입력 문제가 아니라 **데이터 결함**이다 |
| leaf 예외 | **500** | 흡수 금지. 200 빈 응답으로 바꾸지 않는다 |
| `market` 값 이상 | (도달 불가) | 라우트가 `MARKET_ORDER` 상수만 돌린다. leaf 는 `ValueError` |

인증은 기존 `ApiAuthMiddleware` 가 전 경로에 그대로 적용된다(별도 처리 없음).

---

## 4. 산출물 4 — 골든 픽스처 (목이 코드에서 나온다)

cycle266 의 교훈: MSW·Playwright·컴포넌트 목 셋이 **의도한 계약**만 담고 **실제 응답**을 담지 않으면
3개월 초록이어도 화면은 고장 나 있다. cycle278 패턴을 그대로 따른다.

- 생성기 `tools/test_fixtures/gen_market_state_fixture.py`
- 산출 ① `frontend/src/test/fixtures/marketState.fixture.ts` (MSW + vitest + M7 가드의 금지어 목록)
- 산출 ② `e2e/fixtures/market-state.fixture.ts` (Playwright)
- 목 3곳 갱신 — `frontend/src/test/handlers.ts` · `e2e/fixtures/api-mocks.ts`(LIFO: 광역 먼저·구체 나중) ·
  컴포넌트 테스트는 픽스처를 직접 import
- **손으로 고치지 않는다.** I1·I2 가 파일 == 생성기 산출을 byte 로 비교하고, I3 이 픽스처 == 실응답을
  필드별로 비교한다. 표가 바뀌면 생성기를 다시 돌린다.
- 픽스처는 **세 시각 변종**을 담는다 — `AT_0835`(K1⊃K2 동시 중첩) · `AT_1305`(평범한 정규장) ·
  `AT_2030`(장 종료, `seconds_to_next=null`). 프론트 테스트가 이 셋으로 돈다.

---

## 5. 산출물 5 — 프론트 신규 페이지 `장운영상태`

`frontend/src/pages/MarketState.tsx` (신규) · `frontend/src/api/market-state.ts` (신규) ·
`frontend/src/types/market-state.ts` (신규) · `frontend/src/App.tsx` 2행 추가
(`navItems` **맨 끝**에 `{ to: '/market-state', label: '장운영상태' }` + `<Route path="/market-state" …>`,
`lazy()` import). 맨 끝에 넣는 이유 = 기존 e2e 의 나브 인덱스 가정을 건드리지 않는다.

### 5.1 화면 구성

**(0) 헤더** — `as_of_kst`(`Intl.DateTimeFormat`, `timeZone: 'Asia/Seoul'` 명시) · 거래일 배지
(`개장일` / `휴장일` / `확인 불가`) · 수동 새로고침 · `preview` 면 배너.

**(1) 현재 상태 카드 2개** (`market_order` 순) — 카드마다:
- 시장 라벨(`market_label_ko`) · 상태명(`name_ko`) · phase 배지(`tone` 으로 색) · 창(`window`)
- **남은 시간 카운트다운** + `next_row_id`/`next_phase` 로 "다음: 종가 단일가"
- **시장가 가능 여부 배지** — `market_order_ok` (`data-ok`). NXT 는 상시 불가라 **빨강**이고
  `findings[0]` 이 그 이유를 아래에서 설명한다
- **주문 접수 가능 배지** — `can_order`. N5 처럼 `is_open && !can_order` 면 `"주문유형 확인 필요"`
- **지금 쓸 수 있는 주문유형 칩 목록** — `order_divisions` 를 카탈로그와 조인해 `코드 + 이름`
- **동시에 열린 창** — `concurrent_row_ids` 를 그 행의 `name_ko` 칩으로
- `confidence != "confirmed"` 면 **확인 필요 배지** + `confidence_notes` 툴팁

**(2) 커서 표** — 시장별 섹션, 행마다 `row_id · 시각 · 상태 · 체결 · 주문유형 칩 · 유효기간 · 확신`.
- `rel="current"` → **좌측 막대 + 배경 강조**, `rel="concurrent"` → 점선 좌측 막대,
  `rel="past"` → 흐리게(`opacity`), `rel="upcoming"` → 보통, `rel="unknown"` → 보통
- `order_divisions_pending` 이 있으면 그 코드들에 `"(시행일부터)"` 배지 — **숨기지 않는다**
- `confidence != "confirmed"` 행에 ⚠️ 배지 + `note`

**(3) 주문유형 카탈로그 표** — 28행 × (`code` · 이름 · 그룹 · KRX · NXT · SOR · 유효기간 · 비고).
거래소 셀은 `exchange_support` 값 그대로: `●`(yes) / `?`(unknown, 확인 필요 색) / 빈칸(no).
표 아래 `findings` 2건을 콜아웃으로.

**(4) 바닥** — `board_note`(보드 vs 장상태 차이 한 줄) + `unconfirmed_note`.

### 5.2 폴링·카운트다운 규약 (원칙 3의 실행)

```ts
useQuery({ queryKey: ['market-state'], queryFn: fetchMarketState,
           refetchInterval: 30_000, retry: 2, staleTime: 0, refetchOnWindowFocus: true })
```
- **커서는 서버가 판정한다.** 프론트는 `rel`·`row_id`·`seconds_to_next` 를 받아 그릴 뿐이다.
- 카운트다운만 클라이언트가 그린다:
  `remaining = max(0, seconds_to_next - (Date.now() - dataUpdatedAt)/1000)`.
  **로컬 시계의 절대값을 쓰지 않는다 — 두 시각의 *차이*(경과 시간)만 쓴다.** 이건 KST 규약 위반이
  아니다(tz 와 무관한 스톱워치). `getHours`/`getMinutes`/`getDay`/`getDate` 는 **0건**(FE20).
- `remaining` 이 0 에 닿으면 **행을 새로 계산하지 않고 `refetch()` 를 1회** 호출한다
  (`useRef` 로 중복 호출 방지). 다음 행은 서버가 알려준다.
- `seconds_to_next === null` → 카운트다운 대신 `"오늘 장 종료"`.

### 5.3 testid 목록

| testid | 비고 |
|---|---|
| `market-state-page` | 루트 |
| `market-state-asof` | `as_of_kst` 표시 |
| `market-state-trading-day-badge` | `data-value` = `"true"\|"false"\|"unknown"` |
| `market-state-preview-banner` | preview 모드 |
| `market-state-loading` / `market-state-error` / `market-state-retry` | |
| `market-state-card-${market}` | `data-phase` · `data-tone` |
| `market-state-card-name-${market}` / `-window-${market}` / `-countdown-${market}` / `-next-${market}` | |
| `market-state-card-market-order-${market}` | `data-ok` = `"true"\|"false"` |
| `market-state-card-can-order-${market}` | `data-ok` |
| `market-state-card-division-${market}-${code}` | 칩 1개 |
| `market-state-card-concurrent-${market}-${rowId}` | |
| `market-state-card-confidence-${market}` | `data-level` |
| `market-state-table` | |
| `market-state-row-${rowId}` | `data-rel` · `data-market` · `data-confidence` |
| `market-state-row-division-${rowId}-${code}` / `market-state-row-pending-${rowId}-${code}` | |
| `market-state-row-note-${rowId}` | |
| `market-state-catalog` / `market-state-catalog-row-${code}` | |
| `market-state-catalog-cell-${code}-${exchange}` | `data-support` = `"yes"\|"unknown"\|"no"` |
| `market-state-finding-${i}` / `market-state-board-note` / `market-state-unconfirmed-note` | |

`${market}`·`${code}`·`${rowId}`·`${exchange}` 는 **전부 응답 값에서 보간**된다 — 하드코딩이 아니다.

### 5.4 하드코딩 금지 가드 (M7)

`frontend/src/pages/__tests__/_ast_market_state_hardcode.test.ts` —
대상 = `pages/MarketState.tsx` + 이 사이클이 만든 하위 컴포넌트 전부.
**금지어 목록은 손으로 적지 않고 `marketState.fixture.ts` 에서 읽는다.**

금지: ① 모든 `row_id` ② 모든 주문유형 `code` ③ 모든 행 `name_ko`·코드 `name_ko` ④ 모든 `phase` 값
⑤ `"KRX"`·`"NXT"`·`"SOR"` ⑥ 문자열 리터럴 안의 `\d{1,2}:\d{2}` ⑦ 하드코딩 hex(`#rrggbb`) —
디자인시스템 v2 토큰만.
허용(표현 어휘, 픽스처의 `vocab` 과 대조): `tones` · `rels` · `support_levels` · `confidences` ·
`division_confidences`. **예외 목록은 비어 있다** — cycle278 이 파일별 예외를 둔 것은 기존 화면을
개조했기 때문이고, 이 페이지는 신규라 예외가 필요 없다.

전체 줄 주석(`//`·`*`·`/*`)만 제거해 검사한다(문자열 안의 `//` 를 건드리지 않는 cycle278 방식).

---

## 6. 계약 M1~M16

| # | 계약 | 잠그는 테스트 |
|---|---|---|
| **M1** | 각 시장·각 유효일에 **`priority==10` 행끼리 겹침 0**. 의도된 중첩(K2)은 `overlap_ok=True` 이고 `priority` 가 다르다. 날짜 무시 검사(B1)와 날짜 인지 검사(B2)를 **둘 다** 돌린다. 시간 *공백*은 실패가 아니라 데이터다(KRX 는 20:00~08:20 닫혀 있고, 09-13 에는 16:00~20:00 에 행이 없다) | B1 B2 B3 |
| **M2** | 모든 행의 `order_divisions` ⊆ 그 거래소의 `ORDER_DIVISIONS` 가용 집합. 날짜 해석 **전·후 둘 다** | A5 A6 D6 |
| **M3** | 경계 격자 — 각 행의 `start-1s` / `start` / `end-1s` / `end` 에서 반환 행이 기대값과 같다. 구간은 `[start, end)` | C-grid C-a~C-j |
| **M4** | 날짜 차원 — 09-11·09-12·09-13·09-14·09-15 에서 K6/K7 의 유효성이 뒤바뀐다. **09-13 은 둘 다 없다**(정정-2) | D1~D5 |
| **M5** | `now=None` 이면 KST 로 판정. naive=KST 간주, 다른 tz=변환, `on_date` 는 KST 기준 날짜 | E1~E5 |
| **M6** | `market_order_ok == ("01" in order_divisions)` — 전 행·전 격자. NXT 는 항상 False | F1 F2 |
| **M7** | 프론트에 행 id·시각·주문유형 코드·시장명·phase 하드코딩 **0건**. 표는 API 응답으로만 그린다 | FE19 FE20 FE21 |
| **M8** | 8영역·전략 7파일·`scheduler.py`·`strategy_base.py` **diff 0** | H3 + §10 |
| **M9** | `markets[m].row_id` 는 반드시 `table` 안에 있다(또는 None). 표와 커서는 **하나의 `as_of`** 에서 나온다 | G3 G5 |
| **M10** | `is_trading_day` 조회 실패 → `null` + `trading_day_source="unknown"` + **200**. 임의 True/False 금지 | G8 FE18 |
| **M11** | `is_open`(phase 기반)과 `can_order`(divisions 기반)는 **다른 값일 수 있다**. N5 = `is_open ∧ ¬can_order` | F3 F4 |
| **M12** | `decided_by` 는 항상 `"time"`, `code_seen` 은 항상 `None`. 소스에 `"code"` 리터럴 0 | F5 H4 |
| **M13** | leaf 는 `src.*` import 0 · I/O 0 · 로깅 0 · 모듈 로드 부작용 0 | H1 H2 H7 |
| **M14** | `is_market_open` / `next_trading_day` 는 **소스 세그먼트 sha 불변**(`ast.get_source_segment`, `ast.dump` 금지) | H5 |
| **M15** | 빈 표는 **200 빈 화면이 아니라 500**. leaf 예외도 500. 흡수 금지 | G13 G14 |
| **M16** | 픽스처 3곳(vitest·e2e·컴포넌트)이 **생성기 산출·실응답과 일치**. 손으로 고친 목 금지 | I1 I2 I3 |

---

## 7. Red 목록

### 7.1 백엔드 — 82 함수 (케이스 ≥ 250)

파일 = `tests/unit/engine/test_cycle282_market_state.py` ·
`tests/unit/routes/test_cycle282_market_state_route.py` ·
`tests/unit/ast/test_cycle282_guards.py` · `tests/unit/routes/test_cycle282_fixture_sync.py`

**A. 데이터 무결성 (14)**
- `A1` `len(MARKET_TABLE)==13` ∧ row_id 집합 == {K1..K7, N1..N6} ∧ 중복 0
- `A2` 모든 행 `start < end` (자정 넘는 창 0)
- `A3` 모든 행 `market in MARKET_ORDER`
- `A4` 모든 행 `phase` 가 `MarketPhase` 원소 ∧ `match_kind in MATCH_KINDS` ∧ `confidence in CONFIDENCE_LEVELS`
- `A5` **M2(raw)** — 모든 행 `order_divisions` ⊆ 그 시장 가용 코드 집합
- `A6` 모든 행의 코드가 `ORDER_DIVISIONS` 에 존재
- `A7` 모든 행 `order_divisions` 는 오름차순·중복 없음·`tuple`
- `A8` `len(ORDER_DIVISIONS)==28` ∧ 코드 중복 0 ∧ 코드 형식 `^\d{2}$`
- `A9` `exchanges ∩ exchanges_unknown == ∅` ∧ 둘 다 ⊆ `EXCHANGE_ORDER` ∧ 최소 1개 이상
- `A10` **발견 1 봉인** — `"01"` 의 `exchanges` 에 `"NXT"` 없음, `exchanges_unknown` 에도 없음
- `A11` **발견 2 봉인** — `"05"`·`"06"`·`"07"` 의 `exchanges`/`exchanges_unknown` 에 `"SOR"` 없음
- `A12` `27~29` = NXT 전용 ∧ `effective_from == date(2026,9,14)`; `41~47` = KRX 전용 ∧ 같은 날;
  `07.effective_to == date(2026,9,12)`; 셋 다 `exchanges_unknown == {"SOR"}`
- `A13` `MarketRow`·`OrderDivisionSpec` 이 frozen ∧ `MARKET_TABLE`/`ORDER_DIVISIONS` 가 `tuple`
- `A14` **골든 전수** — 13행 × (start, end, phase, name_ko, match_ko, order_divisions, priority,
  overlap_ok, effective_from, effective_to, confidence) 를 §1.3 리터럴과 비교. 행 삭제·값 변조 즉시 RED

**B. 중첩·우선순위 (8)**
- `B1` 날짜 무시 겹침 쌍 == {(K1,K2), (K6,K7)} 이고 각 쌍에 `overlap_ok=True` 행이 하나 이상
- `B2` **M1** — 09-11·09-12·09-13·09-14·09-15 × {KRX, NXT} 에서 `priority==10` 행끼리 겹침 0
- `B3` **정정-3** — K6·K7 이 동시에 유효한 날짜가 하나도 없다(`effective_to(K7) < effective_from(K6)`)
- `B4` 08:35 KRX → `row_id=="K1"` ∧ `concurrent_row_ids==("K2",)`
- `B5` 08:35 KRX → `order_divisions == ("00","01","05")` ∧ `order_divisions_by_row` 가 K1/K2 로 갈림
- `B6` 08:25 KRX → `concurrent_row_ids==()` ∧ `order_divisions==("00","01")`
- `B7` 08:40:00 KRX → K2 종료(반개구간) → `concurrent_row_ids==()` ∧ `"05" not in order_divisions`
- `B8` `priority` 동률 두 행 monkeypatch 주입 → 커서는 `(priority,start,row_id)` 최소로 결정론적 ∧
  `confidence=="ambiguous"`

**C. 경계 격자 (11)**
- `C-grid` 13행 × 4점(`start-1s`·`start`·`end-1s`·`end`) **파라미터라이즈 52 케이스** — freezegun 고정
- `C-a` 09:00:00 KRX → `K3`(K1 아님, 반개구간)
- `C-b` 15:20:00 → KRX `K4` / NXT `N4`(BREAK)
- `C-c` 15:30:00 → KRX `K5` / NXT `N5`
- `C-d` 16:00:00 → 09-14 는 `K6`, 09-11 은 `K7`, 09-13 은 `CLOSED`
- `C-e` 20:00:00 → 양 시장 `CLOSED` ∧ `seconds_to_next is None` ∧ `next_row_id is None`
- `C-f` **미확인 30초** — 09:00:00·09:00:29 NXT → `N2`(BREAK), 09:00:30 → `N3`
- `C-g` 08:49:59 NXT → `N1`, 08:50:00 → `N2`
- `C-h` 07:59:59 NXT → `CLOSED` ∧ `next_row_id=="N1"` ∧ `seconds_to_next==1`
- `C-i` 15:39:59 NXT → `N5`, 15:40:00 → `N6`
- `C-j` **올림** — 19:59:59.5 → `seconds_to_next == 1`(0 아님)
- `C-k` 03:00:00 양 시장 → `CLOSED` ∧ `next_row_id` = 그날 첫 행(KRX `K1`, NXT `N1`)

**D. 날짜 차원 (9)**
- `D1` `get_market_table(2026-09-12)` — K7 있음 ∧ K6 없음
- `D2` `get_market_table(2026-09-13)` — K6·K7 **둘 다 없음** ∧ KRX 행 5개(K1,K2,K3,K4,K5)
- `D3` `get_market_table(2026-09-14)` — K6 있음 ∧ K7 없음
- `D4` `get_market_table(09-15)` row_id 집합 == `get_market_table(09-14)`
- `D5` 09-13 16:30 KRX `get_market_state` → `phase==CLOSED` ∧ `row_id is None`(정정-2 의 귀결 고정)
- `D6` N1 `order_divisions` — 09-12 는 13개(27~29 없음), 09-14 는 16개
- `D7` K6 `order_divisions` 09-14 == `("41",…,"47")`; 09-13 조회 시 K6 행 자체 부재
- `D8` 09-12 N1 행의 `order_divisions_pending == ("27","28","29")` ∧ `_expired == ()`;
  09-14 N1 은 `pending == ()`
- `D9` `get_market_table()` 인자 없음 → KST 오늘 기준(freezegun + TZ=UTC 환경)

**E. KST (5)**
- `E1` `now=None` + `TZ=UTC` 컨테이너 + freezegun `00:30Z` → `K3`(09:30 KST 정규장)
- `E2` naive `datetime(2026,9,11,9,30)` → KST 간주 → `K3`
- `E3` `datetime(2026,9,11,0,30,tzinfo=utc)` → 변환 → `K3`
- `E4` `America/New_York` aware → 변환 일치
- `E5` `23:00Z` → `as_of.date()` 가 **KST 익일** ∧ `on_date` 도 익일 ∧ `N1` 판정

**F. 파생 필드 (6)**
- `F1` **M6** — 13행 × 격자 전수에서 `market_order_ok == ("01" in order_divisions)`
- `F2` NXT 전 구간·전 날짜 `market_order_ok is False`
- `F3` `is_open == (phase not in (BREAK, CLOSED))` 전수
- `F4` `can_order == bool(order_divisions)` 전수 ∧ N5 는 `is_open ∧ ¬can_order`
- `F5` `decided_by=="time"` ∧ `code_seen is None` 전수
- `F6` `next_boundary` 시각에 `get_market_state` 를 다시 부르면 `row_id == next_row_id` ∧
  `phase == next_phase` (전 행 전수)

**G. 라우트 (18)**
- `G1` 200 + `{success,data,message}` 래퍼 ∧ `data` 최상위 키 전수 일치
- `G2` `markets` 키 집합 == `set(market_order)`
- `G3` **M9** — `markets[m].row_id` ∈ `{r.row_id for r in table if r.market==m}` 또는 None
- `G4` `as_of_kst` 가 `+09:00` 접미 ISO ∧ `on_date` 가 그 날짜
- `G5` **하나의 as_of** — leaf 호출 인자 캡처: `get_market_state` 2회 호출의 `now` 가 **동일 객체** ∧
  `get_market_table(on_date)` 가 그 `now.date()` 와 같다
- `G6` `is_trading_day is True` (respx `opnd_yn="Y"`)
- `G7` `is_trading_day is False` (`opnd_yn="N"`)
- `G8` **M10** — respx 500/타임아웃/예외 → `is_trading_day is None` ∧ `trading_day_source=="unknown"` ∧ 200
- `G9` 캐시 — 같은 날짜 2회 요청 시 KIS 호출 **1회**(respx call count) ∧ 2번째 `source=="cache"`
- `G10` 음성 캐시 — 실패 직후 재요청은 KIS 미호출, `time.monotonic` +61s 뒤 재호출
- `G11` `on_date` 미래 → `preview is True` ∧ `markets is None` ∧ `cursor_disabled_reason=="preview_other_date"`
  ∧ `table` 이 그 날짜 ∧ 모든 `rel=="unknown"`
- `G12` `on_date` 형식 오류 → 422 / 범위(±365일) 밖 → 422
- `G13` **M15** — 빈 표 monkeypatch: 오늘 → **500** `market_table_empty`; preview 날짜 → **404** `no_effective_rows`
- `G14` **M15** — leaf 예외 monkeypatch → **500** (200 빈 응답 아님)
- `G15` `order_divisions` 28행 ∧ 각 행 `exchange_support` 가 `exchange_order` 3키 ∧ 값 ⊆ `SUPPORT_LEVELS`
- `G16` `findings`·`board_note`·`unconfirmed_note`·`phases`·`vocab` 이 leaf 상수와 동일
- `G17` `rel` — 13:05 응답에서 K1·K2=`past`, K3=`current`, K4~=`upcoming`;
  08:35 응답에서 K1=`current` ∧ K2=`concurrent`
- `G18` 인증 경유 정상(기존 `_neutralize_api_auth` 픽스처 호환) ∧ `real_api_auth` 마커 시 401

**H. 구조 가드 (8)**
- `H1` **M13** — `market_state.py` AST 에 `src.*` import 0
- `H2` **M13** — `await`·`open(`·`httpx`·`requests`·`logging`·`asyncio` 0
- `H3` **M8** — 8영역 5파일 + `src/api/order.py` + `src/realtime/**` + `src/auth/**` +
  `scheduler.py` + `strategy_base.py` + 전략 7파일의 **파일 sha 핀**(사이클 한정, 헤더에 "커밋 후 삭제" 명시)
- `H4` **M12** — `market_state.py`·라우트에 `"code"` 리터럴 0(`decided_by` 확장 봉인)
- `H5` **M14** — `is_market_open`·`next_trading_day` 의 `ast.get_source_segment` sha256 핀
  (⚠️ `ast.dump` 금지 — 3.12/3.13 출력 상이) ∧ 신규 `is_trading_day` 가 같은 `HOLIDAY_URL`·TR_ID 사용
- `H6` 라우트 소스에 `datetime.now(` 호출 **정확히 1회**(AST) — 시장별 재호출 금지
- `H7` **M13** — 모듈 import 전후 `sys.modules` 델타에 `src.` 항목 0 ∧ 네트워크·파일 접근 0
- `H8` 라우트 파일에 시각 리터럴 `\d{1,2}:\d{2}` 0 (시각은 전부 leaf 에서 온다)

**I. 픽스처 동기 (3)**
- `I1` `frontend/src/test/fixtures/marketState.fixture.ts` == 생성기 산출(byte)
- `I2` `e2e/fixtures/market-state.fixture.ts` == 생성기 산출(byte)
- `I3` 픽스처의 `table`·`order_divisions`·`vocab`·`market_order` 가 **실응답**과 필드별 일치

> 소스 스캔은 `Path(...).rglob("*.py")` + AST 로 한다. **`git grep`/`git ls-files` 금지** —
> 추적 파일만 보므로 Green 이 새로 만든 미추적 파일을 로컬에서는 못 보고 CI 에서만 잡는다.

### 7.2 프론트 — 22 케이스 + E2E 3

파일 = `frontend/src/pages/__tests__/MarketState.test.tsx` ·
`frontend/src/pages/__tests__/_ast_market_state_hardcode.test.ts` · `e2e/market-state.spec.ts`

- `FE1` 로딩 → `market-state-loading`
- `FE2` 에러 → `market-state-error` ∧ `market-state-retry` 클릭 시 재요청 1회
- `FE3` 카드 2개가 `market_order` **순서대로** 렌더
- `FE4` 카드 상태명 == 응답 `name_ko` (문자열 비교)
- `FE5` `AT_1305` 픽스처 — KRX 카드 `data-ok="true"`, NXT 카드 `data-ok="false"`
- `FE6` 칩 개수·코드·이름이 `order_divisions` × 카탈로그 조인과 1:1
- `FE7` `AT_0835` 픽스처 — `market-state-card-concurrent-KRX-K2` 존재 ∧ 칩에 `05` 포함
- `FE8` `confidence!=="confirmed"` 인 카드·행에만 확인 필요 배지 (K1·N3·N5 만)
- `FE9` 표의 `data-rel` 이 서버 값 그대로 ∧ `past` 행에 흐림 클래스, `current` 행에 강조 클래스
- `FE10` 표 행 수 == `table.length` ∧ 순서 == 응답 순서
- `FE11` `order_divisions_pending` 있는 행에 `market-state-row-pending-*` 배지
- `FE12` 카탈로그 28행 ∧ `data-support` 가 `exchange_support` 값 그대로(`yes`/`unknown`/`no` 셋 다 등장)
- `FE13` `findings` 2건·`board_note`·`unconfirmed_note` 텍스트가 응답에서 옴
- `FE14` 카운트다운 — fake timers 로 1초씩 감소 ∧ 0 도달 시 `refetch` **1회만**
- `FE15` `seconds_to_next===null`(`AT_2030`) → `"오늘 장 종료"` ∧ 카운트다운 없음
- `FE16` 폴링 30초 — fake timers 30s 전진 시 요청 1회 추가
- `FE17` preview 응답(`markets:null`) → 카드 대신 `market-state-preview-banner` ∧ 모든 `data-rel="unknown"`
- `FE18` `is_trading_day:null` → 배지 `data-value="unknown"` + "확인 불가" (M10)
- `FE19` **M7 가드** — 페이지 소스에 row_id·코드·행/코드 이름·phase·시장명 리터럴 0
- `FE20` **M7 가드** — `getHours|getMinutes|getDay|getDate|toLocaleTimeString\(\)` 0 ∧
  `new Date(` 는 경과 계산 1곳 ∧ `timeZone: 'Asia/Seoul'` 명시가 있다
- `FE21` **M7 가드** — 하드코딩 hex 0 (디자인시스템 v2 토큰만)
- `FE22` `App.tsx` — nav 항목 1개 추가 ∧ `/market-state` Route 렌더
- `E2E-1` 나브 클릭 → 페이지 진입 ∧ 카드 2개 ∧ `data-rel="current"` 행이 시장당 1개
- `E2E-2` 카탈로그 28행 ∧ `05`·`06`·`07` 의 SOR 셀 `data-support="no"` ∧ `27` 의 SOR 셀 `="unknown"`
- `E2E-3` 확인 필요 배지가 K1·N3·N5 세 행에 보인다

---

## 8. 뮤테이션 후보 16종 (≥12 요구)

| # | 뮤테이션 | 죽이는 테스트 |
|---|---|---|
| m1 | `MARKET_TABLE` 에서 K2 삭제 | A1 A14 B4 B5 |
| m2 | K1 `priority` 를 30 으로(오버레이로 강등) | B4 (08:35 커서가 K2 로 뒤집힘) |
| m3 | 구간을 `[start, end]`(끝 포함)로 | C-a (09:00 에 K1·K3 동시 → ambiguous) B7 |
| m4 | K3 `start` 를 08:59:59 로 1초 이동 | C-grid C-a A14 |
| m5 | `effective_to` 비교를 `>` → `>=`(K7 이 09-13 에도 유효) | D2 B3 |
| m6 | `_resolve_divisions` 의 **코드** 날짜 필터 제거 | D6 D8 (09-12 N1 에 27~29 노출) |
| m7 | `get_market_table` 이 **raw** divisions 반환(날짜 미해석) | D6 D7 I3 |
| m8 | `market_order_ok` 를 `phase == REGULAR` 로 계산 | F1 F2 (N3 가 True) |
| m9 | `now=None` → `datetime.now()`(naive 로컬) | E1 (TZ=UTC 로 CI 실행) |
| m10 | naive `now` 를 UTC 로 간주 | E2 |
| m11 | 라우트가 시장별로 `datetime.now(KST)` 재호출 | H6 G5 |
| m12 | 라우트가 `get_market_table()` 을 인자 없이 호출 | G5 (자정 경계 날짜 불일치) |
| m13 | `is_trading_day` 실패를 `True` 로 | G8 FE18 (M10) |
| m14 | 실패(None)를 영구 캐시 | G10 |
| m15 | 빈 표를 200 + 빈 `table` 로 흡수 | G13 G14 (cycle266 fail-silent 재현) |
| m16 | 프론트가 `seconds_to_next` 대신 로컬 시각으로 커서 재계산 / `'K3'` 리터럴 부활 | FE20 FE19 |

각 뮤테이션은 **행위 테스트**가 죽여야 한다. AST 가드만 죽이는 항목(m11·m16)은 행위 테스트를
추가로 붙인다(G5 의 인자 캡처 / FE14 의 refetch 횟수).

---

## 9. 롤백

| 대상 | 롤백 | 영향 |
|---|---|---|
| 프론트 메뉴 | `App.tsx` 2행 제거 | 메뉴가 사라진다. 다른 화면 무영향 |
| 라우트 | `src/main.py` `include_router` 1행 제거 | `/api/market-state` 404. 다른 라우트 무영향 |
| leaf | `src/engine/market_state.py` 삭제 | 호출자 = 신규 라우트뿐 |
| `is_trading_day` | 함수 삭제 | 호출자 = 신규 라우트뿐. `is_market_open`·`next_trading_day` 는 애초에 무변경 |
| 데이터 | **없음** | DB 마이그레이션 0 · 환경변수 0 · 설정 키 0 |

전체 롤백 = **단일 revert 커밋**. 매매 행위는 어느 방향으로도 바뀌지 않는다(호출자 0).

**배포 모드** = `src/**` 변경이므로 cycle248 판정상 **full**(backend 재생성). 따라서
보유 포지션이 있으면 KRX 메인 시간(09:00~15:30) push 금지(D6), 20:00~20:15 도 피한다.
장외 창(15:30~19:55 · 20:20~익일 07:45 · 주말)에만 push 한다.

---

## 10. 무접촉 증명 (커밋 전 실행)

```bash
cd /Users/koscom/Projects/auto_stock_wt282
git diff --stat 34f662f..HEAD -- \
  src/engine/risk.py src/engine/order_engine.py src/engine/session.py \
  src/engine/scanner.py src/engine/strategy_registry.py src/api/order.py \
  src/realtime/ src/auth/ src/engine/scheduler.py src/engine/strategy_base.py \
  src/engine/strategies/
# → 출력이 비어 있어야 한다 (M8)

git diff --stat 34f662f..HEAD -- src/api/condition.py
# → is_trading_day 추가분만. H5 가 기존 두 함수의 소스 세그먼트 sha 로 무변경을 증명한다
```

**`scheduler.py` 라인 상한** — 이 사이클은 `scheduler.py` 를 안 건드리므로 3,898L 그대로다.
cycle257 의 `<3,900` 영속 가드에 영향 없음.

---

## 11. 검증 게이트

1. 백엔드 — `python -m pytest -q` **전체** PASS(회귀 0). 신규 82 함수 포함.
   `pytest --log-level=DEBUG` 로도 한 번 돌린다(CI 루트 로거가 DEBUG 라 caplog 개수 단언이 갈린다).
2. 프론트 — `tsc -b` 0 → `npm test` PASS(신규 22) → `npm run build` 성공
3. E2E — `npx playwright test --config=e2e/playwright.config.ts` 전체 PASS(신규 3 포함), **4연속**
4. 뮤테이션 16종 — 행위 ESCAPED **0**
5. 픽스처 — `python tools/test_fixtures/gen_market_state_fixture.py` 재실행 후 `git diff` 비어 있음
6. 영향 인덱스 — `python tools/test_impact/build_index.py` + `node tools/test_impact/build_index_frontend.mjs`

---

## 12. 남는 질문 (이 사이클에서 **풀지 않는다**)

| # | 질문 | 왜 지금 안 푸는가 | 다음 단계 |
|---|---|---|---|
| Q1 | K1 시작이 08:20 인가 08:30 인가 | 정본이 없다. 추측으로 채우면 표가 확신 없는 값을 확신 있게 말한다 | KIS MCP 스펙 조회 + 09-14 이후 08:2x 주문 접수 실측 |
| Q2 | N3 시작이 09:00:30 인가 09:00:00 인가 | 같은 이유. 지금은 30초 휴장 꼬리가 그대로 보인다(C-f) | 09-14 이후 NXT 09:00:0x 체결 실측 |
| Q3 | N5(15:30~15:40 애프터 단일가)의 주문유형 | NXT 코드 목록에 단일가 전용 코드가 없다. 빈 튜플이 정직하다 | KIS MCP + 실측 |
| Q4 | SOR 이 27~29·41~47 을 지원하는가 | 미확인. `exchanges_unknown` 으로 드러낸다 | 09-14 이후 SOR 주문 1건 실측 |
| Q5 | `41~47` 각각의 명칭 | 정본 없음. 그룹명 + `name_unconfirmed` | KIS MCP |
| Q6 | `decided_by="code"` (MARKET_CLS_CODE 실측 판정) | 09-14 이후 데이터가 쌓여야 한다. 지금 만들면 검증할 수 없는 분기가 생긴다 | 별도 사이클. H4 가 그 전까지 `"code"` 리터럴을 0 으로 잠근다 |
| Q7 | `quote_channel` 의 실제 값 | wt280(시세 전환)이 같은 값을 바꾸는 중 | wt280 착지 후 대조 |
| Q8 | 전략·주문 경로가 이 함수를 소비 | **이 사이클의 범위 밖**(읽기 전용). 소비는 8영역 변경 = 별도 승인 + `domain-consult` 선행 | 후속 주문 사이클 |

---

## 13. Red 실행 로그 (Green 진행 중 채운다)

| 라운드 | 일시 | 명령 | 결과 |
|---|---|---|---|
| R0 | — | `pytest tests/unit/engine/test_cycle282_market_state.py -x` | (Red 작성 후 기록) |

---

## 14. 후속 검증에서 나온 지적 — 처리와 판단 (2026-09-11)

적대 검증이 GO 를 내면서 뮤테이션 **4종 ESCAPED** + 비차단 지적 9건을 남겼다.
그중 여섯을 시정했고, 둘은 **고치지 않고 판단 근거만 남긴다.**

### 14.1 시정한 것

| # | 지적 | 시정 | 회귀 가드 |
|---|---|---|---|
| 1 | `ResolvedRow` 파생 3필드(`market_order_ok`·`can_order`·`tone`)가 **표 행에서는** 값으로 검정되지 않아 뮤테이션 3종이 살았다(`"01" in live` → `bool(live)` 도 초록) | 전 행 × 전 유효일 격자로 세 필드를 단언. 기대값은 **이 파일의 표 사본**에서 독립 재계산한다(구현의 `PHASE_TONES` 를 읽어 비교하면 자기 자신과의 비교가 된다) | `tests/unit/engine/test_cycle282_market_state.py::G1~G6` (10 함수) |
| 2 | `SUPPORT_GLYPH.unknown` 을 빈 문자열로 바꾸면 **미확인 칸과 미지원 칸이 화면상 완전히 같아지는데** 컴포넌트·E2E 가 전부 초록 | 세 상태의 **보이는 텍스트**를 성질로 잠근다 — 서로 다르다 ∧ "지원"·"미확인" 은 비어 있지 않다 ∧ 빈칸은 "미지원" 하나뿐이다. 글리프 문자는 테스트에 적지 않는다 | `MarketState.test.tsx::FE23` |
| 3 | 픽스처 머리말이 "기계 생성 · 백엔드가 byte 비교" 를 **선언만** 하고 생성기도 가드도 없었다 | 생성기 `tools/test_fixtures/gen_market_state_fixture.py` 신설. `read_market_state` 를 **그대로 호출**하고 시각·휴장일만 고정하므로 픽스처의 바이트가 곧 라우트의 실제 응답이다 | `tests/unit/routes/test_cycle282_fixture_sync.py::I1·I2·I5` |
| 4 | 같은 픽스처가 두 벌(컴포넌트용·E2E용)인데 둘이 같다는 보장이 없었다 | 생성기가 두 파일을 함께 쓰고, 가드가 **머리말을 뺀 본문의 byte 동일**을 단언한다 | 같은 파일 `I3`(+ 이름 계약 `I4`) |
| 5 | 프론트 영향 인덱스에 이번 사이클 산출물이 한 건도 없었다 | `build_index_frontend.mjs` 재생성. 백엔드 세 테스트는 Red 관례(`importlib.import_module`)라 정적 분석에 안 잡혀 `manual_overrides.yaml` 에 등재 | `tools/test_impact/manual_overrides.yaml` cycle282 절 |
| 6 | 화면이 404·422·500·네트워크를 **빨간 박스 하나**로 흡수했다(cycle266 계열) | "안내"(404 = 그 날짜에 행 0)와 "오류"(422·500·네트워크)를 다른 testid·다른 톤·다른 문구로 가른다. 서버가 붙인 `detail` 도 지우지 않는다 | `MarketState.test.tsx::FE24` (6 케이스) |

### 14.2 고치지 않는 것 — K1 유효기간

**지적** — §0 정정-1 은 브리프의 K1 유효기간 `09-14~` 를 `effective_from=None`(상시)로 바꿨다.
브리프와 구현이 다르다.

**판단 — 구현이 맞다. 그대로 둔다.**
브리프대로 `effective_from=2026-09-14` 를 적용하면 09-11~09-13 에 KRX 08:20~09:00 행이
통째로 사라진다. 그러면 **오늘(09-11) 화면의 아침이 빈다.** 그런데 08:20 시작이 신설인지
자체가 아직 미확인이다(Q1, 사용자 확인 대기). 미확인을 이유로 오늘의 표를 비우는 것은
10분을 과다 표시하는 것보다 나쁘다 — 전자는 "장이 안 열린다" 는 거짓이고 후자는 "10분 일찍
열린다고 표시했다" 는 오차다. 시가 단일가는 수십 년 존재했으므로 `09-14~` 는 *행의 신설*이
아니라 **시작 시각의 신설 여부**를 가리킨다고 읽는다.
그 불확실성은 지우지 않고 `confidence="unconfirmed"` + `note` 로 화면에 그대로 띄운다.
Q1 이 풀리면 `start` 를 고치거나 날짜 축을 나눈다.

### 14.3 고치지 않는 것 — K7 과 코드 `07` 의 "하루 차이"

**지적** — 브리프가 카탈로그에는 "09-14 폐지", K7 행에는 "~09-12" 라 적어 모순으로 보였다.
또 "09-13 에 KRX 16:00~20:00 행이 0" 이 결함처럼 보였다.

**판단 — 모순이 아니다. 그대로 둔다.**
달력 실측 — **2026-09-12 는 토요일, 09-13 은 일요일이다.**
그러므로 구 제도의 마지막 *거래일*은 오늘 **09-11(금)** 이고, 주말은 어차피 휴장이다.
"~09-12" 와 "09-14 폐지" 는 거래일 기준으로 **같은 것을 가리킨다.**
같은 이유로 "09-13 에 행 0" 도 무해하다 — 일요일에는 아무도 주문을 내지 않는다.
데이터를 넓혀 그 하루를 메우는 것이야말로 정본에 없는 값을 지어내는 일이라 하지 않는다
(정정-2). 이 귀결은 `D2`·`D5` 가 명시적으로 고정한다.

### 14.4 남은 이견 하나

14.1 의 2번에서 검증은 "세 상태 모두 비어 있지 않다" 를 요구했다.
**그대로 적용하지 않았다.** 명세 §5.3 과 화면의 범례가 "빈칸 = 미지원" 을 계약으로 못박고
있어서, 미지원에 글리프를 주면 그 계약과 범례를 함께 바꿔야 한다. 그것은 이 시정의 범위를
넘는 UI 변경이다. 대신 같은 뮤테이션을 잡는 더 좁은 성질로 잠갔다 — **세 상태가 서로 다르게
보이고, "모른다" 는 비어 있지 않다.** 빈칸은 "미지원" 하나뿐임도 함께 고정해 역방향
(미지원에 글리프를 주어 미확인과 충돌시키는 변경)도 막는다.
