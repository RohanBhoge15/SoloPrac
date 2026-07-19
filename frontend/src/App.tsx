import { Routes, Route, Navigate } from 'react-router-dom'
import { AppLayout } from '@/layouts/AppLayout'
import { Login } from '@/pages/Login'
import { Dashboard } from '@/pages/Dashboard'
import { Calendar } from '@/pages/Calendar'
import { Scratchpad } from '@/pages/Scratchpad'
import { Settings } from '@/pages/Settings'
import { PatientDetail } from '@/pages/PatientDetail'
import { Chat } from '@/pages/Chat'
import { PatientLayout } from '@/layouts/PatientLayout'
import { PatientLogin } from '@/pages/PatientLogin'
import { PatientDashboard } from '@/pages/PatientDashboard'
import { DoctorSearch } from '@/pages/DoctorSearch'
import { PatientAppointments } from '@/pages/PatientAppointments'
import { PatientInbox } from '@/pages/PatientInbox'
import { PatientReports } from '@/pages/PatientReports'
import { WeeklyReport } from '@/pages/WeeklyReport'
import { AuthProvider, useAuth } from '@/contexts/AuthContext'
import { useEffect } from 'react'

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-4 border-primary-600 border-t-transparent" />
      </div>
    )
  }

  if (!user) {
    return <Navigate to="/login" replace />
  }

  return <>{children}</>
}

function PatientProtectedRoute({ children }: { children: React.ReactNode }) {
  const patientToken = localStorage.getItem('patient_token')
  const patientId = localStorage.getItem('patient_id')

  if (!patientToken || !patientId) {
    return <Navigate to="/patient/login" replace />
  }

  return <>{children}</>
}

function AppRoutes() {
  const { user, loading, initializeAuth } = useAuth()

  useEffect(() => {
    initializeAuth()
  }, [initializeAuth])

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-4 border-primary-600 border-t-transparent" />
      </div>
    )
  }

  return (
    <Routes>
      <Route path="/login" element={!user ? <Login /> : <Navigate to="/dashboard" replace />} />
      <Route
        element={
          <ProtectedRoute>
            <AppLayout />
          </ProtectedRoute>
        }
      >
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/calendar" element={<Calendar />} />
        <Route path="/scratchpad" element={<Scratchpad />} />
        <Route path="/chat" element={<Chat />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/weekly-report" element={<WeeklyReport />} />
        <Route path="/patients/:id" element={<PatientDetail />} />
      </Route>
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  )
}

function PatientRoutes() {
  return (
    <Routes>
      <Route path="/patient/login" element={<PatientLogin />} />
      <Route element={<PatientLayout />}>
        <Route
          element={
            <PatientProtectedRoute>
              <PatientDashboard />
            </PatientProtectedRoute>
          }
          path="/patient/dashboard"
        />
        <Route
          element={
            <PatientProtectedRoute>
              <DoctorSearch />
            </PatientProtectedRoute>
          }
          path="/patient/search"
        />
        <Route
          element={
            <PatientProtectedRoute>
              <PatientAppointments />
            </PatientProtectedRoute>
          }
          path="/patient/appointments"
        />
        <Route
          element={
            <PatientProtectedRoute>
              <PatientInbox />
            </PatientProtectedRoute>
          }
          path="/patient/inbox"
        />
        <Route
          element={
            <PatientProtectedRoute>
              <PatientReports />
            </PatientProtectedRoute>
          }
          path="/patient/reports"
        />
        <Route
          element={
            <PatientProtectedRoute>
              <WeeklyReport />
            </PatientProtectedRoute>
          }
          path="/patient/weekly-report"
        />
      </Route>
      <Route path="/patient/*" element={<Navigate to="/patient/login" replace />} />
    </Routes>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route element={<AppRoutes />} />
        <Route element={<PatientRoutes />} />
      </Routes>
    </AuthProvider>
  )
}