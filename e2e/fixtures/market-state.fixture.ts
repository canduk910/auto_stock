/**
 * cycle282 Red — Playwright 용 `GET /api/market-state` 골든 픽스처.
 *
 * `frontend/src/test/fixtures/marketState.fixture.ts` 와 **같은 생성기 산출물**이다
 * (e2e 는 frontend tsconfig 밖이라 교차 import 대신 같은 내용을 각자 보유한다).
 * 손으로 고치지 않는다 — 표가 바뀌면 생성기
 * `tools/test_fixtures/gen_market_state_fixture.py` 로 두 파일을 함께 재생성한다.
 */

export interface MarketStateWindow {
  start: string
  end: string
}

export interface MarketStateDivisionsByRow {
  row_id: string
  codes: string[]
}

/** `markets[<market>]` — 서버가 판정한 **커서 1개**. 프론트는 이 값을 그릴 뿐 다시 계산하지 않는다. */
export interface MarketStateCursor {
  market: string
  market_label_ko: string
  row_id: string | null
  phase: string
  name_ko: string
  tone: string
  window: MarketStateWindow | null
  match_kind: string
  match_ko: string
  is_open: boolean
  can_order: boolean
  market_order_ok: boolean
  order_divisions: string[]
  order_divisions_by_row: MarketStateDivisionsByRow[]
  concurrent_row_ids: string[]
  quote_channel: string | null
  quote_channel_evidence: string
  decided_by: string
  code_seen: string | null
  confidence: string
  confidence_notes: string[]
  seconds_to_next: number | null
  next_boundary: string | null
  next_row_id: string | null
  next_phase: string | null
}

export interface MarketStateTableRow {
  row_id: string
  market: string
  start: string
  end: string
  phase: string
  name_ko: string
  tone: string
  match_kind: string
  match_ko: string
  order_divisions: string[]
  order_divisions_pending: string[]
  order_divisions_expired: string[]
  can_order: boolean
  market_order_ok: boolean
  quote_channel: string | null
  quote_channel_evidence: string
  overlap_ok: boolean
  priority: number
  effective_from: string | null
  effective_to: string | null
  confidence: string
  note: string
  /** 서버 판정 — `past`/`current`/`concurrent`/`upcoming`/`unknown`. 프론트가 시각으로 다시 재지 않는다. */
  rel: string
}

export interface OrderDivisionRow {
  code: string
  name_ko: string
  group_ko: string | null
  /** 거래소별 3상태 — `yes`(●) / `unknown`(?) / `no`(빈칸). "미지원"과 "미확인"은 다르다. */
  exchange_support: Record<string, string>
  effective_from: string | null
  effective_to: string | null
  confidence: string
  note: string
}

export interface MarketPhaseSpec {
  id: string
  label_ko: string
  tone: string
}

export interface MarketStateVocab {
  tones: string[]
  rels: string[]
  support_levels: string[]
  confidences: string[]
  division_confidences: string[]
}

export interface MarketStateData {
  table_version: string
  as_of_kst: string
  on_date: string
  preview: boolean
  cursor_disabled_reason: string | null
  /** `true` 개장 · `false` 휴장 · `null` **확인 불가**(임의 True/False 금지 — M10). */
  is_trading_day: boolean | null
  trading_day_source: string
  market_order: string[]
  exchange_order: string[]
  /** preview(다른 날짜 조회)면 `null` — 커서는 "지금" 에만 의미가 있다. */
  markets: Record<string, MarketStateCursor> | null
  table: MarketStateTableRow[]
  order_divisions: OrderDivisionRow[]
  phases: MarketPhaseSpec[]
  vocab: MarketStateVocab
  findings: string[]
  board_note: string
  unconfirmed_note: string
}

/** M7 가드가 읽는 **금지어 목록**. 손으로 적지 않는다 — 표에서 생성된다. */
export interface MarketStateForbidden {
  rowIds: string[]
  divisionCodes: string[]
  rowNames: string[]
  divisionNames: string[]
  phases: string[]
  markets: string[]
}

