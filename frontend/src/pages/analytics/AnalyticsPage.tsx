import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { useInsights, useRequesterBreakdown, useTrends, useUtilization } from '@/hooks/queries'
import { PageHeader, Skeleton } from '@/components/ui/Misc'
import { Card, CardHeader } from '@/components/ui/Card'
import { cn } from '@/lib/utils'

const BRAND = '#4f46e5'
const SOFT = '#e0e7ff'
const MUTED = '#9ca3af'
const GRID = '#e5e7eb'

export function AnalyticsPage() {
  const { data: utilization } = useUtilization(30)
  const { data: trends } = useTrends(6)
  const { data: insights } = useInsights()
  const { data: breakdown } = useRequesterBreakdown(365)

  const peakData = (insights?.peak_periods ?? []).slice(0, 8).map((period) => ({
    hour: `${String(period.hour).padStart(2, '0')}:00`,
    count: period.count,
  }))

  return (
    <div>
      <PageHeader
        eyebrow="SAS Analytics"
        title="Analytics"
        description="Understand how facilities and equipment are being used across the campus."
      />

      {/* Key metrics */}
      <div className="mt-8 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <MetricCard label="Campus reservations" value={breakdown?.campus ?? null} tone="text-brand" />
        <MetricCard
          label="External reservations"
          value={breakdown?.external ?? null}
          tone="text-status-maintenance"
        />
        <MetricCard label="Facility utilization" value={utilization?.facility.overall ?? null} suffix="%" tone="text-brand" />
        <MetricCard label="Equipment utilization" value={utilization?.equipment.overall ?? null} suffix="%" tone="text-status-approved" />
        <MetricCard label="Cancellation rate" value={insights?.cancellation_rate ?? null} suffix="%" tone="text-status-pending" />
        <MetricCard label="No-show rate" value={insights?.no_show_rate ?? null} suffix="%" tone="text-status-rejected" />
      </div>

      {/* Trends + peak hours */}
      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title="Reservation trends" description="New reservations per month — last 6 months" />
          <div className="mt-5 h-64">
            {trends ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={trends} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
                  <defs>
                    <linearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={BRAND} stopOpacity={0.16} />
                      <stop offset="100%" stopColor={BRAND} stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke={GRID} vertical={false} />
                  <XAxis dataKey="label" tick={{ fill: MUTED, fontSize: 12 }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fill: MUTED, fontSize: 12 }} axisLine={false} tickLine={false} allowDecimals={false} />
                  <Tooltip
                    cursor={{ stroke: SOFT }}
                    contentStyle={{
                      borderRadius: 12,
                      border: `1px solid ${GRID}`,
                      boxShadow: '0 8px 24px rgba(16,24,40,.1)',
                      fontSize: 13,
                    }}
                  />
                  <Area type="monotone" dataKey="total" stroke={BRAND} strokeWidth={2} fill="url(#trendFill)" />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <Skeleton className="h-full" />
            )}
          </div>
        </Card>

        <Card>
          <CardHeader title="Peak reservation periods" description="When requests usually start" />
          <div className="mt-5 h-64">
            {peakData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={peakData} margin={{ top: 4, right: 8, left: -18, bottom: 0 }}>
                  <CartesianGrid stroke={GRID} vertical={false} />
                  <XAxis dataKey="hour" tick={{ fill: MUTED, fontSize: 11 }} axisLine={false} tickLine={false} interval={1} />
                  <YAxis tick={{ fill: MUTED, fontSize: 12 }} axisLine={false} tickLine={false} allowDecimals={false} />
                  <Tooltip
                    cursor={{ fill: '#f8fafc' }}
                    contentStyle={{
                      borderRadius: 12,
                      border: `1px solid ${GRID}`,
                      boxShadow: '0 8px 24px rgba(16,24,40,.1)',
                      fontSize: 13,
                    }}
                  />
                  <Bar dataKey="count" radius={[6, 6, 0, 0]} maxBarSize={28}>
                    {peakData.map((entry, index) => (
                      <Cell key={entry.hour} fill={index === 0 ? BRAND : SOFT} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <Skeleton className="h-full" />
            )}
          </div>
        </Card>
      </div>

      {/* Utilization + most requested */}
      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card>
          <CardHeader title="Facility utilization" description="Booked share of operating hours — 30 days" />
          <div className="mt-5 space-y-4">
            {(utilization?.facility.facilities ?? []).slice(0, 6).map((facility) => (
              <div key={facility.facility_id}>
                <div className="mb-1.5 flex items-baseline justify-between gap-3">
                  <p className="truncate text-sm font-medium text-ink">{facility.name}</p>
                  <p className="shrink-0 text-[13px] tabular-nums text-body">{facility.utilization}%</p>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-softer">
                  <div
                    className={cn(
                      'h-full rounded-full',
                      facility.utilization > 75
                        ? 'bg-status-pending'
                        : facility.utilization > 40
                          ? 'bg-brand'
                          : 'bg-status-available',
                    )}
                    style={{ width: `${Math.min(facility.utilization, 100)}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <CardHeader title="Equipment utilization" description="Reserved share of each pool" />
          <div className="mt-5 space-y-4">
            {(utilization?.equipment.items ?? []).slice(0, 6).map((item) => (
              <div key={item.equipment_id}>
                <div className="mb-1.5 flex items-baseline justify-between gap-3">
                  <p className="truncate text-sm font-medium text-ink">{item.name}</p>
                  <p className="shrink-0 text-[13px] tabular-nums text-body">
                    {item.reserved}/{item.total}
                  </p>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-softer">
                  <div
                    className={cn(
                      'h-full rounded-full',
                      item.utilization > 75
                        ? 'bg-status-pending'
                        : item.utilization > 40
                          ? 'bg-brand'
                          : 'bg-status-available',
                    )}
                    style={{ width: `${Math.min(item.utilization, 100)}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <CardHeader
            title="External facility usage"
            description="External organizations served per facility — last 365 days"
          />
          {(breakdown?.external_facility_usage ?? []).length === 0 ? (
            <p className="mt-4 text-sm text-muted">No external reservations in this period.</p>
          ) : (
            <ol className="mt-4 space-y-1.5">
              {(breakdown?.external_facility_usage ?? []).slice(0, 6).map((row) => (
                <li key={row.facility} className="flex items-center gap-3 text-sm">
                  <span className="flex-1 truncate font-medium text-ink">{row.facility}</span>
                  <span className="shrink-0 tabular-nums text-body">{row.count}</span>
                </li>
              ))}
            </ol>
          )}
        </Card>

        <Card>
          <CardHeader title="Most requested" description="Top facilities and equipment" />
          <div className="mt-4 space-y-5">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-muted">Facilities</p>
              <ol className="mt-2 space-y-1.5">
                {(insights?.most_requested.facilities ?? []).map((facility, index) => (
                  <li key={facility.facility__name} className="flex items-center gap-3 text-sm">
                    <span className="w-4 shrink-0 text-xs font-semibold tabular-nums text-muted">{index + 1}</span>
                    <span className="flex-1 truncate font-medium text-ink">{facility.facility__name}</span>
                    <span className="shrink-0 tabular-nums text-body">{facility.count}</span>
                  </li>
                ))}
              </ol>
            </div>
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.1em] text-muted">Equipment</p>
              <ol className="mt-2 space-y-1.5">
                {(insights?.most_requested.equipment ?? []).map((item, index) => (
                  <li key={item.equipment__name} className="flex items-center gap-3 text-sm">
                    <span className="w-4 shrink-0 text-xs font-semibold tabular-nums text-muted">{index + 1}</span>
                    <span className="flex-1 truncate font-medium text-ink">{item.equipment__name}</span>
                    <span className="shrink-0 tabular-nums text-body">{item.quantity}×</span>
                  </li>
                ))}
              </ol>
            </div>
          </div>
        </Card>
      </div>
    </div>
  )
}

function MetricCard({
  label,
  value,
  suffix = '',
  tone,
}: {
  label: string
  value: number | null
  suffix?: string
  tone: string
}) {
  return (
    <div className="card p-5">
      {value === null ? (
        <Skeleton className="h-8 w-16" />
      ) : (
        <p className={cn('text-[26px] font-semibold leading-none tabular-nums tracking-tight', tone)}>
          {value}
          <span className="ml-0.5 text-base font-medium text-muted">{suffix}</span>
        </p>
      )}
      <p className="mt-2 text-[13px] text-body">{label}</p>
    </div>
  )
}