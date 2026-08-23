import QtQuick

Rectangle {
    id: root
    property var theme
    property color fillColor: theme.surface
    property color strokeColor: theme.line
    radius: 18
    color: fillColor
    border.color: strokeColor
    border.width: 1
}
