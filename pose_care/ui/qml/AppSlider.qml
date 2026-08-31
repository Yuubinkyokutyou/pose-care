import QtQuick
import QtQuick.Controls

Slider {
    id: control
    property var theme

    implicitHeight: 34
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus

    background: Rectangle {
        x: control.leftPadding
        y: control.topPadding + control.availableHeight / 2 - height / 2
        implicitWidth: 200
        implicitHeight: 6
        width: control.availableWidth
        height: implicitHeight
        radius: 3
        color: control.theme.control
        border.width: 1
        border.color: control.theme.lineSoft

        Rectangle {
            width: control.visualPosition * parent.width
            height: parent.height
            radius: 3
            color: control.theme.signal
        }
    }

    handle: Rectangle {
        x: control.leftPadding + control.visualPosition * (control.availableWidth - width)
        y: control.topPadding + control.availableHeight / 2 - height / 2
        implicitWidth: 20
        implicitHeight: 20
        radius: width / 2
        color: control.pressed ? control.theme.surfacePressed
               : control.hovered ? control.theme.surfaceHover : control.theme.surface
        border.width: 2
        border.color: control.theme.signal
        antialiasing: true

        Rectangle {
            anchors.fill: parent
            anchors.margins: -4
            radius: width / 2
            color: "transparent"
            border.width: 2
            border.color: Qt.alpha(control.theme.signal, 0.38)
            visible: control.visualFocus
        }
    }
}
