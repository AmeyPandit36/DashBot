import * as React from "react";
import { cn } from "./utils";

const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => (
    <input
      type={type}
      ref={ref}
      className={cn(
        "flex h-10 w-full rounded-xl border border-line/12 bg-surface/70 px-3.5 py-2 text-sm text-ink shadow-sm transition placeholder:text-faint",
        "focus-visible:border-brand/50 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-brand/10",
        "disabled:cursor-not-allowed disabled:opacity-60 file:mr-3 file:rounded-lg file:border-0 file:bg-brand/10 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-brand",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";

const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, ...props }, ref) => (
    <textarea
      ref={ref}
      className={cn(
        "flex min-h-[96px] w-full rounded-xl border border-line/12 bg-surface/70 px-3.5 py-2.5 text-sm text-ink shadow-sm transition placeholder:text-faint",
        "focus-visible:border-brand/50 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-brand/10",
        className,
      )}
      {...props}
    />
  ),
);
Textarea.displayName = "Textarea";

const Label = React.forwardRef<HTMLLabelElement, React.LabelHTMLAttributes<HTMLLabelElement>>(
  ({ className, ...props }, ref) => (
    <label ref={ref} className={cn("text-[13px] font-medium text-ink/90", className)} {...props} />
  ),
);
Label.displayName = "Label";

export { Input, Textarea, Label };
