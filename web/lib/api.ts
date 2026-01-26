// Auto-detect API URL based on current host
const getApiBase = () => {
  // If NEXT_PUBLIC_API_URL is set, use it
  if (typeof window !== 'undefined' && process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL;
  }
  
  // If running in browser, use the same host/port as the current page
  if (typeof window !== 'undefined') {
    const protocol = window.location.protocol;
    const hostname = window.location.hostname;
    // Use port 8000 for API (backend)
    return `${protocol}//${hostname}:8000`;
  }
  
  // Fallback for server-side rendering
  return process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
};

const API_BASE = getApiBase();

export type Market = {
  id: string;
  condition_id: string;
  question: string;
  status: string;
  neg_risk: boolean;
  token_yes: string;
  token_no: string;
  active_strategy?: string | null;
  pnl_total?: number | null;
  fees_paid?: number | null;
  position_count: number;
};

export async function fetchMarkets(): Promise<Market[]> {
  const res = await fetch(`${API_BASE}/markets`, {
    next: { revalidate: 5 }
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch markets: ${res.status}`);
  }
  return res.json();
}

export async function startBot(marketId: string, strategyName?: string): Promise<void> {
  const res = await fetch(`${API_BASE}/bot/${marketId}/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ strategy_name: strategyName || null }),
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: "Failed to start bot" }));
    throw new Error(error.detail || "Failed to start bot");
  }
}

export async function stopBot(marketId: string, reason?: string): Promise<void> {
  const res = await fetch(`${API_BASE}/bot/${marketId}/stop`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason: reason || null }),
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: "Failed to stop bot" }));
    throw new Error(error.detail || "Failed to stop bot");
  }
}

export async function updateMarketStatus(
  marketId: string,
  status: "active" | "inactive",
  strategyName?: string
): Promise<void> {
  const res = await fetch(`${API_BASE}/markets/${marketId}/status`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      status,
      activate_strategy: strategyName || null,
      deactivate: status === "inactive",
    }),
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: "Failed to update market status" }));
    throw new Error(error.detail || "Failed to update market status");
  }
}

