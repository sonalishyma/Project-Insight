import { useState, useEffect, useCallback, useMemo } from 'react'
import {
  LineChart, Line, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer,
} from 'recharts'
import './App.css'

const BACKEND = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000'
const STORAGE_KEYS = {
  reports: 'insight.savedReports',
  favorites: 'insight.favorites',
  history: 'insight.history',
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function getDomain(url) {
  try { return new URL(url).hostname.replace('www.', '') }
  catch { return '' }
}
function pct(v) {
  if (v == null) return null
  return `${(v * 100).toFixed(1)}%`
}
function fix(v, d = 2) {
  if (v == null) return null
  return v.toFixed(d)
}
function fmtDate(d) {
  if (!d) return null
  try {
    return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
  } catch { return d }
}
function money(v) {
  if (v == null) return null
  return `$${Number(v).toFixed(2)}`
}
function loadStored(key, fallback) {
  try {
    return JSON.parse(localStorage.getItem(key)) || fallback
  } catch {
    return fallback
  }
}
function store(key, value) {
  localStorage.setItem(key, JSON.stringify(value))
}
function reportId(data) {
  return data?.snapshot?.ticker || data?.company
}

// Per-domain brand gradient for source card placeholders
const DOMAIN_COLORS = {
  'bloomberg.com':       '#f26721', 'reuters.com':       '#e07800',
  'wsj.com':             '#004276', 'ft.com':             '#cc0000',
  'cnbc.com':            '#003087', 'forbes.com':         '#a41010',
  'fortune.com':         '#c41230', 'businessinsider.com':'#1a73e8',
  'marketwatch.com':     '#00ac4e', 'seekingalpha.com':   '#f39c12',
  'morningstar.com':     '#e60000', 'investopedia.com':   '#1f8b4c',
  'fool.com':            '#ff6b35', 'techcrunch.com':     '#0a8a00',
  'theverge.com':        '#e01d1d', 'wired.com':          '#222222',
  'axios.com':           '#ff4136', 'nytimes.com':        '#111111',
  'theguardian.com':     '#005689', 'apnews.com':         '#cc0000',
  'barrons.com':         '#1a1a2e', 'economist.com':      '#cc0000',
  'hbr.org':             '#c41230', 'fastcompany.com':    '#1a1a1a',
  'finance.yahoo.com':   '#7b0099', 'nasdaq.com':         '#0051a5',
  'macrotrends.net':     '#2c3e50', 'statista.com':       '#0084c1',
}
function domainColor(domain) {
  if (DOMAIN_COLORS[domain]) return DOMAIN_COLORS[domain]
  // Deterministic color from domain string
  let h = 0
  for (let i = 0; i < domain.length; i++) h = (h * 31 + domain.charCodeAt(i)) & 0xffff
  const hue = h % 360
  return `hsl(${hue}, 55%, 35%)`
}

// Sanity-check financial ratios and warn in console for implausible values.
// NOTE: ROE/ROA are intentionally excluded — they can legitimately exceed 100% for
// buyback-heavy companies (Apple, etc.) whose book equity has been reduced by repurchases.
function warnRatios(r) {
  if (!r) return
  if (r.dividend_yield != null && r.dividend_yield > 15)
    console.warn(`[sanity] dividend_yield=${r.dividend_yield}: >15% is unusual — verify units`)
  if (r.gross_margin != null && Math.abs(r.gross_margin) > 1)
    console.warn(`[sanity] gross_margin=${r.gross_margin}: outside ±100% — check units (should be 0-1 fraction)`)
  if (r.operating_margin != null && Math.abs(r.operating_margin) > 1)
    console.warn(`[sanity] operating_margin=${r.operating_margin}: outside ±100%`)
  if (r.pe_ratio != null && (r.pe_ratio < 0 || r.pe_ratio > 1000))
    console.warn(`[sanity] pe_ratio=${r.pe_ratio}: implausible — negative or >1000`)
  if (r.pb_ratio != null && (r.pb_ratio < 0 || r.pb_ratio > 500))
    console.warn(`[sanity] pb_ratio=${r.pb_ratio}: implausible`)
  if (r.ps_ratio != null && (r.ps_ratio < 0 || r.ps_ratio > 500))
    console.warn(`[sanity] ps_ratio=${r.ps_ratio}: implausible`)
}

// Guess an icon.horse URL from a company name (frontend fallback for logos)
const _LOGO_SKIP_WORDS = new Set([
  'inc', 'corp', 'corporation', 'ltd', 'llc', 'co', 'plc', 'group',
  'holding', 'holdings', 'technologies', 'technology', 'tech', 'electronics',
  'system', 'systems', 'solution', 'solutions', 'service', 'services',
  'company', 'international', 'global', 'enterprise', 'enterprises',
  'partners', 'ventures', 'platform', 'platforms', 'industries', 'the',
])
function guessLogoUrl(name) {
  // Strip parentheticals then use the first meaningful word as the domain slug
  const withoutParens = name.replace(/\s*\([^)]*\)/g, '').trim()
  const words = withoutParens.replace(/[^\w\s]/g, '').toLowerCase().split(/\s+/)
    .filter(w => w.length >= 2 && !_LOGO_SKIP_WORDS.has(w))
  const slug = words[0] || ''
  return slug.length >= 2 ? `https://icon.horse/icon/${slug}.com` : null
}

// ─── Root ─────────────────────────────────────────────────────────────────────

