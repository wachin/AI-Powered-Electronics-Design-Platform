import { createContext, useContext, useState, ReactNode } from 'react'
import { CheckCircle2, AlertCircle, Info, X } from 'lucide-react'

interface Toast {
  id: string
  type: 'success' | 'error' | 'info'
  message: string
}

interface ToastContextType {
  toasts: Toast[]
  success: (message: string) => void
  error: (message: string) => void
  info: (message: string) => void
}

const ToastContext = createContext<ToastContextType | null>(null)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const addToast = (type: Toast['type'], message: string) => {
    const id = Math.random().toString(36).slice(2)
    setToasts(prev => [...prev, { id, type, message }])
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id))
    }, 4000)
  }

  const removeToast = (id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }

  return (
    <ToastContext.Provider value={{
      toasts,
      success: (msg) => addToast('success', msg),
      error: (msg) => addToast('error', msg),
      info: (msg) => addToast('info', msg),
    }}>
      {children}
      <ToastContainer toasts={toasts} onRemove={removeToast} />
    </ToastContext.Provider>
  )
}

export function useToast() {
  const context = useContext(ToastContext)
  if (!context) throw new Error('useToast must be used within ToastProvider')
  return context
}

function ToastContainer({ toasts, onRemove }: { toasts: Toast[]; onRemove: (id: string) => void }) {
  const icons = {
    success: <CheckCircle2 className="toast-icon success" />,
    error: <AlertCircle className="toast-icon error" />,
    info: <Info className="toast-icon info" />,
  }

  return (
    <div className="toast-container">
      {toasts.map(toast => (
        <div key={toast.id} className={`toast ${toast.type}`}>
          {icons[toast.type]}
          <span>{toast.message}</span>
          <button onClick={() => onRemove(toast.id)} className="toast-close">
            <X size={14} />
          </button>
        </div>
      ))}
    </div>
  )
}

export function Toast() {
  const { toasts } = useToast()
  
  const icons = {
    success: <CheckCircle2 className="toast-icon success" />,
    error: <AlertCircle className="toast-icon error" />,
    info: <Info className="toast-icon info" />,
  }

  return (
    <div className="toast-container">
      {toasts.map(toast => (
        <div key={toast.id} className={`toast ${toast.type}`}>
          {icons[toast.type]}
          <span>{toast.message}</span>
          <button onClick={() => {}} className="toast-close">
            <X size={14} />
          </button>
        </div>
      ))}
    </div>
  )
}