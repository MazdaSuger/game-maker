# 配布用ビルド（Mac DMG / Windows EXE）

ノベルメーカー本体を各OS向けの実行ファイルにパッケージ化します。
PyInstaller は **実行する OS のバイナリしか生成できない** ため、
各プラットフォームでビルドします（クロスコンパイル不可）。

## かんたん: GitHub Actions でビルド（推奨）

リポジトリの **Actions → Build Desktop Apps → Run workflow** を実行すると、
macOS / Windows / Linux のランナー上でビルドし、成果物を Artifacts に出力します。

- `NovelMaker-macos-universal.dmg` … **universal2**（Intel + Apple Silicon 両対応）
- `NovelMaker-windows-x64.zip` … Windows 用（解凍して `NovelMaker.exe` を実行）
- `NovelMaker-linux-x64.tar.gz` … Linux 用

`v1.0.0` のような **タグを push** すると、ビルド完了後に自動で
**GitHub Release を作成**し、成果物（dmg / zip / tar.gz）を添付します。

```bash
git tag v1.0.0
git push origin v1.0.0
```

タグを切らずにリリースしたい場合は、**Actions → Build Desktop Apps →
Run workflow** で **「リリースタグ」** を入力して実行します（例: `v1.0.0`）。
入力したタグが無ければ自動で作成され、Release が公開されます
（「プレリリースとして公開する」も選べます）。入力を空にするとビルドのみ
（Artifacts に出力）です。

## 手元でビルド

共通の前準備:

```bash
pip install -r requirements.txt pyinstaller
```

### macOS（universal DMG）

```bash
pyinstaller --noconfirm packaging/novelmaker.spec
# → dist/NovelMaker.app （universal2）

# DMG を作成
hdiutil create -volname NovelMaker -srcfolder dist/NovelMaker.app \
  -ov -format UDZO NovelMaker-macos-universal.dmg
```

> universal2 でビルドするには、universal2 版の Python と PySide6 が必要です
> （python.org 配布の Python と PyPI の PySide6 wheel は universal2 対応）。
> アーキテクチャ確認: `lipo -archs dist/NovelMaker.app/Contents/MacOS/NovelMaker`

### Windows（EXE）

```powershell
pyinstaller --noconfirm packaging/novelmaker.spec
# → dist\NovelMaker\NovelMaker.exe （ワンフォルダ）
Compress-Archive -Path dist/NovelMaker/* -DestinationPath NovelMaker-windows-x64.zip
```

### Linux

```bash
pyinstaller --noconfirm packaging/novelmaker.spec
# → dist/NovelMaker/NovelMaker
```

## アイコン（任意）

`packaging/icon.icns`（macOS）・`packaging/icon.ico`（Windows）を置くと、
spec が自動で取り込みます。無くてもビルドできます。

## 備考

- `web/`（ブラウザ書き出し用ランタイム）はアプリに同梱されるため、
  パッケージ後も「ブラウザ(HTML)に書き出し」機能が動作します。
- macOS 配布時は Gatekeeper 対策の署名/公証（codesign / notarize）を
  別途行うと、初回起動の警告を回避できます（spec の `codesign_identity` 等）。
