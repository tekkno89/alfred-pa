import { useCallback, useRef } from 'react'

type SoundName = 'chime' | 'urgent' | 'gentle' | 'ping'

function playChime(ctx: AudioContext) {
  const now = ctx.currentTime
  // Two ascending tones: C5 → E5
  ;[523.25, 659.25].forEach((freq, i) => {
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.type = 'sine'
    osc.frequency.value = freq
    gain.gain.setValueAtTime(0.3, now + i * 0.2)
    gain.gain.exponentialRampToValueAtTime(0.001, now + i * 0.2 + 0.4)
    osc.connect(gain)
    gain.connect(ctx.destination)
    osc.start(now + i * 0.2)
    osc.stop(now + i * 0.2 + 0.4)
  })
}

function playUrgent(ctx: AudioContext) {
  const now = ctx.currentTime
  // Rapid repeating beeps
  for (let i = 0; i < 4; i++) {
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.type = 'square'
    osc.frequency.value = 880
    gain.gain.setValueAtTime(0.25, now + i * 0.15)
    gain.gain.exponentialRampToValueAtTime(0.001, now + i * 0.15 + 0.1)
    osc.connect(gain)
    gain.connect(ctx.destination)
    osc.start(now + i * 0.15)
    osc.stop(now + i * 0.15 + 0.1)
  }
}

function playGentle(ctx: AudioContext) {
  const now = ctx.currentTime
  // Single soft sine wave
  const osc = ctx.createOscillator()
  const gain = ctx.createGain()
  osc.type = 'sine'
  osc.frequency.value = 440
  gain.gain.setValueAtTime(0.2, now)
  gain.gain.exponentialRampToValueAtTime(0.001, now + 0.8)
  osc.connect(gain)
  gain.connect(ctx.destination)
  osc.start(now)
  osc.stop(now + 0.8)
}

function playPing(ctx: AudioContext) {
  const now = ctx.currentTime
  // Short bright triangle wave
  const osc = ctx.createOscillator()
  const gain = ctx.createGain()
  osc.type = 'triangle'
  osc.frequency.value = 1200
  gain.gain.setValueAtTime(0.35, now)
  gain.gain.exponentialRampToValueAtTime(0.001, now + 0.25)
  osc.connect(gain)
  gain.connect(ctx.destination)
  osc.start(now)
  osc.stop(now + 0.25)
}

const SOUND_MAP: Record<SoundName, (ctx: AudioContext) => void> = {
  chime: playChime,
  urgent: playUrgent,
  gentle: playGentle,
  ping: playPing,
}

export function useAlertSound() {
  const ctxRef = useRef<AudioContext | null>(null)

  const playAlertSound = useCallback((soundName: string) => {
    try {
      if (!ctxRef.current || ctxRef.current.state === 'closed') {
        ctxRef.current = new AudioContext()
      }
      const ctx = ctxRef.current
      if (ctx.state === 'suspended') {
        ctx.resume()
      }

      const play = SOUND_MAP[soundName as SoundName] ?? SOUND_MAP.chime
      play(ctx)
    } catch {
      // Web Audio API not available
    }
  }, [])

  return { playAlertSound }
}
