export function ShellLayoutGrid({ children }: { children: React.ReactNode }) {
  return (
    <main className="flex-1 overflow-y-auto px-4 py-6 lg:px-8">
      <div className="mx-auto flex h-full max-w-6xl flex-col gap-8">{children}</div>
    </main>
  );
}
