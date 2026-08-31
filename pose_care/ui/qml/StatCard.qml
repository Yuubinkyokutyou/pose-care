import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Card {
    id: root
    property string label: ""
    property string value: "—"
    property string detail: ""
    property string helpText: ""
    property color accentColor: theme.signal

    implicitHeight: 116
    activeFocusOnTab: root.helpText.length > 0
    fillColor: (cardHover.hovered || root.activeFocus) && root.helpText.length > 0
               ? theme.surfaceHigh : theme.surface
    strokeColor: (cardHover.hovered || root.activeFocus) && root.helpText.length > 0
                 ? Qt.alpha(root.accentColor, 0.42) : theme.line
    Accessible.name: root.label + " " + root.value
    Accessible.description: root.helpText.length > 0 ? root.helpText : root.detail

    HoverHandler {
        id: cardHover
        enabled: root.helpText.length > 0
        acceptedDevices: PointerDevice.Mouse | PointerDevice.TouchPad
    }

    ToolTip.visible: (cardHover.hovered || root.activeFocus) && root.helpText.length > 0
    ToolTip.text: root.helpText
    ToolTip.delay: 420
    ToolTip.timeout: 8000

    ColumnLayout {
        anchors.fill: parent
        anchors.leftMargin: 16
        anchors.rightMargin: 14
        anchors.topMargin: 13
        anchors.bottomMargin: 13
        spacing: 3

        RowLayout {
            Layout.fillWidth: true
            spacing: 7

            Rectangle {
                Layout.preferredWidth: 7
                Layout.preferredHeight: 7
                radius: width / 2
                color: root.accentColor
            }
            Text {
                Layout.fillWidth: true
                text: root.label
                color: root.theme.muted
                font.family: root.theme.bodyFont
                font.pixelSize: 11
                font.weight: Font.Medium
                elide: Text.ElideRight
            }
            Rectangle {
                visible: root.helpText.length > 0
                Layout.preferredWidth: 17
                Layout.preferredHeight: 17
                radius: width / 2
                color: cardHover.hovered || root.activeFocus
                       ? Qt.alpha(root.accentColor, 0.12) : root.theme.surfaceInset
                border.width: 1
                border.color: cardHover.hovered || root.activeFocus
                              ? Qt.alpha(root.accentColor, 0.45) : root.theme.lineSoft

                Text {
                    anchors.centerIn: parent
                    text: "i"
                    color: cardHover.hovered || root.activeFocus
                           ? root.accentColor : root.theme.muted
                    font.family: root.theme.dataFont
                    font.pixelSize: 10
                    font.weight: Font.Bold
                }
            }
        }
        Text {
            Layout.fillWidth: true
            text: root.value
            color: root.theme.text
            font.family: root.theme.dataFont
            font.pixelSize: 24
            font.weight: Font.Bold
            elide: Text.ElideRight
        }
        Text {
            visible: root.detail.length > 0
            Layout.fillWidth: true
            text: root.detail
            color: root.theme.muted
            font.family: root.theme.bodyFont
            font.pixelSize: 10
            elide: Text.ElideRight
        }
    }
}
