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

# Lead-ins people say (and whisper keeps): "uh, can you please dim the lights"
FILLER = re.compile(r"^(?:(?:hey |ok |okay )?jarvis\s*|(?:uh+|um+|er+m?|hmm+|so|okay|ok|alright|right|well|"
                    r"actually|now|hey|yeah|yes) |can you |could you |would you |will you |would you mind |"
                    r"please |i want you to |i'd like you to |i need you to |go ahead and |just |let's )+")
TRAILER = re.compile(r"(?:\s+(?:please|for me|now|thanks|thank you|jarvis|sir|right now|real quick))+$")
# whisper's usual mishearings of words the rules depend on
SOUNDALIKE = [(r"\b(?:v|b)(?:p|v|b)(?:n|m)\b", "vpn"), (r"\bproton ?(?:vpn)?\b", "proton vpn"),
              (r"\bwork ?space\b", "workspace"), (r"\btemp\b", "temperature"),
              (r"\bspot ?a? ?fy\b", "spotify"), (r"\bcl[ao]u?(?:de|d|ged|wed|w)\b(?= usage)", "claude")]

UNITS = {"zero": 0, "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
         "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
         "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19}
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
NUM = r"(\d+(?:\.\d+)?|(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?: \w+)?|\w+)"
# a lone number word whisper writes as its homophone ("workspace too", "desktop for")
HOMOPHONES = {"to": 2, "too": 2, "for": 4, "fore": 4, "won": 1, "tree": 3, "free": 3, "ate": 8}


def norm(s):
    s = s.lower().replace("-", " ")
    s = re.sub(r"[^\w\s'%.]", " ", s)
    s = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", s)   # keep decimals, drop sentence dots
    s = re.sub(r"\b(\d+)\.0\b", r"\1", s)        # "workspace 2.0"
    s = re.sub(r"\s+", " ", s).strip()
    for pat, rep in SOUNDALIKE:
        s = re.sub(pat, rep, s)
    return s.replace("proton vpn vpn", "proton vpn")


def to_num(w):
    w = w.strip()
    try:
        return float(w)
    except ValueError:
        pass
    parts = w.split()
    if len(parts) == 1:
        return UNITS.get(w, TENS.get(w, HOMOPHONES.get(w)))
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
# Widgets: "… on the second monitor", "… in the top right", "… to the laptop screen"
WSCREEN = (r"(?:the |my )?(?:(?:main|primary|first|left|second|middle|diagnostics?) (?:monitor|screen|display)|"
           r"monitor (?:1|one|2|two)|screen (?:1|one|2|two)|laptop(?: screen| display)?|diagnostics|(?:this|current) (?:monitor|screen))")
WPOS = (r"(?:the )?(?:(?:top|bottom|upper|lower)(?: (?:left|right|center|centre|middle))?|(?:left|right|center|centre|middle)"
        r"(?: (?:top|bottom))?)(?: corner| side| of the screen)?")
WTYPE = (r"(clock|timer|countdown|stopwatch|sticky note|note|now playing|music|media|player|system stats|stats|"
         r"widget|everything)s?(?: widgets?| card| player)?")
WSIZE = r"(?:(big|large|huge|giant|massive|full|small|tiny|little|full size|full screen) )?"
WSIZES = {"big": "large", "large": "large", "huge": "huge", "giant": "huge", "massive": "huge", "full": "huge",
          "full size": "huge", "full screen": "huge", "small": "small", "tiny": "small", "little": "small"}
WTARGET = {"countdown": "timer", "sticky note": "note", "now playing": "media", "music": "media", "player": "media",
           "system stats": "stats", "widget": "all", "everything": "all"}
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
    if M(rf"(?:go to |switch to |show |open |change to )?(?:the |a )?(?:workspace|desktop) (?:number )?{NUM}"):
        n = to_num(m.group(1))
        return [step("switch_workspace", f"Workspace {n:g}.", n=int(n))] if n is not None and n == int(n) else None
    if M(rf"(?:move|send|put) (?:this |the |that )?(?:window |app )?to (?:the |a )?(?:workspace|desktop) (?:number )?{NUM}"):
        n = to_num(m.group(1))
        return [step("move_window_to_workspace", f"Moved to {n:g}.", n=int(n))] if n is not None and n == int(n) else None
    # ── lights ──
    if M(rf"(?:turn |switch )?{LIGHTS} off|(?:turn|switch) off {LIGHTS}|kill {LIGHTS}"):
        return [step("lights", "Lights off.", action="off")]
    if M(rf"(?:turn |switch )?{LIGHTS} on|(?:turn|switch) on {LIGHTS}"):
        return [step("lights", "Lights on.", action="on")]
    if M(rf"dim {LIGHTS}|{LIGHTS} dim|dim {LIGHTS} down"):
        return [step("lights", "Dimmed.", action="brightness", value="30")]
    if M(rf"(?:brighten|raise) (?:{LIGHTS}|them|it)(?: up)?|{LIGHTS} (?:to )?(?:full|max(?:imum)?)(?: brightness)?|full brightness|"
         rf"make (?:{LIGHTS}|them|it) brighter|{LIGHTS} brighter|brighter"):
        return [step("lights", "Full brightness.", action="brightness", value="100")]
    if M(rf"(?:set |turn )?{LIGHTS} (?:brightness )?(?:to )?{NUM}(?: ?%| percent)"):
        n = to_num(m.group(1))
        return [step("lights", f"Lights at {n:g} percent.", action="brightness", value=f"{n:g}")] if n is not None else None
    if M(rf"(?:set |switch |put )?{LIGHTS} (?:to |on )?(music|theme|auto)(?: mode)?|(music|theme|auto) mode (?:for |on )?{LIGHTS}"):
        mode = m.group(1) or m.group(2)
        return [step("lights", f"Lights on {mode}.", action="mode", value=mode)]
    if M(rf"(?:set |switch |change |make )?{LIGHTS} (?:to |on )?(.+?)(?: theme| mode| colou?rs?)?"):
        name = A.match_preset(m.group(1))     # "set the lights to MARK III": the lights follow the theme
        return [step("set_theme", f"{_pretty(name)}, sir.", preset=name)] if name else None
    # ── VPN ──
    if M(r"(?:turn on|connect|enable|start|switch on)(?: to)?(?: the)?(?: proton)? ?vpn|vpn on|connect(?: to)? proton"):
        return [step("vpn", "Connecting Proton.", action="connect_proton")]
    if M(r"(?:turn off|disconnect|disable|stop|switch off)(?: from)?(?: the)?(?: proton| school)? ?vpn|vpn off|disconnect(?: from)? proton"):
        return [step("vpn", "Disconnecting the VPN.", action="disconnect")]
    if M(r"(?:connect|open|turn on|start)(?: to)?(?: the)? (?:school|uni|university|waterloo|uw) vpn(?: login)?"):
        return [step("vpn", "The login window is up, sir.", action="open_school_login")]
    if M(r"(?:what(?:'s| is) (?:the )?)?vpn(?: status)?|(?:is|it's|is it|it is|is my) (?:the )?vpn (?:on|connected|up|running|active|working)|"
         r"am i (?:on|connected to|using) (?:the )?vpn|(?:what(?:'s| is) )?the vpn (?:status|doing)"):
        return [step("vpn", _vpn_status, action="status")]
    # ── theme ──
    if M(r"(?:set|change|switch|make)(?: the)? (?:theme|colou?rs?|hud) to (.+?)(?: theme)?|(?:switch to |use |activate )?(.+?) theme|theme (.+)"):
        name = A.match_preset(next(g for g in m.groups() if g))
        return [step("set_theme", f"{_pretty(name)}, sir.", preset=name)] if name else None
    # ── widgets (Widgets.qml) ──
    w = _widget(t)
    if w is not None:
        return w or None
    # ── timers ──
    if M(r"(?:timers?|reminders?) status|(?:what|which) (?:timers?|reminders?) (?:do i have|are (?:running|set|there))|"
         r"(?:list|show|check)(?: me)? (?:my |the )?(?:timers?|reminders?)|how (?:long|much time) (?:is |'s )?left(?: on (?:my |the )?timer)?|"
         r"how long (?:until|till|on) (?:my |the )?timer|(?:any|are there any) (?:timers?|reminders?)(?: running| set)?"):
        return [step("list_reminders", _timers)]
    if M(r"(?:set |start )?(?:a |an )?(?:timer|countdown)(?: for)? (.+?)(?: timer)?|(?:set |start )?(?:a |an )?(.+?) timer"):
        mins = duration_minutes(m.group(1) or m.group(2))
        return [step("set_timer", f"Timer set for {_spoken_minutes(mins)}.", minutes=round(mins, 2))] if mins else None
    if M(r"remind me in (.+?) to (.+)"):
        mins = duration_minutes(m.group(1))
        return [step("set_timer", f"I'll remind you in {_spoken_minutes(mins)}.", minutes=round(mins, 2),
                     label=m.group(2))] if mins else None
    # ── system ──
    if M(r"(?:what(?:'s| is) |that's |thats )?(?:my |the )?(?:cpu|processor|computer|laptop|pc) temperature|how hot is (?:my |the )?(?:cpu|computer|laptop|pc|processor)"):
        return [step("system_status", _cpu_temp)]
    if M(r"(?:what(?:'s| is) )?(?:my |the )?battery(?: level| status| percentage| life)?|how much battery(?: do i have| is left)?"):
        return [step("system_status", _battery)]
    # ── weather ──
    if M(r"(?:what(?:'s| is) )?(?:the )?(?:weather|forecast)(?: like)?(?: (?:today|now|outside|right now))?|how(?:'s| is) the weather(?: today| outside)?|"
         r"what(?:'s| is) it like outside|is it (?:cold|warm|hot|raining|snowing|nice)(?: outside| out)?(?: today)?"):
        return [step("weather", _weather_now)]
    if M(r"(?:what(?:'s| is) )?(?:the )?(?:weather|forecast)(?: like)? (?:for |like )?tomorrow|(?:will|is) it (?:going to )?(?:rain|snow|be cold|be warm)(?: tomorrow)?"):
        return [step("weather", _weather_tomorrow)]
    if M(r"(?:what(?:'s| is) )?(?:the )?(?:weather|forecast)(?: like)? (?:in|for|at) ([a-z][a-z .']{1,40})"):
        return [step("weather", _weather_now, place=m.group(1))]
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
        return [step("open_app", _opened(name), name=target)] if cmd else None
    if len(t.split()) <= 2:   # a bare app name, exact matches only
        if t in A.ALIASES or t in A.apps():
            return [step("open_app", f"Opening {t.title()}.", name=t)]
    return None


def _where(t):
    """Strip a trailing screen / position: 'show a clock on monitor 2 top right' → ('show a clock', 'monitor 2', 'top right')."""
    screen = pos = ""
    for _ in range(3):
        m = re.search(rf"\s+(?:on|to|onto|in|at|of|over to)\s+({WSCREEN})$", t)
        if m and not screen:
            screen, t = m.group(1), t[:m.start()]
            continue
        m = re.search(rf"\s+(?:in|at|to|on|into)\s+({WPOS})$", t)
        if m and not pos:
            pos, t = m.group(1), t[:m.start()]
            continue
        break
    return t, screen, pos


def _on(screen):
    role = A.norm_screen(screen) if screen else ""
    return {"main": " on the main monitor", "diag": " on the second monitor", "media": " on the laptop screen"}.get(role or "", "")


def _widget(t):
    """Widget commands → steps; [] = it's a widget command but not one the fast path can do; None = not one."""
    rest, scr, pos = _where(t)
    where = dict(screen=scr, position=pos)
    m = None

    def W(p):
        nonlocal m
        m = re.fullmatch(p, rest)
        return m
    show = r"(?:show|put|add|display|open|give me|bring up|pull up|start|set up|pop up|throw up)(?: me)?(?: up)?"
    # timer, when a screen / position is given ("set a timer for 10 minutes on monitor 2")
    if (scr or pos) and W(rf"(?:set |start |{show} )?(?:a |an |the )?(?:timer|countdown)(?: for)? (.+?)(?: timer)?|"
                         rf"(?:set |start |{show} )?(?:a |an )?(.+?) (?:timer|countdown)"):
        mins = duration_minutes(m.group(1) or m.group(2) or "")
        if mins:
            return [step("set_timer", f"Timer set for {_spoken_minutes(mins)}{_on(scr)}.", minutes=round(mins, 2), **where)]
    # move / pin
    if (scr or pos) and W(rf"(?:move|send|drag|shift) (?:the |my |that |this )?{WTYPE}|(?:put|bring) (?:the |my |that |this ){WTYPE}"):
        kind = m.group(1) or m.group(2)
        target = WTARGET.get(kind, kind)
        return [step("widget_move", "Moved.", target=target, **where)]
    if W(rf"(?:make|set) (?:the |my |that |this )?{WTYPE} (bigger|larger|smaller|big|large|huge|giant|small|tiny|normal|normal size|full size|full screen)|"
         rf"(enlarge|grow|expand|maximi[sz]e|shrink|minimi[sz]e) (?:the |my |that |this )?{WTYPE}"):
        kind = m.group(1) or m.group(4)
        word = m.group(2) or {"enlarge": "bigger", "grow": "bigger", "expand": "bigger", "shrink": "smaller"}.get(m.group(3), "")
        if not word:
            word = "huge" if m.group(3).startswith("maxim") else "small"
        size = {"larger": "bigger", "big": "large", "giant": "huge", "tiny": "small", "normal size": "normal",
                "full size": "huge", "full screen": "huge"}.get(word, word)
        return [step("widget_move", "Done.", target=WTARGET.get(kind, kind), size=size)]
    if W(rf"(pin|unpin) (?:the |my |that |this )?{WTYPE}(?: (?:on top|to the top|above (?:the )?windows))?"):
        target = WTARGET.get(m.group(2), m.group(2))
        on = m.group(1) == "pin"
        return [step("widget_move", "Pinned above your windows." if on else "Unpinned.", target=target, pinned=on)]
    # clocks: "show a clock", "show an analog clock", "show New York time", "show a Tokyo clock", "a clock for London"
    if W(rf"{show} (?:a |an |the )?{WSIZE}(?:(analog|analogue|digital) )?clock(?: for (.+))?|"
         rf"{show} (?:the )?time (?:in|for) (.+)|{show} (?:a |an |the )?(?!a |an |the |big |large |huge |small )(.+?) (?:time|clock)"):
        size, style, city = WSIZES.get(m.group(1) or "", ""), m.group(2), m.group(3) or m.group(4) or m.group(5)
        if city and city in ("local", "current"):
            city = None
        if city and not A.city_tz(city):
            return []                          # Claude can work out an odd place name
        name = city.title() if city else ""
        return [step("widget_add", f"{name + ' time' if name else 'Clock'}{_on(scr)}.", type="clock",
                     tz=city or "", analog=bool(style and style.startswith("analog")), size=size, **where)]
    if W(rf"{show} (?:a |an |the )?{WSIZE}stopwatch"):
        return [step("widget_add", f"Stopwatch running{_on(scr)}.", type="stopwatch", size=WSIZES.get(m.group(1) or "", ""), **where)]
    if W(rf"{show} (?:the |a |my )?{WSIZE}(?:now playing|music|media|song|spotify)(?: widget| player| card| info)?"):
        return [step("widget_add", f"Now playing{_on(scr)}.", type="media", size=WSIZES.get(m.group(1) or "", ""), **where)]
    if W(rf"{show} (?:the |my |a )?{WSIZE}(?:system |computer |pc )?(?:stats|statistics|system monitor|system info|system status|cpu and ram|dashboard|diagnostics)(?: widget| card| dashboard)?"):
        size = WSIZES.get(m.group(1) or "", "") or ("huge" if re.search(r"dashboard|diagnostics", rest) else "")
        return [step("widget_add", f"{'Diagnostics dashboard' if size == 'huge' else 'System stats'}{_on(scr)}.", type="stats", size=size, **where)]
    if W(r"(?:add|make|put up|create|leave|show|pin up|write)(?: me)? (?:a )?(?:sticky )?note(?: saying| that says| reading| with| to)? (.+)"):
        text = m.group(1).strip()
        return [step("widget_add", f"Noted{_on(scr)}.", type="note", text=text[:1].upper() + text[1:], **where)]
    # remove / clear
    if W(rf"(?:remove|close|hide|get rid of|dismiss|delete|cancel|kill|clear|take down) (?:the |my |that |this |all (?:the |my )?)?{WTYPE}"):
        target = WTARGET.get(m.group(1), m.group(1))
        return [step("widget_remove", "Cleared." if target == "all" else "Removed.", target=target, screen=scr)]
    if (scr and W(r"clear(?: off)?(?: (?:all|everything|the widgets|all widgets))?")) or W(r"clear (?:all )?(?:the |my )?widgets"):
        return [step("widget_remove", "Cleared.", target="all", screen=scr)]
    m = re.fullmatch(rf"clear(?: off| up)? ({WSCREEN})", t)       # "clear monitor 2"
    if m:
        return [step("widget_remove", "Cleared.", target="all", screen=m.group(1))]
    return None


def _pretty(name):
    return " ".join(w if re.fullmatch(r"[IVX]+", w) else w.title() for w in (name or "").split())


def _opened(name):
    return lambda r: f"{name.title()} is up, sir." if "is up" in str(r.get("result", "")) else f"Opening {name.title()}."


def _timers(r):
    items = r.get("items") or []
    if not items:
        return "No timers running, sir."
    def one(i):
        left = max(0.0, i["minutes_left"])
        what = "" if i["text"] in ("timer", "") else f" for {i['text']}" if i["kind"] == "timer" else f": {i['text']}"
        return f"{'a timer' if i['kind'] == 'timer' else 'a reminder'}{what}, {_spoken_minutes(round(left)) if left >= 1 else 'under a minute'} left"
    head = "You have " if len(items) == 1 else f"You have {len(items)}: "
    return head + "; ".join(one(i) for i in items[:3]) + "."


def _cpu_temp(r):
    c = (r.get("temps") or {}).get("cpu_c")
    return f"The CPU is at {c} degrees, sir, at {r.get('cpu_percent', 0):g}% load." if c else "I can't read the CPU temperature, sir."


def _battery(r):
    b = r.get("battery")
    if not b:
        return "There's no battery reading, sir."
    return f"Battery at {b['percent']}%, {'charging' if b['status'] == 'charging' else b['status'] if b['ac'] else 'on battery'}."


def _weather_now(r):
    n, d = r["now"], r["today"]
    rain = f" {d['rain_chance_pct']}% chance of rain." if (d.get("rain_chance_pct") or 0) >= 30 else ""
    feels = f", feels like {n['feels_like_c']}" if abs(n["feels_like_c"] - n["temp_c"]) >= 3 else ""
    return f"{n['temp_c']}°C and {n['sky']} in {r['place']}{feels}. High of {d['high_c']}, low of {d['low_c']}.{rain}"


def _weather_tomorrow(r):
    d = r["tomorrow"]
    rain = f", {d['rain_chance_pct']}% chance of rain" if (d.get("rain_chance_pct") or 0) >= 20 else ""
    return f"Tomorrow in {r['place']}: {d['sky']}, high of {d['high_c']}, low of {d['low_c']}{rain}."


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
