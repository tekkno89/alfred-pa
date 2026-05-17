import { ArrowLeft } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { LearnedKeywordsCard } from '@/components/triage/LearnedKeywordsCard'

export function TriageTransparencyPage() {
  const navigate = useNavigate()

  return (
    <div className="h-full overflow-y-auto">
      <div className="container max-w-3xl mx-auto py-6 space-y-6">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon" onClick={() => navigate(-1)}>
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div>
            <h1 className="text-2xl font-bold">What Alfred Has Learned</h1>
            <p className="text-sm text-muted-foreground">
              View and manage the signals Alfred uses to classify your messages
            </p>
          </div>
        </div>

        <LearnedKeywordsCard />
      </div>
    </div>
  )
}
