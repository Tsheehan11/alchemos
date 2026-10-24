"""
Fast path: common commands matched locally, no AI, answered in well under 300 ms.

match(text, last_query) → list of steps, or None to hand the request to Claude.
A step is {"tool", "args", "say"}; tools are the same stark_actions the MCP
server exposes, so validation and confirmation rules are shared. "set the theme
to matrix and dim the lights" splits on "and"/"then" and runs locally if every
part matches. Anything that falls through is logged (tier claude) for new rules:
`jarvis --misses`.
"""
import re
from datetime import datetime

import stark_actions as A

FILLER = re.compile(r"^(?:(?:hey |ok |okay )?jarvis\s*|can you |could you |would you |will you |please |"
                    r"i want you to |i'd like you to |go ahead and |just )+")
TRAILER = re.compile(r"(?:\s+(?:please|for me|now|thanks|thank you|jarvis))+$")

UNITS = {"zero": 0, "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
         "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
         "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19}
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
NUM = r"(\d+(?:\.\d+)?|(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?: \w+)?|\w+)"


def norm(s):
    s = s.lower().replace("-", " ")
    s = re.sub(r"[^\w\s'%.]", " ", s)
    s = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", s)   # keep decimals, drop sentence dots
    return re.sub(r"\s+", " ", s).strip()


def to_num(w):
    w = w.strip()
    try:
        return float(w)
    except ValueError:
        pass
    parts = w.split()
    if len(parts) == 1:
        return UNITS.get(w, TENS.get(w))
    if len(parts) == 2 and parts[0] in TENS and parts[1] in UNITS:
        return TENS[parts[0]] + UNITS[parts[1]]
    return None


def duration_minutes(s):
    """'5 minutes', 'an hour and a half', '90 seconds', '1 hour 30 minutes' → minutes, else None."""
    s = s.replace("half an hour", "30 minutes").replace("a half hour", "30 minutes")
    s = s.replace("a quarter of an hour", "15 minutes")
    total, found = 0.0, False
    for num, unit in re.findall(rf"{NUM} (second|sec|minute|min|hour|hr)s?\b", s):
        n = to_num(num)
        if n is None:
            return None
        total += n * {"second": 1 / 60, "sec": 1 / 60, "minute": 1, "min": 1, "hour": 60, "hr": 60}[unit]
        found = True
    if found and re.search(r"(hour|hr)s? and a half", s):
        total += 30
    left = re.sub(rf"{NUM} (second|sec|minute|min|hour|hr)s?\b|and a half|and|\s", "", s)
    return total if found and not left else None


def step(tool, say, **args):
    return {"tool": tool, "args": args, "say": say}


def _now_playing(r):
    if not r.get("title"):
        return "Nothing's playing, sir."
    who = f" by {r['artist']}" if r.get("artist") else ""
    return f"{r['title']}{who}{'' if r.get('playing') else ', paused'}."


def _vpn_status(r):
    if not r.get("active"):
        return "The VPN is off, sir."
    where = f", {r['country']}" if r.get("country") else ""
    return f"{r['active'].title()} is {r['state']}{where}."


SCREEN = r"(?: (?:the|my))?(?: screen| computer| pc| laptop| system)?"
LIGHTS = r"(?:the |my )?(?:lights?|strip|led strip|leds)"


def _clause(t, last_query):
    t = TRAILER.sub("", FILLER.sub("", t)).strip()
    if not t:
        return None
    m = None

    def M(p):
        nonlocal m
        m = re.fullmatch(p, t)
        return m

    # ── chit-chat / dismiss ──
    if M(r"(?:never ?mind|cancel|nothing|forget it|stop|no thanks|that's all|that is all)"):
        return [step(None, "Very good, sir.")]
    if M(r"(?:thanks|thank you|cheers)"):
        return [step(None, "You're welcome, sir.")]
    # ── time ──
    if M(r"what(?:'s| is) the time|what time is it|time"):
        return [step(None, datetime.now().strftime("It's %-I:%M, sir."))]
    if M(r"what(?:'s| is) (?:the |today's )?(?:date|day)(?: today)?|what day is it(?: today)?"):
        return [step(None, datetime.now().strftime("It's %A, the %-d of %B."))]
    # ── media ──
    if M(r"(?:pause|stop)(?: the)?(?: music| song| playback| spotify| track)?"):
        return [step("media", "Paused.", action="pause")] if t != "stop" else None
    if M(r"(?:play|resume|unpause|continue)(?: the)?(?: music| song| spotify| playback)?"):
        return [step("media", "Resuming.", action="play")]
    if M(r"(?:next|skip)(?: this)?(?: song| track)?|(?:play )?(?:the )?next (?:song|track)"):
        return [step("media", "Next track.", action="next")]
    if M(r"(?:previous|go back|last)(?: song| track)?|(?:play )?(?:the )?(?:previous|last) (?:song|track)"):
        return [step("media", "Previous track.", action="previous")]
    if M(r"(?:turn (?:it|the volume|the music|the sound) up|volume up|louder|turn up the (?:volume|music))"):
        return [step("media", "Louder.", action="volume_up")]
    if M(r"(?:turn (?:it|the volume|the music|the sound) down|volume down|quieter|turn down the (?:volume|music))"):
        return [step("media", "Quieter.", action="volume_down")]
    if M(rf"(?:set |turn )?(?:the )?volume (?:to |at )?{NUM}(?: ?%| percent)?"):
        n = to_num(m.group(1))
        return [step("media", f"Volume {n:g}.", action="set_volume", value=n)] if n is not None else None
    if M(r"mute(?: the)?(?: sound| audio| volume| music)?"):
        return [step("media", "Muted.", action="mute")]
    if M(r"unmute(?: the)?(?: sound| audio| volume| music)?"):
        return [step("media", "Unmuted.", action="unmute")]
    if M(r"what(?:'s| is) (?:playing|this song|the song|this track|this)|what song is (?:this|playing)"):
        return [step("what_is_playing", _now_playing)]
    # ── lock / power / windows ──
    if M(rf"lock{SCREEN}|lock (?:it|up)"):
        return [step("lock_screen", "Locking.")]
    if M(rf"(?:suspend|go to sleep|sleep){SCREEN}|put{SCREEN} to sleep"):
        return [step("power", "Goodnight, sir.", action="suspend")]
    if M(rf"(?:shut ?down|power off|turn off){SCREEN}") and (t.startswith("shut") or "computer" in t or "pc" in t or "laptop" in t or "system" in t):
        return [step("power", "Shutting down.", action="shutdown")]
    if M(rf"(?:restart|reboot){SCREEN}"):
        return [step("power", "Restarting.", action="reboot")]
    if M(r"(?:log|sign) ?(?:me )?out"):
        return [step("power", "Logging out.", action="logout")]
    if M(r"close (?:this |the |that )?(?:window|app)"):
        return [step("close_focused_window", "Closed.")]
    # ── workspaces ──
    if M(rf"(?:go to |switch to |show |open )?(?:workspace|desktop) (?:number )?{NUM}"):
        n = to_num(m.group(1))
        return [step("switch_workspace", f"Workspace {n:g}.", n=n)] if n is not None else None
    if M(rf"(?:move|send|put) (?:this |the |that )?(?:window |app )?to (?:workspace|desktop) (?:number )?{NUM}"):
        n = to_num(m.group(1))
        return [step("move_window_to_workspace", f"Moved to {n:g}.", n=n)] if n is not None else None
    # ── lights ──
    if M(rf"(?:turn |switch )?{LIGHTS} off|(?:turn|switch) off {LIGHTS}|kill {LIGHTS}"):
        return [step("lights", "Lights off.", action="off")]
    if M(rf"(?:turn |switch )?{LIGHTS} on|(?:turn|switch) on {LIGHTS}"):
        return [step("lights", "Lights on.", action="on")]
    if M(rf"dim {LIGHTS}|{LIGHTS} dim|dim {LIGHTS} down"):
        return [step("lights", "Dimmed.", action="brightness", value="30")]
    if M(rf"(?:brighten|raise) {LIGHTS}|{LIGHTS} (?:to )?(?:full|max(?:imum)?)(?: brightness)?|full brightness"):
        return [step("lights", "Full brightness.", action="brightness", value="100")]
    if M(rf"(?:set |turn )?{LIGHTS} (?:brightness )?(?:to )?{NUM}(?: ?%| percent)"):
        n = to_num(m.group(1))
        return [step("lights", f"Lights at {n:g} percent.", action="brightness", value=f"{n:g}")] if n is not None else None
    if M(rf"(?:set |switch |put )?{LIGHTS} (?:to |on )?(music|theme|auto)(?: mode)?|(music|theme|auto) mode (?:for |on )?{LIGHTS}"):
        mode = m.group(1) or m.group(2)
        return [step("lights", f"Lights on {mode}.", action="mode", value=mode)]
    # ── VPN ──
    if M(r"(?:turn on|connect|enable|start|switch on)(?: to)?(?: the)?(?: proton)? ?vpn|vpn on|connect(?: to)? proton"):
        return [step("vpn", "Connecting Proton.", action="connect_proton")]
    if M(r"(?:turn off|disconnect|disable|stop|switch off)(?: from)?(?: the)?(?: proton| school)? ?vpn|vpn off|disconnect(?: from)? proton"):
        return [step("vpn", "Disconnecting the VPN.", action="disconnect")]
    if M(r"(?:connect|open|turn on|start)(?: to)?(?: the)? (?:school|uni|university|waterloo|uw) vpn(?: login)?"):
        return [step("vpn", "The login window is up, sir.", action="open_school_login")]
    if M(r"vpn status|is (?:the )?vpn (?:on|connected|up)|am i (?:on|connected to) (?:the )?vpn"):
        return [step("vpn", _vpn_status, action="status")]
    # ── theme ──
    if M(r"(?:set|change|switch|make)(?: the)? (?:theme|colou?rs?|hud) to (.+?)(?: theme)?|(?:switch to |use |activate )?(.+?) theme|theme (.+)"):
        name = A.match_preset(next(g for g in m.groups() if g))
        pretty = " ".join(w if re.fullmatch(r"[IVX]+", w) else w.title() for w in name.split()) if name else ""
        return [step("set_theme", f"{pretty}, sir.", preset=name)] if name else None
    # ── timers ──
    if M(r"(?:set |start )?(?:a |an )?(?:timer|countdown)(?: for)? (.+?)(?: timer)?|(?:set |start )?(?:a |an )?(.+?) timer"):
        mins = duration_minutes(m.group(1) or m.group(2))
        return [step("set_timer", f"Timer set for {_spoken_minutes(mins)}.", minutes=round(mins, 2))] if mins else None
    if M(r"remind me in (.+?) to (.+)"):
        mins = duration_minutes(m.group(1))
        return [step("set_timer", f"I'll remind you in {_spoken_minutes(mins)}.", minutes=round(mins, 2),
                     label=m.group(2))] if mins else None
    # ── browser (only when explicitly asked) ──
    if M(r"(?:open|ask|put|show|send) (?:it|that|this)(?: question)? in (?:the )?browser"):
        return [step("open_in_browser", "Opened in the browser.", query=last_query or "")]
    if M(r"(?:ask claude|search|look up) in (?:the )?browser (?:for |about )?(.+)|open (.+) in (?:the )?browser"):
        return [step("open_in_browser", "Opened in the browser.", query=m.group(1) or m.group(2))]
    # ── apps ──
    if M(r"(?:open|launch|start|run|bring up|pull up|fire up|load)(?: up)?(?: the| my)? (.+?)(?: app| application)?"):
        target = m.group(1)
        if re.search(r"\b(?:uw ?cs|cs servers?|school servers?|student servers?)\b", target):
            return [step("open_uwcs", "Opening VS Code on the CS servers.")]
        cmd, name = A.find_app(target)
        return [step("open_app", f"Opening {name.title()}.", name=target)] if cmd else None
    if len(t.split()) <= 2:   # a bare app name, exact matches only
        if t in A.ALIASES or t in A.apps():
            return [step("open_app", f"Opening {t.title()}.", name=t)]
    return None


def _spoken_minutes(m):
    if m < 1:
        return f"{round(m * 60)} seconds"
    if m >= 60 and m % 60 == 0:
        h = int(m // 60)
        return f"{h} hour{'s' if h > 1 else ''}"
    if m >= 60:
        return f"{int(m // 60)} hour{'s' if m >= 120 else ''} {round(m % 60)} minutes"
    return f"{m:g} minute{'s' if m != 1 else ''}"


def match(text, last_query=""):
    t = norm(text)
    if not t:
        return None
    whole = _clause(t, last_query)
    if whole:
        return whole
    parts = [p for p in re.split(r"\s*(?:,|\band then\b|\bthen\b|\band\b|\balso\b)\s*", t) if p.strip()]
    if len(parts) < 2:
        return None
    steps = []
    for p in parts:
        s = _clause(p, last_query)
        if not s or s[0]["tool"] is None:
            return None
        steps += s
    return steps
