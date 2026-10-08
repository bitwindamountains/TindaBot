import {icon} from './icons.js';
import {deliveryReview} from './recovery.js';
import {handoverQueue, sampleHandovers} from './handover.js';
import {demoSnapshot, demoOrder, demoStatus, demoStock, demoAutomation, demoNote, demoRefund} from './demo.js';
import {heroBackdrop, observeScenes, toggleAmbient} from './motion.js';

const $ = (s, root = document) => root.querySelector(s);
const escape = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const moneyWhole = new Intl.NumberFormat('en-PH', {style: 'currency', currency: 'PHP', maximumFractionDigits: 0});
const moneyFraction = new Intl.NumberFormat('en-PH', {style: 'currency', currency: 'PHP', maximumFractionDigits: 2});
const compactNumber = new Intl.NumberFormat('en', {notation: 'compact', maximumFractionDigits: 1});
const dateFormats = new Map();
const money = (value) => (value % 100 ? moneyFraction : moneyWhole).format(value / 100);
const date = (timestamp, options = {month: 'short', day: 'numeric'}) => {
  const key = JSON.stringify(options);
  if (!dateFormats.has(key)) dateFormats.set(key, new Intl.DateTimeFormat('en-PH', {...options, timeZone: 'Asia/Manila'}));
  return dateFormats.get(key).format(timestamp * 1000);
};
const labels = {overview: 'Overview', orders: 'Orders', inventory: 'Inventory', automation: 'Automation'};
const state = {view: 'overview', days: 7, filter: 'all', query: '', token: '', data: null, loading: false, error: '', request: 0, chartDay: null, sort: 'newest', payment: 'all', stockSort: 'name', scope: 'all', paging: false};
const viewContexts = new Map(), historyContexts = new Map();
let historyKey = crypto.randomUUID(), searchTimer;
const contextKeys = ['view', 'filter', 'query', 'payment', 'sort', 'stockSort', 'scope', 'days'];
function saveContext() {
  const context = Object.fromEntries(contextKeys.map(key => [key, state[key]]));
  context.scroll = window.scrollY;
  if (!isDemo() && !state.loading && state.loadedPath === workspacePath()) {
    context.data = state.data;
    context.loadedPath = state.loadedPath;
  }
  viewContexts.set(state.view, context);
  historyContexts.set(historyKey, context);
}
function workspacePath(cursor = null) {
  const params = new URLSearchParams({days: state.days});
  if (state.view === 'orders') {
    Object.entries({scope: state.scope, status: state.filter, payment: state.payment, sort: state.sort, q: state.query}).forEach(([key, value]) => params.set(key, value));
  }
  if (cursor) params.set('cursor', cursor);
  return `/admin/workspace?${params}`;
}
function updateOrderView(focus = null) {
  saveContext();
  if (!isDemo() && state.view === 'orders') return refresh().then(() => focus && $(focus)?.focus({preventScroll: true}));
  renderPage();
  if (focus) $(focus)?.focus({preventScroll: true});
}
const dialog = $('#dialog');
let toastTimer, modalOpener, modalVersion = 0, detailOrder = null;
const disabledControls = new WeakMap();
const isDemo = () => !state.token;
const badge = (status) => `<span class="badge badge-${escape(status)}"><span class="dot"></span>${escape(({pending: 'Pending', confirmed: 'Confirmed', shipped: 'Shipped', delivered: 'Delivered', cancelled: 'Cancelled', paid: 'Paid', unpaid: 'Unpaid', refund_required: 'Refund required', refunded: 'Refunded'})[status] || status)}</span>`;
const button = (text, action, glyph = '', extra = '') => `<button class="button" data-action="${action}" ${extra}>${glyph ? icon(glyph) : ''}${text}</button>`;
const initials = (name) => name.split(/\s+/).filter(Boolean).slice(0, 2).map(n => [...n][0]).join('');

function toast(message) {
  clearTimeout(toastTimer);
  const node = $('#toast'); node.textContent = message; node.classList.add('visible');
  toastTimer = setTimeout(() => node.classList.remove('visible'), 4200);
}
function shell() {
  const d = state.data;
  $('#app').innerHTML = `<div class="shell">
    <aside class="sidebar" aria-label="Workspace navigation">
      <div class="brand"><span class="brand-mark">${icon('logo')}</span>TindaBot</div>
      <div class="shop-card"><span class="shop-avatar">${escape(initials(d.shop_name))}</span><div class="shop-copy"><strong title="${escape(d.shop_name)}">${escape(d.shop_name)}</strong><small>${isDemo() ? 'Demo workspace' : 'Connected workspace'}</small></div>${icon('down')}</div>
      <div class="nav-caption">Workspace</div>
      <nav class="nav" aria-label="Main">${Object.entries(labels).map(([key, label]) => `<button class="nav-button" aria-label="${label}" data-view="${key}" ${key === state.view ? 'aria-current="page"' : ''}>${icon(({overview: 'overview', orders: 'bag', inventory: 'box', automation: 'bot'})[key])}<span>${label}</span>${key === 'orders' ? `<span class="nav-count numeric">${d.summary.pending}</span>` : ''}</button>`).join('')}</nav>
      <div class="sidebar-bottom"><div class="side-note">${icon('leaf')} <strong>A little less busy.</strong><p>Your shop, with room to grow.</p></div>
      <button class="nav-button" data-action="guide">${icon('shield')}Workspace guide</button>
      <div class="account"><span class="avatar">${isDemo() ? 'SS' : 'OP'}</span><div class="shop-copy"><strong>${isDemo() ? 'Sari Studio' : 'Shop operator'}</strong><small>${isDemo() ? 'Exploring TindaBot' : 'Authenticated session'}</small></div></div></div>
    </aside>
    <div class="workspace"><header class="topbar"><div class="breadcrumb"><span>Workspace</span>${icon('chevron')}<strong id="breadcrumb">${labels[state.view]}</strong></div>
      <div class="top-actions"><label class="top-search">${icon('search')}<span class="sr-only">Search orders or products</span><input id="search" type="search" maxlength="200" placeholder="Search…" autocomplete="off" value="${escape(state.query)}"><kbd aria-hidden="true">/</kbd></label>
      <button class="icon-button shortcut-button" data-action="commands" aria-label="Quick actions" aria-keyshortcuts="Control+k Meta+k" title="Quick actions · Ctrl K">⌘ K</button>
      <button class="icon-button" data-action="theme" aria-label="Switch to ${document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'} mode">${icon(document.documentElement.dataset.theme === 'dark' ? 'sun' : 'moon')}</button>
      ${button(isDemo() ? 'Connect shop' : 'Disconnect', isDemo() ? 'connect' : 'disconnect', isDemo() ? 'link' : '')}</div></header>
      <div class="preview-bar">${icon(isDemo() ? 'eye' : 'shield')}<span>${isDemo() ? '<strong>Preview mode.</strong> A sample shop, ready to explore.' : `<strong>Connected.</strong> ${d.delivery_mode === 'dry_run' ? 'Dry-run delivery · changes affect your database.' : 'Live delivery · changes affect your shop.'}`}</span>${isDemo() ? '<button class="text-button" data-action="connect">Use your own data '+icon('arrow')+'</button>' : ''}</div>
      <main id="main" class="page" tabindex="-1"></main>
    </div></div>`;
  renderPage(true);
}
function heading() {
  const titles = {overview: 'A good day to grow.', orders: 'Every order, in order.', inventory: 'Good things in stock.', automation: 'Your shop’s quiet helper.'};
  const subtitles = {overview: 'Your shop at a glance. Your next step, within reach.', orders: 'Track the journey. Keep every promise.', inventory: 'Keep your shelves ready for the next order.', automation: 'A clear view of what is running behind the scenes.'};
  const overview = state.view === 'overview', pending = state.data.summary.pending;
  return `<div class="page-heading ${overview ? 'page-heading-overview' : ''}">${overview ? heroBackdrop() : ''}<div class="welcome-copy"><div class="welcome-eyebrow">${overview ? `${escape(state.data.shop_name)} <span class="eyebrow-divider">/</span> ${date(state.data.generated_at, {weekday: 'short', month: 'short', day: 'numeric'})}` : `Your workspace / ${labels[state.view]}`}</div><h1>${overview ? 'A good day to <em>grow.</em>' : titles[state.view]}</h1><p>${subtitles[state.view]}</p></div>${overview ? `<div class="hero-brief"><div class="brief-title"><span class="dot"></span>${pending ? 'Your next move' : 'Room to breathe'}</div><div class="brief-copy"><strong class="numeric">${String(pending).padStart(2, '0')}</strong><span>${pending ? 'orders waiting<br>for your okay' : 'orders waiting.<br>You’re all caught up.'}</span></div><div class="hero-actions"><button class="button button-primary" ${pending ? 'data-action="pending"' : 'data-view="orders"'}>${pending ? `Review ${pending} orders` : 'View orders'} ${icon('arrow')}</button><button class="icon-button" data-action="commands" aria-label="Find an action" title="Find an action">${icon('search')}</button></div></div>` : ''}<div class="actions">${(state.view === 'overview' || (state.view === 'orders' && state.scope === 'period')) ? `<label class="select-wrap">${icon('calendar')}<span class="sr-only">Reporting period</span><select id="period"><option value="7" ${state.days === 7 ? 'selected' : ''}>Last 7 days</option><option value="30" ${state.days === 30 ? 'selected' : ''}>Last 30 days</option></select></label>` : ''}<button class="icon-button" data-action="refresh" aria-label="Refresh workspace" ${state.loading ? 'disabled' : ''}>${icon('refresh')}</button></div></div>`;
}

function renderPage(animate = false) {
  document.title = `${labels[state.view]} · TindaBot`;
  $('#breadcrumb').textContent = labels[state.view];
  $('#search').placeholder = state.view === 'inventory' ? 'Search products…' : 'Search orders…';
  document.querySelectorAll('[data-view]').forEach(node => { if (node.dataset.view === state.view) node.setAttribute('aria-current', 'page'); else node.removeAttribute('aria-current'); });
  const main = $('#main');
  main.setAttribute('aria-busy', String(state.loading));
  let content;
  if (state.loading) content = `<div role="status"><span class="sr-only">Loading workspace…</span><div class="metric-strip">${Array.from({length: 4}, () => '<div class="metric"><div class="skeleton"></div><div class="skeleton skeleton-value"></div></div>').join('')}</div><div class="main-grid"><div class="skeleton skeleton-block"></div><div class="skeleton skeleton-block"></div></div><div class="panel">${'<div class="skeleton-row"><div class="skeleton"></div></div>'.repeat(4)}</div></div>`;
  else if (state.error) content = `<div class="panel empty" role="alert">${icon('alert')}<h2>We couldn’t refresh your workspace</h2><p>${escape(state.error)}</p>${button('Try again', 'refresh', 'refresh')}${button('Reconnect', 'connect', 'link')}</div>`;
  else content = ({overview: overview, orders: () => orderPipeline() + orderTable(false), inventory, automation})[state.view]();
  const previousScene = $('.hero-scene', main);
  main.innerHTML = heading() + `<div ${animate ? 'class="view-enter"' : ''}>${content}</div><footer class="page-footer"><span>${isDemo() ? 'Sample data · changes stay in this preview' : `Updated ${date(state.data.generated_at, {hour: 'numeric', minute: '2-digit'})} · refresh for latest data`}</span><button class="motion-control" data-action="motion" aria-pressed="true">${icon('leaf')}<span>Motion on</span></button></footer>`;
  const nextScene = $('.hero-scene', main);
  if (previousScene && nextScene) nextScene.replaceWith(previousScene);
  observeScenes();
}
function metrics() {
  const s = state.data.summary;
  return `<section class="metric-strip" aria-label="Shop summary">
    ${[
      ['Order value', money(s.order_value), 'Excludes cancelled orders', 'chart'],
      ['Total orders', s.orders.toLocaleString(), `In the last ${state.days} days`, 'bag'],
      ['Awaiting confirmation', s.pending.toLocaleString(), 'Across all dates', 'clock'],
      ['Active products', s.products.toLocaleString(), 'Across your entire catalog', 'box'],
    ].map(([label, value, note, glyph]) => `<div class="metric"><div class="metric-label">${label}${icon(glyph)}</div><strong class="metric-value numeric">${value}</strong><p class="metric-note">${note}</p></div>`).join('')}</section>`;
}
function chart() {
  const series = state.data.series;
  const selected = Math.min(state.chartDay ?? series.length - 1, series.length - 1);
  const width = matchMedia('(max-width: 760px)').matches ? 340 : 620;
  const left = 40, right = width - 24;
  const max = Math.max(10000, ...series.map(v => v.value));
  const ceiling = Math.ceil(max / 100000) * 100000;
  const points = series.map((v, i) => [left + i * ((right - left) / Math.max(1, series.length - 1)), 166 - v.value / ceiling * 142]);
  const line = points.map(([x, y], i) => `${i ? 'L' : 'M'}${x.toFixed(2)},${y.toFixed(2)}`).join(' ');
  const axis = [0, 1, 2, 3].map(i => { const y = 166 - i * 142 / 3; return `<line class="chart-grid" x1="${left}" x2="${right}" y1="${y}" y2="${y}"/><text x="${left - 12}" y="${y + 4}" text-anchor="end">${compactNumber.format(ceiling / 100 * i / 3)}</text>`; }).join('');
  const dates = series.map((v, i) => (series.length <= 7 || i % 6 === 0 || i === series.length - 1) ? `<text x="${points[i][0]}" y="198" text-anchor="middle">${escape(date(v.timestamp))}</text>` : '').join('');
  return `<section class="panel chart-panel"><div class="panel-head chart-top"><div><h2>Order value over time</h2><p>A little progress, every day.</p></div><div class="chart-readout"><strong id="chart-value" class="numeric">${money(series[selected].value)}</strong><span id="chart-date">${date(series[selected].timestamp)}</span></div></div>
    <div class="chart"><svg viewBox="0 0 ${width} 210" role="img" aria-labelledby="chart-title chart-description"><title id="chart-title">Daily order value in Philippine pesos</title><desc id="chart-description">${series.map(v => `${date(v.timestamp)}: ${money(v.value)}`).join('; ')}</desc>${axis}<path class="chart-area" d="${line} L${right},166 L${left},166 Z"/><path class="chart-line" d="${line}"/><line class="chart-crosshair" x1="${points[selected][0]}" x2="${points[selected][0]}" y1="20" y2="166"/>${points.map(([x, y], i) => `<circle class="chart-point ${i === selected ? 'is-selected' : ''}" data-day="${i}" cx="${x}" cy="${y}" r="3"/>`).join('')}${dates}</svg></div>
    <div class="chart-explorer"><label for="chart-day">Explore by day</label><input id="chart-day" type="range" min="0" max="${series.length - 1}" value="${selected}" aria-valuetext="${escape(date(series[selected].timestamp) + ': ' + money(series[selected].value))}"></div>
    <div class="chart-footer">${icon('calendar')}<span>${escape(date(series[0].timestamp))} – ${escape(date(series.at(-1).timestamp))} · Manila time</span><button class="text-button" data-action="breakdown">View data</button></div></section>`;
}
function selectChartDay(index) {
  const series = state.data.series;
  const day = Math.max(0, Math.min(Number(index), series.length - 1));
  state.chartDay = day;
  const slider = $('#chart-day');
  if (!slider) return;
  slider.value = day;
  slider.setAttribute('aria-valuetext', `${date(series[day].timestamp)}: ${money(series[day].value)}`);
  $('#chart-value').textContent = money(series[day].value);
  $('#chart-date').textContent = date(series[day].timestamp);
  document.querySelectorAll('.chart-point').forEach(point => point.classList.toggle('is-selected', Number(point.dataset.day) === day));
  const point = $(`.chart-point[data-day="${day}"]`);
  const line = $('.chart-crosshair');
  line.setAttribute('x1', point.getAttribute('cx')); line.setAttribute('x2', point.getAttribute('cx'));
}
function commands() {
  openModal('Where would you like to go?', `<label class="command-search">${icon('search')}<span class="sr-only">Find a quick action</span><input id="command-search" class="field" type="search" placeholder="Find your next step…" autocomplete="off"></label><div class="command-list">${[
    ['overview', 'overview', 'Shop overview', 'See the bigger picture'],
    ['pending', 'bag', 'Confirm orders', 'See orders awaiting your attention'],
    ['inventory', 'box', 'Browse inventory', 'Products, prices, and stock'],
    ['low', 'box', 'Restock your shelves', 'Go straight to low-stock products'],
    ['automation', 'bot', 'Check automation', 'Replies, heartbeat, and delivery queue'],
  ].map(([key, glyph, title, description]) => `<button class="command-item" data-command="${key}">${icon(glyph)}<span><strong>${title}</strong><small>${description}</small></span>${icon('arrow')}</button>`).join('')}</div><p id="command-empty" class="muted" hidden>No actions match. Try “orders” or “stock”.</p><p class="command-help">↑ ↓ to move · Enter to open · Esc to close</p>`);
  dialog.classList.add('command-dialog');
  $('#command-search').focus();
}
function overview() {
  const d = state.data, low = d.products.filter(p => p.active && p.stock <= 5).length;
  return metrics() + `<div class="main-grid">${chart()}<section class="panel focus-panel"><div class="panel-head"><div><span class="eyebrow">Make room for what matters</span><h2>Your short list.</h2><p>Keep orders and customer requests moving.</p></div>${icon('leaf')}</div><div class="attention">
    <button class="attention-row" data-action="pending"><span class="attention-icon numeric">01</span><span><span class="attention-title">${d.summary.pending} orders to confirm</span><small>Give your customers a happy update</small></span>${icon('chevron')}</button>
    <button class="attention-row" data-action="low-stock"><span class="attention-icon numeric">02</span><span><span class="attention-title">${low} products running low</span><small>A good time to check your shelves</small></span>${icon('chevron')}</button>
    <button class="attention-row" data-view="automation"><span class="attention-icon numeric">03</span><span><span class="attention-title">${d.failures ? `${d.failures} jobs need a look` : 'Your automation, at a glance'}</span><small>${d.automation ? 'Replies are enabled' : 'Replies are paused'}</small></span>${icon('chevron')}</button>
    ${handoverButton()}</div><div class="bot-foot">${icon('shield')}<span>${isDemo() ? 'Sample activity · explore with confidence' : d.worker_age_seconds !== null && d.worker_age_seconds < 120 ? 'Worker heartbeat received recently' : 'Worker heartbeat needs attention'}</span></div></section></div>${orderTable(true)}`;
}
function handoverButton() {
  const count = isDemo() ? sampleHandovers.length : state.data.handover_count || 0;
  return `<button class="attention-row" data-action="handovers"><span class="attention-icon numeric">${count}</span><span><span class="attention-title">Customers needing help</span><small>${count} tracked handovers · review paused conversations</small></span>${icon('chevron')}</button>`;
}
function orderPipeline() {
  const stages = [['pending', 'To confirm', 'clock'], ['confirmed', 'To prepare', 'box'], ['shipped', 'On the way', 'arrow'], ['delivered', 'Delivered', 'check']];
  return `<section class="pipeline" aria-label="Order pipeline"><div class="pipeline-caption"><span class="eyebrow">The order journey</span><span>${state.scope === 'period' ? `Last ${state.days} days` : state.scope === 'open' ? 'Needs attention · all dates' : 'All dates'}</span></div><div class="pipeline-stages">${stages.map(([status, label, glyph], index) => `<button class="pipeline-stage" data-stage="${status}" aria-label="${label}: ${(state.data.order_counts?.[status] ?? state.data.orders.filter(o => o.status === status).length)} orders" aria-pressed="${state.filter === status}"><span class="stage-top"><span class="stage-number">0${index + 1}</span>${icon(glyph)}</span><strong class="numeric">${(state.data.order_counts?.[status] ?? state.data.orders.filter(o => o.status === status).length)}</strong><span>${label}</span>${icon('chevron')}</button>`).join('')}</div></section>`;
}
function filteredOrders(sort = state.sort) {
  const q = state.query.trim().toLowerCase();
  return state.data.orders.filter(o => (state.filter === 'all' || o.status === state.filter) && (state.payment === 'all' || o.payment_status === state.payment) && (!q || `${o.code} ${o.name}`.toLowerCase().includes(q))).sort((a, b) => sort === 'highest' ? b.total_minor - a.total_minor : sort === 'lowest' ? a.total_minor - b.total_minor : sort === 'oldest' ? a.created_at - b.created_at : b.created_at - a.created_at);
}
function empty(title, copy, action = 'clear', actionText = 'Clear filters') {
  return `<div class="empty">${icon('bag')}<h2>${title}</h2><p>${copy}</p>${button(actionText, action, 'arrow')}</div>`;
}
function orderTable(compact) {
  const all = filteredOrders(compact ? 'newest' : state.sort), rows = compact ? all.slice(0, 5) : all;
  const filters = ['all', 'pending', 'confirmed', 'shipped', 'delivered', 'cancelled'];
  return `<section aria-labelledby="orders-title"><div class="section-heading"><h2 id="orders-title">${compact ? 'Recent orders' : 'Your orders'}<span class="count numeric">${all.length}</span></h2>${compact ? '<button class="button button-quiet" data-view="orders">View all orders '+icon('arrow')+'</button>' : button('Export CSV', 'export', 'download', !rows.length ? 'disabled' : '')}</div>
    ${state.query && rows.length ? `<div class="search-context"><span>Results for <strong>“${escape(state.query)}”</strong></span><button class="text-button" data-action="clear-search">Clear search ${icon('close')}</button></div>` : ''}<div class="panel orders-panel"><div class="table-toolbar"><div class="filters" role="group" aria-label="Filter orders by status">${filters.map(f => `<button class="filter" data-filter="${f}" aria-pressed="${state.filter === f}">${f === 'all' ? 'All orders' : f[0].toUpperCase() + f.slice(1)}</button>`).join('')}</div>${compact ? '' : `<div class="order-tools"><label class="order-sort"><span>Show</span><select id="order-scope" aria-label="Order date scope">${[['all', 'All dates'], ['open', 'Needs attention'], ['period', 'Reporting period']].map(([value, label]) => `<option value="${value}" ${state.scope === value ? 'selected' : ''}>${label}</option>`).join('')}</select></label><label class="order-sort"><span>Payment</span><select id="payment-filter" aria-label="Filter orders by payment">${[['all', 'All payments'], ['unpaid', 'Unpaid'], ['paid', 'Paid'], ['refund_required', 'Refund required'], ['refunded', 'Refunded']].map(([value, label]) => `<option value="${value}" ${state.payment === value ? 'selected' : ''}>${label}</option>`).join('')}</select></label><label class="order-sort"><span>Sort</span><select id="order-sort" aria-label="Sort orders">${[['newest', 'Newest first'], ['oldest', 'Oldest first'], ['highest', 'Highest amount'], ['lowest', 'Lowest amount']].map(([value, label]) => `<option value="${value}" ${state.sort === value ? 'selected' : ''}>${label}</option>`).join('')}</select></label></div>`}</div>
    ${rows.length ? `<div class="table-scroll" role="region" aria-label="Orders table" tabindex="0"><table><thead><tr><th scope="col">Order</th><th scope="col" class="customer-column">Customer</th><th scope="col">Status</th><th scope="col" class="date-column">Date</th><th scope="col" class="align-right">Amount</th></tr></thead><tbody>${rows.map(o => `<tr><td><button class="order-link numeric" data-order="${escape(o.id)}" aria-label="Open order ${escape(o.code)}">${escape(o.code)}</button><span class="mobile-customer">${escape(o.name)}</span></td><td class="customer-column"><div class="customer"><span class="avatar" aria-hidden="true">${escape(initials(o.name))}</span><span class="customer-name" title="${escape(o.name)}">${escape(o.name)}</span></div></td><td>${badge(o.status)}</td><td class="muted numeric date-column">${escape(date(o.created_at))}</td><td class="align-right numeric">${money(o.total_minor)}<span class="payment-label payment-${escape(o.payment_status)}">${escape(o.payment_status.replaceAll('_', ' '))}</span></td></tr>`).join('')}</tbody></table></div>` : empty(state.query || state.filter !== 'all' || state.payment !== 'all' ? 'No orders match just yet' : 'Your next chapter starts here', state.query || state.filter !== 'all' || state.payment !== 'all' ? 'Try another search or clear your filters.' : 'Orders placed through Messenger will appear here.', state.query || state.filter !== 'all' || state.payment !== 'all' ? 'clear' : 'guide', state.query || state.filter !== 'all' || state.payment !== 'all' ? 'Clear filters' : 'View workspace guide')}
    <div class="table-footer"><span>${compact ? `Showing ${rows.length} recent orders` : `Showing ${rows.length} of ${state.data.order_total ?? all.length} matching orders`}</span><span>${isDemo() ? 'Sample Messenger orders' : 'Messenger orders'}</span>${!compact && state.data.next_cursor ? button(state.paging ? 'Loading more...' : 'Load more orders', 'more-orders', 'arrow', state.paging ? 'disabled' : '') : ''}</div></div></section>`;
}
function inventory() {
  const q = state.query.trim().toLowerCase();
  const matches = p => state.filter === 'all' || (state.filter === 'low' && p.active && p.stock <= 5) || (state.filter === 'out' && p.active && p.stock === 0) || (state.filter === 'inactive' && !p.active);
  const products = state.data.products.filter(p => (!q || `${p.name} ${p.sku}`.toLowerCase().includes(q)) && matches(p)).sort((a, b) => state.stockSort === 'stock' ? a.stock - b.stock || a.name.localeCompare(b.name) : state.stockSort === 'price' ? b.price_minor - a.price_minor || a.name.localeCompare(b.name) : a.name.localeCompare(b.name));
  const low = state.data.products.filter(p => p.active && p.stock <= 5).length;
  return `<div class="section-heading"><h2>Product catalog <span class="count">${products.length}</span></h2></div><div class="inventory-toolbar"><div class="filters" role="group" aria-label="Filter inventory">${[['all', 'All products'], ['low', 'Low stock'], ['out', 'Out of stock'], ['inactive', 'Inactive']].map(([key, label]) => `<button class="filter" data-filter="${key}" aria-pressed="${state.filter === key}">${label}</button>`).join('')}</div><label class="order-sort"><span>Sort</span><select id="stock-sort" aria-label="Sort products">${[['name', 'Name A to Z'], ['stock', 'Lowest stock'], ['price', 'Highest price']].map(([value, label]) => `<option value="${value}" ${state.stockSort === value ? 'selected' : ''}>${label}</option>`).join('')}</select></label></div><p class="catalog-caption">${low} active products at 5 units or fewer. ${state.data.products_truncated ? 'Showing the first 500 products.' : 'Counts describe the loaded catalog.'}</p>
    ${products.length ? `<div class="inventory-grid">${products.map(p => `<article class="panel product"><div class="product-top"><span class="product-art" aria-hidden="true"><span>${escape(initials(p.name))}</span></span><span class="badge ${p.active && p.stock <= 5 ? 'badge-pending' : ''}">${!p.active ? 'Inactive' : p.stock === 0 ? 'Out of stock' : p.stock <= 5 ? 'Running low' : 'In stock'}</span></div><h2>${escape(p.name)}</h2><p class="product-sku">${escape(p.sku)}</p><div class="product-bottom"><div><strong class="numeric">${money(p.price_minor)}</strong><p class="muted ${p.stock <= 5 ? 'stock-warning' : ''}"><span class="numeric">${p.stock}</span> available</p></div>${button('Adjust stock', 'stock', '', `data-sku="${escape(p.sku)}"`)}</div></article>`).join('')}</div>` : `<div class="panel">${empty('A little room on the shelf', state.data.products.length ? 'No products match this view.' : 'Import your catalog through the configured seller sheet or catalog API.', state.data.products.length ? 'clear' : 'guide', state.data.products.length ? 'Clear filters' : 'View workspace guide')}</div>`}`;
}
function automationBrief(d, healthy) {
  const attention = d.failures > 0 || !healthy;
  const title = isDemo() ? 'Explore your assistant.' : attention ? 'A few things need a look.' : !d.automation ? 'Your assistant is paused.' : d.delivery_mode !== 'live' ? 'A rehearsal, before going live.' : 'Your worker is reporting.';
  return `<section class="automation-brief ${attention ? 'needs-attention' : ''}" aria-label="Automation snapshot"><div><span class="eyebrow">${isDemo() ? 'Sample diagnostics' : 'Latest check'}</span><h2>${title}</h2><p>${isDemo() ? 'These are sample signals. Connect your shop for its current status.' : `Snapshot at ${date(d.generated_at, {hour: 'numeric', minute: '2-digit'})}. Refresh to check again.`}</p></div><div class="health-totals"><div><strong class="numeric">${d.queue}</strong><span>queued</span></div><div><strong class="numeric">${d.failures}</strong><span>to review</span></div></div></section>`;
}
function automationChecklist(d, healthy) {
  const steps = [];
  if (!healthy) steps.push(['Check the worker', 'Ask your operator to start or inspect the background worker. Refresh after it has restarted. Queued work needs a running worker.']);
  if (d.job_health?.delivery_uncertain) steps.push(['Confirm what was delivered', `${d.job_health.delivery_uncertain} deliveries have an uncertain result. Check provider records before your operator retries or suppresses them; retrying can duplicate a delivery.`]);
  if (d.job_health?.inbox_failed) steps.push(['Review incoming messages', `${d.job_health.inbox_failed} incoming events failed. Your operator needs to fix the cause before retrying them.`]);
  if (d.job_health?.delivery_failed) steps.push(['Review failed deliveries', `${d.job_health.delivery_failed} delivery jobs failed. Ask your operator to check provider access and delivery errors.`]);
  if (d.failures && !d.job_health) steps.push(['Review the queue', 'Ask your operator to inspect failed or uncertain jobs using the operations runbook before retrying.']);
  if (d.automation_locked) steps.push(['Server setting is off', 'The server has disabled automated replies. Your operator must enable that setting before replies can resume here.']);
  else if (!d.automation) steps.push(['Resume when you are ready', 'Turn on Automated replies to handle new messages. Previously suppressed replies are not replayed.']);
  if (d.delivery_mode !== 'live') steps.push(['Messages stay in dry run', 'Replies are recorded without being sent. Complete a supervised test with your operator before enabling live delivery.']);
  if (!steps.length) steps.push(['Keep checking delivery', 'A recent heartbeat means the worker is reporting. It does not confirm that every provider connection is working. Check a permitted test order end to end.']);
  return `<aside class="panel automation-checklist" aria-label="Recommended checks"><div class="panel-head"><div><span class="eyebrow">Next steps</span><h2>Know what to check.</h2></div>${icon('shield')}</div><ol>${steps.map(([title, copy]) => `<li><h3>${title}</h3><p>${copy}</p></li>`).join('')}</ol></aside>`;
}
function automation() {
  const d = state.data, healthy = d.worker_age_seconds !== null && d.worker_age_seconds < 120;
  return handoverButton() + automationBrief(d, healthy) + `<div class="automation-layout"><section class="panel automation-panel" aria-label="Automation settings"><div class="panel-head"><div><h2>Messenger assistant</h2><p>A helping hand, with you in control.</p></div>${icon('bot')}</div>
    <div class="setting-row"><div><h3>Automated replies</h3><p>${d.automation_locked ? 'Disabled by server configuration. Ask your operator to enable automation.' : 'Let TindaBot guide customers from browsing to checkout.'}</p></div><button class="switch" role="switch" aria-label="Automated replies" aria-checked="${d.automation}" data-action="automation" ${d.automation_locked ? 'disabled' : ''}></button></div>
    <div class="setting-row"><div><h3>Delivery mode</h3><p>${d.delivery_mode === 'live' ? 'Messages can be sent to customers.' : 'Messages are recorded without being sent to customers.'}</p></div><span class="badge">${d.delivery_mode === 'live' ? 'Live' : 'Dry run'}</span></div>
    <div class="setting-row"><div><h3>Worker heartbeat</h3><p>${isDemo() ? 'Illustrative activity for this preview.' : d.worker_age_seconds === null ? 'No heartbeat received. Start the worker and refresh.' : `Last received ${Math.floor(d.worker_age_seconds)} seconds before this refresh.`}</p></div><span class="badge ${healthy ? 'badge-delivered' : 'badge-pending'}">${isDemo() ? 'Sample' : healthy ? 'Recent' : 'Check worker'}</span></div>
    <div class="setting-row"><div><h3>Delivery queue</h3><p>${d.failures ? `${d.failures} failed or uncertain jobs require operator review. Check the operations runbook before retrying.` : 'No failed or uncertain jobs in this snapshot.'}</p></div><span class="badge numeric">${d.queue} waiting</span></div>
    <div class="setting-row setting-row-action"><div><h3>Resolve delivery issues</h3><p>Inspect failed or uncertain deliveries and choose the next step.</p></div>${button('Review deliveries', 'deliveries')}</div>
    <div class="setting-row"><p>Per-conversation pauses and human handover are still respected. Settings refresh on request.</p></div></section>${automationChecklist(d, healthy)}</div>`;
}
async function api(path, options = {}, token = state.token) {
  let response;
  try { response = await fetch(path, {...options, headers: {'Authorization': `Bearer ${token}`, ...(options.body ? {'Content-Type': 'application/json'} : {})}, cache: 'no-store', signal: AbortSignal.timeout(15000)}); }
  catch { throw new Error('The connection timed out or was interrupted. Check your connection and try again.'); }
  if (!response.ok) {
    if (response.status === 401) throw new Error('That operator token wasn’t accepted. Check it and reconnect.');
    if (response.status === 409) {
      const code = (await response.json().catch(() => ({}))).detail;
      if (code === 'conversation_pending') throw new Error('Incoming conversation activity still needs processing. Check the worker and refresh before resuming.');
      const messages = {refund_unavailable: 'This order no longer needs a refund. Reopen it to check its latest state.', refund_exceeds_remaining: 'The amount must be greater than zero and no more than the remaining refund.', refund_reference_required: 'Add the reference for the refund you completed.', refund_date_invalid: 'Choose a completion time between the order date and now.', notes_erased: 'Notes cannot be added after personal fields have been removed.', invalid_note: 'Write a note of up to 2,000 characters.'};
      throw new Error(messages[code] || 'This record changed or the action is no longer available. Reopen it to review the latest details before trying again.');
    }
    if (response.status === 422) throw new Error('Please check the values and try again.');
    throw new Error('The service couldn’t complete the request. Please try again shortly.');
  }
  return response.json();
}
async function refresh(notify = false) {
  const request = ++state.request;
  const path = workspacePath();
  const focused = document.activeElement;
  const restoreFocus = focused?.id === 'period' ? '#period' : focused?.dataset.action === 'refresh' ? '[data-action="refresh"]' : null;
  state.loading = true; state.paging = false; state.error = ''; renderPage();
  try {
    const data = isDemo() ? demoSnapshot(state.days, state.view === 'orders' ? state.scope : 'period') : await api(path);
    if (request !== state.request) return;
    state.data = data;
    state.loadedPath = path;
    if (notify) toast(isDemo() ? 'Preview refreshed.' : 'Workspace is up to date.');
  } catch (error) { if (request === state.request) state.error = error.message; }
  finally { if (request === state.request) { state.loading = false; renderPage(); const count = $('.nav-count'); if (count) count.textContent = state.data.summary.pending; if (restoreFocus && document.activeElement === document.body) $(restoreFocus)?.focus({preventScroll: true}); } }
}
async function navigate(view, filter, restored = null) {
  clearTimeout(searchTimer);
  saveContext();
  const context = restored || viewContexts.get(view) || {filter: 'all', payment: 'all', query: '', scope: 'all', scroll: 0};
  Object.assign(state, context, {view, paging: false});
  if (filter !== undefined) Object.assign(state, {filter, payment: 'all', query: '', scope: 'all'});
  $('#search').value = state.query;
  if (restored) historyKey = history.state?.workspaceKey || crypto.randomUUID();
  if (!restored) {
    historyKey = crypto.randomUUID();
    history.pushState({workspaceKey: historyKey}, '', `#${view}`);
  }
  if (isDemo()) { state.data = demoSnapshot(state.days, view === 'orders' ? state.scope : 'period'); renderPage(true); }
  else if (context.data && filter === undefined && context.loadedPath === workspacePath()) { state.request++; state.loading = false; state.error = ''; renderPage(true); }
  else await refresh();
  $('#main').focus({preventScroll: true});
  window.scrollTo({top: restored ? context.scroll || 0 : 0, behavior: 'instant'});
  saveContext();
}
async function loadMoreOrders() {
  if (!state.data.next_cursor || state.paging || state.loading) return;
  const request = state.request;
  state.paging = true; renderPage();
  try {
    const data = await api(workspacePath(state.data.next_cursor));
    if (request !== state.request) return;
    const ids = new Set(state.data.orders.map(order => order.id));
    state.data.orders.push(...data.orders.filter(order => !ids.has(order.id)));
    state.data.next_cursor = data.next_cursor;
    state.data.orders_truncated = data.orders_truncated;
  } catch (error) { toast(error.message); }
  finally { if (request === state.request) { state.paging = false; renderPage(); ($('[data-action="more-orders"]') || $('#main')).focus({preventScroll: true}); saveContext(); } }
}
function invalidateSnapshots() {
  for (const context of [...viewContexts.values(), ...historyContexts.values()]) delete context.data;
  state.loadedPath = null;
}
function openModal(title, content, drawer = false) {
  modalVersion++;
  if (!dialog.open) modalOpener = document.activeElement;
  dialog.className = drawer ? 'drawer' : '';
  dialog.innerHTML = `<div class="dialog-head"><h2 id="dialog-title" tabindex="-1">${title}</h2><button class="icon-button" data-action="close" aria-label="Close dialog">${icon('close')}</button></div><div class="dialog-body">${content}</div>`;
  if (!dialog.open) dialog.showModal();
  $('#dialog-title', dialog).focus();
}
function closeModal() { if (dialog.getAttribute('aria-busy') !== 'true') dialog.close(); }
dialog.addEventListener('close', () => { modalVersion++; dialog.innerHTML = ''; if (modalOpener?.isConnected) modalOpener.focus(); else $('#main').focus({preventScroll: true}); });
dialog.addEventListener('cancel', event => { if (dialog.getAttribute('aria-busy') === 'true') event.preventDefault(); });
function busy(value) {
  dialog.setAttribute('aria-busy', String(value));
  dialog.querySelectorAll('button, input, textarea, select').forEach(node => {
    if (value) { if (!disabledControls.has(node)) disabledControls.set(node, node.disabled); node.disabled = true; }
    else if (disabledControls.has(node)) { node.disabled = disabledControls.get(node); disabledControls.delete(node); }
  });
}

function activityItem(event) {
  const after = event.data?.after || {}, before = event.data?.before || {};
  const title = event.kind === 'note' ? 'Private note' : event.kind === 'refund' ? `External refund recorded · ${money(event.amount_minor)}` : event.kind === 'created' ? 'Order placed' : event.kind === 'status' ? before.payment_status !== after.payment_status && after.payment_status === 'paid' ? 'Payment verified' : `Order ${after.status || 'updated'}` : 'Personal fields removed';
  const actor = ({operator: 'Operator', customer: 'Customer', seller_sheet: 'Seller sheet', system: 'System'})[event.actor] || 'Operator';
  return `<li class="activity-entry activity-${escape(event.kind)}"><span class="activity-dot" aria-hidden="true"></span><div><strong>${escape(title)}</strong><p class="activity-meta">${escape(actor)} · ${date(event.created_at, {month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit'})}</p>${event.kind === 'note' ? `<p class="activity-body">${event.body ? escape(event.body) : 'Note text removed.'}</p>` : event.kind === 'refund' ? `<p class="activity-body">${event.body ? `Reference: ${escape(event.body)}` : 'Reference not retained.'}</p><p class="activity-meta">Completed ${date(event.occurred_at, {month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit'})} · Manila time</p>` : ''}</div></li>`;
}
function orderJournal(order) {
  const refunded = order.refunded_minor || 0, remaining = Math.max(0, order.total_minor - refunded);
  const refund = ['refund_required', 'refunded'].includes(order.payment_status) ? `<section class="refund-card" aria-label="Refund tracking"><span class="eyebrow">Refund tracking</span><div class="refund-amounts"><div><span>Recorded</span><strong>${money(refunded)}</strong></div><div><span>Remaining</span><strong>${money(remaining)}</strong></div></div><p>${remaining ? 'Record a refund after you have sent it outside TindaBot.' : 'The full external refund has been recorded.'}</p>${remaining ? button('Record external refund', 'record-refund', 'check') : ''}</section>` : '';
  return `${refund}<section class="detail-section journal-section" aria-labelledby="activity-title"><div class="journal-heading"><h3 id="activity-title">Activity & notes</h3><span class="badge">Private</span></div><p class="field-help">Times in Manila. Notes stay with your shop and are never sent to customers.</p>${order.anonymized ? '<p class="muted">Personal fields were removed. New notes are disabled.</p>' : `<form id="note-form"><label for="order-note">Private note</label><textarea class="field" id="order-note" rows="3" maxlength="2000" required placeholder="Packing instructions, a customer follow-up, a detail to remember..." aria-describedby="note-help note-error"></textarea><p class="field-help" id="note-help">Up to 2,000 characters. Saved notes become part of the order history.</p><p id="note-error" class="error-message" aria-live="assertive"></p><div class="dialog-actions"><button class="button" type="submit">Add note ${icon('arrow')}</button></div></form>`}<ol class="activity-list" aria-label="Order activity">${(order.activity || []).map(activityItem).join('')}</ol><p class="field-help">Updates before activity tracking was enabled may not be recorded.</p>${order.next_activity_cursor ? button('Load earlier activity', 'earlier-activity') : ''}</section>`;
}
function refundModal() {
  const order = detailOrder, remaining = order.total_minor - (order.refunded_minor || 0);
  openModal('Record an external refund', `<div class="refund-context"><span class="eyebrow">${escape(order.code)}</span><strong>${money(remaining)} remaining</strong></div><p>This records money you already returned. TindaBot does not send a payment.</p><form id="refund-form"><label for="refund-amount">Amount refunded (PHP)</label><input class="field numeric" id="refund-amount" type="number" min="0.01" max="${(remaining / 100).toFixed(2)}" step="0.01" value="${(remaining / 100).toFixed(2)}" required>${order.anonymized ? '<p class="field-help">Personal fields were removed. A refund reference will not be retained.</p>' : '<label for="refund-reference">Refund reference</label><input class="field" id="refund-reference" maxlength="160" required placeholder="Transfer or receipt reference">'}<label for="refund-completed">Completed at (optional)</label><input class="field" id="refund-completed" type="datetime-local" step="1" aria-describedby="refund-time-help"><p class="field-help" id="refund-time-help">Leave blank for now. This field uses your device time zone.</p><label class="refund-confirm"><input type="checkbox" required><span>I have already sent this refund outside TindaBot.</span></label><p id="refund-error" class="error-message" role="alert"></p><div class="dialog-actions"><button class="button" type="button" data-order="${escape(order.id)}">Go back</button><button class="button button-primary" type="submit">Save refund record</button></div></form>`, true);
  $('#refund-amount').focus();
}
async function saveOrderEntry(form) {
  const order = detailOrder, note = form.id === 'note-form';
  const errorNode = $(note ? '#note-error' : '#refund-error', form);
  const submit = $('button[type="submit"]', form), label = submit.textContent;
  const payload = {expected_version: order.version};
  if (note) {
    payload.body = $('#order-note').value.trim();
    if (!payload.body) { errorNode.textContent = 'Write a note before saving.'; return; }
  } else {
    const raw = $('#refund-amount').value;
    if (!/^\d+(\.\d{1,2})?$/.test(raw)) { errorNode.textContent = 'Use a positive amount with up to two decimal places.'; return; }
    const [whole, fraction = ''] = raw.split('.');
    payload.amount_minor = Number(whole) * 100 + Number(fraction.padEnd(2, '0'));
    payload.reference = $('#refund-reference')?.value.trim() || '';
    payload.completed_at = $('#refund-completed').value ? new Date($('#refund-completed').value).getTime() / 1000 : null;
  }
  const fingerprint = JSON.stringify(payload);
  if (form.dataset.payload !== fingerprint) { form.dataset.payload = fingerprint; form.dataset.commandId = crypto.randomUUID(); }
  payload.command_id = form.dataset.commandId;
  errorNode.textContent = ''; submit.textContent = 'Saving...'; busy(true);
  try {
    if (isDemo()) { if (note) demoNote(order.id, payload.body); else demoRefund(order.id, payload.amount_minor, payload.reference, payload.completed_at); }
    else await api(`/admin/orders/${encodeURIComponent(order.id)}/${note ? 'notes' : 'refunds'}`, {method: 'POST', body: JSON.stringify(payload)});
    invalidateSnapshots(); await refresh(); busy(false); await showOrder(order.id);
    toast(note ? 'Private note saved.' : 'External refund recorded.');
  } catch (error) { errorNode.textContent = error.message; }
  finally { busy(false); submit.textContent = label; }
}
function connectModal() {
  openModal('Make yourself at home', `<p>Connect this workspace to your shop using an operator token.</p><form id="connect-form"><label for="token">Operator token</label><input class="field" id="token" type="password" autocomplete="off" required maxlength="512" aria-describedby="token-help form-error"><p class="field-help" id="token-help">Use the ADMIN_TOKEN from your server configuration. It stays in this tab’s memory and is cleared on reload.</p><p id="form-error" class="error-message" role="alert"></p><div class="dialog-actions">${button('Cancel', 'close', '', 'type="button"')}<button class="button button-primary" type="submit">Connect workspace ${icon('arrow')}</button></div></form>`);
  $('#token').focus();
}
async function showOrder(id) {
  openModal('Order details', '<div role="status" class="skeleton skeleton-block"><span class="sr-only">Loading order details…</span></div>', true);
  const version = modalVersion;
  try {
    const order = isDemo() ? demoOrder(id) : await api(`/admin/workspace/orders/${encodeURIComponent(id)}`);
    if (!dialog.open || version !== modalVersion) return;
    detailOrder = order;
    const next = {pending: ['confirmed', 'Confirm order'], confirmed: ['shipped', 'Mark as shipped'], shipped: ['delivered', 'Mark as delivered']}[order.status];
    const canAdvance = order.status !== 'confirmed' || order.details.payment === 'cod' || order.payment_status === 'paid';
    const queue = filteredOrders(state.view === 'overview' ? 'newest' : state.sort), position = queue.findIndex(item => item.id === id);
    const steps = ['pending', 'confirmed', 'shipped', 'delivered'], step = steps.indexOf(order.status);
    const journey = step < 0 ? '' : `<ol class="order-journey" aria-label="Fulfillment progress">${steps.map((status, index) => `<li class="${index <= step ? 'reached' : ''}" ${index === step ? 'aria-current="step"' : ''}><span>${index < step ? icon('check') : index + 1}</span>${status[0].toUpperCase() + status.slice(1)}</li>`).join('')}</ol>`;
    const browse = position < 0 ? '' : `<div class="order-browse"><span>Order ${position + 1} of ${queue.length} in this view</span><div><button class="icon-button previous-order" aria-label="Previous order" ${position ? `data-order="${escape(queue[position - 1].id)}"` : 'disabled'}>${icon('arrow')}</button><button class="icon-button" aria-label="Next order" ${position < queue.length - 1 ? `data-order="${escape(queue[position + 1].id)}"` : 'disabled'}>${icon('arrow')}</button></div></div>`;
    openModal(escape(order.code), `${browse}<div class="order-summary"><span class="eyebrow">Order total</span><strong class="numeric">${money(order.total_minor)}</strong><span>Placed ${Number.isFinite(order.created_at) ? date(order.created_at, {month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit'}) : 'date unavailable'} · Manila time</span></div>${journey}<div class="detail-section">${badge(order.status)} <span class="badge">${escape(order.details.payment?.toUpperCase() || 'Payment')} · ${escape(order.payment_status.replaceAll('_', ' '))}</span>${isDemo() ? '<p class="field-help">Sample order · edits only affect this preview.</p>' : ''}</div>
      <div class="detail-section"><h3>Customer</h3><p><strong>${escape(order.details.name || 'Customer')}</strong></p><p class="muted">${escape(order.details.phone)}</p><p class="muted">${escape(order.details.address || 'Pickup order')}</p></div>
      <div class="detail-section"><h3>Order items</h3>${order.items.map(i => `<div class="detail-line"><span>${escape(i.name)} <span class="muted">× ${i.qty}</span></span><strong class="numeric">${money(i.price_minor * i.qty)}</strong></div>`).join('')}<div class="detail-line muted"><span>Delivery</span><span class="numeric">${money(order.shipping_minor)}</span></div><div class="detail-line detail-total"><strong>Total</strong><strong class="numeric">${money(order.total_minor)}</strong></div></div>
      <div class="detail-section"><h3>Next steps</h3><p class="muted">${order.status === 'cancelled' ? order.payment_status === 'refund_required' ? 'Arrange the refund with your customer outside TindaBot.' : 'This order is cancelled and stock has been released.' : order.status === 'delivered' ? 'This order has reached its customer.' : !canAdvance ? 'Verify payment before marking this order as shipped.' : 'Update the order when you’re ready. Stock and payment checks apply.'}</p><div class="detail-actions">${next ? `<button class="button button-primary" data-action="order-status" data-status="${next[0]}" ${!canAdvance ? 'disabled' : ''}>${next[1]}</button>` : ''}${order.payment_status === 'unpaid' && order.status !== 'cancelled' ? button('Verify payment…', 'verify-paid', 'check') : ''}${['pending', 'confirmed'].includes(order.status) ? '<button class="button button-quiet button-danger" data-action="verify-cancel">Cancel order…</button>' : ''}</div><p id="form-error" class="error-message" role="alert"></p></div>${orderJournal(order)}`, true);
    dialog.dataset.orderId = id; dialog.dataset.version = order.version;
    delete dialog.dataset.commandId; delete dialog.dataset.commandStatus;
  } catch (error) { if (dialog.open && version === modalVersion) openModal('Order unavailable', `<p class="error-message" role="alert">${escape(error.message)}</p>${button('Close', 'close')}`, true); }
}
function stockModal(sku) {
  const p = state.data.products.find(p => p.sku === sku);
  openModal('A shelf update', `<p>${escape(p.name)} · <span class="numeric">${p.stock}</span> available</p><form id="stock-form" data-stock="${p.stock}" data-sku="${escape(sku)}"><label for="delta">Units to add or remove</label><input class="field numeric" id="delta" type="number" step="1" min="${-Math.min(p.stock, 1000000)}" max="1000000" placeholder="e.g. 12 or −3" required aria-describedby="stock-help stock-preview form-error"><div class="stock-presets" role="group" aria-label="Adjustment shortcuts"><button class="button" type="button" data-stock-delta="5">Add 5</button><button class="button" type="button" data-stock-delta="10">Add 10</button><button class="button" type="button" data-stock-delta="-1" ${p.stock < 1 ? 'disabled' : ''}>Remove 1</button></div><div class="stock-preview" id="stock-preview" role="status">Enter an adjustment to preview available stock.</div><p class="field-help" id="stock-help">Positive adds stock; negative removes it. ${isDemo() ? 'This updates the preview only.' : 'The preview uses this snapshot. New orders can change the final stock count.'}</p><p id="form-error" class="error-message" role="alert"></p><div class="dialog-actions">${button('Cancel', 'close', '', 'type="button"')}<button class="button button-primary" type="submit">Save adjustment</button></div></form>`);
  $('#delta').focus();
}
function previewStock() {
  const form = $('#stock-form'), input = $('#delta');
  if (!form || !input) return;
  const delta = Number(input.value), current = Number(form.dataset.stock);
  const valid = input.value !== '' && Number.isInteger(delta) && delta !== 0 && Math.abs(delta) <= 1000000 && current + delta >= 0;
  $('#stock-preview').textContent = valid ? `${current} available ${delta > 0 ? '+' : '-'} ${Math.abs(delta)} = ${current + delta} after adjustment` : input.value === '' ? 'Enter an adjustment to preview available stock.' : current + delta < 0 ? 'This would remove more stock than is available.' : 'Use a whole, non-zero adjustment up to 1,000,000 units.';
}
function guide() {
  openModal('A calmer way to run your shop', `<p>Your essentials, in one place.</p><div class="detail-section"><h3>1. Explore or connect</h3><p class="muted">The preview uses sample data. Connect with your operator token to view this server’s shop. Reloading clears the connection.</p></div><div class="detail-section"><h3>2. Keep orders moving</h3><p class="muted">Open an order to confirm it, verify payment, or update delivery. Inventory updates use adjustments so incoming orders remain accounted for.</p></div><div class="detail-section"><h3>3. Check your assistant</h3><p class="muted">In Automation, use Customers needing help to review paused conversations and Review deliveries to inspect failed or uncertain deliveries. Resume or retry only after checking the request. Import products through your configured seller sheet or catalog API.</p></div><div class="detail-section"><h3>A few useful shortcuts</h3><p class="muted">Press / to search, Escape to close a dialog, and Tab to move between controls. Use the theme button for a quieter evening view.</p></div><div class="dialog-actions">${button('Got it', 'close', 'check')}</div>`);
}
async function exportOrders() {
  let selected = filteredOrders();
  if (!isDemo() && state.view === 'orders') {
    const path = workspacePath(), token = state.token;
    selected = [];
    let cursor = null;
    toast('Preparing all matching orders...');
    try {
      do {
        const data = await api(path + (cursor ? `&cursor=${encodeURIComponent(cursor)}` : ''), {}, token);
        if (state.token !== token) return;
        selected.push(...data.orders); cursor = data.next_cursor;
      } while (cursor);
    } catch (error) { toast(error.message); return; }
  }
  const safeCell = (v) => { const s = String(v); return `"${(/^[=+\-@\t\r\n]/.test(s) ? "'" + s : s).replaceAll('"', '""')}"`; };
  const rows = [['Order', 'Customer', 'Status', 'Payment status', 'Date (Manila)', 'Amount (PHP)'], ...selected.map(o => [o.code, o.name, o.status, o.payment_status, date(o.created_at, {year: 'numeric', month: '2-digit', day: '2-digit'}), (o.total_minor / 100).toFixed(2)])];
  const url = URL.createObjectURL(new Blob(['\uFEFF' + rows.map(row => row.map(safeCell).join(',')).join('\r\n')], {type: 'text/csv;charset=utf-8'}));
  const link = document.createElement('a'); link.href = url; link.download = `tindabot-${isDemo() ? 'sample-' : ''}orders.csv`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  toast(`${rows.length - 1} ${isDemo() ? 'sample ' : ''}orders exported.`);
}
document.addEventListener('click', async event => {
  const node = event.target.closest('button'); if (!node || node.disabled) return;
  if (node.dataset.command) {
    const key = node.dataset.command;
    closeModal();
    // The native close event restores focus before the new view takes focus.
    requestAnimationFrame(() => navigate(key === 'pending' ? 'orders' : key === 'low' ? 'inventory' : key, key === 'pending' ? 'pending' : key === 'low' ? 'low' : 'all'));
    return;
  }
  if (node.dataset.stockDelta) { $('#delta').value = node.dataset.stockDelta; previewStock(); $('#delta').focus(); return; }
  if (node.dataset.view) return navigate(node.dataset.view);
  if (node.dataset.stage) { state.filter = node.dataset.stage; return updateOrderView(`[data-stage="${state.filter}"]`); }
  if (node.dataset.filter) { state.filter = node.dataset.filter; return updateOrderView(`[data-filter="${state.filter}"]`); }
  if (node.dataset.order) return showOrder(node.dataset.order);
  const action = node.dataset.action;
  if (action === 'handovers') return handoverQueue({api, openModal, escape, date, isDemo, refresh, toast, busy, invalidateSnapshots});
  if (action === 'deliveries') return deliveryReview({api, openModal, escape, date, button, isDemo, refresh, toast, busy});
  if (action === 'clear-search') { state.query = ''; $('#search').value = ''; return updateOrderView('#search'); }
  if (action === 'commands') return commands();
  if (action === 'motion') return toggleAmbient();
  if (action === 'close') return closeModal();
  if (action === 'connect') return connectModal();
  if (action === 'guide') return guide();
  if (action === 'stock') return stockModal(node.dataset.sku);
  if (action === 'refresh') return refresh(true);
  if (action === 'more-orders') return loadMoreOrders();
  if (action === 'pending') return navigate('orders', 'pending');
  if (action === 'low-stock') return navigate('inventory', 'low');
  if (action === 'clear') { state.filter = 'all'; state.payment = 'all'; state.query = ''; $('#search').value = ''; return updateOrderView('#search'); }
  if (action === 'disconnect') { state.request++; state.token = ''; state.loading = false; state.error = ''; state.query = ''; viewContexts.clear(); historyContexts.clear(); state.data = demoSnapshot(state.days, state.view === 'orders' ? state.scope : 'period'); shell(); toast('Disconnected. You’re back in the preview.'); return; }
  if (action === 'theme') {
    const theme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'; document.documentElement.dataset.theme = theme;
    try { localStorage.setItem('tindabot-theme', theme); } catch { /* Theme still works without storage. */ }
    node.innerHTML = icon(theme === 'dark' ? 'sun' : 'moon'); node.setAttribute('aria-label', `Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`); return;
  }
  if (action === 'export') return exportOrders();
  if (action === 'record-refund') return refundModal();
  if (action === 'earlier-activity') {
    const version = modalVersion, order = detailOrder; node.disabled = true;
    try {
      const data = await api(`/admin/workspace/orders/${encodeURIComponent(order.id)}/activity?before=${order.next_activity_cursor}`);
      if (!dialog.open || version !== modalVersion) return;
      order.activity.push(...data.activity); order.next_activity_cursor = data.next_activity_cursor;
      $('.activity-list', dialog).insertAdjacentHTML('beforeend', data.activity.map(activityItem).join(''));
      if (!data.next_activity_cursor) { node.remove(); $('#activity-title').setAttribute('tabindex', '-1'); $('#activity-title').focus(); }
    } catch (error) { toast(error.message); }
    finally { node.disabled = false; } return;
  }
  if (action === 'breakdown') return openModal('Daily order value', `<p>Philippine pesos · Manila time · cancelled orders excluded.</p><table><thead><tr><th scope="col" class="date-column">Date</th><th scope="col" class="align-right">Value</th></tr></thead><tbody>${state.data.series.map(v => `<tr><td>${date(v.timestamp)}</td><td class="align-right numeric">${money(v.value)}</td></tr>`).join('')}</tbody></table>`);
  if (action === 'verify-paid' || action === 'verify-cancel') {
    const status = action === 'verify-paid' ? 'paid' : 'cancelled';
    const section = node.closest('.detail-section');
    section.innerHTML = `<h3>${status === 'paid' ? 'Has payment arrived?' : 'Cancel this order?'}</h3><p class="muted">${status === 'paid' ? 'Only verify payment after you have checked the actual payment receipt. This does not charge the customer.' : 'This releases the reserved stock. If payment was received, you will need to arrange a refund separately.'}</p><div class="detail-actions"><button class="button button-primary" data-action="order-status" data-status="${status}">${status === 'paid' ? 'Yes, payment received' : 'Yes, cancel order'}</button><button class="button" data-order="${escape(dialog.dataset.orderId)}">Go back</button></div><p id="form-error" class="error-message" role="alert"></p>`;
    section.querySelector('button').focus(); return;
  }
  if (action === 'order-status') {
    const id = dialog.dataset.orderId, status = node.dataset.status;
    if (dialog.dataset.commandStatus !== status) { dialog.dataset.commandId = crypto.randomUUID(); dialog.dataset.commandStatus = status; }
    const label = node.textContent; node.textContent = 'Saving…'; busy(true);
    try {
      if (isDemo()) demoStatus(id, status);
      else await api('/admin/order-status', {method: 'POST', body: JSON.stringify({command_id: dialog.dataset.commandId, order_id: id, expected_version: Number(dialog.dataset.version), status})});
      busy(false); dialog.close(); invalidateSnapshots(); await refresh(); toast(isDemo() ? 'Sample order updated.' : 'Order update saved.');
    } catch (error) { $('#form-error', dialog).textContent = error.message; }
    finally { busy(false); node.textContent = label; } return;
  }
  if (action === 'automation') {
    const enabled = !state.data.automation;
    openModal(enabled ? 'Resume automated replies?' : 'Pause automated replies?', `<p>${enabled ? 'TindaBot will guide new messages through your ordering flow. Individual conversation pauses still apply. Previously suppressed replies are not replayed.' : 'New messages won’t receive automated replies, and queued Messenger replies will be suppressed. A send already in progress may finish. Existing orders, Sheet exports, and seller emails are unaffected.'}</p><form id="automation-form" data-enabled="${enabled}"><p id="form-error" class="error-message" role="alert"></p><div class="dialog-actions">${button('Keep current setting', 'close', '', 'type="button"')}<button class="button button-primary" type="submit">${enabled ? 'Resume replies' : 'Pause replies'}</button></div></form>`); return;
  }
});
document.addEventListener('submit', async event => {
  const form = event.target;
  if (['note-form', 'refund-form'].includes(form.id)) { event.preventDefault(); return saveOrderEntry(form); }
  if (!['connect-form', 'stock-form', 'automation-form'].includes(form.id)) return;
  event.preventDefault();
  const submit = $('button[type="submit"]', form), label = submit.textContent;
  const token = form.id === 'connect-form' ? $('#token').value.trim() : '';
  const delta = form.id === 'stock-form' ? Number($('#delta').value) : 0;
  if (form.id === 'stock-form' && (!Number.isInteger(delta) || delta === 0)) { $('#form-error', form).textContent = 'Enter a whole number other than zero.'; return; }
  $('#form-error', form).textContent = ''; submit.textContent = 'Saving…'; busy(true);
  try {
    if (form.id === 'connect-form') {
      submit.textContent = 'Connecting…';
      state.filter = 'all'; state.payment = 'all'; state.query = '';
      const data = await api(workspacePath(), {}, token);
      invalidateSnapshots(); viewContexts.clear(); historyContexts.clear(); state.request++; state.token = token; state.data = data; state.error = ''; state.loading = false; state.query = ''; state.filter = 'all'; state.payment = 'all'; state.loadedPath = workspacePath();
      busy(false); dialog.close(); shell(); toast('Your shop is connected.');
    } else if (form.id === 'stock-form') {
      if (isDemo()) demoStock(form.dataset.sku, delta);
      else {
        if (form.dataset.delta !== String(delta)) { form.dataset.commandId = crypto.randomUUID(); form.dataset.delta = delta; }
        await api('/admin/stock', {method: 'POST', body: JSON.stringify({command_id: form.dataset.commandId, sku: form.dataset.sku, delta})});
      }
      busy(false); dialog.close(); invalidateSnapshots(); await refresh(); toast(isDemo() ? 'Sample stock adjusted.' : 'Stock adjustment saved.');
    } else {
      const enabled = form.dataset.enabled === 'true';
      if (isDemo()) demoAutomation(enabled); else await api('/admin/automation', {method: 'POST', body: JSON.stringify({enabled})});
      busy(false); dialog.close(); invalidateSnapshots(); await refresh(); toast(enabled ? 'Automated replies enabled.' : 'Automated replies paused.');
    }
  } catch (error) { const target = $('#form-error', form); if (target) target.textContent = error.message; }
  finally { busy(false); submit.textContent = label; }
});
document.addEventListener('input', event => {
  if (event.target.id === 'delta') return previewStock();
  if (event.target.id === 'chart-day') return selectChartDay(event.target.value);
  if (event.target.id === 'command-search') {
    const query = event.target.value.toLowerCase();
    dialog.querySelectorAll('.command-item').forEach(item => item.hidden = !item.textContent.toLowerCase().includes(query));
    $('#command-empty').hidden = Boolean($('.command-item:not([hidden])', dialog));
    return;
  }
  if (event.target.id !== 'search') return;
  state.query = event.target.value;
  if (state.view === 'automation') { const query = state.query; navigate('orders', 'all'); state.query = query; $('#search').value = query; }
  saveContext();
  clearTimeout(searchTimer);
  if (!isDemo() && state.view === 'orders') {
    state.request++; state.loading = false; state.paging = false;
    searchTimer = setTimeout(() => updateOrderView(), 250);
  }
  renderPage();
});
document.addEventListener('change', event => {
  const fields = {'payment-filter': 'payment', 'stock-sort': 'stockSort', 'order-sort': 'sort', 'order-scope': 'scope'};
  if (fields[event.target.id]) {
    state[fields[event.target.id]] = event.target.value;
    if (event.target.id === 'order-scope' && isDemo()) state.data = demoSnapshot(state.days, state.scope);
    return updateOrderView(`#${event.target.id}`);
  }
  if (event.target.id === 'period') { state.days = Number(event.target.value); state.chartDay = null; saveContext(); refresh(); }
});

document.addEventListener('pointermove', event => {
  const chart = event.target.closest('.chart svg');
  if (!chart || state.loading) return;
  const rect = chart.getBoundingClientRect(), box = chart.viewBox.baseVal;
  const scale = Math.min(rect.width / box.width, rect.height / box.height);
  const inset = (rect.width - box.width * scale) / 2;
  const x = (event.clientX - rect.left - inset) / scale;
  const index = Math.round((x - 40) / (box.width - 64) * (state.data.series.length - 1));
  if (index !== state.chartDay) selectChartDay(index);
});
document.addEventListener('keydown', event => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k' && !dialog.open) { event.preventDefault(); commands(); return; }
  if (dialog.open && $('#command-search') && ['ArrowDown', 'ArrowUp', 'Enter'].includes(event.key)) {
    const items = [...dialog.querySelectorAll('.command-item:not([hidden])')];
    if (!items.length) return;
    const current = items.indexOf(document.activeElement);
    if (event.key === 'Enter') { if (document.activeElement.id === 'command-search') { event.preventDefault(); items[0].click(); } return; }
    event.preventDefault();
    items[(current + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length].focus(); return;
  }
  if (event.key === '/' && !dialog.open && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) { event.preventDefault(); $('#search').focus(); }
});
window.addEventListener('popstate', event => {
  const view = labels[location.hash.slice(1)] ? location.hash.slice(1) : 'overview';
  const context = historyContexts.get(event.state?.workspaceKey) || {view, filter: 'all', query: '', payment: 'all', scope: 'all', scroll: 0};
  navigate(view, undefined, {...context});
});
window.addEventListener('hashchange', () => { const view = location.hash.slice(1); if (labels[view] && view !== state.view) navigate(view); });
matchMedia('(max-width: 760px)').addEventListener('change', () => renderPage());
state.view = labels[location.hash.slice(1)] ? location.hash.slice(1) : 'overview';
state.data = demoSnapshot(state.days, state.view === 'orders' ? state.scope : 'period');
history.replaceState({workspaceKey: historyKey}, '', `#${state.view}`);
shell();
saveContext();
