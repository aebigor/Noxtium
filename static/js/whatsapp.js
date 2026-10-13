(() => {
    let metaReady = false;
    let authorizationCode = null;
    let signupData = null;

    window.fbAsyncInit = function () {
        FB.init({
            appId: window.NOXTIUM_META_APP_ID,
            cookie: true,
            xfbml: true,
            version: window.NOXTIUM_META_VERSION,
        });

        metaReady = true;
    };

    window.addEventListener("message", (event) => {
        if (!event.origin.endsWith("facebook.com")) {
            return;
        }

        try {
            const data = JSON.parse(event.data);

            if (data.type !== "WA_EMBEDDED_SIGNUP") {
                return;
            }

            console.log("WA_EMBEDDED_SIGNUP:", data);

            if (data.event === "FINISH") {
                signupData = data.data || {};

                if (authorizationCode) {
                    exchangeCode(
                        authorizationCode,
                        signupData.waba_id,
                        signupData.phone_number_id,
                    );
                }
            }

            if (data.event === "ERROR") {
                setStatus(
                    "Meta reportó un error durante el registro.",
                    true,
                );
                console.error(data);
            }

            if (data.event === "CANCEL") {
                setStatus("El registro fue cancelado.", true);
            }
        } catch (_) {
            // Algunos postMessage no son JSON.
        }
    });

    document.addEventListener("DOMContentLoaded", () => {
        const button = document.getElementById("connect-whatsapp");
        if (!button) return;

        button.addEventListener("click", () => {
            if (!metaReady) {
                setStatus("Meta todavía no está listo.", true);
                return;
            }

            const configId = window.NOXTIUM_META_CONFIG_ID;
            if (!configId) {
                setStatus(
                    "Falta META_EMBEDDED_SIGNUP_CONFIG_ID en .env.",
                    true,
                );
                return;
            }

            setStatus("Abriendo registro de Meta...");

            FB.login(
                (response) => {
                    console.log("FB.login:", response);

                    if (!response.authResponse) {
                        setStatus(
                            "Meta no devolvió una autorización.",
                            true,
                        );
                        return;
                    }

                    authorizationCode =
                        response.authResponse.code || null;

                    // En el flujo response_type=code el listener
                    // WA_EMBEDDED_SIGNUP entrega los IDs de onboarding.
                    if (authorizationCode && signupData) {
                        exchangeCode(
                            authorizationCode,
                            signupData.waba_id,
                            signupData.phone_number_id,
                        );
                    } else if (!authorizationCode) {
                        setStatus(
                            "No se recibió authorization code.",
                            true,
                        );
                    }
                },
                {
                    config_id: configId,
                    response_type: "code",
                    override_default_response_type: true,
                    extras: {
                        setup: {},
                    },
                },
            );
        });
    });

    async function exchangeCode(code, wabaId, phoneNumberId) {
        if (!wabaId || !phoneNumberId) {
            setStatus(
                "Meta terminó el proceso, pero no entregó WABA/phone_number_id.",
                true,
            );
            return;
        }

        setStatus("Conectando WhatsApp con Noxtium...");

        try {
            const response = await fetch(
                "/api/meta/embedded-signup",
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                    },
                    body: JSON.stringify({
                        code,
                        waba_id: wabaId,
                        phone_number_id: phoneNumberId,
                    }),
                },
            );

            const data = await response.json();

            if (!response.ok) {
                throw new Error(
                    data.error ||
                    "No fue posible completar la conexión.",
                );
            }

            setStatus(
                `WhatsApp conectado: ${data.display_phone_number || phoneNumberId}`,
            );
            console.log("NOXTIUM connection:", data);
        } catch (error) {
            console.error(error);
            setStatus(error.message, true);
        }
    }

    function setStatus(message, error = false) {
        const element = document.getElementById("whatsapp-status");
        if (!element) return;

        element.textContent = message;
        element.dataset.error = error ? "true" : "false";
    }
})();
