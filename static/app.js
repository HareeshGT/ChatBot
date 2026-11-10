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

// Build formatted output with DOM nodes (never inject model text as HTML).
function appendInline(parent, source) {
  const pattern = /(`[^`]+\`|\*\*[^*]+\*\*|\*[^*]+\*|https?:\/\/[^\s<]+)/g;
  let cursor = 0;
  for (const match of source.matchAll(pattern)) {
    if (match.index > cursor) parent.append(document.createTextNode(source.slice(cursor, match.index)));
    const token = match[0];
    let node;
    if (token.startsWith("`")) {
      node = document.createElement("code");
      node.textContent = token.slice(1, -1);
    } else if (token.startsWith("**")) {
      node = document.createElement("strong");
      node.textContent = token.slice(2, -2);
    } else if (token.startsWith("*")) {
      node = document.createElement("em");
      node.textContent = token.slice(1, -1);
    } else {
      node = document.createElement("a");
      node.href = token;
      node.target = "_blank";
      node.rel = "noopener noreferrer";
      node.textContent = token;
    }
    parent.append(node);
    cursor = match.index + token.length;
  }
  if (cursor < source.length) parent.append(document.createTextNode(source.slice(cursor)));
}

function renderMarkdown(container, markdown) {
  container.replaceChildren();
  // Normalize inline fences and numbered steps commonly emitted by small local models.
  markdown = markdown
    .replace(/\r\n?/g, "\n")
    .replace(/\s*```([a-zA-Z0-9_-]*)/g, "\n```$1\n")
    .replace(/([^\n])\s+(?=\d+[.)]\s+(?:\*\*|[A-Z]))/g, "$1\n")
    .replace(/([^\n])\s+(?=[-*+]\s+)/g, "$1\n");
  const lines = markdown.split("\n");
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }

    if (/^\s*```/.test(line)) {
      const language = line.trim().slice(3).trim();
      i++;
      const codeLines = [];
      while (i < lines.length && !/^\s*```\s*$/.test(lines[i])) codeLines.push(lines[i++]);
      if (i < lines.length) i++;
      const wrapper = document.createElement("div");
      wrapper.className = "code-block";
      const toolbar = document.createElement("div");
      toolbar.className = "code-toolbar";
      const lang = document.createElement("span");
      lang.textContent = language || "CODE";
      const copy = document.createElement("button");
      copy.type = "button";
      copy.className = "copy-code";
      copy.textContent = "Copy";
      const codeText = codeLines.join("\n");
      copy.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(codeText);
          copy.textContent = "Copied";
          setTimeout(() => copy.textContent = "Copy", 1200);
        } catch { copy.textContent = "Select to copy"; }
      });
      toolbar.append(lang, copy);
      const pre = document.createElement("pre");
      const code = document.createElement("code");
      code.textContent = codeText;
      if (language) code.className = "language-" + language.toLowerCase().replace(/[^a-z0-9_-]/g, "");
      pre.append(code);
      wrapper.append(toolbar, pre);
      container.append(wrapper);
      continue;
    }

    const heading = line.match(/^\s{0,3}(#{1,6})\s+(.+)$/);
    if (heading) {
      const h = document.createElement("h" + heading[1].length);
      appendInline(h, heading[2].replace(/\s+#+\s*$/, ""));
      container.append(h); i++; continue;
    }
    if (/^\s*(---+|___+|\*\*\*+)\s*$/.test(line)) {
      container.append(document.createElement("hr")); i++; continue;
    }
    if (/^\s*>/.test(line)) {
      const quote = document.createElement("blockquote");
      while (i < lines.length && /^\s*>/.test(lines[i])) {
        const p = document.createElement("p");
        appendInline(p, lines[i++].replace(/^\s*>\s?/, ""));
        quote.append(p);
      }
      container.append(quote); continue;
    }

    const unordered = line.match(/^\s*[-*+]\s+(.+)$/);
    const ordered = line.match(/^\s*\d+[.)]\s+(.+)$/);
    if (unordered || ordered) {
      const list = document.createElement(unordered ? "ul" : "ol");
      while (i < lines.length) {
        const item = lines[i].match(unordered ? /^\s*[-*+]\s+(.+)$/ : /^\s*\d+[.)]\s+(.+)$/);
        if (!item) break;
        const li = document.createElement("li");
        appendInline(li, item[1]);
        list.append(li); i++;
      }
      container.append(list); continue;
    }

    const paragraph = document.createElement("p");
    appendInline(paragraph, line);
    i++;
    while (i < lines.length && lines[i].trim() &&
      !/^\s*(```|#{1,6}\s|>|[-*+]\s+|\d+[.)]\s+|---+\s*$)/.test(lines[i])) {
      paragraph.append(document.createElement("br"));
      appendInline(paragraph, lines[i++]);
    }
    container.append(paragraph);
  }
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
  if (role === "assistant" && !streaming && !error) renderMarkdown(text, content);
  else text.textContent = content;
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
    renderMarkdown(assistantNode, answer || "(No response)");
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
