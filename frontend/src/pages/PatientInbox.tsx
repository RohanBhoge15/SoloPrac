import { useState, useEffect } from 'react'
import { Card, CardContent } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { apiClient } from '@/services/api'
import { toast } from '@/components/ui/Toast'
import { openPdfViaBlob } from '@/utils/helpers'
import { Loader2, CheckCircle, Clock } from 'lucide-react'
import { usePatientWebSocket } from '@/hooks/useWebSocket'

function cn(...classes: any[]) { return classes.filter(Boolean).join(' ') }

// Map a notification's resource_type to the patient-portal PDF path. The
// notification's stored pdf_url is the DOCTOR endpoint (/patients/.../pdf),
// which rejects patient auth — so patients must use the /patient/me/... routes.
const PATIENT_DOC_PDF: Record<string, (id: string) => string> = {
  prescription: (id) => `/patient/me/prescriptions/${id}/pdf`,
  invoice: (id) => `/patient/me/invoices/${id}/pdf`,
  certificate: (id) => `/patient/me/certificates/${id}/pdf`,
}

function patientDocPath(meta: any): string | null {
  if (meta?.resource_type && meta?.resource_id && PATIENT_DOC_PDF[meta.resource_type]) {
    return PATIENT_DOC_PDF[meta.resource_type](meta.resource_id)
  }
  return null
}

export function PatientInbox() {
  const [notifications, setNotifications] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [unreadCount, setUnreadCount] = useState(0)
  const [patientId, setPatientId] = useState<string>('')
  const { isConnected: wsConnected, lastEvent } = usePatientWebSocket(patientId)

  // Fetch patient ID from profile endpoint
  useEffect(() => {
    apiClient.get('/patient/me/profile')
      .then(res => {
        if (res.data?.user_id) {
          setPatientId(res.data.user_id)
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  // Fetch notifications when patientId is available
  useEffect(() => {
    if (!patientId) { setLoading(false); return }
    apiClient.get('/patient/me/inbox', { params: { limit: 20 } })
      .then(r => {
        setNotifications(r.data || [])
        setUnreadCount((r.data || []).filter((n: any) => !n.read).length)
      })
      .catch((err) => {
        console.warn('[Inbox] Failed to load notifications:', err)
      })
      .finally(() => setLoading(false))
  }, [patientId])

  // Handle real-time notifications from WebSocket
  useEffect(() => {
    if (lastEvent?.type === 'notification' && lastEvent.data) {
      const newNotif = lastEvent.data
      setNotifications(prev => [newNotif, ...prev.slice(0, 19)])
      if (!newNotif.read) setUnreadCount(prev => prev + 1)
    }
  }, [lastEvent])

  const markAsRead = async (id: string) => {
    try {
      await apiClient.patch(`/patient/me/inbox/${id}/read`)
    } catch (err) {
      // R-8: surface mark-as-read failures so the user knows the server didn't
      // record the change (the local optimistic update below will drift).
      console.error('[Inbox] mark-as-read failed:', err)
      toast.error('Failed to mark notification as read')
    }
    setNotifications(prev => prev.map(n => n.id === id ? { ...n, read: true } : n))
    setUnreadCount(prev => Math.max(0, prev - 1))
  }

  if (!patientId) return <p className="text-center text-gray-500 py-8">Please login first.</p>
  if (loading) return <div className="text-center py-8"><Loader2 className="h-6 w-6 animate-spin mx-auto" /></div>

  return (
    <div className="space-y-4 animate-in fade-in duration-300">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-strong-fg">Inbox</h1>
        <div className="flex items-center gap-2">
          {unreadCount > 0 && <Badge className="bg-blue-500 text-white">{unreadCount} unread</Badge>}
          <span className={cn(wsConnected ? 'text-green-600' : 'text-red-600')}>
            {wsConnected ? '🟢 Live' : '🔴 Offline'}
          </span>
        </div>
      </div>
      {notifications.length === 0 ? <p className="text-gray-400 text-center py-8">No notifications yet.</p> : (
        notifications.map((n: any) => (
          <Card key={n.id} className={cn(!n.read && 'border-blue-300 dark:border-blue-700 bg-blue-50 dark:bg-blue-900/10')}>
            <CardContent className="p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-medium text-sm text-strong-fg">{n.subject}</span>
                    {!n.read && <Badge className="bg-blue-500 text-white text-[10px]">New</Badge>}
                    {n.doctor && (
                      <Badge variant="outline" className="text-[10px] text-muted-fg">
                        Dr. {n.doctor.name} {n.doctor.speciality ? `· ${n.doctor.speciality}` : ''} {n.doctor.clinic_name ? `(${n.doctor.clinic_name})` : ''}
                      </Badge>
                    )}
                  </div>
                  <p className="text-sm text-muted-fg">{n.body}</p>
                  <p className="text-xs text-gray-400 mt-1 flex items-center gap-1"><Clock className="h-3 w-3" />{new Date(n.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</p>
                  {n.meta && (patientDocPath(n.meta) || n.meta.pdf_url) && (
                    <a
                      href={patientDocPath(n.meta) || n.meta.pdf_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(e) => {
                        const p = patientDocPath(n.meta)
                        if (p) {
                          e.preventDefault()
                          openPdfViaBlob(p).catch(() => toast.error('Failed to open document'))
                        }
                      }}
                      className="text-xs text-primary-600 dark:text-primary-400 hover:underline mt-2 inline-block"
                    >
                      View document →
                    </a>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant="outline" className="text-[10px]">{n.kind}</Badge>
                  {!n.read && <button onClick={() => markAsRead(n.id)} className="p-1 text-gray-400 hover:text-primary-600" title="Mark as read"><CheckCircle className="h-4 w-4" /></button>}
                </div>
              </div>
            </CardContent>
          </Card>
        ))
      )}
    </div>
  )
}
