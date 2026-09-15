const input = document.getElementById("messageInput");
const sendButton = document.getElementById("sendButton");
const messages = document.getElementById("messages");
const joinButton = document.getElementById("joinButton");
const errorBanner = document.getElementById("errorBanner");
const sosButton = document.getElementById("sosButton");
const sosStatus = document.getElementById("sosStatus");
const broadcastBanner =
    document.getElementById("broadcastBanner");
const broadcastPriority =
    document.getElementById("broadcastPriority");
const broadcastMessage =
    document.getElementById("broadcastMessage");
const broadcastAckButton =
    document.getElementById("broadcastAckButton");

let sessionToken = localStorage.getItem("nirapodnet_session_token");
let currentUser = null;

function authHeaders() {
    return sessionToken
        ? {
            "Authorization": `Bearer ${sessionToken}`
        }
        : {};
}

function storeSession(data) {
    if (!data || !data.token) {
        return;
    }

    sessionToken = data.token;

    localStorage.setItem(
        "nirapodnet_session_token",
        sessionToken
    );

    currentUser = data.user || currentUser;
}

function showError(message) {
    errorBanner.textContent = message;
    errorBanner.style.display = "block";
}

function clearError() {
    errorBanner.textContent = "";
    errorBanner.style.display = "none";
}

function showSOSAlert(data) {
    const message =
        `🚨 SOS ${data.incident_id}\n` +
        `Type: ${data.emergency_type}\n` +
        `Description: ${data.description || "None"}`;

    showError(message);

    if ("speechSynthesis" in window) {
        const speech = new SpeechSynthesisUtterance(
            "Emergency SOS received"
        );

        window.speechSynthesis.speak(speech);
    }
}

function showBroadcastAlert(broadcast) {
    broadcastPriority.textContent =
        broadcast.priority.toUpperCase();

    broadcastMessage.textContent =
        `${broadcast.broadcast_type || broadcast.type}: ` +
        broadcast.message;

    broadcastBanner.className =
        `broadcast-banner ${broadcast.priority}`;

    broadcastBanner.style.display = "block";

    if (broadcast.id) {
        broadcastBanner.dataset.broadcastId =
            broadcast.id;
    }

    if (
        broadcast.priority === "critical" &&
        "speechSynthesis" in window
    ) {
        const speech =
            new SpeechSynthesisUtterance(
                "Critical emergency alert"
            );

        window.speechSynthesis.speak(speech);
    }
}

broadcastAckButton.addEventListener(
    "click",
    () => {
        broadcastBanner.style.display = "none";
    }
);

function handleSOSStatusUpdate(data) {
    console.log(
        `SOS ${data.incident_id} → ${data.status}`
    );
}

let socket = null;
let reconnectTimer = null;

const displayedMessages = new Set();
const displayedClientIds = new Set();

const QUEUE_KEY = "nirapodnet_pending_messages";
const LAST_BROADCAST_ID_KEY =
    "nirapodnet_last_broadcast_id";

function getLastBroadcastId() {
    return Number(
        localStorage.getItem(
            LAST_BROADCAST_ID_KEY
        ) || 0
    );
}

function saveLastBroadcastId(id) {
    localStorage.setItem(
        LAST_BROADCAST_ID_KEY,
        String(id)
    );
}

function getPendingMessages() {
    return JSON.parse(localStorage.getItem(QUEUE_KEY) || "[]");
}

function savePendingMessages(queue) {
    localStorage.setItem(QUEUE_KEY, JSON.stringify(queue));
}

