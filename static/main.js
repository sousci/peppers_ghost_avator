let ws = null;
let audioCtx = null;
let audioQueue = [];        
let isPlayingAudio = false;  

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
const recognition = new SpeechRecognition();
recognition.lang = 'ja-JP';
recognition.interimResults = false; 
recognition.continuous = false;     

const startBtn = document.getElementById('start-btn');
const chatLog = document.getElementById('chat-log');
const micIndicator = document.getElementById('mic-indicator'); 
const optionsOverlay = document.getElementById('options-overlay');

let isRecognitionActive = false; 
let isAiTurn = false; 
let isStarted = false; 
let isOptionsOpen = false; 
let idleTimer = null;
let isVisualParamChanged = false; 
let isPendingSettingsSync = false;
let waitingPromptEl = null;
let cameraOptionsMeta = [];

function guessCameraType(label = "") {
    const l = (label || "").toLowerCase();
    if (l.includes("usb") || l.includes("webcam") || l.includes("external")) return "usb";
    if (l.includes("integrated") || l.includes("internal") || l.includes("built-in") || l.includes("builtin")) return "internal";
    return "unknown";
}

async function refreshCameraOptions(requestPermission = false) {
    const cameraSelect = document.getElementById('param-camera');
    if (!cameraSelect || !navigator.mediaDevices?.enumerateDevices) return;

    let stream = null;
    try {
        if (requestPermission) {
            stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
        }
        const devices = await navigator.mediaDevices.enumerateDevices();
        const cameras = devices.filter((d) => d.kind === "videoinput");
        if (cameras.length === 0) return;

        const previousValue = cameraSelect.value;
        cameraOptionsMeta = cameras.map((cam, idx) => ({
            index: idx,
            label: cam.label || `Camera ${idx}`,
            type: guessCameraType(cam.label || ""),
        }));

        cameraSelect.innerHTML = "";
        cameraOptionsMeta.forEach((cam) => {
            const option = document.createElement("option");
            option.value = String(cam.index);
            const typeLabel = cam.type === "usb" ? "USB" : (cam.type === "internal" ? "Internal" : "Unknown");
            option.textContent = `Camera ${cam.index} (${typeLabel}: ${cam.label})`;
            cameraSelect.appendChild(option);
        });

        if ([...cameraSelect.options].some((o) => o.value === previousValue)) cameraSelect.value = previousValue;
        else cameraSelect.value = "0";
    } catch (e) {
        console.warn("camera list refresh failed:", e);
    } finally {
        if (stream) stream.getTracks().forEach((t) => t.stop());
    }
}

function connectWebSocket() {
    console.log("【通信管理】WebSocket 接続要求を開始します...");
    ws = new WebSocket('ws://localhost:8000/ws');

    ws.onopen = () => {
        console.log("【通信管理】FastAPI バックエンドとのパイプライン接続に成功しました。");
        if (isStarted) { sendSettingsToServer(); }
    };

    ws.onmessage = async (event) => {
        if (!isStarted) return;
        const msg = JSON.parse(event.data);
        
        if (msg.type === "camera_preview") {
            const previewImg = document.getElementById('camera-preview');
            if (previewImg) {
                previewImg.style.display = 'block';
                previewImg.src = 'data:image/jpeg;base64,' + msg.image;
            }
            return;
        }

        if (msg.type === "audio") {
            stopIdleTimer(); 
            let rawText = msg.text;
            let emotion = msg.emotion || 'neutral';
            
            const match = rawText.match(/\[emotion:(.*?)\]/);
            if (match) {
                emotion = match[1];
                rawText = rawText.replace(/\[emotion:.*?\]/, "");
            }

            if (msg.command) { executeVoiceCommand(msg.command); }

            audioQueue.push({ bufferArray: bytesToBuffer(msg.audio), text: rawText, emotion: emotion });
            if (!isPlayingAudio) playNextInQueue();
        }
    };

    ws.onclose = (e) => {
        console.warn("【通信管理】WebSocket 切断を検知しました。3秒後に自動再接続を試みます...", e.reason);
        stopIdleTimer();
        setTimeout(connectWebSocket, 3000); 
    };

    ws.onerror = (err) => {
        console.error("【通信管理】WebSocket 内部エラーが発生しました:", err);
    };
}

connectWebSocket();

function resetIdleTimer() {
    stopIdleTimer();
    if (!isStarted || isOptionsOpen || window.isSpeaking || isAiTurn) return;
    
    const minTimeout = 30000; 
    const maxTimeout = 90000; 
    const dynamicTimeout = Math.floor(minTimeout + Math.random() * (maxTimeout - minTimeout));
    
    console.log(`【タイマー稼働】次回の自発的な独り言まで: ${(dynamicTimeout / 1000).toFixed(1)} 秒`);

    idleTimer = setTimeout(() => {
        if (!isStarted || window.isSpeaking || isAiTurn || isOptionsOpen) return;
        isAiTurn = true; 
        try { recognition.stop(); } catch(e){}
        isRecognitionActive = false;
        micIndicator.style.display = 'none';
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "idle_soliloquy" }));
        }
    }, dynamicTimeout);
}

function stopIdleTimer() {
    if (idleTimer) { clearTimeout(idleTimer); idleTimer = null; }
}

function activateSystem() {
    if (startBtn.disabled) return;
    startBtn.disabled = true;
    startBtn.style.display = 'none'; 
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    
    isStarted = true;
    chatLog.innerHTML = "";
    appendMessage('status', "何か 話しかけるか、下のフォームから文字を入力してください...");
    
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "start_system" }));
    }
    
    sendSettingsToServer();
    refreshCameraOptions(true);
    isAiTurn = false; 
    startListening();
    resetIdleTimer(); 
}

startBtn.addEventListener('click', activateSystem);

window.addEventListener('keydown', (event) => {
    if (event.code === 'Space' && !isStarted) {
        event.preventDefault(); 
        activateSystem();
    }
    if (event.code === 'Escape') {
        event.preventDefault();
        toggleOptionsWindow();
    }
});

function toggleOptionsWindow() {
    if (!isOptionsOpen) {
        isOptionsOpen = true;
        optionsOverlay.style.display = 'block';
        refreshCameraOptions(false);
        try { recognition.stop(); } catch(e){}
        isRecognitionActive = false;
        micIndicator.style.display = 'none';
        stopIdleTimer(); 
        isVisualParamChanged = false; 
    } else {
        isOptionsOpen = false;
        optionsOverlay.style.display = 'none';
        sendSettingsToServer();
        if (isStarted) {
            isAiTurn = true; 
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ type: "settings_changed" }));
            }
        } else {
            startListening();
        }
        resetIdleTimer();
    }
}

function sendSettingsToServer() {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;

    if (isAiTurn || isPlayingAudio || window.isSpeaking) {
        isPendingSettingsSync = true;
        console.log("【通信防衛】AIが発話中のため、サーバーへの設定同期パケットを一時保留しました。");
        return;
    }

    const vRate = (parseInt(document.getElementById('param-rate').value) >= 0 ? "+" : "") + document.getElementById('param-rate').value + "%";
    const vPitch = (parseInt(document.getElementById('param-pitch').value) >= 0 ? "+" : "") + document.getElementById('param-pitch').value + "Hz";
    const vVoice = document.getElementById('param-voice').value;
    const vMirror = document.getElementById('param-mirror').value;
    const vCamera = parseInt(document.getElementById('param-camera').value);

    ws.send(JSON.stringify({
        type: "settings", voice: vVoice, rate: vRate, pitch: vPitch, mirror: vMirror, camera: vCamera, visual_changed: isVisualParamChanged 
    }));
    isVisualParamChanged = false; 
}

function appendMessage(role, text) {
    if (!isStarted && role !== 'status') return null;

    if (role === 'status') {
        if (!waitingPromptEl || !waitingPromptEl.isConnected) {
            waitingPromptEl = document.createElement('div');
            waitingPromptEl.className = 'msg-status';
            chatLog.appendChild(waitingPromptEl);
        }
        waitingPromptEl.innerText = text;
        chatLog.appendChild(waitingPromptEl); // always keep at latest (bottom)
        chatLog.scrollTop = chatLog.scrollHeight;
        return waitingPromptEl;
    }

    // Keep waiting prompt only at the latest idle state, never between conversations.
    if (waitingPromptEl && waitingPromptEl.isConnected) {
        waitingPromptEl.remove();
        waitingPromptEl = null;
    }

    document.querySelectorAll('.msg-status').forEach((el) => el.remove());

    const msgDiv = document.createElement('div');
    if (role === 'user') msgDiv.className = 'msg-user';
    else if (role === 'ai') msgDiv.className = 'msg-ai';
    msgDiv.innerText = text;
    chatLog.appendChild(msgDiv);
    chatLog.scrollTop = chatLog.scrollHeight;
    return msgDiv; 
}

function startListening() {
    if (!isStarted || window.isSpeaking || isRecognitionActive || isAiTurn || isOptionsOpen) return;
    setTimeout(() => {
        if (!isStarted || window.isSpeaking || isRecognitionActive || isAiTurn || isOptionsOpen) return;
        try { recognition.start(); } catch (e) {}
    }, 300);
}

recognition.onstart = () => {
    if (!isStarted || isOptionsOpen) { try { recognition.stop(); } catch(e){} return; }
    isRecognitionActive = true;
    micIndicator.style.display = 'block'; 
};

recognition.onresult = (event) => {
    if (!isStarted || isOptionsOpen) return;
    const speechText = event.results[0][0].transcript;
    appendMessage('user', `あなた: ${speechText}`);
    isAiTurn = true; 
    try { recognition.stop(); } catch(e){}
    isRecognitionActive = false;
    micIndicator.style.display = 'none'; 
    stopIdleTimer(); 
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "text", text: speechText }));
    }
};

recognition.onerror = (event) => {
    isRecognitionActive = false; micIndicator.style.display = 'none'; resetIdleTimer();
};

recognition.onend = () => {
    isRecognitionActive = false; micIndicator.style.display = 'none'; 
    if (isStarted && !isAiTurn && !window.isSpeaking && !isOptionsOpen) startListening();
};

function executeVoiceCommand(cmd) {
    if (!cmd || !cmd.key) return;
    console.log(`【フロントコマンド実行】Key: ${cmd.key} / Value: ${cmd.value}`);

    if (cmd.key === "scale") {
        const scaleInput = document.getElementById('param-vrm-scale');
        let currentScale = parseFloat(scaleInput.value);
        if (cmd.value === "UP") currentScale = Math.min(currentScale + 0.15, 2.0);
        else if (cmd.value === "DOWN") currentScale = Math.max(currentScale - 0.15, 0.5);
        scaleInput.value = currentScale;
        scaleInput.dispatchEvent(new Event('input')); 
    }
    else if (cmd.key === "mirror") {
        const mirrorSelect = document.getElementById('param-mirror');
        mirrorSelect.value = (mirrorSelect.value === 'true') ? 'false' : 'true';
        if (mirrorSelect.value === 'true') document.body.style.transform = 'scaleX(-1)';
        else document.body.style.transform = 'none';
        sendSettingsToServer(); 
    }
    else if (cmd.key === "camera") {
        const cameraSelect = document.getElementById('param-camera');
        const value = String(cmd.value || "").toUpperCase();
        if (value === "TOGGLE") {
            const current = parseInt(cameraSelect.value || "0", 10);
            const next = cameraOptionsMeta.length > 1 ? (current + 1) % cameraOptionsMeta.length : (current === 0 ? 1 : 0);
            cameraSelect.value = String(next);
        } else if (value === "INTERNAL") {
            const target = cameraOptionsMeta.find((c) => c.type === "internal");
            if (target) cameraSelect.value = String(target.index);
        } else if (value === "USB") {
            const target = cameraOptionsMeta.find((c) => c.type === "usb");
            if (target) cameraSelect.value = String(target.index);
        } else if (/^\d+$/.test(value)) {
            cameraSelect.value = value;
        }
        cameraSelect.dispatchEvent(new Event('change')); 
    }
    else if (cmd.key === "rate") {
        const rateInput = document.getElementById('param-rate');
        let currentRate = parseInt(rateInput.value);
        if (cmd.value === "FASTER") currentRate = Math.min(currentRate + 25, 100);
        else if (cmd.value === "SLOWER") currentRate = Math.max(currentRate - 25, -50);
        rateInput.value = currentRate;
        rateInput.dispatchEvent(new Event('input'));  
        rateInput.dispatchEvent(new Event('change')); 
    }
}

function bytesToBuffer(base64Str) {
    const binaryString = window.atob(base64Str);
    const len = binaryString.length;
    const bytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) { bytes[i] = binaryString.charCodeAt(i); }
    return bytes.buffer;
}

async function playNextInQueue() {
    if (!isStarted) return;
    if (audioQueue.length === 0) {
        isPlayingAudio = false; window.isSpeaking = false; isAiTurn = false; 
        appendMessage('status', "何か 話しかけてください...");
        if (window.playMotion) window.playMotion('neutral');

        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "end_interaction" }));
        }

        if (isPendingSettingsSync) {
            isPendingSettingsSync = false;
            console.log("【通信回収】安全待機状態への遷移に伴い、保留設定をサーバーへ一括クリーン同期します。");
            sendSettingsToServer();
        }

        startListening(); resetIdleTimer(); 
        return;
    }
    isPlayingAudio = true; window.isSpeaking = true; 
    const currentItem = audioQueue.shift();
    appendMessage('ai', currentItem.text); 
    if (window.playMotion) { window.playMotion(currentItem.emotion); }

    try {
        const audioBuffer = await audioCtx.decodeAudioData(currentItem.bufferArray);
        const source = audioCtx.createBufferSource();
        source.buffer = audioBuffer;

        if (!window.audioAnalyser) {
            window.audioAnalyser = audioCtx.createAnalyser();
            window.audioAnalyser.fftSize = 32; 
        }
        source.connect(window.audioAnalyser);
        window.audioAnalyser.connect(audioCtx.destination);
        source.onended = () => { playNextInQueue(); };
        source.start(0);
    } catch (e) { playNextInQueue(); }
}

const filterContainer = document.querySelector('.avatar-filter-target');
const pBright = document.getElementById('param-bright');
const pContrast = document.getElementById('param-contrast');
const pSaturate = document.getElementById('param-saturate');
function updateCSSFilters() {
    document.getElementById('val-bright').innerText = pBright.value;
    document.getElementById('val-contrast').innerText = pContrast.value;
    document.getElementById('val-saturate').innerText = pSaturate.value;
    filterContainer.style.filter = `brightness(${pBright.value}) contrast(${pContrast.value}) saturate(${pSaturate.value})`;
    isVisualParamChanged = true; 
}
pBright.addEventListener('input', updateCSSFilters);
pContrast.addEventListener('input', updateCSSFilters);
pSaturate.addEventListener('input', updateCSSFilters);

const pVrmX = document.getElementById('param-vrm-x');
const pVrmY = document.getElementById('param-vrm-y');
const pVrmScale = document.getElementById('param-vrm-scale');
pVrmX.addEventListener('input', (e) => {
    const val = parseFloat(e.target.value); document.getElementById('val-vrm-x').innerText = val.toFixed(2);
    if (window.currentVrm) window.currentVrm.scene.position.x = val;
    isVisualParamChanged = true; 
});
pVrmY.addEventListener('input', (e) => {
    const val = parseFloat(e.target.value); document.getElementById('val-vrm-y').innerText = val.toFixed(2);
    isVisualParamChanged = true;
});
pVrmScale.addEventListener('input', (e) => {
    const val = parseFloat(e.target.value); document.getElementById('val-vrm-scale').innerText = val.toFixed(2);
    if (window.currentVrm) window.currentVrm.scene.scale.set(val, val, val);
    isVisualParamChanged = true;
});

document.getElementById('param-mirror').addEventListener('change', (e) => {
    if (e.target.value === 'true') document.body.style.transform = 'scaleX(-1)';
    else document.body.style.transform = 'none';
    sendSettingsToServer(); 
});
document.getElementById('param-camera').addEventListener('change', () => { sendSettingsToServer(); });
document.getElementById('param-rate').addEventListener('change', () => { sendSettingsToServer(); });
document.getElementById('param-pitch').addEventListener('change', () => { sendSettingsToServer(); });
document.getElementById('param-voice').addEventListener('change', () => { sendSettingsToServer(); });

document.getElementById('param-rate').addEventListener('input', (e) => {
    document.getElementById('val-rate').innerText = (parseInt(e.target.value) >= 0 ? "+" : "") + e.target.value + "%";
});
document.getElementById('param-pitch').addEventListener('input', (e) => {
    document.getElementById('val-pitch').innerText = (parseInt(e.target.value) >= 0 ? "+" : "") + e.target.value + "Hz";
});

function initTextInputForm() {
    const formContainer = document.createElement('div');
    formContainer.id = 'debug-text-input-container';
    // 【修正ポイント】bottomを 15px から 60px へ引き上げ調整完了！
    formContainer.style.cssText = `
        position: fixed; bottom: 60px; left: 50%; transform: translateX(-50%);
        display: flex; gap: 8px; width: 85%; max-width: 480px; z-index: 9999;
        box-sizing: border-box; transition: opacity 0.3s;
    `;

    const inputField = document.createElement('input');
    inputField.type = 'text'; inputField.id = 'param-text-input';
    inputField.placeholder = 'ソラへキーボードからメッセージを入力...';
    inputField.style.cssText = `
        flex: 1; padding: 10px 14px; background: rgba(0, 0, 0, 0.75);
        border: 1px solid #00ffcc; color: #ffffff; border-radius: 6px;
        font-size: 14px; outline: none; font-family: sans-serif;
        box-shadow: 0 0 10px rgba(0, 255, 204, 0.2); transition: all 0.2s;
    `;
    inputField.onfocus = () => { inputField.style.boxShadow = '0 0 15px rgba(0, 255, 204, 0.5)'; };
    inputField.onblur = () => { inputField.style.boxShadow = '0 0 10px rgba(0, 255, 204, 0.2)'; };

    const sendButton = document.createElement('button');
    sendButton.id = 'send-txt-btn'; sendButton.innerText = '送信';
    sendButton.style.cssText = `
        padding: 0 18px; background: #00ffcc; border: none; color: #000000;
        font-weight: bold; border-radius: 6px; font-size: 14px; cursor: pointer;
        box-shadow: 0 0 10px rgba(0, 255, 204, 0.4); transition: background 0.2s;
    `;
    sendButton.onmouseover = () => { sendButton.style.background = '#00e6b8'; };
    sendButton.onmouseout = () => { sendButton.style.background = '#00ffcc'; };

    const handleSend = () => {
        if (!isStarted) { activateSystem(); return; }
        const textValue = inputField.value.trim();
        if (!textValue) return;

        appendMessage('user', `あなた: ${textValue}`);
        isAiTurn = true;
        try { recognition.stop(); } catch(e){}
        isRecognitionActive = false; micIndicator.style.display = 'none'; stopIdleTimer();

        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "text", text: textValue }));
        }
        inputField.value = ''; 
    };

    sendButton.addEventListener('click', handleSend);
    inputField.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); handleSend(); } });

    formContainer.appendChild(inputField); formContainer.appendChild(sendButton);
    document.body.appendChild(formContainer);
}
window.addEventListener('DOMContentLoaded', initTextInputForm);
window.addEventListener('DOMContentLoaded', () => { refreshCameraOptions(false); });
