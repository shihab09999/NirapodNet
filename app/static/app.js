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
        // Clear the linkage so a later check-in is not silently
        // attached to this broadcast after it was acknowledged.
        delete broadcastBanner.dataset.broadcastId;
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
            refreshSosList();
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
            refreshSosList();
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

async function syncMissedBroadcasts() {
    if (!sessionToken) {
        return;
    }

    try {
        const afterId = getLastBroadcastId();

        const response = await fetch(
            `/api/broadcasts?after_id=${afterId}`,
            {
                headers: authHeaders()
            }
        );

        if (!response.ok) {
            return;
        }

        const broadcasts = await response.json();

        if (!broadcasts.length) {
            return;
        }

        // Every missed broadcast is added to the message list as a
        // system notice so none of them is silently dropped; the
        // newest one is also shown as the banner.
        for (const missed of broadcasts) {
            addSystemNotice(
                `📢 ${missed.type}: ${missed.message}`
            );
        }

        const latest = broadcasts[broadcasts.length - 1];

        showBroadcastAlert(latest);
        saveLastBroadcastId(latest.id);
    } catch (error) {
        console.error("Broadcast sync failed:", error);
    }
}

const CHECKIN_LABELS = {
    "SAFE": "Safe",
    "NEED_HELP": "Need Help",
    "NOT_AT_LOCATION": "Not at Location",
    "UNABLE_TO_RESPOND": "Unable to Respond"
};

async function sendCheckIn(status) {
    const checkinStatus =
        document.getElementById("checkinStatus");

    try {
        // Link the check-in to a broadcast only while that
        // broadcast's banner is still on screen.
        const broadcastId =
            broadcastBanner.style.display !== "none" &&
            broadcastBanner.dataset.broadcastId
                ? Number(broadcastBanner.dataset.broadcastId)
                : null;

        const response = await fetch("/api/checkins", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                ...authHeaders()
            },
            body: JSON.stringify({
                status: status,
                broadcast_id: broadcastId
            })
        });

        if (!response.ok) {
            throw new Error("Failed to send check-in.");
        }

        checkinStatus.textContent =
            `Checked in as: ${CHECKIN_LABELS[status] || status}`;

        refreshCheckinSummary();
        refreshCheckinList();
    } catch (error) {
        console.error("Check-in failed:", error);
        checkinStatus.textContent =
            "Check-in failed. Please try again.";
    }
}

function operatorRoles() {
    return ["rescue", "responder", "operator", "admin"];
}

function addSystemNotice(text) {
    const div = document.createElement("div");

    div.className = "message system";
    div.textContent = text;

    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
}

function setupOperatorPanel() {
    const panel = document.getElementById("operatorPanel");

    if (!currentUser || !operatorRoles().includes(currentUser.role)) {
        panel.style.display = "none";
        return;
    }

    panel.style.display = "block";

    const auditBlock = document.getElementById("auditBlock");

    auditBlock.style.display =
        ["operator", "admin"].includes(currentUser.role)
            ? "block"
            : "none";

    const adminBlock = document.getElementById("adminBlock");

    adminBlock.style.display =
        currentUser.role === "admin" ? "block" : "none";

    refreshSosList();
    refreshCheckinSummary();
    refreshCheckinList();
    refreshAuditList();
    refreshAdminUsers();
}

async function refreshCheckinList() {
    const list = document.getElementById("checkinList");

    if (!list || !currentUser ||
        !operatorRoles().includes(currentUser.role)) {
        return;
    }

    try {
        const response = await fetch("/api/checkins", {
            headers: authHeaders()
        });

        if (!response.ok) {
            return;
        }

        const checkins = await response.json();

        list.innerHTML = "";

        if (!checkins.length) {
            list.textContent = "No check-ins yet.";
            return;
        }

        for (const checkin of checkins.slice(0, 10)) {
            const item = document.createElement("div");
            item.className = "operator-item";
            item.textContent =
                `${checkin.username} — ` +
                (CHECKIN_LABELS[checkin.status] || checkin.status);
            list.appendChild(item);
        }
    } catch (error) {
        console.error("Check-in list failed:", error);
    }
}

async function refreshAdminUsers() {
    const list = document.getElementById("adminUserList");

    if (!list || !currentUser || currentUser.role !== "admin") {
        return;
    }

    try {
        const response = await fetch("/api/admin/users", {
            headers: authHeaders()
        });

        if (!response.ok) {
            return;
        }

        const users = await response.json();
        const roles = [
            "user", "rescue", "responder", "operator", "admin"
        ];

        list.innerHTML = "";

        for (const user of users) {
            const item = document.createElement("div");
            item.className = "operator-item";

            const label = document.createElement("span");
            label.textContent = `${user.username} `;
            item.appendChild(label);

            const select = document.createElement("select");

            for (const role of roles) {
                const option = document.createElement("option");
                option.value = role;
                option.textContent = role;
                option.selected = user.role === role;
                select.appendChild(option);
            }

            item.appendChild(select);

            const button = document.createElement("button");
            button.textContent = "Apply";
            button.addEventListener("click", async () => {
                await fetch(
                    `/api/admin/users/${user.id}/role`,
                    {
                        method: "PATCH",
                        headers: {
                            "Content-Type": "application/json",
                            ...authHeaders()
                        },
                        body: JSON.stringify({
                            role: select.value
                        })
                    }
                );
                refreshAdminUsers();
                refreshAuditList();
            });
            item.appendChild(button);

            list.appendChild(item);
        }
    } catch (error) {
        console.error("Admin user list failed:", error);
    }
}

