import type { ReactNode } from 'react';
import { NavLink } from 'react-router-dom';
import { NAV_ITEMS } from '@/app/routes';

/** Application shell: persistent sidebar navigation plus the routed content area. */
export function Layout({ children }: { children: ReactNode }) {
  const sections = [...new Set(NAV_ITEMS.map((item) => item.section))];

  return (
    <div className="app-shell">
      <nav className="sidebar">
        <span className="brand">
          Metadata Copilot
          <small>Enterprise</small>
        </span>

        {sections.map((section) => (
          <div key={section}>
            <div className="nav-section">{section}</div>
            {NAV_ITEMS.filter((item) => item.section === section).map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
              >
                <span aria-hidden>{item.icon}</span>
                {item.label}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>

      <main className="main">{children}</main>
    </div>
  );
}
