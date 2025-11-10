import type { Metadata } from "next";
import { Inter, Roboto_Mono } from "next/font/google";
import { SWRConfig } from "swr";
import "katex/dist/katex.min.css";
import "highlight.js/styles/github.css";

import ClientOnly from "@/components/ClientOnly";
import { NavProgressProvider } from "@/app/nav-progress-provider";
import { RenderLoopGuardProvider } from "@/components/providers/RenderLoopGuardProvider";
import { StatusRibbon } from "@/components/status/StatusRibbon";
import { FirstRunWizard } from "@/components/setup/FirstRunWizard";
import ErrorBoundary from "@/components/ErrorBoundary";
import ErrorClientSetup from "@/components/ErrorClientSetup";

import "./globals.css";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

const robotoMono = Roboto_Mono({
  variable: "--font-roboto-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Self Hosted Copilot",
  description: "Chat-driven UI for the self-hosted search engine",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${inter.variable} ${robotoMono.variable} antialiased`}>
        <SWRConfig
          value={{
            revalidateOnFocus: false,
            revalidateOnReconnect: false,
            dedupingInterval: 4000,
          }}
        >
          {/* The ClientOnly wrapper prevents hydration mismatches and excessive render loops by waiting
             until the component mounts on the client before rendering children. */}
          <ClientOnly>
            <RenderLoopGuardProvider>
              <NavProgressProvider>
                <ErrorBoundary>
                  <ErrorClientSetup />
                  <StatusRibbon />
                  <FirstRunWizard />
                  {children}
                </ErrorBoundary>
              </NavProgressProvider>
            </RenderLoopGuardProvider>
          </ClientOnly>
        </SWRConfig>
      </body>
    </html>
  );
}
