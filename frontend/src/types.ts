export interface DesignRequest {
  prompt: string
  project_name: string
  run_spice: boolean
  run_routing: boolean
}

export interface DesignResponse {
  job_id: string
  status: string
  message: string
}

export interface JobStatus {
  job_id: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  progress: number
  message: string
  result?: DesignResult
  error?: string
  created_at: string
  updated_at: string
}

export interface DesignResult {
  project_name: string
  circuit_ir: CircuitIR
  erc_report: ERCReport
  spice_result?: SpiceResult
  routing_result?: RoutingResult
  generated_files: Record<string, string>
  bom: BOMItem[]
}

export interface CircuitIR {
  id: string
  name: string
  description: string
  components: Record<string, Component>
  nets: Record<string, Net>
  power_domains: Record<string, PowerDomain>
  constraints: Constraint[]
  metadata: Record<string, any>
}

export interface Component {
  ref: string
  value: string
  component_type: string
  footprint: string
  symbol: string
  mpn?: string
  manufacturer?: string
  description?: string
  pins: Pin[]
  attributes: Record<string, any>
  position?: { x: number; y: number }
  rotation: number
}

export interface Pin {
  number: string
  name: string
  pin_type: string
  connected_net?: string
  position?: { x: number; y: number }
}

export interface Net {
  name: string
  is_power: boolean
  voltage?: number
  connected_pins: { ref: string; pin: string }[]
}

export interface PowerDomain {
  name: string
  voltage: number
  max_current_ma: number
  ground_net: string
}

export interface Constraint {
  target_ref: string
  rule_type: string
  parameters: Record<string, any>
}

export interface ERCReport {
  passed: boolean
  issues: ERCIssue[]
  summary: {
    errors: number
    warnings: number
    info: number
    total: number
  }
}

export interface ERCIssue {
  rule_id: string
  severity: 'error' | 'warning' | 'info'
  message: string
  component_ref?: string
  pin_number?: string
  net_name?: string
}

export interface SpiceResult {
  success: boolean
  stdout: string
  stderr: string
  measurements?: Record<string, any>
}

export interface RoutingResult {
  success: boolean
  routed_pcb?: string
}

export interface BOMItem {
  mpn: string
  value: string
  footprint: string
  manufacturer: string
  quantity: number
  designators: string[]
  unit_price: number
  total_price: number
}

export interface ComponentResult {
  mpn: string
  manufacturer: string
  category: string
  value: string
  package: string
  symbol: string
  footprint: string
  description: string
  stock: number
  price: number
  lcsc_part?: string
  is_basic: boolean
  is_preferred: boolean
  datasheet_url: string
  product_url: string
}

export interface ComponentSearchRequest {
  query?: string
  category?: string
  package?: string
  min_stock?: number
  limit?: number
}