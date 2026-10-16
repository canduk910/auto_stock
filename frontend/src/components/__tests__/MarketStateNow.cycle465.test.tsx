/**
 * cycle465 — 서킷브레이커·사이드카 확인 축(`circuit_breaker.confirmed`) 표시.
 *
 * - 확인 축이 없으면(옛 백엔드·조회 실패) 아무것도 그리지 않는다(추정 배지는 그대로).
 * - 시장별 상태: 정상 / 서킷브레이커 N단계 발동 HH:MM / 시장 임시정지 / 해제 직후.
 * - 사이드카는 별도 배지, 후보 재구독 멈춤 문구는 `low_skip_active` 일 때만.
 */
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'

import { MarketStateNow } from '../MarketStateNow'
import type {
  CircuitBreakerConfirmed,
  MarketOperationStatus,
} from '../../types/market-operation'

function op(confirmed?: CircuitBreakerConfirmed | null): MarketOperationStatus {
  return {
    vi_active_count: 0,
    halt_active_count: 0,
    last_event_count: 2,
    iscd_stat_active_count: 0,
    vi_active_sample: [],
    halt_active_sample: [],
    circuit_breaker: {
      suspected: false,
      reasons: [],
      halt_ratio: 0,
      halted: 0,
      observed: 2,
      representative_mkop_cls_code: 'AF8',
      halt_reasons_sample: [],
      ...(confirmed === undefined ? {} : { confirmed }),
    },
    details: [],
  }
}

const normal = {
  state: 'NORMAL' as const, stage: 0, since: null, last_code: '', source: '', ttl_expires_at: null,
}

function renderNow(marketOp: MarketOperationStatus) {
  return render(
    <MarketStateNow
      marketOp={marketOp}
      marketOpLoading={false}
      marketOpError={false}
      engine={undefined}
      engineError={false}
    />,
  )
}

describe('cycle465 — 서킷브레이커 확인 축', () => {
  it('확인 축이 없으면 그리지 않는다(추정 배지는 그대로)', () => {
    renderNow(op())
    expect(screen.queryByTestId('market-state-now-cb-confirmed')).toBeNull()
    expect(screen.getByTestId('market-state-now-cb')).toBeTruthy()
  })

  it('코스피 CB 1단계 발동 + 코스닥 정상 + 재구독 멈춤 문구', () => {
    renderNow(
      op({
        markets: {
          KOSPI: {
            state: 'CB_ACTIVE', stage: 1, since: '2026-10-15T12:38:11+09:00',
            last_code: 'AF8', source: 'UN', ttl_expires_at: '2026-10-15T13:18:11+09:00',
          },
          KOSDAQ: normal,
        },
        sidecar: { KOSPI: null, KOSDAQ: null },
        low_skip_active: true,
        events_today: [],
      }),
    )
    expect(screen.getByTestId('market-state-now-cb-confirmed-KOSPI').textContent).toContain(
      '코스피 서킷브레이커 1단계 발동 12:38',
    )
    expect(screen.getByTestId('market-state-now-cb-confirmed-KOSDAQ').textContent).toBe('코스닥 정상')
    expect(screen.getByTestId('market-state-now-low-skip')).toBeTruthy()
  })

  it('사이드카 배지는 따로, 재구독 멈춤 문구는 없음', () => {
    renderNow(
      op({
        markets: { KOSPI: normal, KOSDAQ: normal },
        sidecar: { KOSPI: { side: 'sell', since: '2026-10-15T10:00:00+09:00' }, KOSDAQ: null },
        low_skip_active: false,
        events_today: [],
      }),
    )
    expect(screen.getByTestId('market-state-now-sidecar-KOSPI').textContent).toBe('사이드카(매도) 10:00')
    expect(screen.queryByTestId('market-state-now-sidecar-KOSDAQ')).toBeNull()
    expect(screen.queryByTestId('market-state-now-low-skip')).toBeNull()
  })

  it('시장 임시정지·해제 직후 문구', () => {
    renderNow(
      op({
        markets: {
          KOSPI: { ...normal, state: 'HALT_164', since: '2026-10-15T11:00:00+09:00' },
          KOSDAQ: { ...normal, state: 'RELEASED', stage: 1 },
        },
        sidecar: { KOSPI: null, KOSDAQ: null },
        low_skip_active: true,
        events_today: [],
      }),
    )
    expect(screen.getByTestId('market-state-now-cb-confirmed-KOSPI').textContent).toBe('코스피 시장 임시정지 11:00')
    expect(screen.getByTestId('market-state-now-cb-confirmed-KOSDAQ').textContent).toContain('해제 직후')
  })
})