function connectWebSocket() {

    const protocol = window.location.protocol === "https:"
        ? "wss:"
        : "ws:";

    socket = new WebSocket(
        `${protocol}//${window.location.host}/ws?token=${encodeURIComponent(sessionToken)}`
    );

    const networkStatus = document.getElementById("networkStatus");

    socket.onopen = () => {
        clearError();

        console.log("websocket connected");

        networkStatus.textContent = "🟢 Connected";
        networkStatus.className = "online";

        syncPendingMessages();
        syncMissedBroadcasts();
        updateQueueCount();

        sendButton.disabled = false;
    };

    socket.onclose = () => {
        networkStatus.textContent = "🔴 Offline";
        networkStatus.className = "offline";

        reconnect();
    };

    socket.onerror = () => {
        networkStatus.textContent = "🔴 Connection Error";
        networkStatus.className = "offline";
        showError("WebSocket connection error. Attempting to reconnect...");
    };

    socket.onmessage = (event) => {

        const data = JSON.parse(event.data);

        if (data.type === "ack") {

            removePending(data.client_id);

            addMessage({
                id: data.message_id,
                client_id: data.client_id,
                sender_id: data.sender_id,
                sender: data.sender,
                content: data.content,
                timestamp: data.timestamp
            });
            return;
        }

        if (data.type === "message") {

            addMessage(data);
            return;
        }

        if (data.type === "sos") {
            showSOSAlert(data);
            return;
        }

        if (data.type === "broadcast") {
            showBroadcastAlert(data);

            if (data.id) {
                saveLastBroadcastId(data.id);
            }

            return;
        }

        if (data.type === "sos_status") {
            handleSOSStatusUpdate(data);
            return;
        }

        if (data.type === "error") {

            console.error("Server error:", data.error);

            if (data.client_id) {
                showPendingMessage({
                    client_id: data.client_id,
                    sender: currentUser.username,
                    content: data.error
                });
            }
        }
    };
}

function reconnect() {

    if (reconnectTimer) {
        return;
    }

    reconnectTimer = setTimeout(() => {

        reconnectTimer = null;

        if (!socket || socket.readyState === WebSocket.CLOSED) {
            connectWebSocket();
        }
    }, 3000);
}

function addMessage(message) {
    if (
        (message.id && displayedMessages.has(message.id)) ||
        (message.client_id && displayedClientIds.has(message.client_id))
    ) {
        return;
    }

    if (message.id) {
        displayedMessages.add(message.id);
    }

    if (message.client_id) {
        displayedClientIds.add(message.client_id);
    }

    const pending = document.querySelector(
        `[data-client-id="${message.client_id}"]`
    );

    if (pending) {
        pending.remove();
    }

    const div = document.createElement("div");

    div.className = "message";

    if (message.sender_id === currentUser.id) {
        div.classList.add("mine");
    } else {
        div.classList.add("other");
    }

    const sender = document.createElement("strong");
    sender.textContent = message.sender;

    const content = document.createElement("div");
    content.textContent = message.content;

    const status = document.createElement("div");
    status.className = "delivery";
    status.textContent = "Delivered";

    div.appendChild(sender);
    div.appendChild(content);
    div.appendChild(status);

    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
}

function showPendingMessage(message) {
    const existing = document.querySelector(
        `[data-client-id="${message.client_id}"]`
    );

    if (existing) {
        return;
    }

    const div = document.createElement("div");

    div.className = "message pending";
    div.dataset.clientId = message.client_id;

    const sender = document.createElement("strong");
    sender.textContent = message.sender;

    const content = document.createElement("div");
    content.textContent = message.content;

    const status = document.createElement("div");
    status.className = "delivery";
    status.textContent = "Pending";

    div.appendChild(sender);
    div.appendChild(content);
    div.appendChild(status);

    messages.appendChild(div);

    messages.scrollTop = messages.scrollHeight;
}

function restorePendingMessages() {

    const queue = getPendingMessages();

    queue.forEach(message => {

        showPendingMessage(message);

    });

    updateQueueCount();
}

async function loadMessages() {

    try {

        const response = await fetch("/messages", {
            headers: authHeaders()
        });

        if (!response.ok) {
            throw new Error("Failed to load messages");
        }

        const data = await response.json();

        messages.innerHTML = "";

        data.forEach(addMessage);

        restorePendingMessages();

    } catch (error) {

        console.error("Message loading failed:", error);

    }
}

