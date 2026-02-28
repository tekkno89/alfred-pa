import { useState, useMemo } from 'react'
import Picker from '@emoji-mart/react'
import data from '@emoji-mart/data'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Button } from '@/components/ui/button'

interface EmojiPickerFieldProps {
  value: string
  onChange: (code: string) => void
  id?: string
}

/** Extract the emoji ID from a Slack-style shortcode like `:no_bell:` */
function parseShortcode(code: string): string | null {
  const match = code.match(/^:([a-z0-9_+-]+):$/)
  return match ? match[1] : null
}

/** Resolve a Slack shortcode to its native emoji character using emoji-mart data */
function resolveNativeEmoji(code: string): string | null {
  const id = parseShortcode(code)
  if (!id) return null

  const emojiData = (data as { emojis: Record<string, { skins: { native: string }[] }> }).emojis
  // Check direct ID match
  const emoji = emojiData[id]
  if (emoji?.skins?.[0]?.native) {
    return emoji.skins[0].native
  }

  // Check aliases
  const aliases = (data as { aliases: Record<string, string> }).aliases
  const aliasTarget = aliases?.[id]
  if (aliasTarget) {
    const aliasEmoji = emojiData[aliasTarget]
    if (aliasEmoji?.skins?.[0]?.native) {
      return aliasEmoji.skins[0].native
    }
  }

  return null
}

export function EmojiPickerField({ value, onChange, id }: EmojiPickerFieldProps) {
  const [open, setOpen] = useState(false)

  const nativeEmoji = useMemo(() => resolveNativeEmoji(value), [value])

  const handleSelect = (emoji: { id: string; native: string }) => {
    onChange(`:${emoji.id}:`)
    setOpen(false)
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          id={id}
          variant="outline"
          role="combobox"
          aria-expanded={open}
          className="h-9 w-full justify-start gap-2 font-normal"
        >
          {nativeEmoji ? (
            <>
              <span className="text-lg leading-none">{nativeEmoji}</span>
              <span className="text-muted-foreground text-xs truncate">{value}</span>
            </>
          ) : (
            <span className="text-muted-foreground">{value || 'Pick emoji...'}</span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="start">
        <Picker
          data={data}
          onEmojiSelect={handleSelect}
          theme="auto"
          previewPosition="none"
          skinTonePosition="search"
        />
      </PopoverContent>
    </Popover>
  )
}
