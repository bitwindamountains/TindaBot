const reduced = matchMedia('(prefers-reduced-motion: reduce)');
const compact = matchMedia('(max-width: 760px)');
let enabled = true, scene = null, effect = null, loading = false, generation = 0;
try { enabled = localStorage.getItem('tindabot-ambient') !== 'off'; } catch { /* In-memory preference still works. */ }
const observer = new IntersectionObserver(entries => {
  for (const entry of entries) entry.target.classList.toggle('scene-paused', !entry.isIntersecting);
  syncEffect();
}, {threshold: .05});
const options = () => ({active: Boolean(enabled && !reduced.matches && !compact.matches && !document.hidden && scene && !scene.classList.contains('scene-paused')), dark: document.documentElement.dataset.theme === 'dark'});
async function syncEffect() {
  if (!scene) return;
  const prefs = options();
  if (effect) { effect.update(prefs); return; }
  if (!prefs.active || loading || scene.dataset.renderer === 'unavailable' || navigator.connection?.saveData) return;
  loading = true;
  const target = scene, version = generation;
  try {
    const canvas = document.createElement('canvas');
    const context = canvas.getContext('webgl2', {failIfMajorPerformanceCaveat: true});
    if (!context) { target.dataset.renderer = 'unavailable'; return; }
    context.getExtension('WEBGL_lose_context')?.loseContext();
    const module = await import('./effects/hero.js');
    if (version !== generation || target !== scene || !target.isConnected) return;
    effect = module.mountHero(target, options());
  } catch { if (target === scene) target.dataset.renderer = 'unavailable'; }
  finally { if (version === generation) loading = false; }
}
function apply() {
  const active = enabled && !reduced.matches;
  document.documentElement.dataset.motion = active ? 'on' : 'off';
  document.documentElement.dataset.pageHidden = String(document.hidden);
  document.querySelectorAll('[data-action="motion"]').forEach(button => {
    button.setAttribute('aria-pressed', String(active));
    button.setAttribute('aria-label', reduced.matches ? 'Ambient motion disabled by system preference' : active ? 'Pause ambient motion' : 'Play ambient motion');
    button.disabled = reduced.matches;
    button.querySelector('span').textContent = reduced.matches ? 'Reduced motion' : active ? 'Motion on' : 'Motion paused';
  });
  syncEffect();
}
export function toggleAmbient() {
  enabled = !enabled;
  try { localStorage.setItem('tindabot-ambient', enabled ? 'on' : 'off'); } catch { /* Preference remains available in memory. */ }
  apply();
}
export function observeScenes() {
  const next = document.querySelector('.hero-scene');
  if (scene !== next) {
    generation++; loading = false;
    effect?.dispose(); effect = null; observer.disconnect(); scene = next;
    if (scene) { scene.classList.add('scene-paused'); observer.observe(scene); }
  }
  apply();
}
reduced.addEventListener('change', apply);
compact.addEventListener('change', apply);
document.addEventListener('visibilitychange', apply);
new MutationObserver(apply).observe(document.documentElement, {attributes: true, attributeFilter: ['data-theme']});
apply();
export function heroBackdrop() {
  return `<div class="hero-scene ambient-scene" aria-hidden="true" data-renderer="fallback"><div class="shader-fallback"></div><div class="shader-mount"></div><div class="hero-orbits"><i></i><i></i><i></i></div></div>`;
}
