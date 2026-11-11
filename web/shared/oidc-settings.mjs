import { InMemoryWebStorage, WebStorageStateStore } from 'oidc-client-ts';

export function createSigninArgs() {
  return { nonce: crypto.randomUUID() };
}

export function createOidcSettings(config, transactionStorage) {
  return {
    authority: config.authority,
    client_id: config.clientId,
    redirect_uri: config.redirectUri,
    post_logout_redirect_uri: config.redirectUri,
    response_type: 'code',
    scope: `openid documents:read documents:write${config.clientId === 'securesync-portal' ? ' members:manage' : ''}`,
    disablePKCE: false,
    userStore: new WebStorageStateStore({ store: new InMemoryWebStorage() }),
    stateStore: new WebStorageStateStore({ store: transactionStorage, prefix: `${config.clientId}.oidc.` }),
    automaticSilentRenew: false,
    monitorSession: false,
    loadUserInfo: false,
    staleStateAgeInSeconds: 300
  };
}
