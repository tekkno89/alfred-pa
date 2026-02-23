// Batman Runner Game Engine
// Chrome T-Rex style runner with Batman theme — monochrome silhouettes

export type GameState = 'IDLE' | 'PLAYING' | 'GAME_OVER'

interface Batman {
  x: number
  y: number
  vy: number
  width: number
  height: number
  frame: number
  frameTimer: number
  grounded: boolean
}

interface Obstacle {
  x: number
  y: number
  width: number
  height: number
  type: 'ac_unit' | 'chimney' | 'antenna' | 'gap'
}

interface Building {
  x: number
  width: number
  height: number
}

interface Engine {
  state: GameState
  focused: boolean
  score: number
  highScore: number
  speed: number
  batman: Batman
  obstacles: Obstacle[]
  buildings: Building[]
  groundY: number
  frameCount: number
  distSinceObstacle: number
  canvasWidth: number
  canvasHeight: number
}

const START_SPEED = 3.5
const IDLE_SPEED = 2.5
const JUMP_VELOCITY = -14
const GRAVITY = 0.7
const MAX_SPEED = 14
const GROUND_OFFSET = 30
const BATMAN_W = 36
const BATMAN_H = 56
const LS_KEY = 'batman-runner-highscore'

// Monochrome palette
const COL_BG = '#f7f7f7'
const COL_FG = '#535353'
const COL_MID = '#a0a0a0'
const COL_LIGHT = '#d4d4d4'
const COL_GROUND_LINE = '#888888'

export function createEngine(width: number, height: number): Engine {
  const groundY = height - GROUND_OFFSET
  return {
    state: 'IDLE',
    focused: false,
    score: 0,
    highScore: getHighScore(),
    speed: START_SPEED,
    batman: {
      x: 60,
      y: groundY - BATMAN_H,
      vy: 0,
      width: BATMAN_W,
      height: BATMAN_H,
      frame: 0,
      frameTimer: 0,
      grounded: true,
    },
    obstacles: [],
    buildings: initBuildings(width),
    groundY,
    frameCount: 0,
    distSinceObstacle: 0,
    canvasWidth: width,
    canvasHeight: height,
  }
}

function getHighScore(): number {
  try {
    return parseInt(localStorage.getItem(LS_KEY) || '0', 10) || 0
  } catch {
    return 0
  }
}

function saveHighScore(score: number) {
  try {
    localStorage.setItem(LS_KEY, String(score))
  } catch {
    // ignore
  }
}

function initBuildings(width: number): Building[] {
  const buildings: Building[] = []
  let x = 0
  while (x < width + 200) {
    const w = 40 + Math.random() * 80
    const h = 30 + Math.random() * 50
    buildings.push({ x, width: w, height: h })
    x += w + Math.random() * 20
  }
  return buildings
}

export function resize(engine: Engine, width: number, height: number) {
  engine.canvasWidth = width
  engine.canvasHeight = height
  engine.groundY = height - GROUND_OFFSET
  engine.batman.y = engine.groundY - BATMAN_H
  engine.batman.grounded = true
}

export function setFocused(engine: Engine, focused: boolean) {
  engine.focused = focused
  if (!focused && (engine.state === 'PLAYING' || engine.state === 'GAME_OVER')) {
    // Return to idle when losing focus
    engine.state = 'IDLE'
    engine.obstacles = []
    engine.batman.y = engine.groundY - BATMAN_H
    engine.batman.vy = 0
    engine.batman.grounded = true
    engine.distSinceObstacle = 0
  }
}

export function handleInput(engine: Engine, action: 'jump' | 'restart' = 'jump') {
  if (engine.state === 'IDLE') {
    startGame(engine)
  } else if (engine.state === 'GAME_OVER' && action === 'restart') {
    startGame(engine)
  } else if (engine.state === 'PLAYING' && engine.batman.grounded) {
    engine.batman.vy = JUMP_VELOCITY
    engine.batman.grounded = false
  }
}

function startGame(engine: Engine) {
  engine.state = 'PLAYING'
  engine.score = 0
  engine.speed = START_SPEED
  engine.obstacles = []
  engine.frameCount = 0
  engine.distSinceObstacle = 200
  engine.batman.y = engine.groundY - BATMAN_H
  engine.batman.vy = 0
  engine.batman.grounded = true
}

