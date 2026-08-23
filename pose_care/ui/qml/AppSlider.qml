import QtQuick
import QtQuick.Controls

Slider {
    id: control
    property var theme

    implicitHeight: 28
    hoverEnabled: true

    background: Rectangle {
        x: control.leftPadding
        y: control.topPadding + control.availableHeight / 2 - height / 2
        implicitWidth: 200
        implicitHeight: 4
        width: control.availableWidth
        height: implicitHeight
        radius: 2
        color: control.theme.control

        Rectangle {
            width: control.visualPosition * parent.width
            height: parent.height
            radius: 2
            color: control.theme.signal
        }
    }

    handle: Rectangle {
        x: control.leftPadding + control.visualPosition * (control.availableWidth - width)
        y: control.topPadding + control.availableHeight / 2 - height / 2
        implicitWidth: 17
        implicitHeight: 17
        radius: 9
        color: control.pressed ? control.theme.signalHover : control.theme.text
        border.width: 2
        border.color: control.theme.signal
    }
}
