'use client'

import { useState } from 'react'
import { cn } from '@/utils/helpers'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { CheckCircle, XCircle, AlertTriangle, CalendarDays, Clock } from 'lucide-react'

interface ProposedMove {
  id: string
  appointment_id: string
  patient_name: string
  current_start: string
  proposed_start: string
  proposed_end: string
  reason: string
  confidence: number
  risk_level: 'low' | 'medium' | 'high'
}

interface ApprovalCardProps {
  title: string
  message: string
  moves: ProposedMove[]
  onApproveAll: () => void
  onReview: () => void
  onCancel: () => void
  loading?: boolean
  // D-4: per-row and bulk callbacks. When omitted, the corresponding UI is hidden
  // instead of rendering interactive-looking but dead controls.
  onApproveOne?: (moveId: string) => void
  onRejectOne?: (moveId: string) => void
  onApproveSelected?: (moveIds: string[]) => void
  onRejectSelected?: (moveIds: string[]) => void
}

function fmt(d: string) {
  return new Date(d).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

export function ApprovalCard({
  title,
  message,
  moves,
  onApproveAll,
  onReview,
  onCancel,
  loading,
  onApproveOne,
  onRejectOne,
  onApproveSelected,
  onRejectSelected,
}: ApprovalCardProps) {
  const [expanded, setExpanded] = useState(false)
  const [selected, setSelected] = useState<Record<string, boolean>>({})

  // D-4: only show per-row Accept/Reject buttons when at least one callback is wired.
  const showRowActions = Boolean(onApproveOne || onRejectOne)
  // D-4: only show selection checkboxes when at least one bulk callback is wired,
  // otherwise selection is a lie (no action can consume it).
  const showSelection = Boolean(onApproveSelected || onRejectSelected)

  const toggleOne = (id: string) => {
    setSelected(prev => ({ ...prev, [id]: !prev[id] }))
  }

  const toggleAll = () => {
    const anySelected = Object.values(selected).some(Boolean)
    const newSelected = moves.reduce((acc, m) => ({ ...acc, [m.appointment_id]: !anySelected }), {})
    setSelected(newSelected)
  }

  const allSelected = moves.length > 0 && Object.values(selected).every(Boolean)
  const selectedCount = Object.values(selected).filter(Boolean).length

  return (
    <Card className="border-2 border-yellow-200 dark:border-yellow-800 bg-yellow-50 dark:bg-yellow-900/10">
      <CardHeader className="bg-yellow-50 dark:bg-yellow-900/20 border-b border-yellow-200 dark:border-yellow-800">
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-lg bg-yellow-100 dark:bg-yellow-900/30">
              <AlertTriangle className="h-5 w-5 text-yellow-600 dark:text-yellow-400" />
            </div>
            <div>
              <CardTitle className="text-lg">{title}</CardTitle>
              <p className="text-sm text-yellow-700 dark:text-yellow-300 mt-0.5">{message}</p>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <Badge variant={moves.length > 0 ? 'default' : 'secondary'} className="text-xs">
              {moves.length} moves
            </Badge>
            <Button variant="ghost" size="sm" onClick={() => setExpanded(!expanded)}>
              {expanded ? 'Less' : 'All'}
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3 pt-3">
        {/* D-4: hide the "Select all" bar entirely when no bulk callback is provided. */}
        {expanded && moves.length > 0 && showSelection && (
          <div className="flex items-center gap-3 px-2 py-1.5 bg-gray-50 dark:bg-gray-800/50 rounded-lg text-xs text-gray-500">
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input type="checkbox" checked={allSelected} onChange={toggleAll} className="accent-primary-600" />
              <span>Select all ({moves.length})</span>
            </label>
            {selectedCount > 0 && (
              <span className="ml-auto text-primary-600 font-medium">{selectedCount} selected</span>
            )}
          </div>
        )}
        <div className="space-y-2 max-h-80 overflow-y-auto">
          {moves.map((move) => (
            <div
              key={move.appointment_id}
              className={cn(
                'p-3 rounded-lg border transition-colors',
                selected[move.appointment_id]
                  ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-300'
                  : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700'
              )}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    {/* D-4: only render selection checkbox when a bulk action can consume it. */}
                    {expanded && showSelection && (
                      <input
                        type="checkbox"
                        checked={selected[move.appointment_id] || false}
                        onChange={() => toggleOne(move.appointment_id)}
                        className="accent-primary-600"
                      />
                    )}
                    <span className="font-medium text-sm text-gray-900 dark:text-white truncate">
                      {move.patient_name}
                    </span>
                    <Badge variant={move.risk_level === 'high' ? 'destructive' : move.risk_level === 'medium' ? 'secondary' : 'default'} className="text-[10px]">
                      {move.risk_level}
                    </Badge>
                    <Badge variant="outline" className="text-[10px]">
                      {(move.confidence * 100).toFixed(0)}%
                    </Badge>
                  </div>
                  <div className="flex items-center gap-3 text-xs text-gray-500 dark:text-gray-400">
                    <span className="flex items-center gap-1">
                      <CalendarDays className="h-3 w-3" />
                      {fmt(move.current_start)}
                    </span>
                    <Clock className="h-3 w-3" />
                    <span>{fmt(move.proposed_start)}</span>
                  </div>
                </div>
                {/* D-4: hide per-row buttons entirely when no handler is wired (were dead before). */}
                {showRowActions && (
                  <div className="flex items-center gap-1 shrink-0">
                    {onApproveOne && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="text-green-600 hover:bg-green-50"
                        title="Accept"
                        onClick={() => onApproveOne(move.appointment_id)}
                        disabled={loading}
                      >
                        <CheckCircle className="h-4 w-4" />
                      </Button>
                    )}
                    {onRejectOne && (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="text-red-600 hover:bg-red-50"
                        title="Reject"
                        onClick={() => onRejectOne(move.appointment_id)}
                        disabled={loading}
                      >
                        <XCircle className="h-4 w-4" />
                      </Button>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
        <div className="flex items-center justify-between pt-2 border-t border-gray-200 dark:border-gray-700">
          <span className="text-xs text-gray-500">
            {showSelection
              ? (selectedCount > 0 ? `${selectedCount} of ${moves.length} selected` : 'Select moves to manage')
              : `${moves.length} pending`}
          </span>
          <div className="flex items-center gap-2">
            {/* D-4: bulk action buttons — only rendered when there IS a selection AND a handler. */}
            {showSelection && selectedCount > 0 && onApproveSelected && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => onApproveSelected(Object.keys(selected).filter(id => selected[id]))}
                disabled={loading}
                className="text-green-700 border-green-300 hover:bg-green-50"
              >
                Approve selected ({selectedCount})
              </Button>
            )}
            {showSelection && selectedCount > 0 && onRejectSelected && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => onRejectSelected(Object.keys(selected).filter(id => selected[id]))}
                disabled={loading}
                className="text-red-700 border-red-300 hover:bg-red-50"
              >
                Reject selected ({selectedCount})
              </Button>
            )}
            <Button variant="outline" size="sm" onClick={onCancel} disabled={loading}>Cancel All</Button>
            <Button variant="outline" size="sm" onClick={onReview} disabled={loading}>Review</Button>
            <Button size="sm" onClick={onApproveAll} disabled={loading || moves.length === 0}>
              Approve All ({moves.length})
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
