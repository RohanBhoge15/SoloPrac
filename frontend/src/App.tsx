import { Routes, Route, Navigate } from 'react-router-dom'
import { AppLayout } from '@/layouts/AppLayout'
import { PatientLayout } from '@/layouts/PatientLayout'
import { Landing } from '@/pages/Landing'
import { Login } from '@/pages/Login'
import { PatientLogin } from '@/pages/PatientLogin'
import { AuthProvider, useAuth } from '@/contexts/AuthContext'
import { Suspense, lazy, useEffect, useState } from 'react'
import { ToastProvider } from '@/components/ui/Toast'
import { apiClient } from '@/services/api'

// P2.19 — Route-level lazy import so first paint only downloads the login /
// landing bundle. Every other page becomes its own async chunk that's fetched
// on demand (and can be prefetched on hover — see P2.20 hooks). Login pages
// stay eager because they're the most common entry point post-logout.
const Register = lazy(() => import('@/pages/Register').then(m => ({ default: m.Register })))
const Dashboard = lazy(() => import('@/pages/Dashboard').then(m => ({ default: m.Dashboard })))
const Calendar = lazy(() => import('@/pages/Calendar').then(m => ({ default: m.Calendar })))
const Scratchpad = lazy(() => import('@/pages/Scratchpad').then(m => ({ default: m.Scratchpad })))
const Settings = lazy(() => import('@/pages/Settings').then(m => ({ default: m.Settings })))
const PatientDetail = lazy(() => import('@/pages/PatientDetail').then(m => ({ default: m.PatientDetail })))
const PatientNew = lazy(() => import('@/pages/PatientNew').then(m => ({ default: m.PatientNew })))
const Chat = lazy(() => import('@/pages/Chat').then(m => ({ default: m.Chat })))
const PatientRegistration = lazy(() => import('@/pages/PatientRegistration').then(m => ({ default: m.PatientRegistration })))
const PatientDashboard = lazy(() => import('@/pages/PatientDashboard').then(m => ({ default: m.PatientDashboard })))
const DoctorSearch = lazy(() => import('@/pages/DoctorSearch').then(m => ({ default: m.DoctorSearch })))
const PatientAppointments = lazy(() => import('@/pages/PatientAppointments').then(m => ({ default: m.PatientAppointments })))
const PatientInbox = lazy(() => import('@/pages/PatientInbox').then(m => ({ default: m.PatientInbox })))
const PatientReports = lazy(() => import('@/pages/PatientReports').then(m => ({ default: m.PatientReports })))
const WeeklyReport = lazy(() => import('@/pages/WeeklyReport').then(m => ({ default: m.WeeklyReport })))
const PatientProfile = lazy(() => import('@/pages/PatientProfile').then(m => ({ default: m.PatientProfile })))
const PatientPendingMatches = lazy(() => import('@/pages/PatientPendingMatches').then(m => ({ default: m.PatientPendingMatches })))

function LazyFallback() {
  return (
    <div className="min-h-[40vh] flex items-center justify-center">
      <div className="animate-spin rounded-full h-8 w-8 border-4 border-primary-600 border-t-transparent" />
    </div>
  )
}

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
  const { user } = useAuth()

  // The `useQuery` inside AuthContext runs automatically on mount, so we don't
  // need to call initializeAuth() here. Blocking the whole app on `loading`
  // used to hide the Login page every time /auth/me refetched (during dev-login
  // click, refresh, etc.), so guarding is handled per-route by <ProtectedRoute>.

  return (
    <Suspense fallback={<LazyFallback />}>
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
        <Route
          path="/patient/pending-matches"
          element={
            <PatientProtectedRoute>
              <PatientPendingMatches />
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
        {/* /patients/new MUST come before /patients/:id — otherwise the
            dynamic segment eats "new" as an id and PatientDetail 404s. */}
        <Route path="/patients/new" element={<PatientNew />} />
        <Route path="/patients/:id" element={<PatientDetail />} />
      </Route>
      <Route path="/" element={<RootRedirect />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
    </Suspense>
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