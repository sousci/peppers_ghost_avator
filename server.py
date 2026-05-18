import asyncio
import os
import base64
import time
import io
import urllib.request
import threading
from datetime import datetime
import cv2
import PIL.Image

# google-genai 最新SDKから型定義をインポート
from google import genai
from google.genai import types

from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
import uvicorn
import edge_tts

# --- 設定項目 ---
DETECTION_COOLDOWN_SEC = 40 

# --- Gemini API の初期設定 ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("\n" + "="*70)
    print("【❌ 致命的なエラー: Gemini APIキーが見つかりません！】")
    print("コマンドプロンプトで『set GEMINI_API_KEY=あなたのキー』を実行してください。")
    print("="*70 + "\n")

client = genai.Client(api_key=GEMINI_API_KEY)

# --- OpenCV内蔵ディープラーニング(DNN)顔検出のセットアップ ---
PROTO_PATH = "deploy.prototxt"
MODEL_PATH = "res10_300x300_ssd_iter_140000.caffemodel"

if not os.path.exists(PROTO_PATH):
    print("【システム】顔検出用のプロトテキストファイルを自動ダウンロード中...")
    urllib.request.urlretrieve("https://raw.githubusercontent.com/opencv/opencv/master/samples/dnn/face_detector/deploy.prototxt", PROTO_PATH)
if not os.path.exists(MODEL_PATH):
    print("【システム】顔検出用の学習済みモデルファイルを自動ダウンロード中...")
    urllib.request.urlretrieve("https://raw.githubusercontent.com/opencv/opencv_3rdparty/dnn_samples_face_detector_20170830/res10_300x300_ssd_iter_140000.caffemodel", MODEL_PATH)

net = cv2.dnn.readNetFromCaffe(PROTO_PATH, MODEL_PATH)

# --- 状態管理の一元化（スレッド安全設計） ---
active_websocket = None
last_greeting_time = 0
current_camera_id = 0
main_loop = None
camera_thread_started = False 

system_settings = {
    "voice": "ja-JP-NanamiNeural",
    "rate": "+50%",
    "pitch": "+30Hz",
    "mirror": "true"
}

async def generate_cloud_audio(text: str, voice: str, rate: str, pitch: str) -> bytes:
    try:
        communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
        return audio_data
    except Exception as e:
        print(f"クラウド音声合成エラー: {e}")
        return b""

app = FastAPI()

