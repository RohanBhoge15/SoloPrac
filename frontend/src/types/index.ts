// Type definitions for SoloPrac API

export interface Doctor {
  id: string
  email: string
  name: string
  speciality: string
  clinic_name?: string
  clinic_address?: string
  phone?: string
  registration_number?: string
  settings: DoctorSettings
  created_at: string
}

export interface DoctorSettings {
  notification_preferences: Record<string, NotificationPreference>
  patient_booking_enabled: boolean
  auto_confirm_booking: boolean
  max_future_booking_days: number
  working_hours_json: Record<string, string[][]>
  buffer_minutes_between_consults: number
  default_consult_duration: number
  auto_email_on_change: boolean
  patient_preference_decay_days: number
}

export interface NotificationPreference {
  enabled: boolean
  hours_before?: number
  channels: ('in_app' | 'email' | 'sms')[]
}

export interface Patient {
  id: string
  doctor_id: string
  head_version_id?: string
  created_at: string
  updated_at: string
  head_version?: PatientVersion
}

export interface PatientVersion {
  id: string
  patient_id: string
  doctor_id: string
  parent_version_id?: string
  version_number: number
  state_jsonb: PatientState
  version_hash: string
  author: string
  edit_type: 'manual' | 'voice' | 'ocr' | 'ai_suggestion' | 'revert'
  summary?: string
  tags: string[]
  clinical_significance?: number
  image_comparison?: ImageComparison
  timestamp: string
}

export interface PatientState {
  demographics?: {
    name?: string
    age?: number
    gender?: string
    phone?: string
    email?: string
    address?: string
    dob?: string
    emergency_contact?: string
  }
  clinical?: {
    diagnoses?: string[]
    medications?: Medication[]
    allergies?: string[]
    vitals?: Vitals[]
    investigations?: Investigation[]
  }
  administrative?: {
    insurance?: string
    referral_source?: string
    notes?: string
  }
}

export interface Medication {
  drug: string
  strength: string
  dose: string
  frequency: string
  route: string
  duration: string
  instructions?: string
  warnings?: string[]
}

export interface Vitals {
  date: string
  bp_systolic?: number
  bp_diastolic?: number
  heart_rate?: number
  temperature?: number
  weight?: number
  height?: number
  bmi?: number
  spo2?: number
}

export interface Investigation {
  name: string
  date: string
  result?: string
  reference_range?: string
  status: 'pending' | 'completed' | 'abnormal'
}

export interface ImageComparison {
  matched_version_id: string
  area_change_pct: number
  overlay_path: string
  edge_convergence_score?: number
  color_shift_score?: number
}

export interface PatientVersionDiff {
  added: Record<string, unknown>
  removed: Record<string, unknown>
  modified: Record<string, { from: unknown; to: unknown }>
}

export interface Appointment {
  id: string
  doctor_id: string
  patient_id: string
  patient_name?: string
  start_at: string
  end_at: string
  reason?: string
  status: 'scheduled' | 'done' | 'cancelled' | 'moved'
  source: 'manual' | 'voice' | 'agent' | 'patient_portal'
  notified: boolean
  created_at: string
}

export interface PrescriptionBox {
  id: string
  version_id: string
  doctor_id: string
  rx_jsonb: PrescriptionData
  pdf_path?: string
  created_at: string
}

export interface PrescriptionData {
  patient_id: string
  issued_at: string
  doctor_id: string
  diagnosis_short: string
  medications: Medication[]
  investigations: string[]
  lifestyle: string[]
  follow_up: { in_days: number; mode: string }
  doctor_notes?: string
  ai_disclaimer_acknowledged: boolean
}

export interface Invoice {
  id: string
  patient_id: string
  doctor_id: string
  appointment_id?: string
  invoice_number: string
  items: InvoiceItem[]
  subtotal: number
  tax: number
  total: number
  status: 'pending' | 'paid' | 'cancelled'
  payment_method?: string
  notes?: string
  generated_at: string
  paid_at?: string
  pdf_path?: string
}

export interface InvoiceItem {
  description: string
  qty: number
  rate: number
  amount: number
}

export interface Certificate {
  id: string
  patient_id: string
  doctor_id: string
  cert_type: 'sick_leave' | 'fitness' | 'school' | 'disability' | 'other'
  cert_jsonb: Record<string, unknown>
  pdf_path?: string
  verification_code: string
  issued_at: string
}

export interface PatientNotification {
  id: string
  patient_id: string
  doctor_id: string
  kind: string
  subject: string
  body: string
  channel: ('in_app' | 'email' | 'sms')[]
  read: boolean
  delivered_at?: string
  created_at: string
}

export interface RiskAlert {
  id: string
  doctor_id: string
  patient_id: string
  kind: string
  reason: string
  severity: number
  triggered_at: string
  acknowledged_by?: string
  acknowledged_at?: string
}

export interface AuditLog {
  id: number
  doctor_id: string
  patient_id?: string
  actor: string
  action: string
  resource_type: string
  resource_id?: string
  payload_jsonb?: Record<string, unknown>
  ip_address?: string
  user_agent?: string
  occurred_at: string
}