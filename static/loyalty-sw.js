self.addEventListener('push', event => {
  let data = {};
  try { data = event.data.json(); } catch (_) { data = { title: 'Nueva promoción', body: event.data ? event.data.text() : '' }; }
  event.waitUntil(self.registration.showNotification(data.title || 'Promoción', {
    body: data.body || '', icon: '/static/img/loyalty-icon.png', data: { url: data.url || '/' }
  }));
});
self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(clients.openWindow(event.notification.data.url || '/'));
});
