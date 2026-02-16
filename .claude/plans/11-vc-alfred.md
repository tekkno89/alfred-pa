# Phase 11: VC Alfred — Voice Chat Desktop App

**Status:** Design / Brainstorm
**Priority:** Future

## Goal

Build a cross-platform application (VC Alfred) that runs in the background and allows the user to have voice conversations with Alfred via speech-to-text (STT) and text-to-speech (TTS). Voice sessions are tracked as regular sessions in the web UI, giving the user a full transcript and history across all interfaces (web, Slack, voice).

The primary desktop UX lives in the system tray / toolbar. When a voice conversation is active, a window appears with an animated Alfred visual. The same app should eventually support iOS and Android.

---

## 1. Session Lifecycle (Hybrid Timeout)

Voice sessions use a hybrid approach to determine when a conversation has ended:

### Primary: Conversational Detection
- Alfred monitors for natural conversation closers ("thanks, that's all," "goodbye," "I'm done," etc.)
- When detected, Alfred confirms: "Sounds like we're wrapping up. I'll close this session. Talk to you later."
- Session is marked as ended after confirmation

### Fallback: Idle Timeout
- If no speech is detected for a configurable duration (default: 5-10 minutes), Alfred enters a grace period
- During grace period, Alfred asks: "Are you still there?" via TTS
- If no response within ~30 seconds, session is closed automatically
- Timeout duration should be a user preference (stored in settings)

### Session State
- Sessions created by VC Alfred use the existing session model with a `source: "voice"` indicator (similar to Slack's `source: "slack"`)
- All messages (STT transcriptions and TTS responses) are stored as regular messages in the database
- Session appears in the web UI sidebar alongside web and Slack sessions

---

## 2. Manual New Session (Intent Detection)

Rather than requiring a hard-coded keyword, Alfred uses intent detection to determine if the user wants to start a new session:

- During an active session, if Alfred detects that the user's intent is to start a new/fresh conversation, Alfred asks for confirmation: "It sounds like you'd like to start a new conversation. Should I wrap up this one and start fresh?"
- User confirms via voice ("yes" / "yeah, let's do that") and Alfred closes the current session and opens a new one
- User declines ("no, this is related") and Alfred continues in the current session
- This keeps the interaction natural — no special commands to memorize

---

## 3. Resuming Recent Conversations

Voice UX is bad for long lists. Keep it short and interactive:

### Flow
1. User asks something like "Can we pick up where we left off?" or "What were we talking about earlier?"
2. Alfred reads the **3 most recent sessions** with short summaries:
   - "Your last three conversations were: one, grocery planning from this morning; two, the backend refactor from yesterday; and three, travel booking from Monday. Which one would you like to continue, or should I look further back?"
3. User picks by name or number: "continue the travel one" / "number two"
4. Alfred reopens that session (or creates a new session that references it for context continuity)
5. If none match: "Would you like me to look further back, or check the web dashboard?"

### Prerequisite: Session Summarization
- Auto-generate a short title/summary for each session at close time (or periodically)
- Store as a field on the session model (e.g., `summary: str`)
- This benefits all interfaces, not just voice — the web UI and Slack can use these summaries too
- Could use a lightweight LLM call to summarize the last N messages when a session ends
- **This is already in the backlog** ("Session summaries for search" in Future Enhancements) — VC Alfred makes it a hard requirement rather than a nice-to-have

---

## 4. Human-in-the-Loop Confirmations

Different actions require different confirmation channels based on complexity and risk.

### Tier 1: Voice Confirmation (Low-Risk Actions)
- Alfred reads back the action: "I'm going to search the web for flight prices to Tokyo. Should I go ahead?"
- User responds with "yes" / "go ahead" / "no, cancel"
- Suitable for: web searches, simple lookups, reading information back

### Tier 2: Voice with Dashboard Review (Medium-Risk Actions)
- Alfred summarizes what it wants to do and notifies the user that details are available in the web UI
- "I've drafted a response to that email. I've sent it to your Alfred dashboard for review. Let me know when you've looked it over, or say 'send it' if you trust me."
- Suitable for: drafting messages, modifying data, multi-step actions

### Tier 3: Web UI Required (High-Risk or Complex Input)
- Alfred routes the confirmation entirely to the web UI
- "This needs your review in the dashboard. I've flagged it for you." Optionally opens the browser to the pending confirmation
- The web UI shows the pending action with approve/deny/custom-response options
- Once the user acts in the web UI, VC Alfred receives the callback and continues: "Got it, I'll proceed with that."
- Suitable for: financial actions, account changes, anything needing detailed review

### API Design
- Tool definitions include a `confirmation_level` field: `voice`, `dashboard_review`, `web_required`
- The agent runtime routes the confirmation request to the appropriate channel based on this field
- Pending confirmations are stored in the database so they persist across app restarts
- The web UI gets a "Pending Actions" section for Tier 2 and 3 confirmations

---

## 5. Transcription Display in Web UI

Even though the interaction happens via voice, the web UI should show the full transcript:

- STT output is stored as the user's message content
- TTS output (Alfred's response) is stored as the assistant's message content
- Messages are tagged with `input_mode: "voice"` so the UI can optionally render a voice indicator (mic icon, audio waveform, etc.)
- User can read back the conversation in the web UI at any time
- Enables debugging of STT misinterpretations

---

## 6. Latency & Filler Responses

Voice interactions are sensitive to silence. Long pauses feel broken.

- When Alfred is processing (LLM call, tool execution, search), it should emit filler acknowledgments via TTS:
  - "Looking that up now..."
  - "One moment..."
  - "Let me check on that..."
- These fillers should be generated quickly (pre-canned or ultra-fast LLM call) while the real work happens in the background
- Once the actual response is ready, Alfred speaks it naturally
- For long-running tool calls (web search with multiple iterations), Alfred can give progress updates: "I'm searching for that... found some results, let me read through them..."

---

## 7. Privacy & Mic Control

An app with mic access needs clear trust signals:

- **Mute toggle**: Always accessible via system tray icon, keyboard shortcut, or voice command ("Alfred, mute")
- **Visual indicator**: System tray icon changes color/state when mic is active vs. muted
- **Wake word (local)**: "Hey Alfred" triggers listening — wake word detection runs entirely on-device for privacy (no audio sent to cloud until wake word is detected)
  - Push-to-talk as an alternative activation method (user preference)
  - Hybrid default: push-to-talk enabled, wake word opt-in
- **Session recording opt-out**: Option to not persist voice session transcripts (ephemeral mode)
- **Audio data**: Raw audio is not stored — only STT text. Audio is processed in real-time and discarded.

---

## 8. App Technology & UX

### Framework: Flet (Python + Flutter)
- Python-based, aligns with the backend language
- Compiles to desktop (macOS, Windows, Linux) and mobile (iOS, Android) from a single codebase
- Supports system tray, notifications, and native platform features via Flutter

### Desktop UX
- **Primary interface is the system tray / toolbar icon**
  - Icon shows connection status (connected, disconnected/unreachable, muted, active conversation)
  - Right-click menu: Start conversation, Mute/Unmute, Settings, Quit
- **Conversation window**: When a voice conversation is active, a small window appears with an animated Alfred visual (avatar, waveform, or similar)
  - Appears with an entrance animation when conversation starts
  - Shows current state: listening, thinking, speaking
  - Dismisses when conversation ends
  - Minimal chrome — not a full app window, more like a floating widget
- **Backend unreachable indicator**: System tray icon changes to a distinct state (e.g., grayed out, warning badge) when the backend API is unreachable. Alfred should not attempt voice interactions while disconnected.

### Mobile UX (Future)
- Same Flet codebase, adapted for mobile conventions
- Push notification for confirmations
- Background audio session for voice conversations

### STT: Whisper (Local)
- Runs on-device for privacy and lower latency
- Use whisper.cpp or faster-whisper for efficient local inference
- Configurable model size (tiny for speed, base/small for accuracy)

### TTS: Qwen3 TTS
- Evaluate streaming support — if available, enable it as a toggleable option in settings
- Streaming TTS: Alfred starts speaking before the full response is generated (lower perceived latency)
- Non-streaming TTS: Full response is synthesized before playback (more predictable, default)
- Fallback to system native TTS if Qwen3 is unavailable

---

## 9. Prerequisites / Dependencies

Before building VC Alfred, these should be in place:

- [ ] **Session summarization** — auto-generate session summaries at close time (needed for conversation browsing)
- [ ] **Confirmation system** — generalized human-in-the-loop confirmation model in the backend (benefits all interfaces)
- [ ] **Session source tracking** — extend session model with `source` field if not already present (web, slack, voice)
- [ ] **Message metadata** — support `input_mode` field on messages to distinguish voice vs. text input

---

## 10. Open Questions

- How do we handle noisy environments or accidental wake word activations? (TBD — figure out during implementation)
- Can Qwen3 TTS stream output? If yes, make it a toggle. If not, use full synthesis.
- What Whisper model size is the right default? (tiny vs. base vs. small — tradeoff between speed and accuracy)
- What's the right UX for offline/unreachable mode beyond the tray indicator? (queue messages? retry? notify?)
- What should the Alfred conversation window animation look like? (avatar, waveform, orb, etc.)
