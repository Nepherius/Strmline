<script lang="ts">
  import { onMount } from "svelte";

  import { clearSavedSettings, loadSettings, saveSettings } from "$lib/settingsApi";
  import { loadSetupStatus, testTmdbConnection, testTorboxConnection } from "$lib/setupApi";
  import type { ConnectionTestResult } from "$lib/setupApi";
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
  let loading = false;
  let saving = false;
  let testingTmdb = false;
  let testingTorbox = false;
  let error = "";
  let saved = false;
  let tmdbTestResult: ConnectionTestResult | null = null;
  let torboxTestResult: ConnectionTestResult | null = null;

  onMount(() => {
    void loadSetup();
  });

  async function loadSetup() {
    loading = true;
    error = "";
    saved = false;
    tmdbTestResult = null;
    torboxTestResult = null;
    try {
      const [nextSettings, nextStatus] = await Promise.all([loadSettings(), loadSetupStatus()]);
      settings = nextSettings;
      setupStatus = nextStatus;
      values = settingsToFormValues(settings);
    } catch (caughtError) {
      const message = caughtError instanceof Error ? caughtError.message : "Unknown error";
      error = `Setup status unavailable. ${message}`;
    } finally {
      loading = false;
    }
  }

  async function saveSetup() {
    saving = true;
    error = "";
    saved = false;
    tmdbTestResult = null;
    torboxTestResult = null;
    try {
      settings = await saveSettings(values);
      values = settingsToFormValues(settings);
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
    try {
      settings = await clearSavedSettings();
      values = settingsToFormValues(settings);
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
</script>

<SetupView
  bind:values
  {error}
  {loading}
  {saved}
  {saving}
  {settings}
  {setupStatus}
  {testingTmdb}
  {testingTorbox}
  {tmdbTestResult}
  {torboxTestResult}
  onClear={clearSavedSetup}
  onRefresh={loadSetup}
  onSave={saveSetup}
  onTestTmdb={testTmdbSetup}
  onTestTorbox={testTorboxSetup}
/>
