import { useState } from 'react'
import { Scissors, ChevronDown, ChevronRight } from 'lucide-react'

interface CompactionDividerProps {
  summary: string
}

export function CompactionDivider({ summary }: CompactionDividerProps) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="my-3">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground transition-colors group"
      >
        <div className="flex-1 h-px bg-border" />
        <Scissors className="h-3 w-3 shrink-0" />
        <span className="shrink-0">Earlier messages summarized</span>
        {expanded ? (
          <ChevronDown className="h-3 w-3 shrink-0" />
        ) : (
          <ChevronRight className="h-3 w-3 shrink-0" />
        )}
        <div className="flex-1 h-px bg-border" />
      </button>
      {expanded && (
        <div className="mt-2 mx-4 p-3 rounded-md bg-muted/50 text-xs text-muted-foreground leading-relaxed whitespace-pre-wrap">
          {summary}
        </div>
      )}
    </div>
  )
}
