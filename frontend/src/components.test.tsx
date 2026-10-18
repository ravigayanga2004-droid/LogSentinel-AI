import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { Badge, Empty, ErrorState, Pager } from './components';
import { ThemeProvider, useTheme } from './context';

describe('accessible shared controls', () => {
  it('includes a text severity label', () => { render(<Badge value="critical" />); expect(screen.getByText('critical')).toBeVisible(); });
  it('explains empty data', () => { render(<Empty title="No matching events" description="Broaden your filters." />); expect(screen.getByText('Broaden your filters.')).toBeVisible(); });
  it('supports keyboard-operable pagination with bounds', () => { const change = vi.fn(); render(<Pager page={1} total={70} setPage={change} />); expect(screen.getByRole('button', { name: 'Previous page' })).toBeDisabled(); fireEvent.click(screen.getByRole('button', { name: 'Next page' })); expect(change).toHaveBeenCalledWith(2); });
  it('disables next on the final page', () => { render(<Pager page={3} total={70} setPage={vi.fn()} />); expect(screen.getByRole('button', { name: 'Next page' })).toBeDisabled(); });
  it('announces errors and allows retry', () => { const retry = vi.fn(); render(<ErrorState error={new Error('Connection unavailable')} retry={retry} />); expect(screen.getByRole('alert')).toHaveTextContent('Connection unavailable'); fireEvent.click(screen.getByRole('button', { name: 'Try again' })); expect(retry).toHaveBeenCalledOnce(); });
});
function ThemeControl() { const { theme, toggle } = useTheme(); return <button onClick={toggle}>{theme}</button>; }
describe('theme preferences', () => {
  it('defaults to dark and persists a switch to light', () => { render(<ThemeProvider><ThemeControl /></ThemeProvider>); fireEvent.click(screen.getByRole('button', { name: 'dark' })); expect(document.documentElement.dataset.theme).toBe('light'); expect(localStorage.getItem('ls_theme')).toBe('light'); });
  it('restores a saved light preference', () => { localStorage.setItem('ls_theme', 'light'); render(<ThemeProvider><ThemeControl /></ThemeProvider>); expect(screen.getByRole('button', { name: 'light' })).toBeVisible(); });
});
