// Button that needs two clicks (for log out / restart / shut down).
import QtQuick

SmallButton {
    id: cb
    property string label: ""
    property bool armed: false
    signal confirmed()

    text: armed ? "CONFIRM?" : label
    active: armed
    onClicked: {
        if (armed) { armed = false; cb.confirmed(); }
        else { armed = true; disarm.restart(); }
    }
    Timer { id: disarm; interval: 3000; onTriggered: cb.armed = false }
}
