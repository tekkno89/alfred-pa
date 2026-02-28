import { useRef, useEffect, useCallback, type KeyboardEvent, type RefObject } from 'react'

// Matches any list marker: unordered (- * +), checkbox, or ordered (1.)
const LIST_RE = /^(\s*)([-*+]\s\[[ x]\]\s|[-*+]\s|\d+\.\s)/

/**
 * Adds markdown-aware keyboard handling to a <textarea>:
 *  - Enter on a list line: continues the list marker (auto-increments numbered lists)
 *  - Enter on an empty list line (just the marker): removes it and stops the list
 *  - Tab on a list line: indents the entire line
 *  - Shift+Tab on a list line: outdents the entire line
 *  - Tab on plain text: inserts 2 spaces at cursor
 *  - Shift+Enter: always plain newline (no list continuation)
 */
export function useMarkdownEditor(
  body: string,
  setBody: (value: string) => void,
): {
  textareaRef: RefObject<HTMLTextAreaElement>
  onKeyDown: (e: KeyboardEvent<HTMLTextAreaElement>) => void
} {
  const textareaRef = useRef<HTMLTextAreaElement>(null!)
  const pendingCursor = useRef<number | null>(null)

  // After React re-renders with the new body, restore cursor position
  useEffect(() => {
    if (pendingCursor.current !== null && textareaRef.current) {
      const pos = pendingCursor.current
      textareaRef.current.selectionStart = pos
      textareaRef.current.selectionEnd = pos
      pendingCursor.current = null
    }
  }, [body])

  const onKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      const { selectionStart, selectionEnd } = e.currentTarget

      // --- Tab / Shift+Tab ---
      if (e.key === 'Tab') {
        e.preventDefault()
        const hasSelection = selectionStart !== selectionEnd
        const before = body.slice(0, selectionStart)
        const lineStart = before.lastIndexOf('\n') + 1

        if (!hasSelection) {
          const lineEndIdx = body.indexOf('\n', lineStart)
          const lineEndPos = lineEndIdx === -1 ? body.length : lineEndIdx
          const currentLine = body.slice(lineStart, lineEndPos)
          const isListLine = LIST_RE.test(currentLine)

          if (isListLine) {
            // Indent/outdent the entire list line
            if (e.shiftKey) {
              const spaces = currentLine.match(/^ {1,2}/)
              if (!spaces) return // already at level 0
              const removed = spaces[0].length
              const newBody = body.slice(0, lineStart) + currentLine.slice(removed) + body.slice(lineEndPos)
              setBody(newBody)
              pendingCursor.current = Math.max(lineStart, selectionStart - removed)
            } else {
              const newBody = body.slice(0, lineStart) + '  ' + currentLine + body.slice(lineEndPos)
              setBody(newBody)
              pendingCursor.current = selectionStart + 2
            }
          } else if (e.shiftKey) {
            // Outdent plain line
            const currentLine = body.slice(lineStart, lineEndPos)
            const spaces = currentLine.match(/^ {1,2}/)
            if (spaces) {
              const removed = spaces[0].length
              const newBody = body.slice(0, lineStart) + currentLine.slice(removed) + body.slice(lineEndPos)
              setBody(newBody)
              pendingCursor.current = Math.max(lineStart, selectionStart - removed)
            }
          } else {
            // Plain text: insert 2 spaces at cursor
            const after = body.slice(selectionStart)
            setBody(before + '  ' + after)
            pendingCursor.current = selectionStart + 2
          }
        } else {
          // Indent/outdent all selected lines
          const selLineStart = body.lastIndexOf('\n', selectionStart - 1) + 1
          const lineEnd = body.indexOf('\n', selectionEnd)
          const blockEnd = lineEnd === -1 ? body.length : lineEnd
          const block = body.slice(selLineStart, blockEnd)
          const lines = block.split('\n')

          let newLines: string[]
          let delta = 0
          if (e.shiftKey) {
            newLines = lines.map((line) => {
              const spaces = line.match(/^ {1,2}/)
              if (spaces) {
                delta -= spaces[0].length
                return line.slice(spaces[0].length)
              }
              return line
            })
          } else {
            newLines = lines.map((line) => {
              delta += 2
              return '  ' + line
            })
          }

          const newBlock = newLines.join('\n')
          const newBody = body.slice(0, selLineStart) + newBlock + body.slice(blockEnd)
          setBody(newBody)

          const firstLineDelta = e.shiftKey
            ? -(lines[0].match(/^ {1,2}/)?.[0].length ?? 0)
            : 2
          pendingCursor.current = null
          requestAnimationFrame(() => {
            if (textareaRef.current) {
              textareaRef.current.selectionStart = Math.max(selLineStart, selectionStart + firstLineDelta)
              textareaRef.current.selectionEnd = blockEnd + delta
            }
          })
        }
        return
      }

      // --- Enter ---
      if (e.key === 'Enter' && !e.shiftKey && !e.metaKey && !e.ctrlKey) {
        const before = body.slice(0, selectionStart)
        const after = body.slice(selectionEnd)

        const lastNewline = before.lastIndexOf('\n')
        const currentLine = before.slice(lastNewline + 1)

        const match = currentLine.match(LIST_RE)
        if (!match) return // Let default Enter behavior happen

        const [fullMatch, indent, marker] = match
        const textAfterMarker = currentLine.slice(fullMatch.length)

        // If the line is just a bare marker with no text, remove it and stop the list
        if (!textAfterMarker.trim()) {
          e.preventDefault()
          const lineStart = lastNewline + 1
          setBody(body.slice(0, lineStart) + '\n' + after)
          pendingCursor.current = lineStart + 1
          return
        }

        // Continue the list
        e.preventDefault()
        let nextMarker: string
        const numberedMatch = marker.match(/^(\d+)\.\s$/)
        if (numberedMatch) {
          nextMarker = `${parseInt(numberedMatch[1], 10) + 1}. `
        } else if (marker.match(/^[-*+]\s\[[ x]\]\s$/)) {
          nextMarker = marker.replace(/\[[ x]\]/, '[ ]')
        } else {
          nextMarker = marker
        }

        const insertion = '\n' + indent + nextMarker
        setBody(before + insertion + after)
        pendingCursor.current = selectionStart + insertion.length
      }
    },
    [body, setBody],
  )

  return { textareaRef, onKeyDown }
}
