import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useDebounce } from '@/hooks';
import { metadataApi } from '@/services/metadataApi';
import type { SearchHit, SearchMode } from '@/types';
import { ENTITY_ICONS } from '@/utils/format';

/**
 * Catalog search box with live results.
 *
 * Exposes the search mode because the difference matters here: keyword finds exact column
 * names, semantic finds concepts, hybrid blends both.
 */
export function SearchBar({
  onSelect,
  placeholder = 'Search tables, columns, dashboards, KPIs...',
  autoFocus = false,
}: {
  onSelect?: (hit: SearchHit) => void;
  placeholder?: string;
  autoFocus?: boolean;
}) {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [mode, setMode] = useState<SearchMode>('hybrid');
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [loading, setLoading] = useState(false);
  const debounced = useDebounce(query, 300);

  useEffect(() => {
    if (debounced.trim().length < 2) {
      setHits([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    metadataApi
      .search(debounced, mode, 10)
      .then((response) => {
        if (!cancelled) setHits(response.hits);
      })
      .catch(() => {
        if (!cancelled) setHits([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [debounced, mode]);

  const select = (hit: SearchHit) => {
    setQuery('');
    setHits([]);
    if (onSelect) onSelect(hit);
    else navigate(`/assets?urn=${encodeURIComponent(hit.urn)}`);
  };

  return (
    <div style={{ position: 'relative' }}>
      <div className="row" style={{ flexWrap: 'nowrap' }}>
        <input
          className="input"
          value={query}
          autoFocus={autoFocus}
          placeholder={placeholder}
          onChange={(event) => setQuery(event.target.value)}
          aria-label="Search the metadata catalog"
        />
        <select
          className="select"
          style={{ width: 130 }}
          value={mode}
          onChange={(event) => setMode(event.target.value as SearchMode)}
          aria-label="Search mode"
        >
          <option value="hybrid">Hybrid</option>
          <option value="keyword">Keyword</option>
          <option value="semantic">Semantic</option>
        </select>
      </div>

      {loading && <div className="faint small" style={{ marginTop: 6 }}>Searching...</div>}

      {hits.length > 0 && (
        <ul
          className="card"
          style={{ position: 'absolute', zIndex: 20, left: 0, right: 0, marginTop: 6, listStyle: 'none', padding: 8 }}
        >
          {hits.map((hit) => (
            <li key={hit.urn}>
              <button
                type="button"
                className="nav-link"
                style={{ width: '100%', textAlign: 'left', background: 'none', border: 'none', cursor: 'pointer' }}
                onClick={() => select(hit)}
              >
                <span aria-hidden>{ENTITY_ICONS[hit.entity_type]}</span>
                <span style={{ flex: 1 }}>
                  <span className="mono">{hit.qualified_name}</span>
                  <span className="faint small" style={{ display: 'block' }}>
                    {hit.entity_type} · {hit.platform} · score {hit.score.toFixed(2)}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
