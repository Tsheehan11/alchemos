// The skin's lock scene (Skin.sceneUrl: the doors that shut over every screen and, captured, the
// lock screen's background). SecurityDoors drives it; scenes share these properties. Anything
// extra a scene offers (flare: the fingerprint flash) is passed only if it has it.
import QtQuick

Item {
    id: wrap
    property real doorP: 1
    property real emblemOpacity: 1
    property bool isMain: true
    property string message: ""
    property string submessage: ""
    property real msgP: 0
    property real spin: 0
    property real flare: 0
    readonly property bool painted: loader.item ? loader.item.painted === true : false

    Loader {
        id: loader
        anchors.fill: parent
        source: Skin.sceneUrl
        onLoaded: {
            for (const k of ["doorP", "emblemOpacity", "isMain", "message", "submessage", "msgP", "spin", "flare"])
                if (k in item) item[k] = Qt.binding(() => wrap[k]);
        }
    }
}
