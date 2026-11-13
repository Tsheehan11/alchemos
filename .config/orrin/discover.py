#!/usr/bin/env python3
"""
Smart-home discovery for Orrin phase 2. READ-ONLY: listens for mDNS / SSDP
announcements and asks Cast devices for their public info; controls nothing.

  ~/.config/orrin/.venv/bin/python ~/.config/orrin/discover.py   → writes devices.md

Run it on the home network (not through Proton: mDNS/SSDP stay on the LAN either way).
"""
import socket
import subprocess
import time
from datetime import datetime
from pathlib import Path

from zeroconf import ServiceBrowser, ServiceListener, Zeroconf

OUT = Path(__file__).resolve().parent / "devices.md"
SCAN_S = 8

# mDNS service → (kind, local API note)
SERVICES = {
    "_googlecast._tcp.local.": ("Google Cast", "Cast protocol (pychromecast): media, volume"),
    "_googlezone._tcp.local.": ("Google speaker group", "Cast group"),
    "_nest-cam._tcp.local.": ("Nest camera", "no documented local API (cloud SDM)"),
    "_hap._tcp.local.": ("HomeKit accessory", "HAP (needs pairing)"),
    "_matter._tcp.local.": ("Matter device", "Matter (needs commissioning)"),
    "_matterc._udp.local.": ("Matter device (commissionable)", "Matter"),
    "_meshcop._udp.local.": ("Thread border router", "Thread"),
    "_hue._tcp.local.": ("Philips Hue bridge", "Hue local REST API"),
    "_esphomelib._tcp.local.": ("ESPHome device", "ESPHome native API"),
    "_wled._tcp.local.": ("WLED", "WLED JSON API"),
    "_shelly._tcp.local.": ("Shelly", "Shelly local HTTP API"),
    "_elg._tcp.local.": ("Elgato light", "Elgato HTTP API"),
    "_home-assistant._tcp.local.": ("Home Assistant", "HA REST / WebSocket API"),
    "_spotify-connect._tcp.local.": ("Spotify Connect", "Spotify Connect (via Spotify)"),
    "_airplay._tcp.local.": ("AirPlay receiver", "AirPlay"),
    "_raop._tcp.local.": ("AirPlay audio", "AirPlay"),
    "_sonos._tcp.local.": ("Sonos", "Sonos local UPnP/HTTP"),
    "_roku._tcp.local.": ("Roku", "Roku ECP HTTP API"),
    "_androidtvremote2._tcp.local.": ("Android / Google TV", "Android TV Remote v2 (needs pairing)"),
    "_amzn-wplay._tcp.local.": ("Fire TV", "limited"),
    "_ipp._tcp.local.": ("Printer", "IPP"),
    "_printer._tcp.local.": ("Printer", "LPD"),
    "_smb._tcp.local.": ("File share", "SMB"),
    "_kdeconnect._udp.local.": ("KDE Connect", "KDE Connect protocol"),
    "_companion-link._tcp.local.": ("Apple device", "none"),
    "_miio._udp.local.": ("Xiaomi device", "miIO (token needed)"),
    "_tplink._tcp.local.": ("TP-Link device", "Kasa/Tapo local API"),
}


class Collector(ServiceListener):
    def __init__(self):
        self.found = {}

    def add_service(self, zc, type_, name):
        info = zc.get_service_info(type_, name, timeout=2000)
        if not info:
            return
        ips = info.parsed_addresses()
        props = {k.decode(errors="ignore"): (v or b"").decode(errors="ignore") for k, v in info.properties.items()}
        friendly = props.get("fn") or props.get("md") or name.replace("." + type_, "")
        self.found[(type_, name)] = {"name": friendly, "type": type_, "ip": ips[0] if ips else "?",
                                     "port": info.port, "model": props.get("md", ""), "props": props}

    update_service = add_service

    def remove_service(self, *a):
        pass


