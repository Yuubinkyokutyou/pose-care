import QtQuick
import QtQuick.Controls

Button {
    id: control
    property var theme
    property bool accent: false
    property bool danger: false
    property bool quiet: false
    property bool selected: false

    implicitHeight: 42
    implicitWidth: Math.max(92, label.implicitWidth + 32)
    padding: 0
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    opacity: enabled ? 1 : 0.46
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
        radius: 12
        color: control.accent
               ? (control.down ? control.theme.signalPressed : control.hovered ? control.theme.signalHover : control.theme.signal)
               : control.danger
                 ? (control.down ? Qt.alpha(control.theme.danger, 0.14)
                    : control.hovered ? Qt.alpha(control.theme.danger, 0.08)
                    : control.theme.surface)
               : control.quiet
                 ? (control.down ? control.theme.surfacePressed
                    : control.selected ? control.theme.surfaceHigh
                    : control.hovered ? control.theme.surfaceHover : "transparent")
                 : (control.down ? control.theme.surfacePressed : control.hovered ? control.theme.surfaceHover : control.theme.surfaceHigh)
        border.width: control.visualFocus ? 2
                      : control.quiet && !control.selected ? 0 : 1
        border.color: control.visualFocus
                      ? (control.accent ? control.theme.inkOnAccent : control.theme.signal)
                      : control.danger ? Qt.alpha(control.theme.danger, 0.34)
                      : control.selected ? Qt.alpha(control.theme.signal, 0.34)
                      : control.theme.line
        antialiasing: true

        Behavior on color {
            ColorAnimation { duration: 90 }
        }
    }
}