function trySendPendingMessages() {

    if (!socket || socket.readyState !== WebSocket.OPEN) {
        return;
    }

    const queue = getPendingMessages();

    for (const message of queue) {

        socket.send(JSON.stringify(message));

    }
}

function syncPendingMessages() {
    trySendPendingMessages();
}

function removePending(clientId) {

    if (!clientId) return;

    const pending = document.querySelector(
        `[data-client-id="${clientId}"]`
    );

    if (pending) {
        pending.remove();
    }

    const queue = getPendingMessages().filter(
        msg => msg.client_id !== clientId
    );

    savePendingMessages(queue);

    updateQueueCount();
}

function updateQueueCount() {
    const count = getPendingMessages().length;

    document.getElementById("queueCount").textContent =
        `Pending: ${count}`;
}

function generateId() {
    if (window.crypto && window.crypto.randomUUID) {
        return crypto.randomUUID();
    }
    // Fallback for non-secure contexts (like HTTP network IPs)
    return 'id-' + Math.random().toString(36).substr(2, 9) + '-' + Date.now();
}

function sendMessage() {

    const text = input.value.trim();
    if (!text) return;

    const message = {
        client_id: generateId(),
        sender_id: currentUser.id,
        content: text
    };

    const queue = getPendingMessages();
    queue.push(message);
    savePendingMessages(queue);
    showPendingMessage(message);
    updateQueueCount();

    input.value = "";
    trySendPendingMessages();

}

async function sendSOS() {
    clearError();

    if (!sessionToken) {
        showError("You must be logged in.");
        return;
    }

    sosButton.disabled = true;

    try {
        const response = await fetch("/api/sos", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${sessionToken}`
            },
            body: JSON.stringify({
                emergency_type: "other",
                latitude: null,
                longitude: null,
                description: "Emergency SOS"
            })
        });

        if (!response.ok) {
            let message = "Failed to send SOS.";

            try {
                const error = await response.json();

                if (error.detail) {
                    message = error.detail;
                }
            } catch {
                // Keep default error message.
            }

            throw new Error(message);
        }

        const incident = await response.json();

        sosStatus.textContent =
            `SOS sent: ${incident.incident_id}`;

    } catch (error) {
        console.error("SOS failed:", error);
        showError(
            error.message || "Failed to send SOS."
        );
    } finally {
        sosButton.disabled = false;
    }
}

async function joinNetwork() {
    clearError();

    const username = document.getElementById("usernameInput").value.trim();

    if (username.length < 3 || username.length > 50) {
        showError("Username must be between 3 and 50 characters.");
        return;
    }

    try {
        const response = await fetch("/users", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ username })
        });

        if (!response.ok) {
    let message = "Unable to join the network.";

    try {
        const error = await response.json();

        if (Array.isArray(error.detail)) {
            message = error.detail
                .map(item => item.msg)
                .join(", ");
        } else if (error.detail) {
            message = error.detail;
        }
    } catch {
        // Keep default error message
    }

    throw new Error(message);
        }

        const data = await response.json();

        if (data.token) {
            storeSession(data);
            currentUser = data.user;
        } else {
            currentUser = data;
        }

        document.getElementById("userLabel").textContent = `Logged in as ${currentUser.username}`;

        document.getElementById("loginBox").style.display = "none";
        document.getElementById("chatBox").style.display = "block";

        connectWebSocket();
        loadMessages();
        updateQueueCount();
    } catch (error) {
        console.error(error);
        showError(error.message || "Unable to join the network.");
    }
}

sendButton.addEventListener("click", sendMessage);

input.addEventListener("keydown", event => {
    if (event.key === "Enter") {
        sendMessage();
    }
});

joinButton.addEventListener("click", joinNetwork);
sosButton.addEventListener("click", sendSOS);