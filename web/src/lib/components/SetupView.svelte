<script lang="ts">
  import AppShell from "$lib/components/ui/AppShell.svelte";
  import MetricCard from "$lib/components/ui/MetricCard.svelte";
  import MetricGrid from "$lib/components/ui/MetricGrid.svelte";
  import Notice from "$lib/components/ui/Notice.svelte";
  import PageHeader from "$lib/components/ui/PageHeader.svelte";
  import TextField from "$lib/components/ui/TextField.svelte";
  import UiButton from "$lib/components/ui/UiButton.svelte";
  import UiLink from "$lib/components/ui/UiLink.svelte";
  import {
    missingLabels,
    settingSourceLabel,
    type SettingSource,
    type AppSettings,
    type SettingsFormValues,
    type SetupStatus,
  } from "$lib/settings";
  import type { ConnectionTestResult } from "$lib/setupApi";

  export let values: SettingsFormValues;
  export let error: string;
  export let loading: boolean;
  export let saved: boolean;
  export let saving: boolean;
  export let settings: AppSettings | null;
  export let setupStatus: SetupStatus | null;
  export let testingTmdb: boolean;
  export let testingTorbox: boolean;
  export let tmdbTestResult: ConnectionTestResult | null;
  export let torboxTestResult: ConnectionTestResult | null;
  export let onClear: () => Promise<void>;
  export let onRefresh: () => Promise<void>;
  export let onSave: () => Promise<void>;
  export let onTestTmdb: () => Promise<void>;
  export let onTestTorbox: () => Promise<void>;

  $: requiredLabels = setupStatus ? missingLabels(setupStatus.missing) : [];

  function settingVariant(
    configured: boolean | undefined,
    source: SettingSource | undefined,
  ): "default" | "ready" | "env" {
    if (source === "environment") {
      return "env";
    }
    if (configured) {
      return "ready";
    }
    return "default";
  }
</script>

<svelte:head>
  <title>Setup - Strmline</title>
</svelte:head>

<AppShell>
  <PageHeader ariaLabel="Setup controls" title="Setup">
    <svelte:fragment slot="actions">
      <UiLink href="/">Home</UiLink>
      <form class="refresh-form" on:submit|preventDefault={onRefresh}>
        <UiButton type="submit" disabled={loading}>{loading ? "Loading" : "Refresh"}</UiButton>
      </form>
    </svelte:fragment>
  </PageHeader>

  {#if error}
    <Notice variant="error">{error}</Notice>
  {/if}

  {#if saved}
    <Notice variant="success">Settings saved.</Notice>
  {/if}

  <MetricGrid ariaLabel="Setup status" columns={4}>
    <MetricCard
      label="Status"
      value={setupStatus?.configured ? "Ready" : "Open"}
      variant={setupStatus?.configured ? "ready" : "default"}
    />
    <MetricCard
      label="TorBox"
      value={settingSourceLabel(settings?.torbox_source ?? null)}
      variant={settingVariant(settings?.torbox_configured, settings?.torbox_source ?? undefined)}
    />
    <MetricCard
      label="TMDB"
      value={settingSourceLabel(settings?.tmdb_source ?? null)}
      variant={settingVariant(settings?.tmdb_configured, settings?.tmdb_source ?? undefined)}
    />
    <MetricCard
      label="Resolver"
      value={settingSourceLabel(settings?.resolver_source ?? null)}
      variant={settingVariant(
        settings?.resolver_configured,
        settings?.resolver_source ?? undefined,
      )}
    />
  </MetricGrid>

  {#if requiredLabels.length > 0}
    <section class="missing" aria-label="Missing setup values">
      {#each requiredLabels as label (label)}
        <span>{label}</span>
      {/each}
    </section>
  {/if}

  <form class="settings-form" on:submit|preventDefault={onSave}>
    <TextField bind:value={values.baseUrl} label="Base URL" placeholder="http://127.0.0.1:8001" />
    <TextField
      bind:value={values.libraryRoot}
      label="Library root"
      placeholder="/tmp/strmline-library"
    />
    <TextField
      bind:value={values.torboxApiKey}
      autocomplete="off"
      label="TorBox API key"
      type="password"
    />
    <TextField
      bind:value={values.tmdbApiKey}
      autocomplete="off"
      label="TMDB API key"
      type="password"
    />
    <TextField
      bind:value={values.resolverToken}
      autocomplete="off"
      label="Resolver token"
      type="password"
    />
    <div class="actions">
      <UiButton type="submit" disabled={saving}>{saving ? "Saving" : "Save settings"}</UiButton>
      <UiButton
        type="button"
        variant="secondary"
        disabled={saving || testingTorbox}
        on:click={onTestTorbox}
      >
        {testingTorbox ? "Testing TorBox" : "Test TorBox"}
      </UiButton>
      <UiButton
        type="button"
        variant="secondary"
        disabled={saving || testingTmdb}
        on:click={onTestTmdb}
      >
        {testingTmdb ? "Testing TMDB" : "Test TMDB"}
      </UiButton>
      <UiButton type="button" variant="secondary" disabled={saving} on:click={onClear}>
        Clear saved setup
      </UiButton>
      {#if torboxTestResult}
        <span class:ok={torboxTestResult.ok} class:error-text={!torboxTestResult.ok}>
          {torboxTestResult.message}
        </span>
      {/if}
      {#if tmdbTestResult}
        <span class:ok={tmdbTestResult.ok} class:error-text={!tmdbTestResult.ok}>
          {tmdbTestResult.message}
        </span>
      {/if}
    </div>
  </form>
</AppShell>

<style>
  .refresh-form {
    display: flex;
    align-items: end;
  }

  .settings-form,
  .missing {
    border: 1px solid #d7ded9;
    border-radius: 6px;
    background: #ffffff;
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
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
  }

  .actions span {
    color: #526057;
    font-size: 13px;
    font-weight: 700;
  }

  .actions span.ok {
    color: #1f5b42;
  }

  .actions span.error-text {
    color: #8e251f;
  }

  @media (max-width: 760px) {
    .refresh-form {
      align-items: stretch;
      flex-direction: column;
    }

    .settings-form {
      grid-template-columns: 1fr;
    }
  }
</style>
