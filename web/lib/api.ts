const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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

export async function fetchCurrentPolymarketMarkets(limit: number = 100): Promise<PolymarketMarket[]> {
  const res = await fetch(`${API_BASE}/markets/current?limit=${limit}`, {
    next: { revalidate: 0 } // Always fetch fresh data
  });
  if (!res.ok) {
    throw new Error(`Failed to fetch current markets: ${res.status}`);
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


