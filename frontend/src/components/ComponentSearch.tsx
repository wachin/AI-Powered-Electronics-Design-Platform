import { useState, useEffect } from 'react'
import { Search, Filter, Package, Database, ChevronDown, ChevronUp } from 'lucide-react'
import { apiClient as api } from '../lib/api'
import type { ComponentResult, ComponentSearchRequest } from '../types'

export function ComponentSearch() {
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('')
  const [packageFilter, setPackageFilter] = useState('')
  const [minStock, setMinStock] = useState(0)
  const [limit, setLimit] = useState(50)
  const [results, setResults] = useState<ComponentResult[]>([])
  const [categories, setCategories] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [showFilters, setShowFilters] = useState(false)

  useEffect(() => {
    api.getCategories().then(res => setCategories(res.data.categories))
  }, [])

  const handleSearch = async () => {
    setLoading(true)
    try {
      const request: ComponentSearchRequest = {
        query,
        category: category || undefined,
        package: packageFilter || undefined,
        min_stock: minStock,
        limit,
      }
      const res = await api.searchComponents(request)
      setResults(res.data)
    } catch (err) {
      console.error('Search failed:', err)
    } finally {
      setLoading(false)
    }
  }

  const toggleExpanded = (mpn: string) => {
    setExpanded(prev => ({ ...prev, [mpn]: !prev[mpn] }))
  }

  return (
    <div className="component-search">
      <div className="search-header">
        <h1>Component Database</h1>
        <p>Search JLCPCB/LCSC catalog (yaqwsx/jlcparts dataset) with parametric filters</p>
      </div>

      <div className="search-form">
        <div className="search-input-group">
          <Search className="search-icon" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="Search components... (e.g., 'ldo 3.3v', '10k 0402', 'esp32')"
          />
          <button className="search-btn" onClick={handleSearch} disabled={loading}>
            {loading ? 'Searching...' : 'Search'}
          </button>
        </div>

        <button className="filter-toggle" onClick={() => setShowFilters(!showFilters)}>
          <Filter />
          Filters {showFilters ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </button>
      </div>

      {showFilters && (
        <div className="filters-panel">
          <div className="filter-row">
            <div className="filter-field">
              <label>Category</label>
              <select value={category} onChange={(e) => setCategory(e.target.value)}>
                <option value="">All Categories</option>
                {categories.map(c => <option key={c} value={c}>{c}</option>)}
              </select>
            </div>
            <div className="filter-field">
              <label>Package</label>
              <input
                type="text"
                value={packageFilter}
                onChange={(e) => setPackageFilter(e.target.value)}
                placeholder="e.g., 0805, SOT-23, QFN-48"
              />
            </div>
            <div className="filter-field">
              <label>Min Stock</label>
              <input
                type="number"
                value={minStock}
                onChange={(e) => setMinStock(Number(e.target.value))}
                min={0}
              />
            </div>
            <div className="filter-field">
              <label>Limit</label>
              <input
                type="number"
                value={limit}
                onChange={(e) => setLimit(Number(e.target.value))}
                min={1}
                max={200}
              />
            </div>
          </div>
        </div>
      )}

      <div className="results-summary">
        <span>{results.length} component{results.length !== 1 ? 's' : ''} found</span>
        <span className="data-source">
          <Database size={14} />
          Using built-in fallback catalog (JLCParts offline catalog not downloaded)
        </span>
      </div>

      {results.length > 0 && (
        <div className="results-table-wrapper">
          <table className="results-table">
            <thead>
              <tr>
                <th></th>
                <th>MPN</th>
                <th>Manufacturer</th>
                <th>Category</th>
                <th>Value</th>
                <th>Package</th>
                <th>Stock</th>
                <th>Price</th>
                <th>Footprint</th>
                <th>Symbol</th>
              </tr>
            </thead>
            <tbody>
              {results.map((comp) => (
                <tr key={comp.mpn}>
                  <td>
                    <button 
                      className="expand-btn"
                      onClick={() => toggleExpanded(comp.mpn)}
                    >
                      {expanded[comp.mpn] ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                    </button>
                  </td>
                  <td><code>{comp.mpn}</code></td>
                  <td>{comp.manufacturer}</td>
                  <td><span className="category-badge">{comp.category}</span></td>
                  <td>{comp.value}</td>
                  <td><code>{comp.package}</code></td>
                  <td>{comp.stock.toLocaleString()}</td>
                  <td>${comp.price.toFixed(4)}</td>
                  <td><code>{comp.footprint}</code></td>
                  <td><code>{comp.symbol}</code></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {results.length === 0 && !loading && query && (
        <div className="no-results">
          <Package size={48} />
          <p>No components found matching your criteria</p>
        </div>
      )}

      {/* Expanded rows */}
      {results.filter(c => expanded[c.mpn]).map(comp => (
        <tr key={`${comp.mpn}-expanded`} className="expanded-row">
          <td colSpan={10}>
            <div className="expanded-content">
              <div className="expanded-grid">
                <div><strong>Description:</strong> {comp.description || 'N/A'}</div>
                <div><strong>LCSC Part:</strong> {comp.lcsc_part || 'N/A'}</div>
                <div><strong>Datasheet:</strong> {comp.datasheet_url ? <a href={comp.datasheet_url} target="_blank" rel="noopener">View</a> : 'N/A'}</div>
                <div><strong>Product Page:</strong> {comp.product_url ? <a href={comp.product_url} target="_blank" rel="noopener">View</a> : 'N/A'}</div>
                <div><strong>Basic Library:</strong> {comp.is_basic ? 'Yes' : 'No'}</div>
                <div><strong>Preferred:</strong> {comp.is_preferred ? 'Yes' : 'No'}</div>
              </div>
            </div>
          </td>
        </tr>
      ))}
    </div>
  )
}