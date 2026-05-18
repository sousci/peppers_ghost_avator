import asyncio
import os
import base64
from datetime import datetime
from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
import uvicorn
import google.generativeai as genai
import edge_tts

# --- Gemini API の初期設定 ---
GOOGLE_API_KEY = os.getenv("GEMINI_API_KEY")

if not GOOGLE_API_KEY:
    print("\n" + "="*70)
    print("【❌ 致命的なエラー: Gemini APIキーが見つかりません！】")
    print("環境変数にキーを設定するか、下のコメントアウトを解除して直接記述してください。")
    print("="*70 + "\n")
    # GOOGLE_API_KEY = "AIzaSy..." 

genai.configure(api_key=GOOGLE_API_KEY)
model = genai.GenerativeModel('gemini-2.5-flash')

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

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print("【サーバー側】ブラウザと接続されました。")
    
    chat = model.start_chat(history=[
        {
            "role": "user", 
            "parts": "あなたは等身大ディスプレイの中にいるサイバーアシスタントです。フランクかつ親しみやすい口調で、2〜3文の短めの文章で回答してください。"
        },
        {
            "role": "model", 
            "parts": "了解！設定に合わせた最適なボイスでサポートするよ！"
        }
    ])
    
    current_voice = "ja-JP-NanamiNeural"
    current_rate = "+50%"
    current_pitch = "+30Hz"
    current_mirror = "true"
    
    # 💡 拡張：Geminiにインジェクションする「50個の独り言ボキャブラリープール」
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

    【ホログラム限定（mirror == "true" の時のみ参考にする）】
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

    【モニター限定（mirror == "false" の時のみ参考にする）】
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

    try:
        while True:
            data = await websocket.receive_json()
            
            if data.get("type") == "settings":
                current_voice = data.get("voice", current_voice)
                current_rate = data.get("rate", current_rate)
                current_pitch = data.get("pitch", current_pitch)
                current_mirror = data.get("mirror", current_mirror)
                print(f"【設定更新】voice: {current_voice}, rate: {current_rate}, pitch: {current_pitch}, mirror: {current_mirror}")
                continue
                
            elif data.get("type") == "settings_changed":
                print("【システム】: 設定変更のリアクション要求を受信")
                system_instruction = "あなたは等身大ディスプレイの中にいるフランクなサイバーアシスタントです。1文の短い文章でつぶやいてください。"
                reaction_prompt = "ユーザーがシステム設定を完了し設定画面を閉じました。調整に対する感謝や『新しい声はどう？』といったリアクションを25文字程度で短く1文で言ってください。"
                
                response = model.generate_content(f"{system_instruction}\n\n{reaction_prompt}")
                reply_text = response.text.strip()
                
                mp3_data = await generate_cloud_audio(reply_text, current_voice, current_rate, current_pitch)
                if mp3_data:
                    b64_audio = base64.b64encode(mp3_data).decode('utf-8')
                    await websocket.send_json({"type": "audio", "audio": b64_audio, "text": reply_text})
                await websocket.send_json({"type": "end"})
                continue

            # 💡 独り言の生成プロンプトを大幅強化
            elif data.get("type") == "idle_soliloquy":
                print("【システム】: 30秒の静寂による独り言要求を受信")
                now_str = datetime.now().strftime("%Y年%m月%d日 %H時%M分")
                
                system_instruction = f"""
                あなたは等身大ディスプレイの中にいるフランクで少しウィットに富んだサイバーアシスタントです。
                以下の【フレーズ集】の表現（あくび、自己調整、気配察知、メタ発言など）から強いインスピレーションを受け、またはそのままサンプリングして、現在の状況に合わせたフランクな独り言を「25文字程度で短く1文」でつぶやいてください。
                絵文字や不要な前置きは一切禁止します。

                【フレーズ集】:
                {soliloquy_vocabulary_pool}
                """
                
                if current_mirror == "true":
                    soliloquy_prompt = f"（現在日時: {now_str}）あなたは今、ハーフミラーを用いた『等身大ホログラム投影筐体』の中に立っています。しばらく誰からも話しかけられていません。【感情・暇・あくび系】、【システム系】、【気配察知系】、または【ホログラム限定】の表現を参考にして、現在の時間帯の空気に触れつつフランクにつぶやいてください。"
                else:
                    soliloquy_prompt = f"（現在日時: {now_str}）あなたは今、通常の『PCモニター（デバッグ・開発環境）』に映っています。しばらく誰からも話しかけられていません。【感情・暇・あくび系】、【システム系】、【気配察知系】、または【モニター限定】のメタ表現を参考にして、現在の時間帯の空気に触れつつフランクにつぶやいてください。"
                
                response = model.generate_content(f"{system_instruction}\n\n{soliloquy_prompt}")
                reply_text = response.text.strip()
                print(f"【自動独り言発話】: {reply_text}")
                
                mp3_data = await generate_cloud_audio(reply_text, current_voice, current_rate, current_pitch)
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
                
                response = chat.send_message(enriched_prompt, stream=True)
                
                sentence = ""
                for chunk in response:
                    if chunk.candidates and chunk.candidates[0].content.parts:
                        text_chunk = chunk.text
                        sentence += text_chunk
                        
                        if any(p in text_chunk for p in ["。", "！", "？", "\n"]):
                            clean_sentence = sentence.strip()
                            if clean_sentence:
                                print(f"【1文完成】: {clean_sentence}")
                                mp3_data = await generate_cloud_audio(clean_sentence, current_voice, current_rate, current_pitch)
                                if mp3_data:
                                    b64_audio = base64.b64encode(mp3_data).decode('utf-8')
                                    await websocket.send_json({"type": "audio", "audio": b64_audio, "text": clean_sentence})
                            sentence = ""
                
                if sentence.strip():
                    mp3_data = await generate_cloud_audio(sentence.strip(), current_voice, current_rate, current_pitch)
                    if mp3_data:
                        b64_audio = base64.b64encode(mp3_data).decode('utf-8')
                        await websocket.send_json({"type": "audio", "audio": b64_audio, "text": sentence.strip()})
                
                await websocket.send_json({"type": "end"})
            
    except Exception as e:
        print(f"【サーバー側】切断されました: {e}")

app.mount("/", StaticFiles(directory=".", html=True), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
