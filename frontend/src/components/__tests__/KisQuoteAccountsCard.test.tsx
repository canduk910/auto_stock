/**
 * 사이클 7-D (2026-05-18) Red — KisQuoteAccountsCard (Settings).
 *
 * 보조 KIS 시세 수신 계좌 등록/제거/활성화 토글 UI.
 *
 * 요구 행위:
 * - 7D-A: 빈 목록 → 안내 메시지 ("등록된 보조 계좌 없음")
 * - 7D-B: 1개 등록 → 표 1행 + 마스킹 확인 (app_secret_masked = "****1234")
 * - 7D-C: 등록 폼 제출 정상 → POST 호출 + 목록 갱신
 * - 7D-D: label 중복 409 → 에러 메시지 노출
 * - 7D-E: 빈 값 422 → 클라이언트/서버 검증 에러
 * - 7D-F: active 토글 클릭 → PUT 호출 (ConfirmModal 이중 확인)
 * - 7D-G: 삭제 버튼 → ConfirmModal 후 DELETE 호출
 * - 7D-H: app_secret 평문이 응답에 절대 노출 안 됨 — UI 가 마스킹만 표시
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import KisQuoteAccountsCard from '../KisQuoteAccountsCard'
import { TestProviders } from '../../test/providers'
import { wrap } from '../../test/factories'
import { server } from '../../test/server'

const account1 = {
  id: 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
  label: 'quote-1',
  app_key: 'PSXXXXXXXXXXXXXXXXXXXXX1234',
  app_secret_masked: '****7890',
  kis_env: 'real' as const,
  active: true,
  created_at: '2026-05-18T08:00:00+09:00',
  updated_at: null,
}

const account2 = {
  id: '11111111-2222-3333-4444-555555555555',
  label: 'quote-2',
  app_key: 'PSYYYYYYYYYYYYYYYYYYYYY5678',
  app_secret_masked: '****abcd',
  kis_env: 'vts' as const,
  active: false,
  created_at: '2026-05-18T08:05:00+09:00',
  updated_at: null,
}

describe('KisQuoteAccountsCard', () => {
  it('7D-A: 빈 목록 → 안내 메시지', async () => {
    server.use(
      http.get('/api/integrations/quote-accounts', () =>
        HttpResponse.json(wrap({ accounts: [] })),
      ),
    )
    render(
      <TestProviders>
        <KisQuoteAccountsCard />
      </TestProviders>,
    )

    await screen.findByTestId('kis-quote-accounts-card')
    await waitFor(() => {
      const empty = screen.getByTestId('quote-accounts-empty')
      expect(empty.textContent).toMatch(/등록된 보조 계좌 없음|41/)
    })
  })

  it('7D-B: 1개 등록 → 표 1행 + app_secret 마스킹', async () => {
    server.use(
      http.get('/api/integrations/quote-accounts', () =>
        HttpResponse.json(wrap({ accounts: [account1] })),
      ),
    )
    render(
      <TestProviders>
        <KisQuoteAccountsCard />
      </TestProviders>,
    )

    const row = await screen.findByTestId(`quote-account-row-${account1.id}`)
    expect(row.textContent).toContain('quote-1')
    expect(row.textContent).toContain('****7890')
    // 평문 app_secret 절대 없음
    expect(row.textContent).not.toContain('abcdef1234567890')
    // app_key 마지막 4 자리(1234) 노출
    expect(row.textContent).toContain('1234')
    // kis_env 배지
    expect(row.textContent).toMatch(/real|REAL/)
  })

  it('7D-C: 등록 폼 제출 정상 → POST + 목록 갱신', async () => {
    let postCallCount = 0
    let postBody: Record<string, unknown> = {}
    let listCallCount = 0
    server.use(
      http.get('/api/integrations/quote-accounts', () => {
        listCallCount += 1
        return HttpResponse.json(
          wrap({ accounts: listCallCount > 1 ? [account1] : [] }),
        )
      }),
      http.post('/api/integrations/quote-accounts', async ({ request }) => {
        postCallCount += 1
        postBody = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(wrap(account1), { status: 201 })
      }),
    )

    render(
      <TestProviders>
        <KisQuoteAccountsCard />
      </TestProviders>,
    )

    // 초기 fetch 완료 대기
    await screen.findByTestId('quote-accounts-empty')

    // 폼 입력
    fireEvent.change(screen.getByTestId('quote-account-input-label'), {
      target: { value: 'quote-1' },
    })
    fireEvent.change(screen.getByTestId('quote-account-input-app-key'), {
      target: { value: 'PSXXXXXXXXXXXXXXXXXXXXX1234' },
    })
    fireEvent.change(screen.getByTestId('quote-account-input-app-secret'), {
      target: { value: 'plain-secret-text-1234567890' },
    })
    // kis_env 라디오 — real 기본 가정. 명시 클릭
    const realRadio = screen.getByTestId('quote-account-input-kis-env-real')
    fireEvent.click(realRadio)

    // 등록 버튼 클릭 (ConfirmModal 노출)
    fireEvent.click(screen.getByTestId('quote-account-submit'))

    // ConfirmModal 확인
    const confirmBtn = await screen.findByText('확인')
    fireEvent.click(confirmBtn)

    await waitFor(() => {
      expect(postCallCount).toBe(1)
    })
    expect(postBody.label).toBe('quote-1')
    expect(postBody.app_key).toBe('PSXXXXXXXXXXXXXXXXXXXXX1234')
    expect(postBody.app_secret).toBe('plain-secret-text-1234567890')
    expect(postBody.kis_env).toBe('real')

    // 목록 invalidate + 재조회
    await waitFor(() => {
      expect(listCallCount).toBeGreaterThan(1)
    })
  })

  it('7D-D: label 중복 409 → 에러 메시지', async () => {
    server.use(
      http.get('/api/integrations/quote-accounts', () =>
        HttpResponse.json(wrap({ accounts: [] })),
      ),
      http.post('/api/integrations/quote-accounts', () =>
        HttpResponse.json({ detail: 'label 충돌: quote-1' }, { status: 409 }),
      ),
    )

    render(
      <TestProviders>
        <KisQuoteAccountsCard />
      </TestProviders>,
    )

    await screen.findByTestId('quote-accounts-empty')

    fireEvent.change(screen.getByTestId('quote-account-input-label'), {
      target: { value: 'quote-1' },
    })
    fireEvent.change(screen.getByTestId('quote-account-input-app-key'), {
      target: { value: 'PS' + 'A'.repeat(20) },
    })
    fireEvent.change(screen.getByTestId('quote-account-input-app-secret'), {
      target: { value: 'secret-1234567890' },
    })
    fireEvent.click(screen.getByTestId('quote-account-submit'))
    fireEvent.click(await screen.findByText('확인'))

    await waitFor(() => {
      const err = screen.getByTestId('quote-account-form-error')
      expect(err.textContent).toMatch(/label|중복|409/i)
    })
  })

  it('7D-E: 빈 값 → 클라이언트 검증 에러 (POST 미발사)', async () => {
    let postCallCount = 0
    server.use(
      http.get('/api/integrations/quote-accounts', () =>
        HttpResponse.json(wrap({ accounts: [] })),
      ),
      http.post('/api/integrations/quote-accounts', () => {
        postCallCount += 1
        return HttpResponse.json(wrap(account1), { status: 201 })
      }),
    )

    render(
      <TestProviders>
        <KisQuoteAccountsCard />
      </TestProviders>,
    )

    await screen.findByTestId('quote-accounts-empty')

    // 빈 상태로 submit 클릭
    fireEvent.click(screen.getByTestId('quote-account-submit'))

    await waitFor(() => {
      const err = screen.getByTestId('quote-account-form-error')
      expect(err.textContent).toMatch(/필수|비어|입력/)
    })
    expect(postCallCount).toBe(0)
  })

  it('7D-F: active 토글 클릭 → PUT 호출 (ConfirmModal 후)', async () => {
    let putCallCount = 0
    let putBody: Record<string, unknown> = {}
    server.use(
      http.get('/api/integrations/quote-accounts', () =>
        HttpResponse.json(wrap({ accounts: [account1] })),
      ),
      http.put('/api/integrations/quote-accounts/:id', async ({ request }) => {
        putCallCount += 1
        putBody = (await request.json()) as Record<string, unknown>
        return HttpResponse.json(wrap({ ...account1, active: false }))
      }),
    )

    render(
      <TestProviders>
        <KisQuoteAccountsCard />
      </TestProviders>,
    )

    const toggle = await screen.findByTestId(`quote-account-toggle-${account1.id}`)
    fireEvent.click(toggle)
    fireEvent.click(await screen.findByText('확인'))

    await waitFor(() => {
      expect(putCallCount).toBe(1)
    })
    expect(putBody.active).toBe(false)
  })

  it('7D-G: 삭제 버튼 → ConfirmModal 후 DELETE 호출', async () => {
    let deleteCallCount = 0
    server.use(
      http.get('/api/integrations/quote-accounts', () =>
        HttpResponse.json(wrap({ accounts: [account1] })),
      ),
      http.delete('/api/integrations/quote-accounts/:id', () => {
        deleteCallCount += 1
        return HttpResponse.json(wrap({ deleted: true, id: account1.id }))
      }),
    )

    render(
      <TestProviders>
        <KisQuoteAccountsCard />
      </TestProviders>,
    )

    const delBtn = await screen.findByTestId(`quote-account-delete-${account1.id}`)
    fireEvent.click(delBtn)
    fireEvent.click(await screen.findByText('확인'))

    await waitFor(() => {
      expect(deleteCallCount).toBe(1)
    })
  })

  it('7D-H: app_secret 평문이 응답·UI 어디에도 노출 안 됨', async () => {
    // 백엔드가 항상 마스킹 — 만약 실수로 평문이 와도 UI 가 의존 안 해야 함
    server.use(
      http.get('/api/integrations/quote-accounts', () =>
        HttpResponse.json(wrap({ accounts: [account1, account2] })),
      ),
    )

    const { container } = render(
      <TestProviders>
        <KisQuoteAccountsCard />
      </TestProviders>,
    )

    await screen.findByTestId(`quote-account-row-${account1.id}`)
    await screen.findByTestId(`quote-account-row-${account2.id}`)
    const text = container.textContent ?? ''
    // 마스킹 형식만 노출
    expect(text).toContain('****7890')
    expect(text).toContain('****abcd')
    // app_secret 평문 키워드(우리가 절대 보내지 말아야 할 형식) 부재
    expect(text).not.toContain('app_secret_plain')
  })

  it('7D-I: app_secret 입력 후 제출 성공 시 폼 state 초기화 (평문 잔존 최소화)', async () => {
    server.use(
      http.get('/api/integrations/quote-accounts', () =>
        HttpResponse.json(wrap({ accounts: [] })),
      ),
      http.post('/api/integrations/quote-accounts', () =>
        HttpResponse.json(wrap(account1), { status: 201 }),
      ),
    )

    render(
      <TestProviders>
        <KisQuoteAccountsCard />
      </TestProviders>,
    )

    await screen.findByTestId('quote-accounts-empty')

    const labelInput = screen.getByTestId('quote-account-input-label') as HTMLInputElement
    const appKeyInput = screen.getByTestId('quote-account-input-app-key') as HTMLInputElement
    const secretInput = screen.getByTestId(
      'quote-account-input-app-secret',
    ) as HTMLInputElement

    fireEvent.change(labelInput, { target: { value: 'quote-1' } })
    fireEvent.change(appKeyInput, { target: { value: 'PS' + 'A'.repeat(20) } })
    fireEvent.change(secretInput, { target: { value: 'plain-secret-1234567890' } })

    fireEvent.click(screen.getByTestId('quote-account-submit'))
    fireEvent.click(await screen.findByText('확인'))

    await waitFor(() => {
      // 제출 성공 후 secret 입력은 비워져 있어야 함 (평문 잔존 최소화)
      expect(secretInput.value).toBe('')
    })
  })

  // password input 타입 검증 — DOM 노출 차단
  it('7D-J: app_secret input type=password 강제', () => {
    server.use(
      http.get('/api/integrations/quote-accounts', () =>
        HttpResponse.json(wrap({ accounts: [] })),
      ),
    )
    render(
      <TestProviders>
        <KisQuoteAccountsCard />
      </TestProviders>,
    )

    const secretInput = screen.getByTestId(
      'quote-account-input-app-secret',
    ) as HTMLInputElement
    expect(secretInput.type).toBe('password')
  })
})

// 사용 안 함 — lint 회피용 placeholder
void vi.fn
