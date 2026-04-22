import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getTradingStatus, startTrading, stopTrading, restartTrading } from '../api/trading'
import ConfirmModal from './ConfirmModal'

export default function ControlPanel() {
  const queryClient = useQueryClient()
  const [modal, setModal] = useState<'start' | 'stop' | 'restart' | null>(null)

  const { data: status, isLoading, isError } = useQuery({
    queryKey: ['tradingStatus'],
    queryFn: getTradingStatus,
    refetchInterval: 5000,
  })

  const startMutation = useMutation({
    mutationFn: startTrading,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tradingStatus'] })
      setModal(null)
    },
  })

  const stopMutation = useMutation({
    mutationFn: stopTrading,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tradingStatus'] })
      setModal(null)
    },
  })

  const restartMutation = useMutation({
    mutationFn: restartTrading,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tradingStatus'] })
      setModal(null)
    },
  })

  if (isLoading) return <div className="p-6 text-gray-500">상태 로딩 중...</div>
  if (isError) return <div className="p-6 text-red-500">서버 연결 끊김</div>

  const isRunning = status?.running ?? false

  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-semibold text-gray-900">구동 관리</h2>
        <div className="flex items-center gap-2">
          <span className={`w-3 h-3 rounded-full ${isRunning ? 'bg-green-500' : 'bg-red-500'}`} />
          <span className="text-sm font-medium text-gray-700">
            {isRunning ? '실행 중' : '정지'}
          </span>
        </div>
      </div>

      {status && (
        <div className="text-sm text-gray-500 mb-4 space-y-1">
          <p>보유 포지션: {status.positions}개</p>
          <p>매수 대기: {status.pending_buys}건</p>
          {status.position_tickers.length > 0 && (
            <p>보유 종목: {status.position_tickers.join(', ')}</p>
          )}
        </div>
      )}

      <div className="flex gap-3">
        <button
          onClick={() => setModal('start')}
          disabled={isRunning}
          className="px-4 py-2 text-sm font-medium text-white bg-green-600 rounded-md hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          시작
        </button>
        <button
          onClick={() => setModal('stop')}
          disabled={!isRunning}
          className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-md hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          정지
        </button>
        <button
          onClick={() => setModal('restart')}
          disabled={!isRunning}
          className="px-4 py-2 text-sm font-medium text-white bg-amber-600 rounded-md hover:bg-amber-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          재기동
        </button>
      </div>

      <ConfirmModal
        open={modal === 'start'}
        title="자동매매 시작"
        message="자동매매를 시작하시겠습니까?"
        onConfirm={() => startMutation.mutate()}
        onCancel={() => setModal(null)}
        loading={startMutation.isPending}
      />
      <ConfirmModal
        open={modal === 'stop'}
        title="자동매매 정지"
        message="정지하시겠습니까? 미체결 주문이 있을 수 있습니다."
        onConfirm={() => stopMutation.mutate()}
        onCancel={() => setModal(null)}
        loading={stopMutation.isPending}
      />
      <ConfirmModal
        open={modal === 'restart'}
        title="자동매매 재기동"
        message="매매를 재기동하시겠습니까? 기존 프로세스를 정지 후 다시 시작합니다."
        onConfirm={() => restartMutation.mutate()}
        onCancel={() => setModal(null)}
        loading={restartMutation.isPending}
      />
    </div>
  )
}
