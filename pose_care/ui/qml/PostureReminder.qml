import QtQuick
import QtQuick.Window

Window {
    id: reminder
    width: 320
    height: 96
    visible: false
    color: "transparent"
    flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
           | Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput

    Rectangle {
        anchors.fill: parent
        anchors.margins: 3
        radius: 16
        color: "#FBFDFC"
        border.width: 1
        border.color: "#D9B5AF"

        Rectangle {
            x: 0
            y: 12
            width: 4
            height: parent.height - 24
            radius: 2
            color: "#B94D49"
        }

        Text {
            x: 21
            y: 15
            text: "姿勢を確認してください"
            color: "#7B302D"
            font.family: "Yu Gothic UI"
            font.pixelSize: 15
            font.weight: Font.DemiBold
        }

        Text {
            x: 21
            y: 45
            width: parent.width - 42
            text: "「" + controller.reminderProfileName + "」に近い状態です。座り直すと消えます。"
            color: "#5F6F66"
            font.family: "Yu Gothic UI"
            font.pixelSize: 11
            elide: Text.ElideRight
        }
    }
}
