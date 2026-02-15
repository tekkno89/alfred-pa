import { useState } from 'react'
import { Search, ChevronRight } from 'lucide-react'
import type { ToolResultData } from '@/types'

interface WebSearchResultsCardProps {
  data: ToolResultData
}

function getDomain(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return url
  }
}

function getFaviconUrl(url: string): string {
  try {
    const domain = new URL(url).hostname
    return `https://www.google.com/s2/favicons?domain=${domain}&sz=16`
  } catch {
    return ''
  }
}

export function WebSearchResultsCard({ data }: WebSearchResultsCardProps) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="py-3 px-4 animate-in fade-in slide-in-from-bottom-2 duration-300">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
      >
        <Search className="h-4 w-4" />
        <span>Searched the web</span>
        <span className="text-xs text-muted-foreground/70">
          {data.sources.length} source{data.sources.length !== 1 ? 's' : ''}
        </span>
        <ChevronRight
          className={`h-3 w-3 transition-transform duration-200 ${expanded ? 'rotate-90' : ''}`}
        />
      </button>

      {expanded && (
        <div className="mt-2 ml-6 space-y-1.5 animate-in fade-in slide-in-from-top-1 duration-200">
          <p className="text-xs text-muted-foreground mb-2">
            &ldquo;{data.query}&rdquo;
          </p>
          {data.sources.map((source, i) => (
            <a
              key={i}
              href={source.url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 text-sm hover:bg-muted/50 rounded px-2 py-1 transition-colors"
            >
              <img
                src={getFaviconUrl(source.url)}
                alt=""
                className="h-4 w-4 flex-shrink-0"
                loading="lazy"
              />
              <span className="truncate text-foreground">{source.title || getDomain(source.url)}</span>
              <span className="text-xs text-muted-foreground flex-shrink-0">
                {getDomain(source.url)}
              </span>
            </a>
          ))}
        </div>
      )}
    </div>
  )
}
