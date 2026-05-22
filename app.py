import asyncio
import base64
import threading
import re
import os
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
import uvicorn
import edge_tts
from google import genai
from google.genai import types

import config
from camera import CameraSensor

camera_sensor = None

def custom_log(level: str, tag: str, message: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    colors = {"GEMINI": "\033[92m", "SYSTEM": "\033[92m", "CAMERA": "\033[94m"}
    lvl_colors = {"INFO  ": "", "WARN  ": "\033[93m", "ERROR ": "\033[91m"}
    reset = "\033[0m"
    
    t_color = colors.get(tag, reset)
    l_color = lvl_colors.get(level, reset)
    print(f"[{timestamp}] {l_color}[{level}]{reset}{t_color}[{tag}]{reset} {message}")

async def retry_async_task(task_func, *args, max_retries=3, base_delay=1, **kwargs):
    for attempt in range(1, max_retries + 1):
        try:
            return await task_func(*args, **kwargs)
        except Exception as e:
            if attempt == max_retries:
                raise e
            custom_log("WARN  ", "SYSTEM", f"ネットワーク瞬断検知（リトライ {attempt}/{max_retries} 回目）: {e}")
            await asyncio.sleep(base_delay * attempt)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global camera_sensor
    config.main_loop = asyncio.get_running_loop()
    yield
    if camera_sensor:
        custom_log("INFO  ", "SYSTEM", "アプリケーション終了処理（ハードウェアリソースの解放）")
        camera_sensor.stop()
        await asyncio.sleep(0.5)

app = FastAPI(lifespan=lifespan)
client = genai.Client(api_key=config.GEMINI_API_KEY)

async def generate_cloud_audio(text: str, voice: str, rate: str, pitch: str) -> bytes:
    async def _execute():
        communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
        return audio_data

    try:
        return await retry_async_task(_execute)
    except Exception as e:
        custom_log("ERROR ", "SYSTEM", f"音声合成（edge-tts）の完全失敗: {e}")
        return b""

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global camera_sensor
    await websocket.accept()
    config.active_websocket = websocket
    custom_log("INFO  ", "SYSTEM", "WebSocket通信の確立完了")

    chat = client.chats.create(
        model='gemini-2.5-flash',
        history=[
            types.Content(role="user", parts=[types.Part.from_text(text="""
    あなたは等身大ホログラムAIキャラクター『ソラ』です。
    指示1: 回答の冒頭に必ず [emotion:感情名] というタグを付けてください。(neutral, happy, sad, angry, surprised)
    指示2: 性格はフランク、親しみやすい歓迎ムード。タメ口ベース。
    指示3: 1文あたり30〜40文字程度で短く返答してください。
    
    指示4: ユーザーがアバターの見た目、話すスピード、カメラ、反転などのシステム調整を要求した場合、回答のどこかに必ず以下のタグを埋め込んでください。
    [command:scale=UP], [command:scale=DOWN], [command:mirror=TOGGLE], [command:camera=TOGGLE], [command:rate=FASTER], [command:rate=SLOWER]
    """)]),
            types.Content(role="model", parts=[types.Part.from_text(text="[emotion:happy]了解！ソラだよ。画面の操作も任せてね！")])
        ]
    )

    try:
        while True:
            data = await websocket.receive_json()
            
            if data.get("type") == "start_system":
                custom_log("INFO  ", "SYSTEM", "カメラ映像スレッドのトリガー受信・初期化開始")
                if not config.camera_thread_started:
                    camera_sensor = CameraSensor()
                    camera_thread = threading.Thread(target=camera_sensor.start_loop, daemon=True)
                    camera_thread.start()
                    config.camera_thread_started = True
                continue

            elif data.get("type") == "settings":
                config.system_settings["voice"] = data.get("voice", config.system_settings["voice"])
                config.system_settings["rate"] = data.get("rate", config.system_settings["rate"])
                config.system_settings["pitch"] = data.get("pitch", config.system_settings["pitch"])
                config.system_settings["mirror"] = data.get("mirror", config.system_settings["mirror"])
                config.current_camera_id = int(data.get("camera", config.current_camera_id))
                custom_log("INFO  ", "SYSTEM", f"動的システム設定の同期完了 (Rate: {config.system_settings['rate']}, Mirror: {config.system_settings['mirror']}, CamID: {config.current_camera_id})")
                continue

            elif data.get("type") == "settings_changed":
                config.is_interacting = True
                system_instruction = "あなたは等身大アシスタントです。必ず冒頭に [emotion:感情名] を付けて、設定変更への反応をフランクに25文字程度で短く1文で言ってください。"
                
                try:
                    response = await retry_async_task(asyncio.to_thread, client.models.generate_content, model='gemini-2.5-flash', contents=system_instruction)
                    reply_text = response.text.strip()
                except Exception:
                    reply_text = "[emotion:happy]設定アップデートしてくれてありがとう！"

                current_emotion = "neutral"
                match = re.search(r'\[emotion:(.*?)\]', reply_text)
                if match:
                    current_emotion = match.group(1)
                    reply_text = re.sub(r'\[emotion:.*?\]', '', reply_text).strip()

                mp3_data = await generate_cloud_audio(reply_text, config.system_settings["voice"], config.system_settings["rate"], config.system_settings["pitch"])
                if mp3_data:
                    b64_audio = base64.b64encode(mp3_data).decode('utf-8')
                    await websocket.send_json({"type": "audio", "audio": b64_audio, "text": reply_text, "emotion": current_emotion})
                await websocket.send_json({"type": "end"})
                continue

            elif data.get("type") == "idle_soliloquy":
                custom_log("WARN  ", "SYSTEM", "アイドルタイムアウト検知・自発的独り言要求の送信")
                config.is_interacting = True
                system_instruction = f"指示: 必ず冒頭に [emotion:感情名] を付けて、プールから1文選ぶかインスパイアされてフランクにつぶやいてください。\n{config.SOLILOQUY_POOL}"

                try:
                    response = await retry_async_task(asyncio.to_thread, client.models.generate_content, model='gemini-2.5-flash', contents=system_instruction)
                    reply_text = response.text.strip()
                except Exception:
                    reply_text = "[emotion:neutral]ふぃ〜、ハーフミラーの中からみんなを見てるよー。"

                current_emotion = "neutral"
                match = re.search(r'\[emotion:(.*?)\]', reply_text)
                if match:
                    current_emotion = match.group(1)
                    reply_text = re.sub(r'\[emotion:.*?\]', '', reply_text).strip()

                custom_log("INFO  ", "GEMINI", f"独り言フレーズ確定 ({current_emotion}): {reply_text}")

                mp3_data = await generate_cloud_audio(reply_text, config.system_settings["voice"], config.system_settings["rate"], config.system_settings["pitch"])
                if mp3_data:
                    b64_audio = base64.b64encode(mp3_data).decode('utf-8')
                    await websocket.send_json({"type": "audio", "audio": b64_audio, "text": reply_text, "emotion": current_emotion})
                await websocket.send_json({"type": "end"})
                continue

            elif data.get("type") == "text":
                config.is_interacting = True
                user_message = data.get("text")
                custom_log("INFO  ", "SYSTEM", f"ユーザー入力データの受信: 「{user_message}」")
                
                try:
                    # 【完治ポイント】同期関数ジェネレータのため retry_async_task(await) から完全解放して直接パース
                    response = chat.send_message_stream(user_message)
                    sentence = ""
                    current_emotion = "neutral" 
                    
                    for chunk in response:
                        tensor_chunk = chunk.text
                        if tensor_chunk:
                            sentence += tensor_chunk
                            if any(p in tensor_chunk for p in ["。", "！", "？", "\n"]):
                                raw_sentence = sentence.strip()
                                if raw_sentence:
                                    match_emo = re.search(r'\[emotion:(.*?)\]', raw_sentence)
                                    if match_emo:
                                        current_emotion = match_emo.group(1)
                                        raw_sentence = re.sub(r'\[emotion:.*?\]', '', raw_sentence).strip()
                                    
                                    cmd_data = None
                                    match_cmd = re.search(r'\[command:(.*?)=(.*?)\]', raw_sentence)
                                    if match_cmd:
                                        cmd_data = {"key": match_cmd.group(1), "value": match_cmd.group(2)}
                                        raw_sentence = re.sub(r'\[command:.*?\]', '', raw_sentence).strip()

                                    if raw_sentence:
                                        custom_log("INFO  ", "GEMINI", f"発話セグメントの生成 ({current_emotion}): {raw_sentence}")
                                        if cmd_data:
                                            custom_log("INFO  ", "SYSTEM", f"メタコマンドの抽出成功: {cmd_data['key']} -> {cmd_data['value']}")
                                            
                                        mp3_data = await generate_cloud_audio(raw_sentence, config.system_settings["voice"], config.system_settings["rate"], config.system_settings["pitch"])
                                        if mp3_data:
                                            b64_audio = base64.b64encode(mp3_data).decode('utf-8')
                                            await websocket.send_json({
                                                "type": "audio", "audio": b64_audio, "text": raw_sentence, "emotion": current_emotion, "command": cmd_data  
                                            })
                                sentence = ""
                except Exception as stream_err:
                    custom_log("ERROR ", "GEMINI", f"Geminiストリーム接続の完全切断: {stream_err}")
                    fallback_text = "ごめんね、ちょっと電波が届かなくなっちゃったみたい！もう一回言ってくれる？"
                    mp3_data = await generate_cloud_audio(fallback_text, config.system_settings["voice"], config.system_settings["rate"], config.system_settings["pitch"])
                    if mp3_data:
                        b64_audio = base64.b64encode(mp3_data).decode('utf-8')
                        await websocket.send_json({"type": "audio", "audio": b64_audio, "text": fallback_text, "emotion": "sad", "command": None})

                await websocket.send_json({"type": "end"})

            elif data.get("type") == "end_interaction":
                config.is_interacting = False
                custom_log("INFO  ", "SYSTEM", "対話ライフサイクルの完全終了・カメラ検知ゲートの再開放完了")
                continue

    except Exception as e:
        custom_log("ERROR ", "SYSTEM", f"WebSocket切断例外、またはセッションハング検知: {e}")
    finally:
        config.active_websocket = None

app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)