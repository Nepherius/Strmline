<script lang="ts">
  import { onMount } from "svelte";

  import { clearSavedSettings, loadSettings, saveSettings } from "$lib/settingsApi";
  import {
    loadSetupStatus,
    testAioStreamsConnection,
    testTmdbConnection,
    testTorboxConnection,
  } from "$lib/setupApi";
  import type { AioStreamsTestResult, ConnectionTestResult } from "$lib/setupApi";
  import {
    settingsToFormValues,
    type AppSettings,
    type SettingsFormValues,
    type SetupStatus,
  } from "$lib/settings";

  import SetupView from "./SetupView.svelte";

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
      aiostreamsTestResult = await testAioStreamsConnection(
        values.aiostreamsBaseUrl,
      );
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
</script>

<SetupView
  bind:values
  {error}
  {saved}
  {saving}
  {setupRequired}
  {settings}
  {setupStatus}
  {testingTmdb}
  {testingTorbox}
  {testingAioStreams}
  {aiostreamsTestResult}
  {tmdbTestResult}
  {torboxTestResult}
  onClear={clearSavedSetup}
  onSave={saveSetup}
  onTestTmdb={testTmdbSetup}
  onTestTorbox={testTorboxSetup}
  onTestAioStreams={testAioStreamsSetup}
/>
