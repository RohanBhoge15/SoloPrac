import axios from 'axios'

export const apiClient = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor for auth (doctor or patient)
apiClient.interceptors.request.use(
  (config) => {
    const doctorToken = localStorage.getItem('access_token')
    const patientToken = localStorage.getItem('patient_token')
    const token = doctorToken || patientToken
    if (token && !config.headers.Authorization) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// Response interceptor for token refresh
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config

    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true

      const refreshToken = localStorage.getItem('refresh_token')
      if (refreshToken) {
        try {
          const response = await axios.post('/api/v1/auth/refresh', { refresh_token: refreshToken })
          const { access_token, refresh_token: newRefreshToken } = response.data
          localStorage.setItem('access_token', access_token)
          localStorage.setItem('refresh_token', newRefreshToken)
          apiClient.defaults.headers.common['Authorization'] = `Bearer ${access_token}`
          originalRequest.headers.Authorization = `Bearer ${access_token}`
          return apiClient(originalRequest)
        } catch {
          // Refresh failed, redirect to login
          localStorage.removeItem('access_token')
          localStorage.removeItem('refresh_token')
          localStorage.removeItem('patient_token')
          localStorage.removeItem('patient_id')
          window.location.href = '/login'
        }
      } else {
        const patientToken = localStorage.getItem('patient_token')
        if (patientToken) {
          // Patient token can't be refreshed, redirect to patient login
          localStorage.removeItem('patient_token')
          localStorage.removeItem('patient_id')
          window.location.href = '/patient/login'
        } else {
          window.location.href = '/login'
        }
      }
    }

    return Promise.reject(error)
  }
)

export default apiClient