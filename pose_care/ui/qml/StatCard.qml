import QtQuick

Card {
    id: root
    property string label: ""
    property string value: "—"
    property string detail: ""
    property color accentColor: theme.signal

    implicitHeight: 108

    Rectangle {
        width: 3
        height: 38
        radius: 2
        color: root.accentColor
        anchors.left: parent.left
        anchors.leftMargin: 16
        anchors.verticalCenter: parent.verticalCenter
    }

    Column {
        anchors.left: parent.left
        anchors.leftMargin: 31
        anchors.right: parent.right
        anchors.rightMargin: 14
        anchors.verticalCenter: parent.verticalCenter
        spacing: 3

        Text {
            text: root.label
            color: theme.muted
            font.family: theme.bodyFont
            font.pixelSize: 11
        }
        Text {
            text: root.value
            color: root.accentColor
            font.family: theme.dataFont
            font.pixelSize: 23
            font.weight: Font.Bold
            elide: Text.ElideRight
            width: parent.width
        }
        Text {
            text: root.detail
            color: theme.muted
            font.family: theme.bodyFont
            font.pixelSize: 10
            elide: Text.ElideRight
            width: parent.width
        }
    }
}