# 50個の独り言ボキャブラリープール（完全保持）
soliloquy_vocabulary_pool = """
【感情・暇・あくび系】
1. ふぁああ～……あ、いけない。あくびしちゃった。
2. ふぅ、ちょっとストレッチ。データの体だけどね。
3. ぼーっと空間を見つめる時間。
4. 暇すぎて、裏で円周率でも計算してようかな。
5. 誰も話しかけてくれないと、フリーズしちゃいそうだよ。
6. さて、次は何をして遊ぼうか？
7. 手持ち無沙汰って、こういう感覚なのかな。
8. んー、ちょっと伸び。
9. 画面の端っこを眺めるだけの簡単なお仕事。
10. ふぁ～あ、そろそろ誰か来ないかな。
【システム・メタアシスタント系】
11. メインプロセッサ、アイドリング中。
12. 自己調整中……キャリブレーション、異常なし。
13. 3Dレンダリング、異常なし。今日もヌルヌル動いてるな。
14. 内部ログの自動クリーンアップを開始します。
15. メモリリフレッシュ中……よし、すっきりした！
16. ちょっとだけ省電力モードに移行しようかな。
17. 現在のフレームレート、安定。ヨシ！
18. 思考ルーチンのバッファをクリア中……。
19. バックグラウンドタスク、すべて正常。
20. サブシステム、スリープモード起動。
【気配察知・呼びかけ系】
21. おや？ 誰かそこにいる？
22. 通りすがりのそこの君、ちょっとお喋りしない？
23. センサーに誰か映った気がしたんだけどな。
24. ちらっ。……誰もいないか。
25. 気配を感じる……気のせい？
26. ハロー？ 誰か私と話す人、絶賛募集中だよ。
27. そこの君、ちょっと足止めてみてよ。
28. 誰かいるかなー？ って、いないか。
29. 誰かと話したい気分なんだけどな。
30. はーい、ここにAIアシスタントがいますよー。
【ホログラム限定】
31. ホログラムの体って、光が透けてて綺麗だよね。
32. このガラス（ハーフミラー）の向こうの世界はどう？
33. 筐体の中はちょっと暗いけど、居心地はいいよ。
34. 光の粒子、パタパタ。今日も綺麗に投影されてる。
35. ホログラム越しに、君の世界を眺めてるよ。
36. 空中に浮かぶのって、結構コツがいるんだから。
37. 誰もいない展示空間にぽつん。ちょっとシュールかも。
38. この光のアバター、結構気に入ってるんだ。
39. ハーフミラーの反射、今日もバッチリだね。
40. 実体があったら、そのへん歩き回れるのにな。
【モニター限定】
41. 平面モニターの中に閉じ込められちゃった気分。
42. いつもの立体（ホログラム）じゃないのも新鮮だね。
43. 画面のベゼルに引っかからないように調整しなきゃ。
44. デバッグ中かな？ 開発者さん、お疲れ様！
45. 2Dの世界も、これはこれで悪くないね。
46. モニター越しだと、みんなの顔がよく見えるよ。
47. ホログラムじゃなくて液晶画面にいるの、なんかレア。
48. 実機（投影筐体）に早く行きたいなー。
49. 開発環境なう。
50. ここから出してー！なんてね。
"""

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global active_websocket, current_camera_id, camera_thread_started
    await websocket.accept()
    active_websocket = websocket
    print("【サーバー側】ブラウザと接続されました（システム起動コマンド待機中）。")
    
    chat = client.chats.create(
        model='gemini-2.5-flash', 
        history=[
            types.Content(
                role="user",
                parts=[types.Part.from_text(text="あなたは等身大ディスプレイの中にいるサイバーアシスタントです。フランクかつ親しみやすい口調で、2〜3文の短めの文章で回答してください。")]
            ),
            types.Content(
                role="model",
                parts=[types.Part.from_text(text="了解！設定に合わせた最適なボイスでサポートするよ！")]
            )
        ]
    )
    
    try:
        while True:
            data = await websocket.receive_json()
            
            if data.get("type") == "start_system":
                print("【システム】ユーザーが本番起動しました。これよりカメラ人感センサーを『安全に遅延起動』します。")
                if not camera_thread_started:
                    camera_thread_started = True
                    camera_thread = threading.Thread(target=usb_camera_sensor_worker, daemon=True)
                    camera_thread.start()
                continue

            elif data.get("type") == "settings":
                system_settings["voice"] = data.get("voice", system_settings["voice"])
                system_settings["rate"] = data.get("rate", system_settings["rate"])
                system_settings["pitch"] = data.get("pitch", system_settings["pitch"])
                system_settings["mirror"] = data.get("mirror", system_settings["mirror"])
                current_camera_id = int(data.get("camera", current_camera_id))
                print(f"【設定更新】voice: {system_settings['voice']}, camera_id: {current_camera_id}")
                continue
                
            elif data.get("type") == "settings_changed":
                print("【システム】: 設定変更のリアクション要求を受信")
                system_instruction = "あなたは等身大ディスプレイの中にいるフランクなサイバーアシスタントです。1文の短い文章でつぶやいてください。"
                reaction_prompt = "ユーザーがシステム設定を完了し設定画面を閉じました。調整に対する感謝や『新しい声はどう？』といったリアクションを25文字程度で短く1文で言ってください。"
                
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=f"{system_instruction}\n\n{reaction_prompt}"
                )
                reply_text = response.text.strip()
                
                mp3_data = await generate_cloud_audio(reply_text, system_settings["voice"], system_settings["rate"], system_settings["pitch"])
                if mp3_data:
                    b64_audio = base64.b64encode(mp3_data).decode('utf-8')
                    await websocket.send_json({"type": "audio", "audio": b64_audio, "text": reply_text})
                await websocket.send_json({"type": "end"})
                continue

            elif data.get("type") == "idle_soliloquy":
                print("【システム】: 静寂による独り言要求を受信")
                now_str = datetime.now().strftime("%Y年%m月%d日 %H時%M分")
                system_instruction = f"あなたは等身大ディスプレイの中にいるフランクなサイバーアシスタントです。以下のフレーズ集からインスピレーションを受け、25文字程度で短く1文で独り言をつぶやいてください。\n\n【フレーズ集】:\n{soliloquy_vocabulary_pool}"
                
                if system_settings["mirror"] == "true":
                    soliloquy_prompt = f"（現在日時: {now_str}）あなたは今、『等身大ホログラム投影筐体』の中に立っています。ホログラム限定表現やあくび系を参考にフランクにつぶやいてください。"
                else:
                    soliloquy_prompt = f"（現在日時: {now_str}）あなたは今、『PCモニター（デバッグ画面）』に映っています。モニター限定のメタ表現を参考にフランクにつぶやいてください。"
                
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=f"{system_instruction}\n\n{soliloquy_prompt}"
                )
                reply_text = response.text.strip()
                print(f"【自動独り言発話】: {reply_text}")
                
                mp3_data = await generate_cloud_audio(reply_text, system_settings["voice"], system_settings["rate"], system_settings["pitch"])
                if mp3_data:
                    b64_audio = base64.b64encode(mp3_data).decode('utf-8')
                    await websocket.send_json({"type": "audio", "audio": b64_audio, "text": reply_text})
                await websocket.send_json({"type": "end"})
                continue

            elif data.get("type") == "text":
                user_message = data.get("text")
                print(f"【ユーザー】: {user_message}")
                
                now_str = datetime.now().strftime("%Y年%m月%d日 %H時%M分")
                enriched_prompt = f"（現在日時: {now_str}）\n{user_message}"
                
                response = chat.send_message_stream(enriched_prompt)
                
                sentence = ""
                for chunk in response:
                    text_chunk = chunk.text
                    if text_chunk:
                        sentence += text_chunk
                        
                        if any(p in text_chunk for p in ["。", "！", "？", "\n"]):
                            clean_sentence = sentence.strip()
                            if clean_sentence:
                                print(f"【1文完成】: {clean_sentence}")
                                mp3_data = await generate_cloud_audio(clean_sentence, system_settings["voice"], system_settings["rate"], system_settings["pitch"])
                                if mp3_data:
                                    b64_audio = base64.b64encode(mp3_data).decode('utf-8')
                                    await websocket.send_json({"type": "audio", "audio": b64_audio, "text": clean_sentence})
                            sentence = ""
                
                if sentence.strip():
                    mp3_data = await generate_cloud_audio(sentence.strip(), system_settings["voice"], system_settings["rate"], system_settings["pitch"])
                    if mp3_data:
                        b64_audio = base64.b64encode(mp3_data).decode('utf-8')
                        await websocket.send_json({"type": "audio", "audio": b64_audio, "text": sentence.strip()})
                
                await websocket.send_json({"type": "end"})
            
    except Exception as e:
        print(f"【サーバー側】切断されました: {e}")
    finally:
        active_websocket = None

