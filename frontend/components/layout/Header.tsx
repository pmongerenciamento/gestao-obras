"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { createClient } from "@/lib/supabase/client";

// Topbar da área autenticada: logo, breadcrumb e avatar do usuário logado (com logout)

interface BreadcrumbItem {
  label: string;
  href?: string;
}

interface HeaderProps {
  breadcrumb: BreadcrumbItem[];
  subtitle?: string;
  userEmail?: string | null;
}

export function Header({ breadcrumb, subtitle, userEmail }: HeaderProps) {
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);

  async function handleLogout() {
    const supabase = createClient();
    await supabase.auth.signOut();
    router.push("/login");
    router.refresh();
  }

  return (
    <header className="flex min-h-16 shrink-0 items-center justify-between border-b border-black/10 bg-white px-6 py-3">
      <div className="flex items-center gap-4">
        <Image
          src="/logo/LOGO_PMON.png"
          alt="PMON"
          width={32}
          height={32}
          className="h-8 w-auto"
        />
        <div>
          <nav className="flex items-center gap-1 text-sm text-black/60">
            {breadcrumb.map((item, index) => (
              <span key={`${item.label}-${index}`} className="flex items-center gap-1">
                {index > 0 && <span className="text-black/30">›</span>}
                {item.href ? (
                  <Link href={item.href} className="hover:text-black">
                    {item.label}
                  </Link>
                ) : (
                  <span className="text-black">{item.label}</span>
                )}
              </span>
            ))}
          </nav>
          {subtitle && <p className="text-xs text-black/50">{subtitle}</p>}
        </div>
      </div>

      <div
        className="relative"
        onBlur={(e) => {
          if (!e.currentTarget.contains(e.relatedTarget)) setMenuOpen(false);
        }}
      >
        <button
          type="button"
          onClick={() => setMenuOpen((open) => !open)}
          className="flex h-9 w-9 items-center justify-center rounded-full bg-pmon-black text-sm font-semibold text-white"
        >
          {(userEmail ?? "?").charAt(0).toUpperCase()}
        </button>
        {menuOpen && (
          <div className="absolute right-0 z-10 mt-2 w-48 rounded-md border border-black/10 bg-white py-1 shadow-lg">
            <p className="truncate px-3 py-2 text-xs text-black/50">{userEmail}</p>
            <button
              type="button"
              onClick={handleLogout}
              className="w-full px-3 py-2 text-left text-sm text-black hover:bg-black/5"
            >
              Sair
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
