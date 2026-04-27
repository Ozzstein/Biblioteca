import { useEffect, useState } from 'react';
import { BookOpen, Search } from 'lucide-react';

interface WikiStats {
  total_pages: number;
  pages_by_category: Record<string, number>;
  recent_pages: Array<{
    title: string;
    category: string;
    path: string;
  }>;
}

interface WikiPage {
  title: string;
  category: string;
  path: string;
}

export default function Wiki() {
  const [stats, setStats] = useState<WikiStats | null>(null);
  const [pages, setPages] = useState<WikiPage[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetch('/api/wiki/stats').then((res) => res.json()),
      fetch('/api/wiki/pages').then((res) => res.json()),
    ])
      .then(([statsData, pagesData]) => {
        setStats(statsData);
        setPages(pagesData);
        setLoading(false);
      })
      .catch((err) => {
        console.error('Failed to fetch wiki data:', err);
        setLoading(false);
      });
  }, []);

  const filteredPages = pages.filter(
    (page) =>
      page.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      page.category.toLowerCase().includes(searchQuery.toLowerCase())
  );

  if (loading) {
    return <div className="text-muted-foreground">Loading...</div>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-3xl font-bold text-foreground">Wiki</h2>
        <p className="text-muted-foreground mt-1">Knowledge base browser</p>
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        <div className="bg-card rounded-lg border border-border p-6 md:col-span-2">
          <p className="text-sm text-muted-foreground">Total Pages</p>
          <p className="text-2xl font-bold mt-1 text-foreground">{stats?.total_pages || 0}</p>
        </div>
        <div className="bg-card rounded-lg border border-border p-6 md:col-span-2">
          <p className="text-sm text-muted-foreground">Categories</p>
          <p className="text-2xl font-bold mt-1 text-foreground">
            {Object.keys(stats?.pages_by_category || {}).length}
          </p>
        </div>
      </div>

      <div className="bg-card rounded-lg border border-border">
        <div className="p-6 border-b border-border">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-semibold text-foreground">Browse Pages</h3>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <input
                type="text"
                placeholder="Search pages..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9 pr-4 py-2 bg-background border border-border rounded-md text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>
          </div>
        </div>

        <div className="max-h-[600px] overflow-auto">
          <div className="divide-y divide-border">
            {filteredPages.length ? (
              filteredPages.map((page) => (
                <div
                  key={page.path}
                  className="p-4 hover:bg-accent/50 transition-colors cursor-pointer"
                >
                  <div className="flex items-center gap-3">
                    <BookOpen className="w-5 h-5 text-muted-foreground" />
                    <div>
                      <p className="text-sm font-medium text-foreground">{page.title}</p>
                      <p className="text-xs text-muted-foreground">{page.category}</p>
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div className="p-8 text-center text-muted-foreground">
                {searchQuery ? 'No pages match your search' : 'No pages yet'}
              </div>
            )}
          </div>
        </div>
      </div>

      {stats?.pages_by_category && Object.keys(stats.pages_by_category).length > 0 && (
        <div className="bg-card rounded-lg border border-border p-6">
          <h3 className="text-lg font-semibold text-foreground mb-4">Pages by Category</h3>
          <div className="grid gap-3 md:grid-cols-3">
            {Object.entries(stats.pages_by_category).map(([category, count]) => (
              <div
                key={category}
                className="flex items-center justify-between p-3 bg-background rounded-md"
              >
                <span className="text-sm text-foreground capitalize">{category}</span>
                <span className="text-sm font-medium text-muted-foreground">{count}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
