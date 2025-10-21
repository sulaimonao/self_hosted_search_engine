function collectBrowserDiagnostics() {
  return (async () => {
    const result = {
      timestamp: Date.now(),
      userAgent: null,
      navigatorLanguage: null,
      navigatorLanguages: [],
      platform: null,
      uaCh: null,
      uaChError: null,
      uaData: null,
      uaDataError: null,
      webdriver: null,
      webdriverError: null,
      webgl: { vendor: null, renderer: null, error: null },
      cookies: { count: null, raw: null, error: null },
      serviceWorker: {
        supported: false,
        status: "unsupported",
        registrations: 0,
        scopes: [],
        error: null,
      },
    };

    try {
      result.userAgent = typeof navigator !== "undefined" && navigator.userAgent ? navigator.userAgent : null;
    } catch (error) {
      result.uaChError = String(error);
    }

    try {
      if (typeof navigator?.language === "string") {
        result.navigatorLanguage = navigator.language;
      }
      if (Array.isArray(navigator?.languages)) {
        result.navigatorLanguages = navigator.languages.slice();
      }
      if (typeof navigator?.platform === "string") {
        result.platform = navigator.platform;
      }
    } catch (error) {
      result.uaChError = result.uaChError ?? String(error);
    }

    try {
      if (navigator && typeof navigator.userAgentData !== "undefined" && navigator.userAgentData) {
        result.uaCh = typeof navigator.userAgentData.toJSON === "function" ? navigator.userAgentData.toJSON() : null;
        if (typeof navigator.userAgentData.getHighEntropyValues === "function") {
          try {
            result.uaData = await navigator.userAgentData.getHighEntropyValues([
              "platform",
              "platformVersion",
              "architecture",
              "model",
              "uaFullVersion",
            ]);
          } catch (error) {
            result.uaDataError = String(error);
          }
        }
      }
    } catch (error) {
      result.uaChError = String(error);
    }

    try {
      if (typeof navigator?.webdriver !== "undefined") {
        result.webdriver = navigator.webdriver;
      }
    } catch (error) {
      result.webdriverError = String(error);
    }

    try {
      const cookieString = document.cookie;
      if (typeof cookieString === "string") {
        result.cookies.raw = cookieString;
        if (!cookieString) {
          result.cookies.count = 0;
        } else {
          result.cookies.count = cookieString.split(";").filter(Boolean).length;
        }
      }
    } catch (error) {
      result.cookies.error = String(error);
    }

    try {
      const canvas = document.createElement("canvas");
      const gl = canvas.getContext("webgl") || canvas.getContext("experimental-webgl");
      if (gl) {
        const debugInfo = gl.getExtension("WEBGL_debug_renderer_info");
        if (debugInfo) {
          const vendor = gl.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL);
          const renderer = gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL);
          result.webgl.vendor = vendor || null;
          result.webgl.renderer = renderer || null;
        } else {
          result.webgl.vendor = gl.getParameter(gl.VENDOR) || null;
          result.webgl.renderer = gl.getParameter(gl.RENDERER) || null;
        }
      } else {
        result.webgl.error = "no_webgl_context";
      }
    } catch (error) {
      result.webgl.error = String(error);
    }

    try {
      if (navigator && "serviceWorker" in navigator) {
        result.serviceWorker.supported = true;
        if (navigator.serviceWorker?.getRegistrations) {
          const registrations = await navigator.serviceWorker.getRegistrations();
          result.serviceWorker.registrations = registrations.length;
          result.serviceWorker.scopes = registrations.map((registration) => registration.scope);
          result.serviceWorker.status = registrations.length > 0 ? "registered" : "not_registered";
        } else if (navigator.serviceWorker?.getRegistration) {
          const registration = await navigator.serviceWorker.getRegistration();
          if (registration) {
            result.serviceWorker.registrations = 1;
            result.serviceWorker.scopes = [registration.scope];
            result.serviceWorker.status = "registered";
          } else {
            result.serviceWorker.registrations = 0;
            result.serviceWorker.status = "not_registered";
          }
        } else {
          result.serviceWorker.status = "unknown";
        }
      }
    } catch (error) {
      result.serviceWorker.error = String(error);
    }

    return result;
  })();
}

const BROWSER_DIAGNOSTICS_SCRIPT = `(${collectBrowserDiagnostics.toString()})()`;

module.exports = { BROWSER_DIAGNOSTICS_SCRIPT };
