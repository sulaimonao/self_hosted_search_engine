import { CaptureSettingsForm } from "@/app/(shell)/settings/components/CaptureSettingsForm";
import { LlmSettingsForm } from "@/app/(shell)/settings/components/LlmSettingsForm";
import { PrivacySettingsSection } from "@/app/(shell)/settings/components/PrivacySettingsSection";
import { RetentionSettingsSection } from "@/app/(shell)/settings/components/RetentionSettingsSection";

export default function SettingsPage() {
  return (
    <div className="flex flex-1 flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold">Settings</h1>
        <p className="text-sm text-muted-foreground">Configure AI, capture, privacy, and retention.</p>
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <LlmSettingsForm />
        <CaptureSettingsForm />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <PrivacySettingsSection />
        <RetentionSettingsSection />
      </div>
    </div>
  );
}
