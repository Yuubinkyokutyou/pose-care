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

    implicitWidth: 132
    implicitHeight: 150

    Rectangle {
        id: signalPanel
        width: 112
        height: 116
        radius: 16
        color: root.theme.surfaceInset
        border.width: 1
        border.color: root.stateKind === "warning" || root.stateKind === "bad"
                      ? Qt.alpha(root.stateColor, 0.38) : root.theme.lineSoft
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: parent.top
        antialiasing: true

        Rectangle {
            id: rail
            width: 4
            height: 64
            radius: 2
            color: root.theme.line
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: parent.top
            anchors.topMargin: 30

            Rectangle {
                width: parent.width
                height: root.stateKind === "warning" ? parent.height * root.progress : parent.height
                anchors.bottom: parent.bottom
                radius: 2
                color: root.stateColor
                opacity: root.stateKind === "starting" || root.stateKind === "paused"
                         || root.stateKind === "idle" || root.stateKind === "locked" ? 0.42 : 1
                Behavior on height { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
            }
        }

        Rectangle {
            width: 15
            height: 15
            radius: width / 2
            color: root.stateColor
            anchors.horizontalCenter: parent.horizontalCenter
            y: 14
            opacity: root.stateKind === "starting" ? 0.54 : 1
            scale: root.stateKind === "warning" ? 1.12 : 1.0
            Behavior on scale {
                NumberAnimation { duration: 180; easing.type: Easing.OutCubic }
            }
        }

        Rectangle {
            width: 76
            height: 3
            radius: 2
            color: root.stateColor
            anchors.horizontalCenter: parent.horizontalCenter
            y: 55
            opacity: 0.86
            rotation: root.stateKind === "bad" ? -8 : root.stateKind === "warning" ? -3 : 0
            Behavior on rotation { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }
        }

        Rectangle {
            width: 10
            height: 10
            radius: width / 2
            color: root.stateColor
            anchors.horizontalCenter: parent.horizontalCenter
            y: 94
        }
    }

    Rectangle {
        id: stateBadge
        width: stateLabel.implicitWidth + 24
        height: 26
        radius: 13
        color: Qt.alpha(root.stateColor, 0.10)
        border.width: 1
        border.color: Qt.alpha(root.stateColor, 0.26)
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
    }

    Text {
        id: stateLabel
        anchors.centerIn: stateBadge
        text: root.stateKind === "normal" ? "通知対象外"
              : root.stateKind === "good" ? "良好"
              : root.stateKind === "warning" ? "確認中"
              : root.stateKind === "bad" ? "悪い姿勢"
              : root.stateKind === "paused" ? "一時停止"
              : root.stateKind === "idle" || root.stateKind === "locked"
              ? "カメラ停止" : "解析中"
        color: root.stateColor
        font.family: root.theme.bodyFont
        font.pixelSize: 10
        font.weight: Font.DemiBold
    }
}
