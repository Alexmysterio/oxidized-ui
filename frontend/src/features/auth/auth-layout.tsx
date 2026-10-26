import { Check, LockKeyhole, RadioTower } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { LanguageSwitcher } from "@/components/layout/language-switcher";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { BrandMark } from "@/components/shared/brand";
import { useAuth } from "@/lib/auth";

function NetworkArt() {
  return (
    <svg viewBox="0 0 640 400" className="h-auto w-full max-w-[660px]" fill="none" aria-hidden="true">
      <defs>
        <linearGradient id="auth-stroke" x1="80" y1="40" x2="560" y2="360" gradientUnits="userSpaceOnUse">
          <stop stopColor="#6D8BFF" stopOpacity="0.9" />
          <stop offset="0.55" stopColor="#6D8BFF" stopOpacity="0.28" />
          <stop offset="1" stopColor="#43D9C4" stopOpacity="0.55" />
        </linearGradient>
        <radialGradient id="auth-glow" cx="0" cy="0" r="1" gradientTransform="translate(320 200) rotate(90) scale(190)" gradientUnits="userSpaceOnUse">
          <stop stopColor="#4E6BFF" stopOpacity="0.24" />
          <stop offset="1" stopColor="#4E6BFF" stopOpacity="0" />
        </radialGradient>
      </defs>
      <circle cx="320" cy="200" r="176" stroke="white" strokeOpacity="0.05" />
      <circle cx="320" cy="200" r="126" stroke="white" strokeOpacity="0.07" strokeDasharray="3 7" />
      <circle cx="320" cy="200" r="68" stroke="white" strokeOpacity="0.06" />
      <rect x="0" y="0" width="640" height="400" fill="url(#auth-glow)" />
      <g stroke="url(#auth-stroke)" strokeWidth="1.2" strokeOpacity="0.7">
        <path d="M320 200L158 112M320 200L490 116M320 200L510 298M320 200L144 300M320 200L320 46M320 200L320 354" />
        <path d="M158 112L490 116M144 300L510 298M158 112L144 300M490 116L510 298" strokeOpacity="0.18" strokeDasharray="2 8" />
      </g>
      <g>
        <circle cx="320" cy="200" r="29" fill="#0B1120" stroke="#6D8BFF" strokeWidth="1.4" />
        <circle cx="320" cy="200" r="8" fill="#6D8BFF" />
        <circle cx="320" cy="200" r="18" stroke="#6D8BFF" strokeOpacity="0.35" />
      </g>
      {[
        [158, 112, "#A8B8FF"],
        [490, 116, "#A8B8FF"],
        [510, 298, "#6ECFC2"],
        [144, 300, "#A8B8FF"],
        [320, 46, "#D7DFFF"],
        [320, 354, "#6ECFC2"],
      ].map(([cx, cy, color], index) => (
        <g key={`${cx}-${cy}`}>
          <circle cx={cx} cy={cy} r="12" fill="#0B1120" stroke={color as string} strokeOpacity="0.55" />
          <circle cx={cx} cy={cy} r="3.5" fill={color as string}>
            <animate attributeName="opacity" values="0.5;1;0.5" dur={`${3.4 + index * 0.45}s`} repeatCount="indefinite" />
          </circle>
        </g>
      ))}
      <g fill="white" fillOpacity="0.3" fontFamily="JetBrains Mono Variable, monospace" fontSize="7" letterSpacing="1.5" />
    </svg>
  );
}

