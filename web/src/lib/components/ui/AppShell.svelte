<script lang="ts">
</script>

<main class="shell">
  <slot />
</main>

<style>
  :global(body) {
    --page: #151815;
    --surface: #202620;
    --surface-subtle: #1a201b;
    --surface-raised: #273028;
    --border: #3b4840;
    --border-strong: #516158;
    --text: #f8f5ed;
    --text-muted: #aab9af;
    --text-soft: #dbe6dd;
    --accent: #26795e;
    --accent-strong: #3e9c7a;
    --focus: #65b493;
    --warning-surface: #352b1d;
    --warning-border: #a8773f;
    --warning-text: #ffdca1;
    --danger-surface: #32201f;
    --danger-border: #a35a51;
    --danger-text: #ffd0ca;
    --success-surface: #193428;
    --success-border: #3e9c7a;
    --success-text: #bde8d2;
    margin: 0;
    background: var(--page);
    color: var(--text);
    color-scheme: dark;
    font-family:
      Inter,
      ui-sans-serif,
      system-ui,
      -apple-system,
      BlinkMacSystemFont,
      "Segoe UI",
      sans-serif;
  }

  :global(button),
  :global(input),
  :global(select) {
    font: inherit;
  }

  .shell {
    box-sizing: border-box;
    min-height: 100vh;
    padding: 24px;
  }

  @media (max-width: 860px) {
    .shell {
      padding: 16px;
    }
  }
</style>