export async function fetchCurrentPolymarketMarkets(
  limit: number = 100,
  minSizeMax?: number,
  sortBy: "rewards" | "min_size" | "min_size_desc" = "rewards"
): Promise<PolymarketMarket[]> {
  const params = new URLSearchParams({
    limit: limit.toString(),
  });
  if (minSizeMax !== undefined) {
    params.append("min_size_max", minSizeMax.toString());
  }
  if (sortBy) {
    params.append("sort_by", sortBy);
  }
  
  const res = await fetch(`${API_BASE}/markets/current?${params.toString()}`, {
    next: { revalidate: 0 } // Always fetch fresh data
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch current markets: ${res.status}`);
  }
  return res.json();
}

export type PolymarketMarket = {
  question: string;
  condition_id: string;
  market_slug?: string | null;
  end_date_iso?: string | null;
  token_yes?: string | null;
  token_no?: string | null;
  outcome_yes?: string | null;
  outcome_no?: string | null;
  rewards_daily_rate?: number | null;
  min_size?: number | null;
  max_spread?: number | null;
};

export async function addMarketToDatabase(market: {
  question: string;
  condition_id: string;
  token_yes: string;
  token_no: string;
  neg_risk?: boolean;
  tick_size?: number;
  trade_size?: number;
  min_size?: number;
  max_spread?: number;
  metadata?: Record<string, any>;
}): Promise<Market> {
  const res = await fetch(`${API_BASE}/markets`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question: market.question,
      condition_id: market.condition_id,
      token_yes: market.token_yes,
      token_no: market.token_no,
      neg_risk: market.neg_risk || false,
      tick_size: market.tick_size,
      trade_size: market.trade_size,
      min_size: market.min_size,
      max_spread: market.max_spread,
      metadata: market.metadata || {},
    }),
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: "Failed to add market" }));
    throw new Error(error.detail || "Failed to add market");
  }
  return res.json();
}

// MM Bot API
export type MMBotStatus = {
  is_running: boolean;
  main_process?: {
    pid: number;
    returncode: number | null;
    alive: boolean;
  } | null;
  trade_process?: {
    pid: number;
    returncode: number | null;
    alive: boolean;
  } | null;
  current_market?: {
    slug?: string;
    market_id?: string;
    bucket_ts?: number;
  } | null;
  recent_errors?: Array<{
    type: string;
    message: string;
    full_error?: string;
  }>;
};

export type MMBotConfig = {
  api: {
    PRIVATE_KEY: string;
    PROXY_ADDRESS: string | null;
    SIGNATURE_TYPE: number;
    CHAIN_ID: number;
  };
  strategies: {
    strategy_1: any;
    strategy_2: any;
  };
  [key: string]: any;
};

export async function getMMBotStatus(): Promise<MMBotStatus> {
  const res = await fetch(`${API_BASE}/mm-bot/status`);
  if (!res.ok) {
    throw new Error(`Failed to fetch MM bot status: ${res.status}`);
  }
  return res.json();
}

export async function getMMBotConfig(): Promise<MMBotConfig> {
  const res = await fetch(`${API_BASE}/mm-bot/config`);
  if (!res.ok) {
    throw new Error(`Failed to fetch MM bot config: ${res.status}`);
  }
  return res.json();
}

export async function startMMBot(): Promise<void> {
  const res = await fetch(`${API_BASE}/mm-bot/start`, {
    method: "POST",
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: "Failed to start MM bot" }));
    throw new Error(error.detail || "Failed to start MM bot");
  }
}

export async function stopMMBot(): Promise<void> {
  const res = await fetch(`${API_BASE}/mm-bot/stop`, {
    method: "POST",
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: "Failed to stop MM bot" }));
    throw new Error(error.detail || "Failed to stop MM bot");
  }
}

export async function restartMMBot(): Promise<void> {
  const res = await fetch(`${API_BASE}/mm-bot/restart`, {
    method: "POST",
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: "Failed to restart MM bot" }));
    throw new Error(error.detail || "Failed to restart MM bot");
  }
}

export async function updateMMBotConfig(config: Partial<MMBotConfig>): Promise<void> {
  const res = await fetch(`${API_BASE}/mm-bot/config`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ config }),
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: "Failed to update MM bot config" }));
    throw new Error(error.detail || "Failed to update MM bot config");
  }
}

// Account API
export type AccountBalance = {
  success: boolean;
  balance?: {
    usdc: number;
    currency: string;
  };
  error?: string;
  note?: string;
};

export type AccountPosition = {
  asset?: string;
  asset_id?: string;
  size?: number;
  avgPrice?: number;
  avg_price?: number;
  title?: string;
  market?: string;
  [key: string]: any;
};

export type AccountPositions = {
  success: boolean;
  positions: AccountPosition[];
  total_positions: number;
  total_value_usd: number;
  error?: string;
};

export type OpenOrder = {
  id?: string;
  order_id?: string;
  orderId?: string;
  market?: string;
  asset?: string;
  side?: string;
  price?: number;
  size?: number;
  remainingSize?: number;
  [key: string]: any;
};

export type AccountOrders = {
  success: boolean;
  orders: OpenOrder[];
  total_orders: number;
  error?: string;
};

export type AccountSummary = {
  balance: AccountBalance;
  positions: AccountPositions;
  orders: AccountOrders;
  wallet_address: string;
};

export async function getAccountBalance(): Promise<AccountBalance> {
  const res = await fetch(`${API_BASE}/mm-bot/account/balance`);
  if (!res.ok) {
    throw new Error(`Failed to fetch account balance: ${res.status}`);
  }
  return res.json();
}

export async function getAccountPositions(): Promise<AccountPositions> {
  const res = await fetch(`${API_BASE}/mm-bot/account/positions`);
  if (!res.ok) {
    throw new Error(`Failed to fetch account positions: ${res.status}`);
  }
  return res.json();
}

export async function getAccountOrders(): Promise<AccountOrders> {
  const res = await fetch(`${API_BASE}/mm-bot/account/orders`);
  if (!res.ok) {
    throw new Error(`Failed to fetch account orders: ${res.status}`);
  }
  return res.json();
}

export async function getAccountSummary(): Promise<AccountSummary> {
  const res = await fetch(`${API_BASE}/mm-bot/account/summary`);
  if (!res.ok) {
    throw new Error(`Failed to fetch account summary: ${res.status}`);
  }
  return res.json();
}

// Alias for cleaner API calls
export async function getAccountSummaryAlt(): Promise<AccountSummary> {
  return getAccountSummary();
}

// Credentials API
export type CredentialsInfo = {
  private_key_masked: string;
  proxy_address: string;
  signature_type: number;
  has_credentials: boolean;
};

export async function getCredentials(): Promise<CredentialsInfo> {
  const res = await fetch(`${API_BASE}/mm-bot/credentials`);
  if (!res.ok) {
    throw new Error(`Failed to fetch credentials: ${res.status}`);
  }
  return res.json();
}

export async function updateCredentials(
  privateKey: string,
  proxyAddress: string,
  signatureType: number = 2
): Promise<void> {
  try {
    const res = await fetch(`${API_BASE}/mm-bot/credentials`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        private_key: privateKey,
        proxy_address: proxyAddress,
        signature_type: signatureType,
      }),
    });
    
    if (!res.ok) {
      let errorMessage = "Failed to update credentials";
      try {
        const error = await res.json();
        errorMessage = error.detail || error.message || errorMessage;
      } catch {
        // If response is not JSON, use status text
        errorMessage = `HTTP ${res.status}: ${res.statusText || "Failed to update credentials"}`;
      }
      throw new Error(errorMessage);
    }
  } catch (err) {
    // Handle network errors
    if (err instanceof TypeError && err.message === "Failed to fetch") {
      throw new Error(`Network error: Cannot connect to API server at ${API_BASE}. Please check if the backend is running.`);
    }
    throw err;
  }
}

// Trading Status API
export type TradingStatus = {
  success: boolean;
  positions?: Record<string, {
    size: number;
    avgPrice: number;
    value: number;
  }>;
  orders?: Record<string, {
    buy: { price: number; size: number };
    sell: { price: number; size: number };
  }>;
  performing_trades?: Record<string, any>;
  market_data?: Record<string, {
    asset_id: string;
    best_bid: number;
    best_ask: number;
    bid_size: number;
    ask_size: number;
  }>;
  total_positions: number;
  total_orders: number;
  active_markets: number;
  error?: string;
};

export async function getTradingStatus(): Promise<TradingStatus> {
  const res = await fetch(`${API_BASE}/trading/status`);
  if (!res.ok) {
    throw new Error(`Failed to fetch trading status: ${res.status}`);
  }
  return res.json();
}


