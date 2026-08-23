import QtQuick

Item {
    id: root
    property var theme
    property var buckets: []
    property bool hasData: {
        var total = 0
        for (var i = 0; i < buckets.length; ++i)
            total += Number(buckets[i].good) + Number(buckets[i].bad)
        return total > 0
    }

    implicitHeight: 210

    Canvas {
        id: canvas
        anchors.fill: parent
        visible: root.hasData
        onWidthChanged: requestPaint()
        onHeightChanged: requestPaint()

        Connections {
            target: root
            function onBucketsChanged() { canvas.requestPaint() }
        }

        onPaint: {
            var ctx = getContext("2d")
            ctx.reset()
            var left = 8
            var right = 8
            var top = 12
            var bottom = 30
            var chartWidth = Math.max(1, width - left - right)
            var chartHeight = Math.max(1, height - top - bottom)

            ctx.strokeStyle = root.theme.lineSoft
            ctx.lineWidth = 1
            ctx.setLineDash([3, 5])
            for (var guide = 0; guide < 3; ++guide) {
                var gy = top + (chartHeight * guide / 2)
                ctx.beginPath()
                ctx.moveTo(left, gy)
                ctx.lineTo(left + chartWidth, gy)
                ctx.stroke()
            }
            ctx.setLineDash([])

            var count = root.buckets.length
            if (count === 0)
                return
            var slot = chartWidth / count
            var barWidth = Math.max(4, Math.min(18, slot * 0.58))
            for (var i = 0; i < count; ++i) {
                var bucket = root.buckets[i]
                var good = Number(bucket.good)
                var bad = Number(bucket.bad)
                var monitored = good + bad
                var capacity = Math.max(1, Number(bucket.capacity))
                var coverage = Math.min(1, monitored / capacity)
                var totalHeight = chartHeight * coverage
                var goodHeight = monitored > 0 ? totalHeight * good / monitored : 0
                var badHeight = Math.max(0, totalHeight - goodHeight)
                var x = left + i * slot + (slot - barWidth) / 2
                var base = top + chartHeight

                if (goodHeight > 0.5) {
                    ctx.fillStyle = root.theme.signal
                    ctx.fillRect(x, base - goodHeight, barWidth, goodHeight)
                }
                if (badHeight > 0.5) {
                    ctx.fillStyle = root.theme.danger
                    ctx.fillRect(x, base - totalHeight, barWidth, badHeight)
                }

                var showEvery = count === 24 ? 4 : count > 10 ? 5 : 1
                if (i % showEvery === 0 || i === count - 1) {
                    ctx.fillStyle = root.theme.muted
                    ctx.font = "10px 'Segoe UI'"
                    ctx.textAlign = "center"
                    ctx.fillText(String(bucket.label), left + i * slot + slot / 2, height - 7)
                }
            }
        }
    }

    Text {
        visible: !root.hasData
        anchors.centerIn: parent
        text: "表示できる統計はまだありません"
        color: theme.muted
        font.family: theme.bodyFont
        font.pixelSize: 12
    }
}
