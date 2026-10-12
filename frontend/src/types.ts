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
  /**
   * Parsed catalogue attributes in base SI units, e.g.
   * `{ resistance: 10000, tolerance: 0.01, power: 0.1 }`.
   * Only the fields the catalogue stated are present.
   */
  attributes?: Record<string, number | string>
  /** Minimum quantity the distributor sells. Not always 1. */
  min_order?: number
  /** The distributor's own attrition figures, kept verbatim. */
  attrition?: Record<string, unknown>
}

export interface ComponentSearchRequest {
  query?: string
  category?: string
  package?: string
  min_stock?: number
  limit?: number
  sort?: 'stock' | 'price' | 'value'
}

/**
 * Search results with the interpretation that produced them.
 *
 * `notes` and `interpretation` exist so the UI can show what the search
 * understood. A parametric search that silently misunderstood the query is
 * worse than one that returns nothing.
 */
export interface ComponentSearchResponse {
  components: ComponentResult[]
  notes: string[]
  interpretation: string
  source: string
}

/** A candidate replacement, with the evidence for and against it. */
export interface Substitute extends ComponentResult {
  /** Properties that were checked and matched. */
  reasons: string[]
  /** Differences, or properties that could not be verified. */
  caveats: string[]
  /** True when every comparable property matched or was verified. */
  verified: boolean
}

export interface SubstituteResponse {
  lcsc_part: string
  substitutes: Substitute[]
  notes: string[]
}

// Collaboration types
export interface Collaborator {
  id: string
  name: string
  color: string
  cursor?: { x: number; y: number }
  selection?: any
}

export interface CollaborationRoom {
  room_id: string
  project_name: string
  design_data: any
  users: Collaborator[]
  created_at: string
  updated_at: string
}

export interface RoomListItem {
  room_id: string
  project_name: string
  user_count: number
  created_at: string
  updated_at: string
}