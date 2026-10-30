"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowLeft, MailCheck } from "lucide-react";
import { AuthShell } from "@/components/auth/auth-shell";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { api, errorMessage } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [devToken, setDevToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const onSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const result = await api.post<{ sent: boolean; development_reset_token?: string }>("/auth/forgot-password", {
        email: email.trim(),
      });
      setSent(true);
      setDevToken(result.development_reset_token ?? null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthShell
      title="Reset your password"
      subtitle="We'll create a time-limited reset link for your account."
      footer={
        <Link href="/login" className="inline-flex items-center gap-1.5 font-medium text-brand hover:underline">
          <ArrowLeft className="h-3.5 w-3.5" /> Back to sign in
        </Link>
      }
    >
      {sent ? (
        <div className="space-y-4">
          <div className="flex items-start gap-3 rounded-xl border border-success/25 bg-success/[0.07] px-4 py-3">
            <MailCheck className="mt-0.5 h-4 w-4 text-success" />
            <div>
              <p className="text-[13px] font-medium text-ink">Reset request accepted</p>
              <p className="mt-1 text-[12.5px] leading-relaxed text-muted">
                If an account exists for {email}, reset instructions have been generated.
              </p>
            </div>
          </div>
          {devToken ? (
            <div className="rounded-xl border border-warning/25 bg-warning/[0.06] p-3">
              <p className="text-[12px] font-medium text-ink">Development email delivery is not configured</p>
              <p className="mt-1 text-[11.5px] leading-relaxed text-muted">
                Use this single-use link to set a new password. This token is only exposed outside production.
              </p>
              <Button asChild size="sm" variant="outline" className="mt-2">
                <Link href={`/reset-password?token=${encodeURIComponent(devToken)}`}>Open reset form</Link>
              </Button>
            </div>
          ) : (
            <p className="text-[12.5px] text-muted">
              Check your inbox for the reset link. In production, email delivery must be configured (SMTP or a
              transactional email provider).
            </p>
          )}
        </div>
      ) : (
        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          <div className="space-y-1.5">
            <Label htmlFor="email">Work email</Label>
            <Input
              id="email"
              type="email"
              required
              placeholder="you@company.com"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
            />
          </div>
          {error && (
            <div role="alert" className="rounded-xl border border-danger/25 bg-danger/[0.07] px-3 py-2.5 text-[12.5px] text-danger">
              {error}
            </div>
          )}
          <Button type="submit" variant="gradient" size="lg" className="w-full" loading={loading}>
            Send reset link
          </Button>
        </form>
      )}
    </AuthShell>
  );
}