async function refreshSosList() {
    const list = document.getElementById("sosList");

    if (!list || !currentUser ||
        !operatorRoles().includes(currentUser.role)) {
        return;
    }

    try {
        const response = await fetch("/api/sos", {
            headers: authHeaders()
        });

        if (!response.ok) {
            return;
        }

        const incidents = await response.json();

        list.innerHTML = "";

        if (!incidents.length) {
            list.textContent = "No SOS incidents.";
            return;
        }

        const nextStatus = {
            "OPEN": "RESPONDING",
            "RESPONDING": "ON-SCENE",
            "ON-SCENE": "RESOLVED"
        };

        for (const incident of incidents) {
            const item = document.createElement("div");
            item.className = "operator-item";

            const text = document.createElement("div");
            text.textContent =
                `${incident.incident_id} — ` +
                `${incident.emergency_type} — ${incident.status}` +
                (incident.description
                    ? ` — ${incident.description}`
                    : "");
            item.appendChild(text);

            const historyButton = document.createElement("button");
            historyButton.textContent = "History";
            historyButton.addEventListener("click", async () => {
                const response = await fetch(
                    `/api/sos/${incident.incident_id}/history`,
                    {
                        headers: authHeaders()
                    }
                );

                if (!response.ok) {
                    return;
                }

                const history = await response.json();
                const detail = document.createElement("div");
                detail.textContent = history
                    .map(entry =>
                        `${entry.old_status || "—"} → ` +
                        entry.new_status)
                    .join(", ");
                item.appendChild(detail);
            });
            item.appendChild(historyButton);

            const next = nextStatus[incident.status];

            if (next) {
                const button = document.createElement("button");
                button.textContent = `Mark ${next}`;
                button.addEventListener("click", async () => {
                    await fetch(
                        `/api/sos/${incident.incident_id}/status`,
                        {
                            method: "PATCH",
                            headers: {
                                "Content-Type": "application/json",
                                ...authHeaders()
                            },
                            body: JSON.stringify({ status: next })
                        }
                    );
                    refreshSosList();
                });
                item.appendChild(button);
            }

            list.appendChild(item);
        }
    } catch (error) {
        console.error("SOS list failed:", error);
    }
}

async function refreshCheckinSummary() {
    const summary = document.getElementById("checkinSummary");

    if (!summary || !currentUser ||
        !operatorRoles().includes(currentUser.role)) {
        return;
    }

    try {
        const response = await fetch("/api/checkins/summary", {
            headers: authHeaders()
        });

        if (!response.ok) {
            return;
        }

        const data = await response.json();

        summary.textContent =
            `Checked in: ${data.checked_in_users} / ` +
            `${data.total_users} users — ` +
            Object.entries(data.counts)
                .map(([status, count]) =>
                    `${CHECKIN_LABELS[status] || status}: ${count}`)
                .join(", ");
    } catch (error) {
        console.error("Check-in summary failed:", error);
    }
}

async function refreshAuditList() {
    const list = document.getElementById("auditList");

    if (!list || !currentUser ||
        !["operator", "admin"].includes(currentUser.role)) {
        return;
    }

    try {
        const response = await fetch("/api/audit-logs?limit=20", {
            headers: authHeaders()
        });

        if (!response.ok) {
            return;
        }

        const logs = await response.json();

        list.innerHTML = "";

        if (!logs.length) {
            list.textContent = "No audit entries yet.";
            return;
        }

        for (const entry of logs) {
            const item = document.createElement("div");
            item.className = "operator-item";
            item.textContent =
                `${entry.actor} — ${entry.action}` +
                (entry.detail ? ` — ${entry.detail}` : "");
            list.appendChild(item);
        }
    } catch (error) {
        console.error("Audit list failed:", error);
    }
}

async function sendBroadcast() {
    const statusElement =
        document.getElementById("broadcastSendStatus");
    const type = document
        .getElementById("broadcastTypeInput").value.trim();
    const priority = document
        .getElementById("broadcastPriorityInput").value;
    const message = document
        .getElementById("broadcastMessageInput").value.trim();

    if (!type || !message) {
        statusElement.textContent =
            "Type and message are required.";
        return;
    }

    try {
        const response = await fetch("/api/broadcasts", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                ...authHeaders()
            },
            body: JSON.stringify({
                type: type,
                message: message,
                priority: priority
            })
        });

        if (!response.ok) {
            throw new Error("Failed to send broadcast.");
        }

        statusElement.textContent = "Broadcast sent.";
        document
            .getElementById("broadcastMessageInput").value = "";
        refreshAuditList();
    } catch (error) {
        console.error("Broadcast failed:", error);
        statusElement.textContent =
            "Broadcast failed. Please try again.";
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

function getCurrentLocation() {
    // Best-effort location: resolves to null when geolocation is
    // unavailable, denied, or too slow, so the SOS is never delayed.
    return new Promise(resolve => {
        if (!navigator.geolocation) {
            resolve(null);
            return;
        }

        const timer = setTimeout(() => resolve(null), 1500);

        navigator.geolocation.getCurrentPosition(
            position => {
                clearTimeout(timer);
                resolve({
                    latitude: position.coords.latitude,
                    longitude: position.coords.longitude
                });
            },
            () => {
                clearTimeout(timer);
                resolve(null);
            },
            { timeout: 1500 }
        );
    });
}

async function sendSOS() {
    clearError();

    if (!sessionToken) {
        showError("You must be logged in.");
        return;
    }

    sosButton.disabled = true;

    try {
        const emergencyType =
            document.getElementById("sosTypeInput").value;
        const description = document
            .getElementById("sosDescriptionInput").value.trim();
        const location = await getCurrentLocation();

        const response = await fetch("/api/sos", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${sessionToken}`
            },
            body: JSON.stringify({
                emergency_type: emergencyType,
                latitude: location ? location.latitude : null,
                longitude: location ? location.longitude : null,
                description: description || null
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

async function loginRequest(username, password) {
    const response = await fetch("/api/login", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({ username, password })
    });

    if (!response.ok) {
        return null;
    }

    return response.json();
}

async function joinNetwork() {
    clearError();

    const username = document.getElementById("usernameInput").value.trim();
    const password = document.getElementById("passwordInput").value;

    if (username.length < 3 || username.length > 50) {
        showError("Username must be between 3 and 50 characters.");
        return;
    }

    if (password.length < 8 || password.length > 128) {
        showError("Password must be between 8 and 128 characters.");
        return;
    }

    try {
        let data = await loginRequest(username, password);

        if (!data) {
            // First time this username is used: register, then log in.
            const registerResponse = await fetch("/api/register", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({ username, password })
            });

            if (registerResponse.status === 409) {
                throw new Error(
                    "That username already exists and the password " +
                    "did not match. Please check your password."
                );
            }

            if (!registerResponse.ok) {
                throw new Error("Unable to create the account.");
            }

            data = await loginRequest(username, password);

            if (!data) {
                throw new Error("Account created, but login failed.");
            }
        }

        storeSession(data);
        currentUser = data.user;

        showChatUI();
    } catch (error) {
        console.error(error);
        showError(error.message || "Unable to join the network.");
    }
}

function showChatUI() {
    document.getElementById("userLabel").textContent =
        `Logged in as ${currentUser.username}`;

    document.getElementById("loginBox").style.display = "none";
    document.getElementById("chatBox").style.display = "block";
    document.getElementById("logoutButton").style.display =
        "inline-block";

    setupOperatorPanel();

    connectWebSocket();
    loadMessages();
    updateQueueCount();
}

async function restoreSession() {
    if (!sessionToken) {
        return;
    }

    try {
        const response = await fetch("/api/me", {
            headers: authHeaders()
        });

        if (!response.ok) {
            throw new Error("Session expired");
        }

        currentUser = await response.json();

        showChatUI();
    } catch (error) {
        sessionToken = null;
        localStorage.removeItem("nirapodnet_session_token");
    }
}

async function logout() {
    try {
        await fetch("/api/logout", {
            method: "POST",
            headers: authHeaders()
        });
    } catch (error) {
        console.error("Logout failed:", error);
    }

    sessionToken = null;
    currentUser = null;
    localStorage.removeItem("nirapodnet_session_token");

    location.reload();
}

sendButton.addEventListener("click", sendMessage);

input.addEventListener("keydown", event => {
    if (event.key === "Enter") {
        sendMessage();
    }
});

joinButton.addEventListener("click", joinNetwork);
sosButton.addEventListener("click", sendSOS);

document
    .querySelectorAll("[data-checkin-status]")
    .forEach(button => {
        button.addEventListener("click", () => {
            sendCheckIn(button.dataset.checkinStatus);
        });
    });

document
    .getElementById("broadcastSendButton")
    .addEventListener("click", sendBroadcast);

document
    .getElementById("sosRefreshButton")
    .addEventListener("click", refreshSosList);

document
    .getElementById("checkinRefreshButton")
    .addEventListener("click", refreshCheckinSummary);

document
    .getElementById("auditRefreshButton")
    .addEventListener("click", refreshAuditList);

document
    .getElementById("adminRefreshButton")
    .addEventListener("click", refreshAdminUsers);

document
    .getElementById("logoutButton")
    .addEventListener("click", logout);

restoreSession();