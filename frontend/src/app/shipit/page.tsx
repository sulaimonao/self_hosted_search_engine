"use client";

import { useEffect } from "react";

import HeaderBar from "./components/HeaderBar";
import FirstRunWizard from "./components/FirstRunWizard";
import SearchPanel from "./components/SearchPanel";
import BrowserPanel from "./components/BrowserPanel";
import { useApp } from "@/app/shipit/store/useApp";
import { fetchServerTime } from "@/lib/api";

export default function Page(): JSX.Element {
  const { mode, setFeature, autopilot, setAutopilot } = useApp();

  useEffect(() => {
    let cancelled = false;
    fetchServerTime()
      .then(() => {
        if (!cancelled) {
          setFeature("serverTime", "available");
        }
      })
      .catch(() => {
        if (!cancelled) {
          setFeature("serverTime", "unavailable");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [setFeature]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const stored = window.localStorage.getItem("shipit:autopilot");
    if (stored !== null) {
      setAutopilot(stored === "1");
    }
  }, [setAutopilot]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    window.localStorage.setItem("shipit:autopilot", autopilot ? "1" : "0");
  }, [autopilot]);

  return (
    <main className="p-6 space-y-4">
      <HeaderBar />
      <FirstRunWizard />
      <div className="mt-4">{mode === "search" ? <SearchPanel /> : <BrowserPanel />}</div>
    </main>
  );
}