export const MARKET_STATE_AT_0835: MarketStateData = {
  "table_version": "2026-09-11",
  "as_of_kst": "2026-09-11T08:35:10+09:00",
  "on_date": "2026-09-11",
  "preview": false,
  "cursor_disabled_reason": null,
  "is_trading_day": true,
  "trading_day_source": "kis",
  "market_order": [
    "KRX",
    "NXT"
  ],
  "exchange_order": [
    "KRX",
    "NXT",
    "SOR"
  ],
  "markets": {
    "KRX": {
      "market": "KRX",
      "market_label_ko": "KRX(한국거래소)",
      "row_id": "K1",
      "phase": "PRE_AUCTION",
      "name_ko": "시가 단일가",
      "tone": "auction",
      "window": {
        "start": "08:20:00",
        "end": "09:00:00"
      },
      "match_kind": "single_auction",
      "match_ko": "단일가(09:00 일괄)",
      "is_open": true,
      "can_order": true,
      "market_order_ok": true,
      "order_divisions": [
        "00",
        "01",
        "05"
      ],
      "order_divisions_by_row": [
        {
          "row_id": "K1",
          "codes": [
            "00",
            "01"
          ]
        },
        {
          "row_id": "K2",
          "codes": [
            "05"
          ]
        }
      ],
      "concurrent_row_ids": [
        "K2"
      ],
      "quote_channel": "H0STCNT0",
      "quote_channel_evidence": "assumed",
      "decided_by": "time",
      "code_seen": null,
      "confidence": "unconfirmed",
      "confidence_notes": [
        "시작 08:20 이 2026-09-14 개편분인지 미확인(종전 08:30). 09-14 이전 날짜에서는 08:20~08:30 을 과다 표시할 수 있다."
      ],
      "seconds_to_next": 290,
      "next_boundary": "08:40:00",
      "next_row_id": "K1",
      "next_phase": "PRE_AUCTION"
    },
    "NXT": {
      "market": "NXT",
      "market_label_ko": "NXT(넥스트레이드)",
      "row_id": "N1",
      "phase": "PRE_MARKET",
      "name_ko": "프리마켓",
      "tone": "active",
      "window": {
        "start": "08:00:00",
        "end": "08:50:00"
      },
      "match_kind": "continuous",
      "match_ko": "실시간",
      "is_open": true,
      "can_order": true,
      "market_order_ok": false,
      "order_divisions": [
        "00",
        "03",
        "04",
        "11",
        "12",
        "13",
        "14",
        "15",
        "16",
        "21",
        "22",
        "23",
        "24"
      ],
      "order_divisions_by_row": [
        {
          "row_id": "N1",
          "codes": [
            "00",
            "03",
            "04",
            "11",
            "12",
            "13",
            "14",
            "15",
            "16",
            "21",
            "22",
            "23",
            "24"
          ]
        }
      ],
      "concurrent_row_ids": [],
      "quote_channel": "H0NXCNT0",
      "quote_channel_evidence": "assumed",
      "decided_by": "time",
      "code_seen": null,
      "confidence": "confirmed",
      "confidence_notes": [],
      "seconds_to_next": 890,
      "next_boundary": "08:50:00",
      "next_row_id": "N2",
      "next_phase": "BREAK"
    }
  },
  "table": [
    {
      "row_id": "K1",
      "market": "KRX",
      "start": "08:20:00",
      "end": "09:00:00",
      "phase": "PRE_AUCTION",
      "name_ko": "시가 단일가",
      "tone": "auction",
      "match_kind": "single_auction",
      "match_ko": "단일가(09:00 일괄)",
      "order_divisions": [
        "00",
        "01"
      ],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": true,
      "market_order_ok": true,
      "quote_channel": "H0STCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": false,
      "priority": 10,
      "effective_from": null,
      "effective_to": null,
      "confidence": "unconfirmed",
      "note": "시작 08:20 이 2026-09-14 개편분인지 미확인(종전 08:30). 09-14 이전 날짜에서는 08:20~08:30 을 과다 표시할 수 있다.",
      "rel": "current"
    },
    {
      "row_id": "K2",
      "market": "KRX",
      "start": "08:30:00",
      "end": "08:40:00",
      "phase": "PRE_CLOSE_FIXED",
      "name_ko": "장전 시간외 종가",
      "tone": "fixed",
      "match_kind": "fixed_price",
      "match_ko": "전일 종가 고정",
      "order_divisions": [
        "05"
      ],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": true,
      "market_order_ok": false,
      "quote_channel": "H0STCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": true,
      "priority": 20,
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "K1(시가 단일가) 안에 들어 있는 의도된 중첩. 08:30~08:40 에는 00·01·05 가 동시에 쓸 수 있다.",
      "rel": "concurrent"
    },
    {
      "row_id": "K3",
      "market": "KRX",
      "start": "09:00:00",
      "end": "15:20:00",
      "phase": "REGULAR",
      "name_ko": "정규장",
      "tone": "active",
      "match_kind": "continuous",
      "match_ko": "실시간 접속매매",
      "order_divisions": [
        "00",
        "01",
        "02",
        "03",
        "04",
        "11",
        "12",
        "13",
        "14",
        "15",
        "16",
        "21",
        "22",
        "23",
        "24"
      ],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": true,
      "market_order_ok": true,
      "quote_channel": "H0STCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": false,
      "priority": 10,
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "",
      "rel": "upcoming"
    },
    {
      "row_id": "K4",
      "market": "KRX",
      "start": "15:20:00",
      "end": "15:30:00",
      "phase": "CLOSE_AUCTION",
      "name_ko": "종가 단일가",
      "tone": "auction",
      "match_kind": "single_auction",
      "match_ko": "단일가(15:30 일괄)",
      "order_divisions": [
        "00",
        "01"
      ],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": true,
      "market_order_ok": true,
      "quote_channel": "H0STCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": false,
      "priority": 10,
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "",
      "rel": "upcoming"
    },
    {
      "row_id": "K5",
      "market": "KRX",
      "start": "15:30:00",
      "end": "16:00:00",
      "phase": "AFTER_CLOSE_FIXED",
      "name_ko": "장후 시간외 종가",
      "tone": "fixed",
      "match_kind": "fixed_price",
      "match_ko": "당일 종가 고정",
      "order_divisions": [
        "06"
      ],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": true,
      "market_order_ok": false,
      "quote_channel": "H0STCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": false,
      "priority": 10,
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "",
      "rel": "upcoming"
    },
    {
      "row_id": "K7",
      "market": "KRX",
      "start": "16:00:00",
      "end": "18:00:00",
      "phase": "AFTER_SINGLE",
      "name_ko": "시간외 단일가",
      "tone": "auction",
      "match_kind": "periodic_auction",
      "match_ko": "10분 주기",
      "order_divisions": [
        "07"
      ],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": true,
      "market_order_ok": false,
      "quote_channel": "H0STCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": true,
      "priority": 10,
      "effective_from": null,
      "effective_to": "2026-09-12",
      "confidence": "confirmed",
      "note": "2026-09-12 폐지. K6 과는 유효기간이 갈려 어떤 날짜에도 공존하지 않는다(B3).",
      "rel": "upcoming"
    },
    {
      "row_id": "N1",
      "market": "NXT",
      "start": "08:00:00",
      "end": "08:50:00",
      "phase": "PRE_MARKET",
      "name_ko": "프리마켓",
      "tone": "active",
      "match_kind": "continuous",
      "match_ko": "실시간",
      "order_divisions": [
        "00",
        "03",
        "04",
        "11",
        "12",
        "13",
        "14",
        "15",
        "16",
        "21",
        "22",
        "23",
        "24"
      ],
      "order_divisions_pending": [
        "27",
        "28",
        "29"
      ],
      "order_divisions_expired": [],
      "can_order": true,
      "market_order_ok": false,
      "quote_channel": "H0NXCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": false,
      "priority": 10,
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "27~29(GTP)는 2026-09-14 부터 유효 — 그 이전 날짜에는 order_divisions_pending 으로 빠진다.",
      "rel": "current"
    },
    {
      "row_id": "N2",
      "market": "NXT",
      "start": "08:50:00",
      "end": "09:00:00",
      "phase": "BREAK",
      "name_ko": "휴장",
      "tone": "break",
      "match_kind": "none",
      "match_ko": "—",
      "order_divisions": [],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": false,
      "market_order_ok": false,
      "quote_channel": "H0NXCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": false,
      "priority": 10,
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "휴장 — 주문 접수 불가.",
      "rel": "upcoming"
    },
    {
      "row_id": "N3",
      "market": "NXT",
      "start": "09:00:30",
      "end": "15:20:00",
      "phase": "REGULAR",
      "name_ko": "정규장",
      "tone": "active",
      "match_kind": "continuous",
      "match_ko": "실시간",
      "order_divisions": [
        "00",
        "03",
        "04",
        "11",
        "12",
        "13",
        "14",
        "15",
        "16",
        "21",
        "22",
        "23",
        "24"
      ],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": true,
      "market_order_ok": false,
      "quote_channel": "H0NXCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": false,
      "priority": 10,
      "effective_from": null,
      "effective_to": null,
      "confidence": "unconfirmed",
      "note": "시작 09:00:30 미확인. 09:00:00~09:00:29 은 N2(휴장)로 남는다 — 표대로 옮겼을 뿐 실측 근거는 없다.",
      "rel": "upcoming"
    },
    {
      "row_id": "N4",
      "market": "NXT",
      "start": "15:20:00",
      "end": "15:30:00",
      "phase": "BREAK",
      "name_ko": "휴장",
      "tone": "break",
      "match_kind": "none",
      "match_ko": "—",
      "order_divisions": [],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": false,
      "market_order_ok": false,
      "quote_channel": "H0NXCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": false,
      "priority": 10,
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "휴장 — 주문 접수 불가.",
      "rel": "upcoming"
    },
    {
      "row_id": "N5",
      "market": "NXT",
      "start": "15:30:00",
      "end": "15:40:00",
      "phase": "AFTER_SINGLE",
      "name_ko": "애프터 단일가",
      "tone": "auction",
      "match_kind": "single_auction",
      "match_ko": "단일가",
      "order_divisions": [],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": false,
      "market_order_ok": false,
      "quote_channel": "H0NXCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": false,
      "priority": 10,
      "effective_from": null,
      "effective_to": null,
      "confidence": "unconfirmed",
      "note": "단일가 구간인 것은 확정이나 쓸 수 있는 주문유형이 미확인이다. NXT 코드 목록에 단일가 전용 코드가 없다. is_open=True 이지만 can_order=False 다 — 이 구간의 주문 가능 여부를 이 표로 판단하지 말 것.",
      "rel": "upcoming"
    },
    {
      "row_id": "N6",
      "market": "NXT",
      "start": "15:40:00",
      "end": "20:00:00",
      "phase": "AFTER_MARKET",
      "name_ko": "애프터마켓",
      "tone": "active",
      "match_kind": "continuous",
      "match_ko": "실시간",
      "order_divisions": [
        "00",
        "03",
        "04",
        "11",
        "12",
        "13",
        "14",
        "15",
        "16",
        "21",
        "22",
        "23",
        "24"
      ],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": true,
      "market_order_ok": false,
      "quote_channel": "H0NXCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": false,
      "priority": 10,
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "",
      "rel": "upcoming"
    }
  ],
  "order_divisions": [
    {
      "code": "00",
      "name_ko": "지정가",
      "group_ko": null,
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "yes"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "01",
      "name_ko": "시장가",
      "group_ko": null,
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "yes"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "NXT 에는 시장가가 없다(발견 1)."
    },
    {
      "code": "02",
      "name_ko": "조건부지정가",
      "group_ko": null,
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "no"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "03",
      "name_ko": "최유리지정가",
      "group_ko": null,
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "yes"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "04",
      "name_ko": "최우선지정가",
      "group_ko": null,
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "yes"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "05",
      "name_ko": "장전시간외",
      "group_ko": null,
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "no"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "SOR 에 없다(발견 2)."
    },
    {
      "code": "06",
      "name_ko": "장후시간외",
      "group_ko": null,
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "no"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "SOR 에 없다(발견 2)."
    },
    {
      "code": "07",
      "name_ko": "시간외단일가",
      "group_ko": null,
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "no"
      },
      "effective_from": null,
      "effective_to": "2026-09-12",
      "confidence": "confirmed",
      "note": "2026-09-12 폐지. SOR 에 없다(발견 2)."
    },
    {
      "code": "11",
      "name_ko": "IOC지정가",
      "group_ko": "IOC/FOK",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "yes"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "12",
      "name_ko": "FOK지정가",
      "group_ko": "IOC/FOK",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "yes"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "13",
      "name_ko": "IOC시장가",
      "group_ko": "IOC/FOK",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "yes"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "14",
      "name_ko": "FOK시장가",
      "group_ko": "IOC/FOK",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "yes"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "15",
      "name_ko": "IOC최유리",
      "group_ko": "IOC/FOK",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "yes"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "16",
      "name_ko": "FOK최유리",
      "group_ko": "IOC/FOK",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "yes"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "21",
      "name_ko": "중간가",
      "group_ko": "중간가/스톱",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "no"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "22",
      "name_ko": "스톱지정가",
      "group_ko": "중간가/스톱",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "no"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "23",
      "name_ko": "중간가IOC",
      "group_ko": "중간가/스톱",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "no"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "24",
      "name_ko": "중간가FOK",
      "group_ko": "중간가/스톱",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "no"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "27",
      "name_ko": "NXT GTP지정가",
      "group_ko": "NXT GTP(27~29)",
      "exchange_support": {
        "KRX": "no",
        "NXT": "yes",
        "SOR": "unknown"
      },
      "effective_from": "2026-09-14",
      "effective_to": null,
      "confidence": "confirmed",
      "note": "명칭 확정 — 공지 2026-09-09(시행 09-14) 원문. 미체결잔량은 프리마켓 종료(08:50) 일괄 취소."
    },
    {
      "code": "28",
      "name_ko": "NXT GTP최유리",
      "group_ko": "NXT GTP(27~29)",
      "exchange_support": {
        "KRX": "no",
        "NXT": "yes",
        "SOR": "unknown"
      },
      "effective_from": "2026-09-14",
      "effective_to": null,
      "confidence": "confirmed",
      "note": "명칭 확정 — 공지 2026-09-09(시행 09-14) 원문. 미체결잔량은 프리마켓 종료(08:50) 일괄 취소."
    },
    {
      "code": "29",
      "name_ko": "NXT GTP최우선",
      "group_ko": "NXT GTP(27~29)",
      "exchange_support": {
        "KRX": "no",
        "NXT": "yes",
        "SOR": "unknown"
      },
      "effective_from": "2026-09-14",
      "effective_to": null,
      "confidence": "confirmed",
      "note": "명칭 확정 — 공지 2026-09-09(시행 09-14) 원문. 미체결잔량은 프리마켓 종료(08:50) 일괄 취소."
    },
    {
      "code": "41",
      "name_ko": "KRX애프터마켓지정가",
      "group_ko": "KRX 애프터마켓(41~47)",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "unknown"
      },
      "effective_from": "2026-09-14",
      "effective_to": null,
      "confidence": "confirmed",
      "note": "명칭 확정 — 공지 2026-09-09(시행 09-14) 원문. 애프터마켓은 시장가 불가·ETP 불가."
    },
    {
      "code": "42",
      "name_ko": "KRX애프터마켓지정가IOC",
      "group_ko": "KRX 애프터마켓(41~47)",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "unknown"
      },
      "effective_from": "2026-09-14",
      "effective_to": null,
      "confidence": "confirmed",
      "note": "명칭 확정 — 공지 2026-09-09(시행 09-14) 원문. 애프터마켓은 시장가 불가·ETP 불가."
    },
    {
      "code": "43",
      "name_ko": "KRX애프터마켓지정가FOK",
      "group_ko": "KRX 애프터마켓(41~47)",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "unknown"
      },
      "effective_from": "2026-09-14",
      "effective_to": null,
      "confidence": "confirmed",
      "note": "명칭 확정 — 공지 2026-09-09(시행 09-14) 원문. 애프터마켓은 시장가 불가·ETP 불가."
    },
    {
      "code": "44",
      "name_ko": "KRX애프터마켓최유리지정가",
      "group_ko": "KRX 애프터마켓(41~47)",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "unknown"
      },
      "effective_from": "2026-09-14",
      "effective_to": null,
      "confidence": "confirmed",
      "note": "명칭 확정 — 공지 2026-09-09(시행 09-14) 원문. 애프터마켓은 시장가 불가·ETP 불가."
    },
    {
      "code": "45",
      "name_ko": "KRX애프터마켓최유리지정가IOC",
      "group_ko": "KRX 애프터마켓(41~47)",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "unknown"
      },
      "effective_from": "2026-09-14",
      "effective_to": null,
      "confidence": "confirmed",
      "note": "명칭 확정 — 공지 2026-09-09(시행 09-14) 원문. 애프터마켓은 시장가 불가·ETP 불가."
    },
    {
      "code": "46",
      "name_ko": "KRX애프터마켓최유리지정가FOK",
      "group_ko": "KRX 애프터마켓(41~47)",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "unknown"
      },
      "effective_from": "2026-09-14",
      "effective_to": null,
      "confidence": "confirmed",
      "note": "명칭 확정 — 공지 2026-09-09(시행 09-14) 원문. 애프터마켓은 시장가 불가·ETP 불가."
    },
    {
      "code": "47",
      "name_ko": "KRX애프터마켓최우선지정가",
      "group_ko": "KRX 애프터마켓(41~47)",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "unknown"
      },
      "effective_from": "2026-09-14",
      "effective_to": null,
      "confidence": "confirmed",
      "note": "명칭 확정 — 공지 2026-09-09(시행 09-14) 원문. 애프터마켓은 시장가 불가·ETP 불가."
    }
  ],
  "phases": [
    {
      "id": "PRE_AUCTION",
      "label_ko": "시가 단일가",
      "tone": "auction"
    },
    {
      "id": "PRE_MARKET",
      "label_ko": "프리마켓",
      "tone": "active"
    },
    {
      "id": "REGULAR",
      "label_ko": "정규장",
      "tone": "active"
    },
    {
      "id": "CLOSE_AUCTION",
      "label_ko": "종가 단일가",
      "tone": "auction"
    },
    {
      "id": "PRE_CLOSE_FIXED",
      "label_ko": "장전 시간외 종가",
      "tone": "fixed"
    },
    {
      "id": "AFTER_CLOSE_FIXED",
      "label_ko": "장후 시간외 종가",
      "tone": "fixed"
    },
    {
      "id": "AFTER_SINGLE",
      "label_ko": "단일가(시간외·애프터)",
      "tone": "auction"
    },
    {
      "id": "AFTER_MARKET",
      "label_ko": "애프터마켓",
      "tone": "active"
    },
    {
      "id": "BREAK",
      "label_ko": "휴장",
      "tone": "break"
    },
    {
      "id": "CLOSED",
      "label_ko": "장 종료",
      "tone": "closed"
    }
  ],
  "vocab": {
    "tones": [
      "active",
      "auction",
      "fixed",
      "break",
      "closed",
      "unknown"
    ],
    "rels": [
      "past",
      "current",
      "concurrent",
      "upcoming",
      "unknown"
    ],
    "support_levels": [
      "yes",
      "unknown",
      "no"
    ],
    "confidences": [
      "confirmed",
      "unconfirmed",
      "ambiguous"
    ],
    "division_confidences": [
      "confirmed",
      "name_unconfirmed",
      "unconfirmed"
    ]
  },
  "findings": [
    "NXT 에 시장가(01)가 없다. 우리 주문의 1차 유형이 시장가다. 프리장 지정가 사전 변환은 우회가 아니라 구조적 필연이었다. 대안은 13 IOC시장가 / 14 FOK시장가다.",
    "SOR 에 시간외 코드(05·06·07)가 없다. 다만 cycle287(2026-09-12)부터 **시각이 거래소를 정하므로**(정규장·애프터 = KRX, 프리장만 전략 설정값) 우리 주문은 09:00 이후 SOR 로 나가지 않는다. 이 열은 KIS 지원 사실만 표시한다.",
    "SOR 은 주문 경로에서 **폐기**됐다(사용자 결정 2026-09-12). 전략 설정의 SOR 선택지는 폐기 표시로 남아 있고 프리장 밖에서는 값이 무엇이든 KRX 로 나간다. 이 표의 SOR 열은 삭제하지 않는다 — 41~47 의 SOR 지원 여부가 아직 **확인 필요**이고, 그 미확인을 화면에서 지우면 44 의 단가 규약이 미검증이라는 사실도 함께 사라진다."
  ],
  "board_note": "이 화면은 거래소의 실제 장 운영 상태다. 우리 시스템의 매매 보드(PRE_NXT/MAIN/POST_NXT)와는 경계가 다르다 — 우리 MAIN 보드는 15:39:59 까지지만 KRX 정규장은 15:20 에 끝난다. 보드는 우리 매매 규약이고 이 표는 거래소 사실이다. 둘을 같은 것으로 읽지 말 것.",
  "unconfirmed_note": "⚠️ 표시 항목은 아직 KIS 정본으로 확인하지 못했다. 이 사이클은 추측으로 채우지 않고 그대로 드러낸다. 확인 경로 = KIS MCP 스펙 조회 + 2026-09-14 이후 실측."
}

