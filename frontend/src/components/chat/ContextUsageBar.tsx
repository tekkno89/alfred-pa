import { Scissors } from 'lucide-react'
import type { ContextUsage } from '@/types'

interface ContextUsageBarProps {
  contextUsage: ContextUsage
  onCompact?: () => void
  isCompacting?: boolean
}

function formatTokens(count: number): string {
  if (count >= 1_000_000) {
    return `${(count / 1_000_000).toFixed(1)}M`
  }
  if (count >= 1_000) {
    return `${(count / 1_000).toFixed(0)}K`
  }
  return String(count)
}

function getBarColor(percentage: number): string {
  if (percentage > 90) return 'rgb(239 68 68)'    // red-500
  if (percentage > 75) return 'rgb(249 115 22)'   // orange-500
  if (percentage > 50) return 'rgb(234 179 8)'    // yellow-500
  return 'rgb(34 197 94)'                          // green-500
}

function getBarBgColor(percentage: number): string {
  if (percentage > 90) return 'rgba(239, 68, 68, 0.15)'
  if (percentage > 75) return 'rgba(249, 115, 22, 0.15)'
  if (percentage > 50) return 'rgba(234, 179, 8, 0.15)'
  return 'rgba(34, 197, 94, 0.15)'
}

export function ContextUsageBar({ contextUsage, onCompact, isCompacting }: ContextUsageBarProps) {
  const { tokens_used, token_limit, percentage } = contextUsage
  const barColor = getBarColor(percentage)
  const barBgColor = getBarBgColor(percentage)
  const width = Math.min(percentage, 100)

  return (
    <div className="px-4 py-1.5 border-t border-border/50">
      <div className="max-w-3xl mx-auto flex items-center gap-2">
        <div
          className="flex-1 h-2 rounded-full overflow-hidden"
          style={{ backgroundColor: barBgColor }}
          title={`Context: ${formatTokens(tokens_used)} / ${formatTokens(token_limit)} tokens (${percentage}%)`}
        >
          <div
            className="h-full rounded-full"
            style={{
              width: `${width}%`,
              backgroundColor: barColor,
              backgroundImage: `repeating-linear-gradient(
                -45deg,
                transparent,
                transparent 3px,
                rgba(255,255,255,0.15) 3px,
                rgba(255,255,255,0.15) 6px
              )`,
              transition: 'width 0.5s ease-in-out',
            }}
          />
        </div>
        <span className="text-[10px] text-muted-foreground whitespace-nowrap tabular-nums">
          {formatTokens(tokens_used)} / {formatTokens(token_limit)}
        </span>
        {percentage > 20 && onCompact && (
          <button
            onClick={onCompact}
            disabled={isCompacting}
            className="p-0.5 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
            title="Compact conversation"
          >
            <Scissors className={`h-3 w-3 ${isCompacting ? 'animate-spin' : ''}`} />
          </button>
        )}
      </div>
    </div>
  )
}