export function update(engine: Engine) {
  engine.frameCount++
  const isPlaying = engine.state === 'PLAYING'
  const isIdle = engine.state === 'IDLE'
  const currentSpeed = isPlaying ? engine.speed : IDLE_SPEED

  // Update background buildings (parallax)
  for (const b of engine.buildings) {
    b.x -= currentSpeed * 0.3
  }
  const lastB = engine.buildings[engine.buildings.length - 1]
  if (lastB && lastB.x + lastB.width < engine.canvasWidth + 200) {
    const w = 40 + Math.random() * 80
    const h = 30 + Math.random() * 50
    engine.buildings.push({ x: lastB.x + lastB.width + Math.random() * 20, width: w, height: h })
  }
  engine.buildings = engine.buildings.filter(b => b.x + b.width > -100)

  // Batman walk animation
  engine.batman.frameTimer++
  const animSpeed = isPlaying ? 6 : 10
  if (engine.batman.frameTimer >= animSpeed) {
    engine.batman.frameTimer = 0
    engine.batman.frame = (engine.batman.frame + 1) % 4
  }

  // Jump physics
  if (!engine.batman.grounded) {
    engine.batman.vy += GRAVITY
    engine.batman.y += engine.batman.vy
    if (engine.batman.y >= engine.groundY - BATMAN_H) {
      engine.batman.y = engine.groundY - BATMAN_H
      engine.batman.vy = 0
      engine.batman.grounded = true
    }
  }

  // Idle auto-play: spawn obstacles and auto-jump
  if (isIdle) {
    engine.distSinceObstacle += currentSpeed
    if (engine.distSinceObstacle >= 350 + Math.random() * 50) {
      spawnObstacle(engine)
      engine.distSinceObstacle = 0
    }

    // Move idle obstacles
    for (const o of engine.obstacles) {
      o.x -= currentSpeed
    }
    engine.obstacles = engine.obstacles.filter(o => o.x + o.width > -50)

    // Auto-jump: look ahead for obstacles
    for (const o of engine.obstacles) {
      const dist = o.x - engine.batman.x
      if (dist > 0 && dist < 50 && engine.batman.grounded) {
        engine.batman.vy = JUMP_VELOCITY
        engine.batman.grounded = false
        break
      }
    }
    return
  }

  if (!isPlaying) return

  // Score
  if (engine.frameCount % 5 === 0) {
    engine.score++
  }

  // Difficulty scaling: starts at 2.5, gains 0.3 every 100 pts, caps at 12
  engine.speed = Math.min(MAX_SPEED, START_SPEED + Math.floor(engine.score / 100) * 0.3)

  // Spawn obstacles — gap shrinks as speed increases
  engine.distSinceObstacle += engine.speed
  const minGap = Math.max(160, 300 - engine.speed * 8) + Math.random() * 80
  if (engine.distSinceObstacle >= minGap) {
    spawnObstacle(engine)
    engine.distSinceObstacle = 0
  }

  // Move obstacles
  for (const o of engine.obstacles) {
    o.x -= engine.speed
  }
  engine.obstacles = engine.obstacles.filter(o => o.x + o.width > -50)

  // Collision detection (AABB)
  const b = engine.batman
  const bx = b.x + 3
  const by = b.y + 3
  const bw = b.width - 6
  const bh = b.height - 3
  for (const o of engine.obstacles) {
    if (o.type === 'gap') {
      if (b.grounded && bx + bw > o.x + 4 && bx < o.x + o.width - 4) {
        gameOver(engine)
        return
      }
    } else {
      if (bx < o.x + o.width && bx + bw > o.x && by < o.y + o.height && by + bh > o.y) {
        gameOver(engine)
        return
      }
    }
  }
}

function spawnObstacle(engine: Engine) {
  const types: Obstacle['type'][] = ['ac_unit', 'chimney', 'antenna', 'gap']
  const type = types[Math.floor(Math.random() * types.length)]
  let obs: Obstacle

  switch (type) {
    case 'ac_unit':
      obs = { x: engine.canvasWidth, y: engine.groundY - 24, width: 40, height: 24, type }
      break
    case 'chimney':
      obs = { x: engine.canvasWidth, y: engine.groundY - 44, width: 20, height: 44, type }
      break
    case 'antenna':
      obs = { x: engine.canvasWidth, y: engine.groundY - 52, width: 10, height: 52, type }
      break
    case 'gap':
      obs = { x: engine.canvasWidth, y: engine.groundY, width: 44, height: 30, type }
      break
  }

  engine.obstacles.push(obs)
}