export function AuthLayout({
  children,
  eyebrow,
  title,
  description,
  heroTitle,
  heroDescription,
  points,
  footer,
}: {
  children: ReactNode;
  eyebrow: string;
  title: string;
  description: string;
  heroTitle?: string;
  heroDescription?: string;
  points?: string[];
  footer?: ReactNode;
}) {
  const { t } = useTranslation();
  const { meta } = useAuth();

  return (
    <div className="min-h-screen bg-background lg:grid lg:grid-cols-[1.08fr_0.92fr]">
      <section className="relative hidden min-h-screen overflow-hidden bg-[#080d18] px-10 py-9 text-slate-100 lg:flex lg:flex-col xl:px-16">
        <div className="sidebar-grid absolute inset-0 opacity-50" />
        <div className="pointer-events-none absolute -left-32 top-1/3 h-[32rem] w-[32rem] rounded-full bg-[#3154ff]/20 blur-[120px]" />
        <div className="pointer-events-none absolute -right-24 bottom-0 h-72 w-72 rounded-full bg-[#38c7b3]/10 blur-[100px]" />
        <div className="relative z-10 flex items-center gap-3">
          <BrandMark className="h-9 w-9" animated />
          <div>
            <div className="text-[15px] font-semibold tracking-tight">{meta?.site_name || t("app.name")}</div>
            <div className="font-mono text-[9px] uppercase tracking-[0.22em] text-slate-500">{t("app.taglineShort")}</div>
          </div>
        </div>

        <div className="relative z-10 my-auto grid max-w-[640px] grid-cols-[1fr_auto] items-center gap-6 py-10">
          <div>
            <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.035] px-3 py-1 font-mono text-[9px] uppercase tracking-[0.2em] text-slate-400">
              <RadioTower className="h-3 w-3 text-[#7f96ff]" />
              {eyebrow}
            </div>
            <h1 className="max-w-xl text-[clamp(2rem,3.4vw,3.6rem)] font-semibold leading-[1.05] tracking-[-0.045em] text-white">
              {heroTitle ?? title}
            </h1>
            <p className="mt-5 max-w-lg text-[15px] leading-relaxed text-slate-400">{heroDescription ?? description}</p>
            {points?.length ? (
              <ul className="mt-8 space-y-3">
                {points.map((point) => (
                  <li key={point} className="flex items-center gap-3 text-sm text-slate-300">
                    <span className="flex h-5 w-5 items-center justify-center rounded-full border border-[#6d8bff]/30 bg-[#6d8bff]/10 text-[#9cb0ff]">
                      <Check className="h-3 w-3" strokeWidth={2.5} />
                    </span>
                    {point}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
          <div className="hidden w-[340px] xl:block">
            <NetworkArt />
          </div>
        </div>

        <div className="relative z-10 flex items-center justify-between border-t border-white/[0.07] pt-5">
          <span className="font-mono text-[9px] uppercase tracking-[0.18em] text-slate-600">
            {t("auth.secureConnection")}
          </span>
          <span className="inline-flex items-center gap-1.5 font-mono text-[9px] uppercase tracking-[0.18em] text-slate-600">
            <LockKeyhole className="h-3 w-3" />
            {t("app.version")} {meta?.app_version ?? "0.1.0"}
          </span>
        </div>
      </section>

      <section className="app-grid relative flex min-h-screen flex-col bg-background">
        <div className="flex items-center justify-between px-5 py-5 sm:px-8">
          <div className="flex items-center gap-2.5 lg:invisible">
            <BrandMark className="h-8 w-8" />
            <span className="text-sm font-semibold tracking-tight">{meta?.site_name || t("app.name")}</span>
          </div>
          <div className="flex items-center gap-1">
            <LanguageSwitcher compact />
            <ThemeToggle compact />
          </div>
        </div>
        <div className="relative flex flex-1 items-center justify-center px-5 pb-12 sm:px-8">
          <div className="w-full max-w-[420px]">
            <div className="mb-7">
              <p className="eyebrow mb-3">{eyebrow}</p>
              <h2 className="text-[26px] font-semibold leading-tight tracking-[-0.03em]">{title}</h2>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{description}</p>
            </div>
            <div className="rounded-xl border border-border/80 bg-card/90 p-5 shadow-soft backdrop-blur-sm sm:p-6">
              {children}
            </div>
            {footer ? <div className="mt-5 text-center text-xs text-muted-foreground">{footer}</div> : null}
          </div>
        </div>
      </section>
    </div>
  );
}
