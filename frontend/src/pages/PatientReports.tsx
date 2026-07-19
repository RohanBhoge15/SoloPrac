import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { apiClient } from '@/services/api'
import { FileText, Loader2, Receipt, FileBadge } from 'lucide-react'

export function PatientReports() {
  const [reports, setReports] = useState<any>({ prescriptions: [], invoices: [], certificates: [] })
  const [loading, setLoading] = useState(true)
  const patientId = localStorage.getItem('patient_id') || ''

  useEffect(() => {
    if (!patientId) { setLoading(false); return }
    apiClient.get('/api/patient/me/reports', { params: { patient_id: patientId } })
      .then(r => setReports(r.data || { prescriptions: [], invoices: [], certificates: [] }))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [patientId])

  if (!patientId) return <p className="text-center text-gray-500 py-8">Please login first.</p>
  if (loading) return <div className="text-center py-8"><Loader2 className="h-6 w-6 animate-spin mx-auto" /></div>

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white">My Reports</h1>

      <Card>
        <CardHeader><CardTitle className="flex items-center gap-2 text-sm"><FileText className="h-4 w-4" />Prescriptions</CardTitle></CardHeader>
        <CardContent>
          {reports.prescriptions.length === 0 ? <p className="text-sm text-gray-400">No prescriptions yet.</p> : (
            <div className="space-y-2">
              {reports.prescriptions.map((r: any) => (
                <div key={r.id} className="flex items-center justify-between p-2 rounded-lg bg-gray-50 dark:bg-gray-800/50">
                  <span className="text-sm">{new Date(r.created_at).toLocaleDateString()}</span>
                  <Badge variant={r.has_pdf ? 'default' : 'secondary'} className="text-xs">{r.has_pdf ? 'PDF Available' : 'No PDF'}</Badge>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="flex items-center gap-2 text-sm"><Receipt className="h-4 w-4" />Invoices</CardTitle></CardHeader>
        <CardContent>
          {reports.invoices.length === 0 ? <p className="text-sm text-gray-400">No invoices yet.</p> : (
            <div className="space-y-2">
              {reports.invoices.map((i: any) => (
                <div key={i.id} className="flex items-center justify-between p-2 rounded-lg bg-gray-50 dark:bg-gray-800/50">
                  <div>
                    <span className="text-sm font-medium">{i.invoice_number}</span>
                    <span className="text-sm ml-3">₹{i.total}</span>
                  </div>
                  <Badge variant={i.status === 'paid' ? 'default' : 'secondary'} className="text-xs">{i.status}</Badge>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="flex items-center gap-2 text-sm"><FileBadge className="h-4 w-4" />Certificates</CardTitle></CardHeader>
        <CardContent>
          {reports.certificates.length === 0 ? <p className="text-sm text-gray-400">No certificates yet.</p> : (
            <div className="space-y-2">
              {reports.certificates.map((c: any) => (
                <div key={c.id} className="flex items-center justify-between p-2 rounded-lg bg-gray-50 dark:bg-gray-800/50">
                  <span className="text-sm">{c.cert_type.replace('_', ' ')}</span>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-400">{c.verification_code}</span>
                    <Badge variant={c.has_pdf ? 'default' : 'secondary'} className="text-xs">{c.has_pdf ? 'PDF' : 'N/A'}</Badge>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
