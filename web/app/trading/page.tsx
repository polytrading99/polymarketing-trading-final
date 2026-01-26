"use client";

import { useState } from "react";
import useSWR from "swr";
import { DollarSign, Package, ShoppingCart, Activity, RefreshCw } from "lucide-react";
import {
  getTradingStatus,
  getAccountSummary,
  syncMarkets,
  type TradingStatus,
  type AccountSummary,
} from "../../lib/api";
import clsx from "clsx";

const tradingStatusFetcher = () => getTradingStatus();
const accountFetcher = () => getAccountSummary();

export default function TradingPage() {
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date());

  const { data: tradingStatus, error: tradingError, mutate: mutateTrading } = useSWR<TradingStatus>(
    "/trading/status",
    tradingStatusFetcher,
    { refreshInterval: 5000 } // Update every 5 seconds
  );

  const { data: accountSummary, error: accountError, mutate: mutateAccount } = useSWR<AccountSummary>(
    "/mm-bot/account/summary",
    accountFetcher,
    { refreshInterval: 5000 } // Update every 5 seconds
  );

  const [syncing, setSyncing] = useState(false);

  const handleRefresh = () => {
    mutateTrading();
    mutateAccount();
    setLastUpdate(new Date());
  };

  const handleSyncMarkets = async () => {
    setSyncing(true);
    try {
      const result = await syncMarkets();
      if (result.success) {
        alert(`Markets synced! ${result.active_markets_count} active markets loaded.`);
        handleRefresh();
      } else {
        alert(`Failed to sync markets: ${result.error}`);
      }
    } catch (err) {
      alert(`Error syncing markets: ${err instanceof Error ? err.message : "Unknown error"}`);
    } finally {
      setSyncing(false);
    }
  };

  // Calculate totals
  const totalPositionValue = tradingStatus?.success
    ? Object.values(tradingStatus.positions || {}).reduce(
        (sum, pos: any) => sum + (pos.value || 0),
        0
      )
    : 0;

  const usdcBalance = accountSummary?.balance?.success
    ? Number(accountSummary.balance.balance?.usdc) || 0
    : 0;

  const activePositions = accountSummary?.positions?.success
    ? accountSummary.positions.total_positions || 0
    : 0;

  const openOrders = accountSummary?.orders?.success
    ? accountSummary.orders.total_orders || 0
    : 0;

  return (
    <main className="space-y-6 p-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-semibold">Trading Dashboard</h1>
          <p className="text-sm text-slate-400 mt-1">
            Real-time account balance and trading status
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={handleSyncMarkets}
            disabled={syncing}
            className="inline-flex items-center gap-2 rounded-md border border-emerald-700 bg-emerald-900/20 px-4 py-2 text-sm font-medium text-emerald-300 hover:bg-emerald-900/40 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {syncing ? (
              <>
                <RefreshCw className="h-4 w-4 animate-spin" />
                Syncing...
              </>
            ) : (
              <>
                <Activity className="h-4 w-4" />
                Sync Markets
              </>
            )}
          </button>
          <button
            onClick={handleRefresh}
            className="inline-flex items-center gap-2 rounded-md border border-slate-700 bg-slate-900 px-4 py-2 text-sm font-medium text-slate-100 hover:bg-slate-800"
          >
            <RefreshCw className="h-4 w-4" />
            Refresh
          </button>
        </div>
      </header>

      {/* Account Balance Table */}
      <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-6">
        <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
          <DollarSign className="h-5 w-5" />
          Account Balance
        </h2>
        <div className="overflow-x-auto">
          <table className="w-full border-collapse">
            <thead>
              <tr className="border-b border-slate-800">
                <th className="text-left py-3 px-4 text-sm font-semibold text-slate-300">Metric</th>
                <th className="text-right py-3 px-4 text-sm font-semibold text-slate-300">Value</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-b border-slate-800/50 hover:bg-slate-900/40">
                <td className="py-3 px-4 text-sm text-slate-400">USDC Balance</td>
                <td className="py-3 px-4 text-sm text-right font-semibold text-emerald-400">
                  ${usdcBalance.toFixed(2)}
                </td>
              </tr>
              <tr className="border-b border-slate-800/50 hover:bg-slate-900/40">
                <td className="py-3 px-4 text-sm text-slate-400">Active Positions</td>
                <td className="py-3 px-4 text-sm text-right font-semibold text-blue-400">
                  {activePositions}
                </td>
              </tr>
              <tr className="border-b border-slate-800/50 hover:bg-slate-900/40">
                <td className="py-3 px-4 text-sm text-slate-400">Open Orders</td>
                <td className="py-3 px-4 text-sm text-right font-semibold text-yellow-400">
                  {openOrders}
                </td>
              </tr>
              {accountSummary?.wallet_address && (
                <tr className="hover:bg-slate-900/40">
                  <td className="py-3 px-4 text-sm text-slate-400">Wallet Address</td>
                  <td className="py-3 px-4 text-sm text-right font-mono text-slate-300">
                    {accountSummary.wallet_address.slice(0, 10)}...{accountSummary.wallet_address.slice(-8)}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Bot Status */}
      {tradingStatus && (
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-6">
          <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
            <Activity className="h-5 w-5" />
            Bot Status
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <div className="p-4 rounded-md bg-slate-800/50">
              <div className="text-xs text-slate-500 mb-1">Active Markets</div>
              <div className="text-2xl font-bold text-blue-400">
                {tradingStatus.active_markets || 0}
              </div>
            </div>
            <div className="p-4 rounded-md bg-slate-800/50">
              <div className="text-xs text-slate-500 mb-1">WebSocket</div>
              <div className={clsx(
                "text-2xl font-bold",
                tradingStatus.websocket_connected ? "text-emerald-400" : "text-red-400"
              )}>
                {tradingStatus.websocket_connected ? "✓ Connected" : "✗ Disconnected"}
              </div>
            </div>
            <div className="p-4 rounded-md bg-slate-800/50">
              <div className="text-xs text-slate-500 mb-1">Bot Positions</div>
              <div className="text-2xl font-bold text-yellow-400">
                {tradingStatus.total_positions || 0}
              </div>
            </div>
            <div className="p-4 rounded-md bg-slate-800/50">
              <div className="text-xs text-slate-500 mb-1">Bot Orders</div>
              <div className="text-2xl font-bold text-purple-400">
                {tradingStatus.total_orders || 0}
              </div>
            </div>
          </div>
          {tradingStatus.active_markets_list && tradingStatus.active_markets_list.length > 0 && (
            <div className="mt-4">
              <div className="text-sm font-semibold text-slate-300 mb-2">Active Markets:</div>
              <div className="space-y-1">
                {tradingStatus.active_markets_list.map((market: any, idx: number) => (
                  <div key={idx} className="text-xs text-slate-400 font-mono">
                    • {market.question || market.condition_id}
                  </div>
                ))}
              </div>
            </div>
          )}
          {tradingStatus.error && (
            <div className="mt-4 p-3 rounded-md bg-red-500/10 border border-red-500/50 text-sm text-red-300">
              {tradingStatus.error}
            </div>
          )}
        </div>
      )}

      {/* Trading Status Table */}
      {tradingStatus?.success && (
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-6">
          <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
            <Activity className="h-5 w-5" />
            Trading Status
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse">
              <thead>
                <tr className="border-b border-slate-800">
                  <th className="text-left py-3 px-4 text-sm font-semibold text-slate-300">Metric</th>
                  <th className="text-right py-3 px-4 text-sm font-semibold text-slate-300">Value</th>
                </tr>
              </thead>
              <tbody>
                <tr className="border-b border-slate-800/50 hover:bg-slate-900/40">
                  <td className="py-3 px-4 text-sm text-slate-400">Active Markets</td>
                  <td className="py-3 px-4 text-sm text-right font-semibold text-blue-400">
                    {tradingStatus.active_markets || 0}
                  </td>
                </tr>
                <tr className="border-b border-slate-800/50 hover:bg-slate-900/40">
                  <td className="py-3 px-4 text-sm text-slate-400">Bot Positions</td>
                  <td className="py-3 px-4 text-sm text-right font-semibold text-purple-400">
                    {tradingStatus.total_positions || 0}
                  </td>
                </tr>
                <tr className="border-b border-slate-800/50 hover:bg-slate-900/40">
                  <td className="py-3 px-4 text-sm text-slate-400">Bot Orders</td>
                  <td className="py-3 px-4 text-sm text-right font-semibold text-yellow-400">
                    {tradingStatus.total_orders || 0}
                  </td>
                </tr>
                <tr className="border-b border-slate-800/50 hover:bg-slate-900/40">
                  <td className="py-3 px-4 text-sm text-slate-400">Pending Trades</td>
                  <td className="py-3 px-4 text-sm text-right font-semibold text-orange-400">
                    {Object.keys(tradingStatus.performing_trades || {}).length}
                  </td>
                </tr>
                <tr className="hover:bg-slate-900/40">
                  <td className="py-3 px-4 text-sm text-slate-400">Total Position Value</td>
                  <td className="py-3 px-4 text-sm text-right font-semibold text-emerald-400">
                    ${totalPositionValue.toFixed(2)}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Current Positions Table */}
      {tradingStatus?.success && tradingStatus.positions && Object.keys(tradingStatus.positions).length > 0 && (
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-6">
          <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
            <Package className="h-5 w-5" />
            Current Positions
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse">
              <thead>
                <tr className="border-b border-slate-800">
                  <th className="text-left py-3 px-4 text-sm font-semibold text-slate-300">Token</th>
                  <th className="text-right py-3 px-4 text-sm font-semibold text-slate-300">Size</th>
                  <th className="text-right py-3 px-4 text-sm font-semibold text-slate-300">Avg Price</th>
                  <th className="text-right py-3 px-4 text-sm font-semibold text-slate-300">Value</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(tradingStatus.positions).map(([token, pos]: [string, any]) => (
                  <tr key={token} className="border-b border-slate-800/50 hover:bg-slate-900/40">
                    <td className="py-3 px-4 text-sm font-mono text-slate-300">
                      {token.slice(0, 12)}...{token.slice(-8)}
                    </td>
                    <td className={clsx(
                      "py-3 px-4 text-sm text-right font-semibold",
                      pos.size >= 0 ? "text-emerald-400" : "text-red-400"
                    )}>
                      {pos.size >= 0 ? "+" : ""}{(pos.size || 0).toFixed(4)}
                    </td>
                    <td className="py-3 px-4 text-sm text-right text-slate-300">
                      ${(pos.avgPrice || 0).toFixed(4)}
                    </td>
                    <td className="py-3 px-4 text-sm text-right text-slate-300">
                      ${(pos.value || 0).toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Open Orders Table */}
      {tradingStatus?.success && tradingStatus.orders && Object.keys(tradingStatus.orders).length > 0 && (
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-6">
          <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
            <ShoppingCart className="h-5 w-5" />
            Open Orders
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse">
              <thead>
                <tr className="border-b border-slate-800">
                  <th className="text-left py-3 px-4 text-sm font-semibold text-slate-300">Token</th>
                  <th className="text-right py-3 px-4 text-sm font-semibold text-slate-300">Side</th>
                  <th className="text-right py-3 px-4 text-sm font-semibold text-slate-300">Size</th>
                  <th className="text-right py-3 px-4 text-sm font-semibold text-slate-300">Price</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(tradingStatus.orders).map(([token, order]: [string, any]) => {
                  const rows = [];
                  if (order.buy?.size > 0) {
                    rows.push(
                      <tr key={`${token}-buy`} className="border-b border-slate-800/50 hover:bg-slate-900/40">
                        <td className="py-3 px-4 text-sm font-mono text-slate-300">
                          {token.slice(0, 12)}...{token.slice(-8)}
                        </td>
                        <td className="py-3 px-4 text-sm text-right font-semibold text-emerald-400">
                          BUY
                        </td>
                        <td className="py-3 px-4 text-sm text-right text-slate-300">
                          {(order.buy.size || 0).toFixed(4)}
                        </td>
                        <td className="py-3 px-4 text-sm text-right text-slate-300">
                          ${(order.buy.price || 0).toFixed(4)}
                        </td>
                      </tr>
                    );
                  }
                  if (order.sell?.size > 0) {
                    rows.push(
                      <tr key={`${token}-sell`} className="border-b border-slate-800/50 hover:bg-slate-900/40">
                        <td className="py-3 px-4 text-sm font-mono text-slate-300">
                          {token.slice(0, 12)}...{token.slice(-8)}
                        </td>
                        <td className="py-3 px-4 text-sm text-right font-semibold text-red-400">
                          SELL
                        </td>
                        <td className="py-3 px-4 text-sm text-right text-slate-300">
                          {(order.sell.size || 0).toFixed(4)}
                        </td>
                        <td className="py-3 px-4 text-sm text-right text-slate-300">
                          ${(order.sell.price || 0).toFixed(4)}
                        </td>
                      </tr>
                    );
                  }
                  return rows;
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Empty State */}
      {tradingStatus?.success && 
       (!tradingStatus.positions || Object.keys(tradingStatus.positions).length === 0) &&
       (!tradingStatus.orders || Object.keys(tradingStatus.orders).length === 0) && (
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-12 text-center">
          <p className="text-slate-400">No active positions or orders. Bot is waiting for trading opportunities.</p>
        </div>
      )}

      {/* Error States */}
      {accountError && (
        <div className="rounded-md border border-red-500/50 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          Failed to fetch account data: {accountError.message}
        </div>
      )}

      {tradingError && (
        <div className="rounded-md border border-yellow-500/50 bg-yellow-500/10 px-4 py-3 text-sm text-yellow-200">
          Trading status unavailable: {tradingError.message}. Bot may not be running.
        </div>
      )}

      {/* Last Update Time */}
      <div className="text-xs text-slate-500 text-center">
        Last updated: {lastUpdate.toLocaleTimeString()}
      </div>
    </main>
  );
}
