/**
 * UI 层：只负责把数据渲染成 DOM，不发请求、不存状态。
 */
window.UI = (function () {
  const el = {
    convList: document.getElementById('conv-list'),
    messageList: document.getElementById('message-list'),
    chatTitle: document.getElementById('chat-title'),
    input: document.getElementById('input'),
    counter: document.getElementById('counter'),
    btnSend: document.getElementById('btn-send'),
    btnStop: document.getElementById('btn-stop'),
    statusDot: document.querySelector('.status__dot'),
    statusText: document.getElementById('status-text'),
    toast: document.getElementById('toast'),
    sidebar: document.getElementById('sidebar'),
  };

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  /** 极简 markdown：只处理代码块和行内代码，其余交给 white-space: pre-wrap */
  function format(text) {
    const blocks = [];
    let out = String(text).replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
      blocks.push(`<pre><code>${escapeHtml(code.replace(/\n$/, ''))}</code></pre>`);
      return `\u0000${blocks.length - 1}\u0000`;
    });

    out = escapeHtml(out).replace(/`([^`\n]+)`/g, '<code class="inline">$1</code>');
    return out.replace(/\u0000(\d+)\u0000/g, (_, i) => blocks[Number(i)]);
  }

  function scrollToBottom() {
    el.messageList.scrollTop = el.messageList.scrollHeight;
  }

  function renderEmpty() {
    el.messageList.innerHTML = `
      <div class="empty">
        <div class="empty__title">开始一段新的对话</div>
        <div>在下方输入内容，按 Enter 发送</div>
      </div>`;
  }

  function createMessageNode(role, content, opts = {}) {
    const node = document.createElement('div');
    node.className = `msg msg--${role}` + (opts.error ? ' msg--error' : '');
    const label = role === 'user' ? '我' : 'AI';
    node.innerHTML = `
      <div class="msg__avatar">${label}</div>
      <div class="msg__body">
        <div class="msg__role">${role === 'user' ? '我' : '助手'}</div>
        <div class="msg__content"></div>
      </div>`;
    node.querySelector('.msg__content').innerHTML = format(content);
    return node;
  }

  return {
    el,
    escapeHtml,
    format,
    scrollToBottom,

    /** 会话列表 */
    renderConversations(list, activeId) {
      if (!list.length) {
        el.convList.innerHTML = '<div class="conv-item conv-item__count">暂无会话</div>';
        return;
      }
      el.convList.innerHTML = list
        .map(
          (c) => `
        <div class="conv-item ${c.id === activeId ? 'is-active' : ''}" data-id="${c.id}">
          <span class="conv-item__title" title="${escapeHtml(c.title)}">${escapeHtml(c.title)}</span>
          <span class="conv-item__count">${c.message_count}</span>
          <span class="conv-item__del" data-action="delete" title="删除">×</span>
        </div>`
        )
        .join('');
    },

    setTitle(title) {
      el.chatTitle.textContent = title || '新对话';
    },

    /** 整屏消息 */
    renderMessages(list) {
      if (!list || !list.length) {
        renderEmpty();
        return;
      }
      el.messageList.innerHTML = '';
      list.forEach((m) => el.messageList.appendChild(createMessageNode(m.role, m.content)));
      scrollToBottom();
    },

    clearMessages: renderEmpty,

    /** 追加一条消息，返回内容节点，便于流式更新 */
    appendMessage(role, content, opts) {
      const empty = el.messageList.querySelector('.empty');
      if (empty) empty.remove();
      const node = createMessageNode(role, content, opts);
      el.messageList.appendChild(node);
      scrollToBottom();
      return node.querySelector('.msg__content');
    },

    /** 流式更新某条消息的内容，typing=true 时带光标 */
    updateContent(contentEl, text, typing) {
      contentEl.innerHTML = format(text) + (typing ? '<span class="cursor"></span>' : '');
      scrollToBottom();
    },

    markError(contentEl, msg) {
      contentEl.closest('.msg').classList.add('msg--error');
      contentEl.textContent = msg;
      scrollToBottom();
    },

    setSending(sending) {
      el.btnSend.disabled = sending;
      el.btnSend.textContent = sending ? '生成中' : '发送';
      el.btnStop.hidden = !sending;
    },

    setStatus(state, text) {
      el.statusDot.dataset.state = state;
      el.statusText.textContent = text;
    },

    updateCounter() {
      el.counter.textContent = `${el.input.value.length} / ${window.APP_CONFIG.MAX_INPUT_LEN}`;
    },

    autoGrow() {
      el.input.style.height = 'auto';
      el.input.style.height = Math.min(el.input.scrollHeight, 180) + 'px';
    },

    toggleSidebar() {
      el.sidebar.classList.toggle('is-open');
    },

    toast(msg) {
      el.toast.textContent = msg;
      el.toast.classList.add('is-show');
      clearTimeout(el.toast._timer);
      el.toast._timer = setTimeout(() => el.toast.classList.remove('is-show'), 2200);
    },
  };
})();
