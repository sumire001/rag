/**
 * API 层：所有 HTTP 请求都收敛在这里，UI 代码不直接碰 fetch。
 */
window.Api = (function () {
  const BASE = window.APP_CONFIG.API_BASE.replace(/\/$/, '');

  async function request(path, options = {}) {
    let resp;
    try {
      resp = await fetch(BASE + path, {
        headers: { 'Content-Type': 'application/json' },
        ...options,
      });
    } catch (e) {
      throw new Error('无法连接后端，请确认 Flask 已启动');
    }

    let body;
    try {
      body = await resp.json();
    } catch (e) {
      throw new Error(`响应解析失败 (HTTP ${resp.status})`);
    }

    if (body.code !== 0) {
      throw new Error(body.msg || `请求失败 (HTTP ${resp.status})`);
    }
    return body.data;
  }

  return {
    health: () => request('/health'),

    /** 读取当前模型配置（api_key 已脱敏） */
    getConfig: () => request('/config'),

    /** 保存模型配置，返回脱敏后的配置 */
    saveConfig: (cfg) =>
      request('/config', { method: 'PUT', body: JSON.stringify(cfg) }),

    listConversations: () => request('/conversations'),

    createConversation: (title) =>
      request('/conversations', { method: 'POST', body: JSON.stringify({ title }) }),

    renameConversation: (id, title) =>
      request(`/conversations/${id}`, { method: 'PATCH', body: JSON.stringify({ title }) }),

    deleteConversation: (id) => request(`/conversations/${id}`, { method: 'DELETE' }),

    listMessages: (id) => request(`/conversations/${id}/messages`),

    clearMessages: (id) => request(`/conversations/${id}/messages`, { method: 'DELETE' }),

    /** 非流式：一次性拿到完整回复 */
    chat: (conversationId, message) =>
      request('/chat', {
        method: 'POST',
        body: JSON.stringify({ conversation_id: conversationId, message }),
      }),

    /**
     * 流式：用 fetch 读取 SSE，比 EventSource 灵活（能发 POST、能中断）。
     * handlers: { onStart, onDelta, onDone, onError }
     * 返回 AbortController，调用方可以随时 abort() 停止生成。
     */
    chatStream(conversationId, message, handlers = {}) {
      const controller = new AbortController();

      (async () => {
        let resp;
        try {
          resp = await fetch(BASE + '/chat/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ conversation_id: conversationId, message }),
            signal: controller.signal,
          });
        } catch (e) {
          if (e.name !== 'AbortError') {
            handlers.onError && handlers.onError('无法连接后端，请确认 Flask 已启动');
          }
          return;
        }

        if (!resp.ok || !resp.body) {
          handlers.onError && handlers.onError(`请求失败 (HTTP ${resp.status})`);
          return;
        }

        const reader = resp.body.getReader();
        const decoder = new TextDecoder('utf-8');
        let buffer = '';

        try {
          while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });

            // SSE 以空行分隔一条完整消息
            let idx;
            while ((idx = buffer.indexOf('\n\n')) !== -1) {
              const frame = buffer.slice(0, idx).trim();
              buffer = buffer.slice(idx + 2);
              if (!frame.startsWith('data:')) continue;

              let payload;
              try {
                payload = JSON.parse(frame.slice(5).trim());
              } catch (e) {
                continue;
              }
              dispatch(payload, handlers);
            }
          }
        } catch (e) {
          if (e.name !== 'AbortError') {
            handlers.onError && handlers.onError('数据流中断：' + e.message);
          }
        }
      })();

      return controller;
    },
  };

  function dispatch(payload, handlers) {
    switch (payload.type) {
      case 'start':
        handlers.onStart && handlers.onStart(payload);
        break;
      case 'delta':
        handlers.onDelta && handlers.onDelta(payload.content || '');
        break;
      case 'done':
        handlers.onDone && handlers.onDone(payload);
        break;
      case 'error':
        handlers.onError && handlers.onError(payload.message || '未知错误');
        break;
      case 'command':
        handlers.onCommand && handlers.onCommand(payload.reply);
        break;
      default:
        break;
    }
  }
})();
