<script lang="ts">
  import { APP_VERSION } from "$lib/appVersion";

  export let title: string;
  export let ariaLabel: string;
</script>

<section class="topbar" aria-label={ariaLabel}>
  <div>
    <p class="eyebrow">Strmline <span class="version">v{APP_VERSION}</span></p>
    <h1>{title}</h1>
  </div>
  <div class="actions">
    <slot name="actions" />
  </div>
</section>

<style>
  .topbar {
    display: flex;
    align-items: end;
    justify-content: space-between;
    gap: 20px;
    padding-bottom: 18px;
    border-bottom: 1px solid var(--border);
  }

  .eyebrow {
    margin: 0 0 2px;
    color: var(--text-muted);
    font-size: 13px;
    font-weight: 700;
    text-transform: uppercase;
  }

  .version {
    color: var(--text-muted);
    font-size: 11px;
    letter-spacing: 0;
    text-transform: none;
  }

  h1 {
    margin: 0;
    font-size: 32px;
    line-height: 1.1;
    letter-spacing: 0;
  }

  .actions {
    display: flex;
    align-items: end;
    gap: 12px;
  }

  @media (max-width: 860px) {
    .topbar,
    .actions {
      align-items: stretch;
      flex-direction: column;
    }
  }
</style>
