import { useState } from 'react'
import {
  ArrowLeft,
  Building2,
  CalendarX2,
  Download,
  FileSpreadsheet,
  FileText,
  Package,
  Printer,
  Users,
  Wrench,
} from 'lucide-react'
import { useReport, useReports } from '@/hooks/queries'
import { PageHeader, Skeleton, EmptyState } from '@/components/ui/Misc'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Form'
import { downloadFile } from '@/lib/utils'
import { cn } from '@/lib/utils'
import type { ReportDefinition } from '@/lib/types'

const reportIcons: Record<string, React.ReactNode> = {
  reservations: <FileText className="size-5" />,
  'facility-utilization': <Building2 className="size-5" />,
  equipment: <Package className="size-5" />,
  maintenance: <Wrench className="size-5" />,
  organizations: <Users className="size-5" />,
  'no-show': <CalendarX2 className="size-5" />,
}

export function ReportsPage() {
  const { data: reports, isLoading } = useReports()
  const [selected, setSelected] = useState<ReportDefinition | null>(null)
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')

  const range = { from: from || undefined, to: to || undefined }
  const { data: detail } = useReport(selected?.slug ?? null, range)

  if (selected && detail) {
    return (
      <ReportDetailView
        definition={selected}
        detail={detail}
        range={range}
        onBack={() => setSelected(null)}
      />
    )
  }

  return (
    <div>
      <PageHeader
        eyebrow="SAS Reports"
        title="Reports"
        description="Generate and export institutional reports from live reservation data."
      />

      <div className="mt-8 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {isLoading &&
          Array.from({ length: 6 }).map((_, index) => <Skeleton key={index} className="h-36" />)}

        {(reports ?? []).map((report) => (
          <button
            key={report.slug}
            onClick={() => {
              setSelected(report)
              setFrom('')
              setTo('')
            }}
            className="card card-hover group flex items-start gap-4 p-5 text-left"
          >
            <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-brand-soft text-brand transition-colors group-hover:bg-brand group-hover:text-white">
              {reportIcons[report.slug] ?? <FileText className="size-5" />}
            </span>
            <span>
              <span className="block text-[15px] font-semibold text-ink">{report.title}</span>
              <span className="mt-1 block text-[13px] leading-relaxed text-body">
                {report.description}
              </span>
            </span>
          </button>
        ))}
      </div>

      {!isLoading && reports?.length === 0 && (
        <Card>
          <EmptyState title="No reports available" />
        </Card>
      )}
    </div>
  )
}

function ReportDetailView({
  definition,
  detail,
  range,
  onBack,
}: {
  definition: ReportDefinition
  detail: import('@/lib/types').ReportDetail
  range: { from?: string; to?: string }
  onBack: () => void
}) {
  const [from, setFrom] = useState(range.from ?? '')
  const [to, setTo] = useState(range.to ?? '')
  const { data: refreshed } = useReport(definition.slug, { from: from || undefined, to: to || undefined })
  const preview = refreshed?.preview ?? detail.preview

  function exportFormat(format: 'csv' | 'xlsx') {
    downloadFile(
      `/api/reports/${definition.slug}/export/${format}/?${new URLSearchParams(
        Object.entries({ from, to }).filter(([, value]) => value),
      ).toString()}`,
    )
  }

  function printPdf() {
    window.print()
  }

  return (
    <div>
      <button
        onClick={onBack}
        className="inline-flex items-center gap-1.5 text-sm font-medium text-body transition-colors hover:text-ink"
      >
        <ArrowLeft className="size-4" /> All reports
      </button>

      <div className="mt-4 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-[32px] font-semibold tracking-tight text-ink">{definition.title}</h1>
          <p className="mt-1.5 max-w-2xl text-[15px] text-body">{definition.description}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          <div className="flex items-center gap-2">
            <Input type="date" value={from} onChange={(event) => setFrom(event.target.value)} aria-label="From date" className="h-9 w-auto text-[13px]" />
            <span className="text-muted">to</span>
            <Input type="date" value={to} onChange={(event) => setTo(event.target.value)} aria-label="To date" className="h-9 w-auto text-[13px]" />
          </div>
          <Button variant="outline" size="sm" onClick={printPdf} icon={<Printer className="size-4" />}>
            PDF
          </Button>
          <Button variant="outline" size="sm" onClick={() => exportFormat('xlsx')} icon={<FileSpreadsheet className="size-4" />}>
            Excel
          </Button>
          <Button variant="outline" size="sm" onClick={() => exportFormat('csv')} icon={<Download className="size-4" />}>
            CSV
          </Button>
        </div>
      </div>

      <Card className="mt-8 overflow-hidden p-0" padding="none">
        <div className="border-b border-line px-5 py-4">
          <p className="text-sm font-semibold text-ink">
            Preview <span className="ml-1 text-xs font-normal text-muted">({preview.count} rows)</span>
          </p>
        </div>
        {preview.rows.length === 0 ? (
          <EmptyState title="No data in this range" description="Adjust the date range or check back later." />
        ) : (
          <div className="print-area overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead>
                <tr className="border-b border-line bg-soft/60 text-[11px] font-semibold uppercase tracking-[0.1em] text-muted">
                  {preview.headers.map((header) => (
                    <th key={header} className="px-5 py-3">
                      {header}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {preview.rows.map((row, rowIndex) => (
                  <tr key={rowIndex} className="transition-colors hover:bg-soft/60">
                    {row.map((cell, cellIndex) => (
                      <td
                        key={cellIndex}
                        className={cn(
                          'px-5 py-3 text-[13px] text-body',
                          cellIndex === 0 && 'font-medium text-ink',
                        )}
                      >
                        {String(cell)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  )
}