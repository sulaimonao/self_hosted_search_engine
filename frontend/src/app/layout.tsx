import type { Metadata } from "next";
import { Inter, Roboto_Mono } from "next/font/google";
import { SWRConfig } from "swr";

import { NavProgressProvider } from "@/app/nav-progress-provider";
import { RenderLoopGuardProvider } from "@/components/providers/RenderLoopGuardProvider";
import { StatusRibbon } from "@/components/status/StatusRibbon";
import { FirstRunWizard } from "@/components/setup/FirstRunWizard";

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
          <RenderLoopGuardProvider>
            <NavProgressProvider>
              <StatusRibbon />
              <FirstRunWizard />
              {children}
            </NavProgressProvider>
          </RenderLoopGuardProvider>
        </SWRConfig>
      </body>
    </html>
  );
}
