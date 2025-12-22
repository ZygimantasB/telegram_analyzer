import { clsx } from 'clsx'

interface AvatarProps {
  src?: string
  name: string
  size?: 'sm' | 'md' | 'lg' | 'xl'
  className?: string
}

export function Avatar({ src, name, size = 'md', className }: AvatarProps) {
  const sizes = {
    sm: 'w-8 h-8 text-xs',
    md: 'w-10 h-10 text-sm',
    lg: 'w-12 h-12 text-base',
    xl: 'w-16 h-16 text-lg',
  }

  const initials = name
    .split(' ')
    .map(n => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2)

  if (src) {
    return (
      <img
        src={src}
        alt={name}
        className={clsx(
          'rounded-full object-cover ring-2 ring-primary-500/20',
          sizes[size],
          className
        )}
      />
    )
  }

  return (
    <div
      className={clsx(
        'rounded-full bg-gradient-to-br from-primary-400 to-accent-500',
        'flex items-center justify-center text-white font-semibold',
        sizes[size],
        className
      )}
    >
      {initials}
    </div>
  )
}
