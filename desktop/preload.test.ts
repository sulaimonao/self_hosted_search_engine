import { beforeAll, describe, expect, it, vi } from 'vitest';

const exposeInMainWorld = vi.fn();
const ipcRenderer = {
  on: vi.fn(),
  removeListener: vi.fn(),
  send: vi.fn(),
  invoke: vi.fn(() => Promise.resolve()),
};

vi.mock('electron', () => ({
  contextBridge: { exposeInMainWorld },
  ipcRenderer,
}));

beforeAll(() => {
  Object.defineProperty(globalThis, 'navigator', {
    configurable: true,
    value: {},
  });
});

describe('preload bridge', () => {
  it('exposes desktop and browser APIs', async () => {
    vi.resetModules();
    await import('./preload');

    expect(exposeInMainWorld).toHaveBeenCalledWith(
      'desktop',
      expect.objectContaining({
        runSystemCheck: expect.any(Function),
        onSystemCheckEvent: expect.any(Function),
      }),
    );

    expect(exposeInMainWorld).toHaveBeenCalledWith(
      'browserAPI',
      expect.objectContaining({
        navigate: expect.any(Function),
        goBack: expect.any(Function),
        onNavState: expect.any(Function),
      }),
    );
  });
});
