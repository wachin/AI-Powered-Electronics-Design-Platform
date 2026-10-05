import { useState, useEffect } from 'react'
import { apiClient as api } from './lib/api'
import { DesignForm } from './components/DesignForm'
import { JobStatus } from './components/JobStatus'
import { ComponentSearch } from './components/ComponentSearch'
import { Header } from './components/Header'
import { useToast } from './components/Toast'
import { CollaborationPage } from './pages/CollaborationPage'
import type { DesignRequest, JobStatus as JobStatusType } from './types'

function App() {
  const [activeTab, setActiveTab] = useState<'design' | 'components' | 'collaborate'>('design')
  const [job, setJob] = useState<JobStatusType | null>(null)
  const [polling, setPolling] = useState(false)
  const toast = useToast()

  // Check for room ID in URL for deep linking
  const [roomIdFromUrl, setRoomIdFromUrl] = useState<string | null>(null)

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const room = params.get('room')
    if (room) {
      setRoomIdFromUrl(room)
    }
  }, [])

  const handleDesignSubmit = async (request: DesignRequest) => {
    try {
      const res = await api.createDesign(request)
      const jobData = res.data
      setJob({ 
        ...jobData, 
        progress: 0,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      } as JobStatusType)
      setPolling(true)
      pollJob(jobData.job_id)
      toast.success('Design job started')
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to start design')
    }
  }

  const pollJob = async (jobId: string) => {
    while (polling && job) {
      try {
        const response = await api.getJob(jobId)
        const jobData = response.data
        setJob(jobData)
        if (jobData.status === 'completed' || jobData.status === 'failed') {
          setPolling(false)
          if (jobData.status === 'completed') {
            toast.success('Design completed!')
          } else {
            toast.error(`Design failed: ${jobData.error}`)
          }
          break
        }
      } catch (err) {
        console.error('Poll error:', err)
      }
      await new Promise(r => setTimeout(r, 2000))
    }
  }

  const handleJobCancel = () => {
    setPolling(false)
    setJob(null)
  }

  // When roomId from URL changes, switch to collaborate tab
  useEffect(() => {
    if (roomIdFromUrl) {
      setActiveTab('collaborate')
    }
  }, [roomIdFromUrl])

  return (
    <div className="app">
      <Header 
        activeTab={activeTab} 
        onTabChange={setActiveTab}
        roomIdFromUrl={roomIdFromUrl}
      />
      
      <main className="main">
        {activeTab === 'design' && (
          <div className="design-page">
            {!job ? (
              <DesignForm onSubmit={handleDesignSubmit} />
            ) : (
              <JobStatus 
                job={job} 
                onCancel={handleJobCancel}
              />
            )}
          </div>
        )}

        {activeTab === 'components' && (
          <ComponentSearch />
        )}

        {activeTab === 'collaborate' && (
          <CollaborationPage roomId={roomIdFromUrl || undefined} />
        )}
      </main>
    </div>
  )
}

export default App