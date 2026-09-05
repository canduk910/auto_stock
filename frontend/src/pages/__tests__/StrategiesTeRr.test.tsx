/**
 * 사이클 F 프론트 (F-FE1~F-FE6) — TE(트레이딩 예지치)/RR(손익비) 전략 카드 회귀 가드.
 *
 * 명세: _workspace/red/_behaviors_cycleF_te_rr_20260802.md §F-FE1~F-FE6
 * 자문: _workspace/domain_consult/cycle_te_expectancy_dashboard_20260802.md §209-234 (통합 카드 레이아웃)
 *
 * 백엔드 계약: GET /api/strategies/te?months=3 → ApiResponse<TeRrMetrics[]>
 * 관찰 전용 — 매매 hot path 무접촉. 기존 4임계 그리드(사이클 103) 회귀 0.
 */
import { describe, expect, it, beforeEach, afterEach } from 'vitest'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import type { ReactNode } from 'react'

import Strategies from '../Strategies'
import { server } from '../../test/server'
import type { TeRrMetrics } from '../../types/strategy'

function withProviders(children: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  })
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  )
}

// 4임계 렌더에 필요한 최소 전략 목록 (사이클 103 패턴 답습)
const STRATEGIES_RESPONSE = {
  strategies: [
    {
      key: 'momentum',
      name: '상한가 모멘텀',
      weight: 0.25,
      enabled: true,
      total_investment: 10_000_000,
      params: { stop_loss_rate: -7.5, daily_loss_limit: -5.0, trailing_stop_rate: -2.0, position_ratio: 0.25 },
    },
    {
      key: 'volatility_breakout',
      name: '변동성 돌파',
      weight: 0.25,
      enabled: true,
      total_investment: 10_000_000,
      params: { stop_loss_rate: -3.0, daily_loss_limit: -5.0, trailing_stop_rate: -2.0, position_ratio: 0.25 },
    },
    {
      key: 'donchian_swing',
      name: '돈치안 스윙',
      weight: 0.15,
      enabled: true,
      total_investment: 5_000_000,
      params: { stop_loss_rate: -7.0, daily_loss_limit: -5.0, trailing_stop_rate: -2.0, position_ratio: 0.2 },
    },
    {
      key: 'long_tail_volatility',
      name: '롱테일 변동성 돌파',
      weight: 0.15,
      enabled: true,
      total_investment: 5_000_000,
      params: { stop_loss_rate: -3.0, daily_loss_limit: -5.0, trailing_stop_rate: -2.0, position_ratio: 0.2 },
    },
    {
      key: 'bull_flag_breakout',
      name: '눌림목 돌파',
      weight: 0.1,
      enabled: true,
      total_investment: 3_000_000,
      params: { stop_loss_rate: -5.0, daily_loss_limit: -5.0, trailing_stop_rate: -2.0, position_ratio: 0.2 },
    },
    {
      key: 'vcp_breakout',
      name: 'VCP 변동성 수축',
      weight: 0.1,
      enabled: true,
      total_investment: 3_000_000,
      params: { stop_loss_rate: -7.0, daily_loss_limit: -5.0, trailing_stop_rate: -2.0, position_ratio: 0.2 },
    },
  ],
}

// 우위 배지 + RR 게이지(마커 우측 채움) — ASCII 목업(자문 §216) 값 답습
const MOMENTUM_TE: TeRrMetrics = {
  strategy_id: 'momentum',
  n: 21,
  win: 8,
  loss: 13,
  even: 0,
  win_rate: 8 / 21,
  avg_win_pct: 6.2,
  avg_loss_pct: -2.1,
  te_pct: 1.5,
  te_krw_avg: 15238,
  realized_sum_krw: 320000,
  rr: 3.0,
  required_rr: 1.86,
  rr_margin: 1.14,
  rr_available: true,
  sample_tier: 'low',
  verdict: 'superior',
  structure_tag: 'robust',
  single_trade_dominant: false,
}

// 열위 배지 + RR 게이지(마커 좌측 채움), 정상 표본.
// team-lead 지적 실측 케이스 답습: verdict='inferior' + structure_tag='robust' 동시 표출
// (win_rate<0.5 ∧ rr>=1.0 4분면 규칙과 정합 — 저승률·고손익비 *구조* 이지 "우량"을 뜻하지 않음).
// verdict 배지(열위/손실색)가 지배 신호, structure_tag(견고형)는 중립 보조 라벨이어야 오독 없음.
const VB_TE: TeRrMetrics = {
  strategy_id: 'volatility_breakout',
  n: 65,
  win: 27,
  loss: 38,
  even: 0,
  win_rate: 27 / 65,
  avg_win_pct: 2.0,
  avg_loss_pct: -1.5,
  te_pct: -0.63,
  te_krw_avg: -8200,
  realized_sum_krw: -533000,
  rr: 1.35,
  required_rr: 1.83,
  rr_margin: -0.48,
  rr_available: true,
  sample_tier: 'normal',
  verdict: 'inferior',
  structure_tag: 'robust',
  single_trade_dominant: false,
}

