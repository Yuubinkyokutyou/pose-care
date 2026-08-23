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
    focusPolicy: Qt.StrongFocus
    opacity: enabled ? 1 : 0.55
    Accessible.name: text

    contentItem: Text {
        id: label
        text: control.text
        color: control.accent ? control.theme.inkOnAccent
              : control.danger ? control.theme.danger
              : control.selected ? control.theme.signal
              : control.theme.text
        font.family: control.theme.bodyFont
        font.pixelSize: 13
        font.weight: Font.DemiBold
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    background: Rectangle {
        radius: 10
        color: control.accent
               ? (control.down ? control.theme.signalPressed : control.hovered ? control.theme.signalHover : control.theme.signal)
               : control.quiet
                 ? (control.selected ? control.theme.surfaceHigh : control.hovered ? control.theme.surface : "transparent")
                 : (control.down ? control.theme.surfacePressed : control.hovered ? control.theme.surfaceHover : control.theme.surfaceHigh)
        border.width: control.activeFocus ? 2 : (control.accent || control.quiet ? 0 : 1)
        border.color: control.activeFocus
                      ? (control.accent ? control.theme.text : control.theme.signal)
                      : control.theme.line
    }
}
