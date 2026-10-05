import { useState } from 'react'
import { 
  Loader2, CheckCircle2, AlertCircle, FileCode, 
  Download, ClipboardList, ChevronDown, ChevronUp,
  Zap, GitBranch, Shield
} from 'lucide-react'
import type { JobStatus, ERCReport, BOMItem } from '../types'

interface JobStatusProps {
  job: JobStatus
  onCancel: () => void
}

const statusIcons = {
  pending: <Loader2 className="spin" size={20} />,
  running: <Loader2 className="spin" size={20} />,
  completed: <CheckCircle2 size={20} />,
  failed: <AlertCircle size={20} />,
}

const statusLabels = {
  pending: 'Queued',
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
}

const statusColors = {
  pending: 'var(--warning)',
  running: 'var(--accent)',
  completed: 'var(--accent)',
  failed: 'var(--danger)',
}

export function JobStatus({ job, onCancel }: JobStatusProps) {
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({
    circuit: true,
    erc: true,
    files: true,
    bom: true,
  })

  const toggleSection = (key: string) => {
    setExpandedSections(prev => ({ ...prev, [key]: !prev[key] }))
  }

  return (
    <div className="job-status">
      <div className="job-header">
        <div className="job-title">
          <span className="status-badge" style={{ backgroundColor: statusColors[job.status] }}>
            {statusIcons[job.status]}
            {statusLabels[job.status]}
          </span>
          <div>
            <h2>{job.message}</h2>
            <p className="job-meta">Job ID: {job.job_id} • {new Date(job.updated_at).toLocaleTimeString()}</p>
          </div>
        </div>
        {job.status !== 'completed' && job.status !== 'failed' && (
          <button className="btn-secondary" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>

      <div className="progress-bar">
        <div 
          className="progress-fill" 
          style={{ width: `${job.progress}%` }}
        />
      </div>

      {job.result && (
        <div className="results">
          <ResultSection 
            title="Circuit Design" 
            icon={<FileCode />}
            expanded={expandedSections.circuit}
            onToggle={() => toggleSection('circuit')}
          >
            <CircuitSummary circuit={job.result.circuit_ir} />
          </ResultSection>

          <ResultSection 
            title="ERC Validation" 
            icon={<Shield />}
            expanded={expandedSections.erc}
            onToggle={() => toggleSection('erc')}
          >
            <ERCSummary report={job.result.erc_report} />
          </ResultSection>

          {job.result.spice_result && (
            <ResultSection 
              title="SPICE Simulation" 
              icon={<Zap />}
              expanded={expandedSections.spice}
              onToggle={() => toggleSection('spice')}
            >
              <SpiceSummary result={job.result.spice_result} />
            </ResultSection>
          )}

          {job.result.routing_result && (
            <ResultSection 
              title="PCB Routing" 
              icon={<GitBranch />}
              expanded={expandedSections.routing}
              onToggle={() => toggleSection('routing')}
            >
              <RoutingSummary result={job.result.routing_result} />
            </ResultSection>
          )}

          <ResultSection 
            title="Generated Files" 
            icon={<Download />}
            expanded={expandedSections.files}
            onToggle={() => toggleSection('files')}
          >
            <FilesList files={job.result.generated_files} />
          </ResultSection>

          <ResultSection 
            title="Bill of Materials" 
            icon={<ClipboardList />}
            expanded={expandedSections.bom}
            onToggle={() => toggleSection('bom')}
          >
            <BOMTable bom={job.result.bom} />
          </ResultSection>
        </div>
      )}

      {job.status === 'running' && (
        <div className="running-steps">
          <p>Current step: {job.message}</p>
        </div>
      )}
    </div>
  )
}

function ResultSection({ title, icon, expanded, onToggle, children }: any) {
  return (
    <details className="result-section" open={expanded}>
      <summary onClick={(e) => { e.preventDefault(); onToggle(); }}>
        <div className="section-header">
          {icon}
          <span>{title}</span>
          {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </div>
      </summary>
      {expanded && <div className="section-content">{children}</div>}
    </details>
  )
}

function CircuitSummary({ circuit }: { circuit: any }) {
  return (
    <div className="circuit-summary">
      <div className="summary-grid">
        <div className="stat">
          <span className="stat-value">{Object.keys(circuit.components).length}</span>
          <span className="stat-label">Components</span>
        </div>
        <div className="stat">
          <span className="stat-value">{Object.keys(circuit.nets).length}</span>
          <span className="stat-label">Nets</span>
        </div>
        <div className="stat">
          <span className="stat-value">{Object.keys(circuit.power_domains).length}</span>
          <span className="stat-label">Power Domains</span>
        </div>
      </div>
      <div className="components-list">
        {Object.entries(circuit.components).map(([ref, comp]: [string, any]) => (
          <div key={ref} className="component-row">
            <code>{ref}</code>
            <span>{comp.value}</span>
            <span className="comp-type">{comp.component_type}</span>
            <span className="comp-mpn">{comp.mpn || '-'}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function ERCSummary({ report }: { report: ERCReport }) {
  return (
    <div className={`erc-summary ${report.passed ? 'passed' : 'failed'}`}>
      <div className="erc-status">
        {report.passed ? (
          <span className="passed"><CheckCircle2 size={24} /> All checks passed</span>
        ) : (
          <span className="failed"><AlertCircle size={24} /> {report.summary.errors} error(s) found</span>
        )}
      </div>
      <div className="erc-stats">
        <span className="erc-stat error">{report.summary.errors} Errors</span>
        <span className="erc-stat warning">{report.summary.warnings} Warnings</span>
        <span className="erc-stat info">{report.summary.info} Info</span>
      </div>
      {report.issues.length > 0 && (
        <ul className="erc-issues">
          {report.issues.map((issue, i) => (
            <li key={i} className={`issue ${issue.severity}`}>
              <span className="issue-rule">{issue.rule_id}</span>
              <span className="issue-msg">{issue.message}</span>
              {issue.component_ref && <span className="issue-ref">{issue.component_ref}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function SpiceSummary({ result }: { result: any }) {
  return (
    <div className={`spice-summary ${result.success ? 'success' : 'failed'}`}>
      <div className="spice-status">
        {result.success ? (
          <span className="success"><CheckCircle2 size={20} /> Simulation completed</span>
        ) : (
          <span className="failed"><AlertCircle size={20} /> {result.error || 'Failed'}</span>
        )}
      </div>
      {result.stdout && (
        <pre className="spice-output">{result.stdout.slice(0, 2000)}</pre>
      )}
    </div>
  )
}

function RoutingSummary({ result }: { result: any }) {
  return (
    <div className={`routing-summary ${result.success ? 'success' : 'failed'}`}>
      <div className="routing-status">
        {result.success ? (
          <span className="success"><CheckCircle2 size={20} /> Auto-routing completed</span>
        ) : (
          <span className="failed"><AlertCircle size={20} /> {result.error || 'Failed'}</span>
        )}
      </div>
      {result.routed_pcb && (
        <p>Routed PCB: <code>{result.routed_pcb}</code></p>
      )}
    </div>
  )
}

function FilesList({ files }: { files: Record<string, string> }) {
  return (
    <ul className="files-list">
      {Object.entries(files).map(([type, path]) => (
        <li key={type} className="file-item">
          <code>{type.toUpperCase()}</code>
          <span>{path}</span>
        </li>
      ))}
    </ul>
  )
}

function BOMTable({ bom }: { bom: BOMItem[] }) {
  const total = bom.reduce((sum, item) => sum + item.total_price, 0)
  
  return (
    <div className="bom-table-wrapper">
      <table className="bom-table">
        <thead>
          <tr>
            <th>Designators</th>
            <th>MPN</th>
            <th>Value</th>
            <th>Footprint</th>
            <th>Manufacturer</th>
            <th>Qty</th>
            <th>Unit $</th>
            <th>Total $</th>
          </tr>
        </thead>
        <tbody>
          {bom.map((item) => (
            <tr key={item.mpn}>
              <td><code>{item.designators.join(', ')}</code></td>
              <td>{item.mpn}</td>
              <td>{item.value}</td>
              <td><code>{item.footprint}</code></td>
              <td>{item.manufacturer}</td>
              <td>{item.quantity}</td>
              <td>${item.unit_price.toFixed(2)}</td>
              <td>${item.total_price.toFixed(2)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <td colSpan={7} className="text-right"><strong>Total</strong></td>
            <td><strong>${total.toFixed(2)}</strong></td>
          </tr>
        </tfoot>
      </table>
    </div>
  )
}