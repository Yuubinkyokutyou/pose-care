import QtQuick

Item {
    id: root
    property var theme
    property string stateKind: "starting"
    property real progress: 0
    property color stateColor: stateKind === "good" || stateKind === "normal" ? theme.signal
                              : stateKind === "warning" ? theme.amber
                              : stateKind === "bad" ? theme.danger
                              : theme.muted

    implicitWidth: 124
    implicitHeight: 150

    Rectangle {
        id: rail
        width: 3
        height: 108
        radius: 2
        color: theme.line
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: parent.top
        anchors.topMargin: 19

        Rectangle {
            width: parent.width
            height: root.stateKind === "warning" ? parent.height * root.progress : parent.height
            anchors.bottom: parent.bottom
            radius: 2
            color: root.stateColor
            opacity: root.stateKind === "starting" || root.stateKind === "paused"
                     || root.stateKind === "idle"
                     || root.stateKind === "locked" ? 0.38 : 1
            Behavior on height { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
        }
    }

    Rectangle {
        width: 14
        height: 14
        radius: 7
        color: root.stateColor
        anchors.horizontalCenter: parent.horizontalCenter
        y: 10
        opacity: root.stateKind === "starting" ? 0.5 : 1

        SequentialAnimation on scale {
            running: root.stateKind === "warning"
            loops: Animation.Infinite
            NumberAnimation { to: 1.35; duration: 520; easing.type: Easing.InOutSine }
            NumberAnimation { to: 1.0; duration: 520; easing.type: Easing.InOutSine }
        }
    }

    Rectangle {
        width: 88
        height: 2
        radius: 1
        color: root.stateColor
        anchors.horizontalCenter: parent.horizontalCenter
        y: 69
        opacity: 0.85
        rotation: root.stateKind === "bad" ? -8 : root.stateKind === "warning" ? -3 : 0
        Behavior on rotation { NumberAnimation { duration: 240; easing.type: Easing.OutCubic } }
    }

    Rectangle {
        width: 9
        height: 9
        radius: 5
        color: root.stateColor
        anchors.horizontalCenter: parent.horizontalCenter
        y: 122
    }

    Text {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        text: root.stateKind === "normal" ? "EXCLUDED"
              : root.stateKind === "good" ? "ALIGNED"
              : root.stateKind === "warning" ? "CHECKING"
              : root.stateKind === "bad" ? "RESET"
              : root.stateKind === "paused" ? "PAUSED"
              : root.stateKind === "idle" || root.stateKind === "locked"
              ? "CAMERA OFF" : "SCANNING"
        color: root.stateColor
        font.family: theme.dataFont
        font.pixelSize: 10
        font.weight: Font.Bold
        font.letterSpacing: 1.4
    }
}
