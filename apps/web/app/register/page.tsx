"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, Check } from "lucide-react";
import { AuthShell } from "@/components/auth/auth-shell";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { useAuth } from "@/lib/auth";
import { errorMessage } from "@/lib/api";

const BENEFITS = [
  "Semantic model you review and approve",
  "Generated dashboard you can edit and publish",
  "AI analyst with SQL provenance",
];

export default function RegisterPage() {
  const { register } = useAuth();
  const router = useRouter();
  const [form, setForm] = useState({ full_name: "", email: "", organization_name: "", password: "", confirm: "" });
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const update = (key: keyof typeof form) => (event: React.ChangeEvent<HTMLInputElement>) =>
    setForm((current) => ({ ...current, [key]: event.target.value }));

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    if (form.password !== form.confirm) {
      setError("Passwords do not match.");
      return;
    }
    if (form.password.length < 8) {
      setError("Use at least 8 characters for your password.");
      return;
    }
    setSubmitting(true);
    try {
      await register({
        email: form.email.trim(),
        password: form.password,
        full_name: form.full_name.trim(),
        organization_name: form.organization_name.trim() || undefined,
      });
      router.replace("/app");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AuthShell
      title="Create your workspace"
      subtitle="Start with the synthetic retail dataset, then upload your own."
      footer={
        <span>
          Already have an account?{" "}
          <Link href="/login" className="font-medium text-brand hover:underline">
            Sign in
          </Link>
        </span>
      }
    >
      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="full_name">Full name</Label>
            <Input id="full_name" required autoComplete="name" placeholder="Asha Rao" value={form.full_name} onChange={update("full_name")} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="organization_name">Organisation</Label>
            <Input id="organization_name" placeholder="Northwind Retail" value={form.organization_name} onChange={update("organization_name")} />
          </div>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="email">Work email</Label>
          <Input id="email" type="email" required autoComplete="email" placeholder="you@company.com" value={form.email} onChange={update("email")} />
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="password">Password</Label>
            <Input id="password" type="password" required autoComplete="new-password" placeholder="At least 8 characters" value={form.password} onChange={update("password")} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="confirm">Confirm password</Label>
            <Input id="confirm" type="password" required autoComplete="new-password" placeholder="Repeat password" value={form.confirm} onChange={update("confirm")} />
          </div>
        </div>

        {error && (
          <div role="alert" className="rounded-xl border border-danger/25 bg-danger/[0.07] px-3 py-2.5 text-[12.5px] text-danger">
            {error}
          </div>
        )}

        <Button type="submit" variant="gradient" size="lg" className="w-full" loading={submitting}>
          Create workspace <ArrowRight className="h-4 w-4" />
        </Button>

        <ul className="space-y-1.5 pt-1">
          {BENEFITS.map((benefit) => (
            <li key={benefit} className="flex items-center gap-2 text-[12px] text-muted">
              <Check className="h-3.5 w-3.5 text-success" />
              {benefit}
            </li>
          ))}
        </ul>
        <p className="text-[11px] leading-relaxed text-faint">
          By creating an account you accept that uploaded data is processed to generate analytics and that AI model
          calls (when configured) may include dataset schemas, never credentials.
        </p>
      </form>
    </AuthShell>
  );
}
