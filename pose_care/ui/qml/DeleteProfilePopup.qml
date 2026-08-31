import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Popup {
    id: popup

    required property var controller
    required property var theme
    required property var hostWindow
    property string profileId: ""
    property string profileName: ""

    width: Math.min(410, hostWindow.width - 48)
    height: 210
    x: (hostWindow.width - width) / 2
    y: (hostWindow.height - height) / 2
    modal: true
    focus: true
    padding: 0

    background: Rectangle {
        color: popup.theme.surface
        radius: 18
        border.color: popup.theme.line
    }

    contentItem: ColumnLayout {
        anchors.fill: parent
        anchors.margins: 22
        spacing: 10

        Text {
            text: "この姿勢を削除しますか？"
            color: popup.theme.text
            font.family: popup.theme.displayFont
            font.pixelSize: 19
            font.weight: Font.Bold
        }
        Text {
            Layout.fillWidth: true
            Layout.fillHeight: true
            text: "「" + popup.profileName + "」の特徴データをこのPCから削除します。"
            color: popup.theme.muted
            font.family: popup.theme.bodyFont
            font.pixelSize: 11
            wrapMode: Text.WordWrap
        }
        RowLayout {
            Layout.fillWidth: true
            Item { Layout.fillWidth: true }
            AppButton {
                theme: popup.theme
                text: "残す"
                onClicked: popup.close()
            }
            AppButton {
                theme: popup.theme
                text: "削除する"
                danger: true
                onClicked: {
                    popup.controller.deleteProfile(popup.profileId)
                    popup.close()
                }
            }
        }
    }
}
