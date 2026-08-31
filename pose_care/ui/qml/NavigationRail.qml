pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts

Rectangle {
    id: rail

    required property var theme
    property int currentPage: 0
    signal pageRequested(int page)

    implicitWidth: 168
    color: theme.nav

    Rectangle {
        anchors.right: parent.right
        width: 1
        height: parent.height
        color: rail.theme.lineSoft
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.leftMargin: 17
        anchors.rightMargin: 17
        anchors.topMargin: 22
        anchors.bottomMargin: 18
        spacing: 0

        RowLayout {
            Layout.fillWidth: true
            spacing: 10

            Item {
                Layout.preferredWidth: 29
                Layout.preferredHeight: 44

                Rectangle {
                    width: 2
                    height: 36
                    radius: 1
                    color: rail.theme.signal
                    anchors.centerIn: parent
                }
                Repeater {
                    model: [8, 20, 32]
                    Rectangle {
                        required property int modelData
                        width: modelData === 20 ? 9 : 6
                        height: width
                        radius: width / 2
                        color: modelData === 20 ? rail.theme.surface : rail.theme.signal
                        border.width: modelData === 20 ? 2 : 0
                        border.color: rail.theme.signal
                        anchors.horizontalCenter: parent.horizontalCenter
                        y: modelData - height / 2
                    }
                }
            }

            Column {
                Layout.fillWidth: true
                spacing: -1
                Text {
                    text: "PoseCare"
                    color: rail.theme.text
                    font.family: rail.theme.displayFont
                    font.pixelSize: 19
                    font.weight: Font.Bold
                    font.letterSpacing: -0.3
                }
            }
        }

        Item { Layout.preferredHeight: 28 }

        NavItem {
            Layout.fillWidth: true
            theme: rail.theme
            text: "モニター"
            symbol: "●"
            selected: rail.currentPage === 0
            onClicked: rail.pageRequested(0)
        }
        Item { Layout.preferredHeight: 5 }
        NavItem {
            Layout.fillWidth: true
            theme: rail.theme
            text: "統計"
            symbol: "▥"
            selected: rail.currentPage === 1
            onClicked: rail.pageRequested(1)
        }
        Item { Layout.preferredHeight: 5 }
        NavItem {
            Layout.fillWidth: true
            theme: rail.theme
            text: "設定"
            symbol: "≡"
            selected: rail.currentPage === 2
            onClicked: rail.pageRequested(2)
        }

        Item { Layout.fillHeight: true }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 82
            radius: 15
            color: rail.theme.surface
            border.color: rail.theme.lineSoft

            Column {
                anchors.fill: parent
                anchors.margins: 13
                spacing: 7

                Row {
                    spacing: 7
                    Rectangle {
                        width: 7
                        height: 7
                        radius: 4
                        color: rail.theme.signal
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    Text {
                        text: "ローカル保存"
                        color: rail.theme.signal
                        font.family: rail.theme.dataFont
                        font.pixelSize: 9
                        font.weight: Font.Bold
                        font.letterSpacing: 0.7
                    }
                }
                Text {
                    width: parent.width
                    text: "映像・骨格は保存しません\n履歴はこのPCに保存します"
                    color: rail.theme.muted
                    font.family: rail.theme.bodyFont
                    font.pixelSize: 10
                    lineHeight: 1.35
                    wrapMode: Text.WordWrap
                }
            }
        }
    }
}
