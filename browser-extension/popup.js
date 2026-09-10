(function () {
  const Storage = window.ExtensionStorage;
  const Api = window.OutlookExtensionApi;

  function getEl(id) {
    return document.getElementById(id);
  }

  function setBusy(isBusy) {
    ['btnTest', 'btnOpen', 'btnLogout', 'btnClear'].forEach((id) => {
      const el = getEl(id);
      if (el) el.disabled = isBusy;
    });
    document.querySelectorAll('.quick-btn').forEach((button) => {
      button.disabled = isBusy;
    });
  }

  function showMessage(message, type) {
    const el = getEl('message');
    el.textContent = message || '';
    el.classList.toggle('error', type === 'error');
  }

  function setConnected(connected) {
    const pill = getEl('statusPill');
    pill.textContent = connected ? '已验证' : '未连接';
    pill.classList.toggle('ok', connected);
  }

  function readFormConfig() {
    return { serverUrl: Api.trimUrl(getEl('serverUrl').value) };
  }

  async function saveFormConfig(config) {
    await Storage.setConfig(config);
  }

  async function openSidePanel(nextPath) {
    const config = readFormConfig();
    if (!config.serverUrl) {
      showMessage('请先填写服务地址', 'error');
      return;
    }
    await saveFormConfig(config);
    await Storage.setSidePanelPath(nextPath || '/');
    setBusy(true);
    showMessage('正在打开侧边栏...');
    try {
      if (!chrome.sidePanel || !chrome.sidePanel.open) {
        throw new Error('当前浏览器不支持 Side Panel，请升级 Chrome / Edge');
      }
      const currentWindow = await chrome.windows.getCurrent();
      await chrome.sidePanel.open({ windowId: currentWindow.id });
      showMessage('已打开侧边栏控制台');
    } catch (error) {
      showMessage(Api.friendlyError(error), 'error');
    } finally {
      setBusy(false);
    }
  }

  async function startPocketIdLogin() {
    const config = readFormConfig();
    await saveFormConfig(config);
    setBusy(true);
    showMessage('正在打开 Pocket ID 登录页...');
    try {
      await Api.openConsole(config, '/');
      setConnected(false);
      showMessage('请在新标签页点击登录并完成 Pocket ID 验证');
    } catch (error) {
      showMessage(Api.friendlyError(error), 'error');
    } finally {
      setBusy(false);
    }
  }

  async function openLogout() {
    const config = readFormConfig();
    if (!config.serverUrl) {
      showMessage('请先填写服务地址', 'error');
      return;
    }
    await chrome.tabs.create({ url: `${config.serverUrl}/logout` });
    setConnected(false);
  }

  async function clearConfig() {
    await Storage.clearConfig();
    getEl('serverUrl').value = '';
    setConnected(false);
    showMessage('本地配置已清除');
  }

  document.addEventListener('DOMContentLoaded', async () => {
    const config = await Storage.getConfig();
    getEl('serverUrl').value = config.serverUrl || '';

    getEl('btnTest').addEventListener('click', startPocketIdLogin);
    getEl('btnOpen').addEventListener('click', () => openSidePanel('/'));
    getEl('btnLogout').addEventListener('click', openLogout);
    getEl('btnClear').addEventListener('click', clearConfig);

    document.querySelectorAll('.quick-btn').forEach((button) => {
      button.addEventListener('click', () => openSidePanel(button.dataset.next || '/'));
    });
  });
})();
