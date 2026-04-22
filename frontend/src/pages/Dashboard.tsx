import ControlPanel from '../components/ControlPanel'
import ScanMonitor from '../components/ScanMonitor'
import OrderMonitor from '../components/OrderMonitor'
import PerformanceCard from '../components/PerformanceCard'
import ProfitChart from '../components/ProfitChart'
import BalanceTable from '../components/BalanceTable'
import LogViewer from '../components/LogViewer'

export default function Dashboard() {
  return (
    <div className="space-y-6">
      <ControlPanel />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <ScanMonitor />
        <OrderMonitor />
      </div>
      <PerformanceCard />
      <ProfitChart />
      <BalanceTable />
      <LogViewer />
    </div>
  )
}
