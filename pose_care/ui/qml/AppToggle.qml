import QtQuick
import QtQuick.Controls

Switch {
    id: control
    property var theme
    property string label: ""

    text: label
    spacing: 10
    hoverEnabled: true
    leftPadding: 0
    rightPadding: 0

    indicator: Rectangle {
        implicitWidth: 42
        implicitHeight: 23
        x: control.width - width
        y: (control.height - height) / 2
        radius: height / 2
        color: control.checked ? theme.signal : theme.control
        border.color: control.activeFocus ? theme.signalHover : control.checked ? theme.signal : theme.controlLine

        Rectangle {
            width: 17
            height: 17
            radius: 9
            y: 3
            x: control.checked ? parent.width - width - 3 : 3
            color: control.checked ? theme.inkOnAccent : theme.text
            Behavior on x { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
        }
    }

    contentItem: Text {
        text: control.text
        color: theme.text
        font.family: theme.bodyFont
        font.pixelSize: 13
        verticalAlignment: Text.AlignVCenter
        rightPadding: control.indicator.width + control.spacing
    }
}
