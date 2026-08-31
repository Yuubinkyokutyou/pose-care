import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Card {
    id: card
    objectName: "updateCard"

    required property var updateController

    implicitHeight: content.implicitHeight + 40

    readonly property string updateState: updateController.updateState
    readonly property bool busy: updateState === "checking" || updateState === "downloading"
    readonly property bool hasLatestVersion: updateController.latestVersion.length > 0

    function displayVersion(version) {
        if (!version || version.length === 0)
            return "--"
        return version.charAt(0).toLowerCase() === "v" ? version : "v" + version
    }

    function compactVersion(version) {
        const fullVersion = displayVersion(version)
        const buildTag = /^(v\d+\.\d+\.\d+)-build\.(\d+)\.(\d+)$/.exec(fullVersion)
        return buildTag
                ? buildTag[1] + " · b" + buildTag[2] + "." + buildTag[3]
                : fullVersion
    }

    function actionText() {
        switch (updateState) {
        case "checking":
            return "確認中…"
        case "available":
            return compactVersion(updateController.latestVersion) + "をダウンロード"
        case "downloading":
            return "ダウンロード中…"
        case "ready":
            return "再起動して更新"
        case "upToDate":
            return "もう一度確認"
        case "error":
            return "再確認"
        default:
            return "更新を確認"
        }
    }

    function fallbackStatus() {
        switch (updateState) {
        case "checking":
            return "GitHub Releasesを確認しています"
        case "available":
            return "新しいバージョンを利用できます"
        case "downloading":
            return "最新版をダウンロードしています"
        case "ready":
            return "ダウンロード完了。再起動すると更新されます"
        case "upToDate":
            return "最新バージョンです"
        case "error":
            return "更新を確認できませんでした。通信環境を確認してください"
        default:
            return "更新の確認は手動で行います"
        }
    }

    function statusColor() {
        switch (updateState) {
        case "error":
            return theme.danger
        case "checking":
        case "downloading":
            return theme.blue
        case "available":
        case "ready":
        case "upToDate":
            return theme.signal
        default:
            return theme.muted
        }
    }

    ColumnLayout {
        id: content
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 20
        spacing: 14

        RowLayout {
            Layout.fillWidth: true
            spacing: 18

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 3

                Text {
                    Layout.fillWidth: true
                    text: "更新"
                    color: card.theme.text
                    font.family: card.theme.displayFont
                    font.pixelSize: 16
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }
            }

            AppButton {
                id: updateActionButton
                objectName: "updateActionButton"
                theme: card.theme
                text: card.actionText()
                accent: card.updateState === "available" || card.updateState === "ready"
                enabled: !card.busy
                Accessible.name: text
                Accessible.description: card.updateState === "ready"
                                        ? "PoseCareを終了し、ダウンロード済みの更新を適用して再起動します"
                                        : "PoseCareの最新版を確認またはダウンロードします"
                onClicked: {
                    if (card.updateState === "available" || card.updateState === "ready")
                        card.updateController.installUpdate()
                    else
                        card.updateController.checkForUpdates()
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 82
            radius: 14
            color: card.theme.surfaceInset
            border.width: 1
            border.color: card.theme.lineSoft
            antialiasing: true

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 17
                anchors.rightMargin: 17
                spacing: 14

                ColumnLayout {
                    Layout.preferredWidth: 160
                    Layout.minimumWidth: 120
                    spacing: 3

                    Text {
                        Layout.fillWidth: true
                        text: "現在のバージョン"
                        color: card.theme.muted
                        font.family: card.theme.bodyFont
                        font.pixelSize: 9
                        font.weight: Font.Medium
                        elide: Text.ElideRight
                    }
                    Text {
                        id: currentVersionValue
                        objectName: "currentVersionValue"
                        Layout.fillWidth: true
                        text: card.compactVersion(card.updateController.appVersion)
                        color: card.theme.text
                        font.family: card.theme.dataFont
                        font.pixelSize: 13
                        font.weight: Font.DemiBold
                        elide: Text.ElideRight
                        Accessible.name: "現在のバージョン "
                                         + card.displayVersion(card.updateController.appVersion)
                    }
                }

                Item {
                    Layout.fillWidth: true
                    Layout.minimumWidth: 56
                    Layout.preferredHeight: 26

                    Rectangle {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        height: 1
                        color: card.theme.line
                    }
                    Rectangle {
                        anchors.left: parent.left
                        anchors.verticalCenter: parent.verticalCenter
                        width: card.hasLatestVersion ? parent.width : 0
                        height: 2
                        radius: 1
                        color: card.statusColor()
                    }
                    Rectangle {
                        width: 24
                        height: 24
                        radius: 12
                        anchors.centerIn: parent
                        color: card.theme.surface
                        border.width: 1
                        border.color: card.theme.line

                        Text {
                            anchors.centerIn: parent
                            text: "→"
                            color: card.statusColor()
                            font.family: card.theme.dataFont
                            font.pixelSize: 13
                            font.weight: Font.DemiBold
                        }
                    }
                }

                ColumnLayout {
                    Layout.preferredWidth: 160
                    Layout.minimumWidth: 120
                    spacing: 3

                    Text {
                        Layout.fillWidth: true
                        text: "利用できるバージョン"
                        color: card.theme.muted
                        font.family: card.theme.bodyFont
                        font.pixelSize: 9
                        font.weight: Font.Medium
                        elide: Text.ElideRight
                    }
                    Text {
                        objectName: "latestVersionValue"
                        Layout.fillWidth: true
                        text: card.hasLatestVersion
                              ? card.compactVersion(card.updateController.latestVersion)
                              : "未確認"
                        color: card.hasLatestVersion ? card.statusColor() : card.theme.muted
                        font.family: card.theme.dataFont
                        font.pixelSize: 13
                        font.weight: Font.DemiBold
                        elide: Text.ElideRight
                        Accessible.name: "利用可能なバージョン "
                                         + (card.hasLatestVersion
                                            ? card.displayVersion(card.updateController.latestVersion)
                                            : "未確認")
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 40
            radius: 12
            color: card.theme.surfaceInset
            border.width: 1
            border.color: card.updateState === "error"
                          ? Qt.alpha(card.theme.danger, 0.30) : card.theme.lineSoft

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 13
                anchors.rightMargin: 13
                spacing: 9

                Rectangle {
                    Layout.preferredWidth: 7
                    Layout.preferredHeight: 7
                    radius: width / 2
                    color: card.statusColor()
                }
                Text {
                    id: updateStatusText
                    objectName: "updateStatusText"
                    Layout.fillWidth: true
                    text: card.updateController.updateStatus.length > 0
                          ? card.updateController.updateStatus
                          : card.fallbackStatus()
                    color: card.updateState === "error" ? card.theme.danger : card.theme.muted
                    font.family: card.theme.bodyFont
                    font.pixelSize: 10
                    elide: Text.ElideRight
                    Accessible.name: text
                }
                Text {
                    visible: card.updateState === "downloading"
                    text: Math.round(card.updateController.updateProgress * 100) + "%"
                    color: card.theme.blue
                    font.family: card.theme.dataFont
                    font.pixelSize: 10
                    font.weight: Font.DemiBold
                }
            }
        }

        ProgressBar {
            id: updateProgressBar
            objectName: "updateProgressBar"
            Layout.fillWidth: true
            Layout.preferredHeight: visible ? 6 : 0
            visible: card.updateState === "downloading"
            from: 0
            to: 1
            value: card.updateController.updateProgress
            padding: 0
            Accessible.name: "更新のダウンロード進捗"

            background: Rectangle {
                implicitHeight: 6
                radius: 3
                color: card.theme.lineSoft
            }
            contentItem: Item {
                implicitHeight: 6
                Rectangle {
                    width: parent.width * updateProgressBar.visualPosition
                    height: parent.height
                    radius: 3
                    color: card.theme.blue
                }
            }
        }
    }
}
