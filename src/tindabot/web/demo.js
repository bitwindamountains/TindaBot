// Sample records are browser-only. They are never written to the service.
const now = Date.now() / 1000;
const today = Math.floor((now + 28800) / 86400) * 86400 - 28800;
const names = ['Sofia Reyes', 'Miguel Santos', 'Isabella Cruz', 'Lucas Garcia', 'Camille Lim', 'Andrea Torres', 'Paolo Mendoza', 'Elena Flores'];
const products = [
  {sku: 'TOTE-01', name: 'Everyday canvas tote', price_minor: 49000, stock: 24, active: true},
  {sku: 'MUG-01', name: 'Sunday ceramic mug', price_minor: 38000, stock: 4, active: true},
  {sku: 'POUCH-01', name: 'Little things pouch', price_minor: 25000, stock: 36, active: true},
  {sku: 'NOTE-01', name: 'Daily notes journal', price_minor: 32000, stock: 18, active: true},
  {sku: 'CANDLE-01', name: 'Slow morning candle', price_minor: 59000, stock: 3, active: true},
  {sku: 'TRAY-01', name: 'Pebble catchall tray', price_minor: 45000, stock: 12, active: true},
];
const orders = Array.from({length: 86}, (_, i) => {
  const p = products[i % products.length];
  const qty = i % 3 === 0 ? 2 : 1;
  const age = i < 6 ? 0 : Math.floor((i - 6) / 4) + 1;
  const created = Math.min(now - 120 - i * 480, today + 43200 - age * 86400 - (i % 4) * 2700);
  const status = i < 3 ? 'pending' : i < 7 ? 'confirmed' : i < 12 ? 'shipped' : i === 18 ? 'cancelled' : 'delivered';
  return {id: `demo-${i}`, code: `TB-${1048 - i}`, name: names[i % names.length], item_count: qty,
    total_minor: p.price_minor * qty + 8000, status, payment_status: i < 5 ? 'unpaid' : 'paid',
    version: 1, created_at: created, shipping_minor: 8000,
    details: {name: names[i % names.length], phone: 'Sample contact', address: 'Sample delivery address · Quezon City', delivery: 'delivery', payment: i % 2 ? 'gcash' : 'cod'},
    items: [{sku: p.sku, name: p.name, price_minor: p.price_minor, qty}]};
});
let automation = true;
export function demoSnapshot(days) {
  const start = today - (days - 1) * 86400;
  const recent = orders.filter(o => o.created_at >= start);
  return {shop_name: 'Sari Studio', generated_at: now, days,
    summary: {order_value: recent.filter(o => o.status !== 'cancelled').reduce((a, o) => a + o.total_minor, 0), orders: recent.length, pending: recent.filter(o => o.status === 'pending').length, products: products.filter(p => p.active).length},
    series: Array.from({length: days}, (_, i) => ({timestamp: start + i * 86400, value: recent.filter(o => o.status !== 'cancelled' && o.created_at >= start + i * 86400 && o.created_at < start + (i + 1) * 86400).reduce((a, o) => a + o.total_minor, 0)})),
    orders: recent, products, automation, automation_locked: false, delivery_mode: 'dry_run', worker_age_seconds: 8, failures: 0, job_health: {inbox_failed: 0, delivery_failed: 0, delivery_uncertain: 0}, queue: 0};
}
export const demoOrder = (id) => orders.find(o => o.id === id);
export function demoStatus(id, status) {
  const order = demoOrder(id);
  if (status === 'paid') order.payment_status = 'paid';
  else {
    order.status = status;
    if (status === 'cancelled') {
      order.items.forEach(item => { products.find(p => p.sku === item.sku).stock += item.qty; });
      if (order.payment_status === 'paid') order.payment_status = 'refund_required';
    }
  }
  order.version++;
}
export function demoStock(sku, delta) { products.find(p => p.sku === sku).stock += delta; }
export function demoAutomation(value) { automation = value; }