function gameOver(engine: Engine) {
  engine.state = 'GAME_OVER'
  if (engine.score > engine.highScore) {
    engine.highScore = engine.score
    saveHighScore(engine.score)
  }
}

// ─── Rendering ────────────────────────────────────────────────

export function render(ctx: CanvasRenderingContext2D, engine: Engine) {
  const { canvasWidth: w, canvasHeight: h } = engine

  ctx.fillStyle = COL_BG
  ctx.fillRect(0, 0, w, h)

  drawSkyline(ctx, engine)
  drawGround(ctx, engine)

  for (const o of engine.obstacles) {
    drawObstacle(ctx, o, engine)
  }

  drawBatman(ctx, engine)
  drawScore(ctx, engine)
  drawOverlay(ctx, engine)
}

function drawSkyline(ctx: CanvasRenderingContext2D, engine: Engine) {
  ctx.fillStyle = COL_LIGHT
  for (const b of engine.buildings) {
    const by = engine.groundY - b.height - 10
    ctx.fillRect(b.x, by, b.width, b.height + 10)
    // Window dots
    ctx.fillStyle = COL_BG
    for (let wy = by + 6; wy < by + b.height; wy += 10) {
      for (let wx = b.x + 5; wx < b.x + b.width - 5; wx += 8) {
        if (Math.random() > 0.6) {
          ctx.fillRect(wx, wy, 3, 3)
        }
      }
    }
    ctx.fillStyle = COL_LIGHT
  }
}

function drawGround(ctx: CanvasRenderingContext2D, engine: Engine) {
  const gy = engine.groundY
  ctx.fillStyle = '#e8e8e8'
  ctx.fillRect(0, gy, engine.canvasWidth, engine.canvasHeight - gy)
  ctx.strokeStyle = COL_GROUND_LINE
  ctx.lineWidth = 2
  ctx.beginPath()
  ctx.moveTo(0, gy)
  ctx.lineTo(engine.canvasWidth, gy)
  ctx.stroke()
}

function drawObstacle(ctx: CanvasRenderingContext2D, o: Obstacle, engine: Engine) {
  ctx.fillStyle = COL_FG
  switch (o.type) {
    case 'ac_unit':
      ctx.fillRect(o.x, o.y, o.width, o.height)
      ctx.strokeStyle = COL_MID
      ctx.lineWidth = 1
      for (let lx = o.x + 5; lx < o.x + o.width - 3; lx += 7) {
        ctx.beginPath()
        ctx.moveTo(lx, o.y + 4)
        ctx.lineTo(lx, o.y + o.height - 4)
        ctx.stroke()
      }
      break
    case 'chimney':
      ctx.fillRect(o.x, o.y, o.width, o.height)
      ctx.fillRect(o.x - 3, o.y, o.width + 6, 5)
      break
    case 'antenna':
      ctx.strokeStyle = COL_FG
      ctx.lineWidth = 3
      ctx.beginPath()
      ctx.moveTo(o.x + o.width / 2, o.y)
      ctx.lineTo(o.x + o.width / 2, o.y + o.height)
      ctx.stroke()
      ctx.fillStyle = COL_FG
      ctx.beginPath()
      ctx.arc(o.x + o.width / 2, o.y, 4, 0, Math.PI * 2)
      ctx.fill()
      ctx.strokeStyle = COL_FG
      ctx.lineWidth = 1.5
      ctx.beginPath()
      ctx.moveTo(o.x - 3, o.y + 14)
      ctx.lineTo(o.x + o.width + 3, o.y + 14)
      ctx.stroke()
      break
    case 'gap': {
      // Dark void
      ctx.fillStyle = '#3a3a3a'
      ctx.fillRect(o.x, o.y, o.width, engine.canvasHeight - o.y)

      // Broken edge bricks on left side
      ctx.fillStyle = COL_FG
      ctx.fillRect(o.x - 2, o.y, 6, 7)
      ctx.fillRect(o.x - 1, o.y + 9, 4, 6)
      ctx.fillRect(o.x, o.y + 17, 3, 5)

      // Broken edge bricks on right side
      ctx.fillRect(o.x + o.width - 4, o.y, 6, 7)
      ctx.fillRect(o.x + o.width - 3, o.y + 9, 4, 6)
      ctx.fillRect(o.x + o.width - 3, o.y + 17, 3, 5)

      // Horizontal edge lines at the top of the gap
      ctx.strokeStyle = COL_FG
      ctx.lineWidth = 2
      ctx.beginPath()
      ctx.moveTo(o.x - 3, o.y)
      ctx.lineTo(o.x + 5, o.y)
      ctx.stroke()
      ctx.beginPath()
      ctx.moveTo(o.x + o.width - 5, o.y)
      ctx.lineTo(o.x + o.width + 3, o.y)
      ctx.stroke()
      break
    }
  }
}

