# Pepper's Ghost Avatar (開発版)

FastAPI バックエンドと Three.js + VRM フロントエンドを組み合わせた、対話型アバターシステムです。  
Gemini (`gemini-2.5-flash`) で会話生成し、`edge-tts` で音声合成を行います。

## 現在の実装ステータス（2026-05-23時点）

### 1. 会話入力
- Web Speech API による音声入力
- 画面下のテキスト入力フォームによる入力

### 2. 会話応答
- Gemini による会話生成
- 感情タグ（`[emotion:...]`）に応じたモーション再生
- edge-tts による音声再生

### 3. カメラ連携
- OpenCV / MediaPipe による人物・物体検知
- プレビュー画像をWebSocketでフロントへ配信
- 一定条件での自発話（独り言）
- 会話中の割り込み抑制（アイドル猶予 + クールダウン）

### 4. Visionオンデマンド再生成（新規）
- まず通常応答（テキスト）で処理
- 必要時のみ `vision` 判定でカメラ画像参照を要求
- 要求時だけ最新カメラフレームを Gemini へ渡し、再生成して回答

### 5. オプションUI
- `Esc` でシステムオプション表示
- カメラ切替（動的列挙）
- ミラー表示
- TTS（Voice / Rate / Pitch）
- アバター見た目（Brightness / Contrast / Saturate）
- アバター配置（X / Y / Scale）

## 機能一覧（実装済み）

### 音声・テキストコマンド
- `scale`: `UP` / `DOWN`
- `mirror`: `TOGGLE`
- `camera`: `TOGGLE` / `INTERNAL` / `USB` / `0` `1` などID指定
- `rate`: `FASTER` / `SLOWER`
- `vision`: `REQUEST_FRAME`（内部制御用）

### UI/UX
- 待機メッセージ（「話しかけてください」）は最新位置のみ表示
- ソラ発話の行間を拡張（視認性改善）

### ログ
- `APP_LOG_LEVEL` でログ下限を制御（`DEBUG` / `INFO` / `WARN` / `ERROR`）
- Vision判定結果、画像送信、Vision再生成テキストを `INFO` 出力

## 具体的な操作例（お手本入力）

### 起動確認
1. ブラウザで `http://localhost:8000/` を開く
2. `Space` で開始
3. マイク許可を与える

### 会話確認
- お手本入力: `今日はどんなことができる？`
- 期待動作: ソラが短文で返答し、音声再生される

### スケール変更
- お手本入力: `アバターを少し大きくして`
- 期待動作: `scale=UP` が実行され、アバターが拡大

### カメラ切替（名称）
- お手本入力: `USBカメラに切り替えて`
- 期待動作: `camera=USB` が実行され、該当カメラへ切替

### カメラ切替（ID）
- お手本入力: `カメラ1にして`
- 期待動作: `camera=1` が実行され、ID1へ切替

### ミラー切替
- お手本入力: `左右反転を切り替えて`
- 期待動作: `mirror=TOGGLE` が実行される

### 話速変更
- お手本入力: `もう少し早口で`
- 期待動作: `rate=FASTER` が実行される

### Visionオンデマンド確認（OBS仮想カメラ利用可）
- 例: OBS Virtual Camera を選択し、アバター画面を映す
- お手本入力: `今の見た目、どう見えてる？`
- 期待動作:
  - Vision判定ログが出る
  - 必要時にカメラ画像をGeminiへ送信
  - 画像文脈を使った再生成回答を返す

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
# 任意: ログ下限（未指定時は INFO）
$env:APP_LOG_LEVEL="INFO"
```

## 起動

```powershell
python app.py
```

ブラウザ:

```text
http://localhost:8000/
```

## ディレクトリ構成

```text
peppers_ghost_avator/
├─ app.py                 # FastAPI + WebSocket + Gemini連携（会話/Vision判定）
├─ camera.py              # カメラ処理・検知・プレビュー/最新フレーム共有
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

## 既知の制約

- 音声/テキストコマンドでの VRM 位置（X/Y）変更は未実装（UIスライダーのみ）
- `enumerateDevices()` の順序と OpenCV カメラインデックスは環境により一致しない場合がある
- Vision再生成は最新フレーム未取得時にテキスト応答へフォールバック
