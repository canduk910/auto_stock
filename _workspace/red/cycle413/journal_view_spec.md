# cycle413 거래일지 화면(1b) — 화면·API 명세 (domain-expert, 트레이더 복기 관점)

- **기준**: 브랜치 `feat/trade-journal-1b`(main `8c28e9a6` — 실비용 cycle411·거래일지 1a cycle412 운영 배포 완료 10-09 06:45).
- **정본 입력**: `_workspace/design/2026-10-08_trade_journal_plan.md`(2절 10항목·3절 전략표·6절 화면·8절 과거분·9절 기본값) · `_workspace/design/2026-10-08_trade_journal_observer.md`(관찰자 방식) · `_workspace/red/cycle412/journal_contract.md`(칸·source 값) · `_workspace/red/cycle411/cost_overlay.md`(비용 계약) · `supabase/migrations/047_trade_journal.sql`.
- **이 문서가 정하는 것**: 응답 모양 · 한국어 표기 · 이유 문장 규칙 · MFE/MAE 규칙 · 「모름/기록 전/해당 없음」 구분 · 필터·정렬·메모 · 화면 배치. 코드 위치·함수 분할은 backend-dev/frontend-dev 가 정한다. 이 문서와 Red 테스트가 갈리면 테스트가 정본이다.
- **금기(이 사이클 공통)**: 8영역·`scheduler.py` 0줄 · `journal_worker/` 0줄(계약 차이는 7절에 보고만) · KIS 호출 0 · 마이그레이션 0(047 표로 충분하다 — 메모 표 포함) · 운영 DB 접속 0.

---

## 0. 지금 실제로 쌓이는 데이터 (명세의 전제)

| 원천 | 기간 | 카드에 주는 것 | 비고 |
|---|---|---|---|
| `trade_history` | 04-22~ 전부 | 일자·체결가·수량·실현손익·주문번호·`order_price`(10-07~) | 페어 = `get_trade_pairs()`(매매손익 탭과 같은 묶음) |
| c411 `overlay_pairs()`·`trade_costs()` | 정산 08-21~, 그 전 추정 | 수수료·세금·세후 손익·배지 | 숫자는 매매손익 탭과 같아야 한다 |
| `trade_journal_orders` `source='log_restore'` | 09-17~10-08 (150행 — 매수 75·매도 75) | 진입: **신호가만**(`signal_src='log_only'`, 구조값 없음) · 청산: 사유·발동선·판단가 일부·주문구분(09-28~) | 아래 재생 실측 |
| `trade_journal_orders` 실시간(`log_harvest` 외) | 10-12 장부터(10-12 은 신규 매수 정지일이라 실시간 진입 행은 10-13 계좌 전환 뒤부터일 수 있다) | 진입: G0 신호 원본(`signal_src='ring'` — 돌파선·K·ATR·목표) + 파라미터 사본 · 청산: 사유·발동선·유효선(스냅샷)·판단가 | `exchange` 는 항상 NULL(7절 C1) |
| `trade_journal_stops` | 10-12 장부터 | 손절선 사건 `first/change/boot/eod/paused/exit` · BFB 목표·도달 · donchian 무장가 | 10-12 전부터 들고 있던 종목은 10-12 첫 관측이 `first` 로 찍힌다 — **최초 손절이 아니다**(4절 규칙) |
| `trade_journal_notes` | 표만 있음(행 0) | 메모 | 1b 가 PUT 을 연다 |
| `stock_master_daily` | 06-12~ (대체로) | 일별 종가 · 잠정 여부(`updated_at`) · 락(`flng_cls_code`·`prtt_rate`) | 결측 있음 — k/n 표시 |
| `llm_buy_evaluations` | 09-11~(주문을 낸 전략·모드만) | 복원분 진입 이유 보강: `target_won`(돌파선)·`k`·`strategy_board`·`signal_price_won` | 「복원(AI평가)」 배지, 2절 표 |

**복원분 재생 실측** (골든 로그 09-17~10-07, `jw.backfill.restore_rows` 로 145행 재생 — scratchpad `c413_domain_probe.py`):
- 매수 75행 전부 `signal_src='log_only'`. 그중 BFB 12·VCP 3 = **15행은 신호가도 없다**(로그 줄이 `*_vol_gate_pass` 뿐). → AI평가 보강이 없으면 「구조값 기록 없음」이 된다.
- 매도 70행 판단가: 정확(`log_price`) 14 · 역산(`log_pct`) 13 · 상한만(`judge_upper`) 3 · 없음 40(FORCE_CLEAR 26 · NEXT_DAY_CLEAR 11 · 시간 2 · 추세 1 — 가격과 무관한 청산이라 원래 없다).
- 매도 발동선: 15행(선 가격·임계 % 가 줄에 있는 것). **LTV 손절 5행은 복원분에서 빈다**(파라미터 사본이 없어 계산 불가 — 실시간분만 계산된다).
- 주문구분: 매도 42행(09-28~, `01` 41 · `44` 1). 그 전은 빈칸.

---

## 1. API

### 1-1. `GET /api/history/journal`

| 쿼리 | 형식 | 기본값 | 검증 |
|---|---|---|---|
| `from`, `to` | `YYYY-MM-DD` (KST) | `to`=오늘, `from`=오늘−30일 | costs 라우트 `_parse_range` 와 같은 규칙(형식·from≤to·366일 이하) → 위반 422 |
| `strategy` | 전략 id | 없음(전체) | 모르는 id 는 빈 결과(`/pnl` 과 같음) |
| `ticker` | 6자리 코드 | 없음 | 정확 일치 |
| `status` | `all`·`open`·`closed` | `all` | 그 밖 422 |
| `outcome` | `all`·`win`·`loss` | `all` | 그 밖 422 |
| `basis` | `net`·`gross` | `net` | `outcome`·`sort` 판정에만 쓴다(화면 토글 값을 그대로 보낸다) |
| `sort` | `recent`·`pnl_asc`·`pnl_desc` | `recent` | 그 밖 422 |
| `page` | ≥1 | 1 | |
| `size` | 1~100 | 20 | 카드가 무거워 `/pnl`(50)보다 작게 |

**고르는 규칙**
- **기간** = 보유 기간이 `[from, to]` 와 겹치는 페어: `buy_date ≤ to` 이고 (`status=='open'` 이거나 `sell_date ≥ from`). 「그 기간에 들고 있던 거래」가 복기 단위다.
- **이익/손실** = `basis` 손익(세후면 `net_profit_loss`, 그것이 None 이면 세전 `profit_loss`)이 `> 0` → win, `< 0` → loss. 0·모름(None)은 `all` 에서만 보인다. 보유 중은 미실현으로 판정한다.
- **정렬**
  - `recent`: 보유 중 먼저(매수 시각 내림차순), 그다음 청산 페어를 **청산 시각** 내림차순. (매매손익 탭은 청산 페어도 매수 시각 순이다 — 일지는 「오늘 판 것부터」 본다.)
  - `pnl_asc`: `basis` 손익(원) 오름차순 = 「손실 큰 순」. 모름은 맨 뒤. 보유 중도 섞는다.
  - `pnl_desc`: 내림차순. 모름은 맨 뒤.
- **계산 범위**: 필터·정렬·건수는 걸러진 페어 전체로, 카드 세부(일지 행·손절선·종가·메모·AI평가)는 **그 페이지 카드만** 읽는다.

