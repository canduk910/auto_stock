/**
 * cycle278 Red — `updateStrategyParams` 오류 계약 (명세 §6.4 · §7.2 F27~F32).
 *
 * 지금(base 34ba9e6)의 `frontend/src/api/trading.ts:41-50` 은 **`data.success` 검사도
 * 422 분기도 없다**. 이 상태로 라우트만 조이면
 *   - 운영자에게는 `Request failed with status code 422` 라는 opaque 문자열만 보이고
 *   - `success:false`(알 수 없는 전략 id)는 **저장 성공으로 보인다**.
 * 그래서 422 도입 **전에** 같은 파일의 `updateStrategyWeights` 와 동형으로 보강한다.
 *
 * Green 이 만들 계약:
 * ```ts
 * export interface ParamErrorDetail {
 *   key: string | null           // 불변식 오류는 null → 폼 레벨 표시
 *   code: string                 // unknown_key | not_editable | type_mismatch |
 *                                // not_in_choices | pattern_mismatch | out_of_range | budget_invariant
 *   msg: string                  // 한글. pydantic 접두사 없음
 *   strategy_id?: string
 *   given?: unknown
 *   expected?: Record<string, unknown>
 * }
 * export class ParamValidationError extends Error { readonly details: ParamErrorDetail[] }
 * export interface ParamWarningDetail { key: string | null; code: string; msg: string }
 * export interface ParamsUpdateResult {
 *   success: boolean
 *   message: string
 *   applied?: Record<string, StrategyParamValue>
 *   warnings?: ParamWarningDetail[]
 * }
 * updateStrategyParams(id, params): Promise<ParamsUpdateResult>
 * ```
 * - 2xx 인데 `success:false` → `Error(data.message)` (일반 Error, **재포장 금지**).
 * - 422 → `ParamValidationError` — `details` 에 `detail[]` 전체, `message` 는 `detail[0].msg`.
 * - 200 → `applied`/`warnings` 를 그대로 통과시킨다(서버가 무엇을 저장했는지 화면이 확인해야
 *   조용한 데이터 소실이 보인다).
 */
import { describe, it, expect } from 'vitest'
import { http, HttpResponse } from 'msw'

import { updateStrategyParams, ParamValidationError } from '../trading'
import { server } from '../../test/server'

const PUT_PATH = '/api/strategies/:id/params'

describe('cycle278 F27~F32 — updateStrategyParams 오류/경고 계약', () => {
  it('F27 2xx 인데 success:false 면 throw 한다 (현행은 저장 성공으로 보인다)', async () => {
    server.use(
      http.put(PUT_PATH, () =>
        HttpResponse.json({
          success: false,
          data: null,
          message: '알 수 없는 전략: momentumm',
        }),
      ),
    )

    await expect(updateStrategyParams('momentumm', { k_period: 20 })).rejects.toThrow(
      '알 수 없는 전략: momentumm',
    )
  })

  it('F28 422 detail 배열을 구조화 오류(ParamValidationError)로 던진다', async () => {
    server.use(
      http.put(PUT_PATH, () =>
        HttpResponse.json(
          {
            detail: [
              {
                key: 'k_period',
                code: 'out_of_range',
                msg: '변동성 산출 기간은 5 ~ 60 이어야 합니다 — 받은 값 999',
                strategy_id: 'volatility_breakout',
                given: 999,
                expected: { min: 5, max: 60, type: 'int', range_src: 'param_ranges' },
              },
              {
                key: null,
                code: 'budget_invariant',
                msg: '종목당 비중 × 동시 보유 종목수 = 0.3 × 10 = 3.00 으로 1.0 을 넘습니다',
                strategy_id: 'volatility_breakout',
              },
            ],
          },
          { status: 422 },
        ),
      ),
    )

    const err = await updateStrategyParams('volatility_breakout', { k_period: 999 }).then(
      () => null,
      (e: unknown) => e,
    )

    expect(err, '422 는 axios 가 던지므로 2xx 본문 경로가 못 잡는다').toBeInstanceOf(
      ParamValidationError,
    )
    const pv = err as ParamValidationError
    expect(pv.details).toHaveLength(2)
    expect(pv.details[0].key).toBe('k_period')
    expect(pv.details[0].code).toBe('out_of_range')
    expect(pv.details[1].key, '불변식 오류는 key 가 null 이라 폼 레벨에 붙는다').toBeNull()
    expect(pv.message).toContain('5 ~ 60')
  })

  it('F29 422 detail 이 문자열이어도 사람이 읽을 메시지를 뽑는다', async () => {
    server.use(
      http.put(PUT_PATH, () =>
        HttpResponse.json({ detail: '요청 본문이 올바르지 않습니다' }, { status: 422 }),
      ),
    )

    await expect(
      updateStrategyParams('momentum', { position_ratio: 0.2 }),
    ).rejects.toThrow('요청 본문이 올바르지 않습니다')
  })

  it('F30 접두사 없는 한글 메시지는 잘리지 않는다 (영문 구절이 섞여도)', async () => {
    const MSG =
      '종목당 비중은 0.01 ~ 1.0 이어야 합니다 — 받은 값 1.5 (range_src=param_ranges, 비율 저장)'
    server.use(
      http.put(PUT_PATH, () =>
        HttpResponse.json(
          { detail: [{ key: 'position_ratio', code: 'out_of_range', msg: MSG }] },
          { status: 422 },
        ),
      ),
    )

    const err = await updateStrategyParams('momentum', { position_ratio: 1.5 }).then(
      () => null,
      (e: unknown) => e as Error,
    )
    expect(
      err?.message,
      "일반 패턴(`^[A-Za-z ]+, `)으로 접두사를 지우면 한글 본문이 잘린다",
    ).toBe(MSG)
  })

  it('F31 !data.success 가 던진 Error 는 422 폴백 문구로 재포장되지 않는다', async () => {
    server.use(
      http.put(PUT_PATH, () =>
        HttpResponse.json({ success: false, data: null, message: '전략 저장 실패' }),
      ),
    )

    const err = await updateStrategyParams('momentum', { position_ratio: 0.2 }).then(
      () => null,
      (e: unknown) => e as Error,
    )
    expect(err).toBeInstanceOf(Error)
    expect(err).not.toBeInstanceOf(ParamValidationError)
    expect(err?.message).toBe('전략 저장 실패')
  })

  it('F32 2xx 성공 응답의 applied/warnings 를 그대로 전달한다', async () => {
    server.use(
      http.put(PUT_PATH, () =>
        HttpResponse.json({
          success: true,
          data: {
            applied: { max_scan_stocks: 300 },
            warnings: [
              {
                key: 'max_scan_stocks',
                code: 'range_unbounded',
                msg: '범위 근거가 없어 자료형만 검사했습니다',
              },
            ],
          },
          message: '파라미터 저장 완료',
        }),
      ),
    )

    const result = await updateStrategyParams('volatility_breakout', {
      max_scan_stocks: 300,
    })
    expect(result.success).toBe(true)
    expect(result.applied).toEqual({ max_scan_stocks: 300 })
    expect(result.warnings).toHaveLength(1)
    expect(result.warnings?.[0].code).toBe('range_unbounded')
  })
})
