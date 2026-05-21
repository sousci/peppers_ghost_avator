import asyncio
import base64
import threading
from datetime import datetime
from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
import uvicorn
import edge_tts
from google import genai
from google.genai import types

import config
from camera import CameraSensor

app = FastAPI()
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

def launch_camera_worker():
    sensor = CameraSensor()
    sensor.start_loop()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    config.active_websocket = websocket
    print("[SUCCESS] WebSocket connection established.")

    chat = client.chats.create(
        model='gemini-2.5-flash',
        history=[
            types.Content(role="user", parts=[types.Part.from_text(text="あなたは等身大ディスプレイの中にいるサイバーアシスタントです。フランクかつ親しみやすい口調で、2〜3文の短めの文章で回答してください。")]),
            types.Content(role="model", parts=[types.Part.from_text(text="了解！設定に合わせた最適なボイスでサポートするよ！")])
        ]
    )

    try:
        while True:
            data = await websocket.receive_json()

            if data.get("type") == "start_system":
                print("[PROCESS] Initializing camera thread...")
                if not config.camera_thread_started:
                    config.camera_thread_started = True
                    camera_thread = threading.Thread(target=launch_camera_worker, daemon=True)
                    camera_thread.start()
                continue

            elif data.get("type") == "settings":
                changes = []
                new_voice = data.get("voice", config.system_settings["voice"])
                new_rate = data.get("rate", config.system_settings["rate"])
                new_pitch = data.get("pitch", config.system_settings["pitch"])
                new_mirror = data.get("mirror", config.system_settings["mirror"])
                new_camera_id = int(data.get("camera", config.current_camera_id))

                if new_voice != config.system_settings["voice"]: changes.append("キャラクター（声色）")
                if new_rate != config.system_settings["rate"]: changes.append("話速（スピード）")
                if new_pitch != config.system_settings["pitch"]: changes.append("声のピッチ（高さ）")
                if new_mirror != config.system_settings["mirror"]: changes.append("画面の左右反転")
                if new_camera_id != config.current_camera_id: changes.append("使用カメラデバイス")
                if data.get("visual_changed", False): changes.append("ビジュアル（位置・明るさ・サイズ等のフィッティング）")

                websocket.scope["last_changes"] = "、".join(changes) if changes else "全体調整"

                config.system_settings["voice"] = new_voice
                config.system_settings["rate"] = new_rate
                config.system_settings["pitch"] = new_pitch
                config.system_settings["mirror"] = new_mirror
                config.current_camera_id = new_camera_id
                
                if changes:
                    print(f"[SUCCESS] Settings updated. Changed: {websocket.scope['last_changes']}")
                continue

            elif data.get("type") == "settings_changed":
                changed_items = websocket.scope.get("last_changes", "全体調整")
                print(f"[PROCESS] Generating reaction for: {changed_items}")
                system_instruction = "あなたは等身大ディスプレイの中にいるフランクなサイバーアシスタントです。1文の短い文章でつぶやいてください。"
                reaction_prompt = f"ユーザーがあなたのシステム設定メニューから【{changed_items}】の項目を変更完了し、画面を閉じました。変更された具体的な項目名にフランクに触れつつ、調整してくれたことへの感謝やリアクションを、25文字程度で短く1文で言ってください。絵文字や解説文は禁止します。"

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
                now_str = datetime.now().strftime("%Y年%m月%d日 %H時%M分")
                system_instruction = f"あなたは等身大ディスプレイの中にいるフランクなサイバーアシスタントです。以下のフレーズ集からインスピレーションを受け、25文字程度で短く1文で独り言をつぶやいてください。\n\n【フレーズ集】:\n{config.SOLILOQUY_POOL}"
                soliloquy_prompt = f"（現在日時: {now_str}）あなたは今、『等身大ホログラム投影筐体』の中に立っています。" if config.system_settings["mirror"] == "true" else f"（現在日時: {now_str}）あなたは今、『PCモニター（デバッグ画面）』に映っています。"
                soliloquy_prompt += "環境表現やあくび系を参考にフランクにつぶやいてください。"

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

@app.on_event("startup")
async def startup_event():
    config.main_loop = asyncio.get_running_loop()

app.mount("/", StaticFiles(directory=".", html=True), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)