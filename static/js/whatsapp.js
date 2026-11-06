(() => {
  let sdkReady = false;
  let authorizationCode = null;
  let signupData = null;
  let submitting = false;

  window.fbAsyncInit = () => {
    FB.init({
      appId: window.NOXTIUM_META_APP_ID,
      cookie: true,
      xfbml: false,
      version: window.NOXTIUM_META_VERSION,
    });
    sdkReady = true;
  };

  window.addEventListener('message', (event) => {
    // Accept only the official Facebook origins used by the Embedded Signup dialog.
    if (!['https://www.facebook.com', 'https://web.facebook.com'].includes(event.origin)) return;
    let data;
    try { data = typeof event.data === 'string' ? JSON.parse(event.data) : event.data; }
    catch (_) { return; }
    if (!data || data.type !== 'WA_EMBEDDED_SIGNUP') return;

    if (data.event === 'FINISH') {
      signupData = data.data || {};
      maybeExchange();
    } else if (data.event === 'ERROR') {
      setStatus('Meta reportó un error. Revisa los permisos de la aplicación y vuelve a intentarlo.', true);
    } else if (data.event === 'CANCEL') {
      setStatus('Cancelaste el registro. Puedes volver a intentarlo cuando quieras.', true);
    }
  });

  document.addEventListener('DOMContentLoaded', () => {
    const button = document.getElementById('connect-whatsapp');
    if (!button) return;
    button.addEventListener('click', () => {
      if (!sdkReady || !window.NOXTIUM_META_APP_ID) {
        setStatus('La conexión oficial todavía no está lista. El administrador debe completar la configuración de Meta.', true);
        return;
      }
      if (!window.NOXTIUM_META_CONFIG_ID) {
        setStatus('Falta configurar META_EMBEDDED_SIGNUP_CONFIG_ID en el servidor.', true);
        return;
      }
      authorizationCode = null;
      signupData = null;
      submitting = false;
      button.disabled = true;
      setStatus('Abriendo el registro oficial de WhatsApp Business de Meta…');
      FB.login((response) => {
        authorizationCode = response?.authResponse?.code || null;
        if (!authorizationCode) {
          button.disabled = false;
          setStatus('Meta no entregó el código de autorización. Verifica la configuración Embedded Signup y vuelve a intentarlo.', true);
          return;
        }
        maybeExchange();
      }, {
        config_id: window.NOXTIUM_META_CONFIG_ID,
        response_type: 'code',
        override_default_response_type: true,
        extras: { setup: {}, featureType: 'whatsapp_business_app_onboarding', sessionInfoVersion: '3' },
      });
    });
  });

  async function maybeExchange() {
    if (!authorizationCode || !signupData || submitting) return;
    const wabaId = signupData.waba_id || signupData.wabaId;
    const phoneNumberId = signupData.phone_number_id || signupData.phoneNumberId;
    if (!wabaId || !phoneNumberId) {
      setStatus('Meta terminó el registro, pero no devolvió el identificador de la cuenta y del número. Revisa el flujo Embedded Signup configurado en Meta.', true);
      enableButton();
      return;
    }
    submitting = true;
    setStatus('Verificando permisos, número y cuenta con Meta…');
    try {
      const response = await fetch('/api/meta/embedded-signup', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: authorizationCode, waba_id: String(wabaId), phone_number_id: String(phoneNumberId) }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || 'No se pudo completar la conexión oficial.');
      setStatus(`WhatsApp Business conectado: ${data.display_phone_number || phoneNumberId}. Ahora vamos a configurar tu catálogo y agente.`);
      window.location.assign(data.next_url || '/crm/agente?connected=1');
    } catch (error) {
      setStatus(error.message || 'No se pudo completar la conexión.', true);
      enableButton();
    } finally {
      submitting = false;
    }
  }

  function enableButton() {
    const button = document.getElementById('connect-whatsapp');
    if (button) button.disabled = false;
  }
  function setStatus(message, isError = false) {
    const element = document.getElementById('whatsapp-status');
    if (!element) return;
    element.textContent = message;
    element.dataset.error = isError ? 'true' : 'false';
  }
})();
