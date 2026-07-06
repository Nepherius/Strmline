<script lang="ts">
  import { resolve } from "$app/paths";
  import { page } from "$app/stores";

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
    border: 1px solid #bdc8c2;
    border-radius: 6px;
    padding: 0 12px;
    background: #ffffff;
    color: #24352d;
    font-size: 14px;
    font-weight: 800;
    text-decoration: none;
  }

  .app-nav a.active {
    border-color: #1f5b42;
    background: #1f5b42;
    color: #ffffff;
  }
</style>
