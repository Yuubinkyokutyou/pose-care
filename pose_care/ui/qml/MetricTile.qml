import QtQuick

Rectangle {
    id: root
    property var theme
    property string label: ""
    property string value: "—"

    implicitHeight: 78
    radius: 14
    color: theme.surfaceInset
    border.color: theme.lineSoft
    border.width: 1
    antialiasing: true

    Column {
        anchors.fill: parent
        anchors.leftMargin: 14
        anchors.rightMargin: 14
        anchors.topMargin: 12
        anchors.bottomMargin: 12
        spacing: 6

        Text {
            width: parent.width
            text: root.label
            color: root.theme.muted
            font.family: root.theme.bodyFont
            font.pixelSize: 11
            font.weight: Font.Medium
            elide: Text.ElideRight
        }
        Text {
            width: parent.width
            text: root.value
            color: root.theme.text
            font.family: root.theme.dataFont
            font.pixelSize: 19
            font.weight: Font.DemiBold
            elide: Text.ElideRight
        }
    }
}
