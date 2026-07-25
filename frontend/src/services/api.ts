import axios from 'axios'

const API_BASE_URL = '/api/v1'

// Module-level refresh lock — prevents concurrent refresh requests
let refreshPromise: Promise<string> | null = null

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor for auth (patient token takes priority over doctor)
apiClient.interceptors.request.use(
  (config) => {
    const patientToken = localStorage.getItem('patient_token')
    const doctorToken = localStorage.getItem('access_token')
    const token = patientToken || doctorToken
    if (token && !config.headers.Authorization) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// Response interceptor for token refresh with concurrency lock
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config

    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true

      const refreshToken = localStorage.getItem('refresh_token')
      if (!refreshToken) {
        const isPatient = !!localStorage.getItem('patient_id')
        localStorage.clear()
        window.location.href = isPatient ? '/patient/login' : '/login'
        return Promise.reject(error)
      }

      // Use module-level promise lock to prevent concurrent refreshes
      if (!refreshPromise) {
        refreshPromise = (async () => {
          try {
            const response = await axios.post(`${API_BASE_URL}/auth/refresh`, {
              refresh_token: refreshToken,
            })
            const { access_token, refresh_token: newRefreshToken } = response.data
            localStorage.setItem('access_token', access_token)
            localStorage.setItem('refresh_token', newRefreshToken)
            return access_token
          } catch (refreshError) {
            localStorage.clear()
            // Prevent infinite redirect loop: don't redirect if already on login
            if (!window.location.pathname.startsWith('/login')) {
              window.location.href = '/login'
            }
            throw refreshError
          } finally {
            refreshPromise = null
          }
        })()
      }

      try {
        const newToken = await refreshPromise
        originalRequest.headers.Authorization = `Bearer ${newToken}`
        return apiClient(originalRequest)
      } catch (refreshError) {
        return Promise.reject(refreshError)
      }
    }

    return Promise.reject(error)
  }
)

export default apiClient
