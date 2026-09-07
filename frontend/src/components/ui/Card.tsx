import type { HTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  hover?: boolean
  padding?: 'none' | 'md' | 'lg'
}

export function Card({ className, hover, padding = 'md', ...props }: CardProps) {
  return (
    <div
      className={cn(
        'card',
        hover && 'card-hover',
        padding === 'md' && 'p-5',
        padding === 'lg' && 'p-6 sm:p-8',
        className,
      )}
      {...props}
    />
  )
}

export function CardHeader({
  title,
  description,
  action,
  className,
}: {
  title: string
  description?: string
  action?: React.ReactNode
  className?: string
}) {
  return (
    <div className={cn('flex items-start justify-between gap-4', className)}>
      <div>
        <h3 className="text-[17px] font-semibold text-ink">{title}</h3>
        {description && <p className="mt-1 text-sm text-body">{description}</p>}
      </div>
      {action}
    </div>
  )
}