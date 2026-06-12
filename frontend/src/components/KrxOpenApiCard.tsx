/**
 * 사이클 112 (2026-06-12): Settings 페이지 — KRX 정식 OPEN API 키 관리.
 *
 * openapi.krx.co.kr (KRX Data Marketplace) 정식 OPEN API 키 입력/조회/토글.
 * - 입력 폼: API key (type=password) + base URL (text) + enabled 토글
 * - 표시: 마스킹된 키 (`****1234`)
 * - 저장: PUT /api/integrations/krx-open-api (평문 잔존 차단 — secret state 즉시 클리어)
 *
 * 보안 원칙 (KIS quote-accounts 패턴 답습):
 * - API key 평문 응답 노출 0 (백엔드 마스킹 + UI 는 마스킹만 표시)
 * - 폼 제출 직후 key state 초기화 — 평문 잔존 시간 최소화
 * - 한글 라벨 (사이클 89 영속)
 *
 * 사이클 65 H3 + 사이클 75 G-RT 영속: useQuery retry: 1 명시.
 *
 * 백엔드: `/api/integrations/krx-open-api` (사이클 112)
 * 실제 endpoint 통합: 사이클 113+ 별도 사이클 (본 사이클 = 인프라 사전 구성만)
 */
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import axios from 'axios'

import { getKrxOpenApi, updateKrxOpenApi } from '../api/krx-open-api'
import type {
  KrxOpenApiStatus,
  KrxOpenApiUpdateRequest,
} from '../types/krx-open-api'

const DEFAULT_BASE_URL = 'https://data-dbg.krx.co.kr/svc/apis'

export default function KrxOpenApiCard() {
  const queryClient = useQueryClient()
  const [keyInput, setKeyInput] = useState('')
  const [baseUrlInput, setBaseUrlInput] = useState('')
  const [enabledDraft, setEnabledDraft] = useState<boolean | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null)

  const { data, isLoading, isError } = useQuery<KrxOpenApiStatus>({
    queryKey: ['integration', 'krx-open-api'],
    queryFn: getKrxOpenApi,
    retry: 1, // 사이클 65 H3 + 사이클 75 G-RT 영속
    refetchInterval: 60_000, // 사이클 75 패턴 답습
  })

  const updateMutation = useMutation({
    mutationFn: (body: KrxOpenApiUpdateRequest) => updateKrxOpenApi(body),
    onSuccess: (next) => {
      // 평문 key state 즉시 클리어 (보안 의무) — 잔존 시간 최소화
      setKeyInput('')
      setBaseUrlInput('')
      setEnabledDraft(null)
      setSaveError(null)
      setSaveSuccess(
        `저장 완료 — ${next.enabled ? '활성화' : '비활성화'} (key: ${next.key_masked})`
      )
      queryClient.invalidateQueries({ queryKey: ['integration', 'krx-open-api'] })
    },
    onError: (err) => {
      setSaveSuccess(null)
      if (axios.isAxiosError(err)) {
        const status = err.response?.status
        if (status === 422) {
          setSaveError('입력값 검증 실패 — 빈 문자열은 허용되지 않습니다.')
        } else if (status === 500) {
          setSaveError('서버 저장 실패 — 잠시 후 재시도하세요.')
        } else {
          setSaveError(`오류 (${status ?? 'unknown'}) — 잠시 후 재시도하세요.`)
        }
      } else {
        setSaveError('알 수 없는 오류 — 잠시 후 재시도하세요.')
      }
    },
  })

  const handleSave = () => {
    const body: KrxOpenApiUpdateRequest = {}
    if (keyInput.trim()) body.key = keyInput.trim()
    if (baseUrlInput.trim()) body.base_url = baseUrlInput.trim()
    if (enabledDraft !== null) body.enabled = enabledDraft
    updateMutation.mutate(body)
  }

  const currentEnabled = enabledDraft !== null ? enabledDraft : data?.enabled ?? false
  const currentBaseUrl = baseUrlInput || data?.base_url || DEFAULT_BASE_URL
  const currentKeyMasked = data?.key_masked || '****'

  return (
    <div
      data-testid="krx-open-api-card"
      className="bg-white rounded-lg shadow p-6 mt-4"
    >
      <h2 className="text-lg font-semibold mb-2">KRX 정식 OPEN API</h2>
      <p className="text-sm text-gray-600 mb-4">
        한국거래소 데이터 마켓플레이스 (openapi.krx.co.kr) 키 관리. 본 사이클은
        인프라 사전 구성 — 실제 endpoint 호출은 후속 사이클에서 추가됩니다.
      </p>

      {isLoading && (
        <div data-testid="krx-open-api-loading" className="text-sm text-gray-500">
          불러오는 중...
        </div>
      )}

      {isError && (
        <div
          data-testid="krx-open-api-error"
          className="text-sm text-red-600 bg-red-50 border border-red-200 rounded p-2 mb-3"
        >
          설정 조회 실패 — 잠시 후 재시도하세요.
        </div>
      )}

      {data && (
        <div className="space-y-4">
          {/* 현재 상태 표시 */}
          <div className="bg-gray-50 border border-gray-200 rounded p-3">
            <div className="text-xs text-gray-500 mb-1">현재 등록된 키</div>
            <div
              data-testid="krx-open-api-key-masked"
              className="font-mono text-sm text-gray-800"
            >
              {currentKeyMasked}
            </div>
          </div>

          {/* 활성화 토글 */}
          <div className="flex items-center gap-3">
            <label className="text-sm font-medium text-gray-700">활성화</label>
            <button
              type="button"
              data-testid="krx-open-api-toggle"
              onClick={() => setEnabledDraft(!currentEnabled)}
              className={`px-3 py-1 rounded text-sm font-medium ${
                currentEnabled
                  ? 'bg-emerald-100 text-emerald-800 border border-emerald-300'
                  : 'bg-gray-100 text-gray-700 border border-gray-300'
              }`}
            >
              {currentEnabled ? 'ON' : 'OFF'}
            </button>
            {enabledDraft !== null && enabledDraft !== data.enabled && (
              <span className="text-xs text-amber-600">변경 사항 저장 필요</span>
            )}
          </div>

          {/* API key 입력 (type=password 평문 잔존 차단) */}
          <div>
            <label
              htmlFor="krx-open-api-key-input"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              키 입력 (신규 키 등록 시에만 입력)
            </label>
            <input
              id="krx-open-api-key-input"
              data-testid="krx-open-api-key-input"
              type="password"
              autoComplete="new-password"
              value={keyInput}
              onChange={(e) => setKeyInput(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded text-sm font-mono"
              placeholder="비워두면 기존 키 보존"
            />
          </div>

          {/* base URL 입력 */}
          <div>
            <label
              htmlFor="krx-open-api-base-url-input"
              className="block text-sm font-medium text-gray-700 mb-1"
            >
              기본 URL
            </label>
            <input
              id="krx-open-api-base-url-input"
              data-testid="krx-open-api-base-url-input"
              type="text"
              value={baseUrlInput}
              onChange={(e) => setBaseUrlInput(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded text-sm font-mono"
              placeholder={currentBaseUrl}
            />
            <div className="text-xs text-gray-500 mt-1">
              디폴트: {DEFAULT_BASE_URL}
            </div>
          </div>

          {/* 저장 버튼 */}
          <button
            type="button"
            data-testid="krx-open-api-save-button"
            onClick={handleSave}
            disabled={updateMutation.isPending}
            className="px-4 py-2 bg-blue-600 text-white rounded text-sm font-medium hover:bg-blue-700 disabled:bg-gray-400"
          >
            {updateMutation.isPending ? '저장 중...' : '저장'}
          </button>

          {saveSuccess && (
            <div
              data-testid="krx-open-api-save-success"
              className="text-sm text-emerald-700 bg-emerald-50 border border-emerald-200 rounded p-2"
            >
              {saveSuccess}
            </div>
          )}

          {saveError && (
            <div
              data-testid="krx-open-api-save-error"
              className="text-sm text-red-600 bg-red-50 border border-red-200 rounded p-2"
            >
              {saveError}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
