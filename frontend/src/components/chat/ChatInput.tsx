import { useState, useRef, useEffect } from 'react'
import { Send, Square } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'

interface ChatInputProps {
  onSend: (content: string) => void
  onCancel: () => void
  isStreaming: boolean
  disabled?: boolean
}

export function ChatInput({ onSend, onCancel, isStreaming, disabled }: ChatInputProps) {
  const [input, setInput] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`
    }
  }, [input])

  const handleSubmit = () => {
    if (!input.trim() || disabled) return
    onSend(input)
    setInput('')
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    <div className="border-t p-4">
      <div className="max-w-3xl mx-auto flex gap-2">
        <Textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Send a message..."
          className="min-h-[44px] max-h-[200px] resize-none"
          rows={1}
          disabled={disabled || isStreaming}
        />
        {isStreaming ? (
          <Button
            variant="destructive"
            size="icon"
            onClick={onCancel}
            className="shrink-0"
          >
            <Square className="h-4 w-4" />
          </Button>
        ) : (
          <Button
            onClick={handleSubmit}
            disabled={!input.trim() || disabled}
            className="shrink-0"
          >
            <Send className="h-4 w-4" />
          </Button>
        )}
      </div>
      <p className="text-xs text-muted-foreground text-center mt-2">
        Press Enter to send, Shift+Enter for new line
      </p>
    </div>
  )
}
