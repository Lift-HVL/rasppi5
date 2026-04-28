import { NavLink } from 'react-router';

const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', end: true },
  { to: '/telemetry', label: 'Telemetry', end: false },
  { to: '/logs', label: 'Logs', end: false },
  { to: '/settings', label: 'Settings', end: false },
];

export function Navbar() {
  return (
    <header className="sticky top-0 z-50 border-b border-gray-800 bg-gray-950/95 backdrop-blur">
      <div className="flex h-12 items-center gap-6 px-4">
        <div className="flex items-center gap-2 select-none">
          <span className="text-lg">🚁</span>
          <span className="font-semibold text-gray-100 text-sm tracking-wide">
            HVL Lift <span className="text-gray-500 font-normal">Ground Station</span>
          </span>
        </div>

        <nav className="flex items-center gap-1 ml-4">
          {NAV_ITEMS.map(({ to, label, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `px-3 py-1.5 rounded text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-gray-800 text-gray-100'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-gray-900'
                }`
              }
            >
              {label}
            </NavLink>
          ))}
        </nav>
      </div>
    </header>
  );
}
