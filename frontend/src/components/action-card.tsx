export function ActionCard() {
  return (
    <div className="p-4 border rounded-lg">
      <p>Action Card</p>
      <div className="flex justify-end gap-2 mt-2">
        <button className="px-4 py-2 rounded-md bg-primary text-primary-foreground">Approve</button>
        <button className="px-4 py-2 rounded-md border">Dismiss</button>
      </div>
    </div>
  );
}