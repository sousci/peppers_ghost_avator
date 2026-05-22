# Pepper's Ghost Avatar (開発版)

FastAPI バックエンドと Three.js + VRM フロントエンドを組み合わせた、対話型アバターシステムです。  
Gemini (`gemini-2.5-flash`) で会話生成し、`edge-tts` で音声合成を行います。

## 現在の実装ステータス（2026-05-23時点）

- 会話入力
  - Web Speech API による音声入力
  - 画面下のテキスト入力フォームによる入力
- 会話応答
  - Gemini による応答文生成
  - 応答に応じた表情モーション切替（emotion タグ）
  - edge-tts による音声再生
- カメラ連携
  - OpenCV ベースの人物/顔検知
  - プレビュー画像を WebSocket 経由でフロントへ配信
  - 一定条件で自発話（ウェルカム/ソリロクイ）
- システム設定（Esc オーバーレイ）
  - カメラ切替
  - ミラー表示
  - TTS（Voice / Rate / Pitch）
  - アバター見た目（Brightness / Contrast / Saturate）
  - アバター配置（X / Y / Scale）

## 重要: コマンド対応範囲（開発中仕様）

音声入力/テキスト入力からの「コマンド実行」は、現在次のみ対応しています。

- `scale` (`UP` / `DOWN`)
- `mirror` (`TOGGLE`)
- `camera` (`TOGGLE`)
- `rate` (`FASTER` / `SLOWER`)

未対応:

- `position`（`X/Y` の音声・テキストコマンド変更）

補足:

- `X/Y` の位置調整は、現時点では **Esc のオプションUIスライダーでのみ** 反映されます。

## ディレクトリ構成

```text
peppers_ghost_avator/
├─ app.py                 # FastAPI + WebSocket + Gemini連携
├─ camera.py              # カメラ処理・検知・プレビュー送信
├─ config.py              # 設定/共有状態
├─ requirements.txt       # Python依存
├─ static/
│  ├─ index.html          # UI本体
│  ├─ main.js             # 音声入力・WebSocket・UIイベント
│  ├─ avatar.js           # Three.js / VRM描画・モーション
│  ├─ style.css           # スタイル
│  └─ *.vrm               # アバターモデル
└─ README.md
```

## セットアップ

### 1) 仮想環境

```powershell
python -m venv venv
venv\Scripts\Activate.ps1
```

### 2) 依存インストール

```powershell
pip install -r requirements.txt
```

### 3) 環境変数

```powershell
$env:GEMINI_API_KEY="<YOUR_API_KEY>"
```

## 起動

```powershell
python app.py
```

ブラウザで以下を開きます。

```text
http://localhost:8000/
```

## 基本操作

- `Space`: 初回起動/対話開始
- `Esc`: システムオプションの開閉
- マイク許可: ブラウザのマイク権限を許可

## 主な実装ファイル

- 会話ストリーミングと command 抽出: `app.py`
- コマンド実行（front）: `static/main.js` の `executeVoiceCommand()`
- VRM位置/スケール反映: `static/main.js` と `static/avatar.js`

## 既知の制約（開発段階）

- 音声/テキストコマンドでの VRM 位置（X/Y）変更は未実装
- 起動直後はカメラ/マイク権限状態により挙動が変わる
- ログ出力の一部に文字化けが残る場合がある（端末エンコーディング依存）
