# Phase 2: UWaterloo Outlook (mail + calendar)

UWaterloo blocks the Microsoft Graph app route (user consent needs an admin), so Outlook comes in
through two workarounds that need no consent. This is the route in use:

| What | How | Where in Orrin |
|---|---|---|
| Calendar | Outlook on the web → Settings → Calendar → Shared calendars → **Publish** → copy the **ICS** link, then `orrin connect outlook-ical` (it prompts with hidden input; never pass the link as an argument, since it would land in shell history) | `mcp/outlook_ical.py`, merged with Google in `calendar_today` / `calendar_next` (`mcp/calendars.py`) |
| Mail | Outlook on the web → Settings → Mail → **Forwarding** → your connected Gmail | read by the Google tools (`email_*`), and by the grade-notice scan |

The calendar link is a secret (anyone with it can read the calendar): it lives in the keyring
(`orrin:outlook` / `ical_url`). The feed is cached in `~/.local/share/orrin/outlook.ics`
(mode 600), refreshed every ~15 min while docked and on demand when older than that. Recurring
classes, moved or cancelled instances and Outlook's Windows time-zone names are handled by
`icalendar` + `recurring-ical-events`.

- **Merging:** Google and Outlook events are combined in Toronto time. An event in both (same iCal
  UID, or same title, start and end) is said once. Orrin names the calendar only if you ask.
- **Settings → ORRIN → INTEGRATIONS:** Outlook shows **CONNECTED · calendar link + mail
  forwarding**. If the link stops working it says "link not updating", and calendar answers say
  Outlook may be out of date.
- **Undo:** `orrin disconnect outlook-ical`, then unpublish the calendar in Outlook to kill the link.

## Optional: direct Microsoft Graph connection (needs admin consent)

Listed in Settings as **Microsoft 365 (direct) · OPTIONAL**, not as broken. Everything above works
without it. Set it up only if IST approves the app. The original notes follow.

## Register the app (Entra ID)

1. <https://entra.microsoft.com/> → sign in with your **@uwaterloo.ca** account →
   Applications → **App registrations** → New registration.
   - Name `Orrin`. Supported accounts: **this organizational directory only**
     (UWaterloo), or "any organizational directory".
   - Redirect URI: none needed for device code.
   - If App registrations is greyed out or refused, UWaterloo blocks students from
     registering apps. Register it in your own free Entra tenant instead (e.g. the one
     that comes with a personal Azure account) as **multitenant**. You still sign in
     with UWaterloo, which leads to the consent question below.
2. Copy the **Application (client) ID**. Also copy the Directory (tenant) ID if you
   registered it inside UWaterloo's tenant.
3. **API permissions** → Add → Microsoft Graph → **Delegated**: `Mail.Read`,
   `Calendars.ReadWrite`, `offline_access`, `User.Read`. Don't click "Grant admin consent"
   (you can't, and it isn't needed if user consent is allowed).
4. **Authentication** → Advanced settings → **Allow public client flows: Yes**.
   Device code needs this. No client secret, since a public client can't keep one.
5. Libraries (once):

   ```sh
   uv pip install --python ~/.config/orrin/.venv/bin/python msal
   ```

6. Connect, or press CONNECT next to Microsoft 365 in Settings → ORRIN:

   ```sh
   orrin connect microsoft <client-id> [<tenant-id or "organizations">]
   ```

   It prints a code. Open <https://microsoft.com/devicelogin> on any device, enter
   the code, sign in with UWaterloo and Duo. No local listener is involved. The client ID,
   tenant and MSAL token cache go to the keyring (`orrin:microsoft`).

## If UWaterloo blocks consent

Many university tenants only allow users to consent to apps an admin has approved.
Sign-in then fails with *"Need admin approval"* (AADSTS90094 / 90095 / 65001).
`orrin connect microsoft` recognizes those errors, records it (`orrin:microsoft` /
`blocked`), and Settings shows **"UWaterloo needs admin consent · using the LEARN
feed instead"**. The Outlook tools then answer *"The university needs an
administrator to approve it, so I'm using the LEARN calendar feed for assignments
instead."* Nothing else breaks.

You can ask IST for approval: open a request from the "Need admin approval" page,
naming the app and the four delegated scopes. Meanwhile these fallbacks need no consent:

1. **LEARN (D2L) iCal feed.** LEARN → Calendar → *Subscribe* → copy the private feed URL, then
   `orrin connect learn-ical '<url>'` (or CONNECT next to LEARN; it asks with hidden
   input). The URL is stored in the keyring (`orrin:learn` / `ical_url`; it's a
   secret, since anyone with it can read your calendar). Connect fetches it once,
   deduplicates the assignments and saves them in `~/.local/share/orrin/academic.json`.
2. **Grade notices from email.** Turn on LEARN's "grade released / feedback available"
   email notifications (LEARN → your name → Notifications); Crowdmark sends its own.
   Orrin recognizes those in whichever inbox is connected: Gmail directly, or forward
   UWaterloo mail to Gmail (Outlook on the web → Settings → Mail → Forwarding).

## Academic sync (`mcp/academic_sync.py`, `mcp/academic_tools.py`, `mcp/academic.py`)

Runs every ~15 min while docked (the voice loop), plus on demand from the tools.

- **Assignments:** the LEARN feed is deduplicated by course + title ("Assignment 5" = "A5"; a
  re-sync updates the due date). `assignments_upcoming` answers "what's due this week?",
  soonest first, and adds recent course emails that mention a due date as hints (subject and
  sender only).
- **Calendar (`STARK – Assignments`):** with **AUTO-ADD ASSIGNMENTS** on, new and changed
  upcoming assignments are written to that calendar only, with course, due time, LEARN link and a
  reminder two days before. With it off, nothing is written automatically;
  `calendar_add_assignment` (after your spoken yes) adds one. On Google the calendar is created
  with `calendar.app.created`, which can't reach any other calendar. Writing to an Outlook
  calendar isn't possible without Graph.
- **Grades:** `grades_new` and the sync scan Gmail for LEARN / Crowdmark "grade released /
  feedback available" notices, including ones forwarded from your UW address. The original sender
  is taken from From / Sender / Reply-To / X-Original-* / Resent-From / an SRS-rewritten
  Return-Path, or, for an "FW:" from your UW address, from the "From: …" line Gmail's snippet
  starts with.
  - Only LEARN / D2L no-reply addresses and Crowdmark count; a person's `@uwaterloo.ca` doesn't.
  - DKIM must not have failed (ARC counts).
  - The subject must say a grade or feedback was released, and name an assignment that is in the feed.
  - Headers and snippet only; bodies are never fetched.
- **When a grade is found:** the event gets the **✓** prefix (with AUTO-ADD, or when you add it),
  and **"Sir, your CS 137 A5 has been graded"** is announced once per assignment, when you're
  docked and not in combat mode. Only notices from the last two days are announced; the first
  scan ever records what's already in the inbox without a word.

## Same safety rules as Google

Read-only by default. Email content is untrusted data (fenced, and it taints the request
so nothing acts without your spoken yes). There's no tool to send or delete mail. These
requests always go to Claude, never the local fast path. Tokens live only in the keyring.
See [phase2-google.md](phase2-google.md#safety-rules-already-enforced).
