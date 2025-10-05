"use client";

import { useApp } from "@/app/shipit/store/useApp";

export default function BrowserPanel(): JSX.Element {
  const { shadow } = useApp();
  return (
    <div className="p-4 border rounded-2xl">
      Browser mode coming online… Shadow: {shadow ? "ON" : "OFF"}
    </div>
  );
}
