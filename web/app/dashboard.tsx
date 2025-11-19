"use client";

import { useMemo } from "react";
import { TrendingUp, TrendingDown, DollarSign, Activity, AlertCircle } from "lucide-react";
import type { Market } from "../lib/api";
import clsx from "clsx";

interface DashboardStatsProps {
  markets: Market[];
}

export function DashboardStats({ markets }: DashboardStatsProps) {
  const stats = useMemo(() => {
    const active = markets.filter(m => m.status === "active").length;
    const totalPnL = markets.reduce((sum, m) => sum + (m.pnl_total || 0), 0);
    const totalFees = markets.reduce((sum, m) => sum + (m.fees_paid || 0), 0);
    const totalPositions = markets.reduce((sum, m) => sum + (m.position_count || 0), 0);
    const netPnL = totalPnL - totalFees;
    
    return {
      total: markets.length,
      active,
      inactive: markets.length - active,
      totalPnL,
      totalFees,
      netPnL,
      totalPositions,
    };
  }, [markets]);

  const statCards = [
    {
      label: "Total Markets",
      value: stats.total,
      icon: Activity,
      color: "slate",
    },
    {
      label: "Active Markets",
      value: stats.active,
      icon: Activity,
      color: "emerald",
    },
    {
      label: "Net PnL",
      value: `$${stats.netPnL.toFixed(2)}`,
      icon: stats.netPnL >= 0 ? TrendingUp : TrendingDown,
      color: stats.netPnL >= 0 ? "emerald" : "red",
    },
    {
      label: "Total Fees",
      value: `$${stats.totalFees.toFixed(2)}`,
      icon: DollarSign,
      color: "amber",
    },
    {
      label: "Total Positions",
      value: stats.totalPositions,
      icon: Activity,
      color: "blue",
    },
  ];

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
      {statCards.map((stat) => {
        const Icon = stat.icon;
        return (
          <div
            key={stat.label}
            className="rounded-lg border border-slate-800 bg-slate-900/60 p-4"
          >
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs text-slate-400">{stat.label}</p>
                <p
                  className={clsx(
                    "mt-1 text-2xl font-semibold",
                    stat.color === "emerald" && "text-emerald-400",
                    stat.color === "red" && "text-red-400",
                    stat.color === "amber" && "text-amber-400",
                    stat.color === "blue" && "text-blue-400",
                    stat.color === "slate" && "text-slate-300"
                  )}
                >
                  {stat.value}
                </p>
              </div>
              <Icon
                className={clsx(
                  "h-5 w-5",
                  stat.color === "emerald" && "text-emerald-400/50",
                  stat.color === "red" && "text-red-400/50",
                  stat.color === "amber" && "text-amber-400/50",
                  stat.color === "blue" && "text-blue-400/50",
                  stat.color === "slate" && "text-slate-400/50"
                )}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function PnLChart({ markets }: DashboardStatsProps) {
  const activeMarkets = markets.filter(m => m.status === "active" && m.pnl_total !== null);
  
  if (activeMarkets.length === 0) {
    return (
      <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-8 text-center">
        <AlertCircle className="mx-auto h-12 w-12 text-slate-500 mb-4" />
        <p className="text-slate-400">No active markets with PnL data</p>
      </div>
    );
  }

  const maxPnL = Math.max(...activeMarkets.map(m => Math.abs(m.pnl_total || 0)), 1);
  
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-6">
      <h3 className="text-lg font-semibold text-slate-100 mb-4">PnL by Market</h3>
      <div className="space-y-3">
        {activeMarkets.slice(0, 10).map((market) => {
          const pnl = market.pnl_total || 0;
          const percentage = (Math.abs(pnl) / maxPnL) * 100;
          const isPositive = pnl >= 0;
          
          return (
            <div key={market.id} className="space-y-1">
              <div className="flex items-center justify-between text-sm">
                <span className="text-slate-300 truncate flex-1 mr-2">
                  {market.question.length > 40 
                    ? `${market.question.substring(0, 40)}...` 
                    : market.question}
                </span>
                <span
                  className={clsx(
                    "font-semibold shrink-0",
                    isPositive ? "text-emerald-400" : "text-red-400"
                  )}
                >
                  {isPositive ? "+" : ""}
                  {pnl.toFixed(2)} USDC
                </span>
              </div>
              <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
                <div
                  className={clsx(
                    "h-full transition-all",
                    isPositive ? "bg-emerald-500" : "bg-red-500"
                  )}
                  style={{ width: `${Math.min(percentage, 100)}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

