/** Fired after login/logout so the nav bar updates without a full reload. */
export function notifyAuthChange() {
  window.dispatchEvent(new Event("auth-change"));
}
