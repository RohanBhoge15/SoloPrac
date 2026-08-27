'use client'

import { useState, useEffect } from 'react'
import { cn, printPdfViaBlob } from '@/utils/helpers'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Badge } from '@/components/ui/Badge'
import { FileText, Loader2, AlertCircle, Download, Printer, IndianRupee } from 'lucide-react'
import apiClient from '@/services/api'

interface InvoiceUIProps {
  patientId: string
  className?: string
}

export function InvoiceUI({ patientId, className }: InvoiceUIProps) {
  const [consultationFee, setConsultationFee] = useState(0)
  const [medicineCost, setMedicineCost] = useState(0)
  const [paymentMethod, setPaymentMethod] = useState('')
  const [notes, setNotes] = useState('')
  const [generating, setGenerating] = useState(false)
  const [result, setResult] = useState<{ id: string; invoice_number?: string; pdf_path?: string; total?: number } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [minFee, setMinFee] = useState(0)

  // Load doctor settings for min_consultation_fee
  useEffect(() => {
    apiClient.get('/auth/me').then(res => {
      const settings = res.data?.settings || {}
      if (settings.min_consultation_fee) {
        setMinFee(settings.min_consultation_fee)
        setConsultationFee(settings.min_consultation_fee)
      }
    }).catch(() => {})
  }, [])

  const total = consultationFee + medicineCost
  const isValid = consultationFee > 0 && paymentMethod

  const handleCreateInvoice = async () => {
    if (!isValid) return
    setGenerating(true)
    setError(null)
    setResult(null)

    try {
      const response = await apiClient.post(`/patients/${patientId}/invoices`, {
        consultation_fee: consultationFee,
        medicine_cost: medicineCost,
        payment_method: paymentMethod,
        notes,
      })
      setResult(response.data)
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || 'Failed to create invoice')
    } finally {
      setGenerating(false)
    }
  }

  return (
    <Card className={cn('w-full border-2 border-green-200 dark:border-green-800', className)}>
      <CardHeader className="bg-green-50 dark:bg-green-900/10 border-b border-green-200 dark:border-green-800">
        <CardTitle className="flex items-center gap-2 text-lg">
          <FileText className="h-5 w-5 text-green-600" />
          Invoice
        </CardTitle>
      </CardHeader>
      <CardContent className="p-4 space-y-4">
        {/* Consultation Fee */}
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Consultation Fee
          </label>
          <div className="relative">
            <IndianRupee className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
            <Input
              type="number"
              min={0}
              value={consultationFee || ''}
              onChange={e => setConsultationFee(Number(e.target.value) || 0)}
              placeholder={minFee > 0 ? `Min: ₹${minFee}` : '0'}
              className="pl-9"
            />
          </div>
          {minFee > 0 && (
            <p className="text-xs text-gray-400 mt-1">Default: ₹{minFee} (from settings)</p>
          )}
        </div>

        {/* Medicine Cost */}
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Medicine Cost <span className="text-gray-400 font-normal">(optional)</span>
          </label>
          <div className="relative">
            <IndianRupee className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
            <Input
              type="number"
              min={0}
              value={medicineCost || ''}
              onChange={e => setMedicineCost(Number(e.target.value) || 0)}
              placeholder="0"
              className="pl-9"
            />
          </div>
        </div>

        {/* Payment Method */}
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Payment Method
          </label>
          <select
            value={paymentMethod}
            onChange={e => setPaymentMethod(e.target.value)}
            className="w-full px-3 py-2 rounded-md border border-gray-300 dark:border-gray-600 text-sm bg-white dark:bg-gray-800"
          >
            <option value="">Select...</option>
            <option value="cash">Cash</option>
            <option value="upi">UPI</option>
            <option value="card">Card</option>
            <option value="insurance">Insurance</option>
          </select>
        </div>

        {/* Notes */}
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            Notes <span className="text-gray-400 font-normal">(optional)</span>
          </label>
          <Input value={notes} onChange={e => setNotes(e.target.value)} placeholder="Optional notes" />
        </div>

        {/* Total */}
        <div className="flex items-center justify-between pt-2 border-t border-gray-200 dark:border-gray-700">
          <span className="text-sm text-gray-500">Total</span>
          <span className="text-xl font-bold text-green-700 dark:text-green-300">₹{total}</span>
        </div>

        {/* Actions */}
        <div className="flex items-center justify-between pt-2">
          {result?.invoice_number && (
            <div className="flex items-center gap-2">
              <Badge variant="default" className="bg-green-100 text-green-700">#{result.invoice_number}</Badge>
              {result.pdf_path && (
                <>
                  <Button variant="outline" size="sm" onClick={() => window.open(result.pdf_path, '_blank')}>
                    <Download className="h-3 w-3 mr-1" /> PDF
                  </Button>
                  {/* D-7: Print button now actually triggers print (was identical to Download). */}
                  <Button variant="outline" size="sm" onClick={() => result.id && printPdfViaBlob(`/patients/${patientId}/invoices/${result.id}/pdf`)}>
                    <Printer className="h-3 w-3 mr-1" /> Print
                  </Button>
                </>
              )}
            </div>
          )}
          <Button onClick={handleCreateInvoice} disabled={!isValid || generating} className="ml-auto">
            {generating ? (
              <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Generating...</>
            ) : (
              <><FileText className="h-4 w-4 mr-2" /> Generate Invoice</>
            )}
          </Button>
        </div>

        {error && (
          <div className="flex items-center gap-2 p-2 rounded-lg bg-red-50 text-sm text-red-700">
            <AlertCircle className="h-4 w-4" /> {error}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
