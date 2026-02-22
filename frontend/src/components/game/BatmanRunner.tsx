import { useRef, useEffect, useCallback, useState } from 'react'
import { createEngine, resize, handleInput, setFocused, update, render } from './gameEngine'

export function BatmanRunner() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const engineRef = useRef(createEngine(600, 120))
  const rafRef = useRef<number>(0)
  const [focused, setFocusedState] = useState(false)
  const [hovered, setHovered] = useState(false)

  const gameLoop = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    update(engineRef.current)
    render(ctx, engineRef.current)
    rafRef.current = requestAnimationFrame(gameLoop)
  }, [])

  useEffect(() => {
    const canvas = canvasRef.current
    const container = containerRef.current
    if (!canvas || !container) return

    const updateSize = () => {
      const rect = container.getBoundingClientRect()
      const w = Math.floor(rect.width)
      const h = 180
      canvas.width = w
      canvas.height = h
      resize(engineRef.current, w, h)
    }

    updateSize()
    const observer = new ResizeObserver(updateSize)
    observer.observe(container)

    rafRef.current = requestAnimationFrame(gameLoop)

    return () => {
      observer.disconnect()
      cancelAnimationFrame(rafRef.current)
    }
  }, [gameLoop])

  // Keyboard only when focused
  useEffect(() => {
    if (!focused) return

    const onKey = (e: KeyboardEvent) => {
      if (e.code === 'Enter') {
        e.preventDefault()
        handleInput(engineRef.current, 'restart')
      } else if (e.code === 'Space' || e.code === 'ArrowUp') {
        e.preventDefault()
        handleInput(engineRef.current, 'jump')
      }
    }

    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [focused])

  const onFocus = useCallback(() => {
    setFocusedState(true)
    setFocused(engineRef.current, true)
  }, [])

  const onBlur = useCallback(() => {
    setFocusedState(false)
    if (!hovered) setFocused(engineRef.current, false)
  }, [hovered])

  const onMouseEnter = useCallback(() => {
    setHovered(true)
    setFocused(engineRef.current, true)
  }, [])

  const onMouseLeave = useCallback(() => {
    setHovered(false)
    if (!focused) setFocused(engineRef.current, false)
  }, [focused])

  const onCanvasInteract = useCallback((e: React.MouseEvent | React.TouchEvent) => {
    e.preventDefault()
    canvasRef.current?.focus()
    handleInput(engineRef.current, 'jump')
  }, [])

  return (
    <div
      ref={containerRef}
      className="w-full max-w-5xl mx-auto px-8 relative"
    >
      {/* Left fade */}
      <div className="absolute left-0 top-0 bottom-0 w-16 z-10 pointer-events-none"
        style={{ background: 'linear-gradient(to right, var(--background, #fff), transparent)' }}
      />
      {/* Right fade */}
      <div className="absolute right-0 top-0 bottom-0 w-16 z-10 pointer-events-none"
        style={{ background: 'linear-gradient(to left, var(--background, #fff), transparent)' }}
      />
      <canvas
        ref={canvasRef}
        height={180}
        tabIndex={0}
        className="block w-full cursor-pointer outline-none"
        onClick={onCanvasInteract}
        onTouchStart={onCanvasInteract}
        onFocus={onFocus}
        onBlur={onBlur}
        onMouseEnter={onMouseEnter}
        onMouseLeave={onMouseLeave}
      />
    </div>
  )
}
