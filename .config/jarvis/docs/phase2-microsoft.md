# Phase 2: Microsoft 365 (UWaterloo Outlook mail and calendar)

Status: **scaffolding**. Registered in `servers.json` as `"microsoft"` (`enabled: false`,
`read_only: true`). The MCP server is `mcp/microsoft_tools.py` (stubs that say "not
connected"), and the sign-in is `jarvis connect microsoft` (MSAL device code flow).

Scopes: `Mail.Read`, `Calendars.ReadWrite`, `offline_access`, `User.Read`.
`Calendars.ReadWrite` is only there so the academic sync can write to the dedicated
**STARK – Assignments** calendar when Settings → JARVIS → Assignments calendar is OUTLOOK.
No tool can send or delete mail, and the integration is read-only to the model.

## Register the app (Entra ID)

1. <https://entra.microsoft.com/> → sign in with your **@uwaterloo.ca** account →
   Applications → **App registrations** → New registration.
   - Name `Jarvis`. Supported accounts: **this organizational directory only**
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
   uv pip install --python ~/.config/jarvis/.venv/bin/python msal
   ```

6. Connect, or press CONNECT next to Microsoft 365 in Settings → JARVIS:

   ```sh
   jarvis connect microsoft <client-id> [<tenant-id or "organizations">]
   ```

   It prints a code. Open <https://microsoft.com/devicelogin> on any device, enter
   the code, sign in with UWaterloo and Duo. No local listener is involved. The client ID,
   tenant and MSAL token cache go to the keyring (`jarvis:microsoft`).

## If UWaterloo blocks consent

Many university tenants only allow users to consent to apps an admin has approved.
Sign-in then fails with *"Need admin approval"* (AADSTS90094 / 90095 / 65001).
`jarvis connect microsoft` recognizes those errors, records it (`jarvis:microsoft` /
`blocked`), and Settings shows **"UWaterloo needs admin consent · using the LEARN
feed instead"**. The Outlook tools then answer *"The university needs an
administrator to approve it, so I'm using the LEARN calendar feed for assignments
instead."* Nothing else breaks.

You can ask IST for approval: open a request from the "Need admin approval" page,
naming the app and the four delegated scopes. Meanwhile these fallbacks need no consent:

1. **LEARN (D2L) iCal feed.** LEARN → Calendar → *Subscribe* → copy the private feed URL, then
   `jarvis connect learn-ical '<url>'` (or CONNECT next to LEARN; it asks with hidden
   input). The URL is stored in the keyring (`jarvis:learn` / `ical_url`; it's a
   secret, since anyone with it can read your calendar). Connect fetches it once,
   deduplicates the assignments and saves them in `~/.local/share/jarvis/academic.json`.
2. **Grade notices from email.** Turn on LEARN's "grade released / feedback available"
   email notifications (LEARN → your name → Notifications); Crowdmark sends its own.
   Jarvis recognizes those in whichever inbox is connected: Gmail directly, or forward
   UWaterloo mail to Gmail (Outlook on the web → Settings → Mail → Forwarding).

## Academic sync (`mcp/academic.py`, `mcp/academic_tools.py`)

Stubbed until a calendar account is connected. The pure logic is implemented and
tested (`tests/test_integrations.py`).

- **Assignments** from the feed are deduplicated by course + title ("Assignment 5" =
  "A5"; a re-sync updates the due date).
- They are written as events to a dedicated **STARK – Assignments** calendar in the account
  chosen in Settings (Google or Outlook), **never the main calendar**. The tool has no
  calendar argument, so not even the model can aim it elsewhere. Each event has the
  course, due time, the LEARN link, and a reminder 2 days before.
- **Grade notices.** A notice counts only if the sender is LEARN/UWaterloo or Crowdmark
  (and DKIM didn't fail), its subject says a grade or feedback was released, and it
  names an assignment already known from the feed. Only the sender and subject are
  read, never the body. The effect is limited to marking that one event graded
  (title prefix **✓**) and queueing *"Sir, your CS 137 A5 has been graded"*, which the
  voice loop says when you're docked (`VoiceLoop.check_academic`).
- The ✓ edit is a calendar write like any other, so it follows the next rule.
- **Writes stay behind confirmation** ("Add CS 137 A5 to your STARK assignments calendar,
  sir?"). Settings → JARVIS → **AUTO-ADD ASSIGNMENTS** lets the sync write to that one
  calendar without asking. Even then, a write Claude proposes right after reading
  email still asks.

Tools: `assignments_upcoming`, `grades_new`, `calendar_add_assignment` (the only write).

## Same safety rules as Google

Read-only by default. Email content is untrusted data (fenced, and it taints the request
so nothing acts without your spoken yes). There's no tool to send or delete mail. These
requests always go to Claude, never the local fast path. Tokens live only in the keyring.
See [phase2-google.md](phase2-google.md#safety-rules-already-enforced).
