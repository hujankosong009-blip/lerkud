(() => {
  const status = document.getElementById('live-status');
  if (!status) return;
  const notice = document.getElementById('live-notice');
  const badge = document.getElementById('waiting-badge');
  const enable = document.getElementById('enable-browser-notifications');
  const originalTitle = document.title;
  let previous = null;
  let dirty = false;
  document.querySelectorAll('form[method="post"] input, form[method="post"] textarea, form[method="post"] select').forEach(el => el.addEventListener('input', () => { dirty = true; }));
  enable.addEventListener('click', async () => {
    if (!('Notification' in window) || !window.isSecureContext) {
      status.textContent = 'Notifikasi browser memerlukan HTTPS/localhost. Penanda halaman tetap aktif.';
      return;
    }
    const permission = await Notification.requestPermission();
    enable.textContent = permission === 'granted' ? '🔔 Notifikasi browser aktif' : 'Izin browser belum diberikan';
  });
  async function poll() {
    try {
      const response = await fetch('/pembaruan/', {headers:{'Accept':'application/json'},cache:'no-store',credentials:'same-origin'});
      if (response.redirected || !response.ok) { status.textContent = 'Sesi berakhir. Silakan login kembali.'; return; }
      const data = await response.json();
      badge.textContent = data.waiting;
      document.title = (data.waiting ? `(${data.waiting}) ` : '') + originalTitle;
      status.textContent = `● Pembaruan otomatis · ${data.notification_mode === 'live' ? 'Telegram live' : 'Telegram simulasi'}`;
      if (previous && (previous.revision !== data.revision || previous.total !== data.total)) {
        notice.hidden = false;
        notice.textContent = `🔔 Ada pembaruan permohonan. ${data.waiting} berkas menunggu verifikasi.`;
        if ('Notification' in window && Notification.permission === 'granted') {
          try { new Notification('SALAM MANIS · Pembaruan layanan', {body:'Ada pembaruan permohonan. Buka dashboard untuk rincian.',tag:'salam-manis-update'}); } catch (_) { /* Some mobile browsers require a service worker; the page badge remains active. */ }
        }
        if (document.getElementById('data-table') && !dirty) {
          const current = await fetch(window.location.href, {cache:'no-store',credentials:'same-origin'});
          if (current.ok && !current.redirected) {
            const html = new DOMParser().parseFromString(await current.text(), 'text/html');
            const table = html.getElementById('data-table');
            if (table) document.getElementById('data-table').replaceChildren(...table.childNodes);
          }
        }
      }
      previous = data;
    } catch (_) { status.textContent = 'Pembaruan terputus; mencoba kembali…'; }
    window.setTimeout(poll, 5000);
  }
  poll();
})();