**읽는 순서와 실패 격리** — 원천마다 1번씩 읽고, 한 원천이 실패해도 응답은 **200** 이다. 실패한 원천에 기대는 칸만 `na="lookup_failed"`.
1. `get_trade_pairs(strategy, ticker)` + 종목명 보충(`/pnl` 과 같음).
2. 기간·상태 필터 → `overlay_pairs()` (`/pnl` 과 같은 try — 실패면 `cost_available=false`, 비용·세후 칸 전부 `lookup_failed`). → 이익/손실 필터 · 정렬 · 건수 · 페이지 자르기.
3. 페이지 카드만: 체결 행(아래) · `trade_journal_orders` · `trade_journal_stops` · `trade_journal_notes` · `stock_master_daily` 종가·영업일 · `llm_buy_evaluations` · 기록 시작일.
- **체결 행 읽기**: 카드의 `buy_trade_ids`·`sell_trade_ids`·`partial_sell_trade_ids` 로 `trade_history` 행을 읽는다. 필요한 칸 = `id, order_no, trade_type, timestamp(KST), price, quantity, order_price, profit_loss(NULL 그대로)`. 🔴 `trade_cost.get_trades_by_status` 는 `profit_loss` 를 `COALESCE(…, 0)` 으로 주므로 실현손익 원천으로 쓰지 않는다(「모름 ≠ 0」).
- **체결 행 단위 비용**: 진입/청산을 나눠 보이려면 `trade_costs()` 의 체결 행 단위 값이 필요한데, `overlay_pairs()` 는 페어 합계만 돌려준다. 한 요청에서 비용 원천(정산 행·체결 행·요율·ETF 판정)을 **두 번 읽지 않는다**(c411 F8 과 같은 원칙). 방법은 backend-dev 가 정한다(예: `overlay_pairs` 가 내부 `costs` 를 함께 돌려주는 가산형 변경). 패리티 = 6절 T3.
- 047 표가 없으면(마이그레이션 실패) 일지 3표의 칸만 `lookup_failed`, 카드는 거래기록·비용·종가로 그린다.

### 1-2. 응답 (`frontend/src/types/journal.ts` 와 같은 키)

```ts
type NaKind = 'unknown' | 'before_record' | 'not_applicable' | 'pending' | 'lookup_failed'
type ValSrc = 'trade' | 'live' | 'restored' | 'restored_ai' | 'snapshot' | 'derived' | 'inferred' | 'computed'
type CostStatus = 'settled' | 'estimated' | 'mixed'

interface JournalResponse {            // ApiResponse.data
  record_start: {                      // KST 'YYYY-MM-DD' 또는 null(행 0)
    orders_restored: string | null     // MIN(order_date) WHERE source='log_restore'
    orders_live: string | null         // MIN(order_date) WHERE source<>'log_restore'
    stops: string | null               // MIN(observed_at) 의 KST 날짜
    order_price: string | null         // trade_history 에서 order_price 가 처음 채워진 KST 날짜
  }
  filters: { from: string; to: string; strategy: string | null; ticker: string | null
             status: 'all'|'open'|'closed'; outcome: 'all'|'win'|'loss'
             basis: 'net'|'gross'; sort: 'recent'|'pnl_asc'|'pnl_desc' }   // 서버가 해석한 값
  counts: { total: number; open: number; closed: number }                  // 필터 적용 뒤
  page: number; size: number; total: number; total_pages: number
  cost_available: boolean
  cards: JournalCard[]
}

interface JournalCard {
  pair_key: string | null
  anchor_trade_id: string              // 첫 매수 trade_history.id(UUID) = buy_trade_ids[0] — 메모 키
  strategy: string; ticker: string; ticker_name: string
  status: 'open' | 'closed'
  opened_at: string                    // 첫 매수 행 timestamp, KST ISO(+09:00)
  closed_at: string | null             // 마지막 매도 행 timestamp(closed)
  held_days: number                    // 달력일 차(매수일=0, 보유 중은 오늘까지)
  record_notice: 'before_orders' | 'before_stops' | null     // 5절
  pnl: {
    gross_krw: number | null; gross_rate_pct: number | null  // = pair.profit_loss / profit_rate
    net_krw: number | null;   net_rate_pct: number | null    // = pair.net_profit_loss / net_profit_rate
    unrealized: boolean                                      // status==='open'
    partial_gross_krw: number | null   // 보유 중 분할 매도 실현(세전) = 그 SELL 행 profit_loss 합(하나라도 NULL 이면 null)
    partial_net_krw: number | null     // = partial_gross_krw − partial_fee − partial_tax
    gross_na: NaKind | null            // gross 가 null 인 이유(보유 중 시세 대기 = 'pending')
    net_na: NaKind | null              // 'lookup_failed' | 'pending'
  }
  entry: {
    avg_price: number                  // pair.buy_price(가중평균, 원 내림)
    qty: number                        // 매수 체결 행 수량 합(보유 중 pair.buy_qty 는 잔량이라 쓰지 않는다)
    orders: OrderLine[]                // 매수 주문마다 1줄, 시간순
    reason: Reason
    initial_stop: StopPoint
    target: Target
  }
  exits: ExitLine[]                    // 매도 주문마다 1줄, 시간순. closed = sell_trade_ids, open = partial_sell_trade_ids
  stop_track: StopTrack
  costs: Costs
  excursion: Excursion
  note: { body: string; updated_at: string } | null
}

interface OrderLine {
  side: 'BUY' | 'SELL'
  order_no: string | null              // 없으면(수기·부팅 동기화 행) null — 일지 행과 잇지 않는다
  trade_ids: string[]
  at: string                           // 그 주문 첫 행 timestamp(KST ISO) — 「접수 직후 시각」
  price: number                        // 그 주문 행들의 수량 가중평균 체결가(원 내림)
  qty: number
  division: string | null; division_na: NaKind | null        // 주문구분 코드(01·00·27·41·44)
  source: string | null; source_na: NaKind | null            // trade_journal_orders.source
  path: 'accept' | 'fallback' | 'reorder' | 'manual' | null  // signal.path
  parent_order_no: string | null                             // 재주문이면 원주문
  judge: { price: number | null; upper: number | null
           src: 'signal' | 'log_price' | 'log_pct' | 'restored_ai' | null
           na: NaKind | null }
  slip_order: Slip | null; slip_order_na: NaKind | null      // 주문가 기준
  slip_judge: Slip | null              // 판단가 기준 — 주문가 기준과 같은 값이면 null(중복 표시 안 함)
}

interface Slip {
  ref_price: number
  ref_src: ValSrc                      // 주문가: 'trade'(trade_history.order_price) | 'live'/'restored'(일지 접수가) · 판단가: 'live'|'restored'|'derived'|'restored_ai'
  per_share_won: number                // 불리하면 +. 매수 = 체결가 − 기준가, 매도 = 기준가 − 체결가
  bp: number                           // per_share_won / ref_price × 10,000, 소수 1자리
  total_won: number                    // per_share_won × qty, 원 반올림
  bound: 'exact' | 'upper'             // 'upper' = 판단가 상한만 알 때(kojiro ATR 손절) → 화면 「≤」
}

interface ExitLine extends OrderLine {
  reason: Reason
  realized_gross_krw: number | null    // 그 주문 SELL 행 profit_loss 합(NULL 있으면 null)
  fired_line: number | null; fired_src: ValSrc | null        // 발동선(3-3절)
  effective_line: number | null; snapshot_age_s: number | null
  line_role: 'fired' | 'reference' | 'target' | null         // 가격 청산 / 가격 무관 청산의 참고값 / 익절 목표
  line_na: NaKind | null
}

interface Reason {
  code: string | null                  // ENTRY · Signal 값 · MANUAL · null(사유 없음)
  sub: string | null                   // reason_sub
  phrase: string | null                // signal.phrase
  renamed_from: string | null          // 접수 이름(signal.signal_name) ≠ code 일 때만(cycle402 이전 이름)
  text: string | null                  // 한 줄 문장 — 3절 규칙, 서버가 만든다
  src: ValSrc | null                   // 'live' | 'restored' | 'restored_ai' | 'inferred'
  signal_src: 'ring' | 'log_only' | 'none' | null            // 매수만
  na: NaKind | null
}

interface StopPoint {
  price: number | null; kind: string | null                  // kind = stop_kind
  pct_from_entry: number | null        // (price − avg_price) / avg_price × 100, 소수 2자리
  observed_at: string | null; delay_s: number | null         // 매수 시각 → 첫 관측까지
  na: NaKind | null
  first_seen: { price: number | null; kind: string | null; observed_at: string } | null  // na 일 때 참고로 보이는 첫 관측값
}

interface Target {
  kind: 'measured_move' | 'none'
  price: number | null; hit: boolean | null
  signal_price: number | null          // BFB 진입 신호의 측정 목표(signal.target_price)
  arm_price: number | null             // donchian 3R 무장가(무장 전 값)
  one_r_price: number | null           // donchian 1R 시간청산 면제선 = 2E − 무장 전 손절선
  armed_at: string | null              // donchian 무장 관측 시각(inputs.kk_armed 가 처음 true)
  text: string                         // 3-4절
  na: NaKind | null
}

interface StopTrack {
  na: NaKind | null                    // 기록 없음 이유
  first: number | null; last: number | null                 // 첫 값 · 청산 직전(또는 지금) 값
  ups: number; downs: number
  paused: boolean                      // paused 사건이 하나라도 있으면 true
  rows: StopRow[]
  hidden_eod: number                   // 값이 그대로라 숨긴 장마감 행 수
}
interface StopRow {
  at: string; event: 'first'|'change'|'boot'|'eod'|'paused'|'exit'
  price: number | null; kind: string | null
  delta_won: number | null; direction: 'up' | 'down' | 'flat' | null
  cause: string                        // 4-3절, 서버가 만든다
  target_price: number | null; target_hit: boolean | null; arm_price: number | null
  snapshot_age_s: number | null        // exit 행만
}

interface Costs {
  na: NaKind | null                    // 'lookup_failed'
  entry_fee: number | null; entry_status: CostStatus | null; entry_allocated: boolean
  exits: { order_no: string | null; at: string; fee: number | null; tax: number | null
           status: CostStatus | null; allocated: boolean }[]  // ExitLine 과 같은 순서
  fee_total: number | null; tax_total: number | null        // closed = pair.fee / pair.tax
  paid_total: number | null            // 이미 낸 비용 = entry_fee + Σexits(fee+tax)
  expected_exit: number | null         // 보유 중 남은 수량 예상 매도비용(추정) — closed 는 null + 'not_applicable'
  expected_exit_na: NaKind | null
  status: CostStatus | null; allocated: boolean             // = pair.cost_status / pair.allocated
}

interface Excursion {
  basis_price: number                  // = entry.avg_price
  mfe: ExPoint | null; mae: ExPoint | null
  closes_k: number; closes_n: number   // 종가를 찾은 날 / 15:30 에 들고 있던 영업일
  provisional_dates: string[]          // 잠정 봉 날짜(포함된 날 중)
  lock_dates: string[]                 // 락 표시 날짜(포함된 날 중)
  na: NaKind | null
}
interface ExPoint { pct: number; krw: number; date: string; close: number; qty: number; provisional: boolean }
```

