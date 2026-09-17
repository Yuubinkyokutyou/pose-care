from __future__ import annotations

import json
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from pose_care.history import PostureHistory


RESTORE_INSTRUCTIONS = """PoseCare 別端末への移行

内容: settings.json（設定・通知対象/通知しない登録姿勢の全特徴量）、
posture_history.sqlite3（保存されている全期間の判定区間・姿勢名・通知履歴）。
削除済みの履歴は含まれません。通常、履歴の保存期間は400日です。
カメラ画像、モデル、更新キャッシュ、Windowsの自動起動登録は含みません。

1. 移行先に同じバージョン以降のPoseCareをインストールします。
2. 移行先のPoseCareをタスクトレイから「終了」します。
3. エクスプローラーで %LOCALAPPDATA% を開き、既存のPoseCareフォルダーを
   PoseCare-before-migration など別名に変更して退避します。
   （既存のSQLiteの-wal/-shmファイルを新しいデータと混在させないためです。）
4. 新しいPoseCareフォルダーを作り、このZIPのsettings.jsonと
   posture_history.sqlite3をその直下へコピーします。
5. PoseCareを起動し、登録姿勢と統計を確認します。必要に応じてカメラ番号と
   Windowsログイン時の自動起動を設定し直してください。

移行は置き換えです。移行先の既存データとの統合は行いません。
初回起動時に姿勢推定モデルを再ダウンロードします。
"""


def export_backup(history: PostureHistory, settings_json: str, destination: Path) -> None:
    """Publish a complete ZIP atomically; call on the history connection's thread."""
    if destination.suffix.lower() != ".zip":
        raise ValueError("保存先には.zipファイルを指定してください")
    if destination.resolve() == history.path.resolve():
        raise ValueError("履歴データベースには上書きできません")
    # Validate before touching the destination. The caller freezes settings on
    # the GUI thread so subsequent profile edits cannot change this snapshot.
    json.loads(settings_json)
    with tempfile.TemporaryDirectory(prefix=".posecare-export-", dir=destination.parent) as folder:
        temporary = Path(folder)
        database = temporary / "posture_history.sqlite3"
        history.backup(database)
        archive = temporary / "backup.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
            output.write(database, "posture_history.sqlite3")
            output.writestr("settings.json", settings_json)
            output.writestr("移行手順.txt", RESTORE_INSTRUCTIONS)
            output.writestr("manifest.json", json.dumps({
                "format": "pose-care-backup",
                "version": 1,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }, indent=2) + "\n")
        archive.replace(destination)
