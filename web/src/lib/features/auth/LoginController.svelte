<script lang="ts">
  import { login } from "$lib/api/auth";
  import { loadSetupStatus } from "$lib/api/setup";
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import AppShell from "$lib/components/ui/AppShell.svelte";
  import Notice from "$lib/components/ui/Notice.svelte";
  import PageHeader from "$lib/components/ui/PageHeader.svelte";
  import TextField from "$lib/components/ui/TextField.svelte";
  import UiButton from "$lib/components/ui/UiButton.svelte";

  let username = "";
  let password = "";
  let error = "";
  let loading = false;

  async function handleLogin() {
    if (!username.trim() || !password.trim()) {
      error = "Username and password are required.";
      return;
    }

    loading = true;
    error = "";
    try {
      await login(username, password);

      // Check if setup is already complete, redirect accordingly
      const status = await loadSetupStatus();
      if (status.configured) {
        await goto(resolve("/"));
      } else {
        await goto(resolve("/setup?required=1"));
      }
    } catch (caughtError) {
      error =
        caughtError instanceof Error ? caughtError.message : "Incorrect username or password.";
    } finally {
      loading = false;
    }
  }
</script>

<svelte:head>
  <title>Login - Strmline</title>
</svelte:head>

<AppShell>
  <PageHeader ariaLabel="Login header" title="Login" />

  <div class="login-container">
    {#if error}
      <Notice variant="error" resetKey={error}>{error}</Notice>
    {/if}

    <form class="login-form" on:submit|preventDefault={handleLogin}>
      <h2>Sign In</h2>
      <p class="subtitle">Access your Strmline dashboard</p>

      <TextField
        bind:value={username}
        autocomplete="on"
        label="Username"
        placeholder="Enter your username"
      />

      <TextField
        bind:value={password}
        autocomplete="on"
        label="Password"
        placeholder="Enter your password"
        type="password"
      />

      <div class="actions">
        <UiButton type="submit" disabled={loading}>
          {loading ? "Signing In" : "Sign In"}
        </UiButton>
      </div>
    </form>
  </div>
</AppShell>

<style>
  .login-container {
    display: grid;
    justify-content: center;
    align-content: start;
    gap: 16px;
    margin-top: 40px;
    padding: 0 16px;
  }

  .login-form {
    display: grid;
    gap: 16px;
    width: 100%;
    max-width: 400px;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 24px;
    background: var(--surface);
    box-shadow: 0 4px 12px rgb(0 0 0 / 18%);
  }

  .login-form h2 {
    margin: 0;
    color: var(--text);
    font-size: 20px;
  }

  .subtitle {
    margin: -8px 0 8px 0;
    color: var(--text-muted);
    font-size: 14px;
  }

  .actions {
    display: flex;
    justify-content: flex-end;
    margin-top: 8px;
  }
</style>
