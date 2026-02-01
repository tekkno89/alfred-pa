import { Routes, Route } from 'react-router-dom'

function App() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <Routes>
        <Route path="/" element={<Home />} />
        {/* TODO: Add routes for login, sessions, chat, memory */}
      </Routes>
    </div>
  )
}

function Home() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="text-center">
        <h1 className="text-4xl font-bold mb-4">Alfred</h1>
        <p className="text-muted-foreground">Your Personal AI Assistant</p>
      </div>
    </div>
  )
}

export default App
