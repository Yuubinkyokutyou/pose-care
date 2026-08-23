import QtQuick

Rectangle {
    id: root
    property var theme
    property string label: ""
    property string value: "—"

    implicitHeight: 76
    radius: 12
    color: theme.surfaceInset
    border.color: theme.lineSoft
    border.width: 1

    Column {
        anchors.fill: parent
        anchors.margins: 13
        spacing: 5

        Text {
            text: root.label
            color: theme.muted
            font.family: theme.bodyFont
            font.pixelSize: 11
        }
        Text {
            text: root.value
            color: theme.text
            font.family: theme.dataFont
            font.pixelSize: 18
            font.weight: Font.DemiBold
        }
    }
}