function drawBatman(ctx: CanvasRenderingContext2D, engine: Engine) {
  const b = engine.batman
  const x = b.x
  const y = b.y

  ctx.fillStyle = COL_FG

  // Ears — straight up, blocky rectangles
  ctx.fillRect(x + 6, y, 5, 14)
  ctx.fillRect(x + 25, y, 5, 14)

  // Head — blocky rectangle
  ctx.fillRect(x + 3, y + 10, 30, 14)

  // Eyes — two small cutouts
  ctx.fillStyle = COL_BG
  ctx.fillRect(x + 9, y + 15, 5, 4)
  ctx.fillRect(x + 20, y + 15, 5, 4)

  // Body — solid block
  ctx.fillStyle = COL_FG
  ctx.fillRect(x + 5, y + 24, 26, 18)

  // Cape — attached to body, starts at mid-back
  const capeOff = Math.round(Math.sin(engine.frameCount * 0.15) * 4)
  ctx.fillRect(x, y + 26, 7, 12)                // top part, fixed to back
  ctx.fillRect(x - 3 + capeOff, y + 38, 8, 10)  // mid, slight flutter
  ctx.fillRect(x - 6 + capeOff, y + 48, 7, 8)   // bottom tip, more flutter

  // Legs — blocky rectangles with walk cycle
  if (b.grounded) {
    const legOffset = [0, 4, 0, -4][b.frame]
    // Left leg
    ctx.fillRect(x + 7 - legOffset, y + 42, 8, 14)
    // Right leg
    ctx.fillRect(x + 21 + legOffset, y + 42, 8, 14)
  } else {
    // Tucked legs
    ctx.fillRect(x + 5, y + 42, 9, 8)
    ctx.fillRect(x + 22, y + 42, 9, 8)
  }

  // Belt — mid-gray stripe
  ctx.fillStyle = COL_MID
  ctx.fillRect(x + 5, y + 40, 26, 3)

  // Bat symbol — small cutout on chest
  ctx.fillStyle = COL_BG
  ctx.fillRect(x + 13, y + 30, 10, 4)
  ctx.fillRect(x + 10, y + 34, 5, 2)
  ctx.fillRect(x + 21, y + 34, 5, 2)
}

function drawScore(ctx: CanvasRenderingContext2D, engine: Engine) {
  if (engine.state === 'IDLE') return

  ctx.font = '12px monospace'
  ctx.textAlign = 'right'

  ctx.fillStyle = COL_MID
  ctx.fillText(`HI ${String(engine.highScore).padStart(5, '0')}`, engine.canvasWidth - 60, 20)

  ctx.fillStyle = COL_FG
  ctx.fillText(String(engine.score).padStart(5, '0'), engine.canvasWidth - 10, 20)
}

function drawOverlay(ctx: CanvasRenderingContext2D, engine: Engine) {
  const cx = engine.canvasWidth / 2
  const cy = engine.canvasHeight / 2

  if (engine.state === 'IDLE' && engine.focused) {
    ctx.font = '13px monospace'
    ctx.textAlign = 'center'
    ctx.fillStyle = COL_MID
    ctx.fillText('Click to play', cx, cy - 5)
  }

  if (engine.state === 'GAME_OVER') {
    ctx.fillStyle = 'rgba(247, 247, 247, 0.6)'
    ctx.fillRect(0, 0, engine.canvasWidth, engine.canvasHeight)

    ctx.textAlign = 'center'
    ctx.fillStyle = COL_FG
    ctx.font = 'bold 16px monospace'
    ctx.fillText('GAME OVER', cx, cy - 12)
    ctx.font = '12px monospace'
    ctx.fillStyle = COL_MID
    ctx.fillText(`Score: ${engine.score}   Best: ${engine.highScore}`, cx, cy + 6)
    ctx.font = '11px monospace'
    ctx.fillStyle = COL_MID
    ctx.fillText('Press ENTER to restart', cx, cy + 24)
  }
}
