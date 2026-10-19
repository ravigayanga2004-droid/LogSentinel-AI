import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, expect, it, vi } from 'vitest';
import { useSession } from './context';

afterEach(() => vi.unstubAllGlobals());
function SessionProbe() {
  const session = useSession();
  return <div>{session.data ? 'Session ready' : 'Loading'}</div>;
}
function mount() {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ id: 'user', workspaces: [{ id: 'allowed-a' }, { id: 'allowed-b' }] }),
    }),
  );
  render(
    <QueryClientProvider client={new QueryClient()}>
      <SessionProbe />
    </QueryClientProvider>,
  );
}
it('repairs a stale workspace selection before authenticated pages load', async () => {
  localStorage.setItem('ls_workspace', 'revoked-workspace');
  mount();
  await screen.findByText('Session ready');
  expect(localStorage.getItem('ls_workspace')).toBe('allowed-a');
});
it('preserves a valid workspace selection on session refresh', async () => {
  localStorage.setItem('ls_workspace', 'allowed-b');
  mount();
  await screen.findByText('Session ready');
  expect(localStorage.getItem('ls_workspace')).toBe('allowed-b');
});
