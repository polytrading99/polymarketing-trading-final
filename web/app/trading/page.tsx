"use client";

import { useState, useCallback } from "react";
import useSWR from "swr";
import { Play, Square, RefreshCw, Loader2, TrendingUp, TrendingDown, DollarSign, Package, ShoppingCart, Activity } from "lucide-react";
import {
  getTradingStatus,
  getAccountSummary,
  startMMBot,
  stopMMBot,
  restartMMBot,
  getMMBotStatus,
  type TradingStatus,
  type AccountSummary,
  type MMBotStatus,
} from "../../lib/api";
import clsx from "clsx";

const tradingStatusFetcher = () => getTradingStatus();
const accountFetcher = () => getAccountSummary();
const botStatusFetcher = () => getMMBotStatus();

export default function TradingPage() {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: tradingStatus, error: tradingError, mutate: mutateTrading } = useSWR<TradingStatus>(
    "/trading/status",
    tradingStatusFetcher,
    { refreshInterval: 3000 } // Update every 3 seconds
  );

  const { data: accountSummary, error: accountError, mutate: mutateAccount } = useSWR<AccountSummary>(
    "/mm-bot/account/summary",
    accountFetcher,
    { refreshInterval: 5000 } // Update every 5 seconds
  );

  const { data: botStatus, error: botStatusError, mutate: mutateBotStatus } = useSWR<MMBotStatus>(
    "/mm-bot/status",
    botStatusFetcher,
    { refreshInterval: 5000 }
  );

  const handleStart = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      await startMMBot();
      await mutateBotStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start bot");
    } finally {
      setIsLoading(false);
    }
  }, [mutateBotStatus]);

  const handleStop = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      await stopMMBot();
      await mutateBotStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to stop bot");
    } finally {
      setIsLoading(false);
    }
  }, [mutateBotStatus]);

  const handleRestart = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      await restartMMBot();
      await mutateBotStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to restart bot");
    } finally {
      setIsLoading(false);
    }
  }, [mutateBotStatus]);

  const isRunning = botStatus?.is_running ?? false;
  const mainAlive = botStatus?.main_process?.alive ?? false;

  // Calculate totals
  const totalPositionValue = tradingStatus?.success
    ? Object.values(tradingStatus.positions || {}).reduce(
        (sum, pos: any) => sum + (pos.value || 0),
        0
      )
    : 0;

  const totalOpenOrders = tradingStatus?.total_orders || 0;

  return (
    <main className="space-y-6 p-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-semibold">Trading Dashboard</h1>
          <p className="text-sm text-slate-400 mt-1">
            Real-time trading status and account information
          </p>
        </div>
        <div className="flex items-center gap-3">
          {!isRunning ? (
            <button
              onClick={handleStart}
              disabled={isLoading}
              className="inline-flex items-center gap-2 rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Play className="h-4 w-4" />
              )}
              Start Bot
            </button>
          ) : (
            <>
              <button
                onClick={handleStop}
                disabled={isLoading}
                className="inline-flex items-center gap-2 rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Square className="h-4 w-4" />
                )}
                Stop Bot
              </button>
              <button
                onClick={handleRestart}
                disabled={isLoading}
                className="inline-flex items-center gap-2 rounded-md border border-slate-700 bg-slate-900 px-4 py-2 text-sm font-medium text-slate-100 hover:bg-slate-800 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCw className="h-4 w-4" />
                )}
                Restart
              </button>
            </>
          )}
        </div>
      </header>

      {error && (
        <div className="rounded-md border border-red-500/50 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          {error}
        </div>
      )}

      {/* Bot Status */}
      <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-6">
        <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
          <Activity className="h-5 w-5" />
          Bot Status
        </h2>
        <div className="flex items-center gap-3">
          <div className={clsx(
            "h-4 w-4 rounded-full",
            isRunning && mainAlive ? "bg-emerald-500 animate-pulse" : "bg-red-500"
          )} />
          <span className="text-lg font-medium">
            {isRunning && mainAlive ? "Running" : "Stopped"}
          </span>
          {botStatus?.main_process && (
            <span className="text-sm text-slate-400 font-mono">
              PID: {botStatus.main_process.pid}
            </span>
          )}
        </div>
        {botStatus?.recent_errors && botStatus.recent_errors.length > 0 && (
          <div className="mt-4 p-3 rounded-md border border-red-500/30 bg-red-500/10">
            <div className="text-sm font-semibold text-red-300 mb-2">Recent Errors</div>
            {botStatus.recent_errors.slice(0, 2).map((error: any, idx: number) => (
              <div key={idx} className="text-xs text-slate-300 mt-1">
                {error.type}: {error.message}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Account Summary */}
      {accountSummary && (
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-6">
          <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
            <DollarSign className="h-5 w-5" />
            Account Summary
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            {/* Balance */}
            <div className="rounded-md border border-slate-800 bg-slate-900/40 p-4">
              <div className="text-sm text-slate-400 mb-1">USDC Balance</div>
              {accountSummary.balance?.success ? (
                <div className="text-2xl font-semibold text-emerald-400">
                  ${(Number(accountSummary.balance.balance?.usdc) || 0).toFixed(2)}
                </div>
              ) : (
                <div className="text-sm text-red-400">
                  {accountSummary.balance?.error || "Unable to fetch"}
                </div>
              )}
            </div>

            {/* Positions */}
            <div className="rounded-md border border-slate-800 bg-slate-900/40 p-4">
              <div className="text-sm text-slate-400 mb-1">Active Positions</div>
              {accountSummary.positions?.success ? (
                <div>
                  <div className="text-2xl font-semibold text-blue-400">
                    {accountSummary.positions.total_positions || 0}
                  </div>
                  <div className="text-xs text-slate-500 mt-1">
                    Value: ${(Number(accountSummary.positions.total_value_usd) || 0).toFixed(2)}
                  </div>
                </div>
              ) : (
                <div className="text-sm text-red-400">
                  {accountSummary.positions?.error || "Unable to fetch"}
                </div>
              )}
            </div>

            {/* Open Orders */}
            <div className="rounded-md border border-slate-800 bg-slate-900/40 p-4">
              <div className="text-sm text-slate-400 mb-1">Open Orders</div>
              {accountSummary.orders?.success ? (
                <div className="text-2xl font-semibold text-yellow-400">
                  {accountSummary.orders.total_orders || 0}
                </div>
              ) : (
                <div className="text-sm text-red-400">
                  {accountSummary.orders?.error || "Unable to fetch"}
                </div>
              )}
            </div>

            {/* Trading Status Positions */}
            <div className="rounded-md border border-slate-800 bg-slate-900/40 p-4">
              <div className="text-sm text-slate-400 mb-1">Bot Positions</div>
              {tradingStatus?.success ? (
                <div>
                  <div className="text-2xl font-semibold text-purple-400">
                    {tradingStatus.total_positions || 0}
                  </div>
                  <div className="text-xs text-slate-500 mt-1">
                    Value: ${totalPositionValue.toFixed(2)}
                  </div>
                </div>
              ) : (
                <div className="text-sm text-slate-500">
                  {tradingStatus?.error || "Bot not running"}
                </div>
              )}
            </div>
          </div>

          {/* Wallet Address */}
          <div className="mt-4 pt-4 border-t border-slate-800">
            <div className="text-xs text-slate-400">Wallet Address</div>
            <div className="text-sm font-mono text-slate-300 mt-1">
              {accountSummary.wallet_address}
            </div>
          </div>
        </div>
      )}

      {/* Trading Status */}
      {tradingStatus?.success && (
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-6">
          <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
            <Activity className="h-5 w-5" />
            Real-Time Trading Status
          </h2>

          {/* Summary Stats */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <div className="rounded-md border border-slate-800 bg-slate-900/40 p-4">
              <div className="text-sm text-slate-400 mb-1">Active Markets</div>
              <div className="text-2xl font-semibold text-blue-400">
                {tradingStatus.active_markets || 0}
              </div>
            </div>
            <div className="rounded-md border border-slate-800 bg-slate-900/40 p-4">
              <div className="text-sm text-slate-400 mb-1">Open Orders</div>
              <div className="text-2xl font-semibold text-yellow-400">
                {totalOpenOrders}
              </div>
            </div>
            <div className="rounded-md border border-slate-800 bg-slate-900/40 p-4">
              <div className="text-sm text-slate-400 mb-1">Pending Trades</div>
              <div className="text-2xl font-semibold text-orange-400">
                {Object.keys(tradingStatus.performing_trades || {}).length}
              </div>
            </div>
          </div>

          {/* Positions */}
          {tradingStatus.positions && Object.keys(tradingStatus.positions).length > 0 && (
            <div className="mb-6">
              <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
                <Package className="h-4 w-4" />
                Current Positions
              </h3>
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {Object.entries(tradingStatus.positions).map(([token, pos]: [string, any]) => (
                  <div key={token} className="rounded-md border border-slate-800 bg-slate-900/40 p-3">
                    <div className="flex items-center justify-between">
                      <div className="flex-1">
                        <div className="text-sm font-mono text-slate-300 truncate">
                          {token.slice(0, 20)}...
                        </div>
                        <div className="text-xs text-slate-500 mt-1">
                          Size: {pos.size?.toFixed(4) || "0"} | Avg Price: ${pos.avgPrice?.toFixed(4) || "0"}
                        </div>
                      </div>
                      <div className="text-right">
                        <div className={clsx(
                          "text-lg font-semibold",
                          pos.size >= 0 ? "text-emerald-400" : "text-red-400"
                        )}>
                          {pos.size >= 0 ? "+" : ""}{pos.size?.toFixed(4) || "0"}
                        </div>
                        <div className="text-xs text-slate-400">
                          ${pos.value?.toFixed(2) || "0"}
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Open Orders */}
          {tradingStatus.orders && Object.keys(tradingStatus.orders).length > 0 && (
            <div className="mb-6">
              <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
                <ShoppingCart className="h-4 w-4" />
                Open Orders
              </h3>
              <div className="space-y-2 max-h-64 overflow-y-auto">
                {Object.entries(tradingStatus.orders).map(([token, order]: [string, any]) => {
                  const hasBuy = order.buy?.size > 0;
                  const hasSell = order.sell?.size > 0;
                  if (!hasBuy && !hasSell) return null;
                  
                  return (
                    <div key={token} className="rounded-md border border-slate-800 bg-slate-900/40 p-3">
                      <div className="text-sm font-mono text-slate-300 truncate mb-2">
                        {token.slice(0, 20)}...
                      </div>
                      <div className="grid grid-cols-2 gap-2">
                        {hasBuy && (
                          <div className="rounded p-2 bg-emerald-500/10 border border-emerald-500/30">
                            <div className="text-xs text-emerald-400 font-semibold">BUY</div>
                            <div className="text-sm text-slate-300">
                              {order.buy.size.toFixed(4)} @ ${order.buy.price.toFixed(4)}
                            </div>
                          </div>
                        )}
                        {hasSell && (
                          <div className="rounded p-2 bg-red-500/10 border border-red-500/30">
                            <div className="text-xs text-red-400 font-semibold">SELL</div>
                            <div className="text-sm text-slate-300">
                              {order.sell.size.toFixed(4)} @ ${order.sell.price.toFixed(4)}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Market Data */}
          {tradingStatus.market_data && Object.keys(tradingStatus.market_data).length > 0 && (
            <div>
              <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
                <TrendingUp className="h-4 w-4" />
                Market Data
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-h-64 overflow-y-auto">
                {Object.entries(tradingStatus.market_data).slice(0, 10).map(([asset, data]: [string, any]) => (
                  <div key={asset} className="rounded-md border border-slate-800 bg-slate-900/40 p-3">
                    <div className="text-xs font-mono text-slate-400 truncate mb-2">
                      {asset.slice(0, 20)}...
                    </div>
                    <div className="grid grid-cols-2 gap-2 text-xs">
                      <div>
                        <div className="text-slate-500">Bid</div>
                        <div className="text-emerald-400 font-semibold">
                          ${data.best_bid?.toFixed(4) || "0"}
                        </div>
                        <div className="text-slate-500 text-xs">
                          Size: {data.bid_size?.toFixed(2) || "0"}
                        </div>
                      </div>
                      <div>
                        <div className="text-slate-500">Ask</div>
                        <div className="text-red-400 font-semibold">
                          ${data.best_ask?.toFixed(4) || "0"}
                        </div>
                        <div className="text-slate-500 text-xs">
                          Size: {data.ask_size?.toFixed(2) || "0"}
                        </div>
                      </div>
                    </div>
                    {data.best_bid > 0 && data.best_ask > 0 && (
                      <div className="mt-2 text-xs text-slate-400">
                        Spread: {((data.best_ask - data.best_bid) / data.best_bid * 100).toFixed(2)}%
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {!tradingStatus.positions || Object.keys(tradingStatus.positions).length === 0 ? (
            <div className="text-center py-8 text-slate-400">
              No active positions or orders. Bot is waiting for trading opportunities.
            </div>
          ) : null}
        </div>
      )}

      {tradingError && (
        <div className="rounded-md border border-yellow-500/50 bg-yellow-500/10 px-4 py-3 text-sm text-yellow-200">
          Trading status unavailable: {tradingError.message}. Bot may not be running.
        </div>
      )}
    </main>
  );
}

