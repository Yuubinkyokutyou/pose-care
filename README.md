# PoseCare

PCカメラで上半身の姿勢を監視し、登録した悪い姿勢が続いたときにWindows通知を出す、最小構成の常駐アプリです。通知しない姿勢も登録でき、一致する状態は通知から除外します。

画面はPySide6 + Qt Quick/QMLで構築し、カメラはWindows MediaCaptureの
`SharedReadOnly` モード、姿勢判定はMediaPipeで処理しています。

## 主な機能

- MediaPipe Pose Landmarkerによる端末内の上半身姿勢推定
- Windows共有カメラAPIを使用し、Windows Helloなど他機能のカメラ利用を妨げない
- 悪い姿勢を複数登録（画像は保存せず、正規化した特徴量のみ保存）
- 通知しない姿勢も複数登録し、近い状態を通知候補から除外
- 一定時間、登録姿勢に近い状態が続いた場合だけ通知
- ネイティブWindowsトースト通知と設定画面からのテスト送信
- メイン画面に骨格・中心線・内部指標をリアルタイム表示
- 最小化／閉じる操作でタスクトレイに常駐
- 設定画面からWindowsログイン時の自動起動をオン／オフ
- 人が映らずPC操作も5分間ない場合はカメラを解放し、操作再開時に自動復帰
- 閉じてバックグラウンドへ移ると通知判定を再開し、良い姿勢が8秒続いた場合も再通知可能に復帰
- 良い姿勢の割合、監視時間、悪い姿勢、通知回数を1日・7日・30日で表示し、日付を前後に切り替え
- 時間別／日別の推移をカーソルで詳しく確認し、登録した悪い姿勢ごとの検知時間も表示
- 感度、判定時間、通知間隔、カメラ番号の設定
- 設定画面からGitHub Releasesの最新版を確認・ダウンロード・再起動更新
- カメラ映像・骨格座標の保存やクラウド送信なし

## 動作環境

- Windows 10 / 11（64 bit）
- Python 3.12
- Webカメラ

## インストール

GitHub Releasesから `PoseCareSetup-windows-x64.exe` をダウンロードして実行します。
管理者権限は不要で、アプリ本体は次のユーザー専用領域へ固定でインストールされます。

```text
%LOCALAPPDATA%\Programs\PoseCare
```

セットアップはスタートメニューと、選択に応じてデスクトップへショートカットを作成します。以前のZIP展開版を使っている場合は、先にタスクトレイのPoseCareアイコンを右クリックして「終了」を選んでからセットアップを実行してください。設定・履歴はそのまま引き継がれます。セットアップ後に新しいショートカットから起動できることを確認したら、以前展開した `PoseCare` フォルダーと、その隣にある旧更新キャッシュ `.PoseCare.updates` は削除できます。

## 開発環境のセットアップ

PowerShellで次を実行します。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\run.ps1
```

初回のみ、Google公式のPose Landmarker Liteモデル（約6 MB）をダウンロードします。その後の推論はローカルで行われます。

## 使い方

1. 頭・両肩・胸元が映るように座り、初回起動の案内に従って悪い姿勢を3秒間保ちます。
2. メイン画面の「監視を開始」をオンにします。
3. ウィンドウを閉じてもアプリはタスクトレイで監視を続けます。
4. 姿勢を追加・削除したい場合は「設定」を開きます。「通知しない姿勢を追加」から、通知したくない普段の姿勢を登録できます。
5. 通知が表示されるか確認する場合は、設定の「テスト通知」を押します。
6. Windowsへのログイン時にも起動する場合は、設定の「Windowsログイン時にPoseCareを起動する」をオンにして保存します。
7. アプリを更新する場合は、設定の「アプリの更新」で「更新を確認」を押します。最新版がある場合はダウンロード後、「再起動して更新」を押します。
8. 完全終了はタスクトレイのPoseCareアイコンを右クリックし、「終了」を選びます。

> 姿勢推定は健康管理の補助機能です。医療上の診断には使用できません。逆光を避け、頭・両肩・胸元がカメラに入る位置で使用してください。腰や脚が映る必要はありません。

## 設定・データの保存先

次のデータをすべてPC内だけに保存します。クラウドへの送信は行いません。

- `%LOCALAPPDATA%\PoseCare\settings.json`: 設定と登録姿勢の正規化済み特徴量
- `%LOCALAPPDATA%\PoseCare\posture_history.sqlite3`: 判定区間、該当した登録姿勢名、姿勢通知の時刻
- `%LOCALAPPDATA%\PoseCare\models`: 姿勢推定モデル
- `%LOCALAPPDATA%\PoseCare\updates`: 自動更新の一時ファイルと更新ログ

統計履歴はSQLiteで管理し、400日を超えたデータは起動時に自動削除します。カメラ画像、骨格座標、顔画像は保存しません。
アプリ本体は `%LOCALAPPDATA%\Programs\PoseCare` に保存し、デスクトップやアプリ本体の親フォルダーへ更新ファイルは作成しません。

## テスト

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## WindowsアプリとセットアップEXEの作成（任意）

事前にPythonの開発依存関係とInno Setupをインストールします。

```powershell
.\scripts\build.ps1
```

`dist\PoseCare\PoseCare.exe` と `dist\installer\PoseCareSetup-windows-x64.exe` が生成されます。アプリ本体だけを確認する場合は `build.ps1 -SkipInstaller` を指定できます。モデルは初回起動時にユーザー領域へダウンロードされます。

## GitHub Releasesへの自動公開

`main` ブランチへ変更が入ると、GitHub Actionsがテスト、Windows x64版のビルド、SHA-256生成、GitHub Releaseの公開までを実行します。手動実行にも対応しています。

Releaseには次の5ファイルが添付されます。

- `PoseCareSetup-windows-x64.exe`: ユーザーが実行するインストーラー
- `PoseCareSetup-windows-x64.exe.sha256`: インストーラーのSHA-256
- `PoseCare-update-windows-x64.zip`: アプリ内の自動更新専用パッケージ
- `PoseCare-update-windows-x64.zip.sha256`: アプリが更新前に照合するSHA-256
- `release.json`: バージョン、ビルド番号、コミットの情報

タグは `v<version>-build.<Actions run ID>.<再実行番号>` の形式です。通常のインストールにはセットアップEXEを使い、更新ZIPは手動展開しません。設定画面の自動更新はセットアップ版の `PoseCare.exe` で利用できます。ソースから `run.ps1` で起動している開発環境や、管理対象外の場所へ直接置いたexeではファイルの自動置換を行いません。
