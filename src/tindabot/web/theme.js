try {
  document.documentElement.dataset.theme = localStorage.getItem('tindabot-theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
} catch {
  document.documentElement.dataset.theme = matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}
