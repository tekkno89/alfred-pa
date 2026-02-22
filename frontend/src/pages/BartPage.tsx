import { useState, useMemo } from 'react'
import { Train, RefreshCw, Settings, ArrowLeft, ArrowDown, Filter } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useBartDepartures, useDashboardPreferences, useUpdateDashboardPreference } from '@/hooks/useDashboard'
import { BartStationPicker } from '@/components/dashboard/BartStationPicker'
import { sortEstimates } from '@/components/dashboard/sortEstimates'
import type { BartStationPreference, BartEstimate } from '@/types'

function StationBoard({ station, onPlatformChange, onSortChange, onDestinationsChange }: {
  station: BartStationPreference
  onPlatformChange: (platform: number | null) => void
  onSortChange: (sort: 'destination' | 'eta') => void
  onDestinationsChange: (destinations: string[]) => void
}) {
  const { data, isLoading, isError, refetch, dataUpdatedAt } = useBartDepartures(
    station.abbr,
    station.platform
  )
  const [filterOpen, setFilterOpen] = useState(false)

  const currentSort = station.sort || 'eta'
  const activeDestinations = station.destinations || []
  const lastUpdated = dataUpdatedAt
    ? new Date(dataUpdatedAt).toLocaleTimeString()
    : null

  // Get unique destinations from the data for the filter UI
  const availableDestinations = useMemo(() => {
    if (!data?.estimates) return []
    const seen = new Map<string, { abbr: string; name: string; color: string }>()
    for (const est of data.estimates) {
      if (!seen.has(est.abbreviation)) {
        seen.set(est.abbreviation, {
          abbr: est.abbreviation,
          name: est.destination,
          color: est.hex_color || '#888',
        })
      }
    }
    return Array.from(seen.values()).sort((a, b) => a.name.localeCompare(b.name))
  }, [data])

  const filtered = activeDestinations.length
    ? data?.estimates.filter((e) => activeDestinations.includes(e.abbreviation)) || []
    : data?.estimates || []
  const sorted = sortEstimates(filtered, currentSort)

  const toggleDestination = (abbr: string) => {
    const current = new Set(activeDestinations)
    if (current.has(abbr)) {
      current.delete(abbr)
    } else {
      current.add(abbr)
    }
    onDestinationsChange(Array.from(current))
  }

  const clearFilter = () => {
    onDestinationsChange([])
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-lg">
            {data?.station_name || station.abbr}
          </CardTitle>
          <div className="flex items-center gap-2">
            <Button
              variant={activeDestinations.length > 0 ? 'default' : 'outline'}
              size="sm"
              className="h-8"
              onClick={() => setFilterOpen(!filterOpen)}
            >
              <Filter className="h-3.5 w-3.5 mr-1.5" />
              {activeDestinations.length > 0
                ? `Filter (${activeDestinations.length})`
                : 'Filter'}
            </Button>
            <Select
              value={station.platform?.toString() || 'all'}
              onValueChange={(v) =>
                onPlatformChange(v === 'all' ? null : parseInt(v))
              }
            >
              <SelectTrigger className="w-28 h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Platforms</SelectItem>
                <SelectItem value="1">Platform 1</SelectItem>
                <SelectItem value="2">Platform 2</SelectItem>
              </SelectContent>
            </Select>
            <Button
              variant="ghost"
              size="sm"
              className="h-8 w-8 p-0"
              onClick={() => refetch()}
            >
              <RefreshCw className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
        {lastUpdated && (
          <p className="text-xs text-muted-foreground">
            Updated {lastUpdated}
          </p>
        )}
        {/* Destination filter badges */}
        {filterOpen && availableDestinations.length > 0 && (
          <div className="flex flex-wrap gap-1.5 pt-2">
            {activeDestinations.length > 0 && (
              <button
                className="text-xs text-muted-foreground hover:text-foreground underline mr-1"
                onClick={clearFilter}
              >
                Clear
              </button>
            )}
            {availableDestinations.map((dest) => {
              const isActive = activeDestinations.includes(dest.abbr)
              return (
                <Badge
                  key={dest.abbr}
                  variant={isActive ? 'default' : 'outline'}
                  className="cursor-pointer select-none text-xs"
                  onClick={() => toggleDestination(dest.abbr)}
                >
                  <span
                    className="inline-block w-2 h-2 rounded-full mr-1 shrink-0"
                    style={{ backgroundColor: dest.color }}
                  />
                  {dest.name}
                </Badge>
              )
            })}
          </div>
        )}
      </CardHeader>
      <CardContent>
        {isLoading && (
          <p className="text-sm text-muted-foreground">Loading departures...</p>
        )}
        {isError && (
          <p className="text-sm text-destructive">Failed to load departures</p>
        )}
        {data && sorted.length === 0 && (
          <p className="text-sm text-muted-foreground">No departures at this time</p>
        )}
        {sorted.length > 0 && (
          <div className="space-y-1.5">
            <div className="grid grid-cols-[1fr_80px_80px_60px] gap-2 text-xs font-medium text-muted-foreground pb-1 border-b">
              <button
                className={`flex items-center gap-1 text-left cursor-pointer hover:text-foreground transition-colors ${currentSort === 'destination' ? 'text-foreground underline underline-offset-4' : ''}`}
                onClick={() => onSortChange('destination')}
              >
                Destination
                <ArrowDown className={`h-3 w-3 transition-opacity ${currentSort === 'destination' ? 'opacity-100' : 'opacity-0'}`} />
              </button>
              <span>Platform</span>
              <span>Length</span>
              <button
                className={`flex items-center gap-1 justify-end cursor-pointer hover:text-foreground transition-colors ${currentSort === 'eta' ? 'text-foreground underline underline-offset-4' : ''}`}
                onClick={() => onSortChange('eta')}
              >
                ETA
                <ArrowDown className={`h-3 w-3 transition-opacity ${currentSort === 'eta' ? 'opacity-100' : 'opacity-0'}`} />
              </button>
            </div>
            {sorted.map((est: BartEstimate, i: number) => {
              const minutes =
                est.minutes === 'Leaving' ? 'Now' : `${est.minutes} min`
              return (
                <div
                  key={`${est.abbreviation}-${est.minutes}-${i}`}
                  className="grid grid-cols-[1fr_80px_80px_60px] gap-2 text-sm items-center"
                >
                  <div className="flex items-center gap-2">
                    <span
                      className="inline-block w-2.5 h-2.5 rounded-full shrink-0"
                      style={{ backgroundColor: est.hex_color || '#888' }}
                    />
                    <span className="truncate">{est.destination}</span>
                  </div>
                  <span className="text-muted-foreground">{est.platform}</span>
                  <span className="text-muted-foreground">{est.length} car</span>
                  <span className="text-right font-medium">{minutes}</span>
                </div>
              )
            })}
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export function BartPage() {
  const navigate = useNavigate()
  const { data: prefs } = useDashboardPreferences()
  const updatePref = useUpdateDashboardPreference()
  const [pickerOpen, setPickerOpen] = useState(false)

  const bartPref = prefs?.items.find((p) => p.card_type === 'bart')
  const stations: BartStationPreference[] =
    (bartPref?.preferences?.stations as BartStationPreference[]) || []

  const saveStations = (updated: BartStationPreference[]) => {
    updatePref.mutate({
      cardType: 'bart',
      data: {
        preferences: { stations: updated },
        sort_order: bartPref?.sort_order || 0,
      },
    })
  }

  const handlePlatformChange = (abbr: string, platform: number | null) => {
    saveStations(stations.map((s) => (s.abbr === abbr ? { ...s, platform } : s)))
  }

  const handleSortChange = (abbr: string, sort: 'destination' | 'eta') => {
    saveStations(stations.map((s) => (s.abbr === abbr ? { ...s, sort } : s)))
  }

  const handleDestinationsChange = (abbr: string, destinations: string[]) => {
    saveStations(stations.map((s) => (s.abbr === abbr ? { ...s, destinations } : s)))
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-3xl mx-auto p-4 space-y-4">
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
              <Train className="h-5 w-5" />
              <h1 className="text-xl font-semibold">BART Departures</h1>
            </div>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setPickerOpen(true)}
          >
            <Settings className="h-3.5 w-3.5 mr-1.5" />
            Stations
          </Button>
        </div>

        {stations.length === 0 ? (
          <Card>
            <CardContent className="p-8 text-center">
              <Train className="h-10 w-10 mx-auto text-muted-foreground mb-3" />
              <p className="text-muted-foreground mb-3">
                No stations configured yet.
              </p>
              <Button onClick={() => setPickerOpen(true)}>
                Add Stations
              </Button>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-4">
            {stations.map((station) => (
              <StationBoard
                key={station.abbr}
                station={station}
                onPlatformChange={(platform) =>
                  handlePlatformChange(station.abbr, platform)
                }
                onSortChange={(sort) =>
                  handleSortChange(station.abbr, sort)
                }
                onDestinationsChange={(destinations) =>
                  handleDestinationsChange(station.abbr, destinations)
                }
              />
            ))}
          </div>
        )}

        <BartStationPicker
          open={pickerOpen}
          onOpenChange={setPickerOpen}
          initialStations={stations}
          onSave={saveStations}
        />
      </div>
    </div>
  )
}