- 시각은 전부 KST ISO `+09:00` 문자열(서버 `to_char(...,'+09:00')`·`_to_kst`). 날짜는 `YYYY-MM-DD`.
- **값이 있으면 그 `*_na` 는 null, 값이 null 이면 `*_na` 가 반드시 있다.** 0 으로 채우지 않는다(라우트 테스트로 고정 — 6절 T1).

### 1-3. `PUT /api/history/journal/notes/{anchor_trade_id}` (D2)

- 본문 `{ "body": string }`. 앞뒤 공백을 걷은 뒤 **4,000자 이하**(파이썬 `len`, 코드포인트 기준). 넘으면 422. 문자열이 아니면 422.
- `anchor_trade_id` 가 UUID 꼴이 아니면 422. `trade_history` 에 그 id 의 **BUY 행**이 없으면 404.
- 공백만이면 그 메모 행을 **지운다** → `data: null`. 그 밖은 upsert(`ON CONFLICT (anchor_trade_id) DO UPDATE SET body, updated_at=now()`), 중복 칸 `strategy`·`ticker`·`buy_date` 는 그 매수 행에서 채운다.
- 응답 `{success: true, data: {anchor_trade_id, body, created_at, updated_at} | null, message: ""}` — 시각 KST ISO.
- 인증은 기존 그대로다: 운영 키만. 리포터 키는 PUT 이 막혀 403, 상태 변경 Origin 검사도 기존 미들웨어가 한다. 마지막 저장이 이긴다(동시 편집 잠금 없음).
- 화면은 본문을 **글자 그대로**(줄바꿈 유지) 보인다. HTML·마크다운 해석 없음(`dangerouslySetInnerHTML` 금지).

---

## 2. 한국어 표기표 (트레이더 말, 짧게)

표기 정본은 프론트 상수 1곳(`frontend/src/utils/journalLabels.ts` — 이름은 구현 판단)이다. 서버는 **코드만** 보내고, 문장(이유·원인)만 서버가 만든다. 전략 이름은 기존 `strategyLabel()` 을 쓴다(새 사본 금지).

### 2-1. 청산 사유 `reason_code` → 짧은 배지

| 코드 | 배지 | 색 결 |
|---|---|---|
| `ENTRY` | 진입 | 중립 |
| `STOP_LOSS` | 손절 | 빨강 |
| `TRAILING_STOP` | 트레일링 | 주황 |
| `TAKE_PROFIT` | 익절 | 초록 |
| `TIME_EXIT` | 시간 청산 | 회색 |
| `TREND_EXIT` | 추세 종료 | 회색 |
| `FORCE_CLEAR` | 15:20 청산 | 회색 |
| `NEXT_DAY_CLEAR` | 익일 청산 | 회색 |
| `STATUS_EXIT` | 종목상태 청산 | 보라 |
| `MANUAL` | 수동 매도 | 파랑 |
| null | 사유 없음 | 회색 |

### 2-2. `reason_sub`

| 값 | 표기 |
|---|---|
| `gap_below` | 갭 미달 |
| `krx_only` | KRX 전용 |
| `nxt_open_missing` | NXT 시가 미수신 |
| `managed` | 관리종목 |
| `overheat` | 단기과열 |
| `managed+overheat` | 관리·과열 |
| 그 밖 | 원문 그대로 |

### 2-3. 사유 줄 `phrase` (툴팁·세부에 쓴다)

| phrase | 표기 | phrase | 표기 |
|---|---|---|---|
| `kojiro_hard_stop` | 하드 손절 | `bfb_time_exit` | 보유 기한 초과 |
| `kojiro_atr_stop` | ATR 손절 | `ltv_intraday_stop` | 당일 모드 손절 |
| `kojiro_trailing` | 샹들리에 트레일 | `ltv_limit_up_stop` | 상한가 모드 손절 |
| `kojiro_stage3_exit` | 스테이지3 — 추세 종료 | `vb_stop` | 고정 손절 |
| `bfb_turtle_stop` | 터틀 손절(E−2N) | `momentum_stop` | 고정 손절 |
| `bfb_turtle_backstop` | 받침선 손절 | `donchian_time_exit` | 시간 청산 |
| `bfb_pullback_stop` | 눌림목 손절 | `donchian_time_exit_legacy` | 시간 청산(옛 규칙) |
| `bfb_measured_target` | 측정 목표 도달 | `donchian_trailing_legacy` | 트레일(옛 규칙) |

### 2-4. 일지 행 출처 `source` · 경로 `path`

| `source` | 배지 | 뜻 |
|---|---|---|
| `log_harvest` | 기록 | 실시간 로그 수확(접수 줄로 주문번호에 정확히 묶임) |
| `log_restore` | 복원 | 과거 로그(09-17~10-08) 1회 적재 |
| `fallback_inferred` | 추정·폴백 | 5호가 폴백 — 같은 종목 줄을 시각으로 묶은 추정 |
| `reorder_inferred` | 추정·재주문 | 손절 잔여 재주문 — 원주문의 사유를 물려받은 추정 |
| `manual_api` | 수동 | 화면 수동 매도 |
| `external` | 외부 주문 | 접수 전문만 있고 엔진 줄이 없는 체결(HTS·MTS 로 본다) |
| `unmatched` | 매핑 없음 | 체결은 있는데 일지 줄을 못 찾음(외부라고 단정하지 않는다) |
| (행 없음) | 기록 전 / — | 5절 |

