import { Search, Loader2 } from 'lucide-react'

const TOOL_DISPLAY: Record<string, { label: string; icon: typeof Search }> = {
  web_search: { label: 'Searching the web...', icon: Search },
}

interface ToolStatusIndicatorProps {
  toolName: string
}

export function ToolStatusIndicator({ toolName }: ToolStatusIndicatorProps) {
  const display = TOOL_DISPLAY[toolName] || { label: `Running ${toolName}...`, icon: Loader2 }
  const Icon = display.icon

  return (
    <div className="flex items-center gap-2 py-3 px-4 text-sm text-muted-foreground animate-in fade-in slide-in-from-bottom-2 duration-300">
      <Icon className="h-4 w-4 animate-pulse" />
      <span>{display.label}</span>
      <Loader2 className="h-3 w-3 animate-spin" />
    </div>
  )
}
