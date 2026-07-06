<script lang="ts">
  import AppShell from "$lib/components/ui/AppShell.svelte";
  import AppNavigation from "$lib/components/ui/AppNavigation.svelte";
  import CheckboxField from "$lib/components/ui/CheckboxField.svelte";
  import NumberField from "$lib/components/ui/NumberField.svelte";
  import Notice from "$lib/components/ui/Notice.svelte";
  import PageHeader from "$lib/components/ui/PageHeader.svelte";
  import SegmentedControl from "$lib/components/ui/SegmentedControl.svelte";
  import TextField from "$lib/components/ui/TextField.svelte";
  import UiButton from "$lib/components/ui/UiButton.svelte";
  import {
    missingLabels,
    type AppSettings,
    type SettingsFormValues,
    type SetupStatus,
  } from "$lib/settings";
  import type { AioStreamsTestResult, ConnectionTestResult } from "$lib/setupApi";

  export let values: SettingsFormValues;
  export let error: string;
  export let saved: boolean;
  export let saving: boolean;
  export let setupRequired: boolean;
  export let settings: AppSettings | null;
  export let setupStatus: SetupStatus | null;
  export let testingAioStreams: boolean;
  export let testingTmdb: boolean;
  export let testingTorbox: boolean;
  export let aiostreamsTestResult: AioStreamsTestResult | null;
  export let tmdbTestResult: ConnectionTestResult | null;
  export let torboxTestResult: ConnectionTestResult | null;
  export let onClear: () => Promise<void>;
  export let onSave: () => Promise<void>;
  export let onTestAioStreams: () => Promise<void>;
  export let onTestTmdb: () => Promise<void>;
  export let onTestTorbox: () => Promise<void>;

  $: requiredLabels = setupStatus ? missingLabels(setupStatus.missing) : [];
  const playbackOptions = [
    { label: "Resolver", value: "resolver" },
    { label: "Direct URLs", value: "direct" },
  ];
</script>

<svelte:head>
  <title>Setup - Strmline</title>
</svelte:head>

<AppShell>
  <PageHeader ariaLabel="Setup controls" title="Setup">
    <svelte:fragment slot="actions">
      <AppNavigation />
    </svelte:fragment>
  </PageHeader>

  {#if error}
    <Notice variant="error">{error}</Notice>
  {/if}

  {#if saved}
    <Notice variant="success">Settings saved.</Notice>
  {/if}

  {#if setupRequired && !setupStatus?.configured}
    <section class="setup-dialog" aria-label="Setup required" aria-live="polite">
      <h2>Setup required</h2>
      <p>Complete the missing items before opening the dashboard.</p>
      {#if requiredLabels.length > 0}
        <div class="dialog-missing" aria-label="Missing setup items">
          {#each requiredLabels as label (label)}
            <span>{label}</span>
          {/each}
        </div>
      {/if}
    </section>
  {/if}

  {#if requiredLabels.length > 0 && !(setupRequired && !setupStatus?.configured)}
    <section class="missing" aria-label="Missing setup values">
      {#each requiredLabels as label (label)}
        <span>{label}</span>
      {/each}
    </section>
  {/if}

  <form class="settings-form" on:submit|preventDefault={onSave}>
    <SegmentedControl
      bind:value={values.playbackMode}
      label="Playback mode"
      options={playbackOptions}
    />
    {#if values.playbackMode === "direct"}
      <div class="wide-field">
        <Notice variant="warning">Direct mode writes tokenized TorBox URLs into STRM files.</Notice>
      </div>
    {/if}
    <NumberField
      bind:value={values.syncIntervalMinutes}
      label="Sync interval minutes"
      min="1"
      placeholder="360"
    />
    <TextField
      bind:value={values.torboxApiKey}
      autocomplete="off"
      label="TorBox API key"
      placeholder={settings?.torbox_configured ? "******" : ""}
      type="password"
    />
    <TextField
      bind:value={values.tmdbApiKey}
      autocomplete="off"
      label="TMDB API key (optional)"
      placeholder={settings?.tmdb_configured ? "******" : ""}
      type="password"
    />
    <TextField
      bind:value={values.resolverToken}
      autocomplete="off"
      label="Resolver token (optional)"
      placeholder={settings?.resolver_configured ? "******" : "Generated automatically"}
      type="password"
    />
    <TextField
      bind:value={values.aiostreamsBaseUrl}
      autocomplete="off"
      label="AIOStreams URL (optional)"
      placeholder={settings?.aiostreams_configured ? "******" : "https://.../manifest.json"}
      type="password"
    />
    <fieldset class="category-options">
      <legend>Categories</legend>
      <CheckboxField bind:checked={values.moviesEnabled} label="Movies" />
      <CheckboxField bind:checked={values.showsEnabled} label="Shows" />
      <CheckboxField bind:checked={values.animeEnabled} label="Anime" />
    </fieldset>
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
      <UiButton
        type="button"
        variant="secondary"
        disabled={saving || testingAioStreams}
        on:click={onTestAioStreams}
      >
        {testingAioStreams ? "Testing AIOStreams" : "Test AIOStreams"}
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
      {#if aiostreamsTestResult}
        <span class:ok={aiostreamsTestResult.ok} class:error-text={!aiostreamsTestResult.ok}>
          {aiostreamsTestResult.message}
        </span>
      {/if}
    </div>
  </form>
</AppShell>

<style>
  .settings-form,
  .category-options,
  .missing,
  .setup-dialog {
    border: 1px solid #d7ded9;
    border-radius: 6px;
    background: #ffffff;
  }

  .setup-dialog {
    display: grid;
    gap: 8px;
    max-width: 760px;
    margin-top: 12px;
    padding: 14px;
    border-color: #d9b66c;
    background: #fff9ea;
  }

  .setup-dialog h2,
  .setup-dialog p {
    margin: 0;
  }

  .setup-dialog h2 {
    color: #4b3510;
    font-size: 16px;
  }

  .setup-dialog p {
    color: #765d1d;
    font-size: 14px;
  }

  .dialog-missing {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .dialog-missing span {
    border: 1px solid #d9b66c;
    border-radius: 999px;
    padding: 5px 10px;
    background: #ffffff;
    color: #765d1d;
    font-size: 12px;
    font-weight: 700;
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

  .category-options {
    display: flex;
    align-items: center;
    align-self: end;
    flex-wrap: wrap;
    gap: 12px;
    min-height: 38px;
    margin: 0;
    padding: 10px 12px;
  }

  .category-options legend {
    padding: 0 4px;
    color: #526057;
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
  }

  .wide-field {
    grid-column: 1 / -1;
  }

  .wide-field :global(.notice) {
    margin: 0;
  }

  .actions {
    grid-column: 1 / -1;
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
    .settings-form {
      grid-template-columns: 1fr;
    }
  }
</style>
