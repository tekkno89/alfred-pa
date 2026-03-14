# Calendar Advanced Features - Brainstorm

Status: Brainstorming (not planned for implementation yet)

## Questions to Answer

1. What do we need so the Alfred calendar tool can check co-workers' schedules (not just my own)?
2. How can Alfred make event reschedule proposals — find times that work for all attendees and suggest them?
3. How do we get members of an org so the UI can show a people picker (e.g., when adding participants to an event, show all people at my company)?

## 1. Check Co-workers' Schedules

### Option A: Google FreeBusy API (recommended)
- [FreeBusy API](https://developers.google.com/calendar/api/v3/reference/freebusy/query) lets you query busy/free blocks for any email address — no extra OAuth from the co-worker needed.
- Pass a list of emails + time range → get back busy time blocks (no event titles/details, just "busy from X to Y").
- Works as long as co-worker hasn't restricted free/busy visibility (most orgs leave it open by default).
- Current scope (`https://www.googleapis.com/auth/calendar`) already covers this — no scope change needed.
- Agent tool would get a new action like `check_availability` taking a list of emails and a time range.

### Option B: Shared/delegated calendar access
- To see event *details* (titles, descriptions, attendees), the co-worker must explicitly share their calendar with you in Google Calendar.
- Once shared, those calendars show up in your `calendarList` API response — Alfred sees them automatically.
- This is a Google Calendar permissions thing, not something Alfred needs to implement.

**Recommendation:** Option A (FreeBusy) is the practical choice. Answers "when is Tyler free?" without requiring anything from the co-worker.

---

## 2. Event Reschedule Proposals

This is more of an agent workflow than a single API call.

### What "propose a reschedule" means in practice
- Find a new time that works for all (or key) attendees
- Send the proposal (email, Slack, calendar invite with a note)

### Implementation pieces

1. **Find alternative times** — Use FreeBusy API to check all attendees' availability, then compute open slots that work for everyone. Scheduling algorithm on top of FreeBusy results.

2. **How to actually propose** — Options:
   - **Update the event with a new time + note** — Google sends update notifications to all attendees automatically. This is "just reschedule it" rather than "propose."
   - **Send a message via Slack/chat** — Alfred DMs you saying "I found these 3 alternative times, which one works?" then updates the event after you pick.
   - **Create a tentative/placeholder event** — New event marked as "proposed" while keeping the old one, let attendees accept/decline.
   - **Google Calendar's "Propose a new time"** — Exists in Google Calendar UI but is **not exposed in the API**. No endpoint for it.

3. **Most practical approach:**
   - Look at who's on the event (attendees list — already stored)
   - Query FreeBusy for all attendees in a given range
   - Run a slot-finding algorithm to suggest open windows
   - Present options in chat
   - Once user picks one, update the event (Google auto-notifies attendees)

This is mostly agent logic + FreeBusy, no new Google APIs beyond that.

---

## 3. Org Member Directory / Participant Picker

Currently Alfred has no concept of organizations or teams.

### Where do org members come from?

**Option A: Google Workspace Directory API**
- [Directory API](https://developers.google.com/admin-sdk/directory/v1/guides/manage-users) lists all users in a Google Workspace domain.
- Requires `https://www.googleapis.com/auth/admin.directory.user.readonly` scope, and the authenticated user must be an admin (or domain must have delegated access).
- Full employee list with names and emails.

**Option B: Google People API / Contacts**
- [People API](https://developers.google.com/people/api/rest) lists your contacts and "other contacts" (people you've emailed).
- Scope: `contacts.readonly` or `contacts.other.readonly`
- Wouldn't give full org, but gives everyone you've interacted with — often good enough.

**Option C: Manual / imported team list**
- Alfred's own "contacts" or "team" model where you manually add people (name + email).
- Simpler but requires manual maintenance.

**Option D: People API `listDirectoryPeople` (recommended)**
- [listDirectoryPeople](https://developers.google.com/people/api/rest/v1/people/listDirectoryPeople) lists people in the Google Workspace directory.
- Scope: `https://www.googleapis.com/auth/directory.readonly`
- **Doesn't require admin access** — any user in the org can call it.
- Returns name, email, photo, job title, department.
- Sweet spot: full org directory without needing admin privileges.

### Frontend changes for the picker
- Replace comma-separated email text input in `EventCreateDialog` with autocomplete/typeahead component.
- Fetch directory (cached), filter as user types, show name + email + avatar.
- Allow selecting multiple people, show as chips/tags.

---

## Summary

| Feature | Google API | New Scope Needed? | Complexity |
|---|---|---|---|
| Check co-worker availability | FreeBusy API | No (covered by `calendar` scope) | Low |
| Find reschedule slots | FreeBusy + slot algorithm | No | Medium |
| Propose reschedule | Agent workflow + event update | No | Medium |
| Org member directory | People API `listDirectoryPeople` | Yes (`directory.readonly`) | Medium |
| Participant picker UI | Frontend autocomplete component | N/A | Medium |

FreeBusy is the easiest win — unlocks both availability checking and reschedule proposals. Org directory is a separate OAuth scope + new service + frontend component, but `listDirectoryPeople` avoids the admin-access problem.
