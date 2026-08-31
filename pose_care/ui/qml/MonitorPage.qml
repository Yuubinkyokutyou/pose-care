pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts

Item {
    id: page

    required property var controller
    required property var theme

    readonly property color stateColor: controller.stateKind === "good"
                                        || controller.stateKind === "normal" ? theme.signal
                                        : controller.stateKind === "warning" ? theme.amber
                                        : controller.stateKind === "bad" ? theme.danger
                                        : theme.blue

    ColumnLayout {
        anchors.fill: parent
        anchors.leftMargin: 24
        anchors.rightMargin: 24
        anchors.topMargin: 22
        anchors.bottomMargin: 22
        spacing: 16

        RowLayout {
            Layout.fillWidth: true
            spacing: 18

            Column {
                Layout.fillWidth: true
                spacing: 2

                Text {
                    text: "モニター"
                    color: page.theme.text
                    font.family: page.theme.displayFont
                    font.pixelSize: 28
                    font.weight: Font.Bold
                    font.letterSpacing: -0.5
                }
                Text {
                    width: Math.min(520, page.width - 300)
                    text: page.controller.cameraStatus
                    color: page.theme.muted
                    font.family: page.theme.bodyFont
                    font.pixelSize: 11
                    elide: Text.ElideRight
                }
            }

            AppToggle {
                theme: page.theme
                label: page.controller.monitoring ? "監視中" : "一時停止"
                checked: page.controller.monitoring
                Accessible.description: checked ? "オフにすると姿勢の監視を一時停止します" : "オンにすると姿勢の監視を再開します"
                onToggled: page.controller.toggleMonitoring(checked)
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 14

            Card {
                id: cameraCard
                objectName: "monitorCameraCard"
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumWidth: 390
                theme: page.theme
                fillColor: "#101713"
                strokeColor: page.theme.line
                radius: 18
                clip: true

                Image {
                    id: cameraImage
                    anchors.fill: parent
                    anchors.margins: 5
                    source: page.controller.cameraFrameSource
                    cache: false
                    asynchronous: false
                    fillMode: Image.PreserveAspectCrop
                    smooth: true
                }

                Rectangle {
                    anchors.fill: parent
                    color: "transparent"
                    border.width: 1
                    border.color: Qt.alpha(page.stateColor, 0.28)
                    radius: 18
                }

                Column {
                    visible: cameraImage.status !== Image.Ready
                             && page.controller.cameraErrorText.length === 0
                    anchors.centerIn: parent
                    spacing: 8

                    Item {
                        width: 46
                        height: 64
                        anchors.horizontalCenter: parent.horizontalCenter

                        Rectangle {
                            width: 2
                            height: 58
                            radius: 1
                            color: page.theme.signal
                            anchors.centerIn: parent
                        }
                        Repeater {
                            model: [4, 28, 52]
                            Rectangle {
                                required property int modelData
                                width: modelData === 28 ? 10 : 7
                                height: width
                                radius: width / 2
                                color: "#101713"
                                border.width: 2
                                border.color: page.theme.signal
                                anchors.horizontalCenter: parent.horizontalCenter
                                y: modelData
                            }
                        }
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: page.controller.stateKind === "locked"
                              ? "Windowsのロック解除後に再開します"
                              : page.controller.stateKind === "idle"
                              ? "操作を検知すると再開します"
                              : "カメラを準備しています"
                        color: "#C9D5CE"
                        font.family: page.theme.bodyFont
                        font.pixelSize: 12
                    }
                }

                Rectangle {
                    visible: page.controller.cameraErrorText.length > 0
                    anchors.fill: parent
                    anchors.margins: 5
                    radius: 15
                    color: "#ED151C18"

                    Column {
                        anchors.centerIn: parent
                        spacing: 8
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: "カメラエラー"
                            color: "#FFB2AD"
                            font.family: page.theme.dataFont
                            font.pixelSize: 10
                            font.weight: Font.Bold
                            font.letterSpacing: 1.1
                        }
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            width: Math.min(380, cameraCard.width - 64)
                            text: page.controller.cameraErrorText
                            color: "#F4F7F5"
                            font.family: page.theme.bodyFont
                            font.pixelSize: 12
                            horizontalAlignment: Text.AlignHCenter
                            wrapMode: Text.WordWrap
                        }
                    }
                }

                Rectangle {
                    anchors.left: parent.left
                    anchors.top: parent.top
                    anchors.margins: 16
                    width: liveLabel.implicitWidth + 25
                    height: 30
                    radius: 15
                    color: "#C9141B17"
                    border.color: "#4DFFFFFF"

                    Row {
                        anchors.centerIn: parent
                        spacing: 7
                        Rectangle {
                            width: 7
                            height: 7
                            radius: 4
                            color: page.controller.monitoring
                                   && page.controller.stateKind !== "idle"
                                   && page.controller.stateKind !== "locked"
                                   ? page.stateColor : "#94A39A"
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Text {
                            id: liveLabel
                            text: page.controller.stateKind === "idle"
                                  || page.controller.stateKind === "locked" ? "待機"
                                  : page.controller.monitoring ? "監視中" : "一時停止"
                            color: "#F5F8F6"
                            font.family: page.theme.dataFont
                            font.pixelSize: 9
                            font.weight: Font.Bold
                            font.letterSpacing: 0.6
                        }
                    }
                }

                Item {
                    anchors.centerIn: parent
                    width: Math.min(parent.width * 0.48, 250)
                    height: Math.min(parent.height * 0.60, 300)
                    opacity: cameraImage.status === Image.Ready ? 0.30 : 0

                    Rectangle { anchors.left: parent.left; anchors.top: parent.top; width: 26; height: 1; color: page.stateColor }
                    Rectangle { anchors.left: parent.left; anchors.top: parent.top; width: 1; height: 26; color: page.stateColor }
                    Rectangle { anchors.right: parent.right; anchors.top: parent.top; width: 26; height: 1; color: page.stateColor }
                    Rectangle { anchors.right: parent.right; anchors.top: parent.top; width: 1; height: 26; color: page.stateColor }
                    Rectangle { anchors.left: parent.left; anchors.bottom: parent.bottom; width: 26; height: 1; color: page.stateColor }
                    Rectangle { anchors.left: parent.left; anchors.bottom: parent.bottom; width: 1; height: 26; color: page.stateColor }
                    Rectangle { anchors.right: parent.right; anchors.bottom: parent.bottom; width: 26; height: 1; color: page.stateColor }
                    Rectangle { anchors.right: parent.right; anchors.bottom: parent.bottom; width: 1; height: 26; color: page.stateColor }
                }

                Text {
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    anchors.margins: 16
                    text: page.controller.fpsText
                    color: "#AEBBB4"
                    font.family: page.theme.dataFont
                    font.pixelSize: 9
                }
            }

            ColumnLayout {
                objectName: "monitorSidePanel"
                Layout.preferredWidth: 260
                Layout.minimumWidth: 248
                Layout.maximumWidth: 286
                Layout.fillHeight: true
                spacing: 12

                Card {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 250
                    theme: page.theme
                    strokeColor: Qt.alpha(page.stateColor, 0.35)

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 16
                        spacing: 5

                        RowLayout {
                            Layout.fillWidth: true
                            Text {
                                text: "判定"
                                color: page.theme.muted
                                font.family: page.theme.bodyFont
                                font.pixelSize: 11
                                font.weight: Font.DemiBold
                            }
                            Item { Layout.fillWidth: true }
                            Rectangle {
                                Layout.preferredWidth: 8
                                Layout.preferredHeight: 8
                                radius: 4
                                color: page.stateColor
                            }
                        }

                        StatusSignal {
                            Layout.alignment: Qt.AlignHCenter
                            Layout.fillHeight: true
                            theme: page.theme
                            stateKind: page.controller.stateKind
                            progress: page.controller.stateProgress
                        }
                        Text {
                            Layout.fillWidth: true
                            text: page.controller.stateTitle
                            color: page.theme.text
                            font.family: page.theme.displayFont
                            font.pixelSize: 17
                            font.weight: Font.DemiBold
                            horizontalAlignment: Text.AlignHCenter
                            wrapMode: Text.WordWrap
                        }
                        Text {
                            Layout.fillWidth: true
                            text: page.controller.stateDetail
                            color: page.theme.muted
                            font.family: page.theme.bodyFont
                            font.pixelSize: 10
                            horizontalAlignment: Text.AlignHCenter
                            wrapMode: Text.WordWrap
                        }
                    }
                }

                Card {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumHeight: 210
                    theme: page.theme

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 15
                        spacing: 10

                        Column {
                            Layout.fillWidth: true
                            spacing: 2
                            Text {
                                text: "位置"
                                color: page.theme.text
                                font.family: page.theme.displayFont
                                font.pixelSize: 15
                                font.weight: Font.DemiBold
                            }
                        }

                        GridLayout {
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            columns: 2
                            columnSpacing: 7
                            rowSpacing: 7

                            MetricTile { Layout.fillWidth: true; Layout.fillHeight: true; theme: page.theme; label: "頭・左右"; value: page.controller.metrics.headSide }
                            MetricTile { Layout.fillWidth: true; Layout.fillHeight: true; theme: page.theme; label: "肩・傾き"; value: page.controller.metrics.shoulderTilt }
                            MetricTile { Layout.fillWidth: true; Layout.fillHeight: true; theme: page.theme; label: "肩・前後"; value: page.controller.metrics.shoulderDepth }
                            MetricTile { Layout.fillWidth: true; Layout.fillHeight: true; theme: page.theme; label: "頭・前後"; value: page.controller.metrics.headForward }
                        }
                    }
                }
            }
        }
    }
}
