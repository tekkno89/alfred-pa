import { useState, useMemo } from 'react'
import { Plus, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useBartStations } from '@/hooks/useDashboard'
import type { BartStationPreference } from '@/types'

interface BartStationPickerProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  initialStations: BartStationPreference[]
  onSave: (stations: BartStationPreference[]) => void
}

export function BartStationPicker({
  open,
  onOpenChange,
  initialStations,
  onSave,
}: BartStationPickerProps) {
  const { data: stationsData, isLoading } = useBartStations()
  const [selected, setSelected] = useState<BartStationPreference[]>(initialStations)
  const [search, setSearch] = useState('')

  // Reset state when dialog opens
  const handleOpenChange = (newOpen: boolean) => {
    if (newOpen) {
      setSelected(initialStations)
      setSearch('')
    }
    onOpenChange(newOpen)
  }

  const filteredStations = useMemo(() => {
    if (!stationsData?.stations) return []
    const term = search.toLowerCase()
    return stationsData.stations.filter(
      (s) =>
        s.name.toLowerCase().includes(term) ||
        s.abbr.toLowerCase().includes(term) ||
        s.city.toLowerCase().includes(term)
    )
  }, [stationsData, search])

  const selectedAbbrs = new Set(selected.map((s) => s.abbr))

  const addStation = (abbr: string) => {
    if (selected.length >= 5 || selectedAbbrs.has(abbr)) return
    setSelected([...selected, { abbr, platform: null }])
  }

  const removeStation = (abbr: string) => {
    setSelected(selected.filter((s) => s.abbr !== abbr))
  }

  const setPlatform = (abbr: string, platform: number | null) => {
    setSelected(
      selected.map((s) => (s.abbr === abbr ? { ...s, platform } : s))
    )
  }

  const handleSave = () => {
    onSave(selected)
    onOpenChange(false)
  }

  const getStationName = (abbr: string) => {
    return stationsData?.stations.find((s) => s.abbr === abbr)?.name || abbr
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Configure BART Stations</DialogTitle>
          <DialogDescription>
            Select up to 5 stations to monitor on your dashboard.
          </DialogDescription>
        </DialogHeader>

        {/* Selected stations */}
        {selected.length > 0 && (
          <div className="space-y-2">
            <label className="text-sm font-medium">Monitored Stations</label>
            {selected.map((station) => (
              <div
                key={station.abbr}
                className="flex items-center gap-2 p-2 border rounded"
              >
                <span className="text-sm flex-1">
                  {getStationName(station.abbr)}
                </span>
                <Select
                  value={station.platform?.toString() || 'all'}
                  onValueChange={(v) =>
                    setPlatform(station.abbr, v === 'all' ? null : parseInt(v))
                  }
                >
                  <SelectTrigger className="w-24 h-8 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All</SelectItem>
                    <SelectItem value="1">Plat 1</SelectItem>
                    <SelectItem value="2">Plat 2</SelectItem>
                  </SelectContent>
                </Select>
                <Button
                  variant="ghost"
                  size="sm"
                  className="h-8 w-8 p-0"
                  onClick={() => removeStation(station.abbr)}
                >
                  <X className="h-3 w-3" />
                </Button>
              </div>
            ))}
          </div>
        )}

        {/* Search and add */}
        {selected.length < 5 && (
          <div className="space-y-2">
            <label className="text-sm font-medium">Add Station</label>
            <Input
              placeholder="Search stations..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            {isLoading ? (
              <p className="text-sm text-muted-foreground">Loading stations...</p>
            ) : (
              <div className="max-h-48 overflow-y-auto space-y-1">
                {filteredStations
                  .filter((s) => !selectedAbbrs.has(s.abbr))
                  .slice(0, 20)
                  .map((station) => (
                    <button
                      key={station.abbr}
                      className="w-full flex items-center gap-2 p-2 text-sm rounded hover:bg-muted text-left"
                      onClick={() => addStation(station.abbr)}
                    >
                      <Plus className="h-3 w-3 text-muted-foreground shrink-0" />
                      <span className="flex-1">{station.name}</span>
                      <span className="text-xs text-muted-foreground">
                        {station.abbr}
                      </span>
                    </button>
                  ))}
              </div>
            )}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSave}>Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
