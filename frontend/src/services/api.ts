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

// Response interceptor - handle 401 for patient routes
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config

    // Don't retry auth endpoints
    if (originalRequest.url?.includes('/auth/') || originalRequest.url?.includes('/public/auth/')) {
      return Promise.reject(error)
    }

    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true

      try {
        // Try to refresh doctor token (uses refresh_token cookie automatically)
        const isPatientRoute = originalRequest.url?.includes('/patient/') || 
                               originalRequest.url?.includes('/public/')
        
        if (isPatientRoute) {
          // Patient routes use patient_token cookie, no refresh endpoint
          // Just redirect to login
          window.location.href = '/patient/login'
          return Promise.reject(error)
        } else {
          // Doctor route - try refresh
          await axios.post(`${API_BASE_URL}/auth/refresh`, {}, { withCredentials: true })
          // Retry original request with new cookies
          return apiClient(originalRequest)
        }
      } catch (refreshError) {
        // Refresh failed - clear cookies via logout endpoint and redirect
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
