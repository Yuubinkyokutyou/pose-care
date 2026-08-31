import QtQuick
import QtQuick.Controls

Switch {
    id: control
    property var theme
    property string label: ""

    text: label
    implicitHeight: 36
    implicitWidth: labelText.implicitWidth + indicator.width + spacing
    spacing: 12
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    leftPadding: 0
    rightPadding: 0
    Accessible.name: label

    indicator: Rectangle {
        implicitWidth: 44
        implicitHeight: 24
        x: control.width - width
        y: (control.height - height) / 2
        radius: height / 2
        color: control.checked
               ? (control.down ? control.theme.signalPressed
                  : control.hovered ? control.theme.signalHover : control.theme.signal)
               : (control.down ? control.theme.surfacePressed
                  : control.hovered ? control.theme.surfaceHover : control.theme.control)
        border.width: control.visualFocus ? 2 : 1
        border.color: control.visualFocus ? control.theme.signal
                      : control.checked ? control.theme.signal : control.theme.controlLine
        antialiasing: true

        Rectangle {
            width: 18
            height: 18
            radius: width / 2
            y: 3
            x: control.checked ? parent.width - width - 3 : 3
            color: control.checked ? control.theme.inkOnAccent : control.theme.surface
            border.width: control.checked ? 0 : 1
            border.color: control.theme.line
            antialiasing: true
            Behavior on x { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }
        }

        Rectangle {
            anchors.fill: parent
            anchors.margins: -4
            radius: width / 2
            color: "transparent"
            border.width: 2
            border.color: Qt.alpha(control.theme.signal, 0.34)
            visible: control.visualFocus
        }

        Behavior on color { ColorAnimation { duration: 90 } }
    }

    contentItem: Text {
        id: labelText
        text: control.text
        color: control.theme.text
        font.family: control.theme.bodyFont
        font.pixelSize: 13
        verticalAlignment: Text.AlignVCenter
        rightPadding: control.indicator.width + control.spacing
    }
}