| `path` | 이유 문장 꼬리 |
|---|---|
| `accept` | (없음) |
| `fallback` | 「· 5호가 폴백」 |
| `reorder` | 「· 잔여 재주문(원주문 {parent_order_no})」 |
| `manual` | (문장 자체가 수동) |

### 2-5. 손절선 종류 `stop_kind` · 사건 `event`

| `stop_kind` | 표기 | 배지 |
|---|---|---|
| `effective` | 전략 손절선 | 없음 |
| `hard_pct` | 고정% 손절선 | **근사**(트레일·시간 청산은 못 담는다 — momentum·VB) |
| `mode_dependent` | 모드 의존 | 값 「—」(LTV — 당일/상한가 모드를 밖에서 알 수 없다) |
| `engine_idle` | 엔진 정지 | 값 「—」 |
| null | — | |

| `event` | 표기 | 강조 |
|---|---|---|
| `first` | 첫 관측 | |
| `change` | 변경 | 내려가면 빨강 |
| `boot` | 재시작 | 노랑 |
| `eod` | 장마감 | |
| `paused` | 손절 정지 | **빨강 경고** 「전략이 꺼져 손절 평가가 멈췄다」 |
| `exit` | 청산 직전 | |

### 2-6. 그 밖

| 대상 | 값 → 표기 |
|---|---|
| 주문구분 `division` | `01` 시장가 · `00` 지정가 · `27` 프리 GTP 지정가 · `41` 애프터 지정가 · `44` 애프터 최유리 · 그 밖 「코드 NN」 · null 은 5절 |
| 판단가 출처 `judge.src` | `signal` 신호 틱 가격 · `log_price` 로그 현재가 · `log_pct` **역산**(±0.05%p) · `restored_ai` 복원(AI평가) · 상한만이면 「≤ {upper}」 |
| 매수 `signal_src` | `ring` (배지 없음) · `log_only` 「신호가만」 · `none` 「신호 기록 없음」 |
| 값 출처 `ValSrc` | `trade` 없음 · `live` 기록 · `restored` 복원 · `restored_ai` 복원(AI평가) · `snapshot` 스냅샷(n초 전) · `derived` 계산 · `inferred` 추정 · `computed` 계산 |
| 비용 `CostStatus` | `settled` 정산 · `estimated` 추정 · `mixed` 일부 추정 · `allocated=true` 배분 |
| VB·LTV `board` | `main` 본장 · `pre_nxt` NXT 프리 · `post_nxt` NXT 애프터 |

---

## 3. 이유 문장 규칙 (서버 `journal_view` 가 읽을 때 만든다 — 저장하지 않는다)

공통: 가격은 천 단위 쉼표, 단위 생략(「12,300 돌파」). % 는 부호 붙여 소수 1자리. 절은 「 · 」로 잇는다. **키가 없는 절은 뺀다**(0 이나 「None」을 찍지 않는다). 절이 하나도 안 남으면 그 행의 대체 문장을 쓴다.

### 3-1. 진입 — `signal_src='ring'` (실시간, G0 신호 원본 + `params`)

| 전략 | 문장 | 쓰는 키 |
|---|---|---|
| `momentum` | 전일 종가 {prev_close} 대비 {change_rate}% 급등 · 기준 {buy_threshold}% | `prev_close`·`change_rate` · params `buy_threshold` |
| `volatility_breakout` | {board} 돌파선 {target_price} 돌파 · K {k:.2f} · 시가 대비 {change_rate}% | `board`·`target_price`·`k`·`change_rate` |
| `long_tail_volatility` | (위와 같음) | 같음 |
| `donchian_swing` | {donchian_period}일 신고가 {donchian_high} 돌파 · ATR {atr} | `donchian_high`·`atr` · params `donchian_period`(없으면 「신고가」) |
| `bull_flag_breakout` | 깃발 상단 {flag_high} 돌파 · 측정 목표 {target_price} · ATR {atr} | `flag_high`·`target_price`·`atr` |
| `vcp_breakout` | 베이스 고점 {base_high} 돌파 · ATR {atr} | `base_high`·`atr` |
| `kojiro` | 스테이지{stage} 신규 진입 · 이평 정배열 · ATR {atr} | `stage`·`atr` |
| `etf_trend` | 돌파선 {line} 종가 돌파(전일) · 시가 {open_price} 진입 · N {atr} | `line`·`open_price`·`atr` |
| 그 밖 | {전략 표시명} 매수 신호 | |

- VB·LTV 의 `target_price` 는 **매수 트리거**다. 진입 문장의 「돌파선」으로만 쓰고 익절 목표 칸에는 넣지 않는다.

### 3-2. 진입 — 그 밖의 경우

| 경우 | 문장 | `reason.src` |
|---|---|---|
| `log_only` + 신호가 있음 | 매수 신호 · 신호가 {judge} — 구조값 기록 없음 | `restored`(복원 행) / `live` |
| `log_only` + 신호가 없음(BFB·VCP 복원) | 거래량 관문 통과 매수 — 구조값 기록 없음 | 같음 |
| `none` | 매수 신호 기록 없음 | 같음 |
| 위 셋 + `llm_buy_evaluations` 행이 있음(아래) | {돌파선 이름} {target_won} 돌파 · (VB·LTV) K {k} · {board} | `restored_ai` |
| 일지 행 없음 | `text=null`, `na` = 5절 | — |

- **AI평가 보강**: `(trade_date, ticker, order_no)` 로 잇는다(`account_no` 는 보지 않는다 — 10-13 계좌 전환 뒤에도 같은 키). 돌파선 이름 = VB·LTV 「{board} 돌파선」 · donchian 「신고가」 · BFB 「깃발 상단」 · VCP 「베이스 고점」 · etf_trend 「돌파선」. momentum·kojiro 는 `target_won` 이 없어 보강하지 않는다.
- 🔴 **`target_won` 의 뜻은 2026-09-17(cycle297 — LLM 매수평가 5전략 확장) 전후로 다르다.** 그 전에는 모든 전략이 `target_price` 를 읽어서 BFB 는 측정 목표가가 들어 있다. 그래서 **`trade_date < 2026-09-17` 행은 VB·LTV 만** 보강하고, 나머지 전략은 보강하지 않는다.
- 판단가: `log_only` 행에 신호가가 없고 AI평가 행의 `signal_price_won` 이 있으면 그것을 `judge.src='restored_ai'` 로 쓴다.

### 3-3. 청산 — 문장과 선

**문장** (`code` → `phrase` → 숫자 키 순으로 고른다. `fired`·`eff` = `fired_line`·`effective_line`)

