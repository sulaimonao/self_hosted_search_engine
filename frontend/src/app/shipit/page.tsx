"use client";

import HeaderBar from "./components/HeaderBar";
import FirstRunWizard from "./components/FirstRunWizard";
import SearchPanel from "./components/SearchPanel";
import BrowserPanel from "./components/BrowserPanel";
import { useApp } from "@/app/shipit/store/useApp";

export default function Page(): JSX.Element {
  const { mode } = useApp();
  return (
    <main className="p-6 space-y-4">
      <HeaderBar />
      <FirstRunWizard />
      <div className="mt-4">{mode === "search" ? <SearchPanel /> : <BrowserPanel />}</div>
    </main>
  );
}
