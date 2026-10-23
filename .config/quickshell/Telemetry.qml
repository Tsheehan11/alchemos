pragma Singleton
// Extra readings for the combat telemetry layout (DiagPanel in combat mode). Polls only while
// that layout is on screen, at SysStats' rate (2.5 s in combat).
// SysStats still supplies total CPU, GPU busy, RAM and battery %; this adds per-core load,
// clocks, package temp, throttling, iGPU frequency, fans, battery power and Windows-partition I/O.
// Everything is read from /proc and sysfs without root (RAPL energy counters are root-only,
// so power draw comes from the battery and is only known while unplugged).
import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: root

    // The layout is on screen (same test as DiagPanel's visible)
    readonly property var screen: Quickshell.screens.find(s => s.name === Perf.telemetryScreen) || null
    readonly property bool active: screen !== null && Theme.cfg.showDiag && !Perf.hidden(screen, "telemetry")
    readonly property int historyLength: 60

    property var cores: []              // 0..1 per logical CPU
    property real clockAvgGhz: 0
    property real clockMaxGhz: 0
    property real pkgTemp: -1           // °C, -1 = no sensor
    property bool cpuThrottling: false  // cores / package spent time thermally throttled this interval
    property real gpuMhz: 0
    property real gpuMaxMhz: 0
    property bool gpuThrottling: false
    property var gpuReasons: []         // e.g. ["thermal", "pl1"]
    property var fans: []               // [{ label, rpm }]
    property var temps: []              // [{ label, c }] board sensors (Dell)
    property real powerW: -1            // battery discharge / charge rate, -1 = unknown
    property real batteryHours: -1      // time left while discharging
    property string disk: ""            // e.g. nvme0n1p3
    property string diskMount: ""
    property real diskRead: 0           // bytes/s
    property real diskWrite: 0
    property var diskReadHistory: []
    property var diskWriteHistory: []
    property real diskUsedGb: 0
    property real diskTotalGb: 0

    // Game shown in the header: Steam name from the app manifest, else the window title
    property string gameName: ""
    readonly property real since: GameMode.since

    property var prevCores: []          // [[total, idle], …]
    property real prevThrottle: -1
    property real prevRead: -1
    property real prevWrite: -1
    property double prevAt: 0

    function push(arr, v) { return arr.concat([v]).slice(-root.historyLength); }

    // hwmon files to poll, found once: coretemp's package sensor and the Dell fans / temps.
    // Only those: nvme and dell_smm (BIOS SMM calls) take 10–20 ms a read and can stutter a game,
    // so dell_smm is used only when dell_ddv (same sensors, read through WMI) isn't there.
    property string sensorFiles: ""
    Process {
        running: true
        command: ["sh", "-c", [
            "cd /sys && for h in class/hwmon/hwmon*; do n=$(cat $h/name); case $n in",
            "  coretemp) for l in $h/temp*_label; do [ \"$(cat $l)\" = 'Package id 0' ] && echo $n $h/name $l ${l%_label}_input; done;;",
            "  dell_ddv) echo $n $h/name $h/fan*_input $h/fan*_label $h/temp*_input $h/temp*_label;;",
            "  dell_smm) echo $n $h/name $h/fan*_input $h/temp*_input;;",
            "esac; done"
        ].join("\n")]
        stdout: StdioCollector {
            onStreamFinished: {
                const rows = text.trim().split("\n").filter(l => l !== "").map(l => l.split(" "));
                const ddv = rows.some(r => r[0] === "dell_ddv");
                root.sensorFiles = rows.filter(r => !(ddv && r[0] === "dell_smm")).map(r => r.slice(1).join(" ")).join(" ");
            }
        }
    }

    // One grep for every sysfs file (path:value lines) keeps a poll to a handful of processes
    Process {
        id: proc
        command: ["sh", "-c", [
            "grep '^cpu[0-9]' /proc/stat",
            // The Windows partition = the first mounted NTFS filesystem (where the Steam games live)
            "m=$(findmnt -rn -t ntfs3,ntfs,fuseblk -o SOURCE,TARGET | head -1)",
            "if [ -n \"$m\" ]; then d=${m%% *}; d=${d##*/}; echo \"MNT $d ${m#* }\"; grep -w \"$d\" /proc/diskstats; df -Pk \"${m#* }\" | awk 'NR==2 {print \"DF\", $3, $2}'; fi",
            "cd /sys && grep -H '' devices/system/cpu/cpu[0-9]*/cpufreq/scaling_cur_freq" +
            // Time spent throttled, not the event counts: those tick on every brief threshold crossing
            " devices/system/cpu/cpu[0-9]*/thermal_throttle/core_throttle_total_time_ms devices/system/cpu/cpu0/thermal_throttle/package_throttle_total_time_ms" +
            " " + root.sensorFiles +
            // rps_cur = the clock it runs at while busy; rps_act reads 0 whenever it naps in RC6 between frames
            " class/drm/card[0-9]*/gt/gt0/rps_cur_freq_mhz class/drm/card[0-9]*/gt/gt0/rps_RP0_freq_mhz class/drm/card[0-9]*/gt/gt0/throttle_reason_*" +
            " class/power_supply/BAT*/status class/power_supply/BAT*/power_now class/power_supply/BAT*/current_now" +
            " class/power_supply/BAT*/voltage_now class/power_supply/BAT*/charge_now class/power_supply/BAT*/energy_now 2>/dev/null"
        ].join("\n")]
        stdout: StdioCollector { onStreamFinished: root.parse(text) }
    }

    Timer {
        interval: SysStats.interval
        running: root.active
        repeat: true
        triggeredOnStart: true
        onTriggered: proc.running = true
    }

    function parse(t) {
        const now = Date.now();
        const dt = root.prevAt > 0 ? (now - root.prevAt) / 1000 : 0;
        root.prevAt = now;
        const cores = [], prev = [], f = {};   // f: sysfs path → value
        let disk = "", diskStat = null;
        for (const raw of t.split("\n")) {
            const line = raw.trim();
            const p = line.split(/\s+/);
            if (/^cpu\d+$/.test(p[0])) {
                const v = p.slice(1).map(Number);
                const idle = v[3] + v[4], total = v.reduce((a, b) => a + b, 0);
                const i = cores.length, o = root.prevCores[i];
                cores.push(o && total > o[0] ? Math.max(0, Math.min(1, 1 - (idle - o[1]) / (total - o[0]))) : 0);
                prev.push([total, idle]);
            } else if (p[0] === "MNT") {
                disk = p[1]; root.diskMount = p.slice(2).join(" ");
            } else if (p[0] === "DF") {
                root.diskUsedGb = Number(p[1]) / 1048576; root.diskTotalGb = Number(p[2]) / 1048576;
            } else if (disk !== "" && p[2] === disk) {
                diskStat = p;                    // /proc/diskstats: sectors read = $6, written = $10
            } else {
                const c = line.indexOf(":");
                if (c > 0) f[line.slice(0, c)] = line.slice(c + 1);
            }
        }
        const keys = Object.keys(f);
        const num = k => Number(f[k]);
        const sum = re => keys.filter(k => re.test(k)).reduce((a, k) => a + num(k), 0);

        root.cores = cores;
        root.prevCores = prev;

        const freqs = keys.filter(k => k.endsWith("scaling_cur_freq")).map(num).filter(x => x > 0);
        root.clockAvgGhz = freqs.length ? freqs.reduce((a, b) => a + b, 0) / freqs.length / 1e6 : 0;
        root.clockMaxGhz = freqs.length ? Math.max.apply(null, freqs) / 1e6 : 0;

        const thr = sum(/throttle_total_time_ms$/);
        root.cpuThrottling = root.prevThrottle >= 0 && thr > root.prevThrottle;
        root.prevThrottle = thr;

        // hwmon: coretemp's package sensor; Dell fans + board temps. dell_ddv and dell_smm report
        // the same sensors; keep the labelled (ddv) set if both exist
        const mons = {};
        for (const k of keys) {
            const m = k.match(/^class\/hwmon\/(hwmon\d+)\/name$/);
            if (m) mons[f[k]] = "class/hwmon/" + m[1] + "/";
        }
        root.pkgTemp = -1;
        if (mons.coretemp) {
            const lab = keys.find(k => k.startsWith(mons.coretemp) && f[k] === "Package id 0");
            if (lab) root.pkgTemp = num(lab.replace("_label", "_input")) / 1000;
        }
        const dell = mons.dell_ddv || mons.dell_smm;
        const fans = [], temps = [];
        if (dell) {
            for (const k of keys.filter(k => k.startsWith(dell) && k.endsWith("_input")).sort()) {
                const label = f[k.replace("_input", "_label")] || "";
                if (/\/fan\d+_input$/.test(k)) fans.push({ label: label || "FAN", rpm: num(k) });
                else if (label && label !== "Unknown" && label !== "Other") temps.push({ label: label, c: num(k) / 1000 });
            }
        }
        root.fans = fans;
        root.temps = temps;

        const gt = keys.find(k => k.endsWith("/gt/gt0/rps_cur_freq_mhz"));
        if (gt) {
            const base = gt.replace("rps_cur_freq_mhz", "");
            root.gpuMhz = num(gt);
            root.gpuMaxMhz = num(base + "rps_RP0_freq_mhz");
            root.gpuThrottling = f[base + "throttle_reason_status"] === "1";
            root.gpuReasons = keys.filter(k => k.startsWith(base + "throttle_reason_") && !k.endsWith("_status") && f[k] === "1")
                                  .map(k => k.slice((base + "throttle_reason_").length).replace("_", " "));
        } else {
            root.gpuMhz = 0; root.gpuMaxMhz = 0; root.gpuThrottling = false; root.gpuReasons = [];
        }

        // Battery: power_now µW, or current_now µA × voltage_now µV; time left = µAh / µA or µWh / µW
        root.powerW = -1; root.batteryHours = -1;
        const st = keys.find(k => /^class\/power_supply\/BAT\w*\/status$/.test(k));
        if (st) {
            const b = st.replace("status", ""), v = n => f[b + n] !== undefined ? num(b + n) : 0;
            const status = f[st], pw = v("power_now"), cur = v("current_now"), volt = v("voltage_now");
            const w = pw > 0 ? pw / 1e6 : cur > 0 && volt > 0 ? cur * volt / 1e12 : 0;
            if ((status === "Discharging" || status === "Charging") && w > 0.05) {
                root.powerW = w;
                if (status === "Discharging")
                    root.batteryHours = v("charge_now") > 0 && cur > 0 ? v("charge_now") / cur : v("energy_now") > 0 && pw > 0 ? v("energy_now") / pw : -1;
            }
        }

        root.disk = diskStat ? disk : "";
        if (diskStat) {
            const rd = Number(diskStat[5]) * 512, wr = Number(diskStat[9]) * 512;
            if (root.prevRead >= 0 && dt > 0) {
                root.diskRead = Math.max(0, (rd - root.prevRead) / dt);
                root.diskWrite = Math.max(0, (wr - root.prevWrite) / dt);
                root.diskReadHistory = root.push(root.diskReadHistory, root.diskRead);
                root.diskWriteHistory = root.push(root.diskWriteHistory, root.diskWrite);
            }
            root.prevRead = rd; root.prevWrite = wr;
        }
    }

    // ── Game name ──
    Process {
        id: namer
        stdout: StdioCollector { onStreamFinished: root.gameName = text.trim() }
    }
    function resolveName() {
        const cls = GameMode.games.length ? GameMode.games[0] : "";
        if (cls === "") { root.gameName = ""; return; }
        namer.running = false;
        // steam_app_<id> → "name" in appmanifest_<id>.acf in any Steam library; else the window title
        namer.command = ["sh", "-c", [
            "id=$(printf '%s' \"$1\" | sed -n 's/^steam_app_\\([0-9]*\\)$/\\1/p')",
            "vdf=~/.local/share/Steam/steamapps/libraryfolders.vdf",
            "[ -n \"$id\" ] && n=$({ echo ~/.local/share/Steam; sed -n 's/.*\"path\"[[:space:]]*\"\\(.*\\)\"/\\1/p' $vdf 2>/dev/null; } |",
            "  while IFS= read -r lib; do sed -n 's/^[[:space:]]*\"name\"[[:space:]]*\"\\(.*\\)\"/\\1/p' \"$lib/steamapps/appmanifest_$id.acf\" 2>/dev/null; done | head -1)",
            "[ -n \"$n\" ] && { echo \"$n\"; exit; }",
            "hyprctl clients -j | jq -r --arg c \"$1\" '[.[] | select(.class == $c) | .title][0] // empty'"
        ].join("\n"), "sh", cls];
        namer.running = true;
    }
    Connections {
        target: GameMode
        function onGamesChanged() { root.resolveName(); }
    }
    Component.onCompleted: resolveName()

    function fmtSession(s) {
        s = Math.max(0, Math.floor(s));
        const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), sec = s % 60;
        return h + ":" + String(m).padStart(2, "0") + ":" + String(sec).padStart(2, "0");
    }
}