export const MARKET_STATE_AT_1305: MarketStateData = {
  "table_version": "2026-09-11",
  "as_of_kst": "2026-09-11T13:05:22+09:00",
  "on_date": "2026-09-11",
  "preview": false,
  "cursor_disabled_reason": null,
  "is_trading_day": true,
  "trading_day_source": "kis",
  "market_order": [
    "KRX",
    "NXT"
  ],
  "exchange_order": [
    "KRX",
    "NXT",
    "SOR"
  ],
  "markets": {
    "KRX": {
      "market": "KRX",
      "market_label_ko": "KRX(한국거래소)",
      "row_id": "K3",
      "phase": "REGULAR",
      "name_ko": "정규장",
      "tone": "active",
      "window": {
        "start": "09:00:00",
        "end": "15:20:00"
      },
      "match_kind": "continuous",
      "match_ko": "실시간 접속매매",
      "is_open": true,
      "can_order": true,
      "market_order_ok": true,
      "order_divisions": [
        "00",
        "01",
        "02",
        "03",
        "04",
        "11",
        "12",
        "13",
        "14",
        "15",
        "16",
        "21",
        "22",
        "23",
        "24"
      ],
      "order_divisions_by_row": [
        {
          "row_id": "K3",
          "codes": [
            "00",
            "01",
            "02",
            "03",
            "04",
            "11",
            "12",
            "13",
            "14",
            "15",
            "16",
            "21",
            "22",
            "23",
            "24"
          ]
        }
      ],
      "concurrent_row_ids": [],
      "quote_channel": "H0STCNT0",
      "quote_channel_evidence": "assumed",
      "decided_by": "time",
      "code_seen": null,
      "confidence": "confirmed",
      "confidence_notes": [],
      "seconds_to_next": 8078,
      "next_boundary": "15:20:00",
      "next_row_id": "K4",
      "next_phase": "CLOSE_AUCTION"
    },
    "NXT": {
      "market": "NXT",
      "market_label_ko": "NXT(넥스트레이드)",
      "row_id": "N3",
      "phase": "REGULAR",
      "name_ko": "정규장",
      "tone": "active",
      "window": {
        "start": "09:00:30",
        "end": "15:20:00"
      },
      "match_kind": "continuous",
      "match_ko": "실시간",
      "is_open": true,
      "can_order": true,
      "market_order_ok": false,
      "order_divisions": [
        "00",
        "03",
        "04",
        "11",
        "12",
        "13",
        "14",
        "15",
        "16",
        "21",
        "22",
        "23",
        "24"
      ],
      "order_divisions_by_row": [
        {
          "row_id": "N3",
          "codes": [
            "00",
            "03",
            "04",
            "11",
            "12",
            "13",
            "14",
            "15",
            "16",
            "21",
            "22",
            "23",
            "24"
          ]
        }
      ],
      "concurrent_row_ids": [],
      "quote_channel": "H0NXCNT0",
      "quote_channel_evidence": "assumed",
      "decided_by": "time",
      "code_seen": null,
      "confidence": "unconfirmed",
      "confidence_notes": [
        "시작 09:00:30 미확인. 09:00:00~09:00:29 은 N2(휴장)로 남는다 — 표대로 옮겼을 뿐 실측 근거는 없다."
      ],
      "seconds_to_next": 8078,
      "next_boundary": "15:20:00",
      "next_row_id": "N4",
      "next_phase": "BREAK"
    }
  },
  "table": [
    {
      "row_id": "K1",
      "market": "KRX",
      "start": "08:20:00",
      "end": "09:00:00",
      "phase": "PRE_AUCTION",
      "name_ko": "시가 단일가",
      "tone": "auction",
      "match_kind": "single_auction",
      "match_ko": "단일가(09:00 일괄)",
      "order_divisions": [
        "00",
        "01"
      ],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": true,
      "market_order_ok": true,
      "quote_channel": "H0STCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": false,
      "priority": 10,
      "effective_from": null,
      "effective_to": null,
      "confidence": "unconfirmed",
      "note": "시작 08:20 이 2026-09-14 개편분인지 미확인(종전 08:30). 09-14 이전 날짜에서는 08:20~08:30 을 과다 표시할 수 있다.",
      "rel": "past"
    },
    {
      "row_id": "K2",
      "market": "KRX",
      "start": "08:30:00",
      "end": "08:40:00",
      "phase": "PRE_CLOSE_FIXED",
      "name_ko": "장전 시간외 종가",
      "tone": "fixed",
      "match_kind": "fixed_price",
      "match_ko": "전일 종가 고정",
      "order_divisions": [
        "05"
      ],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": true,
      "market_order_ok": false,
      "quote_channel": "H0STCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": true,
      "priority": 20,
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "K1(시가 단일가) 안에 들어 있는 의도된 중첩. 08:30~08:40 에는 00·01·05 가 동시에 쓸 수 있다.",
      "rel": "past"
    },
    {
      "row_id": "K3",
      "market": "KRX",
      "start": "09:00:00",
      "end": "15:20:00",
      "phase": "REGULAR",
      "name_ko": "정규장",
      "tone": "active",
      "match_kind": "continuous",
      "match_ko": "실시간 접속매매",
      "order_divisions": [
        "00",
        "01",
        "02",
        "03",
        "04",
        "11",
        "12",
        "13",
        "14",
        "15",
        "16",
        "21",
        "22",
        "23",
        "24"
      ],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": true,
      "market_order_ok": true,
      "quote_channel": "H0STCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": false,
      "priority": 10,
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "",
      "rel": "current"
    },
    {
      "row_id": "K4",
      "market": "KRX",
      "start": "15:20:00",
      "end": "15:30:00",
      "phase": "CLOSE_AUCTION",
      "name_ko": "종가 단일가",
      "tone": "auction",
      "match_kind": "single_auction",
      "match_ko": "단일가(15:30 일괄)",
      "order_divisions": [
        "00",
        "01"
      ],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": true,
      "market_order_ok": true,
      "quote_channel": "H0STCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": false,
      "priority": 10,
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "",
      "rel": "upcoming"
    },
    {
      "row_id": "K5",
      "market": "KRX",
      "start": "15:30:00",
      "end": "16:00:00",
      "phase": "AFTER_CLOSE_FIXED",
      "name_ko": "장후 시간외 종가",
      "tone": "fixed",
      "match_kind": "fixed_price",
      "match_ko": "당일 종가 고정",
      "order_divisions": [
        "06"
      ],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": true,
      "market_order_ok": false,
      "quote_channel": "H0STCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": false,
      "priority": 10,
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "",
      "rel": "upcoming"
    },
    {
      "row_id": "K7",
      "market": "KRX",
      "start": "16:00:00",
      "end": "18:00:00",
      "phase": "AFTER_SINGLE",
      "name_ko": "시간외 단일가",
      "tone": "auction",
      "match_kind": "periodic_auction",
      "match_ko": "10분 주기",
      "order_divisions": [
        "07"
      ],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": true,
      "market_order_ok": false,
      "quote_channel": "H0STCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": true,
      "priority": 10,
      "effective_from": null,
      "effective_to": "2026-09-12",
      "confidence": "confirmed",
      "note": "2026-09-12 폐지. K6 과는 유효기간이 갈려 어떤 날짜에도 공존하지 않는다(B3).",
      "rel": "upcoming"
    },
    {
      "row_id": "N1",
      "market": "NXT",
      "start": "08:00:00",
      "end": "08:50:00",
      "phase": "PRE_MARKET",
      "name_ko": "프리마켓",
      "tone": "active",
      "match_kind": "continuous",
      "match_ko": "실시간",
      "order_divisions": [
        "00",
        "03",
        "04",
        "11",
        "12",
        "13",
        "14",
        "15",
        "16",
        "21",
        "22",
        "23",
        "24"
      ],
      "order_divisions_pending": [
        "27",
        "28",
        "29"
      ],
      "order_divisions_expired": [],
      "can_order": true,
      "market_order_ok": false,
      "quote_channel": "H0NXCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": false,
      "priority": 10,
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "27~29(GTP)는 2026-09-14 부터 유효 — 그 이전 날짜에는 order_divisions_pending 으로 빠진다.",
      "rel": "past"
    },
    {
      "row_id": "N2",
      "market": "NXT",
      "start": "08:50:00",
      "end": "09:00:00",
      "phase": "BREAK",
      "name_ko": "휴장",
      "tone": "break",
      "match_kind": "none",
      "match_ko": "—",
      "order_divisions": [],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": false,
      "market_order_ok": false,
      "quote_channel": "H0NXCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": false,
      "priority": 10,
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "휴장 — 주문 접수 불가.",
      "rel": "past"
    },
    {
      "row_id": "N3",
      "market": "NXT",
      "start": "09:00:30",
      "end": "15:20:00",
      "phase": "REGULAR",
      "name_ko": "정규장",
      "tone": "active",
      "match_kind": "continuous",
      "match_ko": "실시간",
      "order_divisions": [
        "00",
        "03",
        "04",
        "11",
        "12",
        "13",
        "14",
        "15",
        "16",
        "21",
        "22",
        "23",
        "24"
      ],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": true,
      "market_order_ok": false,
      "quote_channel": "H0NXCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": false,
      "priority": 10,
      "effective_from": null,
      "effective_to": null,
      "confidence": "unconfirmed",
      "note": "시작 09:00:30 미확인. 09:00:00~09:00:29 은 N2(휴장)로 남는다 — 표대로 옮겼을 뿐 실측 근거는 없다.",
      "rel": "current"
    },
    {
      "row_id": "N4",
      "market": "NXT",
      "start": "15:20:00",
      "end": "15:30:00",
      "phase": "BREAK",
      "name_ko": "휴장",
      "tone": "break",
      "match_kind": "none",
      "match_ko": "—",
      "order_divisions": [],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": false,
      "market_order_ok": false,
      "quote_channel": "H0NXCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": false,
      "priority": 10,
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "휴장 — 주문 접수 불가.",
      "rel": "upcoming"
    },
    {
      "row_id": "N5",
      "market": "NXT",
      "start": "15:30:00",
      "end": "15:40:00",
      "phase": "AFTER_SINGLE",
      "name_ko": "애프터 단일가",
      "tone": "auction",
      "match_kind": "single_auction",
      "match_ko": "단일가",
      "order_divisions": [],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": false,
      "market_order_ok": false,
      "quote_channel": "H0NXCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": false,
      "priority": 10,
      "effective_from": null,
      "effective_to": null,
      "confidence": "unconfirmed",
      "note": "단일가 구간인 것은 확정이나 쓸 수 있는 주문유형이 미확인이다. NXT 코드 목록에 단일가 전용 코드가 없다. is_open=True 이지만 can_order=False 다 — 이 구간의 주문 가능 여부를 이 표로 판단하지 말 것.",
      "rel": "upcoming"
    },
    {
      "row_id": "N6",
      "market": "NXT",
      "start": "15:40:00",
      "end": "20:00:00",
      "phase": "AFTER_MARKET",
      "name_ko": "애프터마켓",
      "tone": "active",
      "match_kind": "continuous",
      "match_ko": "실시간",
      "order_divisions": [
        "00",
        "03",
        "04",
        "11",
        "12",
        "13",
        "14",
        "15",
        "16",
        "21",
        "22",
        "23",
        "24"
      ],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": true,
      "market_order_ok": false,
      "quote_channel": "H0NXCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": false,
      "priority": 10,
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "",
      "rel": "upcoming"
    }
  ],
  "order_divisions": [
    {
      "code": "00",
      "name_ko": "지정가",
      "group_ko": null,
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "yes"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "01",
      "name_ko": "시장가",
      "group_ko": null,
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "yes"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "NXT 에는 시장가가 없다(발견 1)."
    },
    {
      "code": "02",
      "name_ko": "조건부지정가",
      "group_ko": null,
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "no"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "03",
      "name_ko": "최유리지정가",
      "group_ko": null,
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "yes"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "04",
      "name_ko": "최우선지정가",
      "group_ko": null,
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "yes"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "05",
      "name_ko": "장전시간외",
      "group_ko": null,
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "no"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "SOR 에 없다(발견 2)."
    },
    {
      "code": "06",
      "name_ko": "장후시간외",
      "group_ko": null,
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "no"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "SOR 에 없다(발견 2)."
    },
    {
      "code": "07",
      "name_ko": "시간외단일가",
      "group_ko": null,
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "no"
      },
      "effective_from": null,
      "effective_to": "2026-09-12",
      "confidence": "confirmed",
      "note": "2026-09-12 폐지. SOR 에 없다(발견 2)."
    },
    {
      "code": "11",
      "name_ko": "IOC지정가",
      "group_ko": "IOC/FOK",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "yes"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "12",
      "name_ko": "FOK지정가",
      "group_ko": "IOC/FOK",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "yes"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "13",
      "name_ko": "IOC시장가",
      "group_ko": "IOC/FOK",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "yes"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "14",
      "name_ko": "FOK시장가",
      "group_ko": "IOC/FOK",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "yes"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "15",
      "name_ko": "IOC최유리",
      "group_ko": "IOC/FOK",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "yes"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "16",
      "name_ko": "FOK최유리",
      "group_ko": "IOC/FOK",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "yes"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "21",
      "name_ko": "중간가",
      "group_ko": "중간가/스톱",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "no"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "22",
      "name_ko": "스톱지정가",
      "group_ko": "중간가/스톱",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "no"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "23",
      "name_ko": "중간가IOC",
      "group_ko": "중간가/스톱",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "no"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "24",
      "name_ko": "중간가FOK",
      "group_ko": "중간가/스톱",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "no"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "27",
      "name_ko": "NXT GTP지정가",
      "group_ko": "NXT GTP(27~29)",
      "exchange_support": {
        "KRX": "no",
        "NXT": "yes",
        "SOR": "unknown"
      },
      "effective_from": "2026-09-14",
      "effective_to": null,
      "confidence": "confirmed",
      "note": "명칭 확정 — 공지 2026-09-09(시행 09-14) 원문. 미체결잔량은 프리마켓 종료(08:50) 일괄 취소."
    },
    {
      "code": "28",
      "name_ko": "NXT GTP최유리",
      "group_ko": "NXT GTP(27~29)",
      "exchange_support": {
        "KRX": "no",
        "NXT": "yes",
        "SOR": "unknown"
      },
      "effective_from": "2026-09-14",
      "effective_to": null,
      "confidence": "confirmed",
      "note": "명칭 확정 — 공지 2026-09-09(시행 09-14) 원문. 미체결잔량은 프리마켓 종료(08:50) 일괄 취소."
    },
    {
      "code": "29",
      "name_ko": "NXT GTP최우선",
      "group_ko": "NXT GTP(27~29)",
      "exchange_support": {
        "KRX": "no",
        "NXT": "yes",
        "SOR": "unknown"
      },
      "effective_from": "2026-09-14",
      "effective_to": null,
      "confidence": "confirmed",
      "note": "명칭 확정 — 공지 2026-09-09(시행 09-14) 원문. 미체결잔량은 프리마켓 종료(08:50) 일괄 취소."
    },
    {
      "code": "41",
      "name_ko": "KRX애프터마켓지정가",
      "group_ko": "KRX 애프터마켓(41~47)",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "unknown"
      },
      "effective_from": "2026-09-14",
      "effective_to": null,
      "confidence": "confirmed",
      "note": "명칭 확정 — 공지 2026-09-09(시행 09-14) 원문. 애프터마켓은 시장가 불가·ETP 불가."
    },
    {
      "code": "42",
      "name_ko": "KRX애프터마켓지정가IOC",
      "group_ko": "KRX 애프터마켓(41~47)",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "unknown"
      },
      "effective_from": "2026-09-14",
      "effective_to": null,
      "confidence": "confirmed",
      "note": "명칭 확정 — 공지 2026-09-09(시행 09-14) 원문. 애프터마켓은 시장가 불가·ETP 불가."
    },
    {
      "code": "43",
      "name_ko": "KRX애프터마켓지정가FOK",
      "group_ko": "KRX 애프터마켓(41~47)",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "unknown"
      },
      "effective_from": "2026-09-14",
      "effective_to": null,
      "confidence": "confirmed",
      "note": "명칭 확정 — 공지 2026-09-09(시행 09-14) 원문. 애프터마켓은 시장가 불가·ETP 불가."
    },
    {
      "code": "44",
      "name_ko": "KRX애프터마켓최유리지정가",
      "group_ko": "KRX 애프터마켓(41~47)",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "unknown"
      },
      "effective_from": "2026-09-14",
      "effective_to": null,
      "confidence": "confirmed",
      "note": "명칭 확정 — 공지 2026-09-09(시행 09-14) 원문. 애프터마켓은 시장가 불가·ETP 불가."
    },
    {
      "code": "45",
      "name_ko": "KRX애프터마켓최유리지정가IOC",
      "group_ko": "KRX 애프터마켓(41~47)",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "unknown"
      },
      "effective_from": "2026-09-14",
      "effective_to": null,
      "confidence": "confirmed",
      "note": "명칭 확정 — 공지 2026-09-09(시행 09-14) 원문. 애프터마켓은 시장가 불가·ETP 불가."
    },
    {
      "code": "46",
      "name_ko": "KRX애프터마켓최유리지정가FOK",
      "group_ko": "KRX 애프터마켓(41~47)",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "unknown"
      },
      "effective_from": "2026-09-14",
      "effective_to": null,
      "confidence": "confirmed",
      "note": "명칭 확정 — 공지 2026-09-09(시행 09-14) 원문. 애프터마켓은 시장가 불가·ETP 불가."
    },
    {
      "code": "47",
      "name_ko": "KRX애프터마켓최우선지정가",
      "group_ko": "KRX 애프터마켓(41~47)",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "unknown"
      },
      "effective_from": "2026-09-14",
      "effective_to": null,
      "confidence": "confirmed",
      "note": "명칭 확정 — 공지 2026-09-09(시행 09-14) 원문. 애프터마켓은 시장가 불가·ETP 불가."
    }
  ],
  "phases": [
    {
      "id": "PRE_AUCTION",
      "label_ko": "시가 단일가",
      "tone": "auction"
    },
    {
      "id": "PRE_MARKET",
      "label_ko": "프리마켓",
      "tone": "active"
    },
    {
      "id": "REGULAR",
      "label_ko": "정규장",
      "tone": "active"
    },
    {
      "id": "CLOSE_AUCTION",
      "label_ko": "종가 단일가",
      "tone": "auction"
    },
    {
      "id": "PRE_CLOSE_FIXED",
      "label_ko": "장전 시간외 종가",
      "tone": "fixed"
    },
    {
      "id": "AFTER_CLOSE_FIXED",
      "label_ko": "장후 시간외 종가",
      "tone": "fixed"
    },
    {
      "id": "AFTER_SINGLE",
      "label_ko": "단일가(시간외·애프터)",
      "tone": "auction"
    },
    {
      "id": "AFTER_MARKET",
      "label_ko": "애프터마켓",
      "tone": "active"
    },
    {
      "id": "BREAK",
      "label_ko": "휴장",
      "tone": "break"
    },
    {
      "id": "CLOSED",
      "label_ko": "장 종료",
      "tone": "closed"
    }
  ],
  "vocab": {
    "tones": [
      "active",
      "auction",
      "fixed",
      "break",
      "closed",
      "unknown"
    ],
    "rels": [
      "past",
      "current",
      "concurrent",
      "upcoming",
      "unknown"
    ],
    "support_levels": [
      "yes",
      "unknown",
      "no"
    ],
    "confidences": [
      "confirmed",
      "unconfirmed",
      "ambiguous"
    ],
    "division_confidences": [
      "confirmed",
      "name_unconfirmed",
      "unconfirmed"
    ]
  },
  "findings": [
    "NXT 에 시장가(01)가 없다. 우리 주문의 1차 유형이 시장가다. 프리장 지정가 사전 변환은 우회가 아니라 구조적 필연이었다. 대안은 13 IOC시장가 / 14 FOK시장가다.",
    "SOR 에 시간외 코드(05·06·07)가 없다. 다만 cycle287(2026-09-12)부터 **시각이 거래소를 정하므로**(정규장·애프터 = KRX, 프리장만 전략 설정값) 우리 주문은 09:00 이후 SOR 로 나가지 않는다. 이 열은 KIS 지원 사실만 표시한다.",
    "SOR 은 주문 경로에서 **폐기**됐다(사용자 결정 2026-09-12). 전략 설정의 SOR 선택지는 폐기 표시로 남아 있고 프리장 밖에서는 값이 무엇이든 KRX 로 나간다. 이 표의 SOR 열은 삭제하지 않는다 — 41~47 의 SOR 지원 여부가 아직 **확인 필요**이고, 그 미확인을 화면에서 지우면 44 의 단가 규약이 미검증이라는 사실도 함께 사라진다."
  ],
  "board_note": "이 화면은 거래소의 실제 장 운영 상태다. 우리 시스템의 매매 보드(PRE_NXT/MAIN/POST_NXT)와는 경계가 다르다 — 우리 MAIN 보드는 15:39:59 까지지만 KRX 정규장은 15:20 에 끝난다. 보드는 우리 매매 규약이고 이 표는 거래소 사실이다. 둘을 같은 것으로 읽지 말 것.",
  "unconfirmed_note": "⚠️ 표시 항목은 아직 KIS 정본으로 확인하지 못했다. 이 사이클은 추측으로 채우지 않고 그대로 드러낸다. 확인 경로 = KIS MCP 스펙 조회 + 2026-09-14 이후 실측."
}

