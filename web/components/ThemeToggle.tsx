'use client';

import { useEffect, useState } from 'react';

type Theme = 'light' | 'dark' | 'system';

/** Cycles the three states the stylesheet handles: explicit light, explicit dark,
 *  and unset (follow the system). */
export default function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>('system');

  useEffect(() => {
    const stored = localStorage.getItem('ae-theme');
    if (stored === 'light' || stored === 'dark') setTheme(stored);
  }, []);

  function apply(next: Theme) {
    setTheme(next);
    if (next === 'system') {
      localStorage.removeItem('ae-theme');
      document.documentElement.removeAttribute('data-theme');
    } else {
      localStorage.setItem('ae-theme', next);
      document.documentElement.setAttribute('data-theme', next);
    }
  }

  const next: Theme = theme === 'system' ? 'light' : theme === 'light' ? 'dark' : 'system';

  return (
    <button
      type="button"
      onClick={() => apply(next)}
      className="pill mute"
      style={{ background: 'none', cursor: 'pointer' }}
      aria-label={`Theme: ${theme}. Switch to ${next}.`}
    >
      {theme}
    </button>
  );
}
