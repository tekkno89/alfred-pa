import { useNavigate } from 'react-router-dom'
import { CheckSquare, Plus, Star, AlertTriangle, Clock, Calendar } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { useTodoSummary, useTodoDashboard, useOverdueTick } from '@/hooks/useTodos'

const PRIORITY_COLORS: Record<number, string> = {
  0: 'bg-red-500',
  1: 'bg-orange-500',
  2: 'bg-blue-500',
  3: 'bg-gray-400',
}

function formatDue(dateStr: string | null): string {
  if (!dateStr) return ''
  const utcStr = dateStr.endsWith('Z') || dateStr.includes('+') ? dateStr : dateStr + 'Z'
  const due = new Date(utcStr)
  const now = new Date()
  if (due < now) return 'Overdue'
  return due.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

export function TodosCard() {
  const navigate = useNavigate()
  const { data: summary, isLoading: summaryLoading } = useTodoSummary()
  const { data: items, isLoading: itemsLoading } = useTodoDashboard()
  useOverdueTick(items)
  const isLoading = summaryLoading || itemsLoading

  return (
    <Card
      className="cursor-pointer hover:shadow-md transition-shadow relative h-full flex flex-col"
      onClick={() => navigate('/todos')}
    >
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <CheckSquare className="h-4 w-4" />
          Todos
        </CardTitle>
      </CardHeader>
      <CardContent className="flex-1 overflow-y-auto">
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading...</p>
        ) : (
          <>
            {/* Summary counts */}
            {summary && (
              <div className="grid grid-cols-4 gap-2 mb-3">
                <div className="text-center">
                  <div className="text-lg font-semibold text-red-500">{summary.overdue}</div>
                  <div className="text-[10px] text-muted-foreground flex items-center justify-center gap-0.5">
                    <AlertTriangle className="h-2.5 w-2.5" />
                    Overdue
                  </div>
                </div>
                <div className="text-center">
                  <div className="text-lg font-semibold text-orange-500">{summary.due_today}</div>
                  <div className="text-[10px] text-muted-foreground flex items-center justify-center gap-0.5">
                    <Clock className="h-2.5 w-2.5" />
                    Today
                  </div>
                </div>
                <div className="text-center">
                  <div className="text-lg font-semibold text-blue-500">{summary.due_this_week}</div>
                  <div className="text-[10px] text-muted-foreground flex items-center justify-center gap-0.5">
                    <Calendar className="h-2.5 w-2.5" />
                    Week
                  </div>
                </div>
                <div className="text-center">
                  <div className="text-lg font-semibold">{summary.total_open}</div>
                  <div className="text-[10px] text-muted-foreground">Open</div>
                </div>
              </div>
            )}

            {/* Starred + urgent items */}
            {!items || items.length === 0 ? (
              <p className="text-sm text-muted-foreground">No open todos</p>
            ) : (
              <div className="space-y-1.5">
                {items.map((todo) => (
                  <div
                    key={todo.id}
                    className="flex items-center gap-1.5 text-sm cursor-pointer hover:bg-muted/50 rounded px-1 -mx-1"
                    onClick={(e) => {
                      e.stopPropagation()
                      navigate(`/todos?edit=${todo.id}`)
                    }}
                  >
                    <div className={`h-2 w-2 rounded-full shrink-0 ${PRIORITY_COLORS[todo.priority] || 'bg-gray-400'}`} />
                    {todo.is_starred && (
                      <Star className="h-3 w-3 fill-yellow-400 text-yellow-400 shrink-0" />
                    )}
                    <span className="truncate flex-1">{todo.title}</span>
                    {todo.due_at && (
                      <span className={`text-xs shrink-0 ml-1 ${
                        new Date(todo.due_at) < new Date() ? 'text-red-500 font-medium' : 'text-muted-foreground'
                      }`}>
                        {formatDue(todo.due_at)}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </CardContent>
      <button
        className="absolute bottom-3 right-3 h-8 w-8 rounded-full bg-primary text-primary-foreground flex items-center justify-center shadow-sm hover:bg-primary/90 transition-colors"
        onClick={(e) => {
          e.stopPropagation()
          navigate('/todos?create=true')
        }}
      >
        <Plus className="h-6 w-6 stroke-[2.5]" />
      </button>
    </Card>
  )
}