| code | 조건 | 문장 |
|---|---|---|
| `STOP_LOSS` | `kojiro_hard_stop`·`bfb_turtle_backstop`·`momentum_stop` | {phrase 표기} — 매수가 대비 {pct}% (기준 {threshold}%) |
| | `kojiro_atr_stop`·`bfb_turtle_stop` | {phrase 표기} — 손절선 {line} 이탈 |
| | `bfb_pullback_stop`·`vb_stop` | {phrase 표기} — 매수가 대비 {pct}% · 선 {fired} |
| | `ltv_intraday_stop`·`ltv_limit_up_stop` | {phrase 표기} — {pct}% · 선 {fired} |
| | phrase 없음(donchian·VCP·etf_trend 현행) | 손절선 {fired 또는 eff} 이탈 |
| `TRAILING_STOP` | `kojiro_trailing`·`donchian_trailing_legacy` | {phrase 표기} — 선 {line} 이탈 (현재가 {current_price}) |
| | phrase 없음 | 트레일선 {fired 또는 eff} 이탈 |
| `TAKE_PROFIT` | `bfb_measured_target` | 측정 목표 {target} 도달 — 전량 익절 (현재가 {current_price}) |
| `TIME_EXIT` | `donchian_time_exit` | `reason_line` 의 `reason=no_1r` → 「+1R 미도달 — 시간 청산」 · `reason=max_hold` → 「최대 보유 기간 도달 — 시간 청산」 · 못 읽으면 「시간 청산」 |
| | `bfb_time_exit` | 보유 기한 초과 — 시간 청산 |
| | `donchian_time_exit_legacy` | 돌파선 아래 — 시간 청산(옛 규칙) (현재가 {current_price}) |
| `TREND_EXIT` | `kojiro_stage3_exit` | 스테이지3 진입 — 추세 종료 |
| | etf_trend | 15:20 돌파선 아래 — 돌파 실패 정리 |
| | VCP·그 밖 | 추세 이탈 청산 |
| `FORCE_CLEAR` | | 15:20 강제청산 |
| `NEXT_DAY_CLEAR` | `gap_below` | 익일 청산 — 갭 {gap}% < 기준 {gap_threshold}% |
| | `krx_only` | 익일 청산 — KRX 전용 종목, 09:00 시장가 |
| | `nxt_open_missing` | 익일 청산 — NXT 시가 미수신, KRX 시가 뒤 |
| | sub 없음 | 익일 청산 |
| `STATUS_EXIT` | sub | {sub 표기} 지정 — 보유 청산 |
| `MANUAL` | | 수동 매도(화면) |
| null | `external` | 엔진 밖 주문(HTS·MTS) — 사유 기록 없음 |
| | `unmatched` | 사유 매핑 없음 |

- `reason_line` 원문은 문장에 쓰지 않는다(donchian 시간 청산의 `reason=` 한 토큰만 예외). 툴팁에 원문을 보일 수는 있다.
- `renamed_from`: 접수 이름(`signal.signal_name`)이 `code` 와 다르면 채운다 → 화면 툴팁 「접수 이름 {renamed_from} — 사유 줄로 보정」(cycle402 전 7건).
- 경로 꼬리(2-4)를 끝에 붙인다.

**발동선 출처 `fired_src`** — 워커가 `fired_line` 한 칸에 정확도가 다른 값을 넣으므로 화면이 구분한다.

| `signal` 에 있는 것 | `fired_src` | 정확도 |
|---|---|---|
| `line` | `live`(또는 `restored`) | 줄에 찍힌 선 — 정확 |
| `threshold` + `buy_price` | `derived` | 매수가 × 임계 — 정확 |
| `phrase` 가 `ltv_*` | `derived` | 스냅샷 파라미터로 계산 — PUT 이 없었으면 정확 |
| 그 밖(BFB 눌림목·VB 등) | `snapshot` | 직전 스냅샷 손절선 — 근사 |

**선의 역할 `line_role`**
- 가격 청산(`STOP_LOSS`·`TRAILING_STOP`) = `fired`: 「발동선 {fired}」 + 다르면 「유효선 {eff} ({snapshot_age_s}초 전)」. 둘 다 없으면 `line_na`.
- `TAKE_PROFIT` = `target`: 「목표 {target}」 + `eff` 가 있으면 「· 참고 손절선 {eff} ({n}초 전)」.
- 그 밖(시간·추세·15:20·익일·종목상태·수동·외부) = `reference`: 「손절 미발동 · 참고 손절선 {eff} ({n}초 전)」. `eff` 가 없으면 `line_na='unknown'`.
- 🔴 발동선이 유효선보다 **낮을 수 있다**(kojiro 검사 순서 하드→2ATR→샹들리에, BFB 받침선이 먼저 나감). 둘을 하나로 합치지 않는다.

**판단가 → 체결오차**
- 매도 판단가 = `judge_price`(`judge_src` `log_price`·`log_pct`). `judge_upper` 만 있으면 `judge.upper` 에 넣고 판단가 기준 체결오차는 `bound='upper'`(화면 「≤ +x bp」).
- `judge_src` 가 null 이면 판단가는 없다. 🔴 `trade_history.order_price` 를 판단가로 **옮겨 적지 않는다** — 매도 주문가는 「주문 접수 뒤 시세」라서 판단가가 아니고, 옮기면 두 기준이 같은 숫자가 되어 판단가 기준이 있는 것처럼 보인다(1a 계약 3.3 「1b 가 order_price 로 채운다」와 다르다 — 7절 C2).
- 주문가 기준: `trade_history.order_price`(src `trade`)가 있으면 그것. 없으면 일지 행 `order_price`(매수 접수가 · 매도 폴백 지정가, src `live`/`restored`). 둘 다 없으면 `slip_order_na`(5절).
- 판단가 기준은 **주문가 기준과 값이 같으면 보내지 않는다**(시장가 매수는 주문가 = 신호가라 대부분 같다).

### 3-4. 익절 목표 문장 (`target.text`)

| 전략 | 문장 |
|---|---|
| `bull_flag_breakout` | 측정 목표 {price} ({진입가 대비 +x%}) — 미도달 / **도달** · (signal_price ≠ price 면) 「재시작 뒤 다시 찾은 목표 — 진입 때 {signal_price}」 |
| `donchian_swing` | 없음 · 3R 무장가 {arm_price} · 1R 면제선 {one_r_price} · (무장되면) 「{armed_at} 무장 — 손절선 본전」 |
| `momentum` | 없음 — 익일 갭 판정·트레일 청산 |
| `volatility_breakout` | 없음 — 15:20 당일 청산 |
| `long_tail_volatility` | 없음 — 15:20·익일 청산 |
| `kojiro` | 없음 — 샹들리에 트레일·스테이지3 청산 |
| `vcp_breakout` | 없음 — 트레일·추세 이탈 청산 |
| `etf_trend` | 없음 — 트레일·채널 이탈·돌파 실패 정리 |

- BFB `price` = 그 보유의 마지막 손절선 행 `target_price`(없으면 진입 신호 `target_price`, `src`=진입 신호). `hit` = 어느 행이든 `target_hit=true` 이거나 청산 사유가 `TAKE_PROFIT`. BFB 는 닿으면 **전량** 판다(코드 기준 — 「부분 익절」이라고 쓰지 않는다).
- donchian `one_r_price` = `2 × E − (무장 전 손절선)`. 무장 전 손절선 = `arm_price` 가 찍힌 행의 `stop_price`(무장 전에는 `E − R` 로 고정이다). 그런 행이 없으면 null.
- 복원분 BFB 의 목표는 `before_record` 다 — AI평가 `target_won` 은 깃발 상단이지 측정 목표가가 아니다.

---

## 4. 손절선 — 최초값·변화·원인

### 4-1. 이 보유의 행 고르기
- `trade_journal_stops` 에서 `strategy`·`ticker` 가 같고 `observed_at ∈ [opened_at − 60초, (closed_at + 120초) 또는 지금]` 인 행.
- 단 `pos_order_no` 가 있고 페어 `buy_order_nos` 가 비어 있지 않은데 그 안에 없으면 뺀다(같은 (전략, 종목)의 다음 보유 방지 — 같은 날 재매수·전략 간 중복 매수는 엔진이 막으므로 기간만으로도 대부분 갈린다).

