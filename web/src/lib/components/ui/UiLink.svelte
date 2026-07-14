<script lang="ts">
  import { resolve } from "$app/paths";

  type ResolvableRoute = Parameters<typeof resolve>[0];

  export let href: ResolvableRoute;
</script>

<a href={resolve(href)}>
  <slot />
</a>

<style>
  a {
    display: inline-flex;
    align-items: center;
    height: 36px;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 0 12px;
    background: var(--surface);
    color: var(--text-soft);
    font-weight: 700;
    text-decoration: none;
  }
</style>
