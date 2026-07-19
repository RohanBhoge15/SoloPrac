'use client'

import { cn } from '@/utils/helpers'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import {
  Heart,
  Pill,
  Stethoscope,
  Calendar,
  Clock,
  AlertTriangle,
} from 'lucide-react'

interface Vitals {
  bp_systolic?: number
  bp_diastolic?: number
  heart_rate?: number
  weight?: number
  temperature?: number
  spo2?: number
  date?: string
}

interface Medication {
  drug: string
  strength: string
  dose: string
  frequency: string
}

interface ContextPanelProps {
  patient?: {
    name: string
    age: number
    gender: string
    id: string
  }
  vitals?: Vitals | null
  medications?: Medication[]
  diagnoses?: string[]
  nextAppointment?: {
    date: string
    reason: string
  } | null
  alerts?: Array<{
    severity: 'high' | 'medium' | 'low'
    message: string
  }>
  className?: string
}

export function ContextPanel({
  patient,
  vitals,
  medications = [],
  diagnoses = [],
  nextAppointment,
  alerts = [],
  className,
}: ContextPanelProps) {
  if (!patient) {
    return (
      <div className={cn('p-4', className)}>
        <div className="text-center text-gray-400 text-sm py-8">
          <p>Select a patient to see context</p>
        </div>
      </div>
    )
  }

  return (
    <div className={cn('space-y-3', className)}>
      {/* Patient Header */}
      <Card>
        <CardContent className="p-3">
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary-100 dark:bg-primary-900/30">
              <span className="text-xs font-bold text-primary-700 dark:text-primary-300">
                {patient.name.split(' ').map(n => n[0]).join('')}
              </span>
            </div>
            <div className="min-w-0">
              <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                {patient.name}
              </p>
              <p className="text-[10px] text-gray-500">
                {patient.age} yrs · {patient.gender}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Alerts */}
      {alerts.length > 0 && (
        <Card>
          <CardContent className="p-3 space-y-1.5">
            {alerts.map((alert, i) => (
              <div
                key={i}
                className={cn(
                  'flex items-start gap-2 p-2 rounded-lg text-xs',
                  alert.severity === 'high' && 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300',
                  alert.severity === 'medium' && 'bg-yellow-50 dark:bg-yellow-900/20 text-yellow-700 dark:text-yellow-300',
                  alert.severity === 'low' && 'bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300',
                )}
              >
                <AlertTriangle className="h-3 w-3 shrink-0 mt-0.5" />
                <span>{alert.message}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {/* Vitals */}
      {vitals && (
        <Card>
          <CardHeader className="p-3 pb-0">
            <CardTitle className="flex items-center gap-1.5 text-xs font-semibold">
              <Heart className="h-3 w-3 text-red-500" />
              Current Vitals
              {vitals.date && (
                <span className="text-[9px] text-gray-400 font-normal ml-auto">{vitals.date}</span>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-3 pt-2">
            <div className="grid grid-cols-2 gap-1.5 text-xs">
              {vitals.bp_systolic && vitals.bp_diastolic && (
                <div className="p-1.5 rounded bg-gray-50 dark:bg-gray-800/50">
                  <span className="text-gray-500">BP</span>
                  <p className="font-medium">{vitals.bp_systolic}/{vitals.bp_diastolic}</p>
                </div>
              )}
              {vitals.heart_rate && (
                <div className="p-1.5 rounded bg-gray-50 dark:bg-gray-800/50">
                  <span className="text-gray-500">HR</span>
                  <p className="font-medium">{vitals.heart_rate} <span className="font-normal text-gray-400">bpm</span></p>
                </div>
              )}
              {vitals.weight && (
                <div className="p-1.5 rounded bg-gray-50 dark:bg-gray-800/50">
                  <span className="text-gray-500">Weight</span>
                  <p className="font-medium">{vitals.weight} <span className="font-normal text-gray-400">kg</span></p>
                </div>
              )}
              {vitals.spo2 && (
                <div className="p-1.5 rounded bg-gray-50 dark:bg-gray-800/50">
                  <span className="text-gray-500">SpO2</span>
                  <p className="font-medium">{vitals.spo2}%</p>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Diagnoses */}
      {diagnoses.length > 0 && (
        <Card>
          <CardHeader className="p-3 pb-0">
            <CardTitle className="flex items-center gap-1.5 text-xs font-semibold">
              <Stethoscope className="h-3 w-3 text-primary-500" />
              Diagnoses
            </CardTitle>
          </CardHeader>
          <CardContent className="p-3 pt-2">
            <div className="flex flex-wrap gap-1">
              {diagnoses.map((d, i) => (
                <Badge key={i} variant="secondary" className="text-[10px] px-1.5 py-0.5">
                  {d.length > 20 ? d.slice(0, 20) + '...' : d}
                </Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Medications */}
      {medications.length > 0 && (
        <Card>
          <CardHeader className="p-3 pb-0">
            <CardTitle className="flex items-center gap-1.5 text-xs font-semibold">
              <Pill className="h-3 w-3 text-green-500" />
              Active Medications
            </CardTitle>
          </CardHeader>
          <CardContent className="p-3 pt-2">
            <div className="space-y-1.5">
              {medications.slice(0, 4).map((med, i) => (
                <div key={i} className="text-[11px]">
                  <p className="font-medium text-gray-900 dark:text-white">{med.drug} {med.strength}</p>
                  <p className="text-gray-500">{med.dose} · {med.frequency}</p>
                </div>
              ))}
              {medications.length > 4 && (
                <p className="text-[10px] text-gray-400">+{medications.length - 4} more</p>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Next Appointment */}
      {nextAppointment && (
        <Card>
          <CardHeader className="p-3 pb-0">
            <CardTitle className="flex items-center gap-1.5 text-xs font-semibold">
              <Calendar className="h-3 w-3 text-blue-500" />
              Next Appointment
            </CardTitle>
          </CardHeader>
          <CardContent className="p-3 pt-2">
            <div className="flex items-center gap-2 text-xs">
              <Clock className="h-3 w-3 text-gray-400" />
              <span className="font-medium">{nextAppointment.date}</span>
            </div>
            <p className="text-[11px] text-gray-500 mt-0.5">{nextAppointment.reason}</p>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
