"""Collect Qt QML plugins except the unused WebEngine module."""

from pathlib import PurePath

from PyInstaller.utils.hooks.qt import add_qt6_dependencies
from PyInstaller.utils.hooks.qt import pyside6_library_info


def _is_webengine_qml_file(entry: tuple[str, str]) -> bool:
    destination = PurePath(entry[1].replace("\\", "/"))
    return "QtWebEngine" in destination.parts


hiddenimports, binaries, datas = add_qt6_dependencies(__file__)
qml_binaries, qml_datas = pyside6_library_info.collect_qtqml_files()

# PyInstaller's stock QtQml hook collects every QML module shipped by PySide6.
# PoseCare does not import QtWebEngine, so skip its plugin before dependency
# analysis pulls the 194 MiB Qt6WebEngineCore.dll into the application.
binaries += [entry for entry in qml_binaries if not _is_webengine_qml_file(entry)]
datas += [entry for entry in qml_datas if not _is_webengine_qml_file(entry)]
