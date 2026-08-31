pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts

Card {
    id: card

    required property var profiles
    required property string title
    required property string description
    required property string emptyText
    property string addLabel: "姿勢を追加"
    property color accentColor: theme.signal

    signal addRequested()
    signal deleteRequested(string profileId, string profileName)

    implicitHeight: content.implicitHeight + 36

    ColumnLayout {
        id: content
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 18
        spacing: 12

        RowLayout {
            Layout.fillWidth: true
            spacing: 12

            Column {
                Layout.fillWidth: true
                spacing: 3
                Text {
                    width: parent.width
                    text: card.title
                    color: card.theme.text
                    font.family: card.theme.displayFont
                    font.pixelSize: 16
                    font.weight: Font.DemiBold
                    wrapMode: Text.WordWrap
                }
                Text {
                    width: parent.width
                    text: card.description
                    color: card.theme.muted
                    font.family: card.theme.bodyFont
                    font.pixelSize: 10
                    lineHeight: 1.25
                    wrapMode: Text.WordWrap
                }
            }

            AppButton {
                theme: card.theme
                text: card.addLabel
                accent: true
                onClicked: card.addRequested()
            }
        }

        Rectangle {
            visible: card.profiles.length === 0
            Layout.fillWidth: true
            Layout.preferredHeight: 58
            radius: 12
            color: card.theme.surfaceInset

            Row {
                anchors.centerIn: parent
                spacing: 8
                Rectangle {
                    width: 7
                    height: 7
                    radius: 4
                    color: card.accentColor
                    opacity: 0.75
                    anchors.verticalCenter: parent.verticalCenter
                }
                Text {
                    text: card.emptyText
                    color: card.theme.muted
                    font.family: card.theme.bodyFont
                    font.pixelSize: 10
                }
            }
        }

        Repeater {
            model: card.profiles

            Rectangle {
                id: profileRow
                required property var modelData
                Layout.fillWidth: true
                Layout.preferredHeight: 64
                radius: 12
                color: card.theme.surfaceInset
                border.width: 1
                border.color: card.theme.lineSoft

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 13
                    anchors.rightMargin: 9
                    spacing: 9

                    Rectangle {
                        Layout.preferredWidth: 3
                        Layout.preferredHeight: 30
                        radius: 2
                        color: card.accentColor
                    }
                    Column {
                        Layout.fillWidth: true
                        spacing: 2
                        Text {
                            width: parent.width
                            text: profileRow.modelData.name
                            color: card.theme.text
                            font.family: card.theme.bodyFont
                            font.pixelSize: 12
                            font.weight: Font.DemiBold
                            elide: Text.ElideRight
                        }
                        Text {
                            width: parent.width
                            text: profileRow.modelData.detail
                            color: card.theme.muted
                            font.family: card.theme.bodyFont
                            font.pixelSize: 9
                            elide: Text.ElideRight
                        }
                    }
                    AppButton {
                        theme: card.theme
                        text: "削除"
                        danger: true
                        quiet: true
                        Accessible.description: profileRow.modelData.name + "を削除します"
                        onClicked: card.deleteRequested(
                            profileRow.modelData.id,
                            profileRow.modelData.name
                        )
                    }
                }
            }
        }
    }
}