export const MARKET_STATE_AT_2030: MarketStateData = {
  "table_version": "2026-09-11",
  "as_of_kst": "2026-09-11T20:30:00+09:00",
  "on_date": "2026-09-11",
  "preview": false,
  "cursor_disabled_reason": null,
  "is_trading_day": true,
  "trading_day_source": "kis",
  "market_order": [
    "KRX",
    "NXT"
  ],
  "exchange_order": [
    "KRX",
    "NXT",
    "SOR"
  ],
  "markets": {
    "KRX": {
      "market": "KRX",
      "market_label_ko": "KRX(한국거래소)",
      "row_id": null,
      "phase": "CLOSED",
      "name_ko": "장 종료",
      "tone": "closed",
      "window": null,
      "match_kind": "none",
      "match_ko": "—",
      "is_open": false,
      "can_order": false,
      "market_order_ok": false,
      "order_divisions": [],
      "order_divisions_by_row": [],
      "concurrent_row_ids": [],
      "quote_channel": null,
      "quote_channel_evidence": "assumed",
      "decided_by": "time",
      "code_seen": null,
      "confidence": "confirmed",
      "confidence_notes": [],
      "seconds_to_next": null,
      "next_boundary": null,
      "next_row_id": null,
      "next_phase": null
    },
    "NXT": {
      "market": "NXT",
      "market_label_ko": "NXT(넥스트레이드)",
      "row_id": null,
      "phase": "CLOSED",
      "name_ko": "장 종료",
      "tone": "closed",
      "window": null,
      "match_kind": "none",
      "match_ko": "—",
      "is_open": false,
      "can_order": false,
      "market_order_ok": false,
      "order_divisions": [],
      "order_divisions_by_row": [],
      "concurrent_row_ids": [],
      "quote_channel": null,
      "quote_channel_evidence": "assumed",
      "decided_by": "time",
      "code_seen": null,
      "confidence": "confirmed",
      "confidence_notes": [],
      "seconds_to_next": null,
      "next_boundary": null,
      "next_row_id": null,
      "next_phase": null
    }
  },
  "table": [
    {
      "row_id": "K1",
      "market": "KRX",
      "start": "08:20:00",
      "end": "09:00:00",
      "phase": "PRE_AUCTION",
      "name_ko": "시가 단일가",
      "tone": "auction",
      "match_kind": "single_auction",
      "match_ko": "단일가(09:00 일괄)",
      "order_divisions": [
        "00",
        "01"
      ],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": true,
      "market_order_ok": true,
      "quote_channel": "H0STCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": false,
      "priority": 10,
      "effective_from": null,
      "effective_to": null,
      "confidence": "unconfirmed",
      "note": "시작 08:20 이 2026-09-14 개편분인지 미확인(종전 08:30). 09-14 이전 날짜에서는 08:20~08:30 을 과다 표시할 수 있다.",
      "rel": "past"
    },
    {
      "row_id": "K2",
      "market": "KRX",
      "start": "08:30:00",
      "end": "08:40:00",
      "phase": "PRE_CLOSE_FIXED",
      "name_ko": "장전 시간외 종가",
      "tone": "fixed",
      "match_kind": "fixed_price",
      "match_ko": "전일 종가 고정",
      "order_divisions": [
        "05"
      ],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": true,
      "market_order_ok": false,
      "quote_channel": "H0STCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": true,
      "priority": 20,
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "K1(시가 단일가) 안에 들어 있는 의도된 중첩. 08:30~08:40 에는 00·01·05 가 동시에 쓸 수 있다.",
      "rel": "past"
    },
    {
      "row_id": "K3",
      "market": "KRX",
      "start": "09:00:00",
      "end": "15:20:00",
      "phase": "REGULAR",
      "name_ko": "정규장",
      "tone": "active",
      "match_kind": "continuous",
      "match_ko": "실시간 접속매매",
      "order_divisions": [
        "00",
        "01",
        "02",
        "03",
        "04",
        "11",
        "12",
        "13",
        "14",
        "15",
        "16",
        "21",
        "22",
        "23",
        "24"
      ],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": true,
      "market_order_ok": true,
      "quote_channel": "H0STCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": false,
      "priority": 10,
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "",
      "rel": "past"
    },
    {
      "row_id": "K4",
      "market": "KRX",
      "start": "15:20:00",
      "end": "15:30:00",
      "phase": "CLOSE_AUCTION",
      "name_ko": "종가 단일가",
      "tone": "auction",
      "match_kind": "single_auction",
      "match_ko": "단일가(15:30 일괄)",
      "order_divisions": [
        "00",
        "01"
      ],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": true,
      "market_order_ok": true,
      "quote_channel": "H0STCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": false,
      "priority": 10,
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "",
      "rel": "past"
    },
    {
      "row_id": "K5",
      "market": "KRX",
      "start": "15:30:00",
      "end": "16:00:00",
      "phase": "AFTER_CLOSE_FIXED",
      "name_ko": "장후 시간외 종가",
      "tone": "fixed",
      "match_kind": "fixed_price",
      "match_ko": "당일 종가 고정",
      "order_divisions": [
        "06"
      ],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": true,
      "market_order_ok": false,
      "quote_channel": "H0STCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": false,
      "priority": 10,
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "",
      "rel": "past"
    },
    {
      "row_id": "K7",
      "market": "KRX",
      "start": "16:00:00",
      "end": "18:00:00",
      "phase": "AFTER_SINGLE",
      "name_ko": "시간외 단일가",
      "tone": "auction",
      "match_kind": "periodic_auction",
      "match_ko": "10분 주기",
      "order_divisions": [
        "07"
      ],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": true,
      "market_order_ok": false,
      "quote_channel": "H0STCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": true,
      "priority": 10,
      "effective_from": null,
      "effective_to": "2026-09-12",
      "confidence": "confirmed",
      "note": "2026-09-12 폐지. K6 과는 유효기간이 갈려 어떤 날짜에도 공존하지 않는다(B3).",
      "rel": "past"
    },
    {
      "row_id": "N1",
      "market": "NXT",
      "start": "08:00:00",
      "end": "08:50:00",
      "phase": "PRE_MARKET",
      "name_ko": "프리마켓",
      "tone": "active",
      "match_kind": "continuous",
      "match_ko": "실시간",
      "order_divisions": [
        "00",
        "03",
        "04",
        "11",
        "12",
        "13",
        "14",
        "15",
        "16",
        "21",
        "22",
        "23",
        "24"
      ],
      "order_divisions_pending": [
        "27",
        "28",
        "29"
      ],
      "order_divisions_expired": [],
      "can_order": true,
      "market_order_ok": false,
      "quote_channel": "H0NXCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": false,
      "priority": 10,
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "27~29(GTP)는 2026-09-14 부터 유효 — 그 이전 날짜에는 order_divisions_pending 으로 빠진다.",
      "rel": "past"
    },
    {
      "row_id": "N2",
      "market": "NXT",
      "start": "08:50:00",
      "end": "09:00:00",
      "phase": "BREAK",
      "name_ko": "휴장",
      "tone": "break",
      "match_kind": "none",
      "match_ko": "—",
      "order_divisions": [],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": false,
      "market_order_ok": false,
      "quote_channel": "H0NXCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": false,
      "priority": 10,
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "휴장 — 주문 접수 불가.",
      "rel": "past"
    },
    {
      "row_id": "N3",
      "market": "NXT",
      "start": "09:00:30",
      "end": "15:20:00",
      "phase": "REGULAR",
      "name_ko": "정규장",
      "tone": "active",
      "match_kind": "continuous",
      "match_ko": "실시간",
      "order_divisions": [
        "00",
        "03",
        "04",
        "11",
        "12",
        "13",
        "14",
        "15",
        "16",
        "21",
        "22",
        "23",
        "24"
      ],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": true,
      "market_order_ok": false,
      "quote_channel": "H0NXCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": false,
      "priority": 10,
      "effective_from": null,
      "effective_to": null,
      "confidence": "unconfirmed",
      "note": "시작 09:00:30 미확인. 09:00:00~09:00:29 은 N2(휴장)로 남는다 — 표대로 옮겼을 뿐 실측 근거는 없다.",
      "rel": "past"
    },
    {
      "row_id": "N4",
      "market": "NXT",
      "start": "15:20:00",
      "end": "15:30:00",
      "phase": "BREAK",
      "name_ko": "휴장",
      "tone": "break",
      "match_kind": "none",
      "match_ko": "—",
      "order_divisions": [],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": false,
      "market_order_ok": false,
      "quote_channel": "H0NXCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": false,
      "priority": 10,
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "휴장 — 주문 접수 불가.",
      "rel": "past"
    },
    {
      "row_id": "N5",
      "market": "NXT",
      "start": "15:30:00",
      "end": "15:40:00",
      "phase": "AFTER_SINGLE",
      "name_ko": "애프터 단일가",
      "tone": "auction",
      "match_kind": "single_auction",
      "match_ko": "단일가",
      "order_divisions": [],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": false,
      "market_order_ok": false,
      "quote_channel": "H0NXCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": false,
      "priority": 10,
      "effective_from": null,
      "effective_to": null,
      "confidence": "unconfirmed",
      "note": "단일가 구간인 것은 확정이나 쓸 수 있는 주문유형이 미확인이다. NXT 코드 목록에 단일가 전용 코드가 없다. is_open=True 이지만 can_order=False 다 — 이 구간의 주문 가능 여부를 이 표로 판단하지 말 것.",
      "rel": "past"
    },
    {
      "row_id": "N6",
      "market": "NXT",
      "start": "15:40:00",
      "end": "20:00:00",
      "phase": "AFTER_MARKET",
      "name_ko": "애프터마켓",
      "tone": "active",
      "match_kind": "continuous",
      "match_ko": "실시간",
      "order_divisions": [
        "00",
        "03",
        "04",
        "11",
        "12",
        "13",
        "14",
        "15",
        "16",
        "21",
        "22",
        "23",
        "24"
      ],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": true,
      "market_order_ok": false,
      "quote_channel": "H0NXCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": false,
      "priority": 10,
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "",
      "rel": "past"
    }
  ],
  "order_divisions": [
    {
      "code": "00",
      "name_ko": "지정가",
      "group_ko": null,
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "yes"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "01",
      "name_ko": "시장가",
      "group_ko": null,
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "yes"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "NXT 에는 시장가가 없다(발견 1)."
    },
    {
      "code": "02",
      "name_ko": "조건부지정가",
      "group_ko": null,
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "no"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "03",
      "name_ko": "최유리지정가",
      "group_ko": null,
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "yes"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "04",
      "name_ko": "최우선지정가",
      "group_ko": null,
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "yes"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "05",
      "name_ko": "장전시간외",
      "group_ko": null,
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "no"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "SOR 에 없다(발견 2)."
    },
    {
      "code": "06",
      "name_ko": "장후시간외",
      "group_ko": null,
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "no"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "SOR 에 없다(발견 2)."
    },
    {
      "code": "07",
      "name_ko": "시간외단일가",
      "group_ko": null,
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "no"
      },
      "effective_from": null,
      "effective_to": "2026-09-12",
      "confidence": "confirmed",
      "note": "2026-09-12 폐지. SOR 에 없다(발견 2)."
    },
    {
      "code": "11",
      "name_ko": "IOC지정가",
      "group_ko": "IOC/FOK",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "yes"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "12",
      "name_ko": "FOK지정가",
      "group_ko": "IOC/FOK",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "yes"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "13",
      "name_ko": "IOC시장가",
      "group_ko": "IOC/FOK",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "yes"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "14",
      "name_ko": "FOK시장가",
      "group_ko": "IOC/FOK",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "yes"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "15",
      "name_ko": "IOC최유리",
      "group_ko": "IOC/FOK",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "yes"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "16",
      "name_ko": "FOK최유리",
      "group_ko": "IOC/FOK",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "yes"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "21",
      "name_ko": "중간가",
      "group_ko": "중간가/스톱",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "no"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "22",
      "name_ko": "스톱지정가",
      "group_ko": "중간가/스톱",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "no"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "23",
      "name_ko": "중간가IOC",
      "group_ko": "중간가/스톱",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "no"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "24",
      "name_ko": "중간가FOK",
      "group_ko": "중간가/스톱",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "no"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "27",
      "name_ko": "NXT GTP지정가",
      "group_ko": "NXT GTP(27~29)",
      "exchange_support": {
        "KRX": "no",
        "NXT": "yes",
        "SOR": "unknown"
      },
      "effective_from": "2026-09-14",
      "effective_to": null,
      "confidence": "confirmed",
      "note": "명칭 확정 — 공지 2026-09-09(시행 09-14) 원문. 미체결잔량은 프리마켓 종료(08:50) 일괄 취소."
    },
    {
      "code": "28",
      "name_ko": "NXT GTP최유리",
      "group_ko": "NXT GTP(27~29)",
      "exchange_support": {
        "KRX": "no",
        "NXT": "yes",
        "SOR": "unknown"
      },
      "effective_from": "2026-09-14",
      "effective_to": null,
      "confidence": "confirmed",
      "note": "명칭 확정 — 공지 2026-09-09(시행 09-14) 원문. 미체결잔량은 프리마켓 종료(08:50) 일괄 취소."
    },
    {
      "code": "29",
      "name_ko": "NXT GTP최우선",
      "group_ko": "NXT GTP(27~29)",
      "exchange_support": {
        "KRX": "no",
        "NXT": "yes",
        "SOR": "unknown"
      },
      "effective_from": "2026-09-14",
      "effective_to": null,
      "confidence": "confirmed",
      "note": "명칭 확정 — 공지 2026-09-09(시행 09-14) 원문. 미체결잔량은 프리마켓 종료(08:50) 일괄 취소."
    },
    {
      "code": "41",
      "name_ko": "KRX애프터마켓지정가",
      "group_ko": "KRX 애프터마켓(41~47)",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "unknown"
      },
      "effective_from": "2026-09-14",
      "effective_to": null,
      "confidence": "confirmed",
      "note": "명칭 확정 — 공지 2026-09-09(시행 09-14) 원문. 애프터마켓은 시장가 불가·ETP 불가."
    },
    {
      "code": "42",
      "name_ko": "KRX애프터마켓지정가IOC",
      "group_ko": "KRX 애프터마켓(41~47)",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "unknown"
      },
      "effective_from": "2026-09-14",
      "effective_to": null,
      "confidence": "confirmed",
      "note": "명칭 확정 — 공지 2026-09-09(시행 09-14) 원문. 애프터마켓은 시장가 불가·ETP 불가."
    },
    {
      "code": "43",
      "name_ko": "KRX애프터마켓지정가FOK",
      "group_ko": "KRX 애프터마켓(41~47)",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "unknown"
      },
      "effective_from": "2026-09-14",
      "effective_to": null,
      "confidence": "confirmed",
      "note": "명칭 확정 — 공지 2026-09-09(시행 09-14) 원문. 애프터마켓은 시장가 불가·ETP 불가."
    },
    {
      "code": "44",
      "name_ko": "KRX애프터마켓최유리지정가",
      "group_ko": "KRX 애프터마켓(41~47)",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "unknown"
      },
      "effective_from": "2026-09-14",
      "effective_to": null,
      "confidence": "confirmed",
      "note": "명칭 확정 — 공지 2026-09-09(시행 09-14) 원문. 애프터마켓은 시장가 불가·ETP 불가."
    },
    {
      "code": "45",
      "name_ko": "KRX애프터마켓최유리지정가IOC",
      "group_ko": "KRX 애프터마켓(41~47)",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "unknown"
      },
      "effective_from": "2026-09-14",
      "effective_to": null,
      "confidence": "confirmed",
      "note": "명칭 확정 — 공지 2026-09-09(시행 09-14) 원문. 애프터마켓은 시장가 불가·ETP 불가."
    },
    {
      "code": "46",
      "name_ko": "KRX애프터마켓최유리지정가FOK",
      "group_ko": "KRX 애프터마켓(41~47)",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "unknown"
      },
      "effective_from": "2026-09-14",
      "effective_to": null,
      "confidence": "confirmed",
      "note": "명칭 확정 — 공지 2026-09-09(시행 09-14) 원문. 애프터마켓은 시장가 불가·ETP 불가."
    },
    {
      "code": "47",
      "name_ko": "KRX애프터마켓최우선지정가",
      "group_ko": "KRX 애프터마켓(41~47)",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "unknown"
      },
      "effective_from": "2026-09-14",
      "effective_to": null,
      "confidence": "confirmed",
      "note": "명칭 확정 — 공지 2026-09-09(시행 09-14) 원문. 애프터마켓은 시장가 불가·ETP 불가."
    }
  ],
  "phases": [
    {
      "id": "PRE_AUCTION",
      "label_ko": "시가 단일가",
      "tone": "auction"
    },
    {
      "id": "PRE_MARKET",
      "label_ko": "프리마켓",
      "tone": "active"
    },
    {
      "id": "REGULAR",
      "label_ko": "정규장",
      "tone": "active"
    },
    {
      "id": "CLOSE_AUCTION",
      "label_ko": "종가 단일가",
      "tone": "auction"
    },
    {
      "id": "PRE_CLOSE_FIXED",
      "label_ko": "장전 시간외 종가",
      "tone": "fixed"
    },
    {
      "id": "AFTER_CLOSE_FIXED",
      "label_ko": "장후 시간외 종가",
      "tone": "fixed"
    },
    {
      "id": "AFTER_SINGLE",
      "label_ko": "단일가(시간외·애프터)",
      "tone": "auction"
    },
    {
      "id": "AFTER_MARKET",
      "label_ko": "애프터마켓",
      "tone": "active"
    },
    {
      "id": "BREAK",
      "label_ko": "휴장",
      "tone": "break"
    },
    {
      "id": "CLOSED",
      "label_ko": "장 종료",
      "tone": "closed"
    }
  ],
  "vocab": {
    "tones": [
      "active",
      "auction",
      "fixed",
      "break",
      "closed",
      "unknown"
    ],
    "rels": [
      "past",
      "current",
      "concurrent",
      "upcoming",
      "unknown"
    ],
    "support_levels": [
      "yes",
      "unknown",
      "no"
    ],
    "confidences": [
      "confirmed",
      "unconfirmed",
      "ambiguous"
    ],
    "division_confidences": [
      "confirmed",
      "name_unconfirmed",
      "unconfirmed"
    ]
  },
  "findings": [
    "NXT 에 시장가(01)가 없다. 우리 주문의 1차 유형이 시장가다. 프리장 지정가 사전 변환은 우회가 아니라 구조적 필연이었다. 대안은 13 IOC시장가 / 14 FOK시장가다.",
    "SOR 에 시간외 코드(05·06·07)가 없다. 다만 cycle287(2026-09-12)부터 **시각이 거래소를 정하므로**(정규장·애프터 = KRX, 프리장만 전략 설정값) 우리 주문은 09:00 이후 SOR 로 나가지 않는다. 이 열은 KIS 지원 사실만 표시한다.",
    "SOR 은 주문 경로에서 **폐기**됐다(사용자 결정 2026-09-12). 전략 설정의 SOR 선택지는 폐기 표시로 남아 있고 프리장 밖에서는 값이 무엇이든 KRX 로 나간다. 이 표의 SOR 열은 삭제하지 않는다 — 41~47 의 SOR 지원 여부가 아직 **확인 필요**이고, 그 미확인을 화면에서 지우면 44 의 단가 규약이 미검증이라는 사실도 함께 사라진다."
  ],
  "board_note": "이 화면은 거래소의 실제 장 운영 상태다. 우리 시스템의 매매 보드(PRE_NXT/MAIN/POST_NXT)와는 경계가 다르다 — 우리 MAIN 보드는 15:39:59 까지지만 KRX 정규장은 15:20 에 끝난다. 보드는 우리 매매 규약이고 이 표는 거래소 사실이다. 둘을 같은 것으로 읽지 말 것.",
  "unconfirmed_note": "⚠️ 표시 항목은 아직 KIS 정본으로 확인하지 못했다. 이 사이클은 추측으로 채우지 않고 그대로 드러낸다. 확인 경로 = KIS MCP 스펙 조회 + 2026-09-14 이후 실측."
}

