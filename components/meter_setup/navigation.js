// Loaded alongside the standard ESPHome dashboard.
function addMeterNavigation() {
  if (document.getElementById('meter-navigation')) return;
  const nav = document.createElement('nav');
  nav.id = 'meter-navigation';
  nav.setAttribute('aria-label', 'Wasserzähler');
  nav.style.cssText = 'display:flex;gap:12px;flex-wrap:wrap;padding:16px;font:16px system-ui';
  for (const [label, url] of [['Wasserzähler einrichten', '/setup'], ['Status / Diagnose', '/meter/status']]) {
    const link = document.createElement('a');
    link.textContent = label;
    link.href = url;
    link.style.cssText = 'display:inline-block;padding:10px 16px;background:#115c80;color:white;border-radius:8px;text-decoration:none';
    nav.append(link);
  }
  document.body.prepend(nav);
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', addMeterNavigation, {once:true});
else addMeterNavigation();
