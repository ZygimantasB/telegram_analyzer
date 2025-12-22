import { useState } from 'react'
import { Menu, X, MessageCircle, LayoutDashboard, Trash2, Clock, Settings, LogOut, User } from 'lucide-react'
import { ThemeToggle } from './ThemeToggle'

interface NavbarProps {
  user?: {
    username: string
    email: string
    avatar?: string
  }
  isAuthenticated: boolean
}

export function Navbar({ user, isAuthenticated }: NavbarProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [showDropdown, setShowDropdown] = useState(false)

  return (
    <nav className="sticky top-0 z-50 glass border-b border-white/10 dark:border-dark-700/50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <a href="/" className="flex items-center gap-3 group">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary-500 to-accent-500 flex items-center justify-center shadow-lg group-hover:shadow-xl transition-shadow">
              <MessageCircle className="w-5 h-5 text-white" />
            </div>
            <span className="text-xl font-bold text-gradient">Telegram Analyzer</span>
          </a>

          {/* Desktop Navigation */}
          <div className="hidden md:flex items-center gap-1">
            {isAuthenticated && (
              <>
                <NavLink href="/telegram/dashboard/" icon={<LayoutDashboard className="w-4 h-4" />}>
                  Dashboard
                </NavLink>
                <NavLink href="/telegram/chats/" icon={<MessageCircle className="w-4 h-4" />}>
                  Chats
                </NavLink>
                <NavLink href="/telegram/deleted/" icon={<Trash2 className="w-4 h-4" />}>
                  Deleted
                </NavLink>
                <NavLink href="/telegram/sync-history/" icon={<Clock className="w-4 h-4" />}>
                  History
                </NavLink>
              </>
            )}
          </div>

          {/* Right side */}
          <div className="flex items-center gap-3">
            <ThemeToggle />

            {isAuthenticated && user ? (
              <div className="relative">
                <button
                  onClick={() => setShowDropdown(!showDropdown)}
                  className="flex items-center gap-2 p-1.5 rounded-xl hover:bg-dark-100 dark:hover:bg-dark-800 transition-colors"
                >
                  {user.avatar ? (
                    <img src={user.avatar} alt="" className="w-8 h-8 rounded-full object-cover ring-2 ring-primary-500/30" />
                  ) : (
                    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-primary-500 to-accent-500 flex items-center justify-center">
                      <span className="text-white text-sm font-medium">
                        {user.username.charAt(0).toUpperCase()}
                      </span>
                    </div>
                  )}
                  <span className="hidden sm:block font-medium text-dark-700 dark:text-dark-200">
                    {user.username}
                  </span>
                </button>

                {showDropdown && (
                  <div className="absolute right-0 mt-2 w-56 card p-2 animate-slide-down">
                    <div className="px-3 py-2 border-b border-dark-200 dark:border-dark-700 mb-2">
                      <p className="text-sm font-medium text-dark-900 dark:text-dark-100">{user.username}</p>
                      <p className="text-xs text-dark-500">{user.email}</p>
                    </div>
                    <DropdownLink href="/users/profile/" icon={<User className="w-4 h-4" />}>
                      Profile
                    </DropdownLink>
                    <DropdownLink href="/telegram/dashboard/" icon={<Settings className="w-4 h-4" />}>
                      Settings
                    </DropdownLink>
                    <div className="border-t border-dark-200 dark:border-dark-700 mt-2 pt-2">
                      <DropdownLink href="/users/logout/" icon={<LogOut className="w-4 h-4" />} danger>
                        Logout
                      </DropdownLink>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <a href="/users/login/" className="btn-ghost text-sm">Login</a>
                <a href="/users/register/" className="btn-primary text-sm">Register</a>
              </div>
            )}

            {/* Mobile menu button */}
            <button
              onClick={() => setIsOpen(!isOpen)}
              className="md:hidden p-2 rounded-xl hover:bg-dark-100 dark:hover:bg-dark-800"
            >
              {isOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>
          </div>
        </div>

        {/* Mobile Navigation */}
        {isOpen && (
          <div className="md:hidden py-4 border-t border-dark-200 dark:border-dark-700 animate-slide-down">
            {isAuthenticated && (
              <div className="space-y-1">
                <MobileNavLink href="/telegram/dashboard/">Dashboard</MobileNavLink>
                <MobileNavLink href="/telegram/chats/">Chats</MobileNavLink>
                <MobileNavLink href="/telegram/deleted/">Deleted Messages</MobileNavLink>
                <MobileNavLink href="/telegram/sync-history/">Sync History</MobileNavLink>
              </div>
            )}
          </div>
        )}
      </div>
    </nav>
  )
}

function NavLink({ href, icon, children }: { href: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <a
      href={href}
      className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium
                 text-dark-600 dark:text-dark-300
                 hover:text-dark-900 dark:hover:text-dark-100
                 hover:bg-dark-100 dark:hover:bg-dark-800
                 transition-colors"
    >
      {icon}
      {children}
    </a>
  )
}

function MobileNavLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a
      href={href}
      className="block px-4 py-3 rounded-xl text-dark-700 dark:text-dark-200
                 hover:bg-dark-100 dark:hover:bg-dark-800 transition-colors"
    >
      {children}
    </a>
  )
}

function DropdownLink({ href, icon, children, danger }: { href: string; icon: React.ReactNode; children: React.ReactNode; danger?: boolean }) {
  return (
    <a
      href={href}
      className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors
                 ${danger
                   ? 'text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20'
                   : 'text-dark-700 dark:text-dark-200 hover:bg-dark-100 dark:hover:bg-dark-800'
                 }`}
    >
      {icon}
      {children}
    </a>
  )
}
