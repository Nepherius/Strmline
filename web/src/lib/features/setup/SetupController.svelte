<script lang="ts">
  import { onMount } from "svelte";

  import { setupAdminUser } from "$lib/api/auth";
  import { clearSavedSettings, loadSettings, saveSettings } from "$lib/api/settings";
  import {
    loadSetupStatus,
    testAioStreamsConnection,
    testTmdbConnection,
    testTorboxConnection,
  } from "$lib/api/setup";
  import type { AioStreamsTestResult, ConnectionTestResult } from "$lib/api/setup";
  import AppShell from "$lib/components/ui/AppShell.svelte";
  import AppNavigation from "$lib/components/ui/AppNavigation.svelte";
  import CheckboxField from "$lib/components/ui/CheckboxField.svelte";
  import HelpTooltip from "$lib/components/ui/HelpTooltip.svelte";
  import NumberField from "$lib/components/ui/NumberField.svelte";
  import Notice from "$lib/components/ui/Notice.svelte";
  import PageHeader from "$lib/components/ui/PageHeader.svelte";
  import SegmentedControl from "$lib/components/ui/SegmentedControl.svelte";
  import TextField from "$lib/components/ui/TextField.svelte";
  import UiButton from "$lib/components/ui/UiButton.svelte";
  import {
    missingLabels,
    settingsToFormValues,
    type AppSettings,
    type SettingsFormValues,
    type SetupStatus,
  } from "$lib/domain/settings";

  let settings: AppSettings | null = null;
  let setupStatus: SetupStatus | null = null;
  let values: SettingsFormValues = settingsToFormValues(null);
  let saving = false;
  let testingTmdb = false;
  let testingTorbox = false;
  let testingAioStreams = false;
  let error = "";
  let saved = false;
  let setupRequired = false;
  let tmdbTestResult: ConnectionTestResult | null = null;
  let torboxTestResult: ConnectionTestResult | null = null;
  let aiostreamsTestResult: AioStreamsTestResult | null = null;

  onMount(() => {
    setupRequired = new URLSearchParams(window.location.search).get("required") === "1";
    void loadSetup();
  });

  async function loadSetup() {
    error = "";
    saved = false;
    tmdbTestResult = null;
    torboxTestResult = null;
    aiostreamsTestResult = null;
    try {
      const [nextSettings, nextStatus] = await Promise.all([loadSettings(), loadSetupStatus()]);
      settings = nextSettings;
      setupStatus = nextStatus;
      values = withBrowserBaseUrl(settingsToFormValues(settings));
    } catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : "Unknown error";
      error = `Setup status unavailable. ${message}`;
    }
  }

  async function saveSetup() {
    saving = true;
    error = "";
    saved = false;
    tmdbTestResult = null;
    torboxTestResult = null;
    aiostreamsTestResult = null;
    try {
      if (setupStatus?.missing.includes("admin_user")) {
        if (!values.adminUsername.trim() || !values.adminPassword.trim()) {
          throw new Error("Admin username and password are required.");
        }
        if (values.adminPassword.length < 8) {
          throw new Error("Admin password must be at least 8 characters.");
        }
        try {
          await setupAdminUser(values.adminUsername.trim(), values.adminPassword);
        } catch (setupError) {
          // If the user was already created (e.g. previous partial save), continue
          // to settings save rather than blocking the entire setup flow.
          const msg = setupError instanceof Error ? setupError.message : "";
          if (!msg.toLowerCase().includes("already exists")) {
            throw setupError;
          }
        }
      }

      settings = await saveSettings(withBrowserBaseUrl(values));
      values = withBrowserBaseUrl(settingsToFormValues(settings));
      saved = true;
      await loadSetup();
    } catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : "Unknown error";
      error = `Settings were not saved. ${message}`;
    } finally {
      saving = false;
    }
  }

  async function clearSavedSetup() {
    saving = true;
    error = "";
    saved = false;
    tmdbTestResult = null;
    torboxTestResult = null;
    aiostreamsTestResult = null;
    try {
      settings = await clearSavedSettings();
      values = withBrowserBaseUrl(settingsToFormValues(settings));
      await loadSetup();
    } catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : "Unknown error";
      error = `Saved settings were not cleared. ${message}`;
    } finally {
      saving = false;
    }
  }

  async function testTorboxSetup() {
    testingTorbox = true;
    error = "";
    torboxTestResult = null;
    try {
      torboxTestResult = await testTorboxConnection(values.torboxApiKey);
    } catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : "Unknown error";
      torboxTestResult = {
        ok: false,
        message: `TorBox test unavailable. ${message}`,
      };
    } finally {
      testingTorbox = false;
    }
  }

  async function testTmdbSetup() {
    testingTmdb = true;
    error = "";
    tmdbTestResult = null;
    try {
      tmdbTestResult = await testTmdbConnection(values.tmdbApiKey);
    } catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : "Unknown error";
      tmdbTestResult = {
        ok: false,
        message: `TMDB test unavailable. ${message}`,
      };
    } finally {
      testingTmdb = false;
    }
  }

  async function testAioStreamsSetup() {
    testingAioStreams = true;
    error = "";
    aiostreamsTestResult = null;
    try {
      aiostreamsTestResult = await testAioStreamsConnection(values.aiostreamsBaseUrl);
    } catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : "Unknown error";
      aiostreamsTestResult = {
        ok: false,
        message: `AIOStreams test unavailable. ${message}`,
        addon_name: null,
        addon_version: null,
        resources: [],
        types: [],
        stream_count: null,
        streams: [],
      };
    } finally {
      testingAioStreams = false;
    }
  }

  function withBrowserBaseUrl(nextValues: SettingsFormValues): SettingsFormValues {
    return {
      ...nextValues,
      baseUrl: window.location.origin,
    };
  }

  $: requiredLabels = setupStatus ? missingLabels(setupStatus.missing) : [];
  $: showLogout = setupStatus !== null && !setupStatus.missing.includes("admin_user");
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
      <AppNavigation {showLogout} />
    </svelte:fragment>
  </PageHeader>

  {#if error}
    <Notice variant="error" resetKey={error}>{error}</Notice>
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

  <form class="settings-form" on:submit|preventDefault={saveSetup}>
    {#if setupStatus?.missing.includes("admin_user")}
      <div class="wide-field">
        <Notice variant="default">Define your administrator account credentials.</Notice>
      </div>
      <TextField
        bind:value={values.adminUsername}
        autocomplete="off"
        helpText="The name used to sign in to the Strmline web interface."
        label="Admin Username"
        placeholder="e.g. admin"
      />
      <TextField
        bind:value={values.adminPassword}
        autocomplete="off"
        helpText="The password for the administrator account. It must be at least eight characters."
        label="Admin Password"
        placeholder="At least 8 characters"
        type="password"
      />
    {/if}
    <SegmentedControl
      bind:value={values.playbackMode}
      helpText="Resolver keeps TorBox media URLs out of STRM files. Direct URLs writes tokenized TorBox URLs into them."
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
      helpText="How often Strmline automatically refreshes the TorBox library. Manual sync is always available."
      label="Sync interval minutes"
      min="1"
      placeholder="360"
    />
    <fieldset class="category-options">
      <legend
        >Season auto-complete <HelpTooltip
          text="Searches for missing released episodes in shows already present in your TorBox library."
        /></legend
      >
      <CheckboxField
        bind:checked={values.seasonAutoCompleteEnabled}
        helpText="Enable automatic searches for missing regular episodes. The first check runs when this is saved."
        label="Complete missing regular episodes"
      />
      {#if values.seasonAutoCompleteEnabled}
        <NumberField
          bind:value={values.seasonAutoCompleteIntervalDays}
          helpText="The number of days between season completion checks."
          label="Check interval days"
          min="1"
          placeholder="1"
        />
        <NumberField
          bind:value={values.seasonAutoCompleteShowsPerMinute}
          helpText="Limits provider requests by spacing show checks across each minute."
          label="Shows checked per minute"
          min="1"
          max="60"
          placeholder="1"
        />
        <CheckboxField
          bind:checked={values.seasonAutoCompleteAllowUncached}
          helpText="Also consider torrents that are not already cached by your debrid provider."
          label="Allow uncached torrents"
        />
      {/if}
    </fieldset>
    <fieldset class="category-options">
      <legend
        >Diagnostics <HelpTooltip
          text="Operational logging controls for troubleshooting."
        /></legend
      >
      <CheckboxField
        bind:checked={values.debugLogging}
        helpText="This is the only debug logging control. Detailed logs appear in container output; retained errors are stored in /config/logs."
        label="Enable debug logging"
      />
    </fieldset>
    <fieldset class="category-options operational-settings wide-field">
      <legend
        >TorBox resilience <HelpTooltip
          text="Process-wide traffic and failed playback-recovery controls. Saved Setup values are the single source of truth."
        /></legend
      >
      <NumberField
        bind:value={values.torboxRequestsPerMinute}
        helpText="Maximum TorBox API calls admitted across this Strmline process each minute."
        label="Requests per minute"
        min="1"
        max="1000"
        placeholder="250"
      />
      <NumberField
        bind:value={values.resolverNegativeCacheSeconds}
        helpText="Delay before retrying a playback entry after its recovery call fails."
        label="Failure retry delay (seconds)"
        min="1"
        max="300"
        placeholder="30"
      />
      <NumberField
        bind:value={values.resolverCircuitBreakerFailures}
        helpText="Failures for one playback entry that open its recovery circuit."
        label="Circuit failure threshold"
        min="1"
        max="20"
        placeholder="3"
      />
      <NumberField
        bind:value={values.resolverCircuitBreakerWindowSeconds}
        helpText="Time window used to count failures toward the circuit threshold."
        label="Circuit window (seconds)"
        min="1"
        max="3600"
        placeholder="120"
      />
      <NumberField
        bind:value={values.resolverCircuitBreakerCooldownSeconds}
        helpText="How long recovery remains paused after the circuit opens."
        label="Circuit cooldown (seconds)"
        min="1"
        max="3600"
        placeholder="60"
      />
    </fieldset>
    <TextField
      bind:value={values.torboxApiKey}
      autocomplete="off"
      helpText="Required for listing your TorBox downloads and generating playable library entries."
      label="TorBox API key"
      placeholder={settings?.torbox_configured ? "******" : ""}
      type="password"
    />
    <TextField
      bind:value={values.tmdbApiKey}
      autocomplete="off"
      helpText="Optional. Enables metadata-based titles, categories, and duplicate prevention."
      label="TMDB API key (optional)"
      placeholder={settings?.tmdb_configured ? "******" : ""}
      type="password"
    />
    <TextField
      bind:value={values.resolverToken}
      autocomplete="off"
      helpText="Optional custom token for resolver playback URLs. Leave blank to generate one automatically."
      label="Resolver token (optional)"
      placeholder={settings?.resolver_configured ? "******" : "Generated automatically"}
      type="password"
    />
    <TextField
      bind:value={values.aiostreamsBaseUrl}
      autocomplete="off"
      helpText="Optional Stremio-compatible AIOStreams manifest URL used for search and season auto-complete."
      label="AIOStreams URL (optional)"
      placeholder={settings?.aiostreams_configured ? "******" : "https://.../manifest.json"}
      type="password"
    />
    <fieldset class="category-options">
      <legend
        >Categories <HelpTooltip
          text="Choose which generated media-library folders Strmline maintains."
        /></legend
      >
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
        on:click={testTorboxSetup}
      >
        {testingTorbox ? "Testing TorBox" : "Test TorBox"}
      </UiButton>
      <UiButton
        type="button"
        variant="secondary"
        disabled={saving || testingTmdb}
        on:click={testTmdbSetup}
      >
        {testingTmdb ? "Testing TMDB" : "Test TMDB"}
      </UiButton>
      <UiButton
        type="button"
        variant="secondary"
        disabled={saving || testingAioStreams}
        on:click={testAioStreamsSetup}
      >
        {testingAioStreams ? "Testing AIOStreams" : "Test AIOStreams"}
      </UiButton>
      <UiButton type="button" variant="secondary" disabled={saving} on:click={clearSavedSetup}>
        Clear saved setup
      </UiButton>
      {#if torboxTestResult}
        <Notice
          variant={torboxTestResult.ok ? "success" : "error"}
          resetKey={torboxTestResult.message}>{torboxTestResult.message}</Notice
        >
      {/if}
      {#if tmdbTestResult}
        <Notice variant={tmdbTestResult.ok ? "success" : "error"} resetKey={tmdbTestResult.message}
          >{tmdbTestResult.message}</Notice
        >
      {/if}
      {#if aiostreamsTestResult}
        <Notice
          variant={aiostreamsTestResult.ok ? "success" : "error"}
          resetKey={aiostreamsTestResult.message}>{aiostreamsTestResult.message}</Notice
        >
      {/if}
    </div>
  </form>
</AppShell>

<style>
  .settings-form,
  .category-options,
  .missing,
  .setup-dialog {
    border: 1px solid var(--border);
    border-radius: 6px;
    background: var(--surface);
  }

  .setup-dialog {
    display: grid;
    gap: 8px;
    max-width: 760px;
    margin-top: 12px;
    padding: 14px;
    border-color: var(--warning-border);
    background: var(--warning-surface);
  }

  .setup-dialog h2,
  .setup-dialog p {
    margin: 0;
  }

  .setup-dialog h2 {
    color: var(--warning-text);
    font-size: 16px;
  }

  .setup-dialog p {
    color: var(--warning-text);
    font-size: 14px;
  }

  .dialog-missing {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }

  .dialog-missing span {
    border: 1px solid var(--warning-border);
    border-radius: 999px;
    padding: 5px 10px;
    background: var(--surface-raised);
    color: var(--warning-text);
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
    border: 1px solid var(--warning-border);
    border-radius: 999px;
    padding: 5px 10px;
    background: var(--warning-surface);
    color: var(--warning-text);
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
    color: var(--text-muted);
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
  }

  .operational-settings {
    display: grid;
    grid-template-columns: repeat(5, minmax(150px, 1fr));
    align-items: end;
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

  .actions :global(.notice) {
    margin: 0;
  }

  @media (max-width: 760px) {
    .settings-form {
      grid-template-columns: 1fr;
    }

    .operational-settings {
      grid-template-columns: 1fr;
    }
  }
</style>
