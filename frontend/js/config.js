/**
 * 前端唯一需要改的地方：后端 API 地址。
 * 部署到别的机器时改这里即可，其它 JS 一律通过 APP_CONFIG 读取。
 */
window.APP_CONFIG = {
  API_BASE: 'http://127.0.0.1:5000/api',
  MAX_INPUT_LEN: 4000,
  // 本地记住当前会话 id，刷新后自动回到上次的对话
  STORAGE_KEY: 'chat.conversation.id',
};
