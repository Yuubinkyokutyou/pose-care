pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Window

Item {
    id: overlay
    objectName: "boneGameOverlay"
    required property var game
    required property var theme
    required property bool available
    readonly property bool active: game.state !== "idle"
    readonly property bool canPlay: available && visible && Window.window !== null
                                    && Window.window.visible
                                    && Window.window.visibility !== Window.Minimized
    clip: true

    onCanPlayChanged: { if (!canPlay) game.reset() }
    onWidthChanged: game.setViewport(width, height)
    onHeightChanged: game.setViewport(width, height)
    Component.onCompleted: game.setViewport(width, height)
    Component.onDestruction: game.reset()

    MouseArea {
        anchors.fill: parent
        enabled: overlay.canPlay && !overlay.active
        onClicked: overlay.game.click()
        onDoubleClicked: overlay.game.click()
    }

    Canvas {
        id: field
        anchors.fill: parent
        visible: overlay.active && overlay.game.state !== "result"
        onPaint: {
            const ctx = getContext("2d")
            ctx.reset()
            ctx.lineCap = "round"
            const arms = overlay.game.arms
            ctx.strokeStyle = "#82FFD5"
            ctx.lineWidth = 10
            ctx.globalAlpha = 0.6
            for (let i = 0; i < arms.length; ++i) {
                const arm = arms[i]
                ctx.beginPath()
                ctx.moveTo(arm.ax, arm.ay)
                ctx.lineTo(arm.bx, arm.by)
                ctx.stroke()
            }
        }
    }
    Connections {
        target: overlay.game
        function onChanged() { if (overlay.active) field.requestPaint() }
    }

    Repeater {
        model: overlay.game.sprites
        delegate: Item {
            required property var modelData
            x: modelData.x - width / 2
            y: modelData.y - height / 2
            width: 80
            height: 65
            rotation: modelData.angle
            Rectangle {
                anchors.centerIn: parent
                width: 58; height: 32; radius: 16
                visible: parent.modelData.reflected
                color: "#6682FFD5"
            }
            Image {
                anchors.fill: parent
                source: "assets/bone.png"
                fillMode: Image.PreserveAspectFit
                smooth: true
            }
        }
    }

    Image {
        objectName: "boneGameNoseHeart"
        readonly property var nose: overlay.game.nosePosition
        visible: (overlay.game.state === "intro" || overlay.game.state === "playing")
                 && overlay.game.tracking
        x: (nose.x || 0) - width / 2
        y: (nose.y || 0) - height / 2
        width: 44
        height: 40
        source: "assets/nose-heart.png"
        fillMode: Image.PreserveAspectFit
        smooth: true
    }

    Rectangle {
        anchors.fill: parent
        color: "#44FF5470"
        visible: overlay.active && overlay.game.hitFlash && overlay.game.state === "playing"
    }

    Rectangle {
        visible: overlay.active
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.margins: 12
        width: 142; height: 72; radius: 15
        color: "#E0192724"
        border.color: "#6682FFD5"
        Column {
            anchors.centerIn: parent
            spacing: 2
            Row {
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: 8
                Repeater {
                    model: 2
                    Text {
                        required property int index
                        text: "♥"
                        color: index < overlay.game.hearts ? "#FF7892" : "#52615B"
                        font.pixelSize: 26
                    }
                }
            }
            Text {
                text: overlay.game.score.toFixed(1) + " 秒"
                color: "#FFFFFF"
                font.family: overlay.theme.dataFont
                font.pixelSize: 15
                anchors.horizontalCenter: parent.horizontalCenter
            }
        }
    }

    Text {
        id: startText
        visible: overlay.game.state === "intro"
        y: (parent.height - height) / 2
        text: "スタート"
        color: "#FFFFFF"
        style: Text.Outline
        styleColor: "#176651"
        font.family: overlay.theme.displayFont
        font.pixelSize: 54
        font.bold: true
        SequentialAnimation {
            running: overlay.game.state === "intro"
            NumberAnimation { target: startText; property: "x"; from: overlay.width; to: (overlay.width - startText.width) / 2; duration: 450; easing.type: Easing.OutCubic }
            PauseAnimation { duration: 650 }
            NumberAnimation { target: startText; property: "x"; to: -startText.width; duration: 500; easing.type: Easing.InCubic }
        }
    }

    Rectangle {
        visible: overlay.active && overlay.game.state !== "result"
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 20
        width: Math.min(parent.width - 24, 350); height: 38; radius: 19
        color: "#E0192724"
        Text {
            anchors.centerIn: parent
            text: overlay.game.tracking ? "腕ではじいて、鼻を守ろう！" : "鼻をカメラに映してね · 一時停止中"
            color: "#E9FFF5"
            font.family: overlay.theme.bodyFont
            font.pixelSize: 13
        }
    }

    Rectangle {
        objectName: "boneGameResult"
        visible: overlay.game.state === "result"
        anchors.fill: parent
        color: "#B5101D18"
        Column {
            anchors.centerIn: parent
            spacing: 14
            Text {
                text: "ゲームオーバー"
                color: "#FFADC0"
                font.family: overlay.theme.displayFont
                font.pixelSize: 26
                font.bold: true
                anchors.horizontalCenter: parent.horizontalCenter
            }
            Text {
                text: overlay.game.score.toFixed(1) + " 秒"
                color: "#FFFFFF"
                font.family: overlay.theme.dataFont
                font.pixelSize: 54
                font.bold: true
                anchors.horizontalCenter: parent.horizontalCenter
            }
            Text {
                text: "耐えた時間がスコア！"
                color: "#D2E8DD"
                font.family: overlay.theme.bodyFont
                font.pixelSize: 14
                anchors.horizontalCenter: parent.horizontalCenter
            }
            AppButton {
                text: "モニターに戻る"
                theme: overlay.theme
                anchors.horizontalCenter: parent.horizontalCenter
                onClicked: overlay.game.reset()
            }
            Text {
                text: "5秒後に自動で戻ります"
                color: "#A9BCB2"
                font.family: overlay.theme.bodyFont
                font.pixelSize: 11
                anchors.horizontalCenter: parent.horizontalCenter
            }
        }
    }
}
