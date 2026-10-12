import { Fragment, useState, useEffect } from 'react'
import {
  Search,
  Filter,
  Package,
  Database,
  ChevronDown,
  ChevronUp,
  ArrowLeftRight,
  CheckCircle2,
  AlertTriangle,
  Loader2,
} from 'lucide-react'
import { apiClient as api } from '../lib/api'
import type {
  ComponentResult,
  ComponentSearchRequest,
  Substitute,
} from '../types'

/**
 * Component search over the downloaded JLCPCB/LCSC catalog.
 *
 * The search is parametric: "10k 0603" is matched as 10 kΩ in a 0603 package
 * rather than as a substring, so it does not return 110 kΩ parts. The
 * interpretation the backend derived is shown above the results, because the
 * user has to be able to tell whether the search understood the query.
 */
export function ComponentSearch() {
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState('')
  const [packageFilter, setPackageFilter] = useState('')
  const [minStock, setMinStock] = useState(0)
  const [limit, setLimit] = useState(50)
  const [sort, setSort] = useState<'stock' | 'price' | 'value'>('stock')
  const [results, setResults] = useState<ComponentResult[]>([])
  const [categories, setCategories] = useState<string[]>([])
  const [categoryCounts, setCategoryCounts] = useState<Record<string, number>>({})
  const [notes, setNotes] = useState<string[]>([])
  const [interpretation, setInterpretation] = useState('')
  const [source, setSource] = useState('')
  const [loading, setLoading] = useState(false)
  const [searched, setSearched] = useState(false)
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [showFilters, setShowFilters] = useState(false)

  // Substitutes are loaded per part on demand and cached by LCSC number, so
  // reopening a row does not re-query.
  const [substitutes, setSubstitutes] = useState<Record<string, Substitute[]>>({})
  const [substituteNotes, setSubstituteNotes] = useState<Record<string, string[]>>({})
  const [substituteLoading, setSubstituteLoading] = useState<string | null>(null)

  useEffect(() => {
    api
      .getCategories()
      .then((res) => {
        setCategories(res.data.categories)
        setCategoryCounts(res.data.category_counts ?? {})
      })
      .catch(() => setCategories([]))
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
        sort,
      }
      const res = await api.searchComponents(request)
      setResults(res.data.components)
      setNotes(res.data.notes ?? [])
      setInterpretation(res.data.interpretation ?? '')
      setSource(res.data.source ?? '')
      setSearched(true)
    } catch (err) {
      console.error('Search failed:', err)
      setResults([])
      setNotes(['Search failed. Is the backend running?'])
    } finally {
      setLoading(false)
    }
  }

  const toggleExpanded = (key: string) => {
    setExpanded((prev) => ({ ...prev, [key]: !prev[key] }))
  }

  const findSubstitutes = async (part: ComponentResult) => {
    const key = part.lcsc_part
    if (!key || substitutes[key]) return // already loaded
    setSubstituteLoading(key)
    try {
      const res = await api.getSubstitutes(key, { limit: 8, same_package: true })
      setSubstitutes((prev) => ({ ...prev, [key]: res.data.substitutes }))
      setSubstituteNotes((prev) => ({ ...prev, [key]: res.data.notes }))
    } catch (err) {
      console.error('Substitute lookup failed:', err)
      setSubstituteNotes((prev) => ({ ...prev, [key]: ['Substitute lookup failed.'] }))
    } finally {
      setSubstituteLoading(null)
    }
  }

  const rowKey = (part: ComponentResult, index: number) =>
    part.lcsc_part || `${part.mpn}-${index}`

  return (
    <div className="component-search">
      <div className="search-header">
        <h1>Component Database</h1>
        <p>
          Search the downloaded JLCPCB/LCSC catalog. Values are matched
          numerically: <code>10k 0603</code> finds 10 kΩ parts, not 110 kΩ, and{' '}
          <code>100nF 50V</code> treats 50 V as a minimum rating.
        </p>
      </div>

      <div className="search-form">
        <div className="search-input-group">
          <Search className="search-icon" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="e.g. '10k 1% 0603', '100nF 50V 0805', 'ldo 3.3v', 'esp32'"
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
                {categories.map((c) => (
                  <option key={c} value={c}>
                    {categoryCounts[c] ? `${c} (${categoryCounts[c].toLocaleString()})` : c}
                  </option>
                ))}
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
              <label>Sort by</label>
              <select
                value={sort}
                onChange={(e) => setSort(e.target.value as 'stock' | 'price' | 'value')}
              >
                <option value="stock">Most stock</option>
                <option value="price">Cheapest first</option>
                <option value="value">Value</option>
              </select>
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
        <span>
          {results.length} component{results.length !== 1 ? 's' : ''} found
        </span>
        <span className="data-source">
          <Database size={14} />
          {source || 'Catalog status unknown'}
        </span>
      </div>

      {interpretation && (
        <div className="search-interpretation">
          <strong>Understood as:</strong> {interpretation}
          {notes.length > 0 && (
            <ul>
              {notes.map((note, i) => (
                <li key={i}>{note}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {results.length > 0 && (
        <div className="results-table-wrapper">
          <table className="results-table">
            <thead>
              <tr>
                <th></th>
                <th>LCSC</th>
                <th>MPN</th>
                <th>Category</th>
                <th>Value</th>
                <th>Package</th>
                <th>Stock</th>
                <th>Unit price</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {results.map((comp, index) => {
                const key = rowKey(comp, index)
                const isOpen = !!expanded[key]
                const lcsc = comp.lcsc_part
                const subs = lcsc ? substitutes[lcsc] : undefined
                return (
                  <Fragment key={key}>
                    <tr>
                      <td>
                        <button
                          className="expand-btn"
                          onClick={() => toggleExpanded(key)}
                          aria-label={isOpen ? 'Collapse' : 'Expand'}
                        >
                          {isOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                        </button>
                      </td>
                      <td>
                        {lcsc ? (
                          <a
                            href={
                              comp.product_url || `https://jlcpcb.com/partdetail/${lcsc}`
                            }
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            {lcsc}
                          </a>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td>
                        <code>{comp.mpn}</code>
                        {comp.is_preferred && (
                          <span className="badge-preferred">preferred</span>
                        )}
                        {comp.is_basic && <span className="badge-basic">basic</span>}
                      </td>
                      <td>
                        <span className="category-badge">{comp.category}</span>
                      </td>
                      <td>{comp.value}</td>
                      <td>
                        <code>{comp.package}</code>
                      </td>
                      <td>{comp.stock.toLocaleString()}</td>
                      <td>{comp.price ? `$${comp.price.toFixed(4)}` : '—'}</td>
                      <td>
                        {lcsc && (
                          <button
                            className="substitute-btn"
                            onClick={() => findSubstitutes(comp)}
                            disabled={substituteLoading === lcsc}
                            title="Find parts that can replace this one"
                          >
                            {substituteLoading === lcsc ? (
                              <Loader2 size={14} className="spin" />
                            ) : (
                              <ArrowLeftRight size={14} />
                            )}
                            Alternatives
                          </button>
                        )}
                      </td>
                    </tr>

                    {isOpen && (
                      <tr className="expanded-row">
                        <td colSpan={9}>
                          <div className="expanded-content">
                            <div className="expanded-grid">
                              <div>
                                <strong>Manufacturer:</strong> {comp.manufacturer || '—'}
                              </div>
                              <div>
                                <strong>Description:</strong> {comp.description || '—'}
                              </div>
                              <div>
                                <strong>Symbol:</strong> <code>{comp.symbol}</code>
                              </div>
                              <div>
                                <strong>Footprint:</strong> <code>{comp.footprint}</code>
                              </div>
                              <div>
                                <strong>Datasheet:</strong>{' '}
                                {comp.datasheet_url ? (
                                  <a
                                    href={comp.datasheet_url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                  >
                                    View
                                  </a>
                                ) : (
                                  'not listed'
                                )}
                              </div>
                              <div>
                                <strong>Product page:</strong>{' '}
                                {comp.product_url ? (
                                  <a
                                    href={comp.product_url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                  >
                                    View
                                  </a>
                                ) : (
                                  '—'
                                )}
                              </div>
                            </div>

                            {comp.attributes &&
                              Object.keys(comp.attributes).length > 0 && (
                                <div className="spec-list">
                                  <strong>Parsed specifications</strong>
                                  <table>
                                    <tbody>
                                      {Object.entries(comp.attributes)
                                        .filter(([name]) => name !== 'raw')
                                        .map(([name, value]) => (
                                          <tr key={name}>
                                            <td>{name}</td>
                                            <td>
                                              <code>{String(value)}</code>
                                            </td>
                                          </tr>
                                        ))}
                                    </tbody>
                                  </table>
                                </div>
                              )}

                            {subs && subs.length > 0 && (
                              <div className="substitute-list">
                                <strong>Alternatives</strong>
                                {subs.map((sub) => (
                                  <div key={sub.lcsc_part} className="substitute">
                                    <div className="substitute-head">
                                      {sub.verified ? (
                                        <CheckCircle2 size={14} className="ok" />
                                      ) : (
                                        <AlertTriangle size={14} className="warn" />
                                      )}
                                      <a
                                        href={sub.product_url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                      >
                                        {sub.lcsc_part}
                                      </a>
                                      <code>{sub.mpn}</code>
                                      <span>{sub.value}</span>
                                      <span>{sub.stock.toLocaleString()} in stock</span>
                                    </div>
                                    <ul className="reasons">
                                      {sub.reasons.map((r, i) => (
                                        <li key={i} className="reason">
                                          {r}
                                        </li>
                                      ))}
                                      {sub.caveats.map((c, i) => (
                                        <li key={`c${i}`} className="caveat">
                                          {c}
                                        </li>
                                      ))}
                                    </ul>
                                  </div>
                                ))}
                                <p className="substitute-warning">
                                  Candidates, not guarantees. Check the datasheet —
                                  especially the pinout — before ordering.
                                </p>
                              </div>
                            )}

                            {lcsc && substituteNotes[lcsc] && (
                              <div className="substitute-notes">
                                {substituteNotes[lcsc].map((note, i) => (
                                  <p key={i}>{note}</p>
                                ))}
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {results.length === 0 && !loading && searched && (
        <div className="no-results">
          <Package size={48} />
          <p>No components found matching your criteria</p>
        </div>
      )}
    </div>
  )
}
