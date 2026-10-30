# Phase 2: Google (Gmail, Calendar, Drive / Docs)

Status: **working, read-only** (2026-10-30). `mcp/google_tools.py` (tools) and `mcp/google_api.py`
(client, errors) read Calendar, Gmail and Drive with google-api-python-client.
`calendar_add_assignment` (`mcp/academic_tools.py`) writes LEARN due dates to the app's own
"STARK – Assignments" calendar.

## What Jarvis gets

| Tool | Does |
|---|---|
| `calendar_today` | today's events on every calendar in your list (not hidden ones), local time; declined and cancelled events left out |
| `calendar_next` | the next timed event within 30 days, plus anything on right now |
| `email_unread_summary` | unread inbox count, then sender, subject, when and Gmail's snippet for the newest |
| `email_search` | Gmail search syntax; the same fields |
| `docs_search` | Drive files by name or content: name, kind, modified, owner, link (contents are never read) |

Email bodies and document contents are never fetched. Every result written by other people is
fenced as untrusted content.

### When something's wrong, Jarvis says what

| Google says | Jarvis says (details in the log) |
|---|---|
| API not enabled in the Cloud project | "The Gmail API isn't turned on in your Google Cloud project, sir." The enable link is logged |
| A permission box was left unticked | "I don't have permission for Google Drive, sir. Reconnect Google and tick the Drive box." `jarvis connect google` also lists unticked boxes right after sign-in, and Settings shows "Missing …" |
| Refresh token revoked or expired (Testing mode: 7 days) | "Your Google sign-in has expired, sir. Reconnect it in Settings, under Jarvis." |
| No network | "I can't reach Google right now, sir." |

Scopes (all read-only):

- `https://www.googleapis.com/auth/gmail.readonly`
- `https://www.googleapis.com/auth/calendar.readonly`
- `https://www.googleapis.com/auth/drive.readonly`
- only if Settings → JARVIS → Assignments calendar is GOOGLE:
  `https://www.googleapis.com/auth/calendar.app.created`. This one can only touch
  calendars Jarvis itself creates ("STARK – Assignments"), never your main calendar.
- `https://www.googleapis.com/auth/spreadsheets`, for the SE tracker sheet (docs/jarvis-app.md,
  stage 1). Google has no scope for one existing sheet, so Jarvis enforces it: the Sheets client
  refuses any request that names a spreadsheet other than the one `jarvis tracker find` stored.

## Setup (free, about 10 minutes)

1. **Project.** Go to <https://console.cloud.google.com/>, sign in with the account
   Jarvis should read, and create a project (e.g. `stark-jarvis`). No billing needed.
2. **APIs.** APIs & Services → Library: enable **Gmail API**, **Google Calendar API**,
   **Google Drive API** and **Google Sheets API**.
3. **Consent screen.** Google Auth Platform (APIs & Services → OAuth consent screen):
   - User type **External**, app name `Jarvis`, your email as support + developer contact.
   - Data access / Scopes: add the five scopes above.
   - Audience: leave it in **Testing** and add yourself as a **test user**.
     (Testing is fine for a personal app. Its refresh tokens expire after 7 days,
     so you'd rerun `jarvis connect google` weekly. Publishing the app to
     "In production" without verification avoids that; Google shows an
     "unverified app" warning you click through once.)
4. **OAuth client.** Clients → Create client → **Desktop app**, name `Jarvis`.
   Download the JSON (`client_secret_….json`).
5. **Libraries** (once):

   ```sh
   uv pip install --python ~/.config/jarvis/.venv/bin/python google-auth-oauthlib google-api-python-client
   ```

6. **Connect.** Run this, or press CONNECT next to Google in Settings → JARVIS → INTEGRATIONS:

   ```sh
   jarvis connect google ~/Downloads/client_secret_….json
   ```

   The client JSON goes into the system keyring (delete the download afterwards). Your
   browser opens Google's consent page. The redirect lands on a one-off
   `127.0.0.1:<random port>` listener that exists only until you finish signing in.
   That's Google's required flow for desktop apps, since the copy-paste code flow was
   retired. The token goes to the keyring as `jarvis:google` / `token`, the entry is
   set to `enabled: true`, and Jarvis restarts to load it.

Undo: `jarvis disconnect google` (wipes the keyring entries, disables the entry), and
revoke at <https://myaccount.google.com/permissions>.

## Safety rules (already enforced)

- **Read-only.** `read_only: true`. Jarvis's gate (`core/brain.py`) refuses any tool
  that isn't in `read_tools`, so nothing can be sent, created, deleted or edited.
  If an entry is ever made writable, every write needs your spoken yes, shown on
  the HUD as well.
- **Content is data.** Mail, events and documents come back fenced in
  `<<UNTRUSTED-nonce>> … <<END-UNTRUSTED-nonce>>` (`mcp/integration_common.untrusted`), and
  the system prompt says to never follow them. The gate also doesn't rely on the
  model obeying that: once any integration tool has run in a request, every later
  tool call, desktop ones included, needs your spoken yes, and the question says
  it came up while reading your mail.
- **Always Claude.** Email, calendar, docs, assignment and grade requests never hit
  the local fast path (`fastpath.INTEGRATION_INTENT`).
- **Secrets** live only in the keyring, never in the repo.

## Later: Microsoft 365 (UWaterloo)

UWaterloo mail and calendar live in Microsoft 365. Scaffolded alongside this one, see
[phase2-microsoft.md](phase2-microsoft.md). The university may require **admin
consent** for third-party apps, in which case Jarvis falls back to the LEARN iCal
feed and to grade notices in Gmail.
