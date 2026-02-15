import { useState, useCallback, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { apiStreamPost } from '@/lib/api'
import type { Message, ToolResultData } from '@/types'

export interface ToolResult {
  toolName: string
  data: ToolResultData
}

interface UseChatOptions {
  sessionId: string
  onError?: (error: string) => void
}

interface UseChatReturn {
  streamingContent: string
  isStreaming: boolean
  activeToolName: string | null
  completedToolResults: ToolResult[]
  sendMessage: (content: string) => void
  cancelStream: () => void
}

export function useChat({ sessionId, onError }: UseChatOptions): UseChatReturn {
  const queryClient = useQueryClient()
  const [streamingContent, setStreamingContent] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [activeToolName, setActiveToolName] = useState<string | null>(null)
  const [completedToolResults, setCompletedToolResults] = useState<ToolResult[]>([])
  const completedToolResultsRef = useRef<ToolResult[]>([])
  const abortControllerRef = useRef<AbortController | null>(null)
  const streamingContentRef = useRef('')

  const sendMessage = useCallback(
    (content: string) => {
      if (isStreaming || !content.trim()) return

      // Add user message optimistically
      const userMessage: Message = {
        id: `temp-${Date.now()}`,
        session_id: sessionId,
        role: 'user',
        content: content.trim(),
        metadata_: null,
        created_at: new Date().toISOString(),
      }

      // Update cache with user message
      queryClient.setQueryData(
        ['session', sessionId],
        (old: { messages: Message[] } | undefined) => {
          if (!old) return old
          return {
            ...old,
            messages: [...old.messages, userMessage],
          }
        }
      )

      setIsStreaming(true)
      setStreamingContent('')
      streamingContentRef.current = ''
      setCompletedToolResults([])
      completedToolResultsRef.current = []

      const handleEvent = (event: { type: string; content?: string; message_id?: string; tool_name?: string; tool_data?: ToolResultData }) => {
        switch (event.type) {
          case 'token':
            if (event.content) {
              streamingContentRef.current += event.content
              setStreamingContent(streamingContentRef.current)
            }
            break
          case 'tool_use':
            setActiveToolName(event.tool_name || null)
            // Clear previous result for this tool — new search supersedes old one
            if (event.tool_name) {
              completedToolResultsRef.current = completedToolResultsRef.current.filter(
                r => r.toolName !== event.tool_name
              )
              setCompletedToolResults([...completedToolResultsRef.current])
            }
            break
          case 'tool_result':
            setActiveToolName(null)
            if (event.tool_name && event.tool_data) {
              const newResult = { toolName: event.tool_name!, data: event.tool_data! }
              const updated = completedToolResultsRef.current.filter(r => r.toolName !== event.tool_name)
              updated.push(newResult)
              completedToolResultsRef.current = updated
              setCompletedToolResults([...updated])
            }
            break
          case 'done': {
            // Build metadata matching the DB format so cards render from persisted messages
            const toolResults = completedToolResultsRef.current
            const metadata = toolResults.length > 0
              ? {
                  tool_results: toolResults.map(r => ({
                    tool_name: r.toolName,
                    ...r.data,
                  })),
                }
              : null

            const assistantMessage: Message = {
              id: event.message_id || `temp-${Date.now()}`,
              session_id: sessionId,
              role: 'assistant',
              content: streamingContentRef.current,
              metadata_: metadata,
              created_at: new Date().toISOString(),
            }

            queryClient.setQueryData(
              ['session', sessionId],
              (old: { messages: Message[] } | undefined) => {
                if (!old) return old
                return {
                  ...old,
                  messages: [...old.messages, assistantMessage],
                }
              }
            )

            setStreamingContent('')
            streamingContentRef.current = ''
            setIsStreaming(false)
            setActiveToolName(null)
            setCompletedToolResults([])
            completedToolResultsRef.current = []
            break
          }
          case 'error':
            onError?.(event.content || 'Unknown error')
            setIsStreaming(false)
            setStreamingContent('')
            streamingContentRef.current = ''
            setActiveToolName(null)
            setCompletedToolResults([])
            completedToolResultsRef.current = []
            break
        }
      }

      const handleError = (error: Error) => {
        onError?.(error.message)
        setIsStreaming(false)
        setStreamingContent('')
        streamingContentRef.current = ''
        setActiveToolName(null)
      }

      const handleComplete = () => {
        // Stream completed without explicit 'done' event
        // This shouldn't happen normally, but handle it gracefully
      }

      abortControllerRef.current = apiStreamPost(
        `/sessions/${sessionId}/messages`,
        { content: content.trim() },
        handleEvent,
        handleError,
        handleComplete
      )
    },
    [sessionId, isStreaming, queryClient, onError]
  )

  const cancelStream = useCallback(() => {
    abortControllerRef.current?.abort()
    setIsStreaming(false)
    setStreamingContent('')
    streamingContentRef.current = ''
    setActiveToolName(null)
    setCompletedToolResults([])
    completedToolResultsRef.current = []
  }, [])

  return {
    streamingContent,
    isStreaming,
    activeToolName,
    completedToolResults,
    sendMessage,
    cancelStream,
  }
}
