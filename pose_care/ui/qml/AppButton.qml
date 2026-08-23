import QtQuick
import QtQuick.Controls

Button {
    id: control
    property var theme
    property bool accent: false
    property bool danger: false
    property bool quiet: false
    property bool selected: false

    implicitHeight: 40
    implicitWidth: Math.max(88, label.implicitWidth + 30)
    padding: 0
    hoverEnabled: true

    contentItem: Text {
        id: label
        text: control.text
        color: control.accent ? theme.inkOnAccent
              : control.danger ? theme.danger
              : control.selected ? theme.signal
              : theme.text
        font.family: theme.bodyFont
        font.pixelSize: 13
        font.weight: Font.DemiBold
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    background: Rectangle {
        radius: 10
        color: control.accent
               ? (control.down ? theme.signalPressed : control.hovered ? theme.signalHover : theme.signal)
               : control.quiet
                 ? (control.selected ? theme.surfaceHigh : control.hovered ? theme.surface : "transparent")
                 : (control.down ? theme.surfacePressed : control.hovered ? theme.surfaceHover : theme.surfaceHigh)
        border.width: control.accent || control.quiet ? 0 : 1
        border.color: control.activeFocus ? theme.signal : theme.line
    }
}
