import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render } from '@testing-library/react';
import React from 'react';

import * as logging from '@/lib/logging';
import ErrorClientSetup from '@/components/ErrorClientSetup';
import ErrorBoundary from '@/components/ErrorBoundary';

vi.stubGlobal('fetch', vi.fn());

describe('telemetry helpers', () => {
  beforeEach(() => {
    // ensure a controllable fetch mock exists (simple Response-like object)
  // ensure a controllable fetch mock exists (simple Response-like object)
  globalThis.fetch = vi.fn(() => Promise.resolve(new Response(JSON.stringify({ ok: true }), { status: 200 })));
  // ensure no bridge by default
  const maybeWin = window as unknown as { appLogger?: unknown };
  delete maybeWin.appLogger;
  });

  afterEach(() => {
    vi.resetAllMocks();
  });

  it('sendUiLog uses window.appLogger when present', async () => {
  const spy = vi.fn();
  const maybeWin = window as unknown as { appLogger?: { log: (...args: unknown[]) => void } };
  maybeWin.appLogger = { log: spy };
  await logging.sendUiLog({ event: 'ui.test', level: 'INFO', msg: 'hello' });
    expect(spy).toHaveBeenCalledWith(expect.objectContaining({ event: 'ui.test' }));
  });

  it('sendUiLog falls back to fetch when no bridge', async () => {
    // ensure bridge removed
  const maybeWin = window as unknown as { appLogger?: unknown };
  maybeWin.appLogger = undefined;
  await logging.sendUiLog({ event: 'ui.test', level: 'INFO', msg: 'hello' });
  expect(globalThis.fetch).toHaveBeenCalled();
  });

  it('ErrorClientSetup registers handlers and sends logs on error', async () => {
    render(<ErrorClientSetup />);
    const err = new Error('boom');
    // dispatch window error
    const event = new ErrorEvent('error', { error: err, message: 'boom' });
  window.dispatchEvent(event);
  expect(globalThis.fetch).toHaveBeenCalled();
  });

  it('ErrorBoundary logs when child throws during render', () => {
    // spy on the imported sendUiLog to ensure ErrorBoundary calls it
    const spy = vi.spyOn(logging, 'sendUiLog');
    const Bomb = () => {
      throw new Error('boom');
    };
    render(
      <ErrorBoundary>
        <Bomb />
      </ErrorBoundary>
    );
    expect(spy).toHaveBeenCalled();
  });
});
