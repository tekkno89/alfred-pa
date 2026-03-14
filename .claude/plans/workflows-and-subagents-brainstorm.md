# Workflows & Subagent Architecture - Brainstorm

Status: Brainstorming (not planned for implementation yet)

## Questions to Answer

1. How can Alfred monitor Slack conversations (DMs + channels) and track action items, commitments, and things I say I'll do or look into?
2. How can Alfred make recommendations like creating reminder tasks, adding/updating calendar events, and creating notes based on those tracked items?
3. How can Alfred produce end-of-day summaries of work done and things to plan for the next day or future?
4. Would subagents be a good pattern for handling these complex workflows while keeping Alfred focused on basic chat and simple tool tasks?

---

## Core Principle: Alfred as Orchestrator

Alfred stays lean — handles direct chat, simple tool calls (what's on my calendar, create a todo, quick web search). When something requires multi-step reasoning, coordination across systems, or longer-running work, Alfred hands it off to a specialized subagent and reports back the result.

This aligns with the existing architecture vision: "Alfred is the router agent, sub-agents can be added in `backend/app/agents/`".

### Why Subagents Make Sense Here

- **Context window hygiene** — Complex tasks (check 5 people's availability, find overlapping slots, rank by preference) pollute the conversation context with intermediate reasoning. A subagent does that in its own context and returns a clean result.
- **Focused prompts and toolsets** — Each subagent gets a system prompt tuned for its job with access to only the tools it needs. More reliable than a general-purpose agent trying to do everything.
- **Different LLMs per task** — Extraction and summarization can run on faster/cheaper models (Flash). Triage and scheduling reasoning can use stronger models. Alfred stays on whatever is best for conversational quality.
- **Async execution** — Some subagent tasks (scanning Slack, deep research) take longer. Alfred can kick them off, say "working on it," and deliver results when ready via chat or notification.

---

## Architecture Split

- **ARQ jobs** = data collection, scheduling triggers, notifications
- **Subagents** = reasoning, decision-making, multi-tool coordination
- **Alfred** = chat, simple tools, routing to subagents

```
Scheduled Jobs (ARQ)                    Subagents
─────────────────────                   ────────────

Slack Scanner (every 30min)             Triage Agent
  → Pull recent messages                  → Has tools: check todos,
  → LLM extraction (structured)             check calendar, check notes
  → Store action items in DB              → Produces recommendations
  → Trigger Triage Agent                  → Sends to approval inbox

EOD Summary (daily at 5pm)              Scheduling Agent
  → Aggregate day's data                  → FreeBusy coordination
  → Trigger Summary Agent                 → Slot finding
                                          → Reschedule proposals
Morning Briefing (daily at 8am)?
  → Today's calendar                    Summary Agent
  → Pending items from yesterday          → Reasons about priorities
  → Send via Slack / dashboard            → Produces structured summary

                                        Research Agent
                                          → Multi-step web research
                                          → Deeper than a single search
```

---

## 1. Slack Monitoring & Action Item Extraction

### How does Alfred see messages?

Currently Alfred only sees messages when DM'd or @mentioned. To scan conversations:

**Pull-based (recommended):** Scheduled ARQ job uses `conversations.history` API to fetch recent messages from channels/DMs. Runs on a cadence (e.g., every 30 min or hourly). Batch messages into one LLM call per cycle — more cost-effective than processing every message individually.

**Push-based (alternative):** Subscribe to more Slack events (`message.channels`, `message.im`, `message.groups`). Higher volume, would need filtering and batching before LLM calls.

**New Slack scopes needed:** `channels:history`, `groups:history`, `im:history`, `mpim:history`

### Extraction step

A focused LLM call (not a full agent) that takes a batch of messages and outputs structured data:
- Action items and commitments ("I'll look into X", "I'll send that over")
- Questions to follow up on
- Decisions made
- Things mentioned to track

This is a simple LLM chain with structured output, not a subagent — it doesn't need tools or multi-step reasoning.

---

## 2. Triage & Recommendations (Subagent)

Given extracted items, the Triage Agent reasons about what to do:
- Is this a task? A calendar event? A note? Just informational?
- What's the priority/urgency?
- Is this a duplicate of something already tracked?
- What's the right action to propose?

### Proposal/Inbox Model (not auto-act)

Alfred surfaces recommendations that the user approves, dismisses, or modifies:

> "From your Slack conversations today, I found 3 items:
> 1. You told Sarah you'd review the API spec → **Create todo?**
> 2. Mike asked to reschedule Thursday's standup → **Update calendar?**
> 3. Discussion about migration timeline → **Save as note?**"

This could show up as a Slack DM, a dashboard card/inbox, or both.

---

## 3. End-of-Day Summary

Scheduled ARQ job (e.g., 5pm in user's timezone) that:
- Pulls completed todos, calendar events attended, Slack activity
- Passes aggregated data to Summary Agent
- Summary Agent reasons about priorities and produces structured output:
  - What was accomplished today
  - Carry-over items / unfinished work
  - Tomorrow's calendar preview
  - Recommended priorities for next day
- Delivers via Slack DM and/or dashboard card

### Morning Briefing (optional complement)
- Today's calendar at a glance
- Pending items from yesterday
- Reminders about upcoming deadlines

---

## 4. Delegation Flow Examples

### User-triggered delegation
```
User: "find a time for the eng sync next week that works for everyone"

Alfred (thinks): This needs multi-step scheduling → delegate
Alfred (to user): "Let me check everyone's availability and find some options."
Alfred → Scheduling Agent:
  - Get attendees from existing eng sync event
  - FreeBusy query for all attendees across next week
  - Find overlapping open slots
  - Rank by preferences (morning vs afternoon, duration)
  - Return top 3 options
Alfred (to user): "Here are 3 times that work for everyone: ..."
```

### Background-triggered delegation
```
Scheduled Scanner → extracts 5 action items from Slack
Scanner → Triage Agent:
  - Check each item against existing todos (avoid duplicates)
  - Check calendar for related events
  - Classify: task / calendar update / note / ignore
  - Produce recommendations with confidence levels
Triage Agent → Inbox (dashboard card + optional Slack DM)
```

---

## Subagent Summary

| Subagent | Trigger | What it does |
|---|---|---|
| **Triage Agent** | Scheduled scanner output | Classifies action items, proposes todos/events/notes |
| **Scheduling Agent** | User request via Alfred | FreeBusy coordination, slot finding, reschedule proposals |
| **Summary Agent** | Scheduled (EOD) or user request | Aggregates day's activity, identifies carry-over items |
| **Research Agent** | User request via Alfred | Multi-step web research, deeper than a single search |

---

## New Infrastructure Needed

- **Action items table** — extracted commitments/items with status, source (Slack message link), proposed action
- **Recommendations/inbox table** — proposals from triage agent with accept/dismiss/modify actions
- **Slack API scopes** — `channels:history`, `groups:history`, `im:history`, `mpim:history` for pull-based scanning
- **New ARQ scheduled jobs** — scanner cron, EOD summary cron, optional morning briefing cron
- **Dashboard card or page** — inbox/recommendations UI with approve/dismiss actions
- **User preferences** — which channels to scan, EOD summary time, morning briefing on/off, auto-act vs propose
