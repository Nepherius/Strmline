<script lang="ts">
  import AppShell from "$lib/components/ui/AppShell.svelte";
  import Notice from "$lib/components/ui/Notice.svelte";
  import PageHeader from "$lib/components/ui/PageHeader.svelte";
  import TextField from "$lib/components/ui/TextField.svelte";
  import UiButton from "$lib/components/ui/UiButton.svelte";

  export let username = "";
  export let password = "";
  export let error = "";
  export let loading = false;
  export let onLogin: () => Promise<void>;
</script>

<svelte:head>
  <title>Login - Strmline</title>
</svelte:head>

<AppShell>
  <PageHeader ariaLabel="Login header" title="Login" />

  <div class="login-container">
    {#if error}
      <Notice variant="error">{error}</Notice>
    {/if}

    <form class="login-form" on:submit|preventDefault={onLogin}>
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
    border: 1px solid #d7ded9;
    border-radius: 6px;
    padding: 24px;
    background: #ffffff;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
  }

  .login-form h2 {
    margin: 0;
    color: #15201b;
    font-size: 20px;
  }

  .subtitle {
    margin: -8px 0 8px 0;
    color: #526057;
    font-size: 14px;
  }

  .actions {
    display: flex;
    justify-content: flex-end;
    margin-top: 8px;
  }
</style>
