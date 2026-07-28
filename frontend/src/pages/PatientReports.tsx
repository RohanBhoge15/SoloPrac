import { useState, useEffect } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { apiClient } from '@/services/api'
import { FileText, Loader2, Receipt, FileBadge, Download, Calendar } from 'lucide-react'

export function PatientReports() {
  const [reports, setReports] = useState<any>({ prescriptions: [], invoices: [], certificates: [] })
  const [loading, setLoading] = useState(true)
  const [reportLayout, setReportLayout] = useState<'clinical' | 'executive' | 'family_friendly'>('clinical')
  const [reportDownloading, setReportDownloading] = useState(false)
  const [patientId, setPatientId] = useState<string>('')

  // Fetch patient ID from profile
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

  // Fetch reports when patientId is available
  useEffect(() => {
    if (!patientId) { setLoading(false); return }
    apiClient.get('/patient/me/reports')
      .then(r => setReports(r.data || { prescriptions: [], invoices: [], certificates: [] }))
      .catch((err) => {
        console.warn('[Reports] Failed to load reports:', err)
      })
      .finally(() => setLoading(false))
  }, [patientId])

  const handleDownloadWeeklyReport = async () => {
    if (!patientId) return
    setReportDownloading(true)
    try {
      const res = await apiClient.get('/patient/me/weekly-report/pdf', {
        params: { layout: reportLayout },
        responseType: 'blob',
      })
      const blob = new Blob([res.data], { type: 'application/pdf' })
      const url = window.URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `weekly-report-${reportLayout}-${new Date().toISOString().slice(0, 10)}.pdf`
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
    } catch (err) {
      console.error('Failed to download weekly report:', err)
      alert('Failed to generate weekly report. Please try again.')
    } finally {
      setReportDownloading(false)
    }
  }

  if (!patientId) return <p className="text-center text-gray-500 py-8">Please login first.</p>
  if (loading) return <div className="text-center py-8"><Loader2 className="h-6 w-6 animate-spin mx-auto" /></div>

  return (
    <div className="space-y-6 animate-in fade-in duration-300">
      <h1 className="text-2xl font-bold text-gray-900 dark:text-white">My Reports</h1>

      {/* Weekly Report Card */}
      <Card className="border-primary-200 dark:border-primary-800 bg-primary-50 dark:bg-primary-900/10">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-sm">
            <Calendar className="h-4 w-4 text-primary-600" />
            Weekly Clinical Report
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Download your weekly clinical summary with diagnoses, medications, vitals, and upcoming appointments.
          </p>
          <div className="flex items-center gap-3 flex-wrap">
            <label className="text-sm text-gray-700 dark:text-gray-300">Layout:</label>
            <select
              value={reportLayout}
              onChange={e => setReportLayout(e.target.value as 'clinical' | 'executive' | 'family_friendly')}
              className="px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-sm"
            >
              <option value="clinical">Clinical (Detailed)</option>
              <option value="executive">Executive (Summary)</option>
              <option value="family_friendly">Family Friendly (Simple)</option>
            </select>
            <Button
              variant="default"
              size="sm"
              onClick={handleDownloadWeeklyReport}
              disabled={reportDownloading}
              className="flex items-center gap-2"
            >
              {reportDownloading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Download className="h-4 w-4" />
              )}
              {reportDownloading ? 'Generating...' : 'Generate & Download PDF'}
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="flex items-center gap-2 text-sm"><FileText className="h-4 w-4" />Prescriptions</CardTitle></CardHeader>
        <CardContent>
          {reports.prescriptions.length === 0 ? <p className="text-sm text-gray-400">No prescriptions yet.</p> : (
            <div className="space-y-2">
              {reports.prescriptions.map((r: any) => (
                <div key={r.id} className="flex items-center justify-between p-2 rounded-lg bg-gray-50 dark:bg-gray-800/50">
                  <span className="text-sm">{new Date(r.created_at).toLocaleDateString()}</span>
                  <div className="flex items-center gap-2">
                    <Badge variant={r.has_pdf ? 'default' : 'secondary'} className="text-xs">{r.has_pdf ? 'PDF' : 'No PDF'}</Badge>
                    {r.has_pdf && (
                      <Button variant="ghost" size="sm" onClick={() => window.open(`/api/v1/patient/me/prescriptions/${r.id}/pdf`, '_blank')}>
                        <Download className="h-3 w-3" />
                      </Button>
                    )}
                  </div>
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
                  <div className="flex items-center gap-2">
                    <Badge variant={i.status === 'paid' ? 'default' : 'secondary'} className="text-xs">{i.status}</Badge>
                    {i.has_pdf && (
                      <Button variant="ghost" size="sm" onClick={() => window.open(`/api/v1/patient/me/invoices/${i.id}/pdf`, '_blank')}>
                        <Download className="h-3 w-3" />
                      </Button>
                    )}
                  </div>
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
                    {c.has_pdf && (
                      <Button variant="ghost" size="sm" onClick={() => window.open(`/api/v1/patient/me/certificates/${c.id}/pdf`, '_blank')}>
                        <Download className="h-3 w-3" />
                      </Button>
                    )}
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