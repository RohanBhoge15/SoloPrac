import { useState } from 'react'
import { Badge } from '@/components/ui/Badge'
import { AlertTriangle, Activity, Loader2, Bell, X } from 'lucide-react'
import { cn } from '@/utils/helpers'
import type { RiskAlert } from '@/types'

export function RiskAlertsPanel({ alerts, loading }: { alerts: RiskAlert[]; loading?: boolean }) {
  const [dismissed, setDismissed] = useState<Set<string>>(new Set())
  const [expanded, setExpanded] = useState(false)

  const visibleAlerts = alerts.filter(a => !dismissed.has(a.id))
  const criticalCount = visibleAlerts.filter(a => a.severity > 0.7).length

  if (loading) {
    return (
      <div className="flex items-center gap-2 p-3 text-sm text-gray-500">
        <Loader2 className="h-4 w-4 animate-spin" />
        Analyzing trajectories...
      </div>
    )
  }

  if (visibleAlerts.length === 0) return null

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="relative">
            <Bell className="h-5 w-5 text-gray-600" />
            {criticalCount > 0 && (
              <span className="absolute -top-1 -right-1 h-3 w-3 rounded-full bg-red-500" />
            )}
          </div>
          <span className="text-sm font-medium text-gray-900 dark:text-white">
            Risk Alerts
          </span>
          <Badge className={cn(
            criticalCount > 0 ? 'bg-red-500 text-white' : 'bg-yellow-500 text-white'
          )}>
            {visibleAlerts.length}
          </Badge>
        </div>
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-xs text-primary-600 hover:text-primary-700"
        >
          {expanded ? 'Collapse' : 'View all'}
        </button>
      </div>

      {expanded && visibleAlerts.map((alert, i) => (
        <div key={alert.patient_id + i} className={cn(
          'p-2 rounded-lg border text-sm',
          alert.severity > 0.7
            ? 'bg-red-50 border-red-200 dark:bg-red-900/10 dark:border-red-800'
            : alert.severity > 0.4
              ? 'bg-yellow-50 border-yellow-200 dark:bg-yellow-900/10 dark:border-yellow-800'
              : 'bg-gray-50 border-gray-200 dark:bg-gray-800/30'
        )}>
          <div className="flex items-start justify-between gap-2">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-0.5">
                {alert.kind === 'trajectory_drift' ? (
                  <Activity className="h-3 w-3 text-yellow-600 shrink-0" />
                ) : (
                  <AlertTriangle className="h-3 w-3 text-red-600 shrink-0" />
                )}
                <span className="font-medium text-xs truncate">
                  {alert.patient_name || `Patient ${alert.patient_id.slice(0, 8)}`}
                </span>
                <Badge className={cn(
                  'text-[10px]',
                  alert.severity > 0.7 ? 'bg-red-500 text-white' : 'bg-yellow-500 text-white'
                )}>
                  {(alert.severity * 100).toFixed(0)}%
                </Badge>
              </div>
              <p className="text-xs text-gray-600 dark:text-gray-400">{alert.message}</p>
            </div>
            <button
              onClick={() => setDismissed(prev => new Set([...prev, alert.patient_id]))}
              className="p-0.5 text-gray-400 hover:text-gray-600 shrink-0"
            >
              <X className="h-3 w-3" />
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}

interface RiskBadgeProps {
  count: number
  critical: number
}

export function RiskBadge({ count, critical }: RiskBadgeProps) {
  if (count === 0) return null
  return (
    <div className="relative inline-flex items-center">
      <AlertTriangle className={cn(
        'h-5 w-5',
        critical > 0 ? 'text-red-500' : 'text-yellow-500'
      )} />
      <span className={cn(
        'absolute -top-1.5 -right-1.5 h-4 w-4 rounded-full text-[8px] font-bold text-white flex items-center justify-center',
        critical > 0 ? 'bg-red-500' : 'bg-yellow-500'
      )}>
        {count > 9 ? '9+' : count}
      </span>
    </div>
  )
}
