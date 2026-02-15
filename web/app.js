"use strict";

// --- DOM refs ---
const connectScreen = document.getElementById("connect-screen");
const agentScreen = document.getElementById("agent-screen");
const tokenInput = document.getElementById("token-input");
const connectBtn = document.getElementById("connect-btn");
const connectStatus = document.getElementById("connect-status");
const conversationLog = document.getElementById("conversation-log");
const talkBtn = document.getElementById("talk-btn");
const stopBtn = document.getElementById("stop-btn");
const providerSelect = document.getElementById("provider-select");

// --- State ---
let iceServers = window.__CONFIG__ || [];
let ws = null;
let pc = null;
let audioEl = null;
let micStream = null;
let isRecording = false;
let agentSpeaking = false;

// --- Chat bubble helpers ---
function addChatBubble(text, role) {
    const thinking = conversationLog.querySelector(".thinking");
    if (thinking) thinking.remove();

    const bubble = document.createElement("div");
    bubble.className = "msg msg-" + role;
    bubble.textContent = text;
    conversationLog.appendChild(bubble);
    conversationLog.scrollTop = conversationLog.scrollHeight;
}

function showThinking() {
    const el = document.createElement("div");
    el.className = "msg msg-agent thinking";
    el.textContent = "Thinking...";
    conversationLog.appendChild(el);
    conversationLog.scrollTop = conversationLog.scrollHeight;
}

function setAgentSpeaking(speaking) {
    agentSpeaking = speaking;
    if (speaking) {
        stopBtn.classList.remove("hidden");
    } else {
        stopBtn.classList.add("hidden");
    }
}

// --- WebSocket ---
function sendMsg(type, payload = {}) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type, ...payload }));
}

function connect() {
    const token = tokenInput.value.trim();
    if (!token) { setStatus("Enter a token", true); return; }

    connectBtn.disabled = true;
    setStatus("Connecting...");

    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${proto}//${location.host}/ws`);

    ws.onopen = () => {
        setStatus("Authenticating...");
        sendMsg("hello", { token });
    };

    ws.onmessage = (ev) => {
        let msg;
        try { msg = JSON.parse(ev.data); } catch { return; }
        handleMessage(msg);
    };

    ws.onerror = () => {
        setStatus("Connection failed", true);
        connectBtn.disabled = false;
    };

    ws.onclose = () => {
        if (!agentScreen.classList.contains("hidden")) {
            agentScreen.classList.add("hidden");
            connectScreen.classList.remove("hidden");
        }
        setStatus("Disconnected", true);
        connectBtn.disabled = false;
        cleanupWebRTC();
    };
}

function setStatus(text, isError) {
    connectStatus.textContent = text;
    connectStatus.className = "connect-status" + (isError ? " error" : "");
}

function handleMessage(msg) {
    switch (msg.type) {
        case "hello_ack":
            if (msg.ice_servers && msg.ice_servers.length > 0) {
                iceServers = msg.ice_servers;
            }
            // Populate provider selector
            if (msg.llm_providers) {
                while (providerSelect.firstChild) providerSelect.removeChild(providerSelect.firstChild);
                msg.llm_providers.forEach((p) => {
                    const opt = document.createElement("option");
                    opt.value = p.id;
                    opt.textContent = p.name;
                    if (p.id === msg.llm_default) opt.selected = true;
                    providerSelect.appendChild(opt);
                });
            }
            startWebRTC();
            break;

        case "webrtc_answer":
            handleWebRTCAnswer(msg.sdp);
            break;

        case "transcription":
            if (!msg.partial && msg.text) {
                addChatBubble(msg.text, "user");
            }
            break;

        case "agent_thinking":
            showThinking();
            break;

        case "agent_reply":
            addChatBubble(msg.text, "agent");
            setAgentSpeaking(true);
            break;

        case "error":
            console.error("Server error:", msg.message);
            break;

        case "pong":
            break;
    }
}

