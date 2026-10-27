# Phase 2: Google (Gmail, Calendar, Drive / Docs)

Status: **scaffolding**. The integration is registered in `servers.json` (`"google"`,
`enabled: false`, `read_only: true`), its MCP server (`mcp/google_tools.py`) answers
every tool with a spoken "not connected" line, and `jarvis connect google` runs the
sign-in. Reading real mail and events is the next step.

## What Jarvis gets

| Tool | Does |
|---|---|
| `calendar_today` | today's events |
| `calendar_next` | the next event |
| `email_unread_summary` | unread mail: sender, subject, snippet |
| `email_search` | Gmail search syntax |
| `docs_search` | Drive / Docs by name and content |

Scopes (all read-only):

- `https://www.googleapis.com/auth/gmail.readonly`
- `https://www.googleapis.com/auth/calendar.readonly`
- `https://www.googleapis.com/auth/drive.readonly`
- only if Settings → JARVIS → Assignments calendar is GOOGLE:
  `https://www.googleapis.com/auth/calendar.app.created`. This one can only touch
  calendars Jarvis itself creates ("STARK – Assignments"), never your main calendar.

## Setup (free, about 10 minutes)

1. **Project.** Go to <https://console.cloud.google.com/>, sign in with the account
   Jarvis should read, and create a project (e.g. `stark-jarvis`). No billing needed.
2. **APIs.** APIs & Services → Library: enable **Gmail API**, **Google Calendar API**
   and **Google Drive API**.
3. **Consent screen.** Google Auth Platform (APIs & Services → OAuth consent screen):
   - User type **External**, app name `Jarvis`, your email as support + developer contact.
   - Data access / Scopes: add the four scopes above.
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
