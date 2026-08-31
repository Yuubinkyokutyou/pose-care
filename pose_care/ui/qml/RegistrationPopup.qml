pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Popup {
    id: popup
    objectName: "registrationPopup"

    required property var controller
    required property var theme
    required property var hostWindow

    readonly property color phaseColor: controller.registrationPhase === "moving" ? theme.amber
                                        : controller.registrationPhase === "lost" ? theme.danger
                                        : controller.registrationPhase === "ready" ? theme.blue
                                        : theme.signal
    readonly property color previewPhaseColor: controller.registrationPhase === "moving" ? "#EBC27C"
                                               : controller.registrationPhase === "lost" ? "#FFB2AD"
                                               : controller.registrationPhase === "ready" ? "#9ED7EE"
                                               : "#92E1BD"

    width: Math.min(780, hostWindow.width - 48)
    height: Math.min(590, hostWindow.height - 36)
    x: (hostWindow.width - width) / 2
    y: (hostWindow.height - height) / 2
    modal: true
    focus: true
    closePolicy: Popup.NoAutoClose
    visible: controller.registrationOpen
    padding: 0

    background: Rectangle {
        color: popup.theme.surface
        radius: 20
        border.color: popup.theme.line
        border.width: 1
    }

    onOpened: {
        profileName.text = controller.registrationType === "normal" ? "通知しない姿勢" : "猫背"
        profileName.selectAll()
        profileName.forceActiveFocus()
    }

    contentItem: ColumnLayout {
        anchors.fill: parent
        anchors.margins: 22
        spacing: 15

        RowLayout {
            Layout.fillWidth: true
            spacing: 12

            Column {
                Layout.fillWidth: true
                spacing: 2
                Text {
                    text: popup.controller.registrationType === "normal"
                          ? "通知しない姿勢を登録"
                          : "悪い姿勢を登録"
                    color: popup.theme.text
                    font.family: popup.theme.displayFont
                    font.pixelSize: 22
                    font.weight: Font.Bold
                }
            }

            Rectangle {
                Layout.preferredWidth: 100
                Layout.preferredHeight: 30
                radius: 15
                color: Qt.alpha(popup.phaseColor, 0.10)
                border.color: Qt.alpha(popup.phaseColor, 0.38)
                Text {
                    anchors.centerIn: parent
                        text: popup.controller.registrationPhase === "complete" ? "完了"
                          : popup.controller.registrationCapturing ? "計測中" : "準備完了"
                    color: popup.phaseColor
                    font.family: popup.theme.dataFont
                    font.pixelSize: 9
                    font.weight: Font.Bold
                    font.letterSpacing: 0.7
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 17

            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumWidth: 390
                radius: 16
                color: "#101713"
                border.color: popup.controller.registrationCapturing
                              ? Qt.alpha(popup.previewPhaseColor, 0.82) : popup.theme.line
                border.width: 1
                clip: true

                Image {
                    objectName: "registrationCameraPreview"
                    anchors.fill: parent
                    anchors.margins: 5
                    source: popup.controller.cameraFrameSource
                    cache: false
                    asynchronous: false
                    fillMode: Image.PreserveAspectCrop
                    smooth: true
                }

                Item {
                    anchors.centerIn: parent
                    width: parent.width * 0.53
                    height: parent.height * 0.64
                    opacity: popup.controller.registrationCapturing ? 0.82 : 0.45

                    Rectangle { anchors.left: parent.left; anchors.top: parent.top; width: 28; height: 2; color: popup.previewPhaseColor }
                    Rectangle { anchors.left: parent.left; anchors.top: parent.top; width: 2; height: 28; color: popup.previewPhaseColor }
                    Rectangle { anchors.right: parent.right; anchors.top: parent.top; width: 28; height: 2; color: popup.previewPhaseColor }
                    Rectangle { anchors.right: parent.right; anchors.top: parent.top; width: 2; height: 28; color: popup.previewPhaseColor }
                    Rectangle { anchors.left: parent.left; anchors.bottom: parent.bottom; width: 28; height: 2; color: popup.previewPhaseColor }
                    Rectangle { anchors.left: parent.left; anchors.bottom: parent.bottom; width: 2; height: 28; color: popup.previewPhaseColor }
                    Rectangle { anchors.right: parent.right; anchors.bottom: parent.bottom; width: 28; height: 2; color: popup.previewPhaseColor }
                    Rectangle { anchors.right: parent.right; anchors.bottom: parent.bottom; width: 2; height: 28; color: popup.previewPhaseColor }
                }

                Rectangle {
                    anchors.left: parent.left
                    anchors.bottom: parent.bottom
                    anchors.margins: 13
                    width: cameraHint.implicitWidth + 22
                    height: 29
                    radius: 15
                    color: "#D9151C18"
                    border.color: Qt.alpha(popup.previewPhaseColor, 0.62)
                    Text {
                        id: cameraHint
                        anchors.centerIn: parent
                        text: popup.controller.registrationPhase === "lost"
                              ? "上半身を枠の中へ" : "頭と両肩を枠の中へ"
                        color: popup.previewPhaseColor
                        font.family: popup.theme.bodyFont
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
                    Layout.fillWidth: true
                    text: popup.controller.registrationType === "normal"
                          ? "通知しない姿勢を3秒間保ちます"
                          : "通知対象にする姿勢を3秒間保ちます"
                    color: popup.theme.muted
                    font.family: popup.theme.bodyFont
                    font.pixelSize: 11
                    lineHeight: 1.3
                    wrapMode: Text.WordWrap
                }

                Text {
                    text: "姿勢の名前"
                    color: popup.theme.text
                    font.family: popup.theme.bodyFont
                    font.pixelSize: 10
                    font.weight: Font.DemiBold
                }
                TextField {
                    id: profileName
                    Layout.fillWidth: true
                    Layout.preferredHeight: 42
                    enabled: !popup.controller.registrationCapturing
                    maximumLength: 30
                    color: popup.theme.text
                    selectionColor: popup.theme.signal
                    selectedTextColor: popup.theme.inkOnAccent
                    font.family: popup.theme.bodyFont
                    font.pixelSize: 13
                    Accessible.name: "姿勢の名前"
                    background: Rectangle {
                        radius: 11
                        color: popup.theme.surfaceInset
                        border.width: profileName.activeFocus ? 2 : 1
                        border.color: profileName.activeFocus ? popup.theme.signal : popup.theme.line
                    }
                }

                Item { Layout.fillHeight: true }

                Text {
                    Layout.fillWidth: true
                    horizontalAlignment: Text.AlignHCenter
                    text: popup.controller.registrationPhase === "complete"
                          ? "✓" : "あと " + popup.controller.registrationSecondsRemaining.toFixed(1) + " 秒"
                    color: popup.phaseColor
                    font.family: popup.controller.registrationPhase === "complete"
                                 ? popup.theme.displayFont : popup.theme.dataFont
                    font.pixelSize: popup.controller.registrationPhase === "complete" ? 44 : 28
                    font.weight: Font.Bold
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 5
                    Repeater {
                        model: 3
                        Rectangle {
                            required property int index
                            property real fillRatio: Math.max(
                                0,
                                Math.min(1, (popup.controller.registrationProgress * 3 / 100) - index)
                            )
                            Layout.fillWidth: true
                            Layout.preferredHeight: 9
                            radius: 5
                            color: popup.theme.control
                            Rectangle {
                                width: parent.width * parent.fillRatio
                                height: parent.height
                                radius: parent.radius
                                color: popup.phaseColor
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
                    text: popup.controller.registrationStatus
                    color: popup.phaseColor
                    font.family: popup.theme.bodyFont
                    font.pixelSize: 10
                    font.weight: Font.DemiBold
                    wrapMode: Text.WordWrap
                }

                Item { Layout.fillHeight: true }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    AppButton {
                        theme: popup.theme
                        text: "キャンセル"
                        enabled: popup.controller.registrationPhase !== "complete"
                        onClicked: popup.controller.cancelRegistration()
                    }
                    Item { Layout.fillWidth: true }
                    AppButton {
                        objectName: "registrationStartButton"
                        theme: popup.theme
                        text: popup.controller.registrationCapturing ? "計測中…" : "計測開始"
                        accent: true
                        enabled: !popup.controller.registrationCapturing
                                 && popup.controller.registrationPhase !== "complete"
                        onClicked: popup.controller.startRegistration(profileName.text)
                    }
                }
            }
        }
    }
}