// 균형형 구조 태그 예시 (long_tail_volatility) — win_rate>=0.5 ∧ rr>=1.0 (그 외 분기)
const LTV_TE: TeRrMetrics = {
  strategy_id: 'long_tail_volatility',
  n: 42,
  win: 24,
  loss: 18,
  even: 0,
  win_rate: 24 / 42,
  avg_win_pct: 3.5,
  avg_loss_pct: -2.8,
  te_pct: 1.05,
  te_krw_avg: 7000,
  realized_sum_krw: 294000,
  rr: 1.25,
  required_rr: 0.75,
  rr_margin: 0.5,
  rr_available: true,
  sample_tier: 'normal',
  verdict: 'superior',
  structure_tag: 'balanced',
  single_trade_dominant: false,
}

// N<20 표본 부족 — 뮤트 + 게이지/구조 숨김
const DONCHIAN_TE: TeRrMetrics = {
  strategy_id: 'donchian_swing',
  n: 9,
  win: 2,
  loss: 5,
  even: 2,
  win_rate: 2 / 9,
  avg_win_pct: 8.1,
  avg_loss_pct: -5.4,
  te_pct: -4.42,
  te_krw_avg: -19800,
  realized_sum_krw: -178200,
  rr: null,
  required_rr: null,
  rr_margin: null,
  rr_available: false,
  sample_tier: 'insufficient',
  verdict: 'undecided',
  structure_tag: null,
  single_trade_dominant: false,
}

// 20<=N<50, min(W,L)<5 — RR 참고 불가 + 구조 숨김, TE/배지는 정상
const BFB_TE: TeRrMetrics = {
  strategy_id: 'bull_flag_breakout',
  n: 25,
  win: 22,
  loss: 3,
  even: 0,
  win_rate: 22 / 25,
  avg_win_pct: 4.0,
  avg_loss_pct: -3.0,
  te_pct: 3.16,
  te_krw_avg: 12000,
  realized_sum_krw: 300000,
  rr: null,
  required_rr: 3 / 22,
  rr_margin: null,
  rr_available: false,
  sample_tier: 'low',
  verdict: 'superior',
  structure_tag: null,
  single_trade_dominant: false,
}

// N>=50, 단일거래 의존 플래그
const VCP_TE: TeRrMetrics = {
  strategy_id: 'vcp_breakout',
  n: 55,
  win: 20,
  loss: 15,
  even: 0,
  win_rate: 20 / 55,
  avg_win_pct: 5.0,
  avg_loss_pct: -3.0,
  te_pct: 0.6,
  te_krw_avg: 9000,
  realized_sum_krw: 495000,
  rr: 1.67,
  required_rr: 0.75,
  rr_margin: 0.92,
  rr_available: true,
  sample_tier: 'normal',
  verdict: 'superior',
  structure_tag: 'robust',
  single_trade_dominant: true,
}

const TE_RESPONSE: TeRrMetrics[] = [MOMENTUM_TE, VB_TE, LTV_TE, DONCHIAN_TE, BFB_TE, VCP_TE]

beforeEach(() => {
  server.use(
    http.get('*/api/strategies', () =>
      HttpResponse.json({ success: true, data: STRATEGIES_RESPONSE, message: 'OK' }),
    ),
    http.get('*/api/strategies/te', () =>
      HttpResponse.json({ success: true, data: TE_RESPONSE, message: 'OK' }),
    ),
  )
})

afterEach(() => {
  server.resetHandlers()
})