### 4-2. 최초 손절 (필수 ⑥)
- 고른 행 중 가장 이른 행. 그 행의 KST 날짜가 **매수일과 같으면** 최초 손절로 쓴다(`delay_s` = 관측 − 매수 시각, 300초를 넘으면 화면에 「n분 뒤 관측」).
- 매수일보다 뒤 날짜면 그 값은 최초 손절이 **아니다**(스윙 손절선은 하루만 지나도 움직인다). `price=null`, `na` = 매수가 `record_start.stops` 이전이면 `before_record`, 아니면 `unknown`. 그 행은 `first_seen` 으로 참고 표시한다(「첫 관측 10-12 11,980」).
- 행이 하나도 없으면: 매수가 기록 시작 전 → `before_record` · 아니면 `unknown`(「관측 기록 없음」 — 15초 안에 사고판 거래·워커 공백).
- `stop_kind='mode_dependent'`(LTV)면 `price=null`, `na='unknown'`, `kind` 는 그대로 → 화면 「— 모드 의존」.
- 🔴 과거 거래를 **지금 파라미터로 계산해 채우지 않는다**(계획 9절 — 손절률이 여러 번 바뀌어 틀린 값이 된다).

### 4-3. 변화 표 (필수 ⑦)
- **보이는 행**: `first`·`boot`·`paused`·`exit` 는 언제나. 그 밖(`change`·`eod`)은 직전에 **보인 행**과 `stop_price`·`stop_kind`·`target_price`·`target_hit`·`arm_price` 중 하나라도 다를 때만. 값이 그대로인 `eod` 는 숨기고 `hidden_eod` 로 센다.
- `direction` = 직전에 보인 행 중 값이 있는 것과 비교(`up`·`down`·`flat`), `delta_won` 함께. `first` 는 null.
- `ups`·`downs` = 보인 행의 `up`·`down` 수. `first` = 최초 손절(4-2)이 있으면 그 값, 없으면 첫 행 값 · `last` = 청산 직전(또는 지금) 마지막 값.
- **원인 `cause`** — 직전에 보인 행의 `inputs` 와 비교해 위에서부터 맞는 것을 **최대 2개** 「 · 」로 잇는다.

| 순서 | 조건 | 원인 |
|---|---|---|
| 1 | `event=='paused'` | 전략 꺼짐 — 손절 평가 정지 |
| 2 | `event=='exit'` | 청산 직전 스냅샷 ({snapshot_age_s}초 전) |
| 3 | `event=='boot'` | 재시작 재계산 (LTV 면 「· 상한가 모드 소실 가능」) |
| 4 | `inputs.quantity` 다름 | 수량 변화(추가 체결·분할 매도) |
| 5 | `inputs.buy_price` 다름 | 매수가 변화(추가 체결) |
| 6 | `inputs.kk_armed` false→true | 3R 도달 — 본전 무장 |
| 7 | `stop_kind` 다름 | 손절선 출처 바뀜 |
| 8 | 직전 값 < 매수가 ≤ 이번 값 | 본전 승격 |
| 9 | `inputs.high_since_buy` 커짐 | 고점 갱신 |
| 10 | `inputs.entry_atr` 다름 | ATR 변화 |
| 11 | `target_price`·`target_hit` 다름 | 목표 갱신 / 목표 도달 |
| 12 | `event=='first'` | 첫 관측 |
| 13 | 아무것도 아님 | 입력 그대로 — 파라미터 변경·일봉 재계산 추정 |

- **내림(`down`)은 빨강**이다. 손절선이 내려가는 것은 리스크가 커지는 쪽이라 복기 1순위다(재시작 재계산·ATR 변화·파라미터 PUT 이 원인). `paused` 가 하나라도 있으면 카드 머리에 빨강 경고를 띄운다.
- `exit` 행은 `stop_track.rows` 끝에 오고, 청산 줄의 「유효선」과 같은 값이다.

---

## 5. 「모름 / 기록 전 / 해당 없음」 구분

**원칙**: 숫자를 모르면 0 을 찍지 않는다. 빈칸의 **이유**를 세 가지(+둘)로 가르고, 화면은 이유마다 다르게 보인다.

| `na` | 화면 | 쓰는 때 (예) |
|---|---|---|
| `before_record` | 「기록 전」(연회색 작은 글씨) | 그 칸의 원천 기록이 시작되기 전 거래 — 09-17 전 진입 이유 · 10-12 전 진입의 최초 손절 · 10-07 전 매도 주문가 · 09-28 전 주문구분 |
| `unknown` | 「—」(회색, 툴팁 「모름 — {사유}」) | 기록 기간인데 값이 없다 — 관측 전 청산 · 워커 공백 · LTV 모드 의존 · 복원 LTV 발동선(파라미터 없음) · 판단가가 줄에 없음 |
| `not_applicable` | 「해당 없음」(연회색) | 그 거래에 개념이 없다 — VB 의 익절 목표 · 당일 청산의 MFE/MAE · 가격 무관 청산의 발동선 · 청산 페어의 예상 청산비용 |
| `pending` | 「대기」+ 사유 | 곧 생긴다 — 보유 중 시세 대기(현재가 미수신) · 오늘 종가 미적재(20:30 적재) |
| `lookup_failed` | 「—」+ 주황 「조회 실패」 | 원천 읽기 실패 — 비용(`cost_available=false`) · 일지 표 없음 · 종가 조회 실패 |

**기록 시작일 판정** — 날짜를 코드에 박지 않는다. 응답 `record_start` 의 값과 비교한다.
- 진입·청산 이유·판단가·발동선: 그 주문 날짜 < `orders_restored`(없으면 `orders_live`) → `before_record`.
- 최초 손절·변화·목표·무장가·유효선: `opened_at` 날짜 < `stops` → `before_record`. (보유가 기록 시작을 걸쳐 있으면 변화 표는 그 날부터만 있고, 머리에 「손절선 기록은 {stops}부터」.)
- 주문가 기준 체결오차: 체결 날짜 < `order_price` 이고 일지 접수가도 없음 → `before_record`.
- 주문구분: 일지 행이 있는데 `order_division` 이 null 이고 주문일 < 2026-09-28 → `before_record`(접수 전문 `[order_notice]` 이 그날 처음 나온다 — 고정 사실이라 상수로 둔다). 그 뒤면 `unknown`.

**카드 안내줄 `record_notice`**
- `before_orders`: 「기록 시작 전 거래 — 일자·가격·비용·평가손익만」(진입 이유·손절선·판단가가 모두 기록 전).
- `before_stops`: 「손절선 기록 시작({stops}) 전 진입 — 최초 손절·익절 목표는 기록 전」.

---

## 6. MFE / MAE — 보유 중 최대 평가이익·손실 (일별 종가, 필수 ⑩)

- **포함하는 날** = 그날 **15:30 에 들고 있던** 영업일만. 판정은 체결 행 시각으로 한다.
  - 매수 시각 < 그날 15:30 이고, 그날 15:30 에 남은 수량 > 0.
  - 15:30~20:00(KRX 애프터·NXT)에 판 날은 **포함**한다(15:30 종가 시점에 들고 있었다). 그 시간에 산 날은 다음 영업일부터다.
  - 당일 15:30 전에 다 판 거래(VB·LTV 대부분) → 포함하는 날 0 → `na='not_applicable'` 「해당 없음(당일 청산)」.
- **영업일 집합** = 그 페이지 카드 기간의 `stock_master_daily` `DISTINCT bas_dd`(한 종목이라도 행이 있는 날). 오늘 봉이 아직 없으면(20:30 적재 전) 오늘은 집합 밖이고, 보유 중이면 「오늘 종가 대기」를 덧붙인다. 🔴 휴장일을 KIS 로 묻지 않는다(이 사이클 KIS 호출 0).
- **기준가** = `entry.avg_price`(평균 매수가, 계획 9절). `pct = (종가 − 기준가) / 기준가 × 100`(소수 2자리) · `krw = (종가 − 기준가) × 그날 15:30 보유 수량`(원 반올림) · `qty` 함께.
- **MFE** = 포함한 날 중 `pct` 최대, **MAE** = 최소(같은 값이면 이른 날).
  - MAE ≥ 0 → 화면 「손실 구간 없음 (최저 +x.xx%)」. MFE ≤ 0 → 「이익 구간 없음 (최고 −x.xx%)」. 값은 그대로 보낸다(화면이 문구를 고른다).
