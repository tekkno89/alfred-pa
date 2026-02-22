import type { BartEstimate } from '@/types'

function etaMinutes(est: BartEstimate): number {
  if (est.minutes === 'Leaving') return 0
  const n = parseInt(est.minutes, 10)
  return isNaN(n) ? 999 : n
}

export function sortEstimates(
  estimates: BartEstimate[],
  sort: 'destination' | 'eta'
): BartEstimate[] {
  return [...estimates].sort((a, b) => {
    if (sort === 'eta') {
      return etaMinutes(a) - etaMinutes(b)
    }
    return a.destination.localeCompare(b.destination)
  })
}
