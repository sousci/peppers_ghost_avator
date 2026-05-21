import time
import base64
import io
import os
import urllib.request
import asyncio
import cv2
import PIL.Image
from google import genai
import config

class CameraSensor:
    def __init__(self):
        self.proto_path = "deploy.prototxt"
        self.model_path = "res10_300x300_ssd_iter_140000.caffemodel"
        self._prepare_models()
        self.net = cv2.dnn.readNetFromCaffe(self.proto_path, self.model_path)
        self.client = genai.Client(api_key=config.GEMINI_API_KEY)

    def _prepare_models(self):
        if not os.path.exists(self.proto_path):
            print("[PROCESS] Downloading face detection prototxt...")
            urllib.request.urlretrieve("https://raw.githubusercontent.com/opencv/opencv/master/samples/dnn/face_detector/deploy.prototxt", self.proto_path)
        if not os.path.exists(self.model_path):
            print("[PROCESS] Downloading face detection model...")
            urllib.request.urlretrieve("https://raw.githubusercontent.com/opencv/opencv_3rdparty/dnn_samples_face_detector_20170830/res10_300x300_ssd_iter_140000.caffemodel", self.model_path)

    def start_loop(self):
        current_cap_id = config.current_camera_id
        print(f"[PROCESS] Connecting camera device (ID: {current_cap_id})...")
        cap = cv2.VideoCapture(current_cap_id)
        print(f"[SUCCESS] Camera sensor pipeline activated (ID: {current_cap_id}).")
        consecutive_face_frames = 0
        preview_count = 0

        while True:
            time.sleep(0.03)

            # 動的なカメラデバイスの切り替え検知
            if config.current_camera_id != current_cap_id:
                print(f"[PROCESS] Switching camera pipeline: ID {current_cap_id} -> {config.current_camera_id}...")
                cap.release()
                current_cap_id = config.current_camera_id
                cap = cv2.VideoCapture(current_cap_id)
                consecutive_face_frames = 0
                if cap.isOpened():
                    print(f"[SUCCESS] Switched camera device successfully (ID: {current_cap_id}).")

            if not cap.isOpened():
                time.sleep(0.5)
                continue

            ret, frame = cap.read()
            if not ret:
                continue

            h, w = frame.shape[:2]
            blob = cv2.dnn.blobFromImage(cv2.resize(frame, (300, 300)), 1.0, (300, 300), (104.0, 177.0, 123.0))
            self.net.setInput(blob)
            detections = self.net.forward()

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

            # フロントエンドへのリアルタイムモニター配信（10FPS間引き）
            if config.active_websocket is not None and config.main_loop is not None:
                preview_count += 1
                if preview_count % 3 == 0:
                    try:
                        small_preview = cv2.resize(preview_frame, (320, int(320 * h / w)))
                        _, pre_buf = cv2.imencode('.jpg', small_preview, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
                        pre_b64 = base64.b64encode(pre_buf).decode('utf-8')
                        asyncio.run_coroutine_threadsafe(
                            config.active_websocket.send_json({"type": "camera_preview", "image": pre_b64}),
                            config.main_loop
                        )
                    except Exception:
                        pass

            # 属性看破トリガー発火
            current_time = time.time()
            if consecutive_face_frames >= 3 and (current_time - config.last_greeting_time > config.DETECTION_COOLDOWN_SEC):
                if config.active_websocket is not None and config.main_loop is not None:
                    print("[PROCESS] Human detected by DNN. Initiating multimodal inference...")
                    config.last_greeting_time = current_time
                    consecutive_face_frames = 0
                    asyncio.run_coroutine_threadsafe(
                        self.process_spontaneous_greeting(frame),
                        config.main_loop
                    )

    async def process_spontaneous_greeting(self, frame):
        if config.active_websocket is None:
            return
        try:
            from app import generate_cloud_audio
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_img = PIL.Image.fromarray(rgb_frame)

            prompt = (
                "指示: あなたの目の前のディスプレイに、新しく人が1人立ち止まりました。"
                "画像に写っているその人の大まかな年齢層、性別、服装や髪型、雰囲気（楽しそう、真面目そう、疲れてそうなど）を瞬時に推察してください。"
                "指示に従い、看破した特徴にパーソナライズした、フランクで超親しみやすい歓迎の挨拶を、25文字程度で短く1文で言ってください。"
                "前置きや絵文字、解説文は一切禁止します。挨拶の言葉だけを出力してください。"
            )

            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model='gemini-2.5-flash',
                contents=[pil_img, prompt]
            )
            reply_text = response.text.strip()
            print(f"[CHAT] Spontaneous Greeting: {reply_text}")

            mp3_data = await generate_cloud_audio(reply_text, config.system_settings["voice"], config.system_settings["rate"], config.system_settings["pitch"])
            if mp3_data and config.active_websocket:
                b64_audio = base64.b64encode(mp3_data).decode('utf-8')
                await config.active_websocket.send_json({"type": "audio", "audio": b64_audio, "text": reply_text})
                await config.active_websocket.send_json({"type": "end"})
        except Exception as e:
            print(f"[ERROR] Multimodal process failed: {e}")