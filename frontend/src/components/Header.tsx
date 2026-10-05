import { LayoutDashboard, Search, Users } from 'lucide-react'

interface HeaderProps {
  activeTab: 'design' | 'components' | 'collaborate'
  onTabChange: (tab: 'design' | 'components' | 'collaborate') => void
  roomIdFromUrl?: string | null
}

export function Header({ activeTab, onTabChange, roomIdFromUrl }: HeaderProps) {
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
          <button
            className={`tab ${activeTab === 'collaborate' ? 'active' : ''}`}
            onClick={() => onTabChange('collaborate')}
          >
            <Users className="tab-icon" />
            Collaborate
          </button>
        </nav>
        
        {roomIdFromUrl && (
          <div className="room-indicator">
            <span className="room-badge">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="2" y="6" width="20" height="12" rx="2" />
                <path d="M6 6V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v2" />
                <path d="M12 18V6" />
              </svg>
              Room: {roomIdFromUrl}
            </span>
          </div>
        )}
        </div>
      </header>
    )
  }