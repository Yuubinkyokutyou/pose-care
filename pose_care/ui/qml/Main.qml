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
    // The controller is intentionally supplied as a root context property by Python.
    // qmllint disable unqualified
    property var appController: controller
    // qmllint enable unqualified

    QtObject {
        id: theme

        property color canvas: "#EFF4F0"
        property color nav: "#E8F0EB"
        property color surface: "#FBFDFC"
        property color surfaceHigh: "#EDF4EF"
        property color surfaceInset: "#F0F5F1"
        property color surfaceHover: "#E2ECE5"
        property color surfacePressed: "#D6E3DA"
        property color line: "#C9D7CE"
        property color lineSoft: "#DEE7E1"
        property color text: "#17241C"
        property color muted: "#5F6F66"
        property color signal: "#1F7355"
        property color signalHover: "#2B8465"
        property color signalPressed: "#185C43"
        property color blue: "#3D7088"
        property color amber: "#9A6729"
        property color danger: "#B94D49"
        property color control: "#D6E1DA"
        property color controlLine: "#B7C8BD"
        property color inkOnAccent: "#FFFFFF"
        property string displayFont: "Bahnschrift SemiCondensed"
        property string bodyFont: "Yu Gothic UI"
        property string dataFont: "Cascadia Mono"
    }

    onClosing: function(close) {
        close.accepted = root.appController.requestClose()
    }

    Connections {
        target: root.appController
        function onNavigateRequested(page) { root.currentPage = page }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        NavigationRail {
            Layout.preferredWidth: 168
            Layout.fillHeight: true
            theme: root.appTheme
            currentPage: root.currentPage
            onPageRequested: function(page) {
                root.currentPage = page
                if (page === 1)
                    root.appController.refreshStatistics()
            }
        }

        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: root.currentPage

            MonitorPage {
                controller: root.appController
                theme: root.appTheme
            }

            StatisticsPage {
                controller: root.appController
                theme: root.appTheme
            }

            SettingsPage {
                controller: root.appController
                theme: root.appTheme
                onDeleteRequested: function(profileId, profileName) {
                    deletePopup.profileId = profileId
                    deletePopup.profileName = profileName
                    deletePopup.open()
                }
            }
        }
    }

    RegistrationPopup {
        controller: root.appController
        theme: root.appTheme
        hostWindow: root
    }

    DeleteProfilePopup {
        id: deletePopup
        controller: root.appController
        theme: root.appTheme
        hostWindow: root
    }
}
