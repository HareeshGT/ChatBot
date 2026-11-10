const $ = (id) => document.getElementById(id);
const form = $("chatForm");
const input = $("messageInput");
const messagesEl = $("messages");
const welcome = $("welcome");
const modelSelect = $("modelSelect");
const sendBtn = $("sendBtn");
let history = [];
let busy = false;

function setStatus(online, text) {
  $("statusText").textContent = text;
  $("statusText").previousElementSibling.classList.toggle("online", online);
}

function scrollBottom() {
  $("conversation").scrollTop = $("conversation").scrollHeight;
}

function addMessage(role, content = "", {streaming = false, error = false} = {}) {
  welcome.style.display = "none";
  messagesEl.classList.add("active");
  const row = document.createElement("div");
  row.className = `message ${role}`;
  const avatar = document.createElement("div");
  avatar.className = "avatar";
  avatar.textContent = role === "user" ? "Y" : "✳";
  const body = document.createElement("div");
  body.className = "message-body";
  const label = document.createElement("div");
  label.className = "message-role";
  label.textContent = role === "user" ? "You" : "Assistant";
  const text = document.createElement("div");
  text.className = "message-content" + (error ? " error" : "");
  text.textContent = content;
  body.append(label, text);
  if (streaming) {
    const cursor = document.createElement("span");
    cursor.className = "cursor";
    text.append(cursor);
    row.dataset.streaming = "true";
  }
  row.append(avatar, body);
  messagesEl.append(row);
  scrollBottom();
  return text;
}

function clearChat() {
  history = [];
  messagesEl.replaceChildren();
  messagesEl.classList.remove("active");
  welcome.style.display = "";
  input.focus();
}

async function loadModels() {
  try {
    const response = await fetch("/api/models");
    if (!response.ok) throw new Error("Local model unavailable");
    const data = await response.json();
    modelSelect.replaceChildren();
    for (const item of data.models || []) {
      const option = document.createElement("option");
      option.value = item.name;
      option.textContent = item.name;
      modelSelect.append(option);
    }
    if (data.default && [...modelSelect.options].some(o => o.value === data.default)) modelSelect.value = data.default;
    if (!modelSelect.options.length) {
      const option = document.createElement("option");
      option.textContent = "No models found";
      modelSelect.append(option);
    }
    setStatus(true, "Python model is running");
  } catch {
    modelSelect.innerHTML = '<option>Unavailable</option>';
    setStatus(false, "Local model is unavailable");
  }
}

async function sendMessage(message) {
  const trimmed = message.trim();
  if (!trimmed || busy) return;
  busy = true;
  sendBtn.disabled = true;
  input.value = "";
  input.style.height = "auto";
  addMessage("user", trimmed);
  const assistantNode = addMessage("assistant", "", {streaming: true});
  let answer = "";
  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({message: trimmed, model: modelSelect.value, history})
    });
    if (!response.ok || !response.body) throw new Error(await response.text() || "Request failed");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const {value, done} = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, {stream: true});
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (!line.trim()) continue;
        const item = JSON.parse(line);
        if (item.error) throw new Error(item.error);
        if (item.message?.content) {
          answer += item.message.content;
          assistantNode.textContent = answer;
          scrollBottom();
        }
      }
    }
    if (buffer.trim()) {
      const item = JSON.parse(buffer);
      if (item.error) throw new Error(item.error);
      if (item.message?.content) answer += item.message.content;
    }
    assistantNode.textContent = answer || "(No response)";
    history.push({role: "user", content: trimmed}, {role: "assistant", content: answer});
  } catch (error) {
    assistantNode.textContent = error.message || "Something went wrong.";
    assistantNode.classList.add("error");
  } finally {
    const row = assistantNode.closest(".message");
    row?.querySelector(".cursor")?.remove();
    busy = false;
    sendBtn.disabled = false;
    input.focus();
    scrollBottom();
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  sendMessage(input.value);
});
input.addEventListener("input", () => {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 180) + "px";
});
input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});
$("newChat").addEventListener("click", clearChat);
$("clearBtn").addEventListener("click", clearChat);
document.querySelectorAll(".suggestion").forEach(button => {
  button.addEventListener("click", () => {
    input.value = button.textContent;
    form.requestSubmit();
  });
});
loadModels();
