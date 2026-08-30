import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

ApplicationWindow {
    id: root
    width: 1200
    height: 780
    minimumWidth: 960
    minimumHeight: 660
    visible: false
    title: "PoseCare"
    color: theme.canvas
    property int currentPage: 0
    property var appTheme: theme

    QtObject {
        id: theme
        property color canvas: "#08111E"
        property color nav: "#07101B"
        property color surface: "#101D2C"
        property color surfaceHigh: "#17283A"
        property color surfaceInset: "#0B1725"
        property color surfaceHover: "#1B3045"
        property color surfacePressed: "#0D1A29"
        property color line: "#263A4D"
        property color lineSoft: "#1C3042"
        property color text: "#EDF5F6"
        property color muted: "#91A6B8"
        property color signal: "#42D6BE"
        property color signalHover: "#68E2CF"
        property color signalPressed: "#2CBCA6"
        property color blue: "#62B8F5"
        property color amber: "#F1B867"
        property color danger: "#FF737A"
        property color control: "#2A3D50"
        property color controlLine: "#3B5267"
        property color inkOnAccent: "#05241F"
        property string displayFont: "Yu Gothic UI"
        property string bodyFont: "Yu Gothic UI"
        property string dataFont: "Cascadia Mono"
    }

    function toneColor(tone) {
        if (tone === "blue") return theme.blue
        if (tone === "danger") return theme.danger
        if (tone === "amber") return theme.amber
        return theme.signal
    }

    onClosing: function(close) {
        close.accepted = controller.requestClose()
    }

    Connections {
        target: controller
        function onNavigateRequested(page) { root.currentPage = page }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            Layout.preferredWidth: 214
            Layout.fillHeight: true
            color: theme.nav

            Rectangle {
                anchors.right: parent.right
                width: 1
                height: parent.height
                color: theme.lineSoft
            }

            ColumnLayout {
                anchors.fill: parent
                anchors.leftMargin: 18
                anchors.rightMargin: 18
                anchors.topMargin: 23
                anchors.bottomMargin: 18
                spacing: 0

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 11

                    Item {
                        Layout.preferredWidth: 31
                        Layout.preferredHeight: 37

                        Rectangle {
                            width: 3
                            height: 31
                            radius: 2
                            color: theme.signal
                            anchors.centerIn: parent
                        }
                        Rectangle {
                            width: 19
                            height: 2
                            radius: 1
                            color: theme.text
                            anchors.centerIn: parent
                        }
                        Rectangle {
                            width: 6
                            height: 6
                            radius: 3
                            color: theme.signal
                            anchors.horizontalCenter: parent.horizontalCenter
                            anchors.top: parent.top
                        }
                    }

                    Column {
                        Layout.fillWidth: true
                        spacing: -2
                        Text {
                            text: "PoseCare"
                            color: theme.text
                            font.family: theme.displayFont
                            font.pixelSize: 20
                            font.weight: Font.Bold
                        }
                        Text {
                            text: "LOCAL POSTURE GUIDE"
                            color: theme.muted
                            font.family: theme.dataFont
                            font.pixelSize: 8
                            font.letterSpacing: 0.8
                        }
                    }
                }

                Item { Layout.preferredHeight: 34 }

                AppButton {
                    Layout.fillWidth: true
                    theme: appTheme
                    text: "姿勢モニター"
                    quiet: true
                    selected: root.currentPage === 0
                    onClicked: root.currentPage = 0
                }
                Item { Layout.preferredHeight: 5 }
                AppButton {
                    Layout.fillWidth: true
                    theme: appTheme
                    text: "統計情報"
                    quiet: true
                    selected: root.currentPage === 1
                    onClicked: {
                        root.currentPage = 1
                        controller.refreshStatistics()
                    }
                }
                Item { Layout.preferredHeight: 5 }
                AppButton {
                    Layout.fillWidth: true
                    theme: appTheme
                    text: "設定"
                    quiet: true
                    selected: root.currentPage === 2
                    onClicked: root.currentPage = 2
                }

                Item { Layout.fillHeight: true }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 82
                    radius: 12
                    color: theme.surfaceInset
                    border.color: theme.lineSoft

                    Row {
                        anchors.fill: parent
                        anchors.margins: 12
                        spacing: 9
                        Rectangle {
                            width: 7
                            height: 7
                            radius: 4
                            color: theme.signal
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Text {
                            width: parent.width - 28
                            anchors.verticalCenter: parent.verticalCenter
                            text: "映像・骨格は保存しません\n履歴はこのPC内だけに記録"
                            color: theme.muted
                            font.family: theme.bodyFont
                            font.pixelSize: 10
                            lineHeight: 1.35
                            wrapMode: Text.WordWrap
                        }
                    }
                }
            }
        }

        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: root.currentPage

            Item {
                id: monitorPage

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 27
                    spacing: 18

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 16

                        Column {
                            Layout.fillWidth: true
                            spacing: 2
                            Text {
                                text: "LIVE POSTURE"
                                color: theme.signal
                                font.family: theme.dataFont
                                font.pixelSize: 9
                                font.weight: Font.Bold
                                font.letterSpacing: 1.6
                            }
                            Text {
                                text: "姿勢モニター"
                                color: theme.text
                                font.family: theme.displayFont
                                font.pixelSize: 27
                                font.weight: Font.Bold
                            }
                            Text {
                                text: controller.cameraStatus
                                color: theme.muted
                                font.family: theme.bodyFont
                                font.pixelSize: 11
                                elide: Text.ElideRight
                                width: Math.min(580, monitorPage.width - 340)
                            }
                        }

                        AppToggle {
                            theme: appTheme
                            label: controller.monitoring ? "監視中" : "一時停止中"
                            checked: controller.monitoring
                            onToggled: controller.toggleMonitoring(checked)
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        spacing: 16

                        Card {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            Layout.minimumWidth: 480
                            theme: appTheme
                            fillColor: "#050B12"
                            radius: 20

                            Image {
                                id: cameraImage
                                anchors.fill: parent
                                anchors.margins: 6
                                source: controller.cameraFrameSource
                                cache: false
                                asynchronous: false
                                fillMode: Image.PreserveAspectCrop
                                smooth: true
                            }

                            Column {
                                visible: cameraImage.status !== Image.Ready
                                         && controller.cameraErrorText.length === 0
                                anchors.centerIn: parent
                                spacing: 8
                                Text {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    text: controller.stateKind === "idle"
                                          || controller.stateKind === "locked"
                                          ? "CAMERA RELEASED" : "POSTURE CAMERA"
                                    color: theme.signal
                                    font.family: theme.dataFont
                                    font.pixelSize: 9
                                    font.weight: Font.Bold
                                    font.letterSpacing: 1.3
                                }
                                Text {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    text: controller.stateKind === "locked"
                                          ? "Windowsのロック解除後に自動で再開します"
                                          : controller.stateKind === "idle"
                                          ? "操作を検知すると自動で再開します"
                                          : "カメラ映像を準備しています"
                                    color: theme.muted
                                    font.family: theme.bodyFont
                                    font.pixelSize: 12
                                }
                            }

                            Rectangle {
                                anchors.left: parent.left
                                anchors.top: parent.top
                                anchors.margins: 18
                                width: liveRow.implicitWidth + 20
                                height: 28
                                radius: 14
                                color: "#B30A1724"
                                border.color: theme.line

                                Row {
                                    id: liveRow
                                    anchors.centerIn: parent
                                    spacing: 7
                                    Rectangle {
                                        width: 6
                                        height: 6
                                        radius: 3
                                        color: controller.monitoring
                                               && controller.stateKind !== "idle"
                                               && controller.stateKind !== "locked"
                                               ? theme.signal : theme.muted
                                        anchors.verticalCenter: parent.verticalCenter
                                    }
                                    Text {
                                        text: controller.stateKind === "idle"
                                              || controller.stateKind === "locked" ? "CAMERA OFF"
                                              : controller.monitoring ? "LIVE / LOCAL" : "PAUSED"
                                        color: theme.text
                                        font.family: theme.dataFont
                                        font.pixelSize: 9
                                        font.weight: Font.Bold
                                        font.letterSpacing: 0.8
                                    }
                                }
                            }

                            Rectangle {
                                visible: controller.cameraErrorText.length > 0
                                anchors.fill: parent
                                anchors.margins: 6
                                radius: 15
                                color: "#E60A1420"

                                Column {
                                    anchors.centerIn: parent
                                    spacing: 9
                                    Text {
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        text: "CAMERA OFFLINE"
                                        color: theme.danger
                                        font.family: theme.dataFont
                                        font.pixelSize: 10
                                        font.weight: Font.Bold
                                        font.letterSpacing: 1.2
                                    }
                                    Text {
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        text: controller.cameraErrorText
                                        color: theme.text
                                        font.family: theme.bodyFont
                                        font.pixelSize: 13
                                        horizontalAlignment: Text.AlignHCenter
                                    }
                                }
                            }

                            Text {
                                anchors.right: parent.right
                                anchors.bottom: parent.bottom
                                anchors.margins: 18
                                text: controller.fpsText
                                color: theme.muted
                                font.family: theme.dataFont
                                font.pixelSize: 9
                            }
                        }

                        ColumnLayout {
                            Layout.preferredWidth: 300
                            Layout.minimumWidth: 276
                            Layout.fillHeight: true
                            spacing: 14

                            Card {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 300
                                theme: appTheme

                                ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: 18
                                    spacing: 7

                                    StatusSignal {
                                        Layout.alignment: Qt.AlignHCenter
                                        theme: appTheme
                                        stateKind: controller.stateKind
                                        progress: controller.stateProgress
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        text: controller.stateTitle
                                        color: theme.text
                                        font.family: theme.displayFont
                                        font.pixelSize: 17
                                        font.weight: Font.DemiBold
                                        horizontalAlignment: Text.AlignHCenter
                                        wrapMode: Text.WordWrap
                                    }
                                    Text {
                                        Layout.fillWidth: true
                                        text: controller.stateDetail
                                        color: theme.muted
                                        font.family: theme.bodyFont
                                        font.pixelSize: 11
                                        horizontalAlignment: Text.AlignHCenter
                                        wrapMode: Text.WordWrap
                                    }
                                }
                            }

                            Card {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                theme: appTheme

                                ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: 16
                                    spacing: 10

                                    Column {
                                        Layout.fillWidth: true
                                        spacing: 2
                                        Text {
                                            text: "上半身の位置"
                                            color: theme.text
                                            font.family: theme.displayFont
                                            font.pixelSize: 15
                                            font.weight: Font.DemiBold
                                        }
                                        Text {
                                            text: "頭と両肩から算出した相対値"
                                            color: theme.muted
                                            font.family: theme.bodyFont
                                            font.pixelSize: 10
                                        }
                                    }

                                    GridLayout {
                                        Layout.fillWidth: true
                                        Layout.fillHeight: true
                                        columns: 2
                                        columnSpacing: 8
                                        rowSpacing: 8

                                        MetricTile { Layout.fillWidth: true; theme: appTheme; label: "頭の横ずれ"; value: controller.metrics.headSide }
                                        MetricTile { Layout.fillWidth: true; theme: appTheme; label: "肩の傾き"; value: controller.metrics.shoulderTilt }
                                        MetricTile { Layout.fillWidth: true; theme: appTheme; label: "肩の前後差"; value: controller.metrics.shoulderDepth }
                                        MetricTile { Layout.fillWidth: true; theme: appTheme; label: "頭の前後"; value: controller.metrics.headForward }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            Item {
                id: statisticsPage

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 27
                    spacing: 15

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 16

                        Column {
                            Layout.fillWidth: true
                            spacing: 2
                            Text {
                                text: "POSTURE HISTORY"
                                color: theme.signal
                                font.family: theme.dataFont
                                font.pixelSize: 9
                                font.weight: Font.Bold
                                font.letterSpacing: 1.6
                            }
                            Text {
                                text: "統計情報"
                                color: theme.text
                                font.family: theme.displayFont
                                font.pixelSize: 27
                                font.weight: Font.Bold
                            }
                            Text {
                                text: controller.statisticsUpdated
                                color: theme.muted
                                font.family: theme.bodyFont
                                font.pixelSize: 11
                            }
                        }

                        Card {
                            theme: appTheme
                            Layout.preferredHeight: 44
                            Layout.preferredWidth: 220
                            radius: 12

                            RowLayout {
                                anchors.fill: parent
                                anchors.margins: 4
                                spacing: 2
                                Repeater {
                                    model: [
                                        { label: "1日", value: "day" },
                                        { label: "1週間", value: "week" },
                                        { label: "1ヶ月", value: "month" }
                                    ]
                                    AppButton {
                                        Layout.fillWidth: true
                                        Layout.fillHeight: true
                                        theme: appTheme
                                        text: modelData.label
                                        quiet: true
                                        selected: controller.statisticsPeriod === modelData.value
                                        onClicked: controller.setStatisticsPeriod(modelData.value)
                                    }
                                }
                            }
                        }
                    }

                    GridLayout {
                        Layout.fillWidth: true
                        columns: 4
                        columnSpacing: 10

                        Repeater {
                            model: controller.statisticsCards
                            StatCard {
                                Layout.fillWidth: true
                                theme: appTheme
                                label: modelData.label
                                value: modelData.value
                                detail: modelData.detail
                                accentColor: root.toneColor(modelData.tone)
                            }
                        }
                    }

                    Card {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.minimumHeight: 250
                        theme: appTheme

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 18
                            spacing: 7

                            RowLayout {
                                Layout.fillWidth: true
                                Column {
                                    Layout.fillWidth: true
                                    spacing: 2
                                    Text { text: "姿勢の推移"; color: theme.text; font.family: theme.displayFont; font.pixelSize: 16; font.weight: Font.DemiBold }
                                    Text { text: controller.statisticsNote; color: theme.muted; font.family: theme.bodyFont; font.pixelSize: 10 }
                                }
                                Row {
                                    spacing: 14
                                    Row {
                                        spacing: 5
                                        Rectangle { width: 7; height: 7; radius: 4; color: theme.signal; anchors.verticalCenter: parent.verticalCenter }
                                        Text { text: "良好"; color: theme.muted; font.family: theme.bodyFont; font.pixelSize: 10 }
                                    }
                                    Row {
                                        spacing: 5
                                        Rectangle { width: 7; height: 7; radius: 4; color: theme.danger; anchors.verticalCenter: parent.verticalCenter }
                                        Text { text: "悪い姿勢"; color: theme.muted; font.family: theme.bodyFont; font.pixelSize: 10 }
                                    }
                                }
                            }

                            TimelineChart {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                theme: appTheme
                                buckets: controller.timeline
                            }
                        }
                    }

                    Card {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 175
                        theme: appTheme

                        ColumnLayout {
                            anchors.fill: parent
                            anchors.margins: 18
                            spacing: 7
                            Text { text: "悪い姿勢の内訳"; color: theme.text; font.family: theme.displayFont; font.pixelSize: 16; font.weight: Font.DemiBold }
                            Text { text: "登録した姿勢ごとの検知時間（上位5件）"; color: theme.muted; font.family: theme.bodyFont; font.pixelSize: 10 }

                            Item {
                                Layout.fillWidth: true
                                Layout.fillHeight: true

                                Text {
                                    visible: controller.breakdown.length === 0
                                    anchors.centerIn: parent
                                    text: "この期間に悪い姿勢は記録されていません"
                                    color: theme.muted
                                    font.family: theme.bodyFont
                                    font.pixelSize: 11
                                }

                                ColumnLayout {
                                    visible: controller.breakdown.length > 0
                                    anchors.fill: parent
                                    spacing: 5
                                    Repeater {
                                        model: controller.breakdown
                                        RowLayout {
                                            Layout.fillWidth: true
                                            spacing: 10
                                            Text { Layout.preferredWidth: 125; text: modelData.name; color: theme.text; font.family: theme.bodyFont; font.pixelSize: 11; elide: Text.ElideRight }
                                            Rectangle {
                                                Layout.fillWidth: true
                                                Layout.preferredHeight: 7
                                                radius: 4
                                                color: theme.lineSoft
                                                Rectangle { width: parent.width * modelData.ratio; height: parent.height; radius: 4; color: theme.danger }
                                            }
                                            Text { Layout.preferredWidth: 58; text: modelData.value; color: theme.muted; font.family: theme.dataFont; font.pixelSize: 10 }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }

            Item {
                id: settingsPage
                property int stagedSensitivity: controller.sensitivity
                property real stagedHold: controller.holdSeconds
                property int stagedCooldown: controller.cooldownMinutes
                property bool stagedNotifications: controller.notificationsEnabled
                property int stagedCamera: controller.cameraIndex
                property bool stagedMinimized: controller.startMinimized
                property bool stagedStartup: controller.startupEnabled

                Connections {
                    target: controller
                    function onSettingsChanged() {
                        settingsPage.stagedSensitivity = controller.sensitivity
                        settingsPage.stagedHold = controller.holdSeconds
                        settingsPage.stagedCooldown = controller.cooldownMinutes
                        settingsPage.stagedNotifications = controller.notificationsEnabled
                        settingsPage.stagedCamera = controller.cameraIndex
                        settingsPage.stagedMinimized = controller.startMinimized
                        settingsPage.stagedStartup = controller.startupEnabled
                    }
                }

                ColumnLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 27
                    anchors.rightMargin: 20
                    anchors.topMargin: 27
                    anchors.bottomMargin: 20
                    spacing: 15

                    RowLayout {
                        Layout.fillWidth: true
                        Column {
                            Layout.fillWidth: true
                            spacing: 2
                            Text { text: "PREFERENCES"; color: theme.signal; font.family: theme.dataFont; font.pixelSize: 9; font.weight: Font.Bold; font.letterSpacing: 1.6 }
                            Text { text: "設定"; color: theme.text; font.family: theme.displayFont; font.pixelSize: 27; font.weight: Font.Bold }
                        }
                        Text { objectName: "saveFeedbackText"; text: controller.saveFeedback; color: controller.saveFeedbackError ? theme.danger : theme.signal; font.family: theme.bodyFont; font.pixelSize: 11 }
                        AppButton {
                            theme: appTheme
                            text: "設定を保存"
                            accent: true
                            onClicked: controller.saveSettings(
                                settingsPage.stagedSensitivity,
                                settingsPage.stagedHold,
                                settingsPage.stagedCooldown,
                                settingsPage.stagedNotifications,
                                settingsPage.stagedCamera,
                                settingsPage.stagedMinimized,
                                settingsPage.stagedStartup
                            )
                        }
                    }

                    ScrollView {
                        id: settingsScroll
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                        Column {
                            width: settingsScroll.availableWidth
                            spacing: 13

                            Card {
                                width: parent.width
                                height: badContent.implicitHeight + 38
                                theme: appTheme

                                ColumnLayout {
                                    id: badContent
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    anchors.margins: 19
                                    spacing: 11

                                    RowLayout {
                                        Layout.fillWidth: true
                                        Column {
                                            Layout.fillWidth: true
                                            spacing: 2
                                            Text { text: "通知したい悪い姿勢"; color: theme.text; font.family: theme.displayFont; font.pixelSize: 16; font.weight: Font.DemiBold }
                                            Text { text: "似た姿勢が続くと通知します。複数登録できます。"; color: theme.muted; font.family: theme.bodyFont; font.pixelSize: 10 }
                                        }
                                        AppButton { theme: appTheme; text: "＋ 悪い姿勢"; accent: true; onClicked: controller.beginRegistration("bad", false) }
                                    }

                                    Text {
                                        visible: controller.badProfiles.length === 0
                                        Layout.fillWidth: true
                                        text: "まだ登録されていません。まず1つ登録してください。"
                                        color: theme.muted
                                        font.family: theme.bodyFont
                                        font.pixelSize: 11
                                        topPadding: 9
                                        bottomPadding: 9
                                    }

                                    Repeater {
                                        model: controller.badProfiles
                                        Rectangle {
                                            Layout.fillWidth: true
                                            Layout.preferredHeight: 62
                                            radius: 11
                                            color: theme.surfaceInset
                                            border.color: theme.lineSoft

                                            RowLayout {
                                                anchors.fill: parent
                                                anchors.leftMargin: 14
                                                anchors.rightMargin: 10
                                                spacing: 10
                                                Column {
                                                    Layout.fillWidth: true
                                                    spacing: 2
                                                    Text { text: modelData.name; color: theme.text; font.family: theme.bodyFont; font.pixelSize: 13; font.weight: Font.DemiBold }
                                                    Text { width: parent.width; text: modelData.detail; color: theme.muted; font.family: theme.bodyFont; font.pixelSize: 10; elide: Text.ElideRight }
                                                }
                                                AppButton {
                                                    theme: appTheme
                                                    text: "削除"
                                                    danger: true
                                                    onClicked: {
                                                        deletePopup.profileId = modelData.id
                                                        deletePopup.profileName = modelData.name
                                                        deletePopup.open()
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }

                            Card {
                                width: parent.width
                                height: normalContent.implicitHeight + 38
                                theme: appTheme

                                ColumnLayout {
                                    id: normalContent
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.top: parent.top
                                    anchors.margins: 19
                                    spacing: 11

                                    RowLayout {
                                        Layout.fillWidth: true
                                        Column {
                                            Layout.fillWidth: true
                                            spacing: 2
                                            Text { text: "通知から除外する正常姿勢"; color: theme.text; font.family: theme.displayFont; font.pixelSize: 16; font.weight: Font.DemiBold }
                                            Text { text: "この姿勢に近い場合は、悪い姿勢と少し似ていても通知しません。"; color: theme.muted; font.family: theme.bodyFont; font.pixelSize: 10 }
                                        }
                                        AppButton { theme: appTheme; text: "＋ 正常姿勢"; accent: true; onClicked: controller.beginRegistration("normal", false) }
                                    }

                                    Text {
                                        visible: controller.normalProfiles.length === 0
                                        Layout.fillWidth: true
                                        text: "未登録です。必要に応じて正常姿勢を追加できます。"
                                        color: theme.muted
                                        font.family: theme.bodyFont
                                        font.pixelSize: 11
                                        topPadding: 9
                                        bottomPadding: 9
                                    }

                                    Repeater {
                                        model: controller.normalProfiles
                                        Rectangle {
                                            Layout.fillWidth: true
                                            Layout.preferredHeight: 62
                                            radius: 11
                                            color: theme.surfaceInset
                                            border.color: theme.lineSoft

                                            RowLayout {
                                                anchors.fill: parent
                                                anchors.leftMargin: 14
                                                anchors.rightMargin: 10
                                                spacing: 10
                                                Column {
                                                    Layout.fillWidth: true
                                                    spacing: 2
                                                    Text { text: modelData.name; color: theme.text; font.family: theme.bodyFont; font.pixelSize: 13; font.weight: Font.DemiBold }
                                                    Text { width: parent.width; text: modelData.detail; color: theme.muted; font.family: theme.bodyFont; font.pixelSize: 10; elide: Text.ElideRight }
                                                }
                                                AppButton {
                                                    theme: appTheme
                                                    text: "削除"
                                                    danger: true
                                                    onClicked: {
                                                        deletePopup.profileId = modelData.id
                                                        deletePopup.profileName = modelData.name
                                                        deletePopup.open()
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }

                            Card {
                                width: parent.width
                                height: 270
                                theme: appTheme

                                ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: 19
                                    spacing: 12
                                    Text { text: "検知と通知"; color: theme.text; font.family: theme.displayFont; font.pixelSize: 16; font.weight: Font.DemiBold }

                                    RowLayout {
                                        Layout.fillWidth: true
                                        Text { Layout.preferredWidth: 145; text: "検知感度"; color: theme.text; font.family: theme.bodyFont; font.pixelSize: 12 }
                                        AppSlider {
                                            id: sensitivitySlider
                                            theme: appTheme
                                            Layout.fillWidth: true
                                            from: 0; to: 100; stepSize: 1
                                            value: settingsPage.stagedSensitivity
                                            onMoved: settingsPage.stagedSensitivity = Math.round(value)
                                        }
                                        Text { Layout.preferredWidth: 44; text: settingsPage.stagedSensitivity + "%"; color: theme.signal; font.family: theme.dataFont; font.pixelSize: 12; horizontalAlignment: Text.AlignRight }
                                    }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        Text { Layout.preferredWidth: 145; text: "通知までの時間"; color: theme.text; font.family: theme.bodyFont; font.pixelSize: 12 }
                                        AppSlider { theme: appTheme; Layout.fillWidth: true; from: 1; to: 30; stepSize: 0.5; value: settingsPage.stagedHold; onMoved: settingsPage.stagedHold = value }
                                        Text { Layout.preferredWidth: 54; text: settingsPage.stagedHold.toFixed(1) + "秒"; color: theme.text; font.family: theme.dataFont; font.pixelSize: 11; horizontalAlignment: Text.AlignRight }
                                    }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        Text { Layout.preferredWidth: 145; text: "通知の間隔"; color: theme.text; font.family: theme.bodyFont; font.pixelSize: 12 }
                                        AppSlider { theme: appTheme; Layout.fillWidth: true; from: 1; to: 120; stepSize: 1; value: settingsPage.stagedCooldown; onMoved: settingsPage.stagedCooldown = Math.round(value) }
                                        Text { Layout.preferredWidth: 54; text: settingsPage.stagedCooldown + "分"; color: theme.text; font.family: theme.dataFont; font.pixelSize: 11; horizontalAlignment: Text.AlignRight }
                                    }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        AppToggle { theme: appTheme; label: "Windows通知を有効にする"; checked: settingsPage.stagedNotifications; onToggled: settingsPage.stagedNotifications = checked }
                                        Item { Layout.fillWidth: true }
                                        Text { text: controller.notificationFeedback; color: theme.muted; font.family: theme.bodyFont; font.pixelSize: 10 }
                                        AppButton { theme: appTheme; text: "テスト通知"; onClicked: controller.sendTestNotification() }
                                    }
                                }
                            }

                            Card {
                                width: parent.width
                                height: 218
                                theme: appTheme

                                ColumnLayout {
                                    anchors.fill: parent
                                    anchors.margins: 19
                                    spacing: 12
                                    Text { text: "アプリとカメラ"; color: theme.text; font.family: theme.displayFont; font.pixelSize: 16; font.weight: Font.DemiBold }
                                    RowLayout {
                                        Layout.fillWidth: true
                                        Text { Layout.preferredWidth: 145; text: "カメラ番号"; color: theme.text; font.family: theme.bodyFont; font.pixelSize: 12 }
                                        AppSlider { theme: appTheme; Layout.fillWidth: true; from: 0; to: 9; stepSize: 1; value: settingsPage.stagedCamera; onMoved: settingsPage.stagedCamera = Math.round(value) }
                                        Text { Layout.preferredWidth: 54; text: String(settingsPage.stagedCamera); color: theme.text; font.family: theme.dataFont; font.pixelSize: 11; horizontalAlignment: Text.AlignRight }
                                    }
                                    AppToggle { objectName: "startupToggle"; theme: appTheme; label: "Windowsログイン時にPoseCareを起動する"; checked: settingsPage.stagedStartup; onToggled: settingsPage.stagedStartup = checked }
                                    AppToggle { theme: appTheme; label: "次回からタスクトレイで起動する"; checked: settingsPage.stagedMinimized; onToggled: settingsPage.stagedMinimized = checked }
                                }
                            }

                            UpdateCard {
                                width: parent.width
                                theme: appTheme
                                updateController: controller
                            }
                        }
                    }
                }
            }
        }
    }

    Popup {
        id: registrationPopup
        objectName: "registrationPopup"
        property color phaseColor: controller.registrationPhase === "moving" ? theme.amber
                                   : controller.registrationPhase === "lost" ? theme.danger
                                   : controller.registrationPhase === "ready" ? theme.blue
                                   : theme.signal
        width: Math.min(760, root.width - 48)
        height: Math.min(600, root.height - 36)
        x: (root.width - width) / 2
        y: (root.height - height) / 2
        modal: true
        focus: true
        closePolicy: Popup.NoAutoClose
        visible: controller.registrationOpen
        padding: 0

        background: Rectangle {
            color: theme.surfaceHigh
            radius: 20
            border.color: theme.line
            border.width: 1
        }

        onOpened: {
            profileName.text = controller.registrationType === "normal" ? "いつもの正常姿勢" : "猫背"
            profileName.selectAll()
            profileName.forceActiveFocus()
        }

        contentItem: ColumnLayout {
            anchors.fill: parent
            anchors.margins: 24
            spacing: 16

            RowLayout {
                Layout.fillWidth: true
                spacing: 12

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 3
                    Text {
                        text: controller.registrationFirstRun ? "FIRST SETUP / STILLNESS CHECK" : "POSTURE PROFILE / STILLNESS CHECK"
                        color: theme.signal
                        font.family: theme.dataFont
                        font.pixelSize: 9
                        font.weight: Font.Bold
                        font.letterSpacing: 1.4
                    }
                    Text {
                        text: controller.registrationType === "normal"
                              ? "正常姿勢を3秒間キープ"
                              : "登録する姿勢を3秒間キープ"
                        color: theme.text
                        font.family: theme.displayFont
                        font.pixelSize: 22
                        font.weight: Font.Bold
                    }
                }

                Rectangle {
                    Layout.preferredWidth: 88
                    Layout.preferredHeight: 28
                    radius: 14
                    color: Qt.alpha(registrationPopup.phaseColor, 0.13)
                    border.color: Qt.alpha(registrationPopup.phaseColor, 0.55)
                    Text {
                        anchors.centerIn: parent
                        text: controller.registrationPhase === "complete" ? "CAPTURED"
                              : controller.registrationCapturing ? "MEASURING" : "READY"
                        color: registrationPopup.phaseColor
                        font.family: theme.dataFont
                        font.pixelSize: 9
                        font.weight: Font.Bold
                        font.letterSpacing: 0.8
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 18

                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumWidth: 360
                    radius: 16
                    color: "#050B12"
                    border.color: controller.registrationCapturing
                                  ? Qt.alpha(registrationPopup.phaseColor, 0.72)
                                  : theme.lineSoft
                    border.width: 1
                    clip: true

                    Image {
                        id: registrationCameraImage
                        objectName: "registrationCameraPreview"
                        anchors.fill: parent
                        anchors.margins: 5
                        source: controller.cameraFrameSource
                        cache: false
                        asynchronous: false
                        fillMode: Image.PreserveAspectCrop
                        smooth: true
                    }

                    Rectangle {
                        anchors.fill: parent
                        color: "transparent"
                        border.color: Qt.alpha(registrationPopup.phaseColor, 0.16)
                        border.width: 10
                    }

                    Item {
                        anchors.centerIn: parent
                        width: parent.width * 0.52
                        height: parent.height * 0.62
                        opacity: controller.registrationCapturing ? 0.85 : 0.48

                        Rectangle { anchors.left: parent.left; anchors.top: parent.top; width: 30; height: 2; color: registrationPopup.phaseColor }
                        Rectangle { anchors.left: parent.left; anchors.top: parent.top; width: 2; height: 30; color: registrationPopup.phaseColor }
                        Rectangle { anchors.right: parent.right; anchors.top: parent.top; width: 30; height: 2; color: registrationPopup.phaseColor }
                        Rectangle { anchors.right: parent.right; anchors.top: parent.top; width: 2; height: 30; color: registrationPopup.phaseColor }
                        Rectangle { anchors.left: parent.left; anchors.bottom: parent.bottom; width: 30; height: 2; color: registrationPopup.phaseColor }
                        Rectangle { anchors.left: parent.left; anchors.bottom: parent.bottom; width: 2; height: 30; color: registrationPopup.phaseColor }
                        Rectangle { anchors.right: parent.right; anchors.bottom: parent.bottom; width: 30; height: 2; color: registrationPopup.phaseColor }
                        Rectangle { anchors.right: parent.right; anchors.bottom: parent.bottom; width: 2; height: 30; color: registrationPopup.phaseColor }
                    }

                    Rectangle {
                        anchors.left: parent.left
                        anchors.bottom: parent.bottom
                        anchors.margins: 14
                        width: cameraHint.implicitWidth + 22
                        height: 29
                        radius: 14
                        color: Qt.rgba(0.02, 0.05, 0.08, 0.84)
                        border.color: Qt.alpha(registrationPopup.phaseColor, 0.45)
                        Text {
                            id: cameraHint
                            anchors.centerIn: parent
                            text: controller.registrationPhase === "lost"
                                  ? "上半身を枠内へ"
                                  : "頭と両肩を枠内へ"
                            color: registrationPopup.phaseColor
                            font.family: theme.bodyFont
                            font.pixelSize: 10
                            font.weight: Font.DemiBold
                        }
                    }
                }

                ColumnLayout {
                    Layout.preferredWidth: 300
                    Layout.fillHeight: true
                    spacing: 9

                    Text {
                        text: controller.registrationType === "normal"
                              ? "通知から除外したい姿勢をとり、動かずに保ちます。"
                              : "通知してほしい姿勢をとり、動かずに保ちます。"
                        Layout.fillWidth: true
                        color: theme.muted
                        font.family: theme.bodyFont
                        font.pixelSize: 11
                        lineHeight: 1.3
                        wrapMode: Text.WordWrap
                    }

                    Text { text: "姿勢の名前"; color: theme.text; font.family: theme.bodyFont; font.pixelSize: 11 }
                    TextField {
                        id: profileName
                        Layout.fillWidth: true
                        Layout.preferredHeight: 41
                        enabled: !controller.registrationCapturing
                        maximumLength: 30
                        color: theme.text
                        selectionColor: theme.signal
                        selectedTextColor: theme.inkOnAccent
                        font.family: theme.bodyFont
                        font.pixelSize: 13
                        background: Rectangle {
                            radius: 10
                            color: theme.surfaceInset
                            border.color: profileName.activeFocus ? theme.signal : theme.line
                        }
                    }

                    Item { Layout.fillHeight: true }

                    Text {
                        Layout.fillWidth: true
                        horizontalAlignment: Text.AlignHCenter
                        text: controller.registrationPhase === "complete"
                              ? "✓"
                              : "あと " + controller.registrationSecondsRemaining.toFixed(1) + " 秒"
                        color: registrationPopup.phaseColor
                        font.family: controller.registrationPhase === "complete" ? theme.displayFont : theme.dataFont
                        font.pixelSize: controller.registrationPhase === "complete" ? 48 : 31
                        font.weight: Font.Bold
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 6
                        Repeater {
                            model: 3
                            Rectangle {
                                required property int index
                                property real fillRatio: Math.max(
                                    0,
                                    Math.min(1, (controller.registrationProgress * 3 / 100) - index)
                                )
                                Layout.fillWidth: true
                                Layout.preferredHeight: 10
                                radius: 5
                                color: theme.control
                                Rectangle {
                                    width: parent.width * parent.fillRatio
                                    height: parent.height
                                    radius: parent.radius
                                    color: registrationPopup.phaseColor
                                    Behavior on width { NumberAnimation { duration: 110; easing.type: Easing.OutCubic } }
                                }
                            }
                        }
                    }

                    Text {
                        objectName: "registrationStatusText"
                        Layout.fillWidth: true
                        Layout.preferredHeight: 34
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                        text: controller.registrationStatus
                        color: registrationPopup.phaseColor
                        font.family: theme.bodyFont
                        font.pixelSize: 11
                        font.weight: Font.DemiBold
                        wrapMode: Text.WordWrap
                    }

                    Item { Layout.fillHeight: true }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        AppButton {
                            theme: appTheme
                            text: "キャンセル"
                            enabled: controller.registrationPhase !== "complete"
                            onClicked: controller.cancelRegistration()
                        }
                        Item { Layout.fillWidth: true }
                        AppButton {
                            objectName: "registrationStartButton"
                            theme: appTheme
                            text: controller.registrationCapturing ? "計測中…" : "保持を始める"
                            accent: true
                            enabled: !controller.registrationCapturing && controller.registrationPhase !== "complete"
                            onClicked: controller.startRegistration(profileName.text)
                        }
                    }
                }
            }
        }
    }

    Popup {
        id: deletePopup
        property string profileId: ""
        property string profileName: ""
        width: 420
        height: 205
        x: (root.width - width) / 2
        y: (root.height - height) / 2
        modal: true
        focus: true
        padding: 0

        background: Rectangle { color: theme.surface; radius: 18; border.color: theme.line }
        contentItem: ColumnLayout {
            anchors.fill: parent
            anchors.margins: 24
            spacing: 10
            Text { text: "姿勢を削除"; color: theme.text; font.family: theme.displayFont; font.pixelSize: 20; font.weight: Font.Bold }
            Text { Layout.fillWidth: true; Layout.fillHeight: true; text: "「" + deletePopup.profileName + "」を削除しますか？"; color: theme.muted; font.family: theme.bodyFont; font.pixelSize: 12; wrapMode: Text.WordWrap }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                AppButton { theme: appTheme; text: "キャンセル"; onClicked: deletePopup.close() }
                AppButton { theme: appTheme; text: "削除する"; danger: true; onClicked: { controller.deleteProfile(deletePopup.profileId); deletePopup.close() } }
            }
        }
    }
}
