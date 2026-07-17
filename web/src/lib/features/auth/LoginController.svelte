<script lang="ts">
  import { login } from "$lib/api/auth";
  import { loadSetupStatus } from "$lib/api/setup";
  import { goto } from "$app/navigation";
  import { resolve } from "$app/paths";
  import LoginView from "./LoginView.svelte";

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

<LoginView bind:username bind:password {error} {loading} onLogin={handleLogin} />