- **결측** = 있는 종가로만 계산하고 `closes_k / closes_n` 을 보인다(「종가 3/4일」). k = 0 이고 n > 0 → `na='unknown'`(「종가 없음 0/n일」). 조회 실패 → `lookup_failed`.
- **잠정 봉** = `updated_at < (bas_dd + 1일) 06:00 KST`(`stock_master_daily.list_provisional_rows` 와 같은 판정 — 「20:30 에 쓴 그날 봉은 다음 아침에 확정」). 포함한 날 중 잠정이면 `provisional_dates` 에, MFE·MAE 날 자체가 잠정이면 그 `ExPoint.provisional=true` → 「잠정」 배지.
- **락**(액면분할·배당락 등) = `flng_cls_code ∉ {'', '00'}` 이거나 `prtt_rate ≠ 0`(`_row_has_lock` 과 같은 판정). 보정하지 않고 `lock_dates` 로 「락 — 수정주가 미보정」 배지만 단다.
- 매수가 정확도 한계: 매수 `price` 는 마지막 체결통보 가격이라 분할 체결 매수는 기준가가 조금 어긋난다(계획 10절). 표시하지 않는다.

---

## 7. 현 코드·계약과의 정합성 (워커는 고치지 않는다 — 보고만)

| # | 차이 | 이 명세의 처리 |
|---|---|---|
| **C1** | `trade_journal_orders.exchange` 를 워커가 **항상 NULL** 로 쓴다(`jw/pairing.py::_finalize` `"exchange": None`). 관찰자 설계는 「확보한 것만 채운다」였다 | 거래소는 카드에 **보이지 않는다**(필수 10항목 아님). 채우려면 워커 사이클 — 지금 정하지 않는다 |
| **C2** | 1a 계약 3.3 「매도 `judge_price` 가 없으면 1b 가 `trade_history.order_price` 로 채운다」 | **따르지 않는다.** 매도 주문가는 「주문 접수 뒤 시세」라 판단가가 아니다. 판단가 없음 → 판단가 기준 체결오차를 보이지 않고 주문가 기준만 보인다(계획 2절 ④ 「D1 미승인이면 주문가 기준만」과 같은 결론) |
| **C3** | 워커 `fired_line` 은 한 칸에 정확도 4종(줄의 선·임계 계산·LTV 파라미터·스냅샷)을 섞는다 | `fired_src` 를 `signal` 키로 다시 가려 보낸다(3-3절 표). 워커는 그대로 |
| **C4** | 복원 LTV 손절 5행은 `fired_line` 이 NULL(파라미터 사본 없음) | `line_na='unknown'` 툴팁 「복원분 — 당시 파라미터 없음」. 지금 파라미터로 채우지 않는다 |
| **C5** | 10-12 전부터 들고 있던 종목의 첫 `first` 행은 최초 손절이 아니다 | 4-2절 「매수일과 같은 날 관측만 최초」 규칙 |
| **C6** | `overlay_pairs()` 는 체결 행 단위 비용을 돌려주지 않는다 | 1-1절 — 비용 원천 한 번 읽기 + 패리티 T3. cost_overlay 를 고치면 c411 테스트 전부 다시 돌린다 |
| **C7** | 계획 6절 API 에는 `outcome`·`basis`·`sort` 가 없다 | 계획 6절 「필터: 이익/손실」을 쿼리로 옮긴 것이다. 정렬은 「최근 청산 먼저」 기본 + 손익 두 방향 |
| C8 | 메모 표는 047 에 이미 있다 | 마이그레이션 0 |

---

## 8. 화면 구성 (텍스트 와이어)

### 8-1. 탭과 머리
- 「거래 내역」 메뉴의 세 번째 탭 **「거래일지」**(`History.tsx` `TabKey` 에 `journal`). 기본 탭은 지금처럼 「주문체결내역」.
- 탭 머리줄: 제목 옆에 기존 `CostBasisToggle`(`useCostBasis` 공유 — 다른 화면 토글과 함께 바뀐다).
- 그 아래 **기록 시작일 한 줄**(`journal-record-start`): 「이유 기록 {orders_restored}부터({orders_live} 전은 과거 로그 복원) · 손절선 기록 {stops}부터」. 값이 null 이면 「실시간 기록 대기」.
- 필터줄: 기간(7일·**30일**·90일·직접) · 전략 · 종목코드 · 보유중/청산/전체 · 이익/손실/전체 · 정렬(최근·손실 큰 순·이익 큰 순) · 건수 「총 n · 보유 a · 청산 b」. 400px 에서는 「필터」 버튼 하나로 접고, 걸린 필터를 칩으로 보인다.

### 8-2. 카드 (400px 기준 — 좌우 여백 16px, 가로 스크롤 0, 숫자는 `tabular-nums` 오른쪽 정렬)

```
┌─ journal-card-{anchor_trade_id} ───────────────────┐
│ 에코프로비엠 247540                  [청산] 3일     │ 머리1  종목명 코드 · 상태 · 보유(당일/n일)
│ 추세 눌림목 돌파 · 10-06 09:12 → 10-09 14:31        │ 머리2  전략 · 진입 → 청산 시각
│ 세후 +41,464  +8.39%            세전 +44,000       │ 머리3  토글 기준 값 크게, 다른 기준 작게
│ ⚠ 손절 평가 정지 구간 있음                          │ (paused 일 때만, 빨강)
│ ⓘ 기록 시작 전 거래 — 일자·가격·비용·평가손익만     │ (record_notice 일 때만)
├ 진입 ──────────────────────────────────────────────┤
│ 10-06 09:12:03   12,350 × 40          [시장가]     │ 주문 1줄(분할 진입이면 줄이 늘어난다)
│ 깃발 상단 12,300 돌파 · 측정 목표 13,450 · ATR 410  │ 이유 [기록]/[복원]/[복원(AI평가)]
│ 체결오차 +8.1bp (주문가)                            │ 판단가 = 주문가라 한 줄(다를 때만 둘)
│ 최초 손절 11,530 (−6.64%)                          │ 4-2 (momentum·VB 면 [근사])
│ 익절 목표 13,450 (+8.91%) — 도달                    │ 3-4
├ ▸ 손절선 변화  11,530 → 12,350   ↑2 ↓1            ┤ 접힘(기본). ↓n 은 빨강
│   10-06 09:12  첫 관측     11,530                    │ 펼치면 2줄짜리 목록(표가 아니다)
│   10-07 15:31  장마감     11,980 ↑+450  고점 갱신   │   시각·사건·값·변화·원인
│   10-08 09:00  재시작     11,900 ↓−80   재시작 재계산│   (↓ 빨강, 재시작 노랑)
│   10-08 10:41  변경       12,350 ↑+450  본전 승격   │
│   10-09 14:31  청산 직전   12,350 →   스냅샷 8초 전  │
│   (값 그대로인 장마감 1건 숨김)                       │
├ 청산 ──────────────────────────────────────────────┤
│ 10-09 14:31:20   13,450 × 40   [시장가] [익절]      │
│ 측정 목표 13,450 도달 — 전량 익절 (현재가 13,460)    │ 이유 + 경로 꼬리
│ 목표 13,450 · 참고 손절선 12,350 (8초 전)            │ 손절이면 「발동선 x [출처] · 유효선 y」
│ 체결오차 0.0bp (주문가) · 판단가 13,460 +7.4bp       │
├ 비용 ──────────────────────────────────────────────┤
│ 진입 수수료 701 · 청산 수수료 764 · 세금 1,071       │
│ 합계 2,536                           [정산]         │ 보유 중이면 「낸 비용 x · 예상 청산비용 y [추정]」
├ 보유 중 평가 (일별 종가) ───────────────────────────┤
│ 최대 이익  +6.23%  +30,800  10-08     종가 3/3일    │ 잠정·락 배지는 이 줄 끝
│ 최대 손실  손실 구간 없음 (최저 +0.81%)             │
├ 메모 ──────────────────────────────────────────────┤
│ [ textarea                                     ]   │ 0 / 4,000
│                                   [저장] 저장됨 14:03│ 바뀌면 「저장 안 됨」
└────────────────────────────────────────────────────┘
```

