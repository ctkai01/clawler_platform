import { useEffect } from 'react'
import { AppProviders } from '@/app/providers'
import { useAuthStore } from '@/store/authStore'
import { getToken } from '@/lib/apiClient'
import { authApi } from '@/features/auth/authApi'

function App() {
  const setUser = useAuthStore((s) => s.setUser)
  const setBootstrapping = useAuthStore((s) => s.setBootstrapping)

  // Resolve an existing token (localStorage) into a session user on first
  // load, so a page refresh doesn't bounce a logged-in user to /login.
  useEffect(() => {
    const token = getToken()
    if (!token) {
      setBootstrapping(false)
      return
    }
    authApi
      .me()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setBootstrapping(false))
  }, [setUser, setBootstrapping])

  return <AppProviders />
}

export default App
