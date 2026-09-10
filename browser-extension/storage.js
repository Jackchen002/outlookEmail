(function () {
  const CONFIG_KEY = 'outlookEmailOidcConfig';
  const LEGACY_CONFIG_KEY = 'outlookEmailPasswordConfig';
  const SESSION_PASSWORD_KEY = 'outlookEmailSessionPassword';
  const SIDE_PANEL_PATH_KEY = 'outlookEmailSidePanelPath';
  const SELECTED_MAIL_GROUP_KEY = 'outlookEmailSelectedMailGroupId';

  const ExtensionStorage = {
    async getConfig() {
      const data = await chrome.storage.local.get([CONFIG_KEY, LEGACY_CONFIG_KEY]);
      const config = data[CONFIG_KEY] || data[LEGACY_CONFIG_KEY] || {};
      return { serverUrl: config.serverUrl || '' };
    },

    async setConfig(config) {
      await chrome.storage.local.set({
        [CONFIG_KEY]: { serverUrl: config.serverUrl || '' },
      });
      await chrome.storage.local.remove(LEGACY_CONFIG_KEY);
      if (chrome.storage.session) {
        await chrome.storage.session.remove(SESSION_PASSWORD_KEY);
      }
    },

    async clearConfig() {
      await chrome.storage.local.remove([
        CONFIG_KEY,
        LEGACY_CONFIG_KEY,
        SELECTED_MAIL_GROUP_KEY,
      ]);
      if (chrome.storage.session) {
        await chrome.storage.session.remove(SESSION_PASSWORD_KEY);
      }
    },

    async setSidePanelPath(path) {
      await chrome.storage.local.set({ [SIDE_PANEL_PATH_KEY]: path || '/' });
    },

    async getSidePanelPath() {
      const data = await chrome.storage.local.get(SIDE_PANEL_PATH_KEY);
      return data[SIDE_PANEL_PATH_KEY] || '/';
    },

    async setSelectedMailGroupId(groupId) {
      await chrome.storage.local.set({ [SELECTED_MAIL_GROUP_KEY]: String(groupId || '') });
    },

    async getSelectedMailGroupId() {
      const data = await chrome.storage.local.get(SELECTED_MAIL_GROUP_KEY);
      return data[SELECTED_MAIL_GROUP_KEY] || '';
    },
  };

  window.ExtensionStorage = ExtensionStorage;
})();
