const chat = document.getElementById("chat");
const form = document.getElementById("chatForm");
const input = document.getElementById("input");
const sendBtn = document.getElementById("send");
const welcome = document.getElementById("welcome");
const newChatBtn = document.getElementById("newChat");

let threadId = null;
let busy = false;

// --- helpers ---------------------------------------------------------------

function scrollDown() {
    chat.scrollTop = chat.scrollHeight;
}

function escapeHtml(s) {
    const d = document.createElement("div");
    d.textContent = s;
    return d.innerHTML;
}

function addMessage(role, htmlContent) {
    if (welcome) welcome.remove();
    const wrap = document.createElement("div");
    wrap.className = `msg ${role}`;
    wrap.innerHTML = `
        <div class="avatar">${role === "user" ? "🧑" : "🧭"}</div>
        <div class="bubble">${htmlContent}</div>
    `;
    chat.appendChild(wrap);
    scrollDown();
    return wrap;
}

function typingBubble() {
    return addMessage(
        "bot",
        `<div class="typing"><span></span><span></span><span></span></div>`
    );
}

// Build the collapsible "raw data" section (flights / trains / hotels).
function detailsBlock(data) {
    const parts = [];
    const add = (label, text) => {
        if (text && text.trim()) {
            parts.push(
                `<details class="details"><summary>${label}</summary><pre>${escapeHtml(
                    text
                )}</pre></details>`
            );
        }
    };
    add("✈️ Flights", data.flight_results);
    add("🚆 Trains", data.train_results);
    add("🏨 Hotels", data.hotel_results);
    return parts.join("");
}

// --- send ------------------------------------------------------------------

async function send(message) {
    if (busy || !message.trim()) return;
    busy = true;
    sendBtn.disabled = true;

    addMessage("user", escapeHtml(message));
    input.value = "";
    input.style.height = "auto";

    const typing = typingBubble();

    try {
        const res = await fetch("/chat/stream", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message, thread_id: threadId }),
        });

        if (!res.ok || !res.body) throw new Error(`Server error ${res.status}`);

        // Wire format: first line = JSON meta, everything after = markdown answer.
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let raw = "";
        let meta = null;
        let bubbleEl = null;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            raw += decoder.decode(value, { stream: true });

            const nl = raw.indexOf("\n");
            if (nl === -1) continue; // meta line not complete yet

            if (!meta) {
                meta = JSON.parse(raw.slice(0, nl));
                threadId = meta.thread_id;
                typing.remove();
                const wrap = addMessage("bot", "");
                bubbleEl = wrap.querySelector(".bubble");
            }

            const answer = raw.slice(nl + 1);
            bubbleEl.innerHTML = marked.parse(answer);
            scrollDown();
        }

        // Finalise: attach raw flight/train/hotel panels.
        if (meta && bubbleEl) {
            const answer = raw.slice(raw.indexOf("\n") + 1);
            bubbleEl.innerHTML =
                marked.parse(answer || "*No response.*") + detailsBlock(meta);
            scrollDown();
        }
    } catch (err) {
        typing.remove();
        addMessage(
            "bot",
            `<span style="color:#ff8080">⚠️ ${escapeHtml(err.message)}. Is the server running?</span>`
        );
    } finally {
        busy = false;
        sendBtn.disabled = false;
        input.focus();
    }
}

// --- events ----------------------------------------------------------------

form.addEventListener("submit", (e) => {
    e.preventDefault();
    send(input.value);
});

input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        send(input.value);
    }
});

// Auto-grow textarea.
input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 160) + "px";
});

// Example chips.
document.addEventListener("click", (e) => {
    if (e.target.classList.contains("chip")) {
        send(e.target.textContent);
    }
});

newChatBtn.addEventListener("click", () => {
    threadId = null;
    chat.innerHTML = "";
    location.reload();
});

input.focus();
