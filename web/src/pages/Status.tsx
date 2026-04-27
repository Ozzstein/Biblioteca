import { useEffect, useState } from 'react';
import { Activity, CheckCircle, AlertCircle, Clock, FileText } from 'lucide-react';

interface SystemStatus {
  status: string;
  supervisor_running: boolean;
  supervisor_pid?: number;
  health: string;
  last_heartbeat?: string;
  files_processed: number;
  error_rate: number;
  pending_files: number;
}

export default function Status() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/status')
      .then((res) => res.json())
      .then((data) => {
        setStatus(data);
        setLoading(false);
      })
      .catch((err) => {
        console.error('Failed to fetch status:', err);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return <div className="text-muted-foreground">Loading...</div>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-3xl font-bold text-foreground">System Status</h2>
        <p className="text-muted-foreground mt-1">Real-time overview of your Biblioteca instance</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatusCard
          title="Supervisor"
          value={status?.supervisor_running ? 'Running' : 'Stopped'}
          icon={status?.supervisor_running ? CheckCircle : AlertCircle}
          variant={status?.supervisor_running ? 'success' : 'warning'}
        />
        <StatusCard
          title="Health"
          value={status?.health || 'unknown'}
          icon={Activity}
          variant={status?.health === 'healthy' ? 'success' : 'warning'}
        />
        <StatusCard
          title="Files Processed"
          value={status?.files_processed?.toString() || '0'}
          icon={FileText}
        />
        <StatusCard
          title="Pending Files"
          value={status?.pending_files?.toString() || '0'}
          icon={Clock}
          variant={status?.pending_files ? 'warning' : 'success'}
        />
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="bg-card rounded-lg border border-border p-6">
          <h3 className="text-lg font-semibold text-foreground mb-4">Supervisor Details</h3>
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between">
              <dt className="text-muted-foreground">PID</dt>
              <dd className="text-foreground font-mono">{status?.supervisor_pid || 'N/A'}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted-foreground">Error Rate</dt>
              <dd className="text-foreground">{(status?.error_rate || 0).toFixed(2)}%</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted-foreground">Last Heartbeat</dt>
              <dd className="text-foreground">
                {status?.last_heartbeat
                  ? new Date(status.last_heartbeat).toLocaleString()
                  : 'N/A'}
              </dd>
            </div>
          </dl>
        </div>

        <div className="bg-card rounded-lg border border-border p-6">
          <h3 className="text-lg font-semibold text-foreground mb-4">Quick Actions</h3>
          <div className="space-y-2">
            <button className="w-full px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm hover:opacity-90 transition-opacity">
              Start Supervisor
            </button>
            <button className="w-full px-4 py-2 bg-secondary text-secondary-foreground rounded-md text-sm hover:opacity-90 transition-opacity">
              Refresh Status
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function StatusCard({
  title,
  value,
  icon: Icon,
  variant = 'default',
}: {
  title: string;
  value: string;
  icon: React.ComponentType<{ className?: string }>;
  variant?: 'default' | 'success' | 'warning';
}) {
  const variants = {
    default: 'text-foreground',
    success: 'text-green-500',
    warning: 'text-yellow-500',
  };

  return (
    <div className="bg-card rounded-lg border border-border p-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-muted-foreground">{title}</p>
          <p className={`text-2xl font-bold mt-1 ${variants[variant]}`}>{value}</p>
        </div>
        <Icon className={`w-8 h-8 ${variants[variant]}`} />
      </div>
    </div>
  );
}