export default function App() {
  const [company, setCompany] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [suggestions, setSuggestions] = useState([])
  const [suggesting, setSuggesting] = useState(false)
  const [suppressAutocomplete, setSuppressAutocomplete] = useState(false)
  const [libraryOpen, setLibraryOpen] = useState(false)
  const [savedReports, setSavedReports] = useState(() => loadStored(STORAGE_KEYS.reports, []))
  const [favorites, setFavorites] = useState(() => loadStored(STORAGE_KEYS.favorites, []))
  const [history, setHistory] = useState(() => loadStored(STORAGE_KEYS.history, []))

  useEffect(() => { store(STORAGE_KEYS.reports, savedReports) }, [savedReports])
  useEffect(() => { store(STORAGE_KEYS.favorites, favorites) }, [favorites])
  useEffect(() => { store(STORAGE_KEYS.history, history) }, [history])

  useEffect(() => {
    const q = company.trim()
    if (q.length < 2 || loading || suppressAutocomplete) {
      setSuggestions([])
      setSuggesting(false)
      return
    }
    const timer = setTimeout(async () => {
      setSuggesting(true)
      try {
        const res = await fetch(`${BACKEND}/companies?q=${encodeURIComponent(q)}`)
        if (!res.ok) throw new Error('Autocomplete unavailable')
        const json = await res.json()
        setSuggestions(json.suggestions || [])
      } catch {
        setSuggestions([])
      } finally {
        setSuggesting(false)
      }
    }, 220)
    return () => clearTimeout(timer)
  }, [company, loading, suppressAutocomplete])

  const doSearch = useCallback(async (name) => {
    const q = (name || '').trim()
    if (!q) return
    setCompany(q)
    setSuppressAutocomplete(true)
    setSuggestions([])
    setSuggesting(false)
    setLoading(true)
    setError(null)
    setResult(null)
    try {
      const res = await fetch(`${BACKEND}/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ company: q }),
      })
      if (!res.ok) throw new Error(`Server error: ${res.status}`)
      const json = await res.json()
      if (!json.swot || !json.competitors) throw new Error('Unexpected response — try restarting the backend.')
      setResult(json)
      setHistory(prev => {
        const item = {
          company: json.company,
          ticker: json.snapshot?.ticker,
          searchedAt: new Date().toISOString(),
        }
        return [item, ...prev.filter(h => (h.ticker || h.company) !== (item.ticker || item.company))].slice(0, 10)
      })
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  function handleSubmit(e) {
    e.preventDefault()
    doSearch(company)
  }

  function saveCurrentReport() {
    if (!result) return
    const id = reportId(result)
    const item = {
      id,
      company: result.company,
      ticker: result.snapshot?.ticker,
      savedAt: new Date().toISOString(),
      report: result,
    }
    setSavedReports(prev => [item, ...prev.filter(r => r.id !== id)].slice(0, 8))
  }

  function toggleFavorite(target) {
    const id = target.ticker || target.company || target.id
    if (!id) return
    const item = {
      id,
      company: target.company,
      ticker: target.ticker,
      savedAt: new Date().toISOString(),
    }
    setFavorites(prev => prev.some(f => f.id === id)
      ? prev.filter(f => f.id !== id)
      : [item, ...prev].slice(0, 20))
  }

  function openSavedReport(item) {
    setResult(item.report)
    setCompany(item.company)
    setSuppressAutocomplete(true)
    setError(null)
    setSuggestions([])
    setSuggesting(false)
  }

  function goHome() {
    setResult(null)
    setCompany('')
    setError(null)
  }

  const showHome = !result && !loading && !error
  const currentId = reportId(result)
  const isCurrentSaved = !!currentId && savedReports.some(r => r.id === currentId)
  const isCurrentFavorite = !!currentId && favorites.some(f => f.id === currentId)

  return (
    <>
      {result && (
        <div className="report-top-banner">
          <div className="report-top-banner-inner">
            <button className="banner-btn banner-btn-home" onClick={goHome}>← Home</button>
            <div className="banner-actions">
              <button className="banner-btn" onClick={saveCurrentReport}>
                {isCurrentSaved ? 'Report Saved ✓' : 'Save Report'}
              </button>
              <button className="banner-btn" onClick={() => toggleFavorite({ company: result.company, ticker: result.snapshot?.ticker })}>
                {isCurrentFavorite ? '★ Favorited' : '☆ Favorite'}
              </button>
            </div>
          </div>
        </div>
      )}
      <div className="app">
      <header className="app-header">
        <h1>Insight</h1>
        <p>AI-powered market research for any company, public or private</p>
      </header>

      <form onSubmit={handleSubmit} className="search-form">
        <div className="search-input-wrap">
          <input
            type="text"
            placeholder="Enter a company name..."
            value={company}
            onChange={e => {
              setCompany(e.target.value)
              setSuppressAutocomplete(false)
            }}
            disabled={loading}
            autoComplete="off"
          />
          {(suggestions.length > 0 || suggesting) && (
            <div className="autocomplete-menu">
              {suggesting && <div className="autocomplete-status">Searching...</div>}
              {suggestions.map(s => (
                <button
                  type="button"
                  key={`${s.symbol}-${s.name}`}
                  className="autocomplete-item"
                  onClick={() => doSearch(s.name)}
                >
                  <span>{s.name}</span>
                  <small>{[s.symbol, s.exchange].filter(Boolean).join(' · ')}</small>
                </button>
              ))}
            </div>
          )}
        </div>
        <button type="submit" disabled={loading || !company.trim()}>
          {loading ? 'Analyzing...' : 'Analyze'}
        </button>
      </form>

      <ResearchLibrary
        savedReports={savedReports}
        favorites={favorites}
        history={history}
        open={libraryOpen}
        onToggleOpen={() => setLibraryOpen(open => !open)}
        onOpenReport={openSavedReport}
        onSearch={doSearch}
        onToggleFavorite={toggleFavorite}
      />

      {error && <div className="error">{error}</div>}
      {loading && (
        <div className="loading">
          <div className="spinner" />
          <p>Researching <strong>{company}</strong>...</p>
        </div>
      )}
      {showHome && <HomePage onSearch={doSearch} />}
      {result && (
        <Report
          data={result}
          onSearch={doSearch}
        />
      )}
    </div>
    </>
  )
}

// ─── Home Page ────────────────────────────────────────────────────────────────

const EXAMPLE_COMPANIES = [
  { name: 'Apple', type: 'Public' },
  { name: 'Nvidia', type: 'Public' },
  { name: 'Pano AI', type: 'Private' },
  { name: 'Stripe', type: 'Private' },
  { name: 'Tesla', type: 'Public' },
  { name: 'Anthropic', type: 'Private' },
]

function HomePage({ onSearch }) {
  return (
    <div className="home-page">
      <div className="home-features">
        <div className="home-feature-card">
          <div className="home-feature-title">Public Companies</div>
          <div className="home-feature-desc">
            Stock performance, financial ratios, revenue charts, valuation metrics, quarterly earnings, and AI-generated competitive analysis — all in one place.
          </div>
          <ul className="home-feature-list">
            <li>Stock price &amp; historical charts</li>
            <li>P/E, EV/EBITDA, margins, ROE</li>
            <li>Annual &amp; quarterly financials</li>
            <li>Analyst-grade SWOT &amp; positioning</li>
          </ul>
        </div>

        <div className="home-feature-card">
          <div className="home-feature-title">Private Startups</div>
          <div className="home-feature-desc">
            No financial filings? No problem. Insight automatically switches to a startup-native dashboard covering what actually matters for early-stage companies.
          </div>
          <ul className="home-feature-list">
            <li>Funding rounds &amp; investors</li>
            <li>Employee growth &amp; hiring signals</li>
            <li>Company timeline &amp; milestones</li>
            <li>Market traction &amp; customers</li>
          </ul>
        </div>

        <div className="home-feature-card">
          <div className="home-feature-title">Source-Grounded AI</div>
          <div className="home-feature-desc">
            Every claim in the analysis is traceable to live web sources fetched at query time — not cached knowledge. News, filings, and research from trusted publications.
          </div>
          <ul className="home-feature-list">
            <li>Live web search via Tavily</li>
            <li>Verified financial data via FMP &amp; SEC EDGAR</li>
            <li>Sources cited &amp; linked</li>
            <li>Confidence score on every report</li>
          </ul>
        </div>
      </div>

      <div className="home-examples">
        <div className="home-examples-label">Try an example</div>
        <div className="home-examples-pills">
          {EXAMPLE_COMPANIES.map(c => (
            <button
              key={c.name}
              className="home-example-pill"
              onClick={() => onSearch(c.name)}
            >
              {c.name}
              <span className={`home-example-type ${c.type.toLowerCase()}`}>{c.type}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="home-disclaimer">
        Insight runs on free-tier APIs and an auto-sleeping backend, so your first search may take 30–60 seconds or need a second try &amp; that's completely normal. Results are worth the wait.
      </div>
    </div>
  )
}

// ─── Research Library ─────────────────────────────────────────────────────────

function ResearchLibrary({ savedReports, favorites, history, open, onToggleOpen, onOpenReport, onSearch, onToggleFavorite }) {
  const hasItems = savedReports.length || favorites.length || history.length
  const itemCount = savedReports.length + favorites.length + history.length

  return (
    <aside className={`library-side ${open ? 'open' : ''}`}>
      <button
        className="library-tab"
        onClick={onToggleOpen}
        aria-expanded={open}
        aria-label={open ? 'Close research library' : 'Open research library'}
      >
        <span>Library</span>
        {itemCount > 0 && <strong>{itemCount}</strong>}
      </button>

      <div className="library-panel">
        <div className="library-panel-header">
          <div>
            <h2>Research Library</h2>
            <p>Saved reports, favorites, and recent searches</p>
          </div>
          <button className="library-close" onClick={onToggleOpen} aria-label="Close research library">Close</button>
        </div>

        {!hasItems && <div className="library-empty">Saved reports, favorites, and history will appear here.</div>}

        {savedReports.length > 0 && (
          <div className="library-group">
            <div className="library-label">Saved Reports</div>
            <div className="library-row">
              {savedReports.map(item => (
                <button key={item.id} className="library-pill" onClick={() => onOpenReport(item)}>
                  <span>{item.company}</span>
                  {item.ticker && <small>{item.ticker}</small>}
                </button>
              ))}
            </div>
          </div>
        )}

        {favorites.length > 0 && (
          <div className="library-group">
            <div className="library-label">Favorites</div>
            <div className="library-row">
              {favorites.map(item => (
                <button key={item.id} className="library-pill favorite" onClick={() => onSearch(item.company)}>
                  <span>{item.company}</span>
                  {item.ticker && <small>{item.ticker}</small>}
                </button>
              ))}
            </div>
          </div>
        )}

        {history.length > 0 && (
          <div className="library-group">
            <div className="library-label">History</div>
            <div className="library-row">
              {history.slice(0, 8).map(item => {
                const id = item.ticker || item.company
                const favorite = favorites.some(f => f.id === id)
                return (
                  <div key={`${id}-${item.searchedAt}`} className="history-item">
                    <button className="history-search-btn" onClick={() => onSearch(item.company)}>
                      <span>{item.company}</span>
                      {item.ticker && <small>{item.ticker}</small>}
                    </button>
                    <button
                      className={`history-favorite-btn ${favorite ? 'active' : ''}`}
                      onClick={() => onToggleFavorite(item)}
                      aria-label={favorite ? 'Remove favorite' : 'Add favorite'}
                    >
                      {favorite ? 'Saved' : 'Save'}
                    </button>
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>
    </aside>
  )
}

// ─── Report ───────────────────────────────────────────────────────────────────

function Report({ data, onSearch }) {
  useEffect(() => { warnRatios(data.financial_ratios) }, [data.financial_ratios])

  const isPrivate = data.company_type === 'private'
  const hasFCF = data.annual_data?.some(d => d.fcf != null)
  const hasEPS = data.annual_data?.some(d => d.eps != null)

  return (
    <div className="report">

      {/* ── Header ── */}
      <div className="report-header">
        <div className="report-header-left">
          <HeaderLogo url={data.snapshot?.logo_url} name={data.company} />
          <div>
            <h2>{data.company}</h2>
            <div className="report-header-badges">
              {data.snapshot?.ticker && <span className="badge badge-blue">{data.snapshot.ticker}</span>}
              {data.snapshot?.exchange && <span className="badge badge-gray">{data.snapshot.exchange}</span>}
              {data.market_size && <span className="badge badge-purple">{data.market_size}</span>}
              <CompanyTypeBadge type={data.company_type} stage={data.stage} />
            </div>
          </div>
        </div>
        <div className="report-header-right">
          <ConfidencePill score={data.confidence_score} sources={data.sources_count} />
        </div>
      </div>

      <Snapshot snap={data.snapshot} />

      <Section title="What's Happening Now" tag="OpenRouter">
        <p className="summary-text">{data.summary}</p>
      </Section>

      {/* ── Public: stock + financials ── */}
      {!isPrivate && (
        <>
          <StockChart initialData={data.stock_history} ticker={data.snapshot?.ticker} />
          <PublicMarketIntel sentiment={data.analyst_sentiment} earnings={data.earnings_info} />
          <FinancialMetrics ratios={data.financial_ratios} summary={data.financial_summary} />
          {data.annual_data?.length > 0 && (
            <>
              <div className="two-col">
                <AnnualRevenueChart data={data.annual_data} />
                <AnnualIncomeChart data={data.annual_data} />
              </div>
              {(hasFCF || hasEPS) && (
                <div className="two-col">
                  {hasFCF && <AnnualFCFChart data={data.annual_data} />}
                  {hasEPS && <AnnualEPSChart data={data.annual_data} />}
                </div>
              )}
            </>
          )}
          {data.quarterly_earnings?.length > 0 && <QuarterlyChart data={data.quarterly_earnings} />}
        </>
      )}

      {/* ── Private: funding + growth + milestones + traction ── */}
      {isPrivate && (
        <>
          <PrivateFinancialNote />
          <FundingSection funding={data.funding} />
          <GrowthSignalsSection signals={data.growth_signals} />
          {data.milestones?.length > 0 && <MilestoneTimeline milestones={data.milestones} />}
          <MarketTractionSection traction={data.market_traction} />
          {data.financial_summary && (
            <Section title="Investment Commentary" tag="OpenRouter">
              <p className="summary-text">{data.financial_summary}</p>
            </Section>
          )}
        </>
      )}

      {!isPrivate && data.snapshot?.ticker && (
        <MarketVoices
          ticker={data.snapshot.ticker}
          analystActions={data.analyst_sentiment?.recent_actions}
        />
      )}

      <PositioningSection pos={data.positioning} />

      <Section title="SWOT Analysis" tag="OpenRouter">
        <SwotGrid swot={data.swot} />
      </Section>

      {(data.competitors || []).length > 0 && (
        <Section title="Competitive Landscape" tag="OpenRouter">
          <div className="competitor-list">
            {data.competitors.map((c, i) => (
              <CompetitorCard key={i} c={c} onSearch={onSearch} />
            ))}
          </div>
        </Section>
      )}

      <SourcesAndNews sources={data.sources} company={data.company} ticker={data.snapshot?.ticker} />
    </div>
  )
}

// ─── Company Type Badge ───────────────────────────────────────────────────────

function CompanyTypeBadge({ type, stage }) {
  return (
    <div className={`company-type-badge ${type}`}>
      <span className="type-label">{type === 'private' ? 'Private' : 'Public'}</span>
      {stage && <span className="type-stage">{stage}</span>}
    </div>
  )
}

// ─── Private Financial Note ───────────────────────────────────────────────────

function PrivateFinancialNote() {
  const missing = ['Revenue', 'EPS', 'Profit Margin', 'Cash Flow', 'P/E Ratio', 'Market Cap']
  const available = ['Funding history & investors', 'Hiring & employee growth', 'Company milestones', 'Market traction & customers', 'Partnerships', 'Competitive landscape']
  return (
    <Section title="Financial Information">
      <div className="private-financial-note">
        <p>This company is privately held and does not publicly disclose audited financial statements. Traditional metrics are unavailable — this report focuses on what's actually knowable.</p>
        <div className="private-note-cols">
          <div className="private-note-col missing">
            <div className="private-note-col-label">Not Available</div>
            {missing.map(m => <div key={m} className="private-note-item missing">{m}</div>)}
          </div>
          <div className="private-note-col available">
            <div className="private-note-col-label">This Report Covers</div>
            {available.map(a => <div key={a} className="private-note-item available">{a}</div>)}
          </div>
        </div>
      </div>
    </Section>
  )
}

// ─── Funding Section ──────────────────────────────────────────────────────────

function FundingSection({ funding }) {
  if (!funding) return null
  const hasTopLine = funding.total_raised || funding.latest_round || funding.latest_amount || funding.lead_investor
  const hasInvestors = funding.all_investors?.length > 0
  const hasRounds = funding.rounds?.length > 0
  if (!hasTopLine && !hasInvestors && !hasRounds) return null

  return (
    <Section title="Funding" tag="Tavily">
      {hasTopLine && (
        <div className="snapshot-grid" style={{ marginBottom: hasInvestors || hasRounds ? 18 : 0 }}>
          {funding.total_raised && (
            <div className="snapshot-stat">
              <span className="stat-label">Total Raised</span>
              <span className="stat-value">{funding.total_raised}</span>
            </div>
          )}
          {funding.latest_round && (
            <div className="snapshot-stat">
              <span className="stat-label">Latest Round</span>
              <span className="stat-value">{funding.latest_round}</span>
            </div>
          )}
          {funding.latest_amount && (
            <div className="snapshot-stat">
              <span className="stat-label">Round Size</span>
              <span className="stat-value">{funding.latest_amount}</span>
            </div>
          )}
          {funding.lead_investor && (
            <div className="snapshot-stat">
              <span className="stat-label">Lead Investor</span>
              <span className="stat-value">{funding.lead_investor}</span>
            </div>
          )}
        </div>
      )}

      {hasInvestors && (
        <div style={{ marginBottom: hasRounds ? 18 : 0 }}>
          <div className="stat-label" style={{ marginBottom: 8 }}>All Investors</div>
          <div className="investor-tags">
            {funding.all_investors.map((inv, i) => <span key={i} className="investor-tag">{inv}</span>)}
          </div>
        </div>
      )}

      {hasRounds && (
        <div className="funding-rounds">
          <div className="stat-label" style={{ marginBottom: 10 }}>Funding Rounds</div>
          {funding.rounds.map((r, i) => (
            <div key={i} className="funding-round-row">
              <span className="round-type">{r.round_type}</span>
              {r.amount && <span className="round-amount">{r.amount}</span>}
              {r.date && <span className="round-date">{r.date}</span>}
              {r.lead_investor && <span className="round-lead">Led by {r.lead_investor}</span>}
            </div>
          ))}
        </div>
      )}
    </Section>
  )
}

// ─── Growth Signals ───────────────────────────────────────────────────────────

function GrowthSignalsSection({ signals }) {
  if (!signals) return null
  const hasData = signals.employee_count || signals.employee_growth_pct ||
    signals.hiring_activity || signals.open_positions || signals.new_locations?.length > 0
  if (!hasData) return null

  return (
    <Section title="Growth Signals" tag="Tavily">
      <div className="snapshot-grid">
        {signals.employee_count && (
          <div className="snapshot-stat">
            <span className="stat-label">Employees</span>
            <span className="stat-value">{signals.employee_count}</span>
          </div>
        )}
        {signals.employee_growth_pct && (
          <div className="snapshot-stat">
            <span className="stat-label">Employee Growth</span>
            <span className="stat-value">
              +{signals.employee_growth_pct}%{signals.employee_growth_period ? ` (${signals.employee_growth_period})` : ''}
            </span>
          </div>
        )}
        {signals.hiring_activity && (
          <div className="snapshot-stat">
            <span className="stat-label">Hiring Activity</span>
            <span className="stat-value">{signals.hiring_activity}</span>
          </div>
        )}
        {signals.open_positions && (
          <div className="snapshot-stat">
            <span className="stat-label">Open Positions</span>
            <span className="stat-value">{signals.open_positions}</span>
          </div>
        )}
      </div>
      {signals.new_locations?.length > 0 && (
        <div style={{ marginTop: 14 }}>
          <div className="stat-label" style={{ marginBottom: 8 }}>Locations</div>
          <div className="investor-tags">
            {signals.new_locations.map((loc, i) => <span key={i} className="investor-tag">{loc}</span>)}
          </div>
        </div>
      )}
    </Section>
  )
}

// ─── Milestone Timeline ───────────────────────────────────────────────────────

function MilestoneTimeline({ milestones }) {
  if (!milestones?.length) return null
  return (
    <Section title="Company Timeline" tag="OpenRouter">
      <div className="milestone-timeline">
        {milestones.map((m, i) => (
          <div key={i} className="milestone-item">
            <div className="milestone-year">{m.year}</div>
            <div className="milestone-connector">
              <div className="milestone-dot" />
              {i < milestones.length - 1 && <div className="milestone-line" />}
            </div>
            <div className="milestone-event">{m.event}</div>
          </div>
        ))}
      </div>
    </Section>
  )
}

// ─── Market Traction ──────────────────────────────────────────────────────────

function MarketTractionSection({ traction }) {
  if (!traction) return null
  const hasMetrics = traction.arr || traction.estimated_revenue || traction.mau
  const hasCustomers = traction.customers?.length > 0 || traction.enterprise_clients?.length > 0
  const hasPartners = traction.partnerships?.length > 0
  if (!hasMetrics && !hasCustomers && !hasPartners) return null

  const allCustomers = [...(traction.customers || []), ...(traction.enterprise_clients || [])].filter((v, i, a) => a.indexOf(v) === i)

  return (
    <Section title="Market Traction" tag="Tavily">
      {hasMetrics && (
        <div className="snapshot-grid" style={{ marginBottom: hasCustomers || hasPartners ? 18 : 0 }}>
          {traction.arr && (
            <div className="snapshot-stat">
              <span className="stat-label">ARR</span>
              <span className="stat-value">{traction.arr}</span>
            </div>
          )}
          {traction.estimated_revenue && (
            <div className="snapshot-stat">
              <span className="stat-label">Est. Revenue</span>
              <span className="stat-value">{traction.estimated_revenue}</span>
            </div>
          )}
          {traction.mau && (
            <div className="snapshot-stat">
              <span className="stat-label">Monthly Active Users</span>
              <span className="stat-value">{traction.mau}</span>
            </div>
          )}
        </div>
      )}
      {hasCustomers && (
        <div style={{ marginBottom: hasPartners ? 14 : 0 }}>
          <div className="stat-label" style={{ marginBottom: 8 }}>Notable Customers</div>
          <div className="investor-tags">
            {allCustomers.map((c, i) => <span key={i} className="investor-tag">{c}</span>)}
          </div>
        </div>
      )}
      {hasPartners && (
        <div>
          <div className="stat-label" style={{ marginBottom: 8 }}>Partnerships</div>
          <div className="investor-tags">
            {traction.partnerships.map((p, i) => <span key={i} className="investor-tag">{p}</span>)}
          </div>
        </div>
      )}
    </Section>
  )
}

// ─── Header Logo (3-tier fallback) ───────────────────────────────────────────

function HeaderLogo({ url, name }) {
  const [idx, setIdx] = useState(0)
  const initial = (name || '?')[0].toUpperCase()

  // Build fallback chain: backend URL → guessed icon.horse → Google favicon 128px
  const guessed = guessLogoUrl(name || '')
  const gFavicon = name ? `https://www.google.com/s2/favicons?domain=${(name || '').toLowerCase().replace(/[^a-z0-9]/g, '')}.com&sz=128` : null
  const chain = [url, guessed, gFavicon].filter(Boolean).filter((v, i, a) => a.indexOf(v) === i)

  if (!chain.length || idx >= chain.length) {
    return <div className="company-logo company-logo-initial">{initial}</div>
  }
  return (
    <img
      src={chain[idx]}
      alt={name}
      className="company-logo"
      onError={() => setIdx(i => i + 1)}
    />
  )
}

// ─── Confidence ───────────────────────────────────────────────────────────────

function ConfidencePill({ score, sources }) {
  const color = score >= 80 ? '#1a7a48' : score >= 60 ? '#a06010' : '#a02020'
  return (
    <div className="confidence-pill-wrapper" tabIndex={0} aria-label="AI Confidence Score description">
      <div className="confidence-pill" style={{ borderColor: color }}>
        <span className="confidence-score" style={{ color }}>{score}</span>
        <span className="confidence-label">confidence</span>
        <span className="confidence-sources">{sources} sources</span>
      </div>
      <div className="confidence-tooltip">
        <div className="confidence-tooltip-title">AI Confidence Score</div>
        <p>Reflects how much verified, recent public information was available for this company when the report was generated.</p>
        <div className="confidence-tooltip-ranges">
          <div><span style={{ color: '#1a7a48', fontWeight: 700 }}>90 – 100</span> Rich data, multiple verified sources</div>
          <div><span style={{ color: '#1a7a48', fontWeight: 700 }}>70 – 89</span> Good coverage, minor gaps</div>
          <div><span style={{ color: '#a06010', fontWeight: 700 }}>50 – 69</span> Significant gaps or older data</div>
          <div><span style={{ color: '#a02020', fontWeight: 700 }}>0 – 49</span> Very limited public information</div>
        </div>
      </div>
    </div>
  )
}

// ─── Snapshot ─────────────────────────────────────────────────────────────────

function Snapshot({ snap }) {
  if (!snap?.ticker && !snap?.market_cap) return null

  const stats = [
    { label: 'CEO', value: snap.ceo },
    { label: 'Headquarters', value: snap.headquarters },
    { label: 'Sector', value: snap.sector },
    { label: 'Industry', value: snap.industry },
    { label: 'Employees', value: snap.employees?.toLocaleString() },
    { label: 'Market Cap', value: snap.market_cap, source: 'FMP' },
    { label: 'Revenue (TTM)', value: snap.revenue, source: 'FMP' },
    { label: 'Net Income', value: snap.net_income, source: 'FMP' },
    { label: 'Operating Income', value: snap.operating_income, source: 'FMP' },
    { label: 'Cash on Hand', value: snap.cash, source: 'FMP' },
    { label: 'Total Debt', value: snap.total_debt, source: 'FMP' },
  ].filter(s => s.value)

  return (
    <Section title="Company Snapshot" tag="FMP">
      <div className="snapshot-grid">
        {stats.map(s => (
          <div key={s.label} className="snapshot-stat">
            <span className="stat-label">{s.label}</span>
            <span className="stat-value">{s.value}</span>
            {s.source && (
              <span className="stat-source">{s.source}</span>
            )}
          </div>
        ))}
        {snap.website && (
          <div className="snapshot-stat">
            <span className="stat-label">Website</span>
            <a className="stat-value link" href={snap.website} target="_blank" rel="noreferrer">
              {snap.website.replace(/^https?:\/\//, '')}
            </a>
          </div>
        )}
      </div>
      {snap.wiki_summary && (
        <div className="wiki-block">
          <p className="wiki-summary">{snap.wiki_summary}</p>
          <div className="wiki-actions">
            {snap.wiki_url && (
              <a href={snap.wiki_url} target="_blank" rel="noreferrer" className="wiki-read-more">
                Read more on Wikipedia →
              </a>
            )}
          </div>
        </div>
      )}
    </Section>
  )
}

// ─── Stock Chart ──────────────────────────────────────────────────────────────

const PERIODS = ['1d', '1mo', '6mo', '1y', '5y']
const PERIOD_LABELS = { '1d': '1D', '1mo': '1M', '6mo': '6M', '1y': '1Y', '5y': '5Y' }

function StockChart({ initialData, ticker }) {
  const [period, setPeriod] = useState('1y')
  const [data, setData] = useState(initialData || [])
  const [fetching, setFetching] = useState(false)

  const loadPeriod = useCallback(async (p) => {
    if (!ticker) return
    if (p === '1y' && initialData?.length) { setData(initialData); setPeriod(p); return }
    setFetching(true)
    setPeriod(p)
    try {
      const res = await fetch(`${BACKEND}/stock/${ticker}?period=${p}`)
      const json = await res.json()
      setData(json.data || [])
    } catch { setData([]) }
    finally { setFetching(false) }
  }, [ticker, initialData])

  if (!data?.length && !ticker) return null

  const closes = data.map(d => d.close).filter(Boolean)
  const min = closes.length ? Math.min(...closes) : 0
  const max = closes.length ? Math.max(...closes) : 0
  const pad = (max - min) * 0.05

  const CustomTooltip = ({ active, payload, label }) => {
    if (!active || !payload?.length) return null
    const d = payload[0].payload
    const color = (d.change ?? 0) >= 0 ? '#1a7a48' : '#a02020'
    return (
      <div className="chart-tooltip">
        <div className="tooltip-date">{label}</div>
        <div className="tooltip-close">${d.close?.toFixed(2)}</div>
        <div className="tooltip-change" style={{ color }}>
          {(d.change ?? 0) >= 0 ? '+' : ''}{d.change?.toFixed(2)} ({d.change_pct?.toFixed(2)}%)
        </div>
      </div>
    )
  }

  return (
    <Section title={`Stock Performance${ticker ? ` · ${ticker}` : ''}`} action={<span className="section-source-tag">FMP</span>}>
      <div className="chart-controls">
        {PERIODS.map(p => (
          <button
            key={p}
            className={`period-btn ${period === p ? 'active' : ''}`}
            onClick={() => loadPeriod(p)}
            disabled={fetching}
          >{PERIOD_LABELS[p]}</button>
        ))}
      </div>
      {fetching ? (
        <div className="chart-loading"><div className="spinner small" /></div>
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e4e4dc" />
            <XAxis dataKey="date" tickFormatter={d => period === '1d' ? d.slice(11, 16) : d.slice(5)} tick={{ fontSize: 11, fill: '#a0a0a0' }} axisLine={false} tickLine={false} />
            <YAxis domain={[min - pad, max + pad]} tickFormatter={v => `$${v.toFixed(0)}`} tick={{ fontSize: 11, fill: '#a0a0a0' }} axisLine={false} tickLine={false} width={56} />
            <Tooltip content={<CustomTooltip />} />
            <Line type="monotone" dataKey="close" stroke="#1e3a6e" dot={false} strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
      )}
    </Section>
  )
}

// ─── Public Market Intel ──────────────────────────────────────────────────────

function PublicMarketIntel({ sentiment, earnings }) {
  if (!sentiment && !earnings) return null
  return (
    <div className="two-col">
      <AnalystSentimentSection sentiment={sentiment} />
      <EarningsInfoSection earnings={earnings} />
    </div>
  )
}

function AnalystSentimentSection({ sentiment }) {
  if (!sentiment) return null
  const targetSpread = [
    sentiment.target_low_price != null && `Low ${money(sentiment.target_low_price)}`,
    sentiment.target_median_price != null && `Median ${money(sentiment.target_median_price)}`,
    sentiment.target_high_price != null && `High ${money(sentiment.target_high_price)}`,
  ].filter(Boolean).join(' · ')

  const stats = [
    { label: 'Consensus', value: sentiment.consensus },
    { label: 'Mean Rating', value: fix(sentiment.recommendation_mean, 2), sub: '1 = Strong Buy, 5 = Sell' },
    { label: 'Analysts', value: sentiment.analyst_count },
    { label: 'Mean Target', value: money(sentiment.target_mean_price), sub: sentiment.current_price != null ? `Current ${money(sentiment.current_price)}` : null },
  ].filter(i => i.value != null)

  if (!stats.length && !sentiment.recent_actions?.length) return null

  return (
    <Section
      title={`Analyst Sentiment${sentiment.data_as_of ? ` · as of ${sentiment.data_as_of}` : ''}`}
      action={<span className="section-source-tag">FMP</span>}
    >
      {stats.length > 0 && (
        <div className="intel-stat-grid">
          {stats.map(item => (
            <div key={item.label} className="intel-stat">
              <span className="stat-label">{item.label}</span>
              <strong>{item.value}</strong>
              {item.sub && <small>{item.sub}</small>}
            </div>
          ))}
        </div>
      )}
      {targetSpread && <div className="intel-note">{targetSpread}</div>}
      {sentiment.recent_actions?.length > 0 && (
        <div className="rating-actions">
          <div className="subsection-label">Recent Rating Actions</div>
          {sentiment.recent_actions.slice(0, 4).map((a, i) => (
            <div key={`${a.firm}-${a.date}-${i}`} className="rating-action-row">
              <div>
                <strong>{a.firm}</strong>
                <span>{[a.action, a.to_grade].filter(Boolean).join(' to ')}</span>
              </div>
              <small>{fmtDate(a.date)}</small>
            </div>
          ))}
        </div>
      )}
    </Section>
  )
}

function EarningsInfoSection({ earnings }) {
  if (!earnings) return null
  const stats = [
    { label: 'Next Earnings', value: fmtDate(earnings.next_earnings_date) },
    { label: 'Previous Earnings', value: fmtDate(earnings.previous_earnings_date) },
    { label: 'EPS Estimate', value: earnings.eps_estimate != null ? `$${fix(earnings.eps_estimate)}` : null },
    { label: 'Reported EPS', value: earnings.eps_actual != null ? `$${fix(earnings.eps_actual)}` : null },
    { label: 'EPS Surprise', value: earnings.eps_surprise != null ? `$${fix(earnings.eps_surprise)}` : null, sub: earnings.eps_surprise_pct != null ? `${fix(earnings.eps_surprise_pct * 100, 1)}%` : null },
    { label: 'Revenue Estimate', value: earnings.revenue_estimate },
    { label: 'Revenue Actual', value: earnings.revenue_actual },
    { label: 'Revenue Surprise', value: earnings.revenue_surprise, sub: earnings.revenue_surprise_pct != null ? `${fix(earnings.revenue_surprise_pct * 100, 1)}%` : null },
  ].filter(i => i.value != null)

  if (!stats.length) return null

  return (
    <Section
      title={`Earnings Information${earnings.data_as_of ? ` · as of ${earnings.data_as_of}` : ''}`}
      action={<span className="section-source-tag">FMP</span>}
    >
      <div className="intel-stat-grid">
        {stats.map(item => (
          <div key={item.label} className="intel-stat">
            <span className="stat-label">{item.label}</span>
            <strong>{item.value}</strong>
            {item.sub && <small>{item.sub}</small>}
          </div>
        ))}
      </div>
    </Section>
  )
}

// ─── Financial Metrics ────────────────────────────────────────────────────────

function FinancialMetrics({ ratios, summary }) {
  if (!ratios) return null

  const groups = [
    {
      label: 'Valuation',
      items: [
        { label: 'P/E', value: fix(ratios.pe_ratio, 1), sub: 'Price / Earnings' },
        { label: 'P/B', value: fix(ratios.pb_ratio), sub: 'Price / Book' },
        { label: 'P/S', value: fix(ratios.ps_ratio), sub: 'Price / Sales' },
        { label: 'EV/EBITDA', value: fix(ratios.ev_ebitda, 1), sub: 'Enterprise Value' },
      ],
    },
    {
      label: 'Per Share & Cash',
      items: [
        { label: 'EPS', value: ratios.eps != null ? `$${fix(ratios.eps)}` : null, sub: 'Earnings Per Share' },
        { label: 'FCF', value: ratios.fcf, sub: 'Free Cash Flow' },
        { label: 'Dividend Yield', value: ratios.dividend_yield != null ? `${ratios.dividend_yield.toFixed(2)}%` : null, sub: 'Annual Yield' },
      ],
    },
    {
      label: 'Growth',
      items: [
        { label: 'Revenue Growth', value: pct(ratios.revenue_growth), sub: 'Year-over-Year' },
        { label: 'Earnings Growth', value: pct(ratios.earnings_growth), sub: 'Year-over-Year' },
      ],
    },
    {
      label: 'Profitability',
      items: [
        { label: 'Gross Margin', value: pct(ratios.gross_margin), sub: 'Gross Profit / Revenue' },
        { label: 'Operating Margin', value: pct(ratios.operating_margin), sub: 'EBIT / Revenue' },
        { label: 'Net Margin', value: pct(ratios.net_margin), sub: 'Net Income / Revenue' },
        { label: 'ROE', value: pct(ratios.roe), sub: 'Return on Equity' },
        { label: 'ROA', value: pct(ratios.roa), sub: 'Return on Assets' },
      ],
    },
    {
      label: 'Leverage & Liquidity',
      items: [
        { label: 'Debt / Equity', value: fix(ratios.debt_to_equity), sub: 'Leverage Ratio' },
        { label: 'Current Ratio', value: fix(ratios.current_ratio), sub: 'Current / Liabilities' },
        { label: 'Quick Ratio', value: fix(ratios.quick_ratio), sub: 'Liquid / Liabilities' },
      ],
    },
  ]

  const hasAny = groups.some(g => g.items.some(i => i.value != null))
  if (!hasAny) return null

  return (
    <Section
      title={`Financial Metrics${ratios.data_as_of ? ` · as of ${ratios.data_as_of}` : ''}`}
      action={<span className="section-source-tag">FMP</span>}
    >
      <div className="metrics-board">
        {groups.map(g => {
          const visible = g.items.filter(i => i.value != null)
          if (!visible.length) return null
          return (
            <div key={g.label} className="metrics-group-block">
              <div className="metrics-group-header">{g.label}</div>
              <div className="metrics-tile-row">
                {visible.map(item => (
                  <div key={item.label} className="metric-tile">
                    <div className="metric-tile-value">{item.value}</div>
                    <div className="metric-tile-label">{item.label}</div>
                    <div className="metric-tile-sub">{item.sub}</div>
                  </div>
                ))}
              </div>
            </div>
          )
        })}
      </div>

      {summary && (
        <div className="financial-summary-block">
          <div className="financial-summary-label">AI Financial Analysis</div>
          <p className="financial-summary-text">{summary}</p>
        </div>
      )}
    </Section>
  )
}

// ─── Annual Charts ────────────────────────────────────────────────────────────

// Shared navy hatch pattern — diagonal stripes, used by all bar charts
function NavyHatchDefs({ id }) {
  return (
    <defs>
      <pattern id={id} patternUnits="userSpaceOnUse" width="7" height="7" patternTransform="rotate(-45 0 0)">
        <rect width="7" height="7" fill="#d8e4f4" />
        <line x1="0" y1="0" x2="0" y2="7" stroke="#1e3a6e" strokeWidth="3" />
      </pattern>
    </defs>
  )
}

function AnnualRevenueChart({ data }) {
  return (
    <Section title="Annual Revenue & Gross Profit ($B)" action={<span className="section-source-tag">FMP</span>}>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <NavyHatchDefs id="hatch-rev" />
          <CartesianGrid strokeDasharray="3 3" stroke="#e4e4dc" />
          <XAxis dataKey="year" tick={{ fontSize: 11, fill: '#a0a0a0' }} axisLine={false} tickLine={false} />
          <YAxis tick={{ fontSize: 11, fill: '#a0a0a0' }} axisLine={false} tickLine={false} unit="B" width={40} />
          <Tooltip formatter={v => v != null ? `$${v}B` : '—'} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Bar dataKey="revenue" fill="#1e3a6e" name="Revenue" radius={[3, 3, 0, 0]} />
          <Bar dataKey="gross_profit" fill="url(#hatch-rev)" name="Gross Profit" radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </Section>
  )
}

function AnnualIncomeChart({ data }) {
  return (
    <Section title="Annual Operating & Net Income ($B)" action={<span className="section-source-tag">FMP</span>}>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <NavyHatchDefs id="hatch-inc" />
          <CartesianGrid strokeDasharray="3 3" stroke="#e4e4dc" />
          <XAxis dataKey="year" tick={{ fontSize: 11, fill: '#a0a0a0' }} axisLine={false} tickLine={false} />
          <YAxis tick={{ fontSize: 11, fill: '#a0a0a0' }} axisLine={false} tickLine={false} unit="B" width={40} />
          <Tooltip formatter={v => v != null ? `$${v}B` : '—'} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Bar dataKey="operating_income" fill="#1e3a6e" name="Operating Income" radius={[3, 3, 0, 0]} />
          <Bar dataKey="net_income" fill="url(#hatch-inc)" name="Net Income" radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </Section>
  )
}

function AnnualFCFChart({ data }) {
  return (
    <Section title="Annual Free Cash Flow ($B)" action={<span className="section-source-tag">FMP</span>}>
      <ResponsiveContainer width="100%" height={180}>
        <BarChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e4e4dc" />
          <XAxis dataKey="year" tick={{ fontSize: 11, fill: '#a0a0a0' }} axisLine={false} tickLine={false} />
          <YAxis tick={{ fontSize: 11, fill: '#a0a0a0' }} axisLine={false} tickLine={false} unit="B" width={40} />
          <Tooltip formatter={v => v != null ? `$${v}B` : '—'} />
          <Bar dataKey="fcf" fill="#2a4f9a" name="Free Cash Flow" radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </Section>
  )
}

function AnnualEPSChart({ data }) {
  return (
    <Section title="Annual EPS" action={<span className="section-source-tag">FMP</span>}>
      <ResponsiveContainer width="100%" height={180}>
        <LineChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e4e4dc" />
          <XAxis dataKey="year" tick={{ fontSize: 11, fill: '#a0a0a0' }} axisLine={false} tickLine={false} />
          <YAxis tick={{ fontSize: 11, fill: '#a0a0a0' }} axisLine={false} tickLine={false} tickFormatter={v => `$${v.toFixed(1)}`} width={48} />
          <Tooltip formatter={v => v != null ? `$${v.toFixed(2)}` : '—'} />
          <Line type="monotone" dataKey="eps" stroke="#1e3a6e" strokeWidth={2} dot={{ fill: '#1e3a6e', r: 4 }} name="EPS" />
        </LineChart>
      </ResponsiveContainer>
    </Section>
  )
}

// ─── Quarterly Chart ──────────────────────────────────────────────────────────

function QuarterlyChart({ data }) {
  const [showAll, setShowAll] = useState(false)
  const visible = showAll ? data : data.slice(-6)

  return (
    <Section title="Quarterly Revenue vs Net Income ($B)" action={<span className="section-source-tag">FMP</span>}>
      <div className="chart-controls">
        <button className={`period-btn ${!showAll ? 'active' : ''}`} onClick={() => setShowAll(false)}>Last 6Q</button>
        <button className={`period-btn ${showAll ? 'active' : ''}`} onClick={() => setShowAll(true)}>All</button>
      </div>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={visible} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <NavyHatchDefs id="hatch-qtr" />
          <CartesianGrid strokeDasharray="3 3" stroke="#e4e4dc" />
          <XAxis dataKey="quarter" tickFormatter={d => d.slice(0, 7)} tick={{ fontSize: 10, fill: '#a0a0a0' }} axisLine={false} tickLine={false} />
          <YAxis tick={{ fontSize: 11, fill: '#a0a0a0' }} axisLine={false} tickLine={false} unit="B" width={40} />
          <Tooltip formatter={v => v != null ? `$${v}B` : '—'} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Bar dataKey="revenue" fill="#1e3a6e" name="Revenue" radius={[3, 3, 0, 0]} />
          <Bar dataKey="net_income" fill="url(#hatch-qtr)" name="Net Income" radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </Section>
  )
}

// ─── Positioning ──────────────────────────────────────────────────────────────

function PositioningSection({ pos }) {
  if (!pos) return null
  const items = [
    { label: 'Overview', value: pos.overview },
    { label: 'Primary Customer Base', value: pos.primary_customer_base },
    { label: 'Competitive Advantage', value: pos.competitive_advantage },
    { label: 'Brand Perception', value: pos.brand_perception },
    { label: 'Pricing Strategy', value: pos.pricing_strategy },
    { label: 'Business Model', value: pos.business_model },
    { label: 'Market Differentiation', value: pos.market_differentiation },
  ].filter(i => i.value)
  if (!items.length) return null
  return (
    <Section title="Positioning" tag="OpenRouter">
      <div className="positioning-list">
        {items.map(item => (
          <div key={item.label} className="positioning-item">
            <span className="positioning-label">{item.label}</span>
            <span className="positioning-value">{item.value}</span>
          </div>
        ))}
      </div>
    </Section>
  )
}

// ─── SWOT ─────────────────────────────────────────────────────────────────────

function SwotGrid({ swot }) {
  if (!swot) return null
  const quadrants = [
    { key: 'strengths',    label: 'Strengths',    color: '#1a7a48', bg: 'rgba(26,122,72,.05)',   border: 'rgba(26,122,72,.18)'   },
    { key: 'weaknesses',   label: 'Weaknesses',   color: '#a02020', bg: 'rgba(160,32,32,.05)',   border: 'rgba(160,32,32,.18)'   },
    { key: 'opportunities',label: 'Opportunities',color: '#1a5090', bg: 'rgba(26,80,144,.05)',   border: 'rgba(26,80,144,.18)'   },
    { key: 'threats',      label: 'Threats',      color: '#9a6010', bg: 'rgba(154,96,16,.05)',   border: 'rgba(154,96,16,.18)'   },
  ]
  return (
    <div className="swot-grid">
      {quadrants.map(q => (
        <div key={q.key} className="swot-quadrant" style={{ background: q.bg, borderColor: q.border }}>
          <div className="swot-label" style={{ color: q.color }}>{q.label}</div>
          <ul>
            {(swot[q.key] || []).map((item, i) => (
              <li key={i} style={{ '--dot-color': q.color }}>{item}</li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  )
}

// ─── Competitor Card ──────────────────────────────────────────────────────────

function CompetitorLogo({ logoUrl, name }) {
  const [idx, setIdx] = useState(0)
  const initials = name.split(' ').slice(0, 2).map(w => w[0]).join('').toUpperCase()

  // Three-tier fallback: backend URL → guessed icon.horse → Google favicon 128px
  const guessed = useMemo(() => guessLogoUrl(name), [name])
  const gFavicon = useMemo(() => {
    const slug = name.replace(/\s+(Inc|Corp|Ltd|LLC|Group|Holdings?|Technologies?|Co|Platforms?)\.?\s*$/i, '').toLowerCase().replace(/[^a-z0-9]/g, '')
    return slug.length >= 2 ? `https://www.google.com/s2/favicons?domain=${slug}.com&sz=128` : null
  }, [name])

  const chain = useMemo(
    () => [logoUrl, guessed, gFavicon].filter(Boolean).filter((v, i, a) => a.indexOf(v) === i),
    [logoUrl, guessed, gFavicon]
  )

  if (!chain.length || idx >= chain.length) {
    return <div className="competitor-logo-fallback">{initials}</div>
  }
  return (
    <img
      src={chain[idx]}
      alt={name}
      className="competitor-logo-lg"
      onError={() => setIdx(i => i + 1)}
    />
  )
}

function CompetitorCard({ c, onSearch }) {
  return (
    <div className="competitor-card">
      <div className="competitor-card-top">
        <CompetitorLogo logoUrl={c.logo_url} name={c.name} />
        <div className="competitor-identity">
          <div className="competitor-name">{c.name}</div>
          {c.ticker && <span className="competitor-ticker">{c.ticker}</span>}
          {c.industry && <div className="competitor-industry">{c.industry}</div>}
        </div>
        <div className="competitor-card-right">
          {(c.market_cap || c.revenue) && (
            <div className="competitor-financials">
              {c.market_cap && (
                <div className="comp-fin-item">
                  <span>Mkt Cap</span>
                  <strong>{c.market_cap}</strong>
                </div>
              )}
              {c.revenue && (
                <div className="comp-fin-item">
                  <span>Revenue</span>
                  <strong>{c.revenue}</strong>
                </div>
              )}
            </div>
          )}
          <button className="comp-research-btn" onClick={() => onSearch(c.name)}>
            Research ↗
          </button>
        </div>
      </div>
      <p className="competitor-note">{c.note}</p>
      {c.overlapping_products?.length > 0 && (
        <div className="overlap-tags">
          <span className="overlap-label">Overlapping:</span>
          {c.overlapping_products.map((p, i) => (
            <span key={i} className="overlap-tag">{p}</span>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Source Card ──────────────────────────────────────────────────────────────

function SourceCard({ s, ogImage }) {
  const [imgFailed, setImgFailed] = useState(false)
  const domain = getDomain(s.url)
  const favicon = `https://www.google.com/s2/favicons?domain=${domain}&sz=32`
  const dateStr = fmtDate(s.date)
  const bgColor = domainColor(domain)
  const showBrand = !ogImage || imgFailed

  return (
    <a href={s.url} target="_blank" rel="noreferrer" className="source-card">
      {/* Image area — always present for consistency */}
      <div className="source-card-img-area" style={{ background: showBrand ? bgColor : undefined }}>
        {!showBrand ? (
          <img
            src={ogImage}
            alt=""
            className="source-card-image"
            onError={() => setImgFailed(true)}
          />
        ) : (
          <img
            src={favicon}
            alt={domain}
            className="source-placeholder-favicon"
            onError={e => { e.target.style.display = 'none' }}
          />
        )}
      </div>
      {/* Card body */}
      <div className="source-card-body">
        <div className="source-card-meta">
          <img src={favicon} alt="" className="source-favicon-sm" onError={e => { e.target.style.display = 'none' }} />
          <span className="source-publisher">{domain}</span>
          {dateStr && <span className="source-date">{dateStr}</span>}
        </div>
        <div className="source-card-title">{s.title}</div>
      </div>
    </a>
  )
}

// ─── News Item ────────────────────────────────────────────────────────────────

function NewsItem({ a, preview }) {
  const [imgFailed, setImgFailed] = useState(false)
  const domain = getDomain(a.url)
  const favicon = `https://www.google.com/s2/favicons?domain=${domain}&sz=32`
  const bgColor = domainColor(domain)
  const dateStr = fmtDate(a.date)
  const showPreview = preview && !imgFailed

  return (
    <a href={a.url} target="_blank" rel="noreferrer" className="news-item">
      <div className="news-item-img" style={{ background: bgColor }}>
        {showPreview ? (
          <img src={preview} alt="" className="news-item-img-preview" onError={() => setImgFailed(true)} />
        ) : (
          <img src={favicon} alt="" className="source-placeholder-favicon" onError={e => { e.target.style.display = 'none' }} />
        )}
      </div>
      <div className="news-item-body">
        <div className="news-item-meta">
          <span className="source-publisher">{domain}</span>
          {dateStr && <span className="source-date">{dateStr}</span>}
        </div>
        <div className="news-item-title">{a.title}</div>
        {a.snippet && <div className="news-item-snippet">{a.snippet}</div>}
      </div>
    </a>
  )
}

// ─── News date grouping helper ────────────────────────────────────────────────

function groupNewsByRecency(articles) {
  const now = new Date()
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const startOfWeek = new Date(startOfToday); startOfWeek.setDate(startOfToday.getDate() - 7)
  const startOfMonth = new Date(startOfToday); startOfMonth.setDate(startOfToday.getDate() - 30)

  const groups = { today: [], week: [], month: [], older: [] }
  for (const a of articles) {
    if (!a.date) { groups.older.push(a); continue }
    const d = new Date(a.date)
    if (isNaN(d.getTime())) { groups.older.push(a); continue }
    if (d >= startOfToday) groups.today.push(a)
    else if (d >= startOfWeek) groups.week.push(a)
    else if (d >= startOfMonth) groups.month.push(a)
    else groups.older.push(a)
  }
  return groups
}

// ─── Sources & News (combined) ────────────────────────────────────────────────

function SourcesAndNews({ sources, company, ticker }) {
  const [news, setNews] = useState(null)
  const [newsLoading, setNewsLoading] = useState(true)
  const [previews, setPreviews] = useState({})

  useEffect(() => {
    setNewsLoading(true)
    const url = ticker
      ? `${BACKEND}/news/${encodeURIComponent(company)}?ticker=${encodeURIComponent(ticker)}`
      : `${BACKEND}/news/${encodeURIComponent(company)}`
    fetch(url)
      .then(r => r.json())
      .then(d => { setNews(d.articles || []); setNewsLoading(false) })
      .catch(() => { setNews([]); setNewsLoading(false) })
  }, [company, ticker])

  useEffect(() => {
    if (!sources?.length) return
    sources.forEach(s => {
      fetch(`${BACKEND}/preview?url=${encodeURIComponent(s.url)}`)
        .then(r => r.json())
        .then(p => { if (p.image) setPreviews(prev => ({ ...prev, [s.url]: p.image })) })
        .catch(() => {})
    })
  }, [sources])

  useEffect(() => {
    if (!news?.length) return
    news.forEach(a => {
      fetch(`${BACKEND}/preview?url=${encodeURIComponent(a.url)}`)
        .then(r => r.json())
        .then(p => { if (p.image) setPreviews(prev => ({ ...prev, [a.url]: p.image })) })
        .catch(() => {})
    })
  }, [news])

  const hasNews = !newsLoading && news?.length > 0
  const hasSources = sources?.length > 0
  if (!newsLoading && !hasNews && !hasSources) return null

  const grouped = hasNews ? groupNewsByRecency(news) : null

  return (
    <Section title="News & Sources">
      {newsLoading ? (
        <div className="news-loading"><div className="spinner small" /><span>Loading latest news…</span></div>
      ) : hasNews ? (
        <div className="news-tiered">
          {grouped.today.length > 0 && (
            <div className="news-tier">
              <div className="news-tier-label">Today</div>
              <div className="news-list">{grouped.today.map((a, i) => <NewsItem key={i} a={a} preview={previews[a.url]} />)}</div>
            </div>
          )}
          {grouped.week.length > 0 && (
            <div className="news-tier">
              <div className="news-tier-label">This Week</div>
              <div className="news-list">{grouped.week.map((a, i) => <NewsItem key={i} a={a} preview={previews[a.url]} />)}</div>
            </div>
          )}
          {grouped.month.length > 0 && (
            <div className="news-tier">
              <div className="news-tier-label">This Month</div>
              <div className="news-list">{grouped.month.map((a, i) => <NewsItem key={i} a={a} preview={previews[a.url]} />)}</div>
            </div>
          )}
          {grouped.older.length > 0 && (grouped.today.length + grouped.week.length + grouped.month.length === 0) && (
            <div className="news-tier">
              <div className="news-tier-label">Recent</div>
              <div className="news-list">{grouped.older.map((a, i) => <NewsItem key={i} a={a} preview={previews[a.url]} />)}</div>
            </div>
          )}
        </div>
      ) : null}

      {hasSources && (
        <>
          <div className="subsection-label" style={{ marginTop: hasNews || newsLoading ? 28 : 0 }}>Research Sources</div>
          <div className="source-cards">
            {sources.map((s, i) => (
              <SourceCard key={i} s={s} ogImage={previews[s.url]} />
            ))}
          </div>
        </>
      )}
    </Section>
  )
}

// ─── Market Voices (analyst upgrades + StockTwits sentiment) ─────────────────

function MarketVoices({ ticker, analystActions }) {
  const [social, setSocial] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!ticker) { setLoading(false); return }
    fetch(`${BACKEND}/social/${encodeURIComponent(ticker)}`)
      .then(r => r.json())
      .then(d => { setSocial(d); setLoading(false) })
      .catch(() => { setSocial({}); setLoading(false) })
  }, [ticker])

  const hasUpgrades = analystActions?.length > 0
  const hasSocial = !loading && social && (social.total > 0 || social.posts?.length > 0)

  if (!hasUpgrades && !hasSocial && !loading) return null

  const actionLabel = (action) => {
    if (!action) return ''
    if (action === 'up') return 'Upgrade'
    if (action === 'down') return 'Downgrade'
    if (action === 'init') return 'Initiated'
    if (action === 'main') return 'Maintained'
    return action.charAt(0).toUpperCase() + action.slice(1)
  }

  const actionClass = (action) => {
    if (!action) return ''
    if (action === 'up') return 'upgrade'
    if (action === 'down') return 'downgrade'
    return 'neutral'
  }

  return (
    <Section title="Market Voices" tag="Tavily">
      <div className="market-voices-grid">

        {/* ── Wall Street Analyst Ratings ── */}
        {hasUpgrades && (
          <div className="voices-col">
            <div className="subsection-label" style={{ marginBottom: 12 }}>Wall Street Analysts</div>
            {analystActions.slice(0, 8).map((a, i) => (
              <div key={i} className={`analyst-action-card ${actionClass(a.action)}`}>
                <div className="analyst-action-header">
                  <strong className="analyst-firm">{a.firm}</strong>
                  <span className={`action-badge action-${actionClass(a.action)}`}>{actionLabel(a.action)}</span>
                </div>
                <div className="analyst-grade-row">
                  {a.from_grade && a.to_grade ? (
                    <span className="analyst-grade-change">
                      <span className="from-grade">{a.from_grade}</span>
                      <span className="grade-arrow">→</span>
                      <strong className="to-grade">{a.to_grade}</strong>
                    </span>
                  ) : (
                    <span className="to-grade">{a.to_grade || a.from_grade || '—'}</span>
                  )}
                  {a.date && <small className="analyst-date">{fmtDate(a.date)}</small>}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* ── StockTwits Social Sentiment ── */}
        {(hasSocial || loading) && (
          <div className="voices-col">
            <div className="subsection-label" style={{ marginBottom: 12 }}>Social Sentiment · StockTwits</div>
            {loading ? (
              <div className="news-loading"><div className="spinner small" /><span>Loading…</span></div>
            ) : (
              <>
                {social.bullish_pct != null && (
                  <div className="sentiment-meter">
                    <div className="sentiment-bar">
                      <div className="sentiment-bull" style={{ width: `${social.bullish_pct}%` }} />
                      <div className="sentiment-bear" style={{ width: `${100 - social.bullish_pct}%` }} />
                    </div>
                    <div className="sentiment-labels">
                      <span className="sentiment-bull-label">
                        {social.bullish_pct}% Bullish <small>({social.bullish_count})</small>
                      </span>
                      <span className="sentiment-bear-label">
                        {100 - social.bullish_pct}% Bearish <small>({social.bearish_count})</small>
                      </span>
                    </div>
                  </div>
                )}
                <div className="st-posts">
                  {(social.posts || []).slice(0, 4).map((p, i) => (
                    <div key={i} className={`st-post ${p.sentiment ? p.sentiment.toLowerCase() : ''}`}>
                      <div className="st-post-header">
                        <span className="st-user">
                          {p.verified && <span className="st-verified">✓</span>}
                          @{p.user}
                        </span>
                        {p.followers > 0 && (
                          <span className="st-followers">
                            {p.followers >= 1000 ? `${(p.followers / 1000).toFixed(1)}K` : p.followers} followers
                          </span>
                        )}
                        {p.sentiment && (
                          <span className={`st-sentiment-badge ${p.sentiment.toLowerCase()}`}>{p.sentiment}</span>
                        )}
                      </div>
                      <p className="st-text">{p.text}</p>
                      {p.date && <small className="st-date">{p.date}</small>}
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        )}

      </div>
    </Section>
  )
}



// ─── Section ──────────────────────────────────────────────────────────────────

const _AI_TAGS = new Set(['OpenRouter'])
function Section({ title, children, action, tag }) {
  return (
    <div className="section">
      <div className="section-header">
        <h3>
          {title}
          {tag && (
            <span className={`section-tag ${_AI_TAGS.has(tag) ? 'section-tag-ai' : 'section-tag-data'}`}>
              {tag}
            </span>
          )}
        </h3>
        {action && <div className="section-action">{action}</div>}
      </div>
      {children}
    </div>
  )
}
