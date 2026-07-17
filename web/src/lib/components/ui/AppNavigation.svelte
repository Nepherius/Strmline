<script lang="ts">
  import { resolve } from "$app/paths";
  import { page } from "$app/stores";
  import { logout } from "$lib/api/auth";
  import { goto } from "$app/navigation";

  export let showLogout = true;

  const items: { href: "/" | "/search" | "/setup"; label: string }[] = [
    { href: "/", label: "Library" },
    { href: "/search", label: "Search" },
    { href: "/setup", label: "Setup" },
  ];

  $: pathname = $page.url.pathname;

  function isActive(href: string): boolean {
    if (href === "/") return pathname === "/";
    return pathname === href || pathname.startsWith(`${href}/`);
  }

  async function handleLogout() {
    try {
      await logout();
      void goto(resolve("/login"));
    } catch {
      // Ignore fallback
    }
  }
</script>

<nav class="app-nav" aria-label="Primary navigation">
  {#each items as item (item.href)}
    <a
      href={resolve(item.href)}
      class:active={isActive(item.href)}
      aria-current={isActive(item.href) ? "page" : undefined}
    >
      {item.label}
    </a>
  {/each}
  {#if showLogout && pathname !== resolve("/login")}
    <button on:click={handleLogout} class="logout-btn"> Logout </button>
  {/if}
</nav>

<style>
  .app-nav {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 6px;
  }

  .app-nav a {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 34px;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 0 12px;
    background: var(--surface);
    color: var(--text-soft);
    font-size: 14px;
    font-weight: 800;
    text-decoration: none;
  }

  .app-nav a.active {
    border-color: var(--accent-strong);
    background: var(--accent);
    color: var(--text);
  }

  .logout-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 34px;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 0 12px;
    background: var(--surface);
    color: var(--danger-text);
    font-size: 14px;
    font-weight: 800;
    cursor: pointer;
  }
</style>
