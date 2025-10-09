import { expect, test } from '@playwright/test';

const DEFAULT_TIMEOUT_MS = 120_000;
const POLL_INTERVAL_MS = 2_000;

test.describe('shadow crawl integration', () => {
  test('indexes fixture content and makes it searchable', async ({ request }) => {
    test.skip(process.env.CI === 'true', 'Shadow crawl e2e disabled on CI runners');

    const baseUrl = process.env.APP_BASE_URL ?? 'http://127.0.0.1:8000';
    const fixtureUrl = process.env.SHADOW_FIXTURE_URL;
    const fixturePhrase = process.env.SHADOW_FIXTURE_PHRASE;

    test.skip(!fixtureUrl || !fixturePhrase, 'Shadow crawl fixture not configured');

    const queueResponse = await request.post(`${baseUrl}/api/shadow/queue`, {
      data: { url: fixtureUrl },
    });
    expect(queueResponse.status(), 'queue request should succeed').toBeGreaterThanOrEqual(200);
    expect(queueResponse.status(), 'queue request should succeed').toBeLessThan(400);

    await expect
      .poll(
        async () => {
          const statusResponse = await request.get(`${baseUrl}/api/shadow/status`, {
            params: { url: fixtureUrl },
          });
          if (!statusResponse.ok()) {
            return 'pending';
          }
          const payload = await statusResponse.json();
          return payload?.phase ?? payload?.status ?? 'pending';
        },
        {
          timeout: DEFAULT_TIMEOUT_MS,
          message: 'Shadow crawl did not reach indexed state in time',
          interval: POLL_INTERVAL_MS,
        },
      )
      .toEqual('indexed');

    const searchResponse = await request.post(`${baseUrl}/api/search`, {
      data: { query: fixturePhrase, limit: 5 },
    });
    expect(searchResponse.ok(), 'search request should succeed').toBeTruthy();
    const searchPayload = await searchResponse.json();
    const hits = Array.isArray(searchPayload?.results) ? searchPayload.results : [];
    const matched = hits.some((hit: any) => {
      const text = `${hit?.title ?? ''} ${hit?.snippet ?? ''}`.toLowerCase();
      return text.includes(String(fixturePhrase).toLowerCase());
    });
    expect(matched, 'search results should include the fixture phrase').toBeTruthy();
  });
});
