import type { ReactNode } from 'react';
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Bell,
  BookOpenText,
  Brain,
  ChevronDown,
  ClipboardCheck,
  Compass,
  Database,
  GitBranch,
  LayoutDashboard,
  Menu,
  ScanSearch,
  Search,
  Settings2,
  ShieldCheck,
  Sparkles,
  LogOut,
  UserCircle2,
  X,
} from 'lucide-react';
import { NavLink, useNavigate } from 'react-router-dom';
import { NAV_ITEMS } from '@/app/routes';
import { useAuth } from '@/app/authContext';

interface AppNotification {
  id: string;
  title: string;
  detail: string;
  time: string;
  href?: string;
  read: boolean;
}

/** Application shell: persistent sidebar navigation plus the routed content area. */
export function Layout({ children }: { children: ReactNode }) {
  const { user, signOut } = useAuth();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const [notificationOpen, setNotificationOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const [notifications, setNotifications] = useState<AppNotification[]>([
    {
      id: 'n1',
      title: 'Lineage review queue updated',
      detail: '12 lineage edges need manual confirmation.',
      time: '2m ago',
      href: '/lineage',
      read: false,
    },
    {
      id: 'n2',
      title: '2 sensitive fields pending review',
      detail: 'Customer dataset has PII tags pending governance action.',
      time: '8m ago',
      href: '/pii-detection',
      read: false,
    },
    {
      id: 'n3',
      title: 'Daily quality scan completed',
      detail: '1 warning found in freshness checks.',
      time: '43m ago',
      href: '/trust-center',
      read: false,
    },
    {
      id: 'n4',
      title: '17 tables missing business definitions',
      detail: 'Suggested glossary updates are ready to review.',
      time: '1h ago',
      href: '/glossary',
      read: false,
    },
    {
      id: 'n5',
      title: 'Data source synced: Snowflake',
      detail: '2,341 table metadata objects were refreshed.',
      time: '2h ago',
      href: '/ingestion',
      read: false,
    },
    {
      id: 'n6',
      title: '5 lineage paths inferred by AI',
      detail: 'Verification required before production usage.',
      time: '3h ago',
      href: '/lineage',
      read: false,
    },
    {
      id: 'n7',
      title: 'Compliance policy updated',
      detail: 'Customer data retention policy now includes finance domain.',
      time: '5h ago',
      href: '/governance',
      read: false,
    },
    {
      id: 'n8',
      title: 'Copilot index refreshed',
      detail: 'Semantic retrieval quality improved for KPI questions.',
      time: '1d ago',
      href: '/copilot',
      read: false,
    },
  ]);
  const notificationRef = useRef<HTMLDivElement | null>(null);
  const accountRef = useRef<HTMLDivElement | null>(null);

  const iconMap = useMemo(
    () => ({
      'layout-dashboard': LayoutDashboard,
      compass: Compass,
      database: Database,
      'book-open-text': BookOpenText,
      'git-branch': GitBranch,
      'shield-check': ShieldCheck,
      badges: Brain,
      'scan-search': ScanSearch,
      'clipboard-check': ClipboardCheck,
      sparkles: Sparkles,
      'settings-2': Settings2,
    }),
    [],
  );

  const unreadCount = notifications.filter((item) => !item.read).length;
  const initials = (user?.name?.slice(0, 1) ?? 'A').toUpperCase();

  useEffect(() => {
    const onWindowClick = (event: MouseEvent) => {
      const target = event.target as Node;
      if (notificationRef.current && !notificationRef.current.contains(target)) {
        setNotificationOpen(false);
      }
      if (accountRef.current && !accountRef.current.contains(target)) {
        setAccountOpen(false);
      }
    };

    window.addEventListener('mousedown', onWindowClick);
    return () => window.removeEventListener('mousedown', onWindowClick);
  }, []);

  const markRead = (id: string) => {
    setNotifications((previous) =>
      previous.map((item) => (item.id === id ? { ...item, read: true } : item)),
    );
  };

  const markAllRead = () => {
    setNotifications((previous) => previous.map((item) => ({ ...item, read: true })));
  };

  const openNotification = (notification: AppNotification) => {
    markRead(notification.id);
    setNotificationOpen(false);
    if (notification.href) {
      navigate(notification.href);
    }
  };

  const onSignOut = () => {
    signOut();
    setAccountOpen(false);
  };

  return (
    <div className="app-shell">
      <aside className={`sidebar${menuOpen ? ' open' : ''}`}>
        <div className="brand-wrap">
          <div className="brand-mark" aria-hidden>
            <Sparkles size={16} />
          </div>
          <span className="brand">
            MetaMind AI
            <small>Enterprise Intelligence</small>
          </span>
          <button className="icon-button mobile-only" onClick={() => setMenuOpen(false)}>
            <X size={16} />
          </button>
        </div>

        <div className="sidebar-nav">
          {NAV_ITEMS.map((item) => {
            const Icon = iconMap[item.icon];
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                onClick={() => setMenuOpen(false)}
                className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
              >
                <Icon size={16} className="nav-icon" />
                {item.label}
              </NavLink>
            );
          })}
        </div>

        <div className="sidebar-footer">
          <button className="workspace-switch">
            <span className="faint small">Workspace</span>
            <strong>MetaMind AI</strong>
            <ChevronDown size={14} />
          </button>
          <div className="user-panel" ref={accountRef}>
            <button className="user-tile user-menu-trigger" onClick={() => setAccountOpen((open) => !open)}>
              <span className="avatar">{initials}</span>
              <div>
                <div>{user?.name ?? 'Admin'}</div>
                <div className="faint small">{user?.role ?? 'Platform Owner'}</div>
              </div>
              <ChevronDown size={14} className="faint" />
            </button>

            {accountOpen ? (
              <div className="account-menu">
                <div className="account-menu-header">
                  <div className="small faint">Signed in as</div>
                  <div className="mono small">{user?.email ?? 'admin@metamind.ai'}</div>
                </div>
                <button className="menu-item" onClick={() => navigate('/settings')}>
                  <UserCircle2 size={14} />
                  Account settings
                </button>
                <button className="menu-item danger" onClick={onSignOut}>
                  <LogOut size={14} />
                  Sign out
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </aside>

      <div className="content-shell">
        <header className="top-header">
          <div className="top-left">
            <button className="icon-button mobile-only" onClick={() => setMenuOpen(true)}>
              <Menu size={16} />
            </button>
            <div className="global-search">
              <Search size={15} />
              <input
                className="header-input"
                placeholder="Search anything, Ask MetaMind..."
                aria-label="Global search"
              />
              <span className="kbd">⌘ K</span>
            </div>
          </div>

          <div className="top-actions">
            <NavLink to="/copilot" className="copilot-cta">
              <Sparkles size={16} />
              Ask AI Copilot
            </NavLink>
            <div className="notification-wrap" ref={notificationRef}>
              <button
                className="icon-button notification-btn"
                aria-label="Notifications"
                onClick={() => setNotificationOpen((open) => !open)}
              >
                <Bell size={16} />
                {unreadCount > 0 ? <span className="notification-dot">{unreadCount}</span> : null}
              </button>

              {notificationOpen ? (
                <div className="notification-panel" role="dialog" aria-label="Notifications">
                  <div className="notification-header">
                    <strong>Notifications</strong>
                    <button className="button" onClick={markAllRead} disabled={unreadCount === 0}>
                      Mark all read
                    </button>
                  </div>
                  <div className="notification-list">
                    {notifications.map((item) => (
                      <button
                        key={item.id}
                        className={`notification-item${item.read ? '' : ' unread'}`}
                        onClick={() => openNotification(item)}
                      >
                        <div className="row">
                          <strong>{item.title}</strong>
                          <span className="faint small">{item.time}</span>
                        </div>
                        <div className="muted small">{item.detail}</div>
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}
            </div>
            <button className="avatar avatar-button" onClick={() => setAccountOpen((open) => !open)}>
              {initials}
            </button>
          </div>
        </header>

        <main className="main">{children}</main>
      </div>
    </div>
  );
}
