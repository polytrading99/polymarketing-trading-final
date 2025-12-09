"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Database, Bot } from "lucide-react";
import clsx from "clsx";

export function Navigation() {
  const pathname = usePathname();

  const navItems = [
    { href: "/", label: "Markets", icon: Database },
    { href: "/mm-bot", label: "MM Bot", icon: Bot },
  ];

  return (
    <nav className="mb-8 border-b border-slate-800 pb-4">
      <div className="flex items-center gap-4">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={clsx(
                "inline-flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-slate-800 text-slate-100"
                  : "text-slate-400 hover:bg-slate-900 hover:text-slate-200"
              )}
            >
              <Icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}

