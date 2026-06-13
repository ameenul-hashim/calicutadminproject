(function () {
  'use strict';

  if (window.NeoRealtimeLoaded) return;
  window.NeoRealtimeLoaded = true;

  var ws = null;
  var reconnectTimer = null;
  var pingTimer = null;
  var listeners = {};

  var RECONNECT_DELAY = 3000;

  function getWebSocketUrl() {
    var protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return protocol + '//' + window.location.host + '/ws/notifications/';
  }

  function connect() {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return;

    var url = getWebSocketUrl();
    try {
      ws = new WebSocket(url);
    } catch (e) {
      scheduleReconnect();
      return;
    }

    ws.onopen = function () {
      startPing();
      emit('connected', {});
    };

    ws.onmessage = function (event) {
      try {
        var data = JSON.parse(event.data);
        emit(data.type, data);

        switch (data.type) {
          case 'chat_message':
            handleChatMessage(data);
            break;
          case 'notification':
            handleNotification(data);
            break;
          case 'pending_counts':
            handlePendingCounts(data);
            break;
        }
      } catch (e) {
        // ignore parse errors
      }
    };

    ws.onclose = function () {
      stopPing();
      ws = null;
      scheduleReconnect();
    };

    ws.onerror = function () {
      // onclose will fire next
    };
  }

  function scheduleReconnect() {
    if (reconnectTimer) return;
    reconnectTimer = setTimeout(function () {
      reconnectTimer = null;
      connect();
    }, RECONNECT_DELAY);
  }

  function startPing() {
    stopPing();
    pingTimer = setInterval(function () {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'ping' }));
      }
    }, 25000);
  }

  function stopPing() {
    if (pingTimer) { clearInterval(pingTimer); pingTimer = null; }
  }

  function send(data) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(data));
    }
  }

  function on(event, callback) {
    if (!listeners[event]) listeners[event] = [];
    listeners[event].push(callback);
    return function () {
      listeners[event] = listeners[event].filter(function (fn) { return fn !== callback; });
    };
  }

  function emit(event, data) {
    (listeners[event] || []).forEach(function (fn) { fn(data); });
  }

  function handleChatMessage(data) {
    var badge = document.getElementById('chat-unread-badge');
    if (badge && !data.is_me) {
      var count = parseInt(badge.textContent) || 0;
      badge.textContent = count + 1;
      badge.style.display = 'flex';
    }

    var event = new CustomEvent('neochat-message', { detail: data });
    window.dispatchEvent(event);
  }

  function handleNotification(data) {
    var badge = document.getElementById('notification-badge');
    if (badge && data.count) {
      badge.textContent = data.count > 99 ? '99+' : data.count;
      badge.style.display = 'flex';
    }

    if (data.url) {
      var notifArea = document.getElementById('notification-dropdown');
      if (notifArea) {
        var item = document.createElement('div');
        item.className = 'notification-item';
        item.innerHTML = '<div class="notif-title">' + escapeHtml(data.title) + '</div><div class="notif-msg">' + escapeHtml(data.message) + '</div>';
        item.onclick = function () { window.location.href = data.url; };
        notifArea.insertBefore(item, notifArea.firstChild);
      }
    }
  }

  function handlePendingCounts(data) {
    var counts = data.counts || {};
    Object.keys(counts).forEach(function (key) {
      var el = document.getElementById(key);
      if (el) {
        var val = counts[key];
        if (val > 0) {
          el.textContent = val > 99 ? '99+' : val;
          el.style.display = 'flex';
        } else {
          el.style.display = 'none';
        }
      }
    });
  }

  function escapeHtml(text) {
    var d = document.createElement('div');
    d.textContent = text;
    return d.innerHTML;
  }

  // Expose public API
  window.NeoRealtime = {
    connect: connect,
    send: send,
    on: on,
  };

  // Auto-connect when DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', connect);
  } else {
    connect();
  }
})();
