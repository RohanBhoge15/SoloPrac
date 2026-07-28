import { Routes, Route, Navigate } from 'react-router-dom'
import { AppLayout } from '@/layouts/AppLayout'
import { Login } from '@/pages/Login'
import { Register } from '@/pages/Register'
import { Dashboard } from '@/pages/Dashboard'
import { Calendar } from '@/pages/Calendar'
import { Scratchpad } from '@/pages/Scratchpad'
import { Settings } from '@/pages/Settings'
import { PatientDetail } from '@/pages/PatientDetail'
import { Chat } from '@/pages/Chat'
import { PatientLayout } from '@/layouts/PatientLayout'
import { PatientLogin } from '@/pages/PatientLogin'
import { PatientRegistration } from '@/pages/PatientRegistration'
import { PatientDashboard } from '@/pages/PatientDashboard'
import { DoctorSearch } from '@/pages/DoctorSearch'
import { PatientAppointments } from '@/pages/PatientAppointments'
import { PatientInbox } from '@/pages/PatientInbox'
import { PatientReports } from '@/pages/PatientReports'
import { WeeklyReport } from '@/pages/WeeklyReport'
import { PatientProfile } from '@/pages/PatientProfile'
import { Landing } from '@/pages/Landing'
import { AuthProvider, useAuth } from '@/contexts/AuthContext'
import { useEffect, useState } from 'react'
import { ToastProvider } from '@/components/ui/Toast'
import { apiClient } from '@/services/api'

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
  const [checking, setChecking] = useState(true)
  const [valid, setValid] = useState(false)

  useEffect(() => {
    apiClient.get('/patient/me/profile')
      .then(() => setValid(true))
      .catch(() => setValid(false))
      .finally(() => setChecking(false))
  }, [])

  if (checking) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-4 border-primary-600 border-t-transparent" />
      </div>
    )
  }

  if (!valid) {
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
      {/* ── Patient portal (/patient/*) ── */}
      <Route path="/patient/login" element={
        user ? <Navigate to="/dashboard" replace /> :
        <PatientLogin />
      } />
      <Route path="/patient/register" element={<PatientRegistration />} />
      <Route element={<PatientLayout />}>
        <Route
          path="/patient/dashboard"
          element={
            <PatientProtectedRoute>
              <PatientDashboard />
            </PatientProtectedRoute>
          }
        />
        <Route
          path="/patient/search"
          element={
            <PatientProtectedRoute>
              <DoctorSearch />
            </PatientProtectedRoute>
          }
        />
        <Route
          path="/patient/appointments"
          element={
            <PatientProtectedRoute>
              <PatientAppointments />
            </PatientProtectedRoute>
          }
        />
        <Route
          path="/patient/inbox"
          element={
            <PatientProtectedRoute>
              <PatientInbox />
            </PatientProtectedRoute>
          }
        />
        <Route
          path="/patient/reports"
          element={
            <PatientProtectedRoute>
              <PatientReports />
            </PatientProtectedRoute>
          }
        />
        <Route
          path="/patient/weekly-report"
          element={
            <PatientProtectedRoute>
              <WeeklyReport />
            </PatientProtectedRoute>
          }
        />
        <Route
          path="/patient/profile"
          element={
            <PatientProtectedRoute>
              <PatientProfile />
            </PatientProtectedRoute>
          }
        />
      </Route>
      <Route path="/patient/*" element={<Navigate to="/patient/login" replace />} />

      {/* ── Doctor app ── */}
      <Route path="/login" element={
        user ? <Navigate to="/dashboard" replace /> :
        <Login />
      } />
      <Route path="/register" element={
        user ? <Navigate to="/dashboard" replace /> :
        <Register />
      } />
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
      <Route path="/" element={<RootRedirect />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

function RootRedirect() {
  const { user, loading } = useAuth()

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-4 border-primary-600 border-t-transparent" />
      </div>
    )
  }

  // Doctor logged in → doctor dashboard
  if (user) {
    return <Navigate to="/dashboard" replace />
  }

  // Not logged in → landing page
  return <Landing />
}

export default function App() {
  return (
    <ToastProvider>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </ToastProvider>
  )
}