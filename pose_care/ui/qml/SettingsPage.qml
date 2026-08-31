pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

Item {
    id: page
    objectName: "settingsPage"

    required property var controller
    required property var theme
    signal deleteRequested(string profileId, string profileName)

    property int stagedSensitivity: controller.sensitivity
    property real stagedHold: controller.holdSeconds
    property int stagedCooldown: controller.cooldownMinutes
    property bool stagedNotifications: controller.notificationsEnabled
    property int stagedCamera: controller.cameraIndex
    property bool stagedMinimized: controller.startMinimized
    property bool stagedStartup: controller.startupEnabled
    readonly property int gridColumns: settingsScroll.availableWidth >= 820 ? 2 : 1
    property alias scrollFlickable: settingsFlickable
    property alias settingsContent: settingsGrid

    function isDescendantOf(item, ancestor) {
        var current = item
        while (current) {
            if (current === ancestor)
                return true
            current = current.parent
        }
        return false
    }

    function ensureFocusedControlVisible() {
        var window = page.Window.window
        if (!window || !settingsScroll.visible)
            return
        var item = window.activeFocusItem
        if (!item || !isDescendantOf(item, page.settingsContent))
            return

        var position = item.mapToItem(page.settingsContent, 0, 0)
        var itemTop = position.y
        var itemBottom = itemTop + item.height
        var flickable = page.scrollFlickable
        var viewportTop = flickable.contentY
        var viewportHeight = flickable.height
        var margin = 16

        if (itemTop < viewportTop + margin) {
            flickable.contentY = Math.max(0, itemTop - margin)
        } else if (itemBottom > viewportTop + viewportHeight - margin) {
            var maximumY = Math.max(0, flickable.contentHeight - viewportHeight)
            flickable.contentY = Math.min(
                maximumY,
                itemBottom - viewportHeight + margin
            )
        }
    }

    Connections {
        target: page.Window.window
        function onActiveFocusItemChanged() {
            Qt.callLater(page.ensureFocusedControlVisible)
        }
    }

    Connections {
        target: page.controller
        function onSettingsChanged() {
            page.stagedSensitivity = page.controller.sensitivity
            page.stagedHold = page.controller.holdSeconds
            page.stagedCooldown = page.controller.cooldownMinutes
            page.stagedNotifications = page.controller.notificationsEnabled
            page.stagedCamera = page.controller.cameraIndex
            page.stagedMinimized = page.controller.startMinimized
            page.stagedStartup = page.controller.startupEnabled
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.leftMargin: 24
        anchors.rightMargin: 18
        anchors.topMargin: 22
        anchors.bottomMargin: 18
        spacing: 14

        RowLayout {
            Layout.fillWidth: true
            spacing: 14

            Column {
                Layout.fillWidth: true
                spacing: 2
                Text {
                    text: "設定"
                    color: page.theme.text
                    font.family: page.theme.displayFont
                    font.pixelSize: 28
                    font.weight: Font.Bold
                    font.letterSpacing: -0.5
                }
            }

            Text {
                objectName: "saveFeedbackText"
                text: page.controller.saveFeedback
                color: page.controller.saveFeedbackError ? page.theme.danger : page.theme.signal
                font.family: page.theme.bodyFont
                font.pixelSize: 11
                font.weight: Font.DemiBold
            }
            AppButton {
                theme: page.theme
                text: "保存"
                accent: true
                onClicked: page.controller.saveSettings(
                    page.stagedSensitivity,
                    page.stagedHold,
                    page.stagedCooldown,
                    page.stagedNotifications,
                    page.stagedCamera,
                    page.stagedMinimized,
                    page.stagedStartup
                )
            }
        }

        ScrollView {
            id: settingsScroll
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

            contentItem: Flickable {
                id: settingsFlickable
                objectName: "settingsFlickable"
                clip: true
                contentWidth: width
                contentHeight: settingsGrid.implicitHeight
                boundsBehavior: Flickable.StopAtBounds

                GridLayout {
                    id: settingsGrid
                    width: settingsFlickable.width
                    columns: page.gridColumns
                    columnSpacing: 12
                    rowSpacing: 12

                ProfileCard {
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignTop
                    theme: page.theme
                    profiles: page.controller.badProfiles
                    title: "通知対象の姿勢"
                    description: "続けて検知すると通知"
                    emptyText: "登録なし"
                    addLabel: "悪い姿勢を追加"
                    accentColor: page.theme.danger
                    onAddRequested: page.controller.beginRegistration("bad", false)
                    onDeleteRequested: function(profileId, profileName) {
                        page.deleteRequested(profileId, profileName)
                    }
                }

                ProfileCard {
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignTop
                    theme: page.theme
                    profiles: page.controller.normalProfiles
                    title: "通知しない姿勢"
                    description: "検知しても通知しない"
                    emptyText: "登録なし"
                    addLabel: "通知しない姿勢を追加"
                    accentColor: page.theme.signal
                    onAddRequested: page.controller.beginRegistration("normal", false)
                    onDeleteRequested: function(profileId, profileName) {
                        page.deleteRequested(profileId, profileName)
                    }
                }

                Card {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 306
                    Layout.alignment: Qt.AlignTop
                    theme: page.theme

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 18
                        spacing: 13

                        Column {
                            Layout.fillWidth: true
                            spacing: 2
                            Text {
                                text: "検知と通知"
                                color: page.theme.text
                                font.family: page.theme.displayFont
                                font.pixelSize: 16
                                font.weight: Font.DemiBold
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 12
                            Text { Layout.preferredWidth: 120; text: "検知感度"; color: page.theme.text; font.family: page.theme.bodyFont; font.pixelSize: 11 }
                            AppSlider {
                                Layout.fillWidth: true
                                theme: page.theme
                                from: 0; to: 100; stepSize: 1
                                value: page.stagedSensitivity
                                Accessible.name: "検知感度"
                                Accessible.description: "現在 " + Math.round(value) + "%"
                                onMoved: page.stagedSensitivity = Math.round(value)
                            }
                            Text { Layout.preferredWidth: 42; text: page.stagedSensitivity + "%"; color: page.theme.signal; font.family: page.theme.dataFont; font.pixelSize: 11; horizontalAlignment: Text.AlignRight }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 12
                            Text { Layout.preferredWidth: 120; text: "通知まで"; color: page.theme.text; font.family: page.theme.bodyFont; font.pixelSize: 11 }
                            AppSlider {
                                Layout.fillWidth: true
                                theme: page.theme
                                from: 1; to: 30; stepSize: 0.5
                                value: page.stagedHold
                                Accessible.name: "通知までの時間"
                                Accessible.description: "現在 " + value.toFixed(1) + "秒"
                                onMoved: page.stagedHold = value
                            }
                            Text { Layout.preferredWidth: 48; text: page.stagedHold.toFixed(1) + "秒"; color: page.theme.text; font.family: page.theme.dataFont; font.pixelSize: 10; horizontalAlignment: Text.AlignRight }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 12
                            Text { Layout.preferredWidth: 120; text: "通知の間隔"; color: page.theme.text; font.family: page.theme.bodyFont; font.pixelSize: 11 }
                            AppSlider {
                                Layout.fillWidth: true
                                theme: page.theme
                                from: 1; to: 120; stepSize: 1
                                value: page.stagedCooldown
                                Accessible.name: "通知の間隔"
                                Accessible.description: "現在 " + Math.round(value) + "分"
                                onMoved: page.stagedCooldown = Math.round(value)
                            }
                            Text { Layout.preferredWidth: 48; text: page.stagedCooldown + "分"; color: page.theme.text; font.family: page.theme.dataFont; font.pixelSize: 10; horizontalAlignment: Text.AlignRight }
                        }

                        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: page.theme.lineSoft }

                        RowLayout {
                            Layout.fillWidth: true
                            AppToggle {
                                theme: page.theme
                                label: "Windows通知を使う"
                                checked: page.stagedNotifications
                                onToggled: page.stagedNotifications = checked
                            }
                            Item { Layout.fillWidth: true }
                            Text {
                                text: page.controller.notificationFeedback
                                color: page.theme.muted
                                font.family: page.theme.bodyFont
                                font.pixelSize: 9
                            }
                            AppButton {
                                theme: page.theme
                                text: "通知を試す"
                                onClicked: page.controller.sendTestNotification()
                            }
                        }
                    }
                }

                Card {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 248
                    Layout.alignment: Qt.AlignTop
                    theme: page.theme

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 18
                        spacing: 13

                        Column {
                            Layout.fillWidth: true
                            spacing: 2
                            Text {
                                text: "カメラと起動"
                                color: page.theme.text
                                font.family: page.theme.displayFont
                                font.pixelSize: 16
                                font.weight: Font.DemiBold
                            }
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 12
                            Text { Layout.preferredWidth: 120; text: "カメラ番号"; color: page.theme.text; font.family: page.theme.bodyFont; font.pixelSize: 11 }
                            AppSlider {
                                Layout.fillWidth: true
                                theme: page.theme
                                from: 0; to: 9; stepSize: 1
                                value: page.stagedCamera
                                Accessible.name: "カメラ番号"
                                Accessible.description: "現在 " + Math.round(value)
                                onMoved: page.stagedCamera = Math.round(value)
                            }
                            Text { Layout.preferredWidth: 32; text: String(page.stagedCamera); color: page.theme.text; font.family: page.theme.dataFont; font.pixelSize: 11; horizontalAlignment: Text.AlignRight }
                        }

                        Rectangle { Layout.fillWidth: true; Layout.preferredHeight: 1; color: page.theme.lineSoft }

                        AppToggle {
                            objectName: "startupToggle"
                            theme: page.theme
                            label: "Windowsログイン時に起動する"
                            checked: page.stagedStartup
                            onToggled: page.stagedStartup = checked
                        }
                        AppToggle {
                            theme: page.theme
                            label: "次回からタスクトレイで起動する"
                            checked: page.stagedMinimized
                            onToggled: page.stagedMinimized = checked
                        }

                        Item { Layout.fillHeight: true }
                    }
                }

                    UpdateCard {
                        Layout.fillWidth: true
                        Layout.columnSpan: page.gridColumns
                        theme: page.theme
                        updateController: page.controller
                    }
                }
            }
        }
    }
}
