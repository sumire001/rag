/**
 * 应用层：状态管理 + 事件绑定，把 Api 和 UI 串起来。
 */
(function () {
  const { el } = UI;
  const CFG = window.APP_CONFIG;

  const state = {
    conversationId: localStorage.getItem(CFG.STORAGE_KEY) || null,
    conversations: [],
    sending: false,
    controller: null, // 流式请求的 AbortController
    clearKey: false, // 设置面板里是否要清除已有密钥
  };

  // ---------------- 初始化 ----------------
  async function init() {
    bindEvents();
    UI.updateCounter();
    await checkHealth();
    await loadConversations();
    if (state.conversationId) {
      await openConversation(state.conversationId, false);
    } else {
      UI.clearMessages();
    }
  }

  async function checkHealth() {
    try {
      const data = await Api.health();
      UI.setStatus('up', `已连接 · ${data.provider}`);
    } catch (e) {
      UI.setStatus('down', '后端未连接');
    }
  }

  async function loadConversations() {
    try {
      state.conversations = await Api.listConversations();
      UI.renderConversations(state.conversations, state.conversationId);
    } catch (e) {
      UI.toast(e.message);
    }
  }

  async function openConversation(id, closeSidebar = true) {
    try {
      const messages = await Api.listMessages(id);
      state.conversationId = id;
      localStorage.setItem(CFG.STORAGE_KEY, id);

      const conv = state.conversations.find((c) => c.id === id);
      UI.setTitle(conv ? conv.title : '对话');
      UI.renderMessages(messages);
      UI.renderConversations(state.conversations, id);
      if (closeSidebar) el.sidebar.classList.remove('is-open');
    } catch (e) {
      // 会话可能已被删掉，回到空白状态
      state.conversationId = null;
      localStorage.removeItem(CFG.STORAGE_KEY);
      UI.setTitle('新对话');
      UI.clearMessages();
      UI.toast(e.message);
    }
  }

  async function newConversation() {
    state.conversationId = null;
    localStorage.removeItem(CFG.STORAGE_KEY);
    UI.setTitle('新对话');
    UI.clearMessages();
    UI.renderConversations(state.conversations, null);
    el.input.focus();
  }

  async function removeConversation(id) {
    if (!confirm('确定删除这个会话？')) return;
    try {
      await Api.deleteConversation(id);
      if (state.conversationId === id) await newConversation();
      await loadConversations();
      UI.toast('已删除');
    } catch (e) {
      UI.toast(e.message);
    }
  }

  async function clearCurrent() {
    if (!state.conversationId) return UI.clearMessages();
    if (!confirm('清空当前会话的所有消息？')) return;
    try {
      await Api.clearMessages(state.conversationId);
      UI.clearMessages();
      await loadConversations();
    } catch (e) {
      UI.toast(e.message);
    }
  }

  // ---------------- 发送消息 ----------------
  async function send() {
    const text = el.input.value.trim();
    if (!text || state.sending) return;
    if (text.length > CFG.MAX_INPUT_LEN) {
      return UI.toast(`消息不能超过 ${CFG.MAX_INPUT_LEN} 字`);
    }

    el.input.value = '';
    UI.updateCounter();
    UI.autoGrow();
    UI.appendMessage('user', text);

    state.sending = true;
    UI.setSending(true);

    if (document.getElementById('toggle-stream').checked) {
      await sendStream(text);
    } else {
      await sendOnce(text);
    }

    state.sending = false;
    UI.setSending(false);
    await loadConversations();
    el.input.focus();
  }

  function sendStream(text) {
    return new Promise((resolve) => {
      const contentEl = UI.appendMessage('assistant', '');
      UI.updateContent(contentEl, '', true);

      let answer = '';
      let finished = false;
      const finish = () => {
        if (finished) return;
        finished = true;
        state.controller = null;
        resolve();
      };

      state.controller = Api.chatStream(state.conversationId, text, {
        onStart: (p) => {
          state.conversationId = p.conversation_id;
          localStorage.setItem(CFG.STORAGE_KEY, p.conversation_id);
          if (p.title) UI.setTitle(p.title);
        },
        onDelta: (piece) => {
          answer += piece;
          UI.updateContent(contentEl, answer, true);
        },
        onCommand: (reply) => {
          UI.updateContent(contentEl, reply, false);
          finish();
        },
        onDone: () => {
          UI.updateContent(contentEl, answer, false);
          finish();
        },
        onError: (msg) => {
          if (answer) {
            UI.updateContent(contentEl, answer + `\n\n[中断] ${msg}`, false);
          } else {
            UI.markError(contentEl, msg);
          }
          finish();
        },
      });

      // 用户点“停止”时，把已收到的内容定稿
      state.stopHook = () => {
        UI.updateContent(contentEl, answer + '\n\n[已停止生成]', false);
        finish();
      };
    });
  }

  async function sendOnce(text) {
    const contentEl = UI.appendMessage('assistant', '思考中…');
    try {
      const data = await Api.chat(state.conversationId, text);
      if (data.is_command) {
        UI.updateContent(contentEl, data.reply, false);
        return;
      }
      if (data.conversation_id) {
        state.conversationId = data.conversation_id;
        localStorage.setItem(CFG.STORAGE_KEY, data.conversation_id);
      }
      if (data.title) UI.setTitle(data.title);
      UI.updateContent(contentEl, data.message.content, false);
    } catch (e) {
      UI.markError(contentEl, e.message);
    }
  }

  function stop() {
    if (state.controller) {
      state.controller.abort();
      state.controller = null;
    }
    if (state.stopHook) {
      state.stopHook();
      state.stopHook = null;
    }
  }

  // ---------------- 设置面板 ----------------
  const settings = {
    panel: document.getElementById('settings-panel'),
    provider: document.getElementById('cfg-provider'),
    baseUrl: document.getElementById('cfg-base-url'),
    apiKey: document.getElementById('cfg-api-key'),
    keyHint: document.getElementById('cfg-key-hint'),
    model: document.getElementById('cfg-model'),
    temp: document.getElementById('cfg-temp'),
    tempVal: document.getElementById('cfg-temp-val'),
    strict: document.getElementById('cfg-strict'),
    msg: document.getElementById('settings-msg'),
  };

  function openSettings() {
    settings.msg.textContent = '';
    settings.msg.classList.remove('ok');
    settings.apiKey.value = '';
    state.clearKey = false;
    settings.panel.hidden = false;

    Api.getConfig()
      .then((cfg) => {
        settings.provider.value = cfg.provider || 'echo';
        settings.baseUrl.value = cfg.base_url || '';
        settings.model.value = cfg.model || '';
        settings.temp.value = cfg.temperature ?? 0.7;
        settings.tempVal.textContent = Number(cfg.temperature ?? 0.7).toFixed(1);
        settings.strict.checked = cfg.rag_mode === 'strict';
        settings.keyHint.textContent = cfg.api_key_set ? '已配置密钥（留空保持不变）' : '尚未配置密钥';
        settings.apiKey.placeholder = cfg.api_key_set ? cfg.api_key || '留空则不修改' : '留空则不修改';
      })
      .catch((e) => {
        settings.msg.textContent = e.message;
      });
  }

  function closeSettings() {
    settings.panel.hidden = true;
  }

  function clearKey() {
    state.clearKey = true;
    settings.apiKey.value = '';
    settings.keyHint.textContent = '保存后将清除已配置的密钥';
    UI.toast('保存时将清除密钥');
  }

  async function saveSettings() {
    settings.msg.textContent = '';
    settings.msg.classList.remove('ok');

    const payload = {
      provider: settings.provider.value,
      base_url: settings.baseUrl.value.trim(),
      model: settings.model.value.trim(),
      temperature: parseFloat(settings.temp.value),
      rag_mode: settings.strict.checked ? 'strict' : 'rag_first',
    };
    if (state.clearKey) {
      payload.api_key = '__CLEAR__';
    } else if (settings.apiKey.value.trim()) {
      payload.api_key = settings.apiKey.value.trim();
    }

    try {
      const cfg = await Api.saveConfig(payload);
      settings.msg.textContent = '已保存';
      settings.msg.classList.add('ok');
      state.clearKey = false;
      settings.keyHint.textContent = cfg.api_key_set ? '已配置密钥（留空保持不变）' : '尚未配置密钥';
      settings.apiKey.placeholder = cfg.api_key_set ? cfg.api_key || '留空则不修改' : '留空则不修改';
      settings.apiKey.value = '';
      UI.toast('设置已保存');
      await checkHealth(); // 同步左下角状态（provider 可能变了）
    } catch (e) {
      settings.msg.textContent = e.message;
    }
  }

  settings.temp.addEventListener('input', () => {
    settings.tempVal.textContent = Number(settings.temp.value).toFixed(1);
  });
  settings.apiKey.addEventListener('input', () => {
    if (settings.apiKey.value.trim()) {
      state.clearKey = false;
      settings.keyHint.textContent = '输入新密钥以覆盖';
    }
  });

  document.getElementById('btn-settings').addEventListener('click', openSettings);
  document.getElementById('btn-settings-close').addEventListener('click', closeSettings);
  document.getElementById('btn-settings-cancel').addEventListener('click', closeSettings);
  document.getElementById('btn-settings-save').addEventListener('click', saveSettings);
  document.getElementById('btn-clear-key').addEventListener('click', clearKey);

  // ---------------- 事件 ----------------
  function bindEvents() {
    document.getElementById('btn-new').addEventListener('click', newConversation);
    document.getElementById('btn-clear').addEventListener('click', clearCurrent);
    document.getElementById('btn-menu').addEventListener('click', UI.toggleSidebar);
    el.btnSend.addEventListener('click', send);
    el.btnStop.addEventListener('click', stop);

    el.input.addEventListener('input', () => {
      UI.updateCounter();
      UI.autoGrow();
    });

    el.input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
        e.preventDefault();
        send();
      }
    });

    // 事件委托：会话切换 / 删除
    el.convList.addEventListener('click', (e) => {
      const item = e.target.closest('.conv-item');
      if (!item || !item.dataset.id) return;
      if (e.target.dataset.action === 'delete') {
        e.stopPropagation();
        removeConversation(item.dataset.id);
        return;
      }
      if (item.dataset.id !== state.conversationId) openConversation(item.dataset.id);
    });
  }

  init();
})();
