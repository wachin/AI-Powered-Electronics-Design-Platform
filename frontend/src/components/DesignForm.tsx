import { useState } from 'react'
import { Zap, Cpu, GitBranch, CheckCircle2, AlertCircle } from 'lucide-react'
import type { DesignRequest } from '../types'

interface DesignFormProps {
  onSubmit: (request: DesignRequest) => void
}

const EXAMPLE_PROMPTS = [
  "Design a 5V to 3.3V LDO regulator circuit with green LED indicator and decoupling capacitors",
  "Create a 12V to 5V buck converter with 3A output current",
  "Simple LED blinker circuit with 555 timer",
  "Design a 3.3V LDO regulator 500mA SOT-23 package",
  "USB-C powered board with LED and push button",
]

export function DesignForm({ onSubmit }: DesignFormProps) {
  const [prompt, setPrompt] = useState('')
  const [projectName, setProjectName] = useState('ai_design')
  const [runSpice, setRunSpice] = useState(true)
  const [runRouting, setRunRouting] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [showExamples, setShowExamples] = useState(false)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!prompt.trim()) return
    
    onSubmit({
      prompt: prompt.trim(),
      project_name: projectName.trim() || 'ai_design',
      run_spice: runSpice,
      run_routing: runRouting,
    })
    setSubmitting(true)
    setTimeout(() => setSubmitting(false), 1000)
  }

  return (
    <form className="design-form" onSubmit={handleSubmit}>
      <div className="form-header">
        <h1>Design a Circuit</h1>
        <p>Describe your circuit in natural language. The AI will generate a complete KiCad project with schematic, PCB, BOM, and manufacturing files.</p>
      </div>

      <div className="form-field">
        <label htmlFor="prompt">Circuit Description</label>
        <textarea
          id="prompt"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="e.g., Design a 5V to 3.3V LDO regulator with LED indicator..."
          rows={4}
          required
        />
        <div className="field-hint">
          <button type="button" className="hint-btn" onClick={() => setShowExamples(!showExamples)}>
            {showExamples ? <AlertCircle size={14} /> : <Zap size={14} />} 
            {showExamples ? 'Hide examples' : 'Show examples'}
          </button>
        </div>
      </div>

      {showExamples && (
        <div className="examples">
          {EXAMPLE_PROMPTS.map((ex, i) => (
            <button 
              key={i} 
              type="button" 
              className="example-btn"
              onClick={() => setPrompt(ex)}
            >
              {ex}
            </button>
          ))}
        </div>
      )}

      <div className="form-row">
        <div className="form-field">
          <label htmlFor="projectName">Project Name</label>
          <input
            id="projectName"
            type="text"
            value={projectName}
            onChange={(e) => setProjectName(e.target.value)}
            placeholder="ldo_regulator"
          />
        </div>
      </div>

      <fieldset className="options-fieldset">
        <legend>Pipeline Options</legend>
        <div className="options-grid">
          <label className="option">
            <input
              type="checkbox"
              checked={runSpice}
              onChange={(e) => setRunSpice(e.target.checked)}
            />
            <span className="option-content">
              <Cpu className="option-icon" />
              <div>
                <strong>SPICE Simulation</strong>
                <span>Run ngspice DC/transient analysis</span>
              </div>
            </span>
          </label>
          <label className="option">
            <input
              type="checkbox"
              checked={runRouting}
              onChange={(e) => setRunRouting(e.target.checked)}
            />
            <span className="option-content">
              <GitBranch className="option-icon" />
              <div>
                <strong>PCB Auto-routing</strong>
                <span>Run FreeRouting autorouter</span>
              </div>
            </span>
          </label>
        </div>
      </fieldset>

      <button type="submit" className="submit-btn" disabled={submitting || !prompt.trim()}>
        {submitting ? (
          <>
            <div className="spinner" />
            Starting design...
          </>
        ) : (
          <>
            <CheckCircle2 size={18} />
            Generate Design
          </>
        )}
      </button>

      <div className="form-footer">
        <p>Output: KiCad project (.kicad_sch, .kicad_pcb, .kicad_pro) + BOM + Gerbers</p>
      </div>
    </form>
  )
}