import {
  scanDomForBanner,
  installConsoleDetector,
  installNetworkDetector,
  IncidentSymptoms,
} from "./detectors";

export type BrowserIncident = {
  id: string;
  url: string;
  ts: number;
  context: "browser";
  symptoms: IncidentSymptoms;
  domSnippet?: string;
};

export class IncidentBus {
  private consoleErrors: string[] = [];
  private networkErrors: { url: string; status?: number; error?: string }[] = [];
  private lastBannerText?: string;

  start() {
    installConsoleDetector((m) => {
      this.consoleErrors.push(m);
      if (this.consoleErrors.length > 20) {
        this.consoleErrors.shift();
      }
    });
    installNetworkDetector((e) => {
      this.networkErrors.push(e);
      if (this.networkErrors.length > 20) {
        this.networkErrors.shift();
      }
    });
  }

  snapshot(): BrowserIncident {
    const bannerText = scanDomForBanner();
    this.lastBannerText = bannerText || this.lastBannerText;
    const domEl = document.querySelector(
      '[role="alert"], .toast, .error, .alert-error',
    ) as HTMLElement | null;
    const domSnippet = domEl ? domEl.outerHTML.slice(0, 4000) : undefined;
    return {
      id: crypto.randomUUID(),
      url: location.href,
      ts: Date.now(),
      context: "browser",
      symptoms: {
        bannerText: this.lastBannerText || bannerText,
        consoleErrors: [...this.consoleErrors],
        networkErrors: [...this.networkErrors],
      },
      domSnippet,
    };
  }
}
