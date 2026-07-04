<script lang="ts">
  export let columns = 4;
  export let ariaLabel: string;
</script>

<section class="grid" style={`--columns: ${String(columns)}`} aria-label={ariaLabel}>
  <slot />
</section>

<style>
  .grid {
    display: grid;
    grid-template-columns: repeat(var(--columns), minmax(130px, 1fr));
    gap: 10px;
    margin-top: 18px;
  }

  @media (max-width: 860px) {
    .grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }

  @media (max-width: 760px) {
    .grid {
      grid-template-columns: 1fr;
    }
  }
</style>
