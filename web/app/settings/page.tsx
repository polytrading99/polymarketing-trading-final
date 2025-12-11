"use client";

import { useState, useCallback, useEffect } from "react";
import useSWR from "swr";
import { Save, Eye, EyeOff, AlertCircle, CheckCircle2, Loader2, Key, Wallet } from "lucide-react";
import { getCredentials, updateCredentials, type CredentialsInfo } from "../../lib/api";
import clsx from "clsx";

const credentialsFetcher = () => getCredentials();

export default function SettingsPage() {
  const [privateKey, setPrivateKey] = useState("");
  const [proxyAddress, setProxyAddress] = useState("");
  const [signatureType, setSignatureType] = useState(2);
  const [showPrivateKey, setShowPrivateKey] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const { data: credentials, error: credentialsError, mutate: mutateCredentials } = useSWR<CredentialsInfo>(
    "/mm-bot/credentials",
    credentialsFetcher,
    { refreshInterval: 30000 }
  );

  // Load existing credentials when available
  useEffect(() => {
    if (credentials && credentials.has_credentials) {
      // Don't populate private key field for security (user must re-enter)
      setProxyAddress(credentials.proxy_address || "");
      setSignatureType(credentials.signature_type || 2);
    }
  }, [credentials]);

  const handleSave = useCallback(async () => {
    if (!privateKey.trim()) {
      setError("Private key is required");
      return;
    }

    if (!proxyAddress.trim()) {
      setError("Proxy address is required");
      return;
    }

    // Basic validation
    if (!privateKey.startsWith("0x") || privateKey.length !== 66) {
      setError("Invalid private key format. Must start with 0x and be 66 characters long.");
      return;
    }

    if (!proxyAddress.startsWith("0x") || proxyAddress.length !== 42) {
      setError("Invalid proxy address format. Must start with 0x and be 42 characters long.");
      return;
    }

    setIsSaving(true);
    setError(null);
    setSuccess(null);

    try {
      await updateCredentials(privateKey.trim(), proxyAddress.trim(), signatureType);
      setSuccess("Credentials updated successfully! Restart the bot to apply changes.");
      setPrivateKey(""); // Clear private key for security
      await mutateCredentials();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update credentials");
    } finally {
      setIsSaving(false);
    }
  }, [privateKey, proxyAddress, signatureType, mutateCredentials]);

  return (
    <main className="space-y-6 p-6 max-w-4xl mx-auto">
      <header>
        <h1 className="text-3xl font-semibold">Settings</h1>
        <p className="text-sm text-slate-400 mt-1">
          Configure your Polymarket trading credentials
        </p>
      </header>

      {error && (
        <div className="rounded-md border border-red-500/50 bg-red-500/10 px-4 py-3 text-sm text-red-200 flex items-start gap-2">
          <AlertCircle className="h-5 w-5 flex-shrink-0 mt-0.5" />
          <div>
            <div className="font-semibold">Error</div>
            <div>{error}</div>
          </div>
        </div>
      )}

      {success && (
        <div className="rounded-md border border-green-500/50 bg-green-500/10 px-4 py-3 text-sm text-green-200 flex items-start gap-2">
          <CheckCircle2 className="h-5 w-5 flex-shrink-0 mt-0.5" />
          <div>
            <div className="font-semibold">Success</div>
            <div>{success}</div>
          </div>
        </div>
      )}

      {/* Current Credentials Status */}
      {credentials && (
        <div className="rounded-md border border-slate-700 bg-slate-900/50 p-4">
          <h2 className="text-lg font-semibold mb-3">Current Credentials</h2>
          <div className="space-y-2 text-sm">
            <div className="flex items-center gap-2">
              <Key className="h-4 w-4 text-slate-400" />
              <span className="text-slate-400">Private Key:</span>
              <span className="font-mono text-slate-300">
                {credentials.has_credentials ? credentials.private_key_masked : "Not set"}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <Wallet className="h-4 w-4 text-slate-400" />
              <span className="text-slate-400">Proxy Address:</span>
              <span className="font-mono text-slate-300">
                {credentials.proxy_address || "Not set"}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-slate-400">Signature Type:</span>
              <span className="text-slate-300">{credentials.signature_type}</span>
            </div>
            {credentials.has_credentials && (
              <div className="mt-3 pt-3 border-t border-slate-700">
                <div className="flex items-center gap-2 text-green-400">
                  <CheckCircle2 className="h-4 w-4" />
                  <span>Credentials are configured</span>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Credentials Form */}
      <div className="rounded-md border border-slate-700 bg-slate-900/50 p-6 space-y-6">
        <h2 className="text-lg font-semibold">Update Credentials</h2>

        <div className="space-y-4">
          {/* Private Key */}
          <div>
            <label htmlFor="privateKey" className="block text-sm font-medium text-slate-300 mb-2">
              Private Key <span className="text-red-400">*</span>
            </label>
            <div className="relative">
              <input
                id="privateKey"
                type={showPrivateKey ? "text" : "password"}
                value={privateKey}
                onChange={(e) => setPrivateKey(e.target.value)}
                placeholder="0x..."
                className="w-full px-4 py-2 bg-slate-800 border border-slate-700 rounded-md text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent font-mono text-sm"
              />
              <button
                type="button"
                onClick={() => setShowPrivateKey(!showPrivateKey)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200"
              >
                {showPrivateKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
            <p className="mt-1 text-xs text-slate-500">
              Your Ethereum private key (starts with 0x, 66 characters). Keep this secure!
            </p>
          </div>

          {/* Proxy Address */}
          <div>
            <label htmlFor="proxyAddress" className="block text-sm font-medium text-slate-300 mb-2">
              Proxy Address (Wallet Address) <span className="text-red-400">*</span>
            </label>
            <input
              id="proxyAddress"
              type="text"
              value={proxyAddress}
              onChange={(e) => setProxyAddress(e.target.value)}
              placeholder="0x..."
              className="w-full px-4 py-2 bg-slate-800 border border-slate-700 rounded-md text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent font-mono text-sm"
            />
            <p className="mt-1 text-xs text-slate-500">
              Your Ethereum wallet address (starts with 0x, 42 characters). This is where your USDC balance is.
            </p>
          </div>

          {/* Signature Type */}
          <div>
            <label htmlFor="signatureType" className="block text-sm font-medium text-slate-300 mb-2">
              Signature Type
            </label>
            <select
              id="signatureType"
              value={signatureType}
              onChange={(e) => setSignatureType(parseInt(e.target.value))}
              className="w-full px-4 py-2 bg-slate-800 border border-slate-700 rounded-md text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
              <option value={1}>1 - Email / Magic Link (proxy signer)</option>
              <option value={2}>2 - Browser Wallet (proxy signer)</option>
            </select>
            <p className="mt-1 text-xs text-slate-500">
              Usually 2 for direct private key usage. Use 1 if you logged in via email/magic link.
            </p>
          </div>
        </div>

        {/* Save Button */}
        <div className="flex items-center gap-3 pt-4 border-t border-slate-700">
          <button
            onClick={handleSave}
            disabled={isSaving || !privateKey.trim() || !proxyAddress.trim()}
            className={clsx(
              "inline-flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-colors",
              isSaving || !privateKey.trim() || !proxyAddress.trim()
                ? "bg-slate-700 text-slate-400 cursor-not-allowed"
                : "bg-blue-600 text-white hover:bg-blue-700"
            )}
          >
            {isSaving ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <Save className="h-4 w-4" />
                Save Credentials
              </>
            )}
          </button>
        </div>
      </div>

      {/* Security Warning */}
      <div className="rounded-md border border-yellow-500/50 bg-yellow-500/10 px-4 py-3 text-sm text-yellow-200">
        <div className="font-semibold mb-1">⚠️ Security Warning</div>
        <ul className="list-disc list-inside space-y-1 text-xs">
          <li>Never share your private key with anyone</li>
          <li>Credentials are stored in config.json on the server</li>
          <li>Make sure your server is secure and access is restricted</li>
          <li>After updating credentials, restart the bot to apply changes</li>
        </ul>
      </div>
    </main>
  );
}