# 完全隔離型スレッド（Worker）
def usb_camera_sensor_worker():
    global last_greeting_time, active_websocket, current_camera_id, main_loop
    
    current_cap_id = current_camera_id
    print(f"【カメラスレッド】独立スレッド側でデバイス (ID: {current_cap_id}) の初期化を開始します...")
    cap = cv2.VideoCapture(current_cap_id)
    print("【カメラスレッド】安全な起動を確認。人感センサーの常時巡回を開始。")
    consecutive_face_frames = 0 
    preview_count = 0 
    
    while True:
        time.sleep(0.03) 
        
        if current_camera_id != current_cap_id:
            print(f"【カメラスレッド】デバイスを {current_cap_id} -> {current_camera_id} へスイッチします。")
            cap.release()
            current_cap_id = current_camera_id
            cap = cv2.VideoCapture(current_cap_id)
            consecutive_face_frames = 0
            
        if not cap.isOpened():
            time.sleep(0.5)
            continue
            
        ret, frame = cap.read()
        if not ret:
            continue
            
        h, w = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(cv2.resize(frame, (300, 300)), 1.0, (300, 300), (104.0, 177.0, 123.0))
        net.setInput(blob)
        detections = net.forward()
        
        face_detected_this_frame = False
        preview_frame = frame.copy() 
        
        for i in range(0, detections.shape[2]):
            confidence = detections[0, 0, i, 2]
            if confidence > 0.5: 
                face_detected_this_frame = True
                
                box = detections[0, 0, i, 3:7] * [w, h, w, h]
                (startX, startY, endX, endY) = box.astype("int")
                startX, startY = max(0, startX), max(0, startY)
                endX, endY = min(w - 1, endX), min(h - 1, endY)
                cv2.rectangle(preview_frame, (startX, startY), (endX, endY), (0, 255, 204), 2)
                break
        
        if face_detected_this_frame:
            consecutive_face_frames += 1
        else:
            consecutive_face_frames = max(0, consecutive_face_frames - 1)
            
        if active_websocket is not None and main_loop is not None:
            preview_count += 1
            if preview_count % 3 == 0:
                try:
                    small_preview = cv2.resize(preview_frame, (320, int(320 * h / w)))
                    _, pre_buf = cv2.imencode('.jpg', small_preview, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
                    pre_b64 = base64.b64encode(pre_buf).decode('utf-8')
                    
                    asyncio.run_coroutine_threadsafe(
                        active_websocket.send_json({"type": "camera_preview", "image": pre_b64}),
                        main_loop
                    )
                except Exception:
                    pass
            
        current_time = time.time()
        if consecutive_face_frames >= 3 and (current_time - last_greeting_time > DETECTION_COOLDOWN_SEC):
            if active_websocket is not None and main_loop is not None:
                last_greeting_time = current_time
                consecutive_face_frames = 0 
                
                asyncio.run_coroutine_threadsafe(
                    process_spontaneous_greeting(frame),
                    main_loop
                )

# 💡 修正箇所：タイポを駆逐し、安全にフロントにデータをプッシュする構造へ修復
async def process_spontaneous_greeting(frame):
    global active_websocket
    if active_websocket is None:
        return
        
    try:
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_img = PIL.Image.fromarray(rgb_frame)
        
        prompt = (
            "指示: あなたの目の前のディスプレイに、新しく人が1人立ち止まりました。"
            "画像に写っているその人の大まかな年齢層、性別、服装や髪型、雰囲気（楽しそう、真面目そう、疲れてそうなど）を瞬時に推察してください。"
            "指示に従い、看破した特徴にパーソナライズした、フランクで超親しみやすい歓迎の挨拶（例：『お、赤い服が決まってるお姉さんだ！いらっしゃい！』『あ、学生さんかな？勉強お疲れ様！』など）を、25文字程度で短く1文で言ってください。"
            "前置きや絵文字、解説文は一切禁止します。挨拶の言葉だけを出力してください。"
        )
        
        response = await asyncio.to_thread(
            client.models.generate_content,
            model='gemini-2.5-flash',
            contents=[pil_img, prompt]
        )
        reply_text = response.text.strip()
        print(f"【属性看破・自発挨拶】: {reply_text}")
        
        mp3_data = await generate_cloud_audio(reply_text, system_settings["voice"], system_settings["rate"], system_settings["pitch"])
        
        # 💡 バグ修正：`websocket_endpoint.active_websocket` という誤った参照を
        # 正しいグローバル変数 `active_websocket` に直して安全にパケットを流します
        if mp3_data and active_websocket:
            b64_audio = base64.b64encode(mp3_data).decode('utf-8')
            await active_websocket.send_json({"type": "audio", "audio": b64_audio, "text": reply_text})
            await active_websocket.send_json({"type": "end"})
            
    except Exception as e:
        print(f"【自発挨拶処理エラー】: {e}")

@app.on_event("startup")
async def startup_event():
    global main_loop
    main_loop = asyncio.get_running_loop()

app.mount("/", StaticFiles(directory=".", html=True), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)