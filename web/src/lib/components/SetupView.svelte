<script lang="ts">
  import { resolve } from "$app/paths";

  import {
    missingLabels,
    settingSourceLabel,
    type AppSettings,
    type SettingsFormValues,
    type SetupStatus,
  } from "$lib/settings";

  export let apiBase: string;
  export let values: SettingsFormValues;
  export let error: string;
  export let loading: boolean;
  export let saved: boolean;
  export let saving: boolean;
  export let settings: AppSettings | null;
  export let setupStatus: SetupStatus | null;
  export let onClear: () => Promise<void>;
  export let onRefresh: () => Promise<void>;
  export let onSave: () => Promise<void>;

  $: requiredLabels = setupStatus ? missingLabels(setupStatus.missing) : [];
</script>

<svelte:head>
  <title>Setup - Strmline</title>
</svelte:head>

<main class="shell">
  <section class="topbar" aria-label="Setup controls">
    <div>
      <p class="eyebrow">Strmline</p>
      <h1>Setup</h1>
    </div>
    <div class="topbar-actions">
      <a class="home-link" href={resolve("/")}>Home</a>
      <form class="connection" on:submit|preventDefault={onRefresh}>
        <label>
          <span>API</span>
          <input bind:value={apiBase} aria-label="API base URL" />
        </label>
        <button type="submit" disabled={loading}>{loading ? "Loading" : "Refresh"}</button>
      </form>
    </div>
  </section>

  {#if error}
    <p class="notice error">{error}</p>
  {/if}

  {#if saved}
    <p class="notice success">Settings saved.</p>
  {/if}

  <section class="status-grid" aria-label="Setup status">
    <div class:ready={setupStatus?.configured} class="metric">
      <span>Status</span>
      <strong>{setupStatus?.configured ? "Ready" : "Open"}</strong>
    </div>
    <div
      class:env={settings?.torbox_source === "environment"}
      class:ready={settings?.torbox_configured}
      class="metric"
    >
      <span>TorBox</span>
      <strong>{settingSourceLabel(settings?.torbox_source ?? null)}</strong>
    </div>
    <div
      class:env={settings?.tmdb_source === "environment"}
      class:ready={settings?.tmdb_configured}
      class="metric"
    >
      <span>TMDB</span>
      <strong>{settingSourceLabel(settings?.tmdb_source ?? null)}</strong>
    </div>
    <div
      class:env={settings?.resolver_source === "environment"}
      class:ready={settings?.resolver_configured}
      class="metric"
    >
      <span>Resolver</span>
      <strong>{settingSourceLabel(settings?.resolver_source ?? null)}</strong>
    </div>
  </section>

  {#if requiredLabels.length > 0}
    <section class="missing" aria-label="Missing setup values">
      {#each requiredLabels as label (label)}
        <span>{label}</span>
      {/each}
    </section>
  {/if}

  <form class="settings-form" on:submit|preventDefault={onSave}>
    <label>
      <span>Base URL</span>
      <input bind:value={values.baseUrl} placeholder="http://127.0.0.1:8001" />
    </label>
    <label>
      <span>Library root</span>
      <input bind:value={values.libraryRoot} placeholder="/tmp/strmline-library" />
    </label>
    <label>
      <span>TorBox API key</span>
      <input bind:value={values.torboxApiKey} autocomplete="off" type="password" />
    </label>
    <label>
      <span>TMDB API key</span>
      <input bind:value={values.tmdbApiKey} autocomplete="off" type="password" />
    </label>
    <label>
      <span>Resolver token</span>
      <input bind:value={values.resolverToken} autocomplete="off" type="password" />
    </label>
    <div class="actions">
      <button type="submit" disabled={saving}>{saving ? "Saving" : "Save settings"}</button>
      <button class="secondary" type="button" disabled={saving} on:click={onClear}>
        Clear saved setup
      </button>
    </div>
  </form>
</main>

<style>
  :global(body) {
    margin: 0;
    background: #f5f7f6;
    color: #15201b;
    font-family:
      Inter,
      ui-sans-serif,
      system-ui,
      -apple-system,
      BlinkMacSystemFont,
      "Segoe UI",
      sans-serif;
  }

  button,
  input {
    font: inherit;
  }

  .shell {
    box-sizing: border-box;
    min-height: 100vh;
    padding: 24px;
  }

  .topbar {
    display: flex;
    align-items: end;
    justify-content: space-between;
    gap: 20px;
    padding-bottom: 18px;
    border-bottom: 1px solid #d7ded9;
  }

  .eyebrow {
    margin: 0 0 2px;
    color: #5b6a61;
    font-size: 13px;
    font-weight: 700;
    text-transform: uppercase;
  }

  h1 {
    margin: 0;
    font-size: 32px;
    line-height: 1.1;
    letter-spacing: 0;
  }

  .connection {
    display: flex;
    align-items: end;
    gap: 10px;
  }

  .topbar-actions {
    display: flex;
    align-items: end;
    gap: 12px;
  }

  .home-link {
    display: inline-flex;
    align-items: center;
    height: 36px;
    border: 1px solid #bdc8c2;
    border-radius: 6px;
    padding: 0 12px;
    background: #ffffff;
    color: #24352d;
    font-weight: 700;
    text-decoration: none;
  }

  label {
    display: grid;
    gap: 6px;
    color: #526057;
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
  }

  input {
    box-sizing: border-box;
    min-width: 260px;
    height: 38px;
    border: 1px solid #bcc8c1;
    border-radius: 6px;
    padding: 0 10px;
    background: #ffffff;
    color: #15201b;
  }

  button {
    height: 38px;
    border: 1px solid #1c4333;
    border-radius: 6px;
    padding: 0 14px;
    background: #1f5b42;
    color: #ffffff;
    cursor: pointer;
    font-weight: 700;
  }

  button:disabled {
    cursor: wait;
    opacity: 0.6;
  }

  .notice {
    margin: 18px 0 0;
    border: 1px solid #d7ded9;
    border-radius: 6px;
    padding: 12px;
    background: #ffffff;
  }

  .error {
    border-color: #e1a2a2;
    background: #fff5f4;
    color: #8e251f;
  }

  .success {
    border-color: #9bc9aa;
    background: #f0fff4;
    color: #1f5b42;
  }

  .status-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(130px, 1fr));
    gap: 10px;
    margin-top: 18px;
  }

  .metric,
  .settings-form,
  .missing {
    border: 1px solid #d7ded9;
    border-radius: 6px;
    background: #ffffff;
  }

  .metric {
    padding: 12px;
  }

  .metric.ready {
    border-color: #9bc9aa;
    background: #f0fff4;
  }

  .metric.env {
    border-color: #9ebbd0;
    background: #f0f8ff;
  }

  .metric span {
    display: block;
    color: #5b6a61;
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
  }

  .metric strong {
    display: block;
    margin-top: 6px;
    font-size: 24px;
  }

  .missing {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 12px;
    padding: 12px;
  }

  .missing span {
    border: 1px solid #d9b66c;
    border-radius: 999px;
    padding: 5px 10px;
    background: #fff9ea;
    color: #765d1d;
    font-size: 12px;
    font-weight: 700;
  }

  .settings-form {
    display: grid;
    grid-template-columns: repeat(2, minmax(220px, 1fr));
    gap: 14px;
    margin-top: 18px;
    padding: 14px;
  }

  .actions {
    display: flex;
    align-self: end;
    flex-wrap: wrap;
    gap: 8px;
  }

  .settings-form button {
    align-self: end;
  }

  .secondary {
    border-color: #bdc8c2;
    background: #ffffff;
    color: #24352d;
  }

  @media (max-width: 760px) {
    .shell {
      padding: 16px;
    }

    .topbar,
    .topbar-actions,
    .connection {
      align-items: stretch;
      flex-direction: column;
    }

    .status-grid,
    .settings-form {
      grid-template-columns: 1fr;
    }

    input {
      min-width: 0;
      width: 100%;
    }
  }
</style>
