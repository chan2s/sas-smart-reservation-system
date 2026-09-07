import { Link } from 'react-router-dom'
import {
  ArrowRight,
  BookOpen,
  CalendarPlus,
  LifeBuoy,
  Mail,
  MessageCircleQuestion,
  QrCode,
  ScanLine,
} from 'lucide-react'
import { PageHeader } from '@/components/ui/Misc'
import { Card, CardHeader } from '@/components/ui/Card'
import { useAuth } from '@/hooks/useAuth'

export function HelpPage() {
  const { isStaff } = useAuth()

  const guides = [
    {
      title: 'Creating a reservation',
      description: 'Pick a facility, schedule, and resources — the wizard checks availability in real time.',
      to: '/reservations/new',
      icon: <CalendarPlus className="size-5" />,
      cta: 'Start a reservation',
    },
    {
      title: 'QR check-in',
      description: 'Every approved reservation gets a QR code. Show it to SAS staff when you arrive.',
      to: '/reservations',
      icon: <QrCode className="size-5" />,
      cta: 'View reservations',
    },
    ...(isStaff
      ? [
          {
            title: 'Staff scanning',
            description: 'Verify arriving requesters by scanning their QR code at the facility.',
            to: '/reservations',
            icon: <ScanLine className="size-5" />,
            cta: 'Open reservations',
          },
        ]
      : []),
    {
      title: 'Reading the calendar',
      description: 'Month, week, and day views show every reservation across all facilities.',
      to: '/calendar',
      icon: <BookOpen className="size-5" />,
      cta: 'Open calendar',
    },
  ]

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        eyebrow="SAS Help"
        title="Help"
        description="Quick answers about using the reservation system."
      />

      <div className="mt-8 grid gap-4 sm:grid-cols-2">
        {guides.map((guide) => (
          <Card key={guide.title} hover className="flex flex-col">
            <span className="flex size-10 items-center justify-center rounded-xl bg-brand-soft text-brand">
              {guide.icon}
            </span>
            <h2 className="mt-4 text-[17px] font-semibold text-ink">{guide.title}</h2>
            <p className="mt-1.5 flex-1 text-sm leading-relaxed text-body">{guide.description}</p>
            <Link
              to={guide.to}
              className="mt-4 inline-flex items-center gap-1.5 text-sm font-medium text-brand hover:text-brand-dark"
            >
              {guide.cta} <ArrowRight className="size-3.5" />
            </Link>
          </Card>
        ))}
      </div>

      <div className="mt-8 grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader title="Need more help?" />
          <p className="mt-2 text-sm text-body">
            The SAS Office manages all accounts, approvals, and facility scheduling.
          </p>
          <ul className="mt-4 space-y-2.5 text-sm text-body">
            <li className="flex items-center gap-2.5">
              <Mail className="size-4 text-muted" aria-hidden /> sas@school.edu
            </li>
            <li className="flex items-center gap-2.5">
              <MessageCircleQuestion className="size-4 text-muted" aria-hidden /> Room 101, Main Building
            </li>
            <li className="flex items-center gap-2.5">
              <LifeBuoy className="size-4 text-muted" aria-hidden /> Mon–Fri, 8:00 AM – 5:00 PM
            </li>
          </ul>
        </Card>
      </div>
    </div>
  )
}