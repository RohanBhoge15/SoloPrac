import axios from 'axios'

const API_BASE_URL = '/api/v1'

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
  // Send HttpOnly cookies with all requests
  withCredentials: true,
})

// Request interceptor - no need to add Authorization header manually
// Cookies are sent automatically with withCredentials: true
apiClient.interceptors.request.use(
  (config) => {
    return config
  },
  (error) => Promise.reject(error)
)

// Helpers so URL prefix matching is precise:
//   - '/patient/me/…', '/patient/appointments' → patient portal
//   - '/patients/…' (plural, doctor side) → NOT patient portal
//   - '/public/…' → patient-portal / marketing endpoints, no doctor cookie
const isPatientPortalUrl = (url: string) => {
  return /^\/(patient|public)(\/|$)/.test(url) && !/^\/patients\//.test(url)
}

// Response interceptor - handle 401 with a targeted refresh/redirect policy.
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config
    const rawUrl: string = originalRequest?.url ?? ''
    // Normalise: axios stores request URL without the baseURL prefix
    const url = rawUrl.startsWith('/') ? rawUrl : `/${rawUrl}`

    // Never retry / redirect on auth-flow endpoints — those pages handle it.
    if (url.includes('/auth/') || url.includes('/public/auth/')) {
      return Promise.reject(error)
    }

    // Probe endpoints used by route guards: DO NOT hard-redirect on 401,
    // let the caller's .catch() decide. Redirect-on-401 for a probe creates
    // an infinite loop when a doctor-logged-in session hits a patient guard.
    const isSessionProbe =
      url === '/patient/me/profile' || url === '/auth/me'

    if (error.response?.status === 401 && !originalRequest._retry && !isSessionProbe) {
      originalRequest._retry = true

      try {
        if (isPatientPortalUrl(url)) {
          // Patient portal: no refresh endpoint. Redirect to portal login.
          window.location.href = '/patient/login'
          return Promise.reject(error)
        }
        // Doctor route — try silent refresh, then retry.
        await axios.post(`${API_BASE_URL}/auth/refresh`, {}, { withCredentials: true })
        return apiClient(originalRequest)
      } catch (refreshError) {
        try {
          await axios.post(`${API_BASE_URL}/auth/logout`, {}, { withCredentials: true })
        } catch {}
        window.location.href = '/login'
        return Promise.reject(refreshError)
      }
    }

    return Promise.reject(error)
  }
)

export default apiClient
