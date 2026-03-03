import { useState, useEffect } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  CheckSquare, Plus, ArrowLeft, Star, Trash2, Check, Pencil, CalendarIcon, X,
} from 'lucide-react'
import { format } from 'date-fns'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Calendar } from '@/components/ui/calendar'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import {
  useTodos,
  useCreateTodo,
  useUpdateTodo,
  useCompleteTodo,
  useDeleteTodo,
} from '@/hooks/useTodos'
import { cn } from '@/lib/utils'
import type { Todo, TodoCreate, TodoUpdate } from '@/types'

const PRIORITY_LABELS: Record<number, string> = {
  0: 'Urgent',
  1: 'High',
  2: 'Medium',
  3: 'Low',
}

const PRIORITY_COLORS: Record<number, string> = {
  0: 'bg-red-500',
  1: 'bg-orange-500',
  2: 'bg-blue-500',
  3: 'bg-gray-400',
}

function formatDate(dateStr: string): string {
  const utcStr = dateStr.endsWith('Z') || dateStr.includes('+') ? dateStr : dateStr + 'Z'
  return new Date(utcStr).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  })
}

function formatDueLabel(dateStr: string | null): string {
  if (!dateStr) return ''
  const utcStr = dateStr.endsWith('Z') || dateStr.includes('+') ? dateStr : dateStr + 'Z'
  const due = new Date(utcStr)
  const now = new Date()
  if (due < now) return 'Overdue'
  return formatDate(dateStr)
}

