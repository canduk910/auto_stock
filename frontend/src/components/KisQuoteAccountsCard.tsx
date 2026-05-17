/**
 * 사이클 7-D (2026-05-18): Settings 페이지 — 보조 KIS 시세 계좌 관리.
 *
 * 보조 KIS 시세 수신 계좌 등록/제거/활성화 토글 UI.
 * - 등록 폼: label / kis_env / app_key / app_secret(password)
 * - 표: label / kis_env 배지 / app_key 마지막 4자리 / app_secret_masked / active 토글 / 삭제
 * - ConfirmModal 이중 확인 (등록 / active 토글 / 삭제)
 *
 * 안전 원칙:
 * - app_secret 평문 응답 노출 0 (백엔드 마스킹 + UI 는 마스킹만 표시)
 * - 폼 제출 직후 secret state 초기화 — 평문 잔존 시간 최소화
 * - 등록 시 ConfirmModal — "다음 _boot(07:50) 부터 시세 풀에 분배" 안내
 *
 * 백엔드: `/api/integrations/quote-accounts` (사이클 7-A)
 * 시세 활용: 사이클 7-B (WebsocketPool) + 7-C (REST 풀)
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'

import {
  createAccount,
  deleteAccount,
  listAccounts,
  updateAccount,
} from '../api/kis-quote-accounts'
import type {
  KisEnv,
  KisQuoteAccount,
  KisQuoteAccountCreateInput,
} from '../types/kis-quote-accounts'
import ConfirmModal from './ConfirmModal'

const KST_FORMATTER = new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'Asia/Seoul',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})

function formatCreatedAt(iso: string): string {
  try {
    return KST_FORMATTER.format(new Date(iso))
  } catch {
    return iso
  }
}

function maskAppKey(appKey: string): string {
  if (!appKey) return '****'
  if (appKey.length <= 4) return '****'
  return `****${appKey.slice(-4)}`
}

function envBadgeClass(env: KisEnv): string {
  if (env === 'real') {
    return 'bg-red-100 text-red-800 border border-red-300'
  }
  return 'bg-emerald-100 text-emerald-800 border border-emerald-300'
}

export default function KisQuoteAccountsCard() {
  const queryClient = useQueryClient()
  const [formError, setFormError] = useState<string | null>(null)
  const [form, setForm] = useState<KisQuoteAccountCreateInput>({
    label: '',
    app_key: '',
    app_secret: '',
    kis_env: 'real',
  })

  const [pendingAction, setPendingAction] = useState<
    | { kind: 'create' }
    | { kind: 'toggle'; account: KisQuoteAccount; nextActive: boolean }
    | { kind: 'delete'; account: KisQuoteAccount }
    | null
  >(null)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['kis-quote-accounts'],
    queryFn: () => listAccounts(false),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  })

  const accounts: KisQuoteAccount[] = data ?? []

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ['kis-quote-accounts'] })

  const createMutation = useMutation({
    mutationFn: (payload: KisQuoteAccountCreateInput) => createAccount(payload),
    onSuccess: () => {
      invalidate()
      // 평문 secret 잔존 최소화 — 폼 클리어
      setForm({ label: '', app_key: '', app_secret: '', kis_env: 'real' })
      setFormError(null)
      setPendingAction(null)
    },
    onError: (err: unknown) => {
      let msg = '등록 실패'
      if (axios.isAxiosError(err)) {
        const status = err.response?.status
        const detail =
          (err.response?.data as { detail?: string } | undefined)?.detail ?? err.message
        if (status === 409) {
          msg = `label 중복(409): ${detail}`
        } else if (status === 422) {
          msg = `검증 실패(422): ${detail}`
        } else {
          msg = `${status ?? ''} ${detail}`.trim()
        }
      }
      setFormError(msg)
      setPendingAction(null)
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) =>
      updateAccount(id, { active }),
    onSuccess: () => {
      invalidate()
      setPendingAction(null)
    },
    onError: () => {
      setPendingAction(null)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteAccount(id),
    onSuccess: () => {
      invalidate()
      setPendingAction(null)
    },
    onError: () => {
      setPendingAction(null)
    },
  })

  const onSubmitClick = () => {
    setFormError(null)
    // 클라이언트 검증
    const labelTrim = form.label.trim()
    const appKeyTrim = form.app_key.trim()
    const secretTrim = form.app_secret.trim()
    if (!labelTrim || !appKeyTrim || !secretTrim) {
      setFormError('label / app_key / app_secret 모두 필수 입력입니다.')
      return
    }
    if (!/^[A-Za-z0-9\-]+$/.test(labelTrim)) {
      setFormError('label 은 영문/숫자/하이픈만 허용됩니다 (예: quote-1).')
      return
    }
    setPendingAction({ kind: 'create' })
  }

  const onConfirm = () => {
    if (!pendingAction) return
    if (pendingAction.kind === 'create') {
      createMutation.mutate({
        label: form.label.trim(),
        app_key: form.app_key.trim(),
        app_secret: form.app_secret,
        kis_env: form.kis_env,
      })
    } else if (pendingAction.kind === 'toggle') {
      updateMutation.mutate({
        id: pendingAction.account.id,
        active: pendingAction.nextActive,
      })
    } else if (pendingAction.kind === 'delete') {
      deleteMutation.mutate(pendingAction.account.id)
    }
  }

  const onCancel = () => {
    setPendingAction(null)
  }

  const confirmTitle = (() => {
    if (!pendingAction) return ''
    if (pendingAction.kind === 'create') return '보조 KIS 시세 계좌 등록'
    if (pendingAction.kind === 'toggle')
      return `${pendingAction.account.label} ${
        pendingAction.nextActive ? '활성화' : '비활성화'
      }`
    return `${pendingAction.account.label} 삭제`
  })()

  const confirmMessage = (() => {
    if (!pendingAction) return ''
    if (pendingAction.kind === 'create') {
      return `보조 계좌 "${form.label}" (${form.kis_env}) 를 등록합니다. 다음 _boot(07:50) 부터 시세 풀에 분배됩니다 — 41 × (1 + N) 슬롯 확장. 진행하시겠습니까?`
    }
    if (pendingAction.kind === 'toggle') {
      return pendingAction.nextActive
        ? `"${pendingAction.account.label}" 를 활성화합니다. 다음 _boot 부터 시세 풀에 포함됩니다.`
        : `"${pendingAction.account.label}" 를 비활성화합니다. 다음 _boot 부터 시세 풀에서 제외됩니다. 진행하시겠습니까?`
    }
    return `"${pendingAction.account.label}" 를 영구 삭제합니다. 시세 풀에서 즉시 제외됩니다. 진행하시겠습니까?`
  })()

  const confirmLoading =
    createMutation.isPending || updateMutation.isPending || deleteMutation.isPending

  return (
    <div
      className="bg-white rounded-lg shadow p-6 mb-6"
      data-testid="kis-quote-accounts-card"
    >
      <h2 className="text-lg font-semibold text-gray-900 mb-1">
        보조 KIS 시세 계좌
      </h2>
      <p className="text-xs text-gray-500 mb-4">
        시세 수신 전용 보조 계좌를 등록합니다. 매매·잔고·체결통보는 메인 계좌 단일 유지.
        등록 시 시세 풀 슬롯이 <strong>41 × (1 + N)</strong> 으로 확장됩니다 (KIS 공식 한도 — 메인 41 + 보조 N×41).
        다음 부트(07:50) 부터 활성화됩니다.
      </p>

      {/* 목록 */}
      <div className="mb-6">
        {isLoading ? (
          <div className="text-sm text-gray-500">계좌 목록 로딩 중...</div>
        ) : isError ? (
          <div
            className="text-sm text-red-700 bg-red-50 border border-red-200 rounded p-3"
            data-testid="quote-accounts-load-error"
          >
            계좌 목록을 불러오지 못했습니다. 잠시 후 재시도하세요.
          </div>
        ) : accounts.length === 0 ? (
          <div
            className="text-sm text-gray-500 bg-gray-50 border border-gray-200 rounded p-3"
            data-testid="quote-accounts-empty"
          >
            등록된 보조 계좌 없음. 추가하면 시세 풀 슬롯이 <strong>41 × (1 + N)</strong>
            으로 확대됩니다.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-xs">
              <thead>
                <tr className="text-gray-500 text-left border-b border-gray-200">
                  <th className="py-2 px-2 font-medium">label</th>
                  <th className="py-2 px-2 font-medium">환경</th>
                  <th className="py-2 px-2 font-medium">app_key</th>
                  <th className="py-2 px-2 font-medium">app_secret</th>
                  <th className="py-2 px-2 font-medium">등록일</th>
                  <th className="py-2 px-2 font-medium">상태</th>
                  <th className="py-2 px-2 font-medium text-right">관리</th>
                </tr>
              </thead>
              <tbody>
                {accounts.map((a) => (
                  <tr
                    key={a.id}
                    data-testid={`quote-account-row-${a.id}`}
                    className="border-b border-gray-100"
                  >
                    <td className="py-2 px-2 font-medium text-gray-900">{a.label}</td>
                    <td className="py-2 px-2">
                      <span
                        className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium ${envBadgeClass(
                          a.kis_env,
                        )}`}
                      >
                        {a.kis_env.toUpperCase()}
                      </span>
                    </td>
                    <td className="py-2 px-2 font-mono text-gray-700">
                      {maskAppKey(a.app_key)}
                    </td>
                    <td className="py-2 px-2 font-mono text-gray-700">
                      {a.app_secret_masked}
                    </td>
                    <td className="py-2 px-2 text-gray-500">
                      {formatCreatedAt(a.created_at)}
                    </td>
                    <td className="py-2 px-2">
                      <button
                        type="button"
                        data-testid={`quote-account-toggle-${a.id}`}
                        onClick={() =>
                          setPendingAction({
                            kind: 'toggle',
                            account: a,
                            nextActive: !a.active,
                          })
                        }
                        className={`px-2 py-0.5 rounded text-[11px] font-medium ${
                          a.active
                            ? 'bg-emerald-100 text-emerald-800 border border-emerald-300'
                            : 'bg-gray-100 text-gray-600 border border-gray-300'
                        }`}
                      >
                        {a.active ? '활성' : '비활성'}
                      </button>
                    </td>
                    <td className="py-2 px-2 text-right">
                      <button
                        type="button"
                        data-testid={`quote-account-delete-${a.id}`}
                        onClick={() => setPendingAction({ kind: 'delete', account: a })}
                        className="px-2 py-0.5 text-[11px] text-red-600 hover:bg-red-50 rounded"
                      >
                        삭제
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* 등록 폼 */}
      <div className="border-t border-gray-200 pt-4">
        <h3 className="text-sm font-medium text-gray-800 mb-3">신규 보조 계좌 등록</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label
              htmlFor="quote-account-input-label"
              className="text-xs text-gray-500 block mb-1"
            >
              label (영문/숫자/하이픈, 예: quote-1)
            </label>
            <input
              id="quote-account-input-label"
              data-testid="quote-account-input-label"
              type="text"
              value={form.label}
              onChange={(e) => setForm({ ...form, label: e.target.value })}
              className="w-full px-2 py-1 text-sm border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="quote-1"
            />
          </div>
          <div>
            <label className="text-xs text-gray-500 block mb-1">환경</label>
            <div className="flex gap-2">
              <label className="flex items-center gap-1 text-sm cursor-pointer">
                <input
                  type="radio"
                  name="kis-env"
                  data-testid="quote-account-input-kis-env-real"
                  checked={form.kis_env === 'real'}
                  onChange={() => setForm({ ...form, kis_env: 'real' })}
                />
                <span>real (실전)</span>
              </label>
              <label className="flex items-center gap-1 text-sm cursor-pointer">
                <input
                  type="radio"
                  name="kis-env"
                  data-testid="quote-account-input-kis-env-vts"
                  checked={form.kis_env === 'vts'}
                  onChange={() => setForm({ ...form, kis_env: 'vts' })}
                />
                <span>vts (모의)</span>
              </label>
            </div>
          </div>
          <div className="md:col-span-2">
            <label
              htmlFor="quote-account-input-app-key"
              className="text-xs text-gray-500 block mb-1"
            >
              app_key (KIS Developers 발급)
            </label>
            <input
              id="quote-account-input-app-key"
              data-testid="quote-account-input-app-key"
              type="text"
              value={form.app_key}
              onChange={(e) => setForm({ ...form, app_key: e.target.value })}
              className="w-full px-2 py-1 text-sm border border-gray-300 rounded font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="PSXX..."
              autoComplete="off"
            />
          </div>
          <div className="md:col-span-2">
            <label
              htmlFor="quote-account-input-app-secret"
              className="text-xs text-gray-500 block mb-1"
            >
              app_secret (password — 등록 후 평문은 응답·DB 어디에도 노출 안 됨)
            </label>
            <input
              id="quote-account-input-app-secret"
              data-testid="quote-account-input-app-secret"
              type="password"
              value={form.app_secret}
              onChange={(e) => setForm({ ...form, app_secret: e.target.value })}
              className="w-full px-2 py-1 text-sm border border-gray-300 rounded font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
              autoComplete="new-password"
            />
          </div>
        </div>

        {formError && (
          <div
            className="mt-3 p-2 bg-red-50 border border-red-200 rounded text-xs text-red-700"
            data-testid="quote-account-form-error"
          >
            {formError}
          </div>
        )}

        <div className="mt-3 flex justify-end">
          <button
            type="button"
            data-testid="quote-account-submit"
            onClick={onSubmitClick}
            disabled={createMutation.isPending}
            className="px-4 py-1.5 text-sm font-medium text-white bg-blue-600 rounded hover:bg-blue-700 disabled:opacity-50"
          >
            등록
          </button>
        </div>
      </div>

      <ConfirmModal
        open={pendingAction !== null}
        title={confirmTitle}
        message={confirmMessage}
        onConfirm={onConfirm}
        onCancel={onCancel}
        loading={confirmLoading}
      />
    </div>
  )
}
