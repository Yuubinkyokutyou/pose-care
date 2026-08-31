pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts

Item {
    id: page
    objectName: "statisticsPage"

    required property var controller
    required property var theme
    readonly property bool hasStatisticsData: {
        for (var i = 0; i < controller.timeline.length; ++i) {
            if (controller.timeline[i].hasData)
                return true
        }
        return false
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.leftMargin: 24
        anchors.rightMargin: 24
        anchors.topMargin: 22
        anchors.bottomMargin: 22
        spacing: 14

        RowLayout {
            objectName: "statisticsToolbar"
            Layout.fillWidth: true
            Layout.maximumHeight: 54
            spacing: 16

            Column {
                Layout.fillWidth: true
                spacing: 2
                Text {
                    text: "統計"
                    color: page.theme.text
                    font.family: page.theme.displayFont
                    font.pixelSize: 28
                    font.weight: Font.Bold
                    font.letterSpacing: -0.5
                }
            }

            Text {
                text: page.controller.statisticsUpdated
                color: page.theme.muted
                font.family: page.theme.bodyFont
                font.pixelSize: 10
                horizontalAlignment: Text.AlignRight
            }
        }

        RowLayout {
            objectName: "statisticsDateRow"
            Layout.fillWidth: true
            Layout.minimumHeight: 46
            Layout.preferredHeight: 46
            Layout.maximumHeight: 46
            spacing: 12

            Card {
                Layout.preferredWidth: 224
                Layout.fillHeight: true
                theme: page.theme
                radius: 13

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 4
                    spacing: 2

                    Repeater {
                        model: [
                            { label: "1日", value: "day" },
                            { label: "7日", value: "week" },
                            { label: "30日", value: "month" }
                        ]

                        AppButton {
                            required property var modelData
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            theme: page.theme
                            text: modelData.label
                            quiet: true
                            selected: page.controller.statisticsPeriod === modelData.value
                            Accessible.role: Accessible.RadioButton
                            Accessible.checked: selected
                            Accessible.description: "統計の表示期間を" + modelData.label + "に切り替えます"
                            onClicked: page.controller.setStatisticsPeriod(modelData.value)
                        }
                    }
                }
            }

            Item { Layout.fillWidth: true }

            Card {
                Layout.preferredWidth: 360
                Layout.fillHeight: true
                theme: page.theme
                radius: 13

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 4
                    spacing: 3

                    AppButton {
                        objectName: "statisticsPreviousButton"
                        Layout.preferredWidth: 38
                        Layout.fillHeight: true
                        theme: page.theme
                        text: "‹"
                        quiet: true
                        enabled: page.controller.statisticsCanGoPrevious
                        Accessible.name: "前の期間"
                        onClicked: page.controller.showPreviousStatistics()
                    }

                    Item {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Layout.alignment: Qt.AlignVCenter
                        Text {
                            anchors.fill: parent
                            text: page.controller.statisticsRangeLabel
                            color: page.theme.text
                            font.family: page.theme.bodyFont
                            font.pixelSize: 12
                            font.weight: Font.DemiBold
                            horizontalAlignment: Text.AlignHCenter
                            verticalAlignment: Text.AlignVCenter
                            elide: Text.ElideRight
                        }
                    }

                    AppButton {
                        objectName: "statisticsNextButton"
                        Layout.preferredWidth: 38
                        Layout.fillHeight: true
                        theme: page.theme
                        text: "›"
                        quiet: true
                        enabled: page.controller.statisticsCanGoNext
                        Accessible.name: "次の期間"
                        onClicked: page.controller.showNextStatistics()
                    }
                    AppButton {
                        objectName: "statisticsTodayButton"
                        Layout.preferredWidth: 49
                        Layout.fillHeight: true
                        theme: page.theme
                        text: "今日"
                        quiet: true
                        enabled: page.controller.statisticsCanGoNext
                        Accessible.description: "今日を含む期間へ戻ります"
                        onClicked: page.controller.showTodayStatistics()
                    }
                }
            }
        }

        GridLayout {
            objectName: "statisticsCardsGrid"
            Layout.fillWidth: true
            Layout.minimumHeight: 116
            Layout.preferredHeight: 116
            Layout.maximumHeight: 116
            columns: 4
            columnSpacing: 9

            Repeater {
                model: page.controller.statisticsCards

                StatCard {
                    required property var modelData
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    theme: page.theme
                    label: modelData.label
                    value: modelData.value
                    detail: modelData.detail
                    helpText: modelData.help || modelData.detail
                    accentColor: modelData.tone === "blue" ? page.theme.blue
                                 : modelData.tone === "danger" ? page.theme.danger
                                 : modelData.tone === "amber" ? page.theme.amber
                                 : page.theme.signal
                }
            }
        }

        RowLayout {
            objectName: "statisticsDetailRow"
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 12

            Card {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumWidth: 420
                theme: page.theme

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 16
                    spacing: 8

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 12

                        Column {
                            Layout.fillWidth: true
                            spacing: 2
                            Text {
                                text: page.controller.statisticsNote
                                color: page.theme.text
                                font.family: page.theme.displayFont
                                font.pixelSize: 16
                                font.weight: Font.DemiBold
                            }
                            Text {
                                text: "ホバーで詳細表示"
                                color: page.theme.muted
                                font.family: page.theme.bodyFont
                                font.pixelSize: 9
                            }
                        }

                        Row {
                            spacing: 12
                            Row {
                                spacing: 5
                                Rectangle { width: 7; height: 7; radius: 4; color: page.theme.signal; anchors.verticalCenter: parent.verticalCenter }
                                Text { text: "良い姿勢"; color: page.theme.muted; font.family: page.theme.bodyFont; font.pixelSize: 9 }
                            }
                            Row {
                                spacing: 5
                                Rectangle { width: 7; height: 7; radius: 4; color: page.theme.danger; anchors.verticalCenter: parent.verticalCenter }
                                Text { text: "悪い姿勢"; color: page.theme.muted; font.family: page.theme.bodyFont; font.pixelSize: 9 }
                            }
                        }
                    }

                    TimelineChart {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        theme: page.theme
                        buckets: page.controller.timeline
                    }
                }
            }

            Card {
                Layout.preferredWidth: 235
                Layout.minimumWidth: 220
                Layout.fillHeight: true
                theme: page.theme

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 16
                    spacing: 9

                    Column {
                        Layout.fillWidth: true
                        spacing: 2
                        Text {
                            text: "姿勢別"
                            color: page.theme.text
                            font.family: page.theme.displayFont
                            font.pixelSize: 16
                            font.weight: Font.DemiBold
                        }
                    }

                    Item {
                        Layout.fillWidth: true
                        Layout.fillHeight: true

                        Column {
                            visible: page.controller.breakdown.length === 0
                            anchors.centerIn: parent
                            spacing: 4
                            Text {
                                objectName: "breakdownEmptyTitle"
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: page.hasStatisticsData
                                      ? "悪い姿勢 0分" : "記録なし"
                                color: page.theme.text
                                font.family: page.theme.bodyFont
                                font.pixelSize: 12
                                font.weight: Font.DemiBold
                            }
                        }

                        ColumnLayout {
                            visible: page.controller.breakdown.length > 0
                            anchors.fill: parent
                            spacing: 9

                            Repeater {
                                model: page.controller.breakdown

                                ColumnLayout {
                                    id: breakdownRow
                                    required property var modelData
                                    Layout.fillWidth: true
                                    spacing: 4
                                    Accessible.role: Accessible.Graphic
                                    Accessible.name: modelData.name + " " + modelData.value

                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 6
                                        Text {
                                            Layout.fillWidth: true
                                            text: breakdownRow.modelData.name
                                            color: page.theme.text
                                            font.family: page.theme.bodyFont
                                            font.pixelSize: 10
                                            font.weight: Font.DemiBold
                                            elide: Text.ElideRight
                                        }
                                        Text {
                                            text: breakdownRow.modelData.value
                                            color: page.theme.muted
                                            font.family: page.theme.dataFont
                                            font.pixelSize: 9
                                        }
                                    }
                                    Rectangle {
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 6
                                        radius: 3
                                        color: page.theme.surfaceInset
                                        Rectangle {
                                            width: parent.width * breakdownRow.modelData.ratio
                                            height: parent.height
                                            radius: 3
                                            color: page.theme.danger
                                        }
                                    }
                                }
                            }

                            Item { Layout.fillHeight: true }
                        }
                    }

                }
            }
        }
    }
}