export function TodosPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [statusFilter, setStatusFilter] = useState<string>('open')
  const [priorityFilter, setPriorityFilter] = useState<number | undefined>(undefined)
  const [starredFilter, setStarredFilter] = useState<boolean | undefined>(undefined)
  const [sortBy, setSortBy] = useState('created_at')
  const [sortOrder, setSortOrder] = useState('desc')

  const { data, isLoading } = useTodos(
    1, 100, sortBy, sortOrder,
    statusFilter,
    priorityFilter,
    starredFilter,
  )
  const createTodo = useCreateTodo()
  const updateTodo = useUpdateTodo()
  const completeTodo = useCompleteTodo()
  const deleteTodo = useDeleteTodo()

  // Dialog state
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingTodo, setEditingTodo] = useState<Todo | null>(null)
  const [formTitle, setFormTitle] = useState('')
  const [formDescription, setFormDescription] = useState('')
  const [formPriority, setFormPriority] = useState(2)
  const [formDueDate, setFormDueDate] = useState<Date | undefined>(undefined)
  const [formDueTime, setFormDueTime] = useState('09:00')
  const [formStarred, setFormStarred] = useState(false)
  const [formTags, setFormTags] = useState('')
  const [formRecurrence, setFormRecurrence] = useState('')

  // Handle URL params for create/edit
  useEffect(() => {
    if (searchParams.get('create') === 'true') {
      openCreateDialog()
      setSearchParams({}, { replace: true })
    }
  }, [searchParams])

  const openCreateDialog = () => {
    setEditingTodo(null)
    setFormTitle('')
    setFormDescription('')
    setFormPriority(2)
    setFormDueDate(undefined)
    setFormDueTime('09:00')
    setFormStarred(false)
    setFormTags('')
    setFormRecurrence('')
    setDialogOpen(true)
  }

  const openEditDialog = (todo: Todo) => {
    setEditingTodo(todo)
    setFormTitle(todo.title)
    setFormDescription(todo.description || '')
    setFormPriority(todo.priority)
    if (todo.due_at) {
      const utcStr = todo.due_at.endsWith('Z') || todo.due_at.includes('+') ? todo.due_at : todo.due_at + 'Z'
      const d = new Date(utcStr)
      setFormDueDate(d)
      setFormDueTime(
        `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
      )
    } else {
      setFormDueDate(undefined)
      setFormDueTime('09:00')
    }
    setFormStarred(todo.is_starred)
    setFormTags(todo.tags.join(', '))
    setFormRecurrence(todo.recurrence_rule || '')
    setDialogOpen(true)
  }

  const buildDueAt = (): string | null | undefined => {
    if (!formDueDate) return editingTodo ? null : undefined
    const [hours, minutes] = formDueTime.split(':').map(Number)
    const d = new Date(formDueDate)
    d.setHours(hours || 0, minutes || 0, 0, 0)
    return d.toISOString()
  }

  const handleSave = async () => {
    if (!formTitle.trim()) return

    const tags = formTags
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean)

    const dueAt = buildDueAt()

    if (editingTodo) {
      const updates: TodoUpdate = {
        title: formTitle.trim(),
        description: formDescription.trim() || null,
        priority: formPriority,
        due_at: dueAt,
        is_starred: formStarred,
        tags,
        recurrence_rule: formRecurrence.trim() || null,
      }
      await updateTodo.mutateAsync({ id: editingTodo.id, data: updates })
    } else {
      const newTodo: TodoCreate = {
        title: formTitle.trim(),
        description: formDescription.trim() || undefined,
        priority: formPriority,
        due_at: dueAt ?? undefined,
        is_starred: formStarred,
        tags,
        recurrence_rule: formRecurrence.trim() || undefined,
      }
      await createTodo.mutateAsync(newTodo)
    }

    setDialogOpen(false)
  }

  const toggleStar = (todo: Todo) => {
    updateTodo.mutate({ id: todo.id, data: { is_starred: !todo.is_starred } })
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-3xl mx-auto p-4 space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate('/')}
              className="h-8 w-8 p-0"
            >
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <div className="flex items-center gap-2">
              <CheckSquare className="h-5 w-5" />
              <h1 className="text-xl font-semibold">Todos</h1>
            </div>
          </div>
          <Button size="sm" onClick={openCreateDialog}>
            <Plus className="h-4 w-4 mr-1" />
            New Todo
          </Button>
        </div>

        {/* Filter bar */}
        <div className="flex items-center gap-2 flex-wrap">
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="w-[120px] h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="open">Open</SelectItem>
              <SelectItem value="completed">Completed</SelectItem>
              <SelectItem value="all">All</SelectItem>
            </SelectContent>
          </Select>

          <Select
            value={priorityFilter !== undefined ? String(priorityFilter) : 'all'}
            onValueChange={(v) => setPriorityFilter(v === 'all' ? undefined : Number(v))}
          >
            <SelectTrigger className="w-[120px] h-8 text-xs">
              <SelectValue placeholder="Priority" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Any Priority</SelectItem>
              <SelectItem value="0">Urgent</SelectItem>
              <SelectItem value="1">High</SelectItem>
              <SelectItem value="2">Medium</SelectItem>
              <SelectItem value="3">Low</SelectItem>
            </SelectContent>
          </Select>

          <Button
            variant={starredFilter ? 'default' : 'outline'}
            size="sm"
            className="h-8 text-xs"
            onClick={() => setStarredFilter(starredFilter ? undefined : true)}
          >
            <Star className={cn('h-3.5 w-3.5 mr-1', starredFilter && 'fill-current')} />
            Starred
          </Button>

          <Select
            value={`${sortBy}:${sortOrder}`}
            onValueChange={(v) => {
              const [sb, so] = v.split(':')
              setSortBy(sb)
              setSortOrder(so)
            }}
          >
            <SelectTrigger className="w-[140px] h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="created_at:desc">Newest first</SelectItem>
              <SelectItem value="created_at:asc">Oldest first</SelectItem>
              <SelectItem value="priority:asc">Priority (high first)</SelectItem>
              <SelectItem value="due_at:asc">Due date (soonest)</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {/* Todo list */}
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading...</p>
        ) : !data?.items.length ? (
          <div className="text-center py-12 space-y-2">
            <CheckSquare className="h-10 w-10 mx-auto text-muted-foreground" />
            <p className="text-muted-foreground">
              {statusFilter === 'completed' ? 'No completed todos' : 'No todos yet'}
            </p>
            {statusFilter !== 'completed' && (
              <Button variant="outline" size="sm" onClick={openCreateDialog}>
                Create your first todo
              </Button>
            )}
          </div>
        ) : (
          <div className="space-y-1">
            {data.items.map((todo) => {
              const isOverdue = todo.due_at && new Date(todo.due_at) < new Date() && todo.status === 'open'

              return (
                <div
                  key={todo.id}
                  className="flex items-center gap-2 p-2 rounded-lg hover:bg-muted/50 group"
                >
                  {/* Complete checkbox */}
                  {todo.status === 'open' && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 w-7 p-0 shrink-0"
                      onClick={() => completeTodo.mutate(todo.id)}
                    >
                      <div className="h-4 w-4 rounded border-2 border-muted-foreground flex items-center justify-center group-hover:border-primary">
                        <Check className="h-3 w-3 opacity-0 group-hover:opacity-30" />
                      </div>
                    </Button>
                  )}
                  {todo.status === 'completed' && (
                    <div className="h-7 w-7 flex items-center justify-center shrink-0">
                      <div className="h-4 w-4 rounded bg-primary flex items-center justify-center">
                        <Check className="h-3 w-3 text-primary-foreground" />
                      </div>
                    </div>
                  )}

                  {/* Priority dot */}
                  <div
                    className={`h-2.5 w-2.5 rounded-full shrink-0 ${PRIORITY_COLORS[todo.priority] || 'bg-gray-400'}`}
                    title={PRIORITY_LABELS[todo.priority]}
                  />

                  {/* Star */}
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-7 w-7 p-0 shrink-0"
                    onClick={() => toggleStar(todo)}
                  >
                    <Star
                      className={cn(
                        'h-3.5 w-3.5',
                        todo.is_starred
                          ? 'fill-yellow-400 text-yellow-400'
                          : 'text-muted-foreground'
                      )}
                    />
                  </Button>

                  {/* Title + tags */}
                  <div className="flex-1 min-w-0">
                    <span
                      className={cn(
                        'text-sm truncate block cursor-pointer',
                        todo.status === 'completed' && 'line-through text-muted-foreground'
                      )}
                      onClick={() => openEditDialog(todo)}
                    >
                      {todo.title}
                    </span>
                  </div>

                  {/* Tags */}
                  <div className="hidden sm:flex flex-wrap gap-1 shrink-0 max-w-[120px]">
                    {todo.tags?.map((tag) => (
                      <span
                        key={tag}
                        className="inline-flex items-center px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-muted text-muted-foreground"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>

                  {/* Due date */}
                  {todo.due_at && (
                    <span
                      className={cn(
                        'text-xs shrink-0',
                        isOverdue ? 'text-red-500 font-medium' : 'text-muted-foreground'
                      )}
                    >
                      {formatDueLabel(todo.due_at)}
                    </span>
                  )}

                  {/* Actions */}
                  <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 w-7 p-0"
                      onClick={() => openEditDialog(todo)}
                      title="Edit"
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 w-7 p-0 text-destructive hover:text-destructive"
                          title="Delete"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>Delete todo?</AlertDialogTitle>
                          <AlertDialogDescription>
                            This action cannot be undone. The todo will be permanently deleted.
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>Cancel</AlertDialogCancel>
                          <AlertDialogAction
                            onClick={() => deleteTodo.mutate(todo.id)}
                            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                          >
                            Delete
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Create/Edit Dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-[425px]">
          <DialogHeader>
            <DialogTitle>
              {editingTodo ? 'Edit Todo' : 'New Todo'}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4 pt-2">
            <div className="space-y-2">
              <Label htmlFor="title">Title</Label>
              <Input
                id="title"
                value={formTitle}
                onChange={(e) => setFormTitle(e.target.value)}
                placeholder="What needs to be done?"
                autoFocus
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="description">Description</Label>
              <Textarea
                id="description"
                value={formDescription}
                onChange={(e) => setFormDescription(e.target.value)}
                placeholder="Optional details..."
                rows={2}
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Priority</Label>
                <Select
                  value={String(formPriority)}
                  onValueChange={(v) => setFormPriority(Number(v))}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="0">Urgent</SelectItem>
                    <SelectItem value="1">High</SelectItem>
                    <SelectItem value="2">Medium</SelectItem>
                    <SelectItem value="3">Low</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>Due Date</Label>
                <Popover>
                  <PopoverTrigger asChild>
                    <Button
                      variant="outline"
                      className={cn(
                        'w-full justify-start text-left font-normal',
                        !formDueDate && 'text-muted-foreground'
                      )}
                    >
                      <CalendarIcon className="mr-2 h-4 w-4" />
                      {formDueDate ? format(formDueDate, 'MMM d, yyyy') : 'Pick a date'}
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-auto p-0" align="start">
                    <Calendar
                      mode="single"
                      selected={formDueDate}
                      onSelect={setFormDueDate}
                      initialFocus
                    />
                  </PopoverContent>
                </Popover>
              </div>
            </div>

            {/* Time picker + clear — only show when a date is selected */}
            {formDueDate && (
              <div className="flex items-center gap-2">
                <div className="space-y-2 flex-1">
                  <Label htmlFor="due_time">Time</Label>
                  <Input
                    id="due_time"
                    type="time"
                    value={formDueTime}
                    onChange={(e) => setFormDueTime(e.target.value)}
                  />
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  className="mt-7 text-muted-foreground"
                  onClick={() => { setFormDueDate(undefined); setFormDueTime('09:00') }}
                >
                  <X className="h-4 w-4 mr-1" />
                  Clear
                </Button>
              </div>
            )}

            <div className="space-y-2">
              <Label htmlFor="tags">Tags (comma-separated)</Label>
              <Input
                id="tags"
                value={formTags}
                onChange={(e) => setFormTags(e.target.value)}
                placeholder="work, personal, errands"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="recurrence">Recurrence (RRULE)</Label>
              <Input
                id="recurrence"
                value={formRecurrence}
                onChange={(e) => setFormRecurrence(e.target.value)}
                placeholder="e.g. FREQ=DAILY;INTERVAL=1"
              />
            </div>

            <div className="flex items-center gap-2">
              <Button
                variant={formStarred ? 'default' : 'outline'}
                size="sm"
                onClick={() => setFormStarred(!formStarred)}
              >
                <Star className={cn('h-3.5 w-3.5 mr-1', formStarred && 'fill-current')} />
                {formStarred ? 'Starred' : 'Star'}
              </Button>
            </div>

            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setDialogOpen(false)}>
                Cancel
              </Button>
              <Button
                onClick={handleSave}
                disabled={!formTitle.trim() || createTodo.isPending || updateTodo.isPending}
              >
                {editingTodo ? 'Save' : 'Create'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
