import { useState } from 'react'
import TradeHistoryGrid from '../components/TradeHistoryGrid'
import TradePnLGrid from '../components/TradePnLGrid'

type TabKey = 'orders' | 'pnl'

export default function History() {
  const [tab, setTab] = useState<TabKey>('orders')

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-4">거래 내역</h1>

      <div className="flex gap-1 border-b border-gray-200 mb-4">
        <button
          onClick={() => setTab('orders')}
          className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${
            tab === 'orders'
              ? 'border-blue-600 text-blue-700'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          주문체결내역
        </button>
        <button
          onClick={() => setTab('pnl')}
          className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${
            tab === 'pnl'
              ? 'border-blue-600 text-blue-700'
              : 'border-transparent text-gray-500 hover:text-gray-700'
          }`}
        >
          매매손익
        </button>
      </div>

      {tab === 'orders' ? <TradeHistoryGrid /> : <TradePnLGrid />}
    </div>
  )
}
