export const sampleHandovers = [
  {psid: 'sample-1', name: 'Sofia Reyes', reason: 'customer', version: 1, last_customer_at: Date.now()/1000 - 1200},
  {psid: 'sample-2', name: 'Miguel Santos', reason: 'page_reply', version: 1, last_customer_at: Date.now()/1000 - 3600},
];

export function handoverQueue({api, openModal, escape, date, isDemo, refresh, toast, busy, invalidateSnapshots}) {
  const dialog = document.querySelector('dialog');
  let rows = [], cursor = null, active = true, loading = false;
  const reasons = {customer: 'Asked for the seller', stop: 'Asked to stop the bot', page_reply: 'Page reply detected', operator: 'Paused by the operator'};
  function close() { active = false; dialog.removeEventListener('click', click); dialog.removeEventListener('submit', submit); }
  dialog.addEventListener('close', close, {once: true});
  function render() {
    openModal('Customers needing help', `<p class="muted">${isDemo() ? 'Sample conversations. Changes stay in this preview.' : 'Tracked handovers with bot replies paused. Refresh for the latest requests.'}</p><div class="detail-actions"><button class="button" data-handover="refresh">Refresh handovers</button>${!isDemo() ? '<a class="button" href="https://business.facebook.com/latest/inbox/all/" target="_blank" rel="noopener noreferrer">Open Page inbox ↗</a>' : ''}</div><p class="muted">Find the conversation in your Page inbox using its name and last-contact time. The inbox link does not select an individual thread.</p><div class="recovery-list">${rows.map(c => `<article class="detail-section"><div class="recovery-heading"><h3>${escape(c.name)}</h3><span class="badge badge-pending">Bot paused</span></div><p>${escape(reasons[c.reason] || 'Needs attention')}</p><p class="muted">Last customer message: ${c.last_customer_at ? escape(date(c.last_customer_at, {month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit'})) : 'Not recorded'}</p><small class="muted">Reference · ${escape(c.psid.slice(-6))}</small><div class="detail-actions"><button class="button" data-resume="${escape(c.psid)}">Review resume</button></div></article>`).join('') || '<div class="detail-section"><h3>No tracked handovers waiting.</h3><p class="muted">New seller requests and detected Page replies appear here.</p></div>'}</div>${cursor ? '<button class="button" data-handover="more">Load more handovers</button>' : ''}<p id="handover-error" class="error-message" role="alert"></p>`, true);
  }
  async function load(more = false) {
    if (loading) return;
    loading = true; busy(true);
    try {
      const data = isDemo() ? {conversations: sampleHandovers, next_cursor: null} : await api(`/admin/workspace/handovers${more && cursor ? `?after=${encodeURIComponent(cursor)}` : ''}`);
      if (!active) return;
      rows = more ? [...rows, ...data.conversations] : [...data.conversations]; cursor = data.next_cursor; render();
    } finally { loading = false; busy(false); }
  }
  async function click(event) {
    const node = event.target.closest('button'); if (!node || node.disabled) return;
    if (node.dataset.resume) {
      const c = rows.find(c => c.psid === node.dataset.resume);
      openModal('Resume the bot for this customer?', `<p><strong>${escape(c.name)}</strong> · ${escape(reasons[c.reason])}</p><p>Resume only after handling the request in Messenger. This allows replies to future customer messages; it sends nothing now. The shop-wide automation setting still applies.</p><form id="handover-resume" data-psid="${escape(c.psid)}"><label class="refund-confirm"><input type="checkbox" required><span>${c.reason === 'stop' ? 'The customer wants bot replies again, and I have handled their request.' : 'I have handled the request and want to resume bot replies.'}</span></label><p id="handover-error" class="error-message" role="alert"></p><div class="dialog-actions"><button class="button" type="button" data-handover="back">Keep paused</button><button class="button button-primary" type="submit">Resume bot</button></div></form>`, true); return;
    }
    if (node.dataset.handover === 'back') return render();
    if (!['refresh', 'more'].includes(node.dataset.handover)) return;
    try { await load(node.dataset.handover === 'more'); }
    catch (error) { if (active) dialog.querySelector('#handover-error').textContent = error.message; }
  }
  async function submit(event) {
    const form = event.target; if (form.id !== 'handover-resume') return;
    event.preventDefault(); busy(true);
    const c = rows.find(c => c.psid === form.dataset.psid);
    let saved = false;
    try {
      if (isDemo()) sampleHandovers.splice(sampleHandovers.findIndex(row => row.psid === c.psid), 1);
      else await api(`/admin/conversations/${encodeURIComponent(c.psid)}/pause`, {method: 'POST', body: JSON.stringify({enabled: false, expected_version: c.version})});
      saved = true;
      openModal('Conversation resumed', '<p>Resume saved. No message was sent. Refresh the queue to check current requests.</p><button class="button" data-handover="refresh">Refresh handovers</button><p id="handover-error" class="error-message" role="alert"></p>', true);
      busy(true);
      invalidateSnapshots(); await refresh(); toast('Conversation resumed. No message was sent.');
      busy(false); await load();
    } catch (error) { if (active) dialog.querySelector('#handover-error').textContent = saved ? `Resume saved, but the queue could not refresh. ${error.message} Use Refresh handovers to check current requests.` : `${error.message} Return to the list and refresh before trying again.`; }
    finally { busy(false); }
  }
  dialog.addEventListener('click', click); dialog.addEventListener('submit', submit);
  openModal('Customers needing help', '<p>Loading handovers…</p><button class="button" data-handover="refresh">Refresh handovers</button><p id="handover-error" class="error-message" role="alert"></p>', true);
  load().catch(error => { if (active) dialog.querySelector('#handover-error').textContent = error.message; });
}
