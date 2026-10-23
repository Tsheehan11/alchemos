// Shared system stats, updated every 2 s (5 s on battery saver, 10 s in combat mode,
// 2.5 s in combat mode while the diagnostics wall is on screen):
// CPU, GPU, RAM, battery, Wi-Fi signal, network speed, disk, uptime + history for graphs.
pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: root

    property bool diagShown: false  // set by DiagPanel
    readonly property int interval: GameMode.quiet ? (diagShown ? 2500 : 10000) : PowerMode.saver ? 5000 : 2000
    readonly property int historyLength: 60

    property real cpu: 0            // 0..1
    property real gpu: 0            // 0..1  GPU busy (smoothed)
    property bool gpuAvailable: false
    property real gpuMhz: 0
    property real ram: 0            // 0..1
    property real ramUsedGb: 0
    property real ramTotalGb: 0
    property real battery: 0        // 0..1
    property bool charging: false
    property bool discharging: false    // running on battery
    property real wifi: 0           // 0..1 signal quality
    property real rxRate: 0         // bytes/s
    property real txRate: 0         // bytes/s
    property real diskUsedGb: 0
    property real diskTotalGb: 0
    property real uptimeS: 0
    property bool polled: false     // first reading is in (battery state is real)

    property var cpuHistory: []
    property var gpuHistory: []
    property var rxHistory: []
    property var txHistory: []

    property real prevTotal: 0
    property real prevIdle: 0
    property real prevRc6: -1
    property double prevRc6At: 0
    property bool haveRc6: false
    readonly property real smoothing: 0.35   // 0..1 — lower = smoother GPU reading
    property real prevRx: -1
    property real prevTx: -1

    function push(arr, v) { return arr.concat([v]).slice(-root.historyLength); }

    function fmtRate(bps) {
        if (bps >= 1048576) return (bps / 1048576).toFixed(1) + " MB/s";
        if (bps >= 1024) return Math.round(bps / 1024) + " KB/s";
        return Math.round(bps) + " B/s";
    }

    function fmtUptime(s) {
        const d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60);
        return (d > 0 ? d + "d " : "") + h + "h " + m + "m";
    }

    Process {
        id: proc
        command: ["sh", "-c", [
            "echo \"CPU $(head -1 /proc/stat)\"",
            "awk '/^MemTotal:/{t=$2} /^MemAvailable:/{a=$2} END{print \"MEM\", t, a}' /proc/meminfo",
            "echo \"BAT $(cat /sys/class/power_supply/BAT*/capacity 2>/dev/null | head -1) $(cat /sys/class/power_supply/BAT*/status 2>/dev/null | head -1)\"",
            "for c in /sys/class/drm/card[0-9]*; do if [ -r $c/gt_act_freq_mhz ]; then echo \"GPU $(cat $c/gt_act_freq_mhz) $(cat $c/gt_RP0_freq_mhz)\"; break; fi; done",
            "for f in /sys/class/drm/card[0-9]*/gt/gt0/rc6_residency_ms /sys/class/drm/card[0-9]*/power/rc6_residency_ms; do if [ -r \"$f\" ]; then echo \"RC6 $(cat $f)\"; break; fi; done",
            "awk 'NR>2 && $1 !~ /^lo/ {gsub(\":\", \" \"); rx+=$2; tx+=$10} END{print \"NET\", rx, tx}' /proc/net/dev",
            "awk 'NR>2 {print \"WIFI\", $3; exit}' /proc/net/wireless",
            "df -Pk / | awk 'NR==2 {print \"DISK\", $3, $2}'",
            "echo \"UP $(cut -d' ' -f1 /proc/uptime)\""
        ].join("\n")]
        stdout: StdioCollector {
            onStreamFinished: root.parse(text)
        }
    }

    Timer {
        interval: root.interval
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: proc.running = true
    }

    function parse(t) {
        const dt = root.interval / 1000;
        let sawWifi = false;
        for (const raw of t.split("\n")) {
            const p = raw.trim().split(/\s+/);
            switch (p[0]) {
            case "CPU": {
                const f = p.slice(2).map(Number);
                const idle = f[3] + f[4];
                const total = f.reduce((a, b) => a + b, 0);
                if (root.prevTotal > 0) {
                    const d = total - root.prevTotal;
                    if (d > 0) root.cpu = Math.max(0, Math.min(1, 1 - (idle - root.prevIdle) / d));
                }
                root.prevTotal = total; root.prevIdle = idle;
                root.cpuHistory = root.push(root.cpuHistory, root.cpu);
                break;
            }
            case "MEM": {
                const tot = Number(p[1]), avail = Number(p[2]);
                if (tot > 0) {
                    root.ram = 1 - avail / tot;
                    root.ramTotalGb = tot / 1048576;
                    root.ramUsedGb = (tot - avail) / 1048576;
                }
                break;
            }
            case "BAT":
                if (p[1]) root.battery = Number(p[1]) / 100;
                root.charging = p[2] === "Charging";
                root.discharging = p[2] === "Discharging";
                break;
            case "RC6": {
                // Real GPU busy %: time the GPU spent NOT in its idle (RC6) state
                const rc6 = Number(p[1]), now = Date.now();
                if (root.prevRc6 >= 0 && now > root.prevRc6At) {
                    const busy = 1 - (rc6 - root.prevRc6) / (now - root.prevRc6At);
                    root.haveRc6 = true;
                    root.gpuAvailable = true;
                    root.gpu = root.gpu + root.smoothing * (Math.max(0, Math.min(1, busy)) - root.gpu);
                    root.gpuHistory = root.push(root.gpuHistory, root.gpu);
                }
                root.prevRc6 = rc6; root.prevRc6At = now;
                break;
            }
            case "GPU": {
                // Fallback when RC6 isn't readable: clock speed vs max, smoothed
                const act = Number(p[1]), max = Number(p[2]);
                root.gpuMhz = act;
                if (max > 0 && !root.haveRc6) {
                    root.gpuAvailable = true;
                    root.gpu = root.gpu + root.smoothing * (Math.max(0, Math.min(1, act / max)) - root.gpu);
                    root.gpuHistory = root.push(root.gpuHistory, root.gpu);
                }
                break;
            }
            case "NET": {
                const rx = Number(p[1]), tx = Number(p[2]);
                if (root.prevRx >= 0) {
                    root.rxRate = Math.max(0, (rx - root.prevRx) / dt);
                    root.txRate = Math.max(0, (tx - root.prevTx) / dt);
                    root.rxHistory = root.push(root.rxHistory, root.rxRate);
                    root.txHistory = root.push(root.txHistory, root.txRate);
                }
                root.prevRx = rx; root.prevTx = tx;
                break;
            }
            case "WIFI":
                sawWifi = true;
                root.wifi = Math.max(0, Math.min(1, parseFloat(p[1]) / 70));
                break;
            case "DISK":
                root.diskUsedGb = Number(p[1]) / 1048576;
                root.diskTotalGb = Number(p[2]) / 1048576;
                break;
            case "UP":
                root.uptimeS = parseFloat(p[1]);
                break;
            }
        }
        if (!sawWifi) root.wifi = 0;
        root.polled = true;
    }
}
