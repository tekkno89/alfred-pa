import { useNavigate } from 'react-router-dom'
import { Train, RefreshCw } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { useBartDepartures } from '@/hooks/useDashboard'
import { sortEstimates } from '@/components/dashboard/sortEstimates'
import type { BartStationPreference, BartEstimate } from '@/types'

interface StationDeparturesProps {
  station: BartStationPreference
}

function StationDepartures({ station }: StationDeparturesProps) {
  const { data, isLoading, isError } = useBartDepartures(
    station.abbr,
    station.platform
  )

  if (isLoading) {
    return (
      <div className="py-2">
        <div className="text-sm font-medium text-muted-foreground mb-1">
          {station.abbr}
        </div>
        <div className="text-xs text-muted-foreground">Loading...</div>
      </div>
    )
  }

  if (isError || !data) {
    return (
      <div className="py-2">
        <div className="text-sm font-medium text-muted-foreground mb-1">
          {station.abbr}
        </div>
        <div className="text-xs text-destructive">Failed to load</div>
      </div>
    )
  }

  const filtered = station.destinations?.length
    ? data.estimates.filter((e) => station.destinations!.includes(e.abbreviation))
    : data.estimates
  const sorted = sortEstimates(filtered, station.sort || 'eta')
  const topEstimates = sorted.slice(0, 3)

  return (
    <div className="py-2 first:pt-0 last:pb-0">
      <div className="text-sm font-medium mb-1.5">{data.station_name}</div>
      {topEstimates.length === 0 ? (
        <div className="text-xs text-muted-foreground">No departures</div>
      ) : (
        <div className="space-y-1">
          {topEstimates.map((est: BartEstimate, i: number) => (
            <DepartureRow key={`${est.abbreviation}-${est.minutes}-${i}`} estimate={est} />
          ))}
        </div>
      )}
    </div>
  )
}

function DepartureRow({ estimate }: { estimate: BartEstimate }) {
  const minutes =
    estimate.minutes === 'Leaving' ? 'Now' : `${estimate.minutes} min`

  return (
    <div className="flex items-center justify-between text-xs">
      <div className="flex items-center gap-1.5">
        <span
          className="inline-block w-2 h-2 rounded-full shrink-0"
          style={{ backgroundColor: estimate.hex_color || '#888' }}
        />
        <span className="truncate max-w-[140px]">{estimate.destination}</span>
      </div>
      <div className="flex items-center gap-2 text-muted-foreground">
        <span>Plat {estimate.platform}</span>
        <span className="font-medium text-foreground">{minutes}</span>
      </div>
    </div>
  )
}

interface BartCardProps {
  stations: BartStationPreference[]
}

export function BartCard({ stations }: BartCardProps) {
  const navigate = useNavigate()

  return (
    <Card
      className="cursor-pointer hover:shadow-md transition-shadow"
      onClick={() => navigate('/dashboard/bart')}
    >
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Train className="h-4 w-4" />
          BART Departures
          <RefreshCw className="h-3 w-3 ml-auto text-muted-foreground" />
        </CardTitle>
      </CardHeader>
      <CardContent>
        {stations.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Click to configure stations
          </p>
        ) : (
          <div className="divide-y">
            {stations.map((station) => (
              <StationDepartures key={station.abbr} station={station} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