describe('사이클 F 프론트 — TE/RR 전략 카드', () => {
  it('F-FE2/F-FE3 우위 배지 + TE 헤드라인 렌더 (momentum, low tier, rr_available)', async () => {
    render(withProviders(<Strategies />))

    await waitFor(() => {
      expect(screen.getByTestId('te-section-momentum')).toBeTruthy()
    })

    const verdict = screen.getByTestId('te-verdict-momentum')
    expect(verdict.textContent ?? '').toContain('우위')

    const teValue = screen.getByTestId('te-value-momentum')
    expect(teValue.textContent ?? '').toContain('1.5')
    // TE 양수 = 이익색
    expect(teValue.className).toContain('pnl-profit')
  })

  it('F-FE2/F-FE3 열위 배지 렌더 (volatility_breakout, normal tier)', async () => {
    render(withProviders(<Strategies />))

    await waitFor(() => {
      expect(screen.getByTestId('te-section-volatility_breakout')).toBeTruthy()
    })

    const verdict = screen.getByTestId('te-verdict-volatility_breakout')
    expect(verdict.textContent ?? '').toContain('열위')

    const teValue = screen.getByTestId('te-value-volatility_breakout')
    expect(teValue.textContent ?? '').toContain('-0.6')
    // TE 음수 = 손실색
    expect(teValue.className).toContain('pnl-loss')
  })

  it('F-FE3 N<20 표본 부족 뮤트 — 배지 회색 + 게이지/구조 숨김 + raw 승/패/N', async () => {
    render(withProviders(<Strategies />))

    await waitFor(() => {
      expect(screen.getByTestId('te-section-donchian_swing')).toBeTruthy()
    })

    const verdict = screen.getByTestId('te-verdict-donchian_swing')
    expect(verdict.textContent ?? '').toContain('판정 유보')

    // 게이지 자체는 렌더되지만 "RR 참고 불가" 류 안내 텍스트만 (막대 fill 없음)
    expect(screen.queryByTestId('rr-gauge-fill-donchian_swing')).toBeNull()
    // 구조 태그 숨김
    expect(screen.queryByTestId('te-structure-donchian_swing')).toBeNull()

    // raw 승/패/N 노출
    const decomposition = screen.getByTestId('te-decomposition-donchian_swing')
    expect(decomposition.textContent ?? '').toContain('2')
    expect(decomposition.textContent ?? '').toContain('5')
    expect(decomposition.textContent ?? '').toContain('9')

    // 표본 부족 캡션
    const caption = screen.getByTestId('te-sample-caption-donchian_swing')
    expect(caption.textContent ?? '').toContain('표본 부족')
    expect(caption.textContent ?? '').toContain('9건')
  })

  it('F-FE3 20<=N<50 + min(W,L)<5 — RR 게이지 대신 "참고 불가" + 구조 숨김 (bull_flag_breakout)', async () => {
    render(withProviders(<Strategies />))

    await waitFor(() => {
      expect(screen.getByTestId('te-section-bull_flag_breakout')).toBeTruthy()
    })

    // TE/배지는 정상 표시 (뮤트 아님)
    const verdict = screen.getByTestId('te-verdict-bull_flag_breakout')
    expect(verdict.textContent ?? '').toContain('우위')

    // RR 게이지 fill 없음 + 안내 텍스트
    expect(screen.queryByTestId('rr-gauge-fill-bull_flag_breakout')).toBeNull()
    const gaugeArea = screen.getByTestId('rr-gauge-bull_flag_breakout')
    expect(gaugeArea.textContent ?? '').toContain('참고 불가')

    // 구조 태그 숨김
    expect(screen.queryByTestId('te-structure-bull_flag_breakout')).toBeNull()
  })

  it('F-FE2 RR 게이지 채움/마커 — 우위(채움>마커) vs 열위(채움<마커)', async () => {
    render(withProviders(<Strategies />))

    await waitFor(() => {
      expect(screen.getByTestId('rr-gauge-fill-momentum')).toBeTruthy()
    })

    const momentumFill = screen.getByTestId('rr-gauge-fill-momentum')
    const momentumMarker = screen.getByTestId('rr-gauge-marker-momentum')
    const momentumFillPct = parseFloat((momentumFill as HTMLElement).style.width)
    const momentumMarkerPct = parseFloat((momentumMarker as HTMLElement).style.left)
    // momentum: rr=3.0 > required_rr=1.86 → 채움이 마커보다 우측(큰 값)
    expect(momentumFillPct).toBeGreaterThan(momentumMarkerPct)
    // 우위 = 이익색
    expect(momentumFill.className).toContain('pnl-profit')

    const vbFill = screen.getByTestId('rr-gauge-fill-volatility_breakout')
    const vbMarker = screen.getByTestId('rr-gauge-marker-volatility_breakout')
    const vbFillPct = parseFloat((vbFill as HTMLElement).style.width)
    const vbMarkerPct = parseFloat((vbMarker as HTMLElement).style.left)
    // VB: rr=1.35 < required_rr=1.83 → 채움이 마커보다 작음
    expect(vbFillPct).toBeLessThan(vbMarkerPct)
    // 열위 = 손실색
    expect(vbFill.className).toContain('pnl-loss')
  })

  it('F-FE2 구조 태그 렌더 — robust/balanced 한글 라벨', async () => {
    render(withProviders(<Strategies />))

    await waitFor(() => {
      expect(screen.getByTestId('te-structure-momentum')).toBeTruthy()
    })

    expect(screen.getByTestId('te-structure-momentum').textContent ?? '').toContain('견고형')
    expect(screen.getByTestId('te-structure-long_tail_volatility').textContent ?? '').toContain('균형형')
  })

  it('team-lead 보강 — verdict 배지가 지배 신호, structure_tag 는 중립 보조 (VB: 열위+견고형 동시 오독 방지)', async () => {
    render(withProviders(<Strategies />))

    await waitFor(() => {
      expect(screen.getByTestId('te-structure-volatility_breakout')).toBeTruthy()
    })

    // verdict 배지 = 지배적 신호: 손실색 + 굵은 글씨 + structure_tag 보다 큰 글자
    const verdict = screen.getByTestId('te-verdict-volatility_breakout')
    expect(verdict.textContent ?? '').toContain('열위')
    expect(verdict.className).toContain('pnl-loss')
    expect(verdict.className).toContain('font-bold')
    expect(verdict.className).toContain('text-sm')

    // structure_tag = 중립 보조: verdict 색(이익/손실)을 따라가지 않는 회색 + 작은 글자 +
    // "형태 설명"을 병기해 "견고형" 단독 긍정 어감을 완화
    const structure = screen.getByTestId('te-structure-volatility_breakout')
    expect(structure.textContent ?? '').toContain('견고형')
    expect(structure.textContent ?? '').toContain('저승률')
    expect(structure.className).not.toContain('pnl-profit')
    expect(structure.className).not.toContain('pnl-loss')
    expect(structure.className).toContain('text-gray')
    expect(structure.className).toContain('text-xs')
  })

  it('F-FE3 표본 캡션 — low+rr_available amber 안내, normal+single_trade_dominant 플래그', async () => {
    render(withProviders(<Strategies />))

    await waitFor(() => {
      expect(screen.getByTestId('te-sample-caption-momentum')).toBeTruthy()
    })

    // momentum: low tier + rr_available → 추세 참고용 안내
    expect(screen.getByTestId('te-sample-caption-momentum').textContent ?? '').toContain('표본 적음')

    // vcp_breakout: single_trade_dominant → RR 과대 가능 플래그
    const vcpCaption = screen.getByTestId('te-sample-caption-vcp_breakout')
    expect(vcpCaption.textContent ?? '').toContain('단일')
  })

  it('F-FE5 페이지 하단 참조표 + 교육 캡션 1회 렌더 (자문 §234 문구)', async () => {
    render(withProviders(<Strategies />))

    await waitFor(() => {
      expect(screen.getByTestId('te-reference-table')).toBeTruthy()
    })

    const table = screen.getByTestId('te-reference-table')
    // 승률 10~90 → 필요RR 9.00~0.11 (표 1-2)
    expect(table.textContent ?? '').toContain('10%')
    expect(table.textContent ?? '').toContain('9.00')
    expect(table.textContent ?? '').toContain('90%')
    expect(table.textContent ?? '').toContain('0.11')
    expect(table.textContent ?? '').toContain('50%')
    expect(table.textContent ?? '').toContain('1.00')

    const caption = screen.getByTestId('te-education-caption')
    expect(caption.textContent ?? '').toContain('TE는 거래당 기대손익')
    expect(caption.textContent ?? '').toContain('RR비율은 손익비')
    expect(caption.textContent ?? '').toContain('RR > 필요RR 이면 우위')
    expect(caption.textContent ?? '').toContain('터틀 전략')
    expect(caption.textContent ?? '').toContain('미실현은 제외')

    // 하단 1회만 — 카드별 반복 렌더 아님 (전체 문서에 정확히 1개)
    expect(screen.getAllByTestId('te-reference-table')).toHaveLength(1)
    expect(screen.getAllByTestId('te-education-caption')).toHaveLength(1)
  })

  it('F-FE6 성과 데이터 API 에러 시 graceful (서버 연결 끊김)', async () => {
    server.use(
      http.get('*/api/strategies/te', () => HttpResponse.error()),
    )

    render(withProviders(<Strategies />))

    // 기존 4임계 카드는 정상 렌더 (TE 실패가 카드 전체를 무너뜨리지 않음)
    await waitFor(() => {
      expect(screen.getByTestId('strategy-card-momentum')).toBeTruthy()
    })

    await waitFor(
      () => {
        const section = screen.getByTestId('te-section-momentum')
        expect((section.textContent ?? '')).toMatch(/서버 연결 끊김|조회 실패/)
      },
      { timeout: 3000 },
    )
  })

  it('회귀: 기존 4임계 그리드 + testid 변경 0 (사이클 103 영속)', async () => {
    render(withProviders(<Strategies />))

    await waitFor(() => {
      expect(screen.getByTestId('strategy-card-momentum')).toBeTruthy()
    })

    expect(screen.getByTestId('strategy-momentum-stop-loss-rate')).toBeTruthy()
    expect(screen.getByTestId('strategy-momentum-daily-loss-limit')).toBeTruthy()
    expect(screen.getByTestId('strategy-momentum-trailing-stop-rate')).toBeTruthy()
    expect(screen.getByTestId('strategy-momentum-position-ratio')).toBeTruthy()
  })
})
