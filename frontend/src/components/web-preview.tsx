export function WebPreview() {
  return (
    <div className="flex flex-col h-full bg-muted/20">
      <div className="flex items-center p-2 border-b">
        <input
          type="text"
          placeholder="https://example.com"
          className="flex-1 p-2 border rounded-md"
        />
      </div>
      <div className="flex-1 p-4">
        <p>Web Preview</p>
      </div>
    </div>
  );
}