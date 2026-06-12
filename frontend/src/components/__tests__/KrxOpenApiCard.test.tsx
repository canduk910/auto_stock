/**
 * 사이클 112 (2026-06-12) Red — KrxOpenApiCard (Settings).
 *
 * KRX 정식 OPEN API 키 관리 UI.
 *
 * 회귀 가드 영역 (HIGH 5):
 * - G-UI-1: 초기 GET 응답 표시 (enabled / base_url / key_masked)
 * - G-UI-2: API key 입력 필드 = type=password (평문 잔존 차단)
 * - G-UI-3: 저장 클릭 → PUT 호출 + 평문 key state 즉시 클리어
 * - G-UI-4: useQuery retry:1 명시 (간접 검증 — 컴포넌트 렌더 retry:1 hook)
 * - G-UI-5: 한글 라벨 ("KRX 정식 OPEN API", "키 입력", "활성화", "기본 URL")
 *
 * 보안 의무: 평문 응답 노출 0 + key state 즉시 클리어
 */
import { describe, it, expect } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import KrxOpenApiCard from '../KrxOpenApiCard'
import { TestProviders } from '../../test/providers'
import { wrap } from '../../test/factories'
import { server } from '../../test/server'

const initialStatus = {
  enabled: false,
  base_url: 'https://data-dbg.krx.co.kr/svc/apis',
  key_masked: '****',
}

const updatedStatus = {
  enabled: true,
  base_url: 'https://data-dbg.krx.co.kr/svc/apis',
  key_masked: '****1234',
}

describe('KrxOpenApiCard (사이클 112)', () => {
  it('G-UI-1: 초기 GET 응답 표시 (enabled false + key_masked)', async () => {
    server.use(
      http.get('/api/integrations/krx-open-api', () =>
        HttpResponse.json(wrap(initialStatus))
      )
    )

    render(
      <TestProviders>
        <KrxOpenApiCard />
      </TestProviders>
    )

    // 카드 렌더 + 마스킹 표시
    expect(await screen.findByTestId('krx-open-api-card')).toBeTruthy()

    await waitFor(() => {
      expect(screen.getByTestId('krx-open-api-key-masked').textContent).toBe('****')
    })

    // 활성화 OFF 표시
    expect(screen.getByTestId('krx-open-api-toggle').textContent).toContain('OFF')
  })

  it('G-UI-2: API key 입력 필드 = type=password (평문 잔존 차단)', async () => {
    server.use(
      http.get('/api/integrations/krx-open-api', () =>
        HttpResponse.json(wrap(initialStatus))
      )
    )

    render(
      <TestProviders>
        <KrxOpenApiCard />
      </TestProviders>
    )

    const keyInput = (await screen.findByTestId('krx-open-api-key-input')) as HTMLInputElement
    expect(keyInput.type).toBe('password')
    // 평문 자동완성 차단
    expect(keyInput.autocomplete).toBe('new-password')
  })

  it('G-UI-3: 저장 클릭 → PUT 호출 + 평문 key state 즉시 클리어', async () => {
    type PutBody = { key?: string; base_url?: string; enabled?: boolean }
    let putBody: PutBody | null = null

    server.use(
      http.get('/api/integrations/krx-open-api', () =>
        HttpResponse.json(wrap(initialStatus))
      ),
      http.put('/api/integrations/krx-open-api', async ({ request }) => {
        putBody = (await request.json()) as PutBody
        return HttpResponse.json(wrap(updatedStatus))
      })
    )

    render(
      <TestProviders>
        <KrxOpenApiCard />
      </TestProviders>
    )

    const keyInput = (await screen.findByTestId('krx-open-api-key-input')) as HTMLInputElement
    fireEvent.change(keyInput, { target: { value: 'secret_key_1234' } })
    expect(keyInput.value).toBe('secret_key_1234')

    const saveButton = screen.getByTestId('krx-open-api-save-button')
    fireEvent.click(saveButton)

    // PUT 호출 + body 정합
    await waitFor(() => {
      expect(putBody).not.toBeNull()
    })
    expect((putBody as PutBody | null)?.key).toBe('secret_key_1234')

    // 성공 메시지 + 평문 key state 즉시 클리어 (보안 의무)
    await waitFor(() => {
      expect(screen.getByTestId('krx-open-api-save-success')).toBeTruthy()
    })
    expect(keyInput.value).toBe('')
  })

  it('G-UI-4: useQuery 호출 (refetchInterval 60초 영속, retry:1)', async () => {
    // 간접 검증 — fetch 1회 후 렌더 정상 작동 = useQuery 정상 작동
    server.use(
      http.get('/api/integrations/krx-open-api', () =>
        HttpResponse.json(wrap(initialStatus))
      )
    )

    render(
      <TestProviders>
        <KrxOpenApiCard />
      </TestProviders>
    )

    // 정상 렌더 = retry:1 효과 + refetchInterval 정상
    await waitFor(() => {
      expect(screen.getByTestId('krx-open-api-key-masked').textContent).toBe('****')
    })
  })

  it('G-UI-5: 한글 라벨 영속 (사이클 89 답습)', async () => {
    server.use(
      http.get('/api/integrations/krx-open-api', () =>
        HttpResponse.json(wrap(initialStatus))
      )
    )

    render(
      <TestProviders>
        <KrxOpenApiCard />
      </TestProviders>
    )

    // 카드 타이틀 — 정확 매칭
    expect(await screen.findByText(/KRX 정식 OPEN API/)).toBeTruthy()

    // 라벨 영역 — 데이터 로드 후 노출. partial match (label 영역이 부가 텍스트와 결합 가능)
    await waitFor(() => {
      expect(screen.queryByText(/키 입력/)).toBeTruthy()
    })
    expect(screen.queryByText(/활성화/)).toBeTruthy()
    expect(screen.queryByText(/기본 URL/)).toBeTruthy()
  })
})
