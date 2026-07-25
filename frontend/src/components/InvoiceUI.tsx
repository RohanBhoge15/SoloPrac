'use client'

import { useState } from 'react'
import { cn } from '@/utils/helpers'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Badge } from '@/components/ui/Badge'
import { Plus, X, Printer, Download, FileText, Loader2, AlertCircle } from 'lucide-react'
import apiClient from '@/services/api'

interface InvoiceItem {
  description: string
  qty: number
  rate: number
  amount: number
}

interface InvoiceUIProps {
  patientId: string
  patientName: string
  className?: string
}

export function InvoiceUI({ patientId, patientName, className }: InvoiceUIProps) {
  const [items, setItems] = useState<InvoiceItem[]>([
    { description: '', qty: 1, rate: 0, amount: 0 },
  ])
  const [taxRate, setTaxRate] = useState(0)
  const [status, setStatus] = useState('pending')
  const [notes, setNotes] = useState('')
  const [generating, setGenerating] = useState(false)
  const [result, setResult] = useState<{ id: string; invoice_number?: string; pdf_path?: string } | null>(null)
  const [error, setError] = useState<string | null>(null)

  const addItem = () => setItems([...items, { description: '', qty: 1, rate: 0, amount: 0 }])
  const removeItem = (idx: number) => items.length > 1 && setItems(items.filter((_, i) => i !== idx))
  const updateItem = (idx: number, field: keyof InvoiceItem, value: string | number) => {
    setItems(items.map((item, i) => i === idx ? { ...item, [field]: value } : item))
    if (field === 'qty' || field === 'rate') {
      const qty = field === 'qty' ? Number(value) : items[idx].qty
      const rate = field === 'rate' ? Number(value) : items[idx].rate
      setItems(items.map((item, i) => i === idx ? { ...item, [field]: value, amount: qty * rate } : item))
    }
  }

  const subtotal = items.reduce((sum, item) => sum + (item.amount || 0), 0)
  const tax = Math.round(subtotal * taxRate / 100)
  const total = subtotal + tax

  const isValid = items.some(item => item.description.trim() && item.amount > 0)

  const handleCreateInvoice = async () => {
    if (!isValid) return
    setGenerating(true)
    setError(null)
    setResult(null)

    try {
      const response = await apiClient.post(`/patients/${patientId}/invoices`, {
        patient_name: patientName,
        items: items.filter(i => i.description.trim()),
        tax_rate: taxRate,
        status,
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
          Invoice Generator
        </CardTitle>
      </CardHeader>
      <CardContent className="p-4 space-y-4">
        <div className="flex items-center gap-4">
          <select value={status} onChange={e => setStatus(e.target.value)} className="px-3 py-1.5 rounded-md border border-gray-300 dark:border-gray-600 text-sm bg-white dark:bg-gray-800">
            <option value="pending">Pending</option>
            <option value="paid">Paid</option>
            <option value="cancelled">Cancelled</option>
          </select>
          <label className="text-sm text-gray-500 dark:text-gray-400">Tax Rate:</label>
          <select value={taxRate} onChange={e => setTaxRate(Number(e.target.value))} className="ml-1 px-2 py-1.5 rounded-md border border-gray-300 dark:border-gray-600 text-sm bg-white dark:bg-gray-800">
            <option value={0}>0%</option>
            <option value={5}>5%</option>
            <option value={12}>12%</option>
            <option value={18}>18%</option>
            <option value={28}>28%</option>
          </select>
        </div>

        <div className="space-y-2">
          <div className="flex items-center gap-2 px-2 py-1 text-xs font-medium text-gray-500 bg-gray-50 dark:bg-gray-800 rounded-t-lg">
            <div className="w-4">#</div>
            <div className="flex-1 min-w-[150px]">Description</div>
            <div className="w-16 text-right">Qty</div>
            <div className="w-24 text-right">Rate</div>
            <div className="w-24 text-right">Amount</div>
            <div className="w-8"></div>
          </div>
          {items.map((item, idx) => (
            <div key={idx} className="flex items-center gap-2 px-2 py-1.5 rounded-lg bg-gray-50 dark:bg-gray-800/50">
              <span className="w-4 text-xs text-gray-500">{idx + 1}</span>
              <Input value={item.description} onChange={e => updateItem(idx, 'description', e.target.value)} placeholder="Description" className="flex-1 min-w-[150px] text-sm" />
              <Input type="number" min={1} value={item.qty} onChange={e => updateItem(idx, 'qty', Number(e.target.value))} className="w-16 text-sm text-right" />
              <Input type="number" step="0.01" min={0} value={item.rate} onChange={e => updateItem(idx, 'rate', Number(e.target.value))} className="w-24 text-sm text-right" />
              <Input type="number" step="0.01" min={0} value={item.amount} onChange={e => updateItem(idx, 'amount', Number(e.target.value))} className="w-24 text-sm text-right font-medium" readOnly />
              {items.length > 1 && (
                <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => removeItem(idx)}>
                  <X className="h-3 w-3" />
                </Button>
              )}
            </div>
          ))}
          <Button variant="ghost" size="sm" onClick={addItem} className="w-full justify-start text-green-600 dark:text-green-400">
            <Plus className="h-3.5 w-3.5 mr-1" /> Add Line Item
          </Button>
        </div>

        <div className="flex items-center justify-between pt-2 border-t border-gray-200 dark:border-gray-700">
          <div className="text-sm text-gray-500 dark:text-gray-400">Subtotal: <span className="font-medium text-gray-900 dark:text-white">₹{subtotal.toFixed(2)}</span></div>
          <div className="text-sm text-gray-500 dark:text-gray-400">Tax ({taxRate}%): <span className="font-medium text-gray-900 dark:text-white">₹{tax.toFixed(2)}</span></div>
          <div className="text-lg font-bold text-green-700 dark:text-green-300">Total: ₹{total.toFixed(2)}</div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Notes</label>
          <Input value={notes} onChange={e => setNotes(e.target.value)} placeholder="Optional notes" />
        </div>

        <div className="flex items-center justify-between pt-2">
          {result?.invoice_number && (
            <div className="flex items-center gap-2">
              <Badge variant="default" className="bg-green-100 text-green-700">Invoice #{result.invoice_number}</Badge>
              <Button variant="outline" size="sm" onClick={() => window.open(result.pdf_path, '_blank')}>
                <Download className="h-3 w-3 mr-1" /> Download
              </Button>
              <Button variant="outline" size="sm" onClick={() => window.open(result.pdf_path, '_blank')}>
                <Printer className="h-3 w-3 mr-1" /> Print
              </Button>
            </div>
          )}
          <Button onClick={handleCreateInvoice} disabled={!isValid || generating} className="ml-auto">
            {generating ? <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Generating...</> : <><FileText className="h-4 w-4 mr-2" /> Generate Invoice</>}
          </Button>
        </div>

        {error && <div className="flex items-center gap-2 p-2 rounded-lg bg-red-50 text-sm text-red-700"><AlertCircle className="h-4 w-4" /> {error}</div>}
      </CardContent>
    </Card>
  )
}