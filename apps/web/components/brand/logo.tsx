import { cn } from "@/components/ui/utils";

export function LogoMark({ className, size = 32 }: { className?: string; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 40 40"
      fill="none"
      className={className}
      role="img"
      aria-label="Agentic BI mark"
    >
      <defs>
        <linearGradient id="abi-mark-a" x1="4" y1="4" x2="36" y2="36" gradientUnits="userSpaceOnUse">
          <stop stopColor="#4F6BFF" />
          <stop offset="0.52" stopColor="#8B5CF6" />
          <stop offset="1" stopColor="#06B6D4" />
        </linearGradient>
        <linearGradient id="abi-mark-b" x1="10" y1="30" x2="32" y2="8" gradientUnits="userSpaceOnUse">
          <stop stopColor="#06B6D4" stopOpacity="0.9" />
          <stop offset="1" stopColor="#8B5CF6" stopOpacity="0.35" />
        </linearGradient>
      </defs>
      <rect x="1" y="1" width="38" height="38" rx="12" fill="url(#abi-mark-a)" opacity="0.14" />
      <path d="M11 27.5 L20 10.5 L29 27.5 Z" stroke="url(#abi-mark-a)" strokeWidth="2.1" strokeLinejoin="round" />
      <circle cx="20" cy="10.5" r="3.1" fill="url(#abi-mark-a)" />
      <circle cx="11" cy="27.5" r="2.7" fill="#4F6BFF" />
      <circle cx="29" cy="27.5" r="2.7" fill="#06B6D4" />
      <path d="M20 16.5 V23.5" stroke="url(#abi-mark-b)" strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="20" cy="23.5" r="1.6" fill="#8B5CF6" />
    </svg>
  );
}

export function Logo({ className, showWordmark = true }: { className?: string; showWordmark?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <LogoMark />
      {showWordmark && (
        <span className="flex flex-col leading-none">
          <span className="font-display text-[15px] font-semibold tracking-[-0.02em] text-ink">Agentic BI</span>
          <span className="mt-1 text-[9px] font-medium uppercase tracking-[0.18em] text-faint">Analytical intelligence</span>
        </span>
      )}
    </span>
  );
}