// --- WebRTC ---
async function startWebRTC() {
    setStatus("Setting up mic...");

    try {
        micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
        setStatus("Mic access denied", true);
        connectBtn.disabled = false;
        return;
    }

    setStatus("Connecting audio...");

    const config = { iceServers: iceServers.length > 0 ? iceServers : undefined };
    pc = new RTCPeerConnection(config);

    const micTrack = micStream.getAudioTracks()[0];
    pc.addTrack(micTrack, micStream);

    pc.oniceconnectionstatechange = () => {
        if (pc.iceConnectionState === "connected" || pc.iceConnectionState === "completed") {
            connectScreen.classList.add("hidden");
            agentScreen.classList.remove("hidden");
            talkBtn.disabled = false;

            if (audioEl) {
                audioEl.play().catch(() => {});
            }
        }
    };

    pc.ontrack = (ev) => {
        if (audioEl) { audioEl.srcObject = null; audioEl.remove(); }
        audioEl = document.createElement("audio");
        audioEl.autoplay = true;
        audioEl.playsInline = true;
        audioEl.srcObject = ev.streams[0] || new MediaStream([ev.track]);
        document.body.appendChild(audioEl);
    };

    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    await waitForIceGathering(pc);
    sendMsg("webrtc_offer", { sdp: pc.localDescription.sdp });
}

function waitForIceGathering(pc) {
    return new Promise((resolve) => {
        if (pc.iceGatheringState === "complete") { resolve(); return; }
        pc.onicegatheringstatechange = () => {
            if (pc.iceGatheringState === "complete") resolve();
        };
    });
}

async function handleWebRTCAnswer(sdp) {
    if (!pc) return;
    await pc.setRemoteDescription({ type: "answer", sdp });
}

function cleanupWebRTC() {
    if (pc) { pc.close(); pc = null; }
    if (audioEl) { audioEl.srcObject = null; audioEl.remove(); audioEl = null; }
    if (micStream) {
        micStream.getTracks().forEach((t) => t.stop());
        micStream = null;
    }
    isRecording = false;
    talkBtn.textContent = "Hold to Talk";
    talkBtn.classList.remove("recording");
    talkBtn.disabled = true;
    setAgentSpeaking(false);
}

// --- Hold to Talk ---
function startTalking() {
    if (!micStream || isRecording) return;
    isRecording = true;
    talkBtn.classList.add("recording");
    talkBtn.textContent = "Listening... release to send";

    // Stop any current agent audio
    if (agentSpeaking) {
        sendMsg("stop_speaking");
        setAgentSpeaking(false);
    }

    sendMsg("mic_start");
}

function stopTalking() {
    if (!isRecording) return;
    isRecording = false;
    talkBtn.classList.remove("recording");
    talkBtn.textContent = "Hold to Talk";
    sendMsg("mic_stop");
}

// --- Stop agent audio ---
function stopSpeaking() {
    sendMsg("stop_speaking");
    setAgentSpeaking(false);
}

// --- Keepalive ---
setInterval(() => { sendMsg("ping"); }, 25000);

// --- Event listeners ---
connectBtn.addEventListener("click", connect);
stopBtn.addEventListener("click", stopSpeaking);
providerSelect.addEventListener("change", () => {
    sendMsg("set_provider", { provider: providerSelect.value });
});

tokenInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter") connect();
});

// Hold-to-talk: touch events (mobile)
talkBtn.addEventListener("touchstart", (e) => {
    e.preventDefault(); // Prevent long-press menu & ghost clicks
    startTalking();
});
talkBtn.addEventListener("touchend", (e) => {
    e.preventDefault();
    stopTalking();
});
talkBtn.addEventListener("touchcancel", (e) => {
    e.preventDefault();
    stopTalking();
});

// Hold-to-talk: mouse events (desktop fallback)
talkBtn.addEventListener("mousedown", (e) => {
    if (e.button !== 0) return; // Left click only
    startTalking();
});
talkBtn.addEventListener("mouseup", () => { stopTalking(); });
talkBtn.addEventListener("mouseleave", () => {
    if (isRecording) stopTalking();
});
