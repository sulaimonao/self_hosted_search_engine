export function SettingsModels() {
  return (
    <div>
      <h3 className="font-semibold">Model Selection</h3>
      <div className="mt-2">
        <label htmlFor="chat-model" className="block">Chat Model</label>
        <select id="chat-model" className="w-full p-2 border rounded-md">
          <option>gpt-oss</option>
          <option>Gemma3</option>
        </select>
      </div>
      <div className="mt-2">
        <label htmlFor="embedding-model" className="block">Embedding Model</label>
        <select id="embedding-model" className="w-full p-2 border rounded-md">
          <option>embeddinggemma</option>
        </select>
      </div>
    </div>
  );
}