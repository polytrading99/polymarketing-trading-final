"use client";

import useSWR from "swr";
import { ArrowRightCircle, Loader2, RefreshCcw, Play, Square, Database, Globe, Plus, Filter } from "lucide-react";
import { fetchMarkets, fetchCurrentPolymarketMarkets, startBot, stopBot, updateMarketStatus, addMarketToDatabase, type Market, type PolymarketMarket } from "../lib/api";
import { useCallback, useState } from "react";
import clsx from "clsx";
import { DashboardStats, PnLChart } from "./dashboard";

const fetcher = () => fetchMarkets();

type ViewMode = "database" | "live";
type SortMode = "rewards" | "min_size" | "min_size_desc";

export default function HomePage() {
  const [viewMode, setViewMode] = useState<ViewMode>("database");
  const [sortMode, setSortMode] = useState<SortMode>("min_size"); // Default to sorting by min_size (smallest first)
  const [showSmallMarketsOnly, setShowSmallMarketsOnly] = useState(true); // Default to showing only small markets
  const { data, error, isLoading, mutate } = useSWR<Market[]>("/markets", fetcher, {
    refreshInterval: 10_000
  });
  const { 
    data: liveMarkets, 
    error: liveError, 
    isLoading: liveLoading, 
    mutate: mutateLive 
  } = useSWR<PolymarketMarket[]>(
    viewMode === "live" ? `/markets/current?min_size_max=${showSmallMarketsOnly ? 10 : ''}&sort_by=${sortMode}` : null,
    () => fetchCurrentPolymarketMarkets(100, showSmallMarketsOnly ? 10 : undefined, sortMode),
    {
      refreshInterval: viewMode === "live" ? 30_000 : 0 // Refresh every 30s when viewing live
    }
  );
  const [loadingMarkets, setLoadingMarkets] = useState<Set<string>>(new Set());
  const [addingMarkets, setAddingMarkets] = useState<Set<string>>(new Set());

  const onRefresh = useCallback(() => {
    if (viewMode === "database") {
      mutate();
    } else {
      mutateLive();
    }
  }, [mutate, mutateLive, viewMode]);

  const handleAddMarket = useCallback(async (market: PolymarketMarket) => {
    if (!market.token_yes || !market.token_no || !market.condition_id) {
      alert("Market is missing required information (tokens or condition_id)");
      return;
    }
    
    if (addingMarkets.has(market.condition_id)) return;
    
    setAddingMarkets(prev => new Set(prev).add(market.condition_id));
    try {
      await addMarketToDatabase({
        question: market.question,
        condition_id: market.condition_id,
        token_yes: market.token_yes,
        token_no: market.token_no,
        neg_risk: false, // Default to false, can be updated later
        tick_size: 0.01,
        trade_size: 1.0,
        min_size: market.min_size,
        max_spread: market.max_spread,
        metadata: {
          market_slug: market.market_slug,
          end_date_iso: market.end_date_iso,
          rewards_daily_rate: market.rewards_daily_rate,
        }
      });
      alert("Market added to database! Switch to Database view to activate it.");
      await mutate(); // Refresh database markets
    } catch (err) {
      console.error("Failed to add market:", err);
      alert(err instanceof Error ? err.message : "Failed to add market");
    } finally {
      setAddingMarkets(prev => {
        const next = new Set(prev);
        next.delete(market.condition_id);
        return next;
      });
    }
  }, [addingMarkets, mutate]);

  const handleToggleMarket = useCallback(async (market: Market) => {
    if (loadingMarkets.has(market.id)) return;
    
    setLoadingMarkets(prev => new Set(prev).add(market.id));
    try {
      if (market.status === "active") {
        await stopBot(market.id, "Stopped via UI");
        await updateMarketStatus(market.id, "inactive");
      } else {
        await startBot(market.id, market.active_strategy || undefined);
        await updateMarketStatus(market.id, "active", market.active_strategy || undefined);
      }
      await mutate();
    } catch (err) {
      console.error("Failed to toggle market:", err);
      alert(err instanceof Error ? err.message : "Failed to toggle market");
    } finally {
      setLoadingMarkets(prev => {
        const next = new Set(prev);
        next.delete(market.id);
        return next;
      });
    }
  }, [loadingMarkets, mutate]);

  return (
    <main className="space-y-6">
      <header className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-3xl font-semibold">Poly Maker Dashboard</h1>
          <p className="text-sm text-slate-400">
            {viewMode === "database" 
              ? "Control which markets are active and monitor strategy assignments."
              : "Browse currently open markets from Polymarket (live data)."}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 rounded-md border border-slate-700 bg-slate-900 p-1">
            <button
              onClick={() => setViewMode("database")}
              className={clsx(
                "inline-flex items-center gap-2 rounded px-3 py-1.5 text-sm font-medium transition-colors",
                viewMode === "database"
                  ? "bg-slate-800 text-slate-100"
                  : "text-slate-400 hover:text-slate-200"
              )}
            >
              <Database className="h-4 w-4" />
              Database
            </button>
            <button
              onClick={() => setViewMode("live")}
              className={clsx(
                "inline-flex items-center gap-2 rounded px-3 py-1.5 text-sm font-medium transition-colors",
                viewMode === "live"
                  ? "bg-slate-800 text-slate-100"
                  : "text-slate-400 hover:text-slate-200"
              )}
            >
              <Globe className="h-4 w-4" />
              Live Markets
            </button>
          </div>
          <button
            onClick={onRefresh}
            className="inline-flex items-center gap-2 rounded-md border border-slate-700 bg-slate-900 px-4 py-2 text-sm font-medium text-slate-100 hover:bg-slate-800"
          >
            <RefreshCcw className="h-4 w-4" />
            Refresh
          </button>
          {viewMode === "live" && (
            <>
              <button
                onClick={() => {
                  setShowSmallMarketsOnly(!showSmallMarketsOnly);
                  mutateLive();
                }}
                className={clsx(
                  "inline-flex items-center gap-2 rounded-md border px-4 py-2 text-sm font-medium transition-colors",
                  showSmallMarketsOnly
                    ? "border-emerald-500/50 bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30"
                    : "border-slate-700 bg-slate-900 text-slate-100 hover:bg-slate-800"
                )}
                title="Show only markets with min_size ≤ $10"
              >
                <Filter className="h-4 w-4" />
                Small Markets Only
              </button>
              <select
                value={sortMode}
                onChange={(e) => {
                  setSortMode(e.target.value as SortMode);
                  mutateLive();
                }}
                className="rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm font-medium text-slate-100 hover:bg-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="min_size">Sort: Smallest Min Size First</option>
                <option value="min_size_desc">Sort: Largest Min Size First</option>
                <option value="rewards">Sort: Highest Rewards First</option>
              </select>
            </>
          )}
        </div>
      </header>

      {viewMode === "database" && data && data.length > 0 ? (
        <>
          <DashboardStats markets={data} />
          <PnLChart markets={data} />
        </>
      ) : null}

      <div>
        <h2 className="text-2xl font-semibold mb-4">
          {viewMode === "database" ? "Database Markets" : "Live Markets from Polymarket"}
        </h2>

        {viewMode === "database" ? (
          <>
            {isLoading && (
              <div className="flex items-center gap-2 text-slate-400">
                <Loader2 className="h-5 w-5 animate-spin" />
                Loading markets…
              </div>
            )}

            {error && (
              <div className="rounded-md border border-red-500/50 bg-red-500/10 px-4 py-3 text-sm text-red-200">
                Failed to load markets: {error.message}
              </div>
            )}

            {data && data.length === 0 && (
              <div className="rounded-md border border-slate-700 bg-slate-900 px-4 py-6 text-center text-sm text-slate-400">
                No markets found. Ensure the backend sync has populated the database.
              </div>
            )}

            {data && data.length > 0 && (
              <section className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                {data.map((market) => (
            <article
              key={market.id}
              className="group flex flex-col rounded-lg border border-slate-800 bg-slate-900/60 p-5 shadow-lg transition-all hover:border-slate-700 hover:bg-slate-900/80"
            >
              <div className="space-y-4">
                <div className="flex items-start justify-between gap-3">
                  <h2 className="flex-1 text-lg font-semibold leading-tight text-slate-100 line-clamp-2">
                    {market.question}
                  </h2>
                  <div className="flex items-center gap-2 shrink-0">
                    <span
                      className={clsx(
                        "rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wide",
                        market.status === "active"
                          ? "bg-emerald-500/20 text-emerald-300 ring-1 ring-emerald-500/30"
                          : "bg-slate-700/50 text-slate-400"
                      )}
                    >
                      {market.status}
                    </span>
                    <button
                      onClick={() => handleToggleMarket(market)}
                      disabled={loadingMarkets.has(market.id)}
                      className={clsx(
                        "rounded-md p-1.5 transition-colors",
                        market.status === "active"
                          ? "text-red-400 hover:bg-red-500/20 hover:text-red-300"
                          : "text-emerald-400 hover:bg-emerald-500/20 hover:text-emerald-300",
                        loadingMarkets.has(market.id) && "opacity-50 cursor-not-allowed"
                      )}
                      title={market.status === "active" ? "Stop bot" : "Start bot"}
                    >
                      {loadingMarkets.has(market.id) ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : market.status === "active" ? (
                        <Square className="h-4 w-4" />
                      ) : (
                        <Play className="h-4 w-4" />
                      )}
                    </button>
                  </div>
                </div>
                
                <div className="space-y-2.5 text-sm">
                  <div>
                    <span className="font-medium text-slate-300">Condition:</span>
                    <p className="mt-0.5 font-mono text-xs text-slate-500 break-all">
                      {market.condition_id}
                    </p>
                  </div>
                  
                  <div>
                    <span className="font-medium text-slate-300">Tokens:</span>
                    <div className="mt-0.5 space-y-0.5 font-mono text-xs text-slate-500">
                      <p className="break-all">YES: {market.token_yes}</p>
                      <p className="break-all">NO: {market.token_no}</p>
                    </div>
                  </div>
                  
                  <div className="flex items-center gap-4">
                    <div>
                      <span className="font-medium text-slate-300">Strategy:</span>{" "}
                      <span className="text-slate-400">
                        {market.active_strategy ?? (
                          <span className="italic text-slate-500">None</span>
                        )}
                      </span>
                    </div>
                    <div>
                      <span className="font-medium text-slate-300">Neg Risk:</span>{" "}
                      <span className={clsx(
                        "font-semibold",
                        market.neg_risk ? "text-amber-400" : "text-slate-400"
                      )}>
                        {market.neg_risk ? "Yes" : "No"}
                      </span>
                    </div>
                  </div>
                  
                  {(market.pnl_total !== null && market.pnl_total !== undefined) || market.position_count > 0 ? (
                    <div className="grid grid-cols-2 gap-3 pt-2 border-t border-slate-800">
                      {market.pnl_total !== null && market.pnl_total !== undefined && (
                        <div>
                          <span className="text-xs text-slate-500">Total PnL</span>
                          <p className={clsx(
                            "text-sm font-semibold",
                            market.pnl_total >= 0 ? "text-emerald-400" : "text-red-400"
                          )}>
                            {market.pnl_total >= 0 ? "+" : ""}
                            {market.pnl_total.toFixed(2)} USDC
                          </p>
                        </div>
                      )}
                      {market.fees_paid !== null && market.fees_paid !== undefined && (
                        <div>
                          <span className="text-xs text-slate-500">Fees Paid</span>
                          <p className="text-sm font-medium text-slate-400">
                            {market.fees_paid.toFixed(4)} USDC
                          </p>
                        </div>
                      )}
                      {market.position_count > 0 && (
                        <div>
                          <span className="text-xs text-slate-500">Positions</span>
                          <p className="text-sm font-medium text-slate-400">
                            {market.position_count}
                          </p>
                        </div>
                      )}
                    </div>
                  ) : null}
                </div>
              </div>
              
              <footer className="mt-4 flex items-center justify-between border-t border-slate-800 pt-3 text-xs text-slate-500">
                <span className="font-mono truncate flex-1 mr-2" title={market.id}>
                  ID: {market.id}
                </span>
                <ArrowRightCircle className="h-4 w-4 shrink-0 text-slate-600 transition-colors group-hover:text-slate-400" />
              </footer>
            </article>
          ))}
        </section>
      )}
          </>
        ) : (
          <>
            {liveLoading && (
              <div className="flex items-center gap-2 text-slate-400">
                <Loader2 className="h-5 w-5 animate-spin" />
                Fetching live markets from Polymarket...
              </div>
            )}

            {liveError && (
              <div className="rounded-md border border-red-500/50 bg-red-500/10 px-4 py-3 text-sm text-red-200">
                Failed to load live markets: {liveError.message}
              </div>
            )}

            {liveMarkets && liveMarkets.length === 0 && (
              <div className="rounded-md border border-slate-700 bg-slate-900 px-4 py-6 text-center text-sm text-slate-400">
                No live markets found. Check your connection to Polymarket API.
              </div>
            )}

            {liveMarkets && liveMarkets.length > 0 && (
              <>
                <div className="mb-4 rounded-md border border-blue-500/50 bg-blue-500/10 px-4 py-3 text-sm text-blue-200">
                  Showing {liveMarkets.length} {showSmallMarketsOnly ? "small " : ""}markets from Polymarket (min_size ≤ $10) - {sortMode === "min_size" ? "sorted by smallest min_size first" : sortMode === "rewards" ? "sorted by highest rewards" : "sorted by largest min_size first"}
                </div>
                <section className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                  {liveMarkets.map((market, idx) => (
                    <article
                      key={market.condition_id || idx}
                      className="group flex flex-col rounded-lg border border-slate-800 bg-slate-900/60 p-5 shadow-lg transition-all hover:border-slate-700 hover:bg-slate-900/80"
                    >
                      <div className="space-y-4">
                        <div className="flex items-start justify-between gap-3">
                          <h2 className="flex-1 text-lg font-semibold leading-tight text-slate-100 line-clamp-2">
                            {market.question}
                          </h2>
                          <div className="flex items-center gap-2 shrink-0">
                            <span className="rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wide bg-blue-500/20 text-blue-300 ring-1 ring-blue-500/30">
                              Live
                            </span>
                            {market.token_yes && market.token_no && (
                              <button
                                onClick={() => handleAddMarket(market)}
                                disabled={addingMarkets.has(market.condition_id)}
                                className={clsx(
                                  "rounded-md p-1.5 transition-colors text-emerald-400 hover:bg-emerald-500/20 hover:text-emerald-300",
                                  addingMarkets.has(market.condition_id) && "opacity-50 cursor-not-allowed"
                                )}
                                title="Add to Database"
                              >
                                {addingMarkets.has(market.condition_id) ? (
                                  <Loader2 className="h-4 w-4 animate-spin" />
                                ) : (
                                  <Plus className="h-4 w-4" />
                                )}
                              </button>
                            )}
                          </div>
                        </div>
                        
                        <div className="space-y-2.5 text-sm">
                          <div>
                            <span className="font-medium text-slate-300">Condition:</span>
                            <p className="mt-0.5 font-mono text-xs text-slate-500 break-all">
                              {market.condition_id}
                            </p>
                          </div>
                          
                          {market.outcome_yes && market.outcome_no && (
                            <div>
                              <span className="font-medium text-slate-300">Outcomes:</span>
                              <div className="mt-0.5 space-y-0.5 text-xs text-slate-400">
                                <p>YES: {market.outcome_yes}</p>
                                <p>NO: {market.outcome_no}</p>
                              </div>
                            </div>
                          )}
                          
                          {market.token_yes && market.token_no && (
                            <div>
                              <span className="font-medium text-slate-300">Tokens:</span>
                              <div className="mt-0.5 space-y-0.5 font-mono text-xs text-slate-500">
                                <p className="break-all">YES: {market.token_yes}</p>
                                <p className="break-all">NO: {market.token_no}</p>
                              </div>
                            </div>
                          )}
                          
                          <div className="flex items-center gap-4 flex-wrap">
                            {market.end_date_iso && (
                              <div>
                                <span className="font-medium text-slate-300">End Date:</span>{" "}
                                <span className="text-slate-400 text-xs">
                                  {new Date(market.end_date_iso).toLocaleDateString()}
                                </span>
                              </div>
                            )}
                            {market.rewards_daily_rate !== null && market.rewards_daily_rate !== undefined && (
                              <div>
                                <span className="font-medium text-slate-300">Daily Reward:</span>{" "}
                                <span className="text-emerald-400 font-semibold">
                                  {(market.rewards_daily_rate * 100).toFixed(2)}%
                                </span>
                              </div>
                            )}
                          </div>
                          
                          {(market.min_size !== null && market.min_size !== undefined) || 
                           (market.max_spread !== null && market.max_spread !== undefined) ? (
                            <div className="grid grid-cols-2 gap-3 pt-2 border-t border-slate-800">
                              {market.min_size !== null && market.min_size !== undefined && (
                                <div>
                                  <span className="text-xs text-slate-500">Min Size</span>
                                  <p className={clsx(
                                    "text-sm font-medium",
                                    market.min_size <= 10 ? "text-emerald-400 font-semibold" : "text-slate-400"
                                  )}>
                                    ${market.min_size} USDC
                                    {market.min_size <= 10 && <span className="ml-1 text-xs">✓ Good for $10</span>}
                                  </p>
                                </div>
                              )}
                              {market.max_spread !== null && market.max_spread !== undefined && (
                                <div>
                                  <span className="text-xs text-slate-500">Max Spread</span>
                                  <p className="text-sm font-medium text-slate-400">
                                    {market.max_spread}%
                                  </p>
                                </div>
                              )}
                            </div>
                          ) : null}
                        </div>
                      </div>
                      
                      <footer className="mt-4 flex items-center justify-between border-t border-slate-800 pt-3 text-xs text-slate-500">
                        {market.market_slug && (
                          <span className="font-mono truncate flex-1 mr-2" title={market.market_slug}>
                            Slug: {market.market_slug}
                          </span>
                        )}
                        <ArrowRightCircle className="h-4 w-4 shrink-0 text-slate-600 transition-colors group-hover:text-slate-400" />
                      </footer>
                    </article>
                  ))}
                </section>
              </>
            )}
          </>
        )}
      </div>
    </main>
  );
}


