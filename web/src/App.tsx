import { Routes, Route, Link, useLocation } from 'react-router-dom';
import { Activity, Database, BookOpen, Network, MessageSquare } from 'lucide-react';
import Status from './pages/Status';
import Corpus from './pages/Corpus';
import Wiki from './pages/Wiki';
import Graph from './pages/Graph';
import Query from './pages/Query';

function Sidebar() {
  const location = useLocation();
  
  const navItems = [
    { path: '/', icon: Activity, label: 'Status' },
    { path: '/corpus', icon: Database, label: 'Corpus' },
    { path: '/wiki', icon: BookOpen, label: 'Wiki' },
    { path: '/graph', icon: Network, label: 'Graph' },
    { path: '/query', icon: MessageSquare, label: 'Query' },
  ];

  return (
    <div className="w-64 bg-card border-r border-border min-h-screen">
      <div className="p-6 border-b border-border">
        <h1 className="text-xl font-bold text-foreground">Biblioteca</h1>
        <p className="text-xs text-muted-foreground mt-1">Battery Research OS</p>
      </div>
      <nav className="p-4 space-y-1">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = location.pathname === item.path;
          return (
            <Link
              key={item.path}
              to={item.path}
              className={`flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors ${
                isActive
                  ? 'bg-accent text-accent-foreground'
                  : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
              }`}
            >
              <Icon className="w-4 h-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}

function App() {
  return (
    <div className="flex bg-background min-h-screen">
      <Sidebar />
      <main className="flex-1 p-8 overflow-auto">
        <Routes>
          <Route path="/" element={<Status />} />
          <Route path="/corpus" element={<Corpus />} />
          <Route path="/wiki" element={<Wiki />} />
          <Route path="/graph" element={<Graph />} />
          <Route path="/query" element={<Query />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;