def ssdp(timeout=3.0):
    """UPnP devices answering an M-SEARCH (TVs, Roku, Sonos, WeMo, routers…)."""
    msg = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: \"ssdp:discover\"\r\n"
           "MX: 2\r\nST: ssdp:all\r\n\r\n").encode()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    s.settimeout(0.5)
    s.sendto(msg, ("239.255.255.250", 1900))
    seen, end = {}, time.time() + timeout
    while time.time() < end:
        try:
            data, (ip, _) = s.recvfrom(4096)
        except socket.timeout:
            continue
        hdr = {}
        for line in data.decode(errors="ignore").split("\r\n")[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                hdr[k.strip().lower()] = v.strip()
        e = seen.setdefault(ip, {"server": hdr.get("server", ""), "st": set(), "location": hdr.get("location", "")})
        e["st"].add(hdr.get("st", ""))
    s.close()
    return seen


def cast_details():
    try:
        import pychromecast
    except ImportError:
        return {}
    casts, browser = pychromecast.get_chromecasts(timeout=SCAN_S)
    out = {}
    for c in casts:
        ci = c.cast_info
        out[str(ci.host)] = {"name": ci.friendly_name, "model": ci.model_name, "cast_type": ci.cast_type,
                             "manufacturer": ci.manufacturer or ""}
    browser.stop_discovery()
    return out


def govee():
    try:
        p = subprocess.run(["alchemos-govee", "scan"], capture_output=True, text=True, timeout=10)
        return p.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def main():
    print(f"listening for mDNS for {SCAN_S} s…")
    zc = Zeroconf()
    col = Collector()
    browsers = [ServiceBrowser(zc, t, col) for t in SERVICES]
    casts = cast_details()   # takes SCAN_S while the browsers collect
    time.sleep(1)
    zc.close()
    print("asking UPnP (SSDP)…")
    upnp = ssdp()
    gv = govee()

    rows, ips_done = [], set()
    for (type_, name), d in sorted(col.found.items(), key=lambda kv: kv[1]["ip"]):
        kind, api = SERVICES[type_]
        if type_ == "_googlecast._tcp.local." and d["ip"] in casts:
            c = casts[d["ip"]]
            kind = {"audio": "Google/Nest speaker", "group": "Speaker group", "cast": "Chromecast / Google TV / Nest display"}.get(c["cast_type"], kind)
            d["model"] = c["model"] or d["model"]
        rows.append((d["name"], kind + (f" ({d['model']})" if d["model"] else ""), f"{d['ip']}:{d['port']}", api))
        ips_done.add(d["ip"])
    for ip, e in sorted(upnp.items()):
        if ip in ips_done:
            continue
        sts = ", ".join(sorted(x.split(":")[-2] if x.count(":") > 2 else x for x in e["st"] if x))[:80]
        rows.append((e["server"][:50] or "UPnP device", f"UPnP ({sts})", ip, "UPnP / SSDP; check its description XML"))

    lines = [
        "# Smart-home devices on the LAN",
        "",
        f"Scanned {datetime.now():%Y-%m-%d %H:%M} by `discover.py` (read-only: mDNS, SSDP, Cast info; nothing was controlled).",
        "Phase 2 candidates for Orrin MCP servers. Not tracked by `stark` (local network details).",
        "",
        "| Name | Type | Address | Local API |",
        "|---|---|---|---|",
    ]
    lines += [f"| {n} | {t} | {a} | {api} |" for n, t, a, api in rows] or ["| (nothing found) | | | |"]
    if gv:
        lines += ["", "## Govee (alchemos-govee scan)", "", "```", gv, "```"]
    lines += ["", "## Notes", "",
              "- Google Cast / Nest speakers and displays: local Cast protocol (pychromecast) covers media and volume; "
              "Google Home routines and Nest thermostats/cameras need Google's cloud APIs (Device Access / SDM).",
              "- Devices that sleep or sit on another VLAN / guest Wi-Fi won't answer; re-run `discover.py` to refresh."]
    OUT.write_text("\n".join(lines) + "\n")
    print(f"{len(rows)} devices → {OUT}")


if __name__ == "__main__":
    main()
