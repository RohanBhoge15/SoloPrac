import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/Button'
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/Avatar'
import { getInitials } from '@/utils/helpers'
import { LogOut, Globe } from 'lucide-react'

interface UserMenuProps {
  user: {
    name: string
    email: string
    avatarUrl?: string
  }
  onLogout: () => void
}

export function UserMenu({ user, onLogout }: UserMenuProps) {
  const [open, setOpen] = useState(false)
  const { i18n } = useTranslation()

  const toggleLanguage = () => {
    const newLang = i18n.language === 'en' ? 'hi' : 'en'
    i18n.changeLanguage(newLang)
    localStorage.setItem('soloprac_lang', newLang)
  }

  return (
    <div className="relative">
      <Button
        variant="ghost"
        size="icon"
        className="h-10 w-10 rounded-full"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        aria-haspopup="true"
      >
        <Avatar className="h-8 w-8">
          {user.avatarUrl ? (
            <AvatarImage src={user.avatarUrl} alt={user.name} />
          ) : (
            <AvatarFallback className="text-xs font-medium">
              {getInitials(user.name)}
            </AvatarFallback>
          )}
        </Avatar>
      </Button>

      {open && (
        <>
          <div
            className="fixed inset-0 z-40"
            onClick={() => setOpen(false)}
            aria-hidden="true"
          />
          <div className="absolute right-0 top-full mt-2 z-50 w-56 animate-in fade-in-0 zoom-in-95">
            <div className="card p-2">
              <div className="px-2 py-2 border-b border-gray-200 dark:border-gray-700">
                <p className="text-sm font-medium text-gray-900 dark:text-white">{user.name}</p>
                <p className="text-xs text-gray-500 truncate">{user.email}</p>
              </div>
              <Button
                variant="ghost"
                className="w-full justify-start gap-2 mt-1"
                onClick={toggleLanguage}
              >
                <Globe className="h-4 w-4" />
                {i18n.language === 'en' ? 'हिंदी' : 'English'}
              </Button>
              <Button
                variant="ghost"
                className="w-full justify-start gap-2 mt-1"
                onClick={() => { onLogout(); setOpen(false); }}
              >
                <LogOut className="h-4 w-4" />
                Log out
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}