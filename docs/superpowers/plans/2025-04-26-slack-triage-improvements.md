# Slack Triage Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve the Slack triage digest system to include all remaining messages in end-of-day summaries, enhance P3 summary quality, consolidate thread summaries, and add channel-level controls for summary behavior.

**Architecture:** Four independent improvements that touch different parts of the triage system: digest scheduling, summary generation, message grouping, and channel configuration.

**Tech Stack:** Python (FastAPI, SQLAlchemy), Slack API, LLM integration

---

## Overview of Changes

| Issue | Root Cause | Solution |
|-------|------------|----------|
| P1/P2 messages delayed to next day | P3 daily digest only includes P3 items | Add `end_of_day` digest type that collects all priorities |
| P3 summaries too brief | Generic prompt doesn't emphasize detail for P3 | Enhance P3-specific prompts with more detail requirements |
| Duplicate summaries for threads | Initial message and replies grouped separately | Group initial message with its replies in `group_messages` |
| Can't exclude thread replies from summaries | No channel-level summary behavior control | Add `summary_behavior` field to `MonitoredChannel` |

---

## Task 1: End-of-Day Summary Includes All Priorities

**Files:**
- Modify: `backend/app/services/digest_scheduler.py`
- Modify: `backend/app/worker/tasks.py`
- Modify: `backend/app/db/repositories/triage.py`
- Test: `backend/tests/services/test_triage_delivery.py`

**Problem:** Currently the P3 daily digest only fetches P3 items. The user wants ALL remaining unsummarized messages (P1, P2, P3) to be included in the end-of-day summary, so only messages that arrive AFTER the digest are shown at the start of the next day.

**Solution:** When the P3 digest time triggers, fetch ALL unalerted items across all priorities and send them in one consolidated end-of-day digest.

### Task 1.1: Update Repository Method

- [ ] **Step 1: Add repository method for all-priority items**

In `backend/app/db/repositories/triage.py`, add a new method:

```python
async def get_unalerted_all_priorities(
    self, user_id: str
) -> list[TriageClassification]:
    """Get all items queued for digest across all priorities (P1, P2, P3)."""
    result = await self.db.execute(
        select(TriageClassification)
        .where(TriageClassification.user_id == user_id)
        .where(TriageClassification.priority_level.in_(["p1", "p2", "p3"]))
        .where(TriageClassification.queued_for_digest == True)
        .where(TriageClassification.focus_session_id.is_(None))
        .order_by(TriageClassification.priority_level.asc())
        .order_by(TriageClassification.created_at.asc())
    )
    return list(result.scalars().all())
```

- [ ] **Step 2: Run tests to verify existing functionality**

Run: `docker-compose -f docker-compose.dev.yml exec backend pytest tests/services/test_triage_delivery.py -v`
Expected: All tests pass

### Task 1.2: Update Digest Scheduler

- [ ] **Step 3: Modify scheduler to send end-of-day digest**

In `backend/app/services/digest_scheduler.py`, update the P3 digest scheduling around line 99-107:

```python
# Replace the existing P3 block with:
if (
    settings.p3_alerts_enabled
    and settings.p3_digest_time
    and current_time == settings.p3_digest_time
):
    logger.info(
        f"Scheduling end-of-day digest (all priorities) for user {user_id} at {current_time} ({user_tz})"
    )
    await self._enqueue_digest(pool, user_id, "all", "end_of_day")
```

### Task 1.3: Update send_digest Worker Task

- [ ] **Step 4: Handle `priority="all"` in send_digest task**

In `backend/app/worker/tasks.py`, update the `send_digest` function around line 484:

```python
# Replace:
# items = await class_repo.get_unalerted_scheduled_items(user_id, priority)

# With:
if priority == "all":
    items = await class_repo.get_unalerted_all_priorities(user_id)
else:
    items = await class_repo.get_unalerted_scheduled_items(user_id, priority)
```

- [ ] **Step 5: Update digest DM for end-of-day to show by priority sections**

In `backend/app/services/triage_delivery.py`, add a new method `send_end_of_day_digest_dm`:

```python
async def send_end_of_day_digest_dm(
    self,
    user_id: str,
    conversations: list["ConversationGroup"],
) -> None:
    """Send an end-of-day digest DM with conversations grouped by priority."""
    user = await self.user_repo.get(user_id)
    if not user or not user.slack_user_id:
        return

    try:
        slack_service = SlackService()
        lines = ["*End of Day Digest*\n"]

        # Group conversations by their highest priority
        p1_convs = [c for c in conversations if c.priority == "p1"]
        p2_convs = [c for c in conversations if c.priority == "p2"]
        p3_convs = [c for c in conversations if c.priority == "p3"]

        # Show P1 items first
        if p1_convs:
            lines.append("*P1 — Important:*")
            for i, conv in enumerate(p1_convs[:5], 1):
                channel = conv.channel_name or f"#{conv.channel_id}"
                conv_type_label = (
                    "Thread"
                    if conv.conversation_type == "thread"
                    else ("DM" if conv.conversation_type == "dm" else "Chat")
                )
                summary = conv.topic or await self.create_conversation_summary(conv)
                first_msg = min(conv.messages, key=lambda m: m.message_ts)
                link = f" <{first_msg.slack_permalink}|View>" if first_msg.slack_permalink else ""
                lines.append(f"{i}. *{conv_type_label} in #{channel}*")
                lines.append(f"   {summary}{link}\n")
            if len(p1_convs) > 5:
                lines.append(f"   _...and {len(p1_convs) - 5} more P1 items_\n")

        # Show P2 items
        if p2_convs:
            lines.append("*P2 — Notable:*")
            for i, conv in enumerate(p2_convs[:5], 1):
                channel = conv.channel_name or f"#{conv.channel_id}"
                conv_type_label = (
                    "Thread"
                    if conv.conversation_type == "thread"
                    else ("DM" if conv.conversation_type == "dm" else "Chat")
                )
                summary = conv.topic or await self.create_conversation_summary(conv)
                first_msg = min(conv.messages, key=lambda m: m.message_ts)
                link = f" <{first_msg.slack_permalink}|View>" if first_msg.slack_permalink else ""
                lines.append(f"{i}. *{conv_type_label} in #{channel}*")
                lines.append(f"   {summary}{link}\n")
            if len(p2_convs) > 5:
                lines.append(f"   _...and {len(p2_convs) - 5} more P2 items_\n")

        # Show P3 items
        if p3_convs:
            lines.append("*P3 — Daily Digest:*")
            for i, conv in enumerate(p3_convs[:5], 1):
                channel = conv.channel_name or f"#{conv.channel_id}"
                conv_type_label = (
                    "Thread"
                    if conv.conversation_type == "thread"
                    else ("DM" if conv.conversation_type == "dm" else "Chat")
                )
                summary = conv.topic or await self.create_conversation_summary(conv)
                first_msg = min(conv.messages, key=lambda m: m.message_ts)
                link = f" <{first_msg.slack_permalink}|View>" if first_msg.slack_permalink else ""
                lines.append(f"{i}. *{conv_type_label} in #{channel}*")
                lines.append(f"   {summary}{link}\n")
            if len(p3_convs) > 5:
                lines.append(f"   _...and {len(p3_convs) - 5} more P3 items_\n")

        if not (p1_convs or p2_convs or p3_convs):
            return

        await slack_service.send_message(
            channel=user.slack_user_id,
            text="\n".join(lines),
        )
    except Exception:
        logger.exception(f"Failed to send end-of-day digest DM for user={user_id}")
```

- [ ] **Step 6: Update send_digest to use end-of-day DM for all priorities**

In `backend/app/worker/tasks.py`, update the logic to call the appropriate DM method:

```python
# Around line 560, when priority == "all":
if priority == "all":
    await delivery.send_end_of_day_digest_dm(user_id, conversations)
else:
    await delivery.send_conversation_digest_dm(
        user_id, conversations, priority, digest_type
    )
```

- [ ] **Step 7: Write tests for the new functionality**

Add tests in `backend/tests/services/test_triage_delivery.py`:

```python
@pytest.mark.asyncio
async def test_end_of_day_digest_includes_all_priorities(db_session):
    """End-of-day digest should include P1, P2, and P3 items."""
    # Create items across all priorities
    # Call send_digest with priority="all"
    # Verify all items are included in the digest
    pass

@pytest.mark.asyncio
async def test_get_unalerted_all_priorities(db_session):
    """Repository should fetch items across all priorities."""
    # Create P1, P2, P3 items
    # Call get_unalerted_all_priorities
    # Verify all three are returned, sorted by priority
    pass
```

- [ ] **Step 8: Run tests to verify**

Run: `docker-compose -f docker-compose.dev.yml exec backend pytest tests/services/test_triage_delivery.py -v`
Expected: All tests pass

- [ ] **Step 9: Commit**

```bash
git add backend/app/services/digest_scheduler.py backend/app/worker/tasks.py backend/app/services/triage_delivery.py backend/app/db/repositories/triage.py backend/tests/services/test_triage_delivery.py
git commit -m "feat(triage): end-of-day digest includes all remaining messages (P1/P2/P3)"
```

---

## Task 2: Enhance P3 Summary Quality

**Files:**
- Modify: `backend/app/services/triage_delivery.py`
- Test: `backend/tests/services/test_triage_delivery.py`

**Problem:** P3 summaries are too brief and don't contain enough information.

**Solution:** Enhance the LLM prompt for P3 summaries to require more detail and context.

### Task 2.1: Enhance P3 Summary Prompt

- [ ] **Step 1: Update create_conversation_summary for P3**

In `backend/app/services/triage_delivery.py`, modify `create_conversation_summary` around line 650-736. Add a priority parameter and adjust the prompt:

```python
async def create_conversation_summary(
    self, conversation: "ConversationGroup", priority: str = "p2"
) -> str:
    """
    Create a summary for a single conversation.

    Args:
        conversation: ConversationGroup to summarize
        priority: Priority level for context-aware summary depth

    Returns:
        Summary string
    """
    messages = conversation.messages
    if not messages:
        return "Empty conversation"

    settings = get_settings()
    provider = get_llm_provider(
        settings.web_search_synthesis_model or "gemini-2.5-flash-lite"
    )

    mode = conversation.summarization_mode
    thread_ctx = conversation.thread_context

    # Base quality requirements
    quality_requirements = """
Requirements:
- Write 1-2 full sentences (never a single clause or fragment)
- Name participants by their display name (never use "user" or "a user")
- State the subject — what was discussed, decided, or asked
- Include the outcome or any open questions
"""

    # P3-specific enhanced requirements
    if priority == "p3":
        quality_requirements = """
Requirements:
- Write 2-3 detailed sentences that fully capture the context
- Name all participants by their display name
- Clearly state what was discussed, announced, or asked
- Include specific details: dates, times, action items, links shared
- Mention any decisions made or next steps agreed upon
- If it's an announcement, summarize the key information conveyed
- If it's a question, note whether it was answered and by whom
"""
    
    few_shot_examples = """
BAD: "User stated the build is broken."
BAD: "A discussion occurred about deployment."
BAD: "Message contains only an emoji."
BAD: "User announces their return to the channel."

GOOD: "Caitlin flagged that the main branch build was failing. Max identified a stale Docker cache as the cause and Caitlin triggered a rebuild, which resolved the issue."
GOOD: "Sara asked whether to roll back the 3.2.1 release after a customer-reported regression. Mike agreed and took the rollback; root cause investigation is still open."
GOOD: "Raj shared the Q3 planning doc and asked the platform team for feedback on the migration timeline by Friday."
"""
    
    # P3-specific examples
    if priority == "p3":
        few_shot_examples = """
BAD: "Someone announced they're leaving."
BAD: "A notification about a new hire."
BAD: "Discussion about lunch plans."

GOOD: "HR announced that Sarah Chen's last day will be Friday, March 15th. She's been with the team for 3 years on the infrastructure squad. A farewell gathering is planned for Thursday at 4pm in the main break room."
GOOD: "The team welcomed Alex Kumar as the new Senior Frontend Engineer starting Monday. Alex joins from Stripe and will be working on the dashboard redesign project."
GOOD: "Jamie organized a team lunch for Friday at noon at The Local Diner to celebrate the successful Q4 release. 8 people confirmed attendance, RSVP by Thursday EOD."
"""

    # ... rest of the function remains the same, just pass priority to the prompt context
```

- [ ] **Step 2: Update callers to pass priority**

Find all callers of `create_conversation_summary` and update them to pass the conversation's priority:

```python
# In prepare_conversation_digest and other callers:
summary = conv.topic or await self.create_conversation_summary(conv, conv.priority)
```

- [ ] **Step 3: Write tests for enhanced P3 summaries**

```python
@pytest.mark.asyncio
async def test_p3_summaries_include_more_detail():
    """P3 summaries should include more detailed information."""
    # Create a P3 conversation
    # Call create_conversation_summary with priority="p3"
    # Verify the summary is 2-3 sentences and includes specific details
    pass
```

- [ ] **Step 4: Run tests**

Run: `docker-compose -f docker-compose.dev.yml exec backend pytest tests/services/test_triage_delivery.py -v`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/triage_delivery.py backend/tests/services/test_triage_delivery.py
git commit -m "feat(triage): enhance P3 summary prompts for more detailed output"
```

---

## Task 3: Consolidate Thread Initial Messages with Replies

**Files:**
- Modify: `backend/app/services/digest_grouper.py`
- Test: `backend/tests/services/test_digest_grouper.py`

**Problem:** Currently, the initial message in a thread and subsequent replies are being summarized separately. The user wants one consolidated summary for both.

**Root Cause:** In `group_messages`, only messages with `thread_ts` set are grouped as threads. The initial message in a thread (where `message_ts == thread_ts` or `thread_ts` is None) is not being grouped with its replies.

**Solution:** When grouping, identify thread parent messages and include them in the thread group.

### Task 3.1: Understand Thread Message Structure

A Slack thread works as follows:
- **Thread parent (initial message):** `thread_ts` is None OR `message_ts == thread_ts`
- **Thread replies:** `thread_ts` is set to the parent's `message_ts`

### Task 3.2: Update group_messages Logic

- [ ] **Step 1: Modify group_messages to include thread parents**

In `backend/app/services/digest_grouper.py`, update the `group_messages` method around line 318-371:

```python
def group_messages(
    self, messages: list[TriageClassification]
) -> list[ConversationGroup]:
    """
    Group messages into conversations.

    Strategy:
    1. Thread messages (same thread_ts) → one conversation (deterministic)
       - Includes both the parent message AND all replies
    2. DM messages (same channel) → one conversation per DM channel
    3. Channel messages without thread → grouped by LLM later

    Args:
        messages: List of TriageClassification items to group

    Returns:
        List of ConversationGroup objects
    """
    if not messages:
        return []

    conversations: list[ConversationGroup] = []
    thread_groups: dict[str, list[TriageClassification]] = {}
    dm_groups: dict[str, list[TriageClassification]] = {}
    channel_messages: list[TriageClassification] = []

    # First pass: identify all thread_ts values from replies
    all_thread_ts_values: set[str] = set()
    for msg in messages:
        if msg.thread_ts:
            all_thread_ts_values.add(msg.thread_ts)

    for msg in messages:
        if msg.thread_ts:
            # Thread reply - group by thread_ts
            if msg.thread_ts not in thread_groups:
                thread_groups[msg.thread_ts] = []
            thread_groups[msg.thread_ts].append(msg)
        elif msg.message_ts in all_thread_ts_values:
            # This is a thread parent (initial message) - add to its thread group
            if msg.message_ts not in thread_groups:
                thread_groups[msg.message_ts] = []
            thread_groups[msg.message_ts].append(msg)
        elif msg.channel_id.startswith("D"):
            # DM - group by channel
            if msg.channel_id not in dm_groups:
                dm_groups[msg.channel_id] = []
            dm_groups[msg.channel_id].append(msg)
        else:
            # Channel message without thread - will be grouped by LLM
            channel_messages.append(msg)

    # Create thread conversations
    for thread_ts, msgs in thread_groups.items():
        sorted_msgs = sorted(msgs, key=lambda m: m.message_ts)
        conversations.append(
            ConversationGroup(
                id=f"thread:{thread_ts}",
                messages=sorted_msgs,
                conversation_type="thread",
                channel_id=sorted_msgs[0].channel_id,
                channel_name=sorted_msgs[0].channel_name,
                thread_ts=thread_ts,
                participants=list({m.sender_slack_id for m in sorted_msgs}),
            )
        )

    # ... rest of the method remains the same
```

- [ ] **Step 2: Write tests for thread consolidation**

In `backend/tests/services/test_digest_grouper.py`:

```python
@pytest.mark.asyncio
async def test_thread_parent_grouped_with_replies():
    """Thread parent message should be grouped with its replies."""
    # Create a thread parent (message_ts="100.0", thread_ts=None or "100.0")
    # Create thread replies (thread_ts="100.0")
    # Group messages
    # Verify parent and replies are in the same ConversationGroup
    pass

@pytest.mark.asyncio
async def test_standalone_message_not_grouped_as_thread():
    """Messages without thread context should not be grouped as threads."""
    # Create a standalone message (no thread_ts, no replies referencing it)
    # Group messages
    # Verify it's grouped as channel message, not thread
    pass
```

- [ ] **Step 3: Run tests**

Run: `docker-compose -f docker-compose.dev.yml exec backend pytest tests/services/test_digest_grouper.py -v`

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/digest_grouper.py backend/tests/services/test_digest_grouper.py
git commit -m "fix(triage): consolidate thread parent with replies in single summary"
```

---

## Task 4: Channel-Level Summary Behavior Control

**Files:**
- Modify: `backend/app/db/models/triage.py`
- Create: `backend/alembic/versions/XXX_add_summary_behavior_to_monitored_channel.py`
- Modify: `backend/app/services/digest_grouper.py`
- Modify: `backend/app/services/triage_delivery.py`
- Modify: `backend/app/schemas/triage.py`
- Modify: `backend/app/api/triage.py`
- Test: `backend/tests/services/test_digest_grouper.py`

**Problem:** Users want channel-level control over what gets summarized. Example: a P3 channel for employee departure notices where the user wants the initial notification but doesn't care about the responses.

**Solution:** Add a `summary_behavior` field to `MonitoredChannel` with options like:
- `default`: Include all messages and thread replies (current behavior)
- `initial_only`: Only include the initial message, ignore thread replies
- `summary_only`: Only include in daily/periodic summaries, no individual alerts

### Task 4.1: Add Database Field

- [ ] **Step 1: Add summary_behavior field to MonitoredChannel model**

In `backend/app/db/models/triage.py`, add to the `MonitoredChannel` class around line 114:

```python
# Summary behavior control
# default | initial_only | summary_only
summary_behavior: Mapped[str] = mapped_column(
    String(20), default="default", server_default="default"
)
```

- [ ] **Step 2: Create migration**

Run: `cd backend && uv run alembic revision --autogenerate -m "add summary_behavior to monitored_channel"`

Then edit the generated migration file to ensure it has the correct default:

```python
# In the upgrade():
op.add_column('monitored_channels', sa.Column('summary_behavior', sa.String(20), server_default='default', nullable=False))

# In the downgrade():
op.drop_column('monitored_channels', 'summary_behavior')
```

- [ ] **Step 3: Run migration**

Run: `docker-compose -f docker-compose.dev.yml exec backend alembic upgrade head`

### Task 4.2: Update Schemas

- [ ] **Step 4: Add to MonitoredChannelCreate/Update schemas**

In `backend/app/schemas/triage.py`, add the field to the relevant schemas:

```python
class MonitoredChannelCreate(BaseModel):
    slack_channel_id: str
    channel_name: str
    channel_type: str = "public"
    priority: str = "medium"
    triage_instructions: str | None = None
    summary_behavior: str = "default"  # Add this

class MonitoredChannelUpdate(BaseModel):
    is_active: bool | None = None
    priority: str | None = None
    triage_instructions: str | None = None
    summary_behavior: str | None = None  # Add this

class MonitoredChannelResponse(BaseModel):
    id: str
    slack_channel_id: str
    channel_name: str
    channel_type: str
    priority: str
    is_active: bool
    is_hidden: bool
    triage_instructions: str | None
    summary_behavior: str  # Add this
    created_at: datetime
    updated_at: datetime
```

### Task 4.3: Apply Summary Behavior in Digest Grouper

- [ ] **Step 5: Filter thread replies based on summary_behavior**

In `backend/app/services/digest_grouper.py`, modify `group_messages_with_context` to filter based on channel settings:

```python
async def group_messages_with_context(
    self,
    messages: list[TriageClassification],
    user_id: str,
    db,
) -> list[ConversationGroup]:
    """Group messages with full thread context for better summarization.
    
    Respects channel-level summary_behavior settings:
    - default: Include all messages and replies
    - initial_only: Only include thread parents, exclude replies
    """
    if not messages:
        return []

    # Fetch channel summary behaviors
    from app.db.repositories.triage import MonitoredChannelRepository
    channel_repo = MonitoredChannelRepository(db)
    channels = await channel_repo.get_by_user(user_id, active_only=False)
    channel_settings = {c.slack_channel_id: c for c in channels}
    
    # Filter messages based on summary_behavior
    filtered_messages = []
    for msg in messages:
        channel = channel_settings.get(msg.channel_id)
        if channel and channel.summary_behavior == "initial_only":
            # Only include if this is a thread parent (no thread_ts) or the parent itself
            if msg.thread_ts and msg.thread_ts != msg.message_ts:
                # This is a reply, skip it
                continue
        filtered_messages.append(msg)
    
    # Proceed with grouping the filtered messages
    conversations = self.group_messages(filtered_messages)
    # ... rest of the method
```

- [ ] **Step 6: Add helper to identify if message is a thread reply**

Add a helper property or function to identify thread replies:

```python
def is_thread_reply(msg: TriageClassification) -> bool:
    """Check if a message is a reply in a thread (not the parent)."""
    return msg.thread_ts is not None and msg.thread_ts != msg.message_ts
```

### Task 4.4: Update API Endpoint

- [ ] **Step 7: Update PATCH endpoint to accept summary_behavior**

In `backend/app/api/triage.py`, ensure the PATCH endpoint for monitored channels accepts the new field:

```python
@router.patch("/channels/{channel_id}")
async def update_monitored_channel(
    channel_id: str,
    update_data: MonitoredChannelUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # ... existing logic
    if update_data.summary_behavior is not None:
        channel.summary_behavior = update_data.summary_behavior
    # ...
```

### Task 4.5: Write Tests

- [ ] **Step 8: Write tests for summary_behavior filtering**

```python
@pytest.mark.asyncio
async def test_initial_only_excludes_thread_replies(db_session):
    """Channels with initial_only should exclude thread replies from summaries."""
    # Create a monitored channel with summary_behavior="initial_only"
    # Create a thread parent and replies
    # Group messages
    # Verify only the parent is included
    pass

@pytest.mark.asyncio
async def test_default_includes_all_messages(db_session):
    """Channels with default behavior should include all messages."""
    # Create a monitored channel with summary_behavior="default"
    # Create a thread parent and replies
    # Group messages
    # Verify both parent and replies are included
    pass
```

- [ ] **Step 9: Run tests**

Run: `docker-compose -f docker-compose.dev.yml exec backend pytest tests/services/test_digest_grouper.py -v`

- [ ] **Step 10: Commit**

```bash
git add backend/app/db/models/triage.py backend/alembic/versions/XXX_add_summary_behavior.py backend/app/schemas/triage.py backend/app/services/digest_grouper.py backend/app/api/triage.py backend/tests/services/test_digest_grouper.py
git commit -m "feat(triage): add channel-level summary_behavior control"
```

---

## Task 5: Frontend Support for Summary Behavior

**Files:**
- Modify: `frontend/src/types/triage.ts`
- Modify: `frontend/src/pages/TriageSettingsPage.tsx`
- Modify: `frontend/src/components/triage/MonitoredChannelCard.tsx` (if exists)
- Modify: `frontend/src/hooks/useTriage.ts`
- Test: `frontend/src/components/triage/__tests__/MonitoredChannelCard.test.tsx`

### Task 5.1: Update Types

- [ ] **Step 1: Add summary_behavior to types**

In `frontend/src/types/triage.ts`:

```typescript
export interface MonitoredChannel {
  id: string;
  slack_channel_id: string;
  channel_name: string;
  channel_type: string;
  priority: string;
  is_active: boolean;
  is_hidden: boolean;
  triage_instructions: string | null;
  summary_behavior: "default" | "initial_only";  // Add this
  created_at: string;
  updated_at: string;
}

export interface MonitoredChannelUpdate {
  is_active?: boolean;
  priority?: string;
  triage_instructions?: string | null;
  summary_behavior?: "default" | "initial_only";  // Add this
}
```

### Task 5.2: Update Hook

- [ ] **Step 2: Ensure useTriage hook handles the new field**

In `frontend/src/hooks/useTriage.ts`, verify the update mutation includes `summary_behavior`:

```typescript
const updateMonitoredChannel = useMutation({
  mutationFn: async ({ channelId, data }: { channelId: string; data: MonitoredChannelUpdate }) => {
    const response = await fetch(`/api/triage/channels/${channelId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!response.ok) throw new Error("Failed to update channel");
    return response.json();
  },
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ["triage", "channels"] });
  },
});
```

### Task 5.3: Add UI Component

- [ ] **Step 3: Add dropdown to channel settings**

In `frontend/src/pages/TriageSettingsPage.tsx` or `MonitoredChannelCard.tsx`:

```tsx
<Select
  value={channel.summary_behavior}
  onValueChange={(value) => updateMonitoredChannel.mutate({
    channelId: channel.id,
    data: { summary_behavior: value as "default" | "initial_only" }
  })}
>
  <SelectTrigger>
    <SelectValue />
  </SelectTrigger>
  <SelectContent>
    <SelectItem value="default">
      <div>
        <div className="font-medium">Default</div>
        <div className="text-xs text-muted-foreground">Include all messages and replies</div>
      </div>
    </SelectItem>
    <SelectItem value="initial_only">
      <div>
        <div className="font-medium">Initial Messages Only</div>
        <div className="text-xs text-muted-foreground">Exclude thread replies from summaries</div>
      </div>
    </SelectItem>
  </SelectContent>
</Select>
```

- [ ] **Step 4: Write tests**

```tsx
test("summary_behavior dropdown updates channel setting", async () => {
  render(<MonitoredChannelCard channel={mockChannel} />);
  const select = screen.getByRole("combobox", { name: /summary/i });
  await userEvent.click(select);
  await userEvent.click(screen.getByText("Initial Messages Only"));
  expect(mockUpdateChannel).toHaveBeenCalledWith({
    channelId: "test-id",
    data: { summary_behavior: "initial_only" }
  });
});
```

- [ ] **Step 5: Run frontend build to verify no TypeScript errors**

Run: `cd frontend && npm run build`

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/triage.ts frontend/src/hooks/useTriage.ts frontend/src/pages/TriageSettingsPage.tsx frontend/src/components/triage/
git commit -m "feat(frontend): add summary_behavior control to channel settings"
```

---

## Verification

After all tasks are complete, verify the improvements:

1. **End-of-day digest:** Check that P1, P2, and P3 items all appear in the 5pm (or configured time) digest
2. **P3 summaries:** Compare before/after summary quality for P3 conversations
3. **Thread consolidation:** Verify thread parents and replies appear in a single summary
4. **Channel summary behavior:** Set a channel to "initial_only" and verify thread replies are excluded

---

## Questions for User

1. **Priority for end-of-day digest:** When showing the end-of-day digest, should P1 items always appear first, or should we group by channel? (Current plan: group by priority)

2. **Summary behavior options:** Are the three options (`default`, `initial_only`, `summary_only`) sufficient, or would you like additional options like:
   - `threads_only`: Only show thread summaries, no standalone messages
   - `mentions_only`: Only show messages that mention the user

3. **Frontend priority:** Should the frontend changes be included in this implementation, or can they be done separately?
