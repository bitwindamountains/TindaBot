// Recovery contains no message bodies, recipients, or raw provider errors.
export function deliveryReview({api, openModal, escape, date, button, isDemo, refresh, toast, busy}) {
  let jobs = [], cursor = null, active = true, loading = false;
  const dialog = document.querySelector('dialog');
  const close = () => { active = false; dialog.removeEventListener('click', click); dialog.removeEventListener('submit', submit); };
  dialog.addEventListener('close', close, {once: true});
  const sample = [{id: 104, destination: 'messenger', status: 'uncertain', attempts: 2, created_at: Date.now()/1000, error_code: 'meta_transport_unknown', guidance: 'Check the provider result before deciding whether to retry.', revision: 'sample'}];
  function render() {
    openModal('Delivery review', `<p class="muted">${isDemo() ? 'Sample deliveries. Changes stay in this preview.' : 'Failed and uncertain outbound deliveries. Incoming event failures still require operator investigation.'}</p><div class="detail-actions">${button('Refresh review', 'recovery-refresh')}</div><div class="recovery-list">${jobs.length ? jobs.map(j => `<article class="detail-section"><div class="recovery-heading"><h3>${escape(({messenger: 'Messenger reply', sheets: 'Sheet export', email: 'Seller email'})[j.destination] || 'Delivery')} <span class="muted">#${j.id}</span></h3><span class="badge badge-pending">${escape(j.status)}</span></div><p class="muted">${j.attempts} attempts · ${escape(date(j.created_at, {month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit'}))}</p><p>${escape(j.guidance)}</p><p class="muted">Code: ${escape(j.error_code)}</p><div class="detail-actions"><button class="button" data-recovery-id="${j.id}" data-recovery-action="retry">Review retry</button><button class="button button-quiet" data-recovery-id="${j.id}" data-recovery-action="suppress">Suppress delivery</button></div></article>`).join('') : '<div class="detail-section"><h3>No deliveries awaiting review.</h3><p class="muted">Refresh to check for new failures. This does not confirm end-to-end provider delivery.</p></div>'}</div>${cursor ? button('Load earlier deliveries', 'recovery-more') : ''}<p id="recovery-error" class="error-message" role="alert"></p>`, true);
  }
  async function load(more = false) {
    if (loading) return;
    loading = true; busy(true);
    try {
      const result = isDemo() ? {jobs: sample, next_cursor: null} : await api(`/admin/workspace/jobs${more && cursor ? `?before=${cursor}` : ''}`);
      if (!active) return;
      jobs = more ? [...jobs, ...result.jobs] : [...result.jobs]; cursor = result.next_cursor; render();
    } finally { loading = false; busy(false); }
  }
  async function click(event) {
    const node = event.target.closest('button');
    if (!node || node.disabled) return;
    if (node.dataset.recoveryId) {
      const job = jobs.find(j => j.id === Number(node.dataset.recoveryId)), action = node.dataset.recoveryAction;
      const uncertain = job.status === 'uncertain' && action === 'retry';
      openModal(action === 'retry' ? 'Retry this delivery?' : 'Suppress this delivery?', `<p>${action === 'retry' ? 'Check the external provider first and fix the cause. This queues another attempt; it does not confirm delivery. Normal automation and privacy checks still apply.' : 'This stops further attempts for this job. It does not recall a message or undo an external update.'}</p>${uncertain ? '<p><strong>The original delivery may already have succeeded.</strong> Retrying could send a duplicate.</p>' : ''}<form id="recovery-form" data-job="${job.id}" data-action="${action}"><label class="refund-confirm"><input type="checkbox" required name="confirmed"><span>${uncertain ? 'I checked the provider result and accept the risk of duplicate delivery.' : action === 'retry' ? 'I checked the provider and want to queue another attempt.' : 'I want to stop further attempts for this job.'}</span></label><p id="recovery-error" class="error-message" role="alert"></p><div class="dialog-actions">${button('Back to deliveries', 'recovery-back', '', 'type="button"')}<button class="button button-primary" type="submit">${action === 'retry' ? 'Queue retry' : 'Confirm suppression'}</button></div></form>`, true);
      return;
    }
    if (node.dataset.action === 'recovery-back') return render();
    if (!['recovery-refresh', 'recovery-more'].includes(node.dataset.action)) return;
    node.disabled = true;
    try { await load(node.dataset.action === 'recovery-more'); }
    catch (error) { if (active) dialog.querySelector('#recovery-error').textContent = error.message; }
    finally { node.disabled = false; }
  }
  async function submit(event) {
    const form = event.target;
    if (form.id !== 'recovery-form') return;
    event.preventDefault();
    const job = jobs.find(j => j.id === Number(form.dataset.job));
    form.dataset.commandId ||= crypto.randomUUID();
    busy(true);
    try {
      if (isDemo()) sample.splice(sample.findIndex(j => j.id === job.id), 1);
      else await api(`/admin/jobs/${job.id}/resolve`, {method: 'POST', body: JSON.stringify({command_id: form.dataset.commandId, expected_revision: job.revision, action: form.dataset.action, accept_duplicate_risk: job.status === 'uncertain' && form.dataset.action === 'retry'})});
      toast(form.dataset.action === 'retry' ? 'Retry queued. Delivery is not yet confirmed.' : 'Delivery suppressed.');
      await refresh();
      busy(false); await load();
    } catch (error) { if (active) dialog.querySelector('#recovery-error').textContent = `${error.message} If the job changed, return and refresh the review.`; }
    finally { busy(false); }
  }
  dialog.addEventListener('click', click); dialog.addEventListener('submit', submit);
  openModal('Delivery review', `<p>Loading deliveries…</p>${button('Refresh review', 'recovery-refresh')}<p id="recovery-error" class="error-message" role="alert"></p>`, true);
  load().catch(error => { if (active) dialog.querySelector('#recovery-error').textContent = error.message; });
}
