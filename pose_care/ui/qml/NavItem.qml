import QtQuick
import QtQuick.Controls

Button {
    id: control

    required property var theme
    property string symbol: ""
    property bool selected: false

    implicitWidth: 132
    implicitHeight: 48
    padding: 0
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus

    Accessible.name: text
    Accessible.description: selected ? "現在のページ" : "このページを開く"

    contentItem: Row {
        leftPadding: 13
        spacing: 11

        Rectangle {
            width: 26
            height: 26
            radius: 9
            anchors.verticalCenter: parent.verticalCenter
            color: control.selected
                   ? control.theme.signal
                   : control.hovered ? control.theme.surfaceHigh : "transparent"
            border.width: control.selected ? 0 : 1
            border.color: control.theme.line

            Text {
                anchors.centerIn: parent
                text: control.symbol
                color: control.selected ? control.theme.inkOnAccent : control.theme.muted
                font.family: control.theme.dataFont
                font.pixelSize: 12
                font.weight: Font.Bold
            }
        }

        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: control.text
            color: control.selected ? control.theme.text : control.theme.muted
            font.family: control.theme.bodyFont
            font.pixelSize: 13
            font.weight: control.selected ? Font.DemiBold : Font.Medium
        }
    }

    background: Rectangle {
        radius: 13
        color: control.selected
               ? control.theme.surface
               : control.hovered ? control.theme.surfaceHigh : "transparent"
        border.width: control.activeFocus ? 2 : (control.selected ? 1 : 0)
        border.color: control.activeFocus ? control.theme.signal : control.theme.lineSoft

        Rectangle {
            visible: control.selected
            width: 3
            height: 22
            radius: 2
            anchors.left: parent.left
            anchors.leftMargin: -1
            anchors.verticalCenter: parent.verticalCenter
            color: control.theme.signal
        }
    }
}
