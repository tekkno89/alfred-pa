import { Trash2, AlertCircle, Eye, EyeOff } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
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
  useLearnedKeywords,
  useDeleteKeyword,
  useDeleteKeywordsByCategory,
} from '@/hooks/useTriageTransparency'
import type { LearnedKeyword } from '@/hooks/useTriageTransparency'

const CATEGORY_LABELS: Record<string, { label: string; icon: typeof Eye; className: string }> = {
  public: {
    label: 'Public Channels',
    icon: Eye,
    className: 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-200',
  },
  sensitive: {
    label: 'Sensitive Channels',
    icon: EyeOff,
    className: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200',
  },
  dm: {
    label: 'Direct Messages',
    icon: AlertCircle,
    className: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200',
  },
}

function KeywordItem({
  keyword,
  onDelete,
}: {
  keyword: LearnedKeyword
  onDelete: (keyword: string) => void
}) {
  const categoryInfo = CATEGORY_LABELS[keyword.source_category] ?? CATEGORY_LABELS.public
  const CategoryIcon = categoryInfo.icon
  const isPositive = keyword.weight > 0

  return (
    <div className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-muted/50 group">
      <div className="flex items-center gap-3 min-w-0">
        <span className="font-medium truncate">{keyword.keyword}</span>
        <div className="flex items-center gap-2 shrink-0">
          <Badge
            variant={isPositive ? 'default' : 'secondary'}
            className={
              isPositive
                ? 'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-200'
                : 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200'
            }
          >
            {isPositive ? '+' : ''}
            {keyword.weight.toFixed(2)}
          </Badge>
          <Badge variant="outline" className={categoryInfo.className}>
            <CategoryIcon className="h-3 w-3 mr-1" />
            {categoryInfo.label}
          </Badge>
        </div>
      </div>
      <Button
        variant="ghost"
        size="sm"
        className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive"
        onClick={() => onDelete(keyword.keyword)}
      >
        <Trash2 className="h-4 w-4" />
      </Button>
    </div>
  )
}

export function LearnedKeywordsCard() {
  const { data: keywords, isLoading, error } = useLearnedKeywords()
  const deleteKeyword = useDeleteKeyword()
  const deleteByCategory = useDeleteKeywordsByCategory()

  if (isLoading) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-muted-foreground">
          Loading learned keywords...
        </CardContent>
      </Card>
    )
  }

  if (error) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-destructive">
          Failed to load keywords. Please try again.
        </CardContent>
      </Card>
    )
  }

  const groupedKeywords = (keywords ?? []).reduce(
    (acc, kw) => {
      if (!acc[kw.source_category]) acc[kw.source_category] = []
      acc[kw.source_category].push(kw)
      return acc
    },
    {} as Record<string, LearnedKeyword[]>
  )

  const handleDeleteCategory = (category: string) => {
    deleteByCategory.mutate(category)
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Learned Topic Keywords</CardTitle>
        <CardDescription>
          Keywords Alfred has learned from your feedback. These influence how messages are
          classified.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {Object.keys(groupedKeywords).length === 0 ? (
          <p className="text-sm text-muted-foreground py-4">
            No learned keywords yet. Keywords appear when you provide feedback on message
            classifications.
          </p>
        ) : (
          Object.entries(groupedKeywords).map(([category, kws]) => {
            const categoryInfo = CATEGORY_LABELS[category] ?? CATEGORY_LABELS.public
            const CategoryIcon = categoryInfo.icon

            return (
              <div key={category} className="space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <CategoryIcon className="h-4 w-4 text-muted-foreground" />
                    <h4 className="text-sm font-medium">{categoryInfo.label}</h4>
                    <Badge variant="secondary" className="text-xs">
                      {kws.length}
                    </Badge>
                  </div>
                  <AlertDialog>
                    <AlertDialogTrigger asChild>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-xs text-muted-foreground hover:text-destructive"
                      >
                        <Trash2 className="h-3 w-3 mr-1" />
                        Clear All
                      </Button>
                    </AlertDialogTrigger>
                    <AlertDialogContent>
                      <AlertDialogHeader>
                        <AlertDialogTitle>Delete all {categoryInfo.label.toLowerCase()} keywords?</AlertDialogTitle>
                        <AlertDialogDescription>
                          This will remove {kws.length} keyword{kws.length !== 1 ? 's' : ''} learned
                          from {categoryInfo.label.toLowerCase()}. Deleted keywords won't be
                          re-learned until you provide new feedback.
                        </AlertDialogDescription>
                      </AlertDialogHeader>
                      <AlertDialogFooter>
                        <AlertDialogCancel>
                          Cancel
                        </AlertDialogCancel>
                        <AlertDialogAction
                          onClick={() => handleDeleteCategory(category)}
                          className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                        >
                          Delete {kws.length} keyword{kws.length !== 1 ? 's' : ''}
                        </AlertDialogAction>
                      </AlertDialogFooter>
                    </AlertDialogContent>
                  </AlertDialog>
                </div>
                <div className="space-y-1 border rounded-lg divide-y">
                  {kws
                    .sort((a, b) => Math.abs(b.weight) - Math.abs(a.weight))
                    .slice(0, 20)
                    .map((kw) => (
                      <KeywordItem
                        key={kw.keyword}
                        keyword={kw}
                        onDelete={(k) => deleteKeyword.mutate(k)}
                      />
                    ))}
                  {kws.length > 20 && (
                    <p className="text-xs text-muted-foreground py-2 px-3">
                      Showing top 20 of {kws.length} keywords
                    </p>
                  )}
                </div>
              </div>
            )
          })
        )}
      </CardContent>
    </Card>
  )
}
