// Weather at home (Settings → JARVIS place, jarvisPlace) from Open-Meteo, through jarvis feed
// (weather.json, refreshed every 30 min). A radar sweep turns while effects run.
import QtQuick
import ".."

WidgetBody {
    id: w
    readonly property var wx: JarvisFeed.weather || ({})
    readonly property var now: wx.now || null
    readonly property bool has: now !== null
    title: "WEATHER" + (wx.place ? " // " + String(wx.place).toUpperCase() : "")
    detail: wx.updated ? Qt.formatDateTime(new Date(wx.updated * 1000), Theme.cfg.clock24 ? "HH:mm" : "h:mm AP") : ""
    // Nerd Font weather glyphs (monochrome, so they take the theme colour)
    readonly property var glyphs: [["thunder", "\ue31d"], ["snow", "\ue31a"], ["freezing", "\ue3ad"], ["drizzle", "\ue31b"], ["shower", "\ue319"],
                                   ["rain", "\ue318"], ["fog", "\ue313"], ["overcast", "\ue312"], ["partly", "\ue302"], ["clear", "\ue30d"]]
    function glyph(sky) { sky = String(sky || "").toLowerCase(); const g = glyphs.find(x => sky.indexOf(x[0]) >= 0); return g ? g[1] : "\ue312"; }
    function line(d) { return d ? d.high_c + "° / " + d.low_c + "°  " + String(d.sky).toUpperCase() + (d.rain_chance_pct ? "  ☂ " + d.rain_chance_pct + "%" : "") : ""; }

    implicitWidth: 300
    implicitHeight: 92

    Item {
        width: 84; height: 84
        Ring { anchors.centerIn: parent; radius: 38; thickness: 1; value: 1; animated: false; color: Theme.p(0.3); trackColor: "transparent" }
        Ring { anchors.centerIn: parent; radius: 30; thickness: 1; value: 1; animated: false; dashed: true; dash: [1, 7]; color: Theme.p(0.35); trackColor: "transparent" }
        Rectangle {     // radar sweep
            visible: w.live && !w.saver
            x: 42; y: 42 - 38; width: 1.5; height: 38
            gradient: Gradient { GradientStop { position: 0; color: Theme.p(0.0) } GradientStop { position: 1; color: Theme.p(0.7) } }
            transform: Rotation { origin.x: 0.75; origin.y: 38; angle: w.t * 40 }
        }
        Text { anchors.centerIn: parent; text: w.has ? w.glyph(w.now.sky) : "◌"; color: Theme.text; font.family: Style.fonts.body; font.pixelSize: 28 }
    }
    Column {
        x: 96; width: 204; spacing: 2
        Row {
            spacing: 8
            Text { text: w.has ? w.now.temp_c + "°" : "—"; color: Theme.text; font.family: Style.fonts.numeric; font.pixelSize: 34; font.weight: Font.Light }
            Column {
                anchors.bottom: parent.bottom; anchors.bottomMargin: 6
                Text { text: w.has ? String(w.now.sky).toUpperCase() : "NO DATA"; color: Theme.primary; font.family: Style.fonts.label; font.pixelSize: 10; font.letterSpacing: 2 }
                Text { text: w.has ? "FEELS " + w.now.feels_like_c + "° · " + w.now.wind_kmh + " KM/H" : ""; color: Theme.dim; font.family: Style.fonts.body; font.pixelSize: 9 }
            }
        }
        Text { text: "TODAY     " + w.line(w.wx.today); color: Theme.textSoft; font.family: Style.fonts.body; font.pixelSize: 10 }
        Text { text: "TOMORROW  " + w.line(w.wx.tomorrow); color: Theme.faint; font.family: Style.fonts.body; font.pixelSize: 10 }
    }
}