export const MARKET_STATE_PREVIEW: MarketStateData = {
  "table_version": "2026-09-11",
  "as_of_kst": "2026-09-11T13:05:22+09:00",
  "on_date": "2026-09-14",
  "preview": true,
  "cursor_disabled_reason": "preview_other_date",
  "is_trading_day": true,
  "trading_day_source": "kis",
  "market_order": [
    "KRX",
    "NXT"
  ],
  "exchange_order": [
    "KRX",
    "NXT",
    "SOR"
  ],
  "markets": null,
  "table": [
    {
      "row_id": "K1",
      "market": "KRX",
      "start": "08:20:00",
      "end": "09:00:00",
      "phase": "PRE_AUCTION",
      "name_ko": "시가 단일가",
      "tone": "auction",
      "match_kind": "single_auction",
      "match_ko": "단일가(09:00 일괄)",
      "order_divisions": [
        "00",
        "01"
      ],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": true,
      "market_order_ok": true,
      "quote_channel": "H0STCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": false,
      "priority": 10,
      "effective_from": null,
      "effective_to": null,
      "confidence": "unconfirmed",
      "note": "시작 08:20 이 2026-09-14 개편분인지 미확인(종전 08:30). 09-14 이전 날짜에서는 08:20~08:30 을 과다 표시할 수 있다.",
      "rel": "unknown"
    },
    {
      "row_id": "K2",
      "market": "KRX",
      "start": "08:30:00",
      "end": "08:40:00",
      "phase": "PRE_CLOSE_FIXED",
      "name_ko": "장전 시간외 종가",
      "tone": "fixed",
      "match_kind": "fixed_price",
      "match_ko": "전일 종가 고정",
      "order_divisions": [
        "05"
      ],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": true,
      "market_order_ok": false,
      "quote_channel": "H0STCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": true,
      "priority": 20,
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "K1(시가 단일가) 안에 들어 있는 의도된 중첩. 08:30~08:40 에는 00·01·05 가 동시에 쓸 수 있다.",
      "rel": "unknown"
    },
    {
      "row_id": "K3",
      "market": "KRX",
      "start": "09:00:00",
      "end": "15:20:00",
      "phase": "REGULAR",
      "name_ko": "정규장",
      "tone": "active",
      "match_kind": "continuous",
      "match_ko": "실시간 접속매매",
      "order_divisions": [
        "00",
        "01",
        "02",
        "03",
        "04",
        "11",
        "12",
        "13",
        "14",
        "15",
        "16",
        "21",
        "22",
        "23",
        "24"
      ],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": true,
      "market_order_ok": true,
      "quote_channel": "H0STCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": false,
      "priority": 10,
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "",
      "rel": "unknown"
    },
    {
      "row_id": "K4",
      "market": "KRX",
      "start": "15:20:00",
      "end": "15:30:00",
      "phase": "CLOSE_AUCTION",
      "name_ko": "종가 단일가",
      "tone": "auction",
      "match_kind": "single_auction",
      "match_ko": "단일가(15:30 일괄)",
      "order_divisions": [
        "00",
        "01"
      ],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": true,
      "market_order_ok": true,
      "quote_channel": "H0STCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": false,
      "priority": 10,
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "",
      "rel": "unknown"
    },
    {
      "row_id": "K5",
      "market": "KRX",
      "start": "15:30:00",
      "end": "16:00:00",
      "phase": "AFTER_CLOSE_FIXED",
      "name_ko": "장후 시간외 종가",
      "tone": "fixed",
      "match_kind": "fixed_price",
      "match_ko": "당일 종가 고정",
      "order_divisions": [
        "06"
      ],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": true,
      "market_order_ok": false,
      "quote_channel": "H0STCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": false,
      "priority": 10,
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "",
      "rel": "unknown"
    },
    {
      "row_id": "K6",
      "market": "KRX",
      "start": "16:00:00",
      "end": "20:00:00",
      "phase": "AFTER_MARKET",
      "name_ko": "애프터마켓",
      "tone": "active",
      "match_kind": "continuous",
      "match_ko": "실시간",
      "order_divisions": [
        "41",
        "42",
        "43",
        "44",
        "45",
        "46",
        "47"
      ],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": true,
      "market_order_ok": false,
      "quote_channel": "H0STCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": false,
      "priority": 10,
      "effective_from": "2026-09-14",
      "effective_to": null,
      "confidence": "confirmed",
      "note": "2026-09-14 신설(공지). 시장가 없음 — 41~47 만.",
      "rel": "unknown"
    },
    {
      "row_id": "N1",
      "market": "NXT",
      "start": "08:00:00",
      "end": "08:50:00",
      "phase": "PRE_MARKET",
      "name_ko": "프리마켓",
      "tone": "active",
      "match_kind": "continuous",
      "match_ko": "실시간",
      "order_divisions": [
        "00",
        "03",
        "04",
        "11",
        "12",
        "13",
        "14",
        "15",
        "16",
        "21",
        "22",
        "23",
        "24",
        "27",
        "28",
        "29"
      ],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": true,
      "market_order_ok": false,
      "quote_channel": "H0NXCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": false,
      "priority": 10,
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "27~29(GTP)는 2026-09-14 부터 유효 — 그 이전 날짜에는 order_divisions_pending 으로 빠진다.",
      "rel": "unknown"
    },
    {
      "row_id": "N2",
      "market": "NXT",
      "start": "08:50:00",
      "end": "09:00:00",
      "phase": "BREAK",
      "name_ko": "휴장",
      "tone": "break",
      "match_kind": "none",
      "match_ko": "—",
      "order_divisions": [],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": false,
      "market_order_ok": false,
      "quote_channel": "H0NXCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": false,
      "priority": 10,
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "휴장 — 주문 접수 불가.",
      "rel": "unknown"
    },
    {
      "row_id": "N3",
      "market": "NXT",
      "start": "09:00:30",
      "end": "15:20:00",
      "phase": "REGULAR",
      "name_ko": "정규장",
      "tone": "active",
      "match_kind": "continuous",
      "match_ko": "실시간",
      "order_divisions": [
        "00",
        "03",
        "04",
        "11",
        "12",
        "13",
        "14",
        "15",
        "16",
        "21",
        "22",
        "23",
        "24"
      ],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": true,
      "market_order_ok": false,
      "quote_channel": "H0NXCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": false,
      "priority": 10,
      "effective_from": null,
      "effective_to": null,
      "confidence": "unconfirmed",
      "note": "시작 09:00:30 미확인. 09:00:00~09:00:29 은 N2(휴장)로 남는다 — 표대로 옮겼을 뿐 실측 근거는 없다.",
      "rel": "unknown"
    },
    {
      "row_id": "N4",
      "market": "NXT",
      "start": "15:20:00",
      "end": "15:30:00",
      "phase": "BREAK",
      "name_ko": "휴장",
      "tone": "break",
      "match_kind": "none",
      "match_ko": "—",
      "order_divisions": [],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": false,
      "market_order_ok": false,
      "quote_channel": "H0NXCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": false,
      "priority": 10,
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "휴장 — 주문 접수 불가.",
      "rel": "unknown"
    },
    {
      "row_id": "N5",
      "market": "NXT",
      "start": "15:30:00",
      "end": "15:40:00",
      "phase": "AFTER_SINGLE",
      "name_ko": "애프터 단일가",
      "tone": "auction",
      "match_kind": "single_auction",
      "match_ko": "단일가",
      "order_divisions": [],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": false,
      "market_order_ok": false,
      "quote_channel": "H0NXCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": false,
      "priority": 10,
      "effective_from": null,
      "effective_to": null,
      "confidence": "unconfirmed",
      "note": "단일가 구간인 것은 확정이나 쓸 수 있는 주문유형이 미확인이다. NXT 코드 목록에 단일가 전용 코드가 없다. is_open=True 이지만 can_order=False 다 — 이 구간의 주문 가능 여부를 이 표로 판단하지 말 것.",
      "rel": "unknown"
    },
    {
      "row_id": "N6",
      "market": "NXT",
      "start": "15:40:00",
      "end": "20:00:00",
      "phase": "AFTER_MARKET",
      "name_ko": "애프터마켓",
      "tone": "active",
      "match_kind": "continuous",
      "match_ko": "실시간",
      "order_divisions": [
        "00",
        "03",
        "04",
        "11",
        "12",
        "13",
        "14",
        "15",
        "16",
        "21",
        "22",
        "23",
        "24"
      ],
      "order_divisions_pending": [],
      "order_divisions_expired": [],
      "can_order": true,
      "market_order_ok": false,
      "quote_channel": "H0NXCNT0",
      "quote_channel_evidence": "assumed",
      "overlap_ok": false,
      "priority": 10,
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "",
      "rel": "unknown"
    }
  ],
  "order_divisions": [
    {
      "code": "00",
      "name_ko": "지정가",
      "group_ko": null,
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "yes"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "01",
      "name_ko": "시장가",
      "group_ko": null,
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "yes"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "NXT 에는 시장가가 없다(발견 1)."
    },
    {
      "code": "02",
      "name_ko": "조건부지정가",
      "group_ko": null,
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "no"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "03",
      "name_ko": "최유리지정가",
      "group_ko": null,
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "yes"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "04",
      "name_ko": "최우선지정가",
      "group_ko": null,
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "yes"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "05",
      "name_ko": "장전시간외",
      "group_ko": null,
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "no"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "SOR 에 없다(발견 2)."
    },
    {
      "code": "06",
      "name_ko": "장후시간외",
      "group_ko": null,
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "no"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": "SOR 에 없다(발견 2)."
    },
    {
      "code": "07",
      "name_ko": "시간외단일가",
      "group_ko": null,
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "no"
      },
      "effective_from": null,
      "effective_to": "2026-09-12",
      "confidence": "confirmed",
      "note": "2026-09-12 폐지. SOR 에 없다(발견 2)."
    },
    {
      "code": "11",
      "name_ko": "IOC지정가",
      "group_ko": "IOC/FOK",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "yes"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "12",
      "name_ko": "FOK지정가",
      "group_ko": "IOC/FOK",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "yes"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "13",
      "name_ko": "IOC시장가",
      "group_ko": "IOC/FOK",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "yes"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "14",
      "name_ko": "FOK시장가",
      "group_ko": "IOC/FOK",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "yes"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "15",
      "name_ko": "IOC최유리",
      "group_ko": "IOC/FOK",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "yes"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "16",
      "name_ko": "FOK최유리",
      "group_ko": "IOC/FOK",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "yes"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "21",
      "name_ko": "중간가",
      "group_ko": "중간가/스톱",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "no"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "22",
      "name_ko": "스톱지정가",
      "group_ko": "중간가/스톱",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "no"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "23",
      "name_ko": "중간가IOC",
      "group_ko": "중간가/스톱",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "no"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "24",
      "name_ko": "중간가FOK",
      "group_ko": "중간가/스톱",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "yes",
        "SOR": "no"
      },
      "effective_from": null,
      "effective_to": null,
      "confidence": "confirmed",
      "note": ""
    },
    {
      "code": "27",
      "name_ko": "NXT GTP지정가",
      "group_ko": "NXT GTP(27~29)",
      "exchange_support": {
        "KRX": "no",
        "NXT": "yes",
        "SOR": "unknown"
      },
      "effective_from": "2026-09-14",
      "effective_to": null,
      "confidence": "confirmed",
      "note": "명칭 확정 — 공지 2026-09-09(시행 09-14) 원문. 미체결잔량은 프리마켓 종료(08:50) 일괄 취소."
    },
    {
      "code": "28",
      "name_ko": "NXT GTP최유리",
      "group_ko": "NXT GTP(27~29)",
      "exchange_support": {
        "KRX": "no",
        "NXT": "yes",
        "SOR": "unknown"
      },
      "effective_from": "2026-09-14",
      "effective_to": null,
      "confidence": "confirmed",
      "note": "명칭 확정 — 공지 2026-09-09(시행 09-14) 원문. 미체결잔량은 프리마켓 종료(08:50) 일괄 취소."
    },
    {
      "code": "29",
      "name_ko": "NXT GTP최우선",
      "group_ko": "NXT GTP(27~29)",
      "exchange_support": {
        "KRX": "no",
        "NXT": "yes",
        "SOR": "unknown"
      },
      "effective_from": "2026-09-14",
      "effective_to": null,
      "confidence": "confirmed",
      "note": "명칭 확정 — 공지 2026-09-09(시행 09-14) 원문. 미체결잔량은 프리마켓 종료(08:50) 일괄 취소."
    },
    {
      "code": "41",
      "name_ko": "KRX애프터마켓지정가",
      "group_ko": "KRX 애프터마켓(41~47)",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "unknown"
      },
      "effective_from": "2026-09-14",
      "effective_to": null,
      "confidence": "confirmed",
      "note": "명칭 확정 — 공지 2026-09-09(시행 09-14) 원문. 애프터마켓은 시장가 불가·ETP 불가."
    },
    {
      "code": "42",
      "name_ko": "KRX애프터마켓지정가IOC",
      "group_ko": "KRX 애프터마켓(41~47)",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "unknown"
      },
      "effective_from": "2026-09-14",
      "effective_to": null,
      "confidence": "confirmed",
      "note": "명칭 확정 — 공지 2026-09-09(시행 09-14) 원문. 애프터마켓은 시장가 불가·ETP 불가."
    },
    {
      "code": "43",
      "name_ko": "KRX애프터마켓지정가FOK",
      "group_ko": "KRX 애프터마켓(41~47)",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "unknown"
      },
      "effective_from": "2026-09-14",
      "effective_to": null,
      "confidence": "confirmed",
      "note": "명칭 확정 — 공지 2026-09-09(시행 09-14) 원문. 애프터마켓은 시장가 불가·ETP 불가."
    },
    {
      "code": "44",
      "name_ko": "KRX애프터마켓최유리지정가",
      "group_ko": "KRX 애프터마켓(41~47)",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "unknown"
      },
      "effective_from": "2026-09-14",
      "effective_to": null,
      "confidence": "confirmed",
      "note": "명칭 확정 — 공지 2026-09-09(시행 09-14) 원문. 애프터마켓은 시장가 불가·ETP 불가."
    },
    {
      "code": "45",
      "name_ko": "KRX애프터마켓최유리지정가IOC",
      "group_ko": "KRX 애프터마켓(41~47)",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "unknown"
      },
      "effective_from": "2026-09-14",
      "effective_to": null,
      "confidence": "confirmed",
      "note": "명칭 확정 — 공지 2026-09-09(시행 09-14) 원문. 애프터마켓은 시장가 불가·ETP 불가."
    },
    {
      "code": "46",
      "name_ko": "KRX애프터마켓최유리지정가FOK",
      "group_ko": "KRX 애프터마켓(41~47)",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "unknown"
      },
      "effective_from": "2026-09-14",
      "effective_to": null,
      "confidence": "confirmed",
      "note": "명칭 확정 — 공지 2026-09-09(시행 09-14) 원문. 애프터마켓은 시장가 불가·ETP 불가."
    },
    {
      "code": "47",
      "name_ko": "KRX애프터마켓최우선지정가",
      "group_ko": "KRX 애프터마켓(41~47)",
      "exchange_support": {
        "KRX": "yes",
        "NXT": "no",
        "SOR": "unknown"
      },
      "effective_from": "2026-09-14",
      "effective_to": null,
      "confidence": "confirmed",
      "note": "명칭 확정 — 공지 2026-09-09(시행 09-14) 원문. 애프터마켓은 시장가 불가·ETP 불가."
    }
  ],
  "phases": [
    {
      "id": "PRE_AUCTION",
      "label_ko": "시가 단일가",
      "tone": "auction"
    },
    {
      "id": "PRE_MARKET",
      "label_ko": "프리마켓",
      "tone": "active"
    },
    {
      "id": "REGULAR",
      "label_ko": "정규장",
      "tone": "active"
    },
    {
      "id": "CLOSE_AUCTION",
      "label_ko": "종가 단일가",
      "tone": "auction"
    },
    {
      "id": "PRE_CLOSE_FIXED",
      "label_ko": "장전 시간외 종가",
      "tone": "fixed"
    },
    {
      "id": "AFTER_CLOSE_FIXED",
      "label_ko": "장후 시간외 종가",
      "tone": "fixed"
    },
    {
      "id": "AFTER_SINGLE",
      "label_ko": "단일가(시간외·애프터)",
      "tone": "auction"
    },
    {
      "id": "AFTER_MARKET",
      "label_ko": "애프터마켓",
      "tone": "active"
    },
    {
      "id": "BREAK",
      "label_ko": "휴장",
      "tone": "break"
    },
    {
      "id": "CLOSED",
      "label_ko": "장 종료",
      "tone": "closed"
    }
  ],
  "vocab": {
    "tones": [
      "active",
      "auction",
      "fixed",
      "break",
      "closed",
      "unknown"
    ],
    "rels": [
      "past",
      "current",
      "concurrent",
      "upcoming",
      "unknown"
    ],
    "support_levels": [
      "yes",
      "unknown",
      "no"
    ],
    "confidences": [
      "confirmed",
      "unconfirmed",
      "ambiguous"
    ],
    "division_confidences": [
      "confirmed",
      "name_unconfirmed",
      "unconfirmed"
    ]
  },
  "findings": [
    "NXT 에 시장가(01)가 없다. 우리 주문의 1차 유형이 시장가다. 프리장 지정가 사전 변환은 우회가 아니라 구조적 필연이었다. 대안은 13 IOC시장가 / 14 FOK시장가다.",
    "SOR 에 시간외 코드(05·06·07)가 없다. 다만 cycle287(2026-09-12)부터 **시각이 거래소를 정하므로**(정규장·애프터 = KRX, 프리장만 전략 설정값) 우리 주문은 09:00 이후 SOR 로 나가지 않는다. 이 열은 KIS 지원 사실만 표시한다.",
    "SOR 은 주문 경로에서 **폐기**됐다(사용자 결정 2026-09-12). 전략 설정의 SOR 선택지는 폐기 표시로 남아 있고 프리장 밖에서는 값이 무엇이든 KRX 로 나간다. 이 표의 SOR 열은 삭제하지 않는다 — 41~47 의 SOR 지원 여부가 아직 **확인 필요**이고, 그 미확인을 화면에서 지우면 44 의 단가 규약이 미검증이라는 사실도 함께 사라진다."
  ],
  "board_note": "이 화면은 거래소의 실제 장 운영 상태다. 우리 시스템의 매매 보드(PRE_NXT/MAIN/POST_NXT)와는 경계가 다르다 — 우리 MAIN 보드는 15:39:59 까지지만 KRX 정규장은 15:20 에 끝난다. 보드는 우리 매매 규약이고 이 표는 거래소 사실이다. 둘을 같은 것으로 읽지 말 것.",
  "unconfirmed_note": "⚠️ 표시 항목은 아직 KIS 정본으로 확인하지 못했다. 이 사이클은 추측으로 채우지 않고 그대로 드러낸다. 확인 경로 = KIS MCP 스펙 조회 + 2026-09-14 이후 실측."
}

