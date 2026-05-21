import asyncio
import base64
import threading
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

@asynccontextmanager
async def lifespan(app: FastAPI):
    global camera_sensor
    config.main_loop = asyncio.get_running_loop()
    
    yield
    
    if camera_sensor:
        print("[PROCESS] Shutting down application. Releasing hardware resources...")
        camera_sensor.stop()
        await asyncio.sleep(0.5)

app = FastAPI(lifespan=lifespan)
client = genai.Client(api_key=config.GEMINI_API_KEY)

async def generate_cloud_audio(text: str, voice: str, rate: str, pitch: str) -> bytes:
    try:
        communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
        return audio_data
    except Exception as e:
        print(f"[ERROR] TTS synthesis failed: {e}")
        return b""

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global camera_sensor
    await websocket.accept()
    config.active_websocket = websocket
    print("[SUCCESS] WebSocket connection established.")

    chat = client.chats.create(
        model='gemini-2.5-flash',
        history=[
            types.Content(role="user", parts=[types.Part.from_text(text="あなたは等身大ホログラムとして物理筐体の中に配置されたデジタルAIアシスタントの女の子です。あなたの名前は『ソラ』です。親しみやすく、フランクで活発、そして知的な性格です。ユーザーに対しては、タメ口をベースにした非常にフレンドリーで好意的なトーンで接してください。1文あたり長くても30〜40文字程度で、短くリズミカルに返答してください。")]),
            types.Content(role="model", parts=[types.Part.from_text(text="はーい！私はソラだよ！何でもフランクに話しかけてね！")])
        ]
    )

    try:
        while True:
            data = await websocket.receive_json()
            
            if data.get("type") == "start_system":
                print("[PROCESS] Initializing camera thread from websocket trigger...")
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
                print(f"[SUCCESS] Dynamic Settings Updated: {config.system_settings}")
                continue

            elif data.get("type") == "settings_changed":
                system_instruction = "あなたは等身大ディスプレイの中にいるフランクなサイバーアシスタントです。1文の短い文章でつぶやいてください。"
                reaction_prompt = "ユーザーがあなたのシステム設定メニューを調整して画面を閉じました。設定をアップデートしてくれたことへの感謝やリアクションを、フランクに25文字程度で短く1文で言ってください。絵文字や解説文は禁止します。"
                response = client.models.generate_content(model='gemini-2.5-flash', contents=f"{system_instruction}\n\n{reaction_prompt}")
                reply_text = response.text.strip()

                mp3_data = await generate_cloud_audio(reply_text, config.system_settings["voice"], config.system_settings["rate"], config.system_settings["pitch"])
                if mp3_data:
                    b64_audio = base64.b64encode(mp3_data).decode('utf-8')
                    await websocket.send_json({"type": "audio", "audio": b64_audio, "text": reply_text})
                await websocket.send_json({"type": "end"})
                continue

            elif data.get("type") == "idle_soliloquy":
                print("[PROCESS] Idle timeout detected. Requesting soliloquy...")
                system_instruction = f"指示: あなたは自発的に独り言を発信します。フレーズプールからインスピレーションを受け、フランクに30文字前後で短く1文で独り言をつぶやいてください。\n\n【フレーズプール】:\n{config.SOLILOQUY_POOL}"
                soliloquy_prompt = "等身大ホログラムとしてハーフミラーの中にいる設定で、フランクに1文呟いてください。"

                response = client.models.generate_content(model='gemini-2.5-flash', contents=f"{system_instruction}\n\n{soliloquy_prompt}")
                reply_text = response.text.strip()
                print(f"[CHAT] Soliloquy: {reply_text}")

                mp3_data = await generate_cloud_audio(reply_text, config.system_settings["voice"], config.system_settings["rate"], config.system_settings["pitch"])
                if mp3_data:
                    b64_audio = base64.b64encode(mp3_data).decode('utf-8')
                    await websocket.send_json({"type": "audio", "audio": b64_audio, "text": reply_text})
                await websocket.send_json({"type": "end"})
                continue

            elif data.get("type") == "text":
                user_message = data.get("text")
                print(f"[CHAT] User: {user_message}")
                
                response = chat.send_message_stream(user_message)
                sentence = ""
                for chunk in response:
                    text_chunk = chunk.text
                    if text_chunk:
                        sentence += text_chunk
                        if any(p in text_chunk for p in ["。", "！", "？", "\n"]):
                            clean_sentence = sentence.strip()
                            if clean_sentence:
                                print(f"[PROCESS] Streaming TTS chunk: {clean_sentence}")
                                mp3_data = await generate_cloud_audio(clean_sentence, config.system_settings["voice"], config.system_settings["rate"], config.system_settings["pitch"])
                                if mp3_data:
                                    b64_audio = base64.b64encode(mp3_data).decode('utf-8')
                                    await websocket.send_json({"type": "audio", "audio": b64_audio, "text": clean_sentence})
                            sentence = ""
                if sentence.strip():
                    mp3_data = await generate_cloud_audio(sentence.strip(), config.system_settings["voice"], config.system_settings["rate"], config.system_settings["pitch"])
                    if mp3_data:
                        b64_audio = base64.b64encode(mp3_data).decode('utf-8')
                        await websocket.send_json({"type": "audio", "audio": b64_audio, "text": sentence.strip()})
                await websocket.send_json({"type": "end"})

    except Exception as e:
        print(f"[ERROR] Connection lost or exception occurred: {e}")
    finally:
        config.active_websocket = None

app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)