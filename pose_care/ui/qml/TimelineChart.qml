pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls

Item {
    id: root
    objectName: "timelineChart"

    required property var theme
    property var buckets: []
    property int hoveredIndex: -1
    property bool pointerInside: false

    readonly property real chartLeft: 8
    readonly property real chartRight: 8
    readonly property real chartTop: 24
    readonly property real chartBottom: 34
    readonly property real slotWidth: buckets.length > 0
                                      ? Math.max(1, plot.width / buckets.length) : 1
    readonly property real maximumMonitored: {
        var maximum = 0
        for (var i = 0; i < buckets.length; ++i)
            maximum = Math.max(maximum, Number(buckets[i].good) + Number(buckets[i].bad))
        return Math.max(1, maximum)
    }
    readonly property bool hasData: {
        for (var i = 0; i < buckets.length; ++i) {
            if (Number(buckets[i].good) + Number(buckets[i].bad) > 0)
                return true
        }
        return false
    }

    implicitHeight: 230
    clip: false
    activeFocusOnTab: hasData
    Accessible.role: Accessible.Chart
    Accessible.name: "姿勢の推移。棒の高さは監視時間、色は良好と悪い姿勢の内訳です"
    Accessible.focusable: hasData

    function formatDuration(value) {
        var seconds = Math.max(0, Number(value))
        var minutes = Math.floor(seconds / 60)
        if (minutes >= 60) {
            var hours = Math.floor(minutes / 60)
            var remainder = minutes % 60
            return hours + "時間" + (remainder > 0 ? remainder + "分" : "")
        }
        if (minutes > 0)
            return minutes + "分"
        return Math.floor(seconds) + "秒"
    }

    function bucketSummary(bucket) {
        if (!bucket)
            return ""
        var good = Number(bucket.good)
        var bad = Number(bucket.bad)
        var total = good + bad
        var rate = total > 0 ? Math.round(good * 100 / total) + "%" : "—"
        return (bucket.detailLabel || bucket.label)
                + "、監視 " + (bucket.monitoredText || formatDuration(total))
                + "、良好 " + (bucket.goodText || formatDuration(good))
                + "、悪い姿勢 " + (bucket.badText || formatDuration(bad))
                + "、良好率 " + (bucket.ratioText || rate)
    }

    function showPreviousBucket() {
        if (buckets.length === 0)
            return
        hoveredIndex = hoveredIndex <= 0 ? buckets.length - 1 : hoveredIndex - 1
    }

    function showNextBucket() {
        if (buckets.length === 0)
            return
        hoveredIndex = hoveredIndex >= buckets.length - 1 ? 0 : hoveredIndex + 1
    }

    function firstDataBucket() {
        for (var i = 0; i < buckets.length; ++i) {
            if (Number(buckets[i].good) + Number(buckets[i].bad) > 0)
                return i
        }
        return -1
    }

    onActiveFocusChanged: {
        if (activeFocus && hoveredIndex < 0)
            hoveredIndex = firstDataBucket()
        else if (!activeFocus && !pointerInside)
            hoveredIndex = -1
    }

    Keys.onLeftPressed: showPreviousBucket()
    Keys.onRightPressed: showNextBucket()
    Keys.onEscapePressed: hoveredIndex = -1

    Rectangle {
        anchors.fill: parent
        anchors.margins: -3
        radius: 10
        color: "transparent"
        border.width: root.activeFocus ? 2 : 0
        border.color: root.theme.signal
        z: 30
    }

    Item {
        id: plot
        anchors.fill: parent
        anchors.leftMargin: root.chartLeft
        anchors.rightMargin: root.chartRight
        anchors.topMargin: root.chartTop
        anchors.bottomMargin: root.chartBottom

        Repeater {
            model: 3

            Rectangle {
                required property int index
                x: 0
                y: index * (plot.height - 1) / 2
                width: plot.width
                height: 1
                color: root.theme.lineSoft
                opacity: index === 2 ? 0.9 : 0.65
            }
        }

        Repeater {
            model: root.buckets

            Item {
                id: slot
                required property int index
                required property var modelData

                readonly property real goodSeconds: Number(modelData.good)
                readonly property real badSeconds: Number(modelData.bad)
                readonly property real monitoredSeconds: goodSeconds + badSeconds
                readonly property real renderedHeight: monitoredSeconds > 0
                                                       ? Math.max(5, (plot.height - 8) * monitoredSeconds / root.maximumMonitored)
                                                       : 0

                x: index * root.slotWidth
                y: 0
                width: root.slotWidth
                height: plot.height
                Accessible.role: Accessible.Graphic
                Accessible.name: root.bucketSummary(modelData)

                Rectangle {
                    id: bar
                    width: Math.max(5, Math.min(20, slot.width * 0.55))
                    height: slot.renderedHeight
                    radius: Math.min(width / 2, 7)
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.bottom: parent.bottom
                    color: root.theme.surfaceInset
                    clip: true

                    Rectangle {
                        width: parent.width
                        height: slot.monitoredSeconds > 0
                                ? parent.height * slot.goodSeconds / slot.monitoredSeconds : 0
                        anchors.bottom: parent.bottom
                        color: root.theme.signal
                    }

                    Rectangle {
                        width: parent.width
                        height: slot.monitoredSeconds > 0
                                ? parent.height * slot.badSeconds / slot.monitoredSeconds : 0
                        anchors.top: parent.top
                        color: root.theme.danger
                    }
                }

                Rectangle {
                    visible: root.hoveredIndex === slot.index && slot.monitoredSeconds > 0
                    width: bar.width + 7
                    height: bar.height + 7
                    radius: bar.radius + 3
                    anchors.horizontalCenter: bar.horizontalCenter
                    anchors.verticalCenter: bar.verticalCenter
                    color: "transparent"
                    border.width: 2
                    border.color: root.theme.text
                }

                MouseArea {
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onEntered: {
                        root.pointerInside = true
                        root.hoveredIndex = slot.index
                    }
                    onExited: {
                        root.pointerInside = false
                        if (!root.activeFocus && root.hoveredIndex === slot.index)
                            root.hoveredIndex = -1
                    }
                    onClicked: {
                        root.hoveredIndex = slot.index
                        root.forceActiveFocus()
                    }
                }
            }
        }
    }

    Repeater {
        model: root.buckets

        Text {
            required property int index
            required property var modelData
            readonly property int showEvery: root.buckets.length === 24 ? 4
                                                   : root.buckets.length > 10 ? 5 : 1
            visible: index % showEvery === 0 || index === root.buckets.length - 1
            x: root.chartLeft + index * root.slotWidth
            y: root.height - root.chartBottom + 10
            width: root.slotWidth
            text: String(modelData.label)
            color: root.theme.muted
            font.family: root.theme.dataFont
            font.pixelSize: 9
            horizontalAlignment: Text.AlignHCenter
        }
    }

    Rectangle {
        id: tooltip
        objectName: "timelineTooltip"
        property string summaryText: root.hoveredIndex >= 0 && root.hoveredIndex < root.buckets.length
                                     ? root.bucketSummary(root.buckets[root.hoveredIndex]) : ""

        visible: root.hoveredIndex >= 0
                 && root.hoveredIndex < root.buckets.length
                 && Number(root.buckets[root.hoveredIndex].good)
                    + Number(root.buckets[root.hoveredIndex].bad) > 0
        z: 20
        width: 218
        height: tooltipContent.implicitHeight + 22
        radius: 12
        x: Math.max(0, Math.min(root.width - width,
                    root.chartLeft + (root.hoveredIndex + 0.5) * root.slotWidth - width / 2))
        y: 0
        color: root.theme.text
        border.color: Qt.alpha(root.theme.surface, 0.45)
        Accessible.role: Accessible.ToolTip
        Accessible.name: summaryText

        Column {
            id: tooltipContent
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: 11
            spacing: 4

            Text {
                width: parent.width
                text: root.hoveredIndex >= 0
                      ? String(root.buckets[root.hoveredIndex].detailLabel
                               || root.buckets[root.hoveredIndex].label) : ""
                color: root.theme.inkOnAccent
                font.family: root.theme.bodyFont
                font.pixelSize: 11
                font.weight: Font.DemiBold
            }
            Text {
                width: parent.width
                text: root.hoveredIndex >= 0
                      ? "監視  " + (root.buckets[root.hoveredIndex].monitoredText
                                    || root.formatDuration(Number(root.buckets[root.hoveredIndex].good)
                                                           + Number(root.buckets[root.hoveredIndex].bad))) : ""
                color: Qt.alpha(root.theme.inkOnAccent, 0.78)
                font.family: root.theme.bodyFont
                font.pixelSize: 10
            }
            Row {
                spacing: 12
                Text {
                    text: root.hoveredIndex >= 0
                          ? "● 良好 " + (root.buckets[root.hoveredIndex].goodText
                                         || root.formatDuration(root.buckets[root.hoveredIndex].good)) : ""
                    color: "#8FE0BC"
                    font.family: root.theme.bodyFont
                    font.pixelSize: 10
                }
                Text {
                    text: root.hoveredIndex >= 0
                          ? "● 悪い姿勢 " + (root.buckets[root.hoveredIndex].badText
                                              || root.formatDuration(root.buckets[root.hoveredIndex].bad)) : ""
                    color: "#FFAAA4"
                    font.family: root.theme.bodyFont
                    font.pixelSize: 10
                }
            }
            Text {
                text: root.hoveredIndex >= 0
                      ? "良好率  " + (root.buckets[root.hoveredIndex].ratioText || "—") : ""
                color: root.theme.inkOnAccent
                font.family: root.theme.dataFont
                font.pixelSize: 10
                font.weight: Font.Bold
            }
        }
    }

    Column {
        visible: !root.hasData
        anchors.centerIn: parent
        spacing: 5

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: "記録なし"
            color: root.theme.text
            font.family: root.theme.displayFont
            font.pixelSize: 15
            font.weight: Font.DemiBold
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: "監視データがありません"
            color: root.theme.muted
            font.family: root.theme.bodyFont
            font.pixelSize: 10
        }
    }
}
