/**
 * `/api/macro/*` 5개 엔드포인트 호출 (cycle303 — macro_lite 이식 1단계).
 *
 * 🔴 패키지 원본(`packaging/macro_lite/frontend/macro/api/client.js`)의 최소 fetch 래퍼는
 * 가져오지 않는다 — 우리 `api/client.ts`(axios, `baseURL:'/api'`, `withCredentials:true`)를
 * 그대로 쓴다. `X-API-Key` 헤더는 붙이지 않는다 — nginx `proxy_set_header X-API-Key
 * $api_key_for_user` 가 서버 측에서 주입하고 클라이언트가 보낸 헤더를 **치환**하므로,
 * 프론트에서 붙여도 무의미하고 "여기서 인증한다"는 오해만 남긴다.
 *
 * ⚠️ 이 5개 응답은 `ApiResponse<T>` 래퍼(`{success, data, message}`)를 쓰지 않는다 —
 * macro 서비스는 독립 FastAPI 프로세스라 원본 계약(`{ <section>, updated_at, errors }`)을
 * 그대로 반환한다. `response.data` 를 그대로 돌려준다(`.data.data` 로 벗기지 않는다).
 *
 * ⚠️ 타임아웃 오버라이드 — 우리 `apiClient` 기본 `timeout` 은 10초다. macro 는 콜드
 * 캐시일 때 yfinance 약 27건을 순회해 10초를 넘길 수 있다(README §4 "yfinance 호출량과
 * TTL" — 콜드 캐시 1회 전체 갱신 ≈ 27건). 그래서 요청마다 `{ timeout: 60000 }` 을 준다
 * (nginx `proxy_read_timeout 60s` 와 맞춘 값).
 */
import apiClient from "./client"
import type {
  CommoditiesResponse,
  CreditSpreadResponse,
  CurrenciesResponse,
  MacroCycleResponse,
  YieldCurveResponse,
} from "../types/macro"

const MACRO_TIMEOUT_MS = 60000

export async function fetchYieldCurve(): Promise<YieldCurveResponse> {
  const res = await apiClient.get<YieldCurveResponse>("/macro/yield-curve", {
    timeout: MACRO_TIMEOUT_MS,
  })
  return res.data
}

export async function fetchCreditSpread(): Promise<CreditSpreadResponse> {
  const res = await apiClient.get<CreditSpreadResponse>("/macro/credit-spread", {
    timeout: MACRO_TIMEOUT_MS,
  })
  return res.data
}

export async function fetchCurrencies(): Promise<CurrenciesResponse> {
  const res = await apiClient.get<CurrenciesResponse>("/macro/currencies", {
    timeout: MACRO_TIMEOUT_MS,
  })
  return res.data
}

export async function fetchCommodities(): Promise<CommoditiesResponse> {
  const res = await apiClient.get<CommoditiesResponse>("/macro/commodities", {
    timeout: MACRO_TIMEOUT_MS,
  })
  return res.data
}

export async function fetchMacroCycle(): Promise<MacroCycleResponse> {
  const res = await apiClient.get<MacroCycleResponse>("/macro/macro-cycle", {
    timeout: MACRO_TIMEOUT_MS,
  })
  return res.data
}