- **분할 매도**: 청산 영역에 매도 주문마다 위 4줄 묶음을 반복하고, 비용 영역도 매도 주문마다 한 줄. 보유 중 페어의 분할 매도는 「분할 매도」 제목으로 같은 모양 + 머리3 아래 「분할 실현 세후 +x」.
- **보유 중**: 청산 영역 자리에 「보유 중 · 지금 손절선 {last} ({stop_kind 배지})」 한 줄. 머리3 은 「미실현」 꼬리표, 시세를 모르면 「미실현 시세 대기」.
- 768px 이상: 진입·청산을 두 칸으로 나란히, 손절선 변화는 표(시각·사건·값·변화·원인 5칸)로. 그 밖은 같다.
- 시각 표기는 `src/utils/kst.ts` 의 `formatKstDateTime` 을 잘라 쓴다(`MM-DD HH:mm:ss` = `.slice(5)`). 새 `Intl.DateTimeFormat` 금지.
- 「출처 배지」는 작은 회색 칩이다: 기록 · 복원 · 복원(AI평가) · 스냅샷 · 계산 · 추정 · 근사. `trade`(거래기록 원본)는 칩을 달지 않는다.
- 메모: 저장은 버튼(또는 Ctrl/⌘+Enter)으로만 — 자동 저장 없음. 카운터는 4,000 을 넘으면 빨강 + 저장 비활성. 실패하면 입력 내용을 그대로 두고 「저장 실패」.

### 8-3. 화면 testid (Red 가 쓰는 최소 집합)
`history-tab-journal` · `journal-record-start` · `journal-card-{anchor_trade_id}` · `journal-head-pnl` · `journal-paused-warning` · `journal-record-notice` · `journal-entry-reason` · `journal-initial-stop` · `journal-target` · `journal-stop-toggle` · `journal-stop-row` · `journal-exit-{order_no 또는 index}` · `journal-exit-reason` · `journal-exit-line` · `journal-cost-total` · `journal-mfe` · `journal-mae` · `journal-note-input` · `journal-note-save` · `journal-na-{na}`(모든 빈칸 표시가 이 testid 를 단다).

---

## 9. 후속 검증 권고 (tdd-engineer / tester)

**백엔드 순수 함수 (`journal_view`)**
- T1 「모름 ≠ 0」: 값이 null 이면 그 `*_na` 가 있고, 숫자 칸에 0 이 없다(비용 조회 실패 · 보유 중 시세 None · 일지 표 없음 · 종가 0개 4경우).
- T2 체결오차 부호: 매수 체결 > 주문가 → +, 매도 체결 < 주문가 → +. bp 소수 1자리. 판단가 = 주문가면 `slip_judge=null`. 상한만이면 `bound='upper'`.
- T3 패리티: 닫힌 페어에서 (a) 진입+청산 `slip_order.total_won` 중 `ref_src='trade'` 인 것의 합 = c411 `slippage_won`(±1원) (b) `entry_fee + Σexits.fee` = `pair.fee`, `Σexits.tax` = `pair.tax`(±0.01) (c) 머리 `net_krw` = `/api/history/pnl` 같은 페어 `net_profit_loss`.
- T4 MFE/MAE: 15:20 청산(포함 0일 → 해당 없음) · 16:02 애프터 매도(그날 포함) · 16:30 매수(다음 날부터) · 분할 매도 날 수량 · 결측 k/n · 잠정·락 날짜 · 손실 구간 없음.
- T5 최초 손절: 매수일 관측 = 최초 · 다음 날 첫 관측 = `before_record`/`unknown` + `first_seen` · LTV `mode_dependent` · 행 0.
- T6 변화 표: 값 그대로 `eod` 숨김·카운트 · 내림 방향 · 원인 우선순위(표 13줄 각 1건) · `pos_order_no` 가 다른 다음 보유 행 배제.
- T7 이유 문장: 3-1 전략 8개 각 1건(예: BFB 「깃발 상단 12,300 돌파 · 측정 목표 13,450 · ATR 410」) · 키 빠진 절 생략 · `log_only`/`none` · AI평가 보강(09-17 전 BFB 는 보강 안 함) · 3-3 표 각 행 1건 · `renamed_from` · 경로 꼬리.
- T8 골든: 위 재생 145행을 pg 하네스에 넣고 페어로 묶어 카드 75장이 나오고 「사유 없음」 매도 0, BFB·VCP 복원 진입 15장이 「거래량 관문 통과 매수 — 구조값 기록 없음」(AI평가 행 없을 때).

**라우트**
- 필터: 기간 겹침 규칙(기간 전에 사서 기간 안에 판 것 포함 · 기간 뒤에 산 것 제외) · `outcome`×`basis` · 정렬 3종(모름 맨 뒤) · 422 4종 · `size` 상한.
- 실패 격리: 일지 표 없음·종가 조회 실패·비용 실패 각각 200 + 해당 칸만 `lookup_failed`.
- 메모 PUT: 4,000자 통과 / 4,001자 422 · 공백만 = 삭제 · 없는 id 404 · UUID 아님 422 · 리포터 키 403 · GET 에 반영.

**프론트 (vitest + RTL + MSW)**
- MSW 핸들러 `GET /api/history/journal`·`PUT …/notes/:id` 는 **이 명세의 키 그대로**(예시 카드에 na 5종이 모두 한 번씩 나오게).
- 세후/세전 토글이 머리3 큰 글씨를 바꾸고, 다른 화면 토글과 같이 움직인다.
- `journal-na-*`: 다섯 na 가 서로 다른 문구로 보이고 「0」·「0원」이 없다.
- 손절선 변화 접힘 기본 · ↓ 행 빨강 · `paused` 경고.
- 400px: 가로 스크롤 0(카드 너비 ≤ 뷰포트), 손절선 변화가 표가 아니라 목록.

**tester(통합)**
- 10-12 장 뒤 실데이터로 카드 3종(실시간 진입 1 · 복원 1 · 보유 중 1)을 눈으로 대조한다 — 잔고 화면 손절가 = 카드 「지금 손절선」, 매매손익 탭 세후 = 카드 머리.

---

## 10. 반례 / 한계

- **스냅샷 유효선은 최대 15초 전 값**이다. 그 15초 안에 고점·무장·래치·파라미터가 바뀌었으면 주문 순간 값과 다르다(`snapshot_age_s` 로만 드러난다).
- **`hard_pct` 근사**(momentum·VB)는 momentum D+1 트레일·VB 실패 돌파 조기청산을 담지 못한다. 실제 걸린 선은 청산 사유로 사후 확인한다.
- **원인 추정은 추정이다.** `inputs` 7칸만 비교하므로 파라미터 PUT·일봉 재계산·VCP `base_low` 재탐색 실패는 「입력 그대로 — 추정」으로 뭉친다.
- **AI평가 보강은 그 전략이 그날 LLM 평가를 돌렸을 때만** 있다(전략별 `llm_gate_mode` 운영값 미확인). 없으면 복원 진입은 「신호가만」으로 남는다.
- **영업일 집합을 DB 로 정하므로** 적재가 통째로 빠진 날은 n 에서도 빠진다(결측이 아니라 「휴장」처럼 보인다).
- **`get_trade_pairs` 는 매 요청 전체 `trade_history` 를 읽는다**(`/pnl` 과 같음). 거래가 수만 건이 되면 다시 본다.

## 지금 정하지 않는 것 (새 제안 금지 — 기록만)
- R 배수(손익 ÷ 최초 리스크)·MFE 대비 반납폭 같은 파생 지표는 넣지 않았다. 필수 10항목을 다 보인 뒤 사용자가 쓰면서 원하면 따로 정한다.
- 거래소 칸(C1)은 워커 사이클 몫이다.