export const MARKET_STATE_FORBIDDEN: MarketStateForbidden = {
  "rowIds": [
    "K1",
    "K2",
    "K3",
    "K4",
    "K5",
    "K6",
    "K7",
    "N1",
    "N2",
    "N3",
    "N4",
    "N5",
    "N6"
  ],
  "divisionCodes": [
    "00",
    "01",
    "02",
    "03",
    "04",
    "05",
    "06",
    "07",
    "11",
    "12",
    "13",
    "14",
    "15",
    "16",
    "21",
    "22",
    "23",
    "24",
    "27",
    "28",
    "29",
    "41",
    "42",
    "43",
    "44",
    "45",
    "46",
    "47"
  ],
  "rowNames": [
    "시가 단일가",
    "시간외 단일가",
    "애프터 단일가",
    "애프터마켓",
    "장전 시간외 종가",
    "장후 시간외 종가",
    "정규장",
    "종가 단일가",
    "프리마켓",
    "휴장"
  ],
  "divisionNames": [
    "FOK시장가",
    "FOK지정가",
    "FOK최유리",
    "IOC/FOK",
    "IOC시장가",
    "IOC지정가",
    "IOC최유리",
    "KRX 애프터마켓(41~47)",
    "KRX애프터마켓지정가",
    "KRX애프터마켓지정가FOK",
    "KRX애프터마켓지정가IOC",
    "KRX애프터마켓최우선지정가",
    "KRX애프터마켓최유리지정가",
    "KRX애프터마켓최유리지정가FOK",
    "KRX애프터마켓최유리지정가IOC",
    "NXT GTP(27~29)",
    "NXT GTP지정가",
    "NXT GTP최우선",
    "NXT GTP최유리",
    "스톱지정가",
    "시간외단일가",
    "시장가",
    "장전시간외",
    "장후시간외",
    "조건부지정가",
    "중간가",
    "중간가/스톱",
    "중간가FOK",
    "중간가IOC",
    "지정가",
    "최우선지정가",
    "최유리지정가"
  ],
  "phases": [
    "PRE_AUCTION",
    "PRE_MARKET",
    "REGULAR",
    "CLOSE_AUCTION",
    "PRE_CLOSE_FIXED",
    "AFTER_CLOSE_FIXED",
    "AFTER_SINGLE",
    "AFTER_MARKET",
    "BREAK",
    "CLOSED"
  ],
  "markets": [
    "KRX",
    "NXT",
    "SOR"
  ]
}

/** MSW 기본 핸들러가 쓰는 변종 — 평범한 정규장(13:05). */
export const MARKET_STATE_FIXTURE: MarketStateData = MARKET_STATE_AT_1305
