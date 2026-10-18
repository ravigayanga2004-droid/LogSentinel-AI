import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError, params } from './api';

afterEach(() => vi.unstubAllGlobals());
describe('API transport', () => {
  it('encodes filters and omits empty parameters', () => {
    expect(params({ q: 'a & b', source: '', anomaly: false, page: 2 })).toBe('q=a+%26+b&page=2');
  });
  it('sends workspace and csrf tokens with mutations', async () => {
    localStorage.setItem('ls_workspace', 'workspace-1');
    document.cookie = 'ls_csrf=csrf-value';
    const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: true }) });
    vi.stubGlobal('fetch', fetcher);
    await api('/sources', 'POST', { name: 'test' });
    expect(fetcher).toHaveBeenCalledWith(
      '/api/sources',
      expect.objectContaining({
        headers: expect.objectContaining({
          'x-workspace-id': 'workspace-1',
          'x-csrf-token': 'csrf-value',
        }),
      }),
    );
  });
  it('surfaces safe validation errors', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue({
          ok: false,
          status: 422,
          json: async () => ({ detail: [{ field: 'body.name', message: 'Required' }] }),
        }),
    );
    await expect(api('/sources')).rejects.toThrow('body.name: Required');
  });
  it('identifies expired authentication', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue({
          ok: false,
          status: 401,
          json: async () => ({ detail: 'Please sign in' }),
        }),
    );
    await expect(api('/auth/me')).rejects.toBeInstanceOf(ApiError);
  });
});
