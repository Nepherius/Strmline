<script lang="ts">
</script>

<main class="shell">
  <slot />
</main>

<style>
  :global(body) {
    margin: 0;
    background: #f5f7f6;
    color: #15201b;
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
  :global(input) {
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
