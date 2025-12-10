"use client";

import { useState, useCallback } from "react";
import useSWR from "swr";
import { Play, Square, RefreshCw, Loader2, Settings, AlertCircle, CheckCircle2 } from "lucide-react";
import {
  getMMBotStatus,
  getMMBotConfig,
  startMMBot,
  stopMMBot,
  restartMMBot,
  updateMMBotConfig,
  getAccountSummary,
  type MMBotStatus,
  type MMBotConfig,
  type AccountSummary,
} from "../../lib/api";
import clsx from "clsx";

const statusFetcher = () => getMMBotStatus();
const configFetcher = () => getMMBotConfig();

export default function MMBotPage() {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showConfig, setShowConfig] = useState(false);

  const { data: status, error: statusError, mutate: mutateStatus } = useSWR<MMBotStatus>(
    "/mm-bot/status",
    statusFetcher,
    { refreshInterval: 5000 }
  );

  const { data: config, error: configError, mutate: mutateConfig } = useSWR<MMBotConfig>(
    "/mm-bot/config",
    configFetcher,
    { refreshInterval: 10000 }
  );

  const { data: accountSummary, error: accountError } = useSWR<AccountSummary>(
    "/mm-bot/account/summary",
    () => getAccountSummary(),
    { refreshInterval: 10000 }
  );

  const handleStart = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      await startMMBot();
      await mutateStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start bot");
    } finally {
      setIsLoading(false);
    }
  }, [mutateStatus]);

  const handleStop = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      await stopMMBot();
      await mutateStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to stop bot");
    } finally {
      setIsLoading(false);
    }
  }, [mutateStatus]);

  const handleRestart = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      await restartMMBot();
      await mutateStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to restart bot");
    } finally {
      setIsLoading(false);
    }
  }, [mutateStatus]);

  const isRunning = status?.is_running ?? false;
  const mainAlive = status?.main_process?.alive ?? false;
  const tradeAlive = status?.trade_process?.alive ?? false;

  return (
    <main className="space-y-6 p-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-semibold">Market Making Bot</h1>
          <p className="text-sm text-slate-400 mt-1">
            Control the Polymarket BTC 15m Up/Down market making bot
          </p>
        </div>
        <button
          onClick={() => setShowConfig(!showConfig)}
          className="inline-flex items-center gap-2 rounded-md border border-slate-700 bg-slate-900 px-4 py-2 text-sm font-medium text-slate-100 hover:bg-slate-800"
        >
          <Settings className="h-4 w-4" />
          {showConfig ? "Hide" : "Show"} Config
        </button>
      </header>

      {error && (
        <div className="rounded-md border border-red-500/50 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          {error}
        </div>
      )}

      {/* Account Summary */}
      {accountSummary && (
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-6">
          <h2 className="text-xl font-semibold mb-4">Account Status</h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Balance */}
            <div className="rounded-md border border-slate-800 bg-slate-900/40 p-4">
              <div className="text-sm text-slate-400 mb-1">USDC Balance</div>
              {accountSummary.balance?.success ? (
                <div className="text-2xl font-semibold text-emerald-400">
                  ${(accountSummary.balance.balance?.usdc || 0).toFixed(2)}
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
                    Total Value: ${(accountSummary.positions.total_value_usd || 0).toFixed(2)}
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
          </div>

          {/* Wallet Address */}
          <div className="mt-4 pt-4 border-t border-slate-800">
            <div className="text-xs text-slate-400">Wallet Address</div>
            <div className="text-sm font-mono text-slate-300 mt-1">
              {accountSummary.wallet_address}
            </div>
          </div>

          {/* Recent Positions */}
          {accountSummary.positions?.success && accountSummary.positions.positions?.length > 0 && (
            <div className="mt-4 pt-4 border-t border-slate-800">
              <div className="text-sm font-semibold text-slate-300 mb-2">Recent Positions</div>
              <div className="space-y-2 max-h-40 overflow-y-auto">
                {accountSummary.positions.positions.slice(0, 5).map((pos, idx) => {
                  const size = pos.size || 0;
                  const avgPrice = pos.avgPrice || pos.avg_price || 0;
                  const value = size * avgPrice;
                  return (
                    <div key={idx} className="text-xs bg-slate-900/40 p-2 rounded">
                      <div className="flex justify-between">
                        <span className="text-slate-300 truncate">
                          {pos.title || pos.asset || "Unknown"}
                        </span>
                        <span className="text-slate-400 ml-2">
                          {size.toFixed(2)} @ ${avgPrice.toFixed(4)}
                        </span>
                      </div>
                      <div className="text-slate-500 mt-1">
                        Value: ${value.toFixed(2)}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Recent Orders */}
          {accountSummary.orders?.success && accountSummary.orders.orders?.length > 0 && (
            <div className="mt-4 pt-4 border-t border-slate-800">
              <div className="text-sm font-semibold text-slate-300 mb-2">Recent Orders</div>
              <div className="space-y-2 max-h-40 overflow-y-auto">
                {accountSummary.orders.orders.slice(0, 5).map((order, idx) => {
                  const orderId = order.id || order.order_id || order.orderId || "Unknown";
                  const side = order.side || "UNKNOWN";
                  const price = order.price || 0;
                  const size = order.size || order.remainingSize || 0;
                  return (
                    <div key={idx} className="text-xs bg-slate-900/40 p-2 rounded">
                      <div className="flex justify-between">
                        <span className={side === "BUY" ? "text-emerald-400" : "text-red-400"}>
                          {side}
                        </span>
                        <span className="text-slate-300">
                          {size.toFixed(2)} @ ${price.toFixed(4)}
                        </span>
                      </div>
                      <div className="text-slate-500 mt-1 font-mono text-xs">
                        {orderId.slice(0, 20)}...
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {accountError && (
        <div className="rounded-md border border-yellow-500/50 bg-yellow-500/10 px-4 py-3 text-sm text-yellow-200">
          Failed to load account information: {accountError.message}
        </div>
      )}

      {/* Status Card */}
      <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-6">
        <h2 className="text-xl font-semibold mb-4">Bot Status</h2>
        
        {statusError ? (
          <div className="text-red-400">Failed to load status</div>
        ) : !status ? (
          <div className="flex items-center gap-2 text-slate-400">
            <Loader2 className="h-5 w-5 animate-spin" />
            Loading status...
          </div>
        ) : (
          <>
          <div className="space-y-4">
            <div className="flex items-center gap-3">
              <div className={clsx(
                "h-3 w-3 rounded-full",
                isRunning && mainAlive && tradeAlive ? "bg-emerald-500" : "bg-red-500"
              )} />
              <span className="text-lg font-medium">
                {isRunning && mainAlive && tradeAlive ? "Running" : "Stopped"}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="rounded-md border border-slate-800 bg-slate-900/40 p-4">
                <div className="text-sm text-slate-400 mb-1">Main Process</div>
                {status.main_process ? (
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      {status.main_process.alive ? (
                        <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                      ) : (
                        <AlertCircle className="h-4 w-4 text-red-400" />
                      )}
                      <span className="text-sm font-mono">
                        PID: {status.main_process.pid}
                      </span>
                    </div>
                    {status.main_process.returncode !== null && (
                      <div className="text-xs text-slate-500">
                        Exit code: {status.main_process.returncode}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-sm text-slate-500">Not started</div>
                )}
              </div>

              <div className="rounded-md border border-slate-800 bg-slate-900/40 p-4">
                <div className="text-sm text-slate-400 mb-1">Trade Process</div>
                {status.trade_process ? (
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      {status.trade_process.alive ? (
                        <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                      ) : (
                        <AlertCircle className="h-4 w-4 text-red-400" />
                      )}
                      <span className="text-sm font-mono">
                        PID: {status.trade_process.pid}
                      </span>
                    </div>
                    {status.trade_process.returncode !== null && (
                      <div className="text-xs text-slate-500">
                        Exit code: {status.trade_process.returncode}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-sm text-slate-500">Not started</div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Control Buttons */}
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
              Restart Bot
            </button>
          </>
        )}
      </div>

      {/* Configuration */}
      {showConfig && (
        <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-6">
          <h2 className="text-xl font-semibold mb-4">Configuration</h2>
          {configError ? (
            <div className="text-red-400">Failed to load config</div>
          ) : !config ? (
            <div className="flex items-center gap-2 text-slate-400">
              <Loader2 className="h-5 w-5 animate-spin" />
              Loading config...
            </div>
          ) : (
            <div className="space-y-4">
              <div className="rounded-md border border-slate-800 bg-slate-900/40 p-4">
                <h3 className="text-sm font-semibold text-slate-300 mb-2">API Settings</h3>
                <div className="space-y-2 text-sm">
                  <div>
                    <span className="text-slate-400">Chain ID:</span>{" "}
                    <span className="text-slate-200">{config.api.CHAIN_ID}</span>
                  </div>
                  <div>
                    <span className="text-slate-400">Signature Type:</span>{" "}
                    <span className="text-slate-200">{config.api.SIGNATURE_TYPE}</span>
                  </div>
                  <div>
                    <span className="text-slate-400">Proxy Address:</span>{" "}
                    <span className="text-slate-200 font-mono text-xs">
                      {config.api.PROXY_ADDRESS || "None"}
                    </span>
                  </div>
                </div>
              </div>

              <div className="rounded-md border border-slate-800 bg-slate-900/40 p-4">
                <h3 className="text-sm font-semibold text-slate-300 mb-2">Strategy 1</h3>
                <div className="text-xs text-slate-400">
                  {config.strategies.strategy_1.ENABLED ? (
                    <span className="text-emerald-400">Enabled</span>
                  ) : (
                    <span className="text-slate-500">Disabled</span>
                  )}
                </div>
              </div>

              <div className="rounded-md border border-slate-800 bg-slate-900/40 p-4">
                <h3 className="text-sm font-semibold text-slate-300 mb-2">Strategy 2</h3>
                <div className="text-xs text-slate-400">
                  {config.strategies.strategy_2.ENABLED ? (
                    <span className="text-emerald-400">Enabled</span>
                  ) : (
                    <span className="text-slate-500">Disabled</span>
                  )}
                </div>
              </div>

              <div className="text-xs text-slate-500 mt-4">
                Note: Configuration changes require a bot restart to take effect.
              </div>
            </div>
          )}
        </div>
      )}
    </main>
  );
}

