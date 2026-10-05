import { LayoutDashboard, Search } from 'lucide-react'

interface HeaderProps {
  activeTab: 'design' | 'components'
  onTabChange: (tab: 'design' | 'components') => void
}

export function Header({ activeTab, onTabChange }: HeaderProps) {
  return (
    <header className="header">
      <div className="header-content">
        <div className="logo">
          <svg width="32" height="32" viewBox="0 0 32 32" fill="none">
            <rect width="32" height="32" rx="8" fill="currentColor"/>
            <path d="M8 16L14 22L24 10" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          <span>AI Electronics Design</span>
        </div>
        
        <nav className="tabs">
          <button
            className={`tab ${activeTab === 'design' ? 'active' : ''}`}
            onClick={() => onTabChange('design')}
          >
            <LayoutDashboard className="tab-icon" />
            Design
          </button>
          <button
            className={`tab ${activeTab === 'components' ? 'active' : ''}`}
            onClick={() => onTabChange('components')}
          >
            <Search className="tab-icon" />
            Components
          </button>
        </nav>
      </div>
    </header>
  )
}