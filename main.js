const ws = new WebSocket('ws://localhost:8000/ws');
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
        ws.send(JSON.stringify({ type: "idle_soliloquy" }));
    }, dynamicTimeout);
}

function stopIdleTimer() {
    if (idleTimer) {
        clearTimeout(idleTimer);
        idleTimer = null;
    }
}

function activateSystem() {
    if (startBtn.disabled) return;
    startBtn.disabled = true;
    startBtn.style.display = 'none'; 
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    
    isStarted = true;
    chatLog.innerHTML = "";
    appendMessage('status', "何か 話しかけてください...");
    
    ws.send(JSON.stringify({ type: "start_system" }));
    
    sendSettingsToServer();
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
            ws.send(JSON.stringify({ type: "settings_changed" }));
        } else {
            startListening();
        }
        resetIdleTimer();
    }
}

function sendSettingsToServer() {
    if (ws.readyState !== WebSocket.OPEN) return;

    const vRate = (parseInt(document.getElementById('param-rate').value) >= 0 ? "+" : "") + document.getElementById('param-rate').value + "%";
    const vPitch = (parseInt(document.getElementById('param-pitch').value) >= 0 ? "+" : "") + document.getElementById('param-pitch').value + "Hz";
    const vVoice = document.getElementById('param-voice').value;
    const vMirror = document.getElementById('param-mirror').value;
    const vCamera = parseInt(document.getElementById('param-camera').value);

    ws.send(JSON.stringify({
        type: "settings",
        voice: vVoice,
        rate: vRate,
        pitch: vPitch,
        mirror: vMirror,
        camera: vCamera,
        visual_changed: isVisualParamChanged 
    }));
    isVisualParamChanged = false; 
}

function appendMessage(role, text) {
    if (!isStarted && role !== 'status') return null;
    const msgDiv = document.createElement('div');
    if (role === 'user') msgDiv.className = 'msg-user';
    else if (role === 'ai') msgDiv.className = 'msg-ai';
    else if (role === 'status') msgDiv.className = 'msg-status'; 
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
    if (!isStarted || isOptionsOpen) {
        try { recognition.stop(); } catch(e){}
        return;
    }
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
    ws.send(JSON.stringify({ type: "text", text: speechText }));
};

recognition.onerror = (event) => {
    isRecognitionActive = false;
    micIndicator.style.display = 'none';
    resetIdleTimer();
};

recognition.onend = () => {
    isRecognitionActive = false;
    micIndicator.style.display = 'none'; 
    if (isStarted && !isAiTurn && !window.isSpeaking && !isOptionsOpen) startListening();
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
        audioQueue.push({ bufferArray: bytesToBuffer(msg.audio), text: msg.text });
        if (!isPlayingAudio) playNextInQueue();
    }
};

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
        startListening(); resetIdleTimer(); 
        return;
    }
    isPlayingAudio = true; window.isSpeaking = true; 
    const currentItem = audioQueue.shift();
    appendMessage('ai', currentItem.text); 
    try {
        const audioBuffer = await audioCtx.decodeAudioData(currentItem.bufferArray);
        const source = audioCtx.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(audioCtx.destination);
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
    const val = parseFloat(e.target.value);
    document.getElementById('val-vrm-x').innerText = val.toFixed(2);
    if (window.currentVrm) window.currentVrm.scene.position.x = val;
    isVisualParamChanged = true; 
});
pVrmY.addEventListener('input', (e) => {
    const val = parseFloat(e.target.value);
    document.getElementById('val-vrm-y').innerText = val.toFixed(2);
    isVisualParamChanged = true;
});
pVrmScale.addEventListener('input', (e) => {
    const val = parseFloat(e.target.value);
    document.getElementById('val-vrm-scale').innerText = val.toFixed(2);
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