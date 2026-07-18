<script lang="ts">
  import {
    healthLabels,
    libraryHealthTooltip,
    type LibraryHealthSummary,
  } from "$lib/domain/library/summary";

  export let health: LibraryHealthSummary | undefined;
  export let checking = false;

  $: status = checking ? "checking" : (health?.status ?? "unknown");
  $: label = checking ? "Checking" : healthLabels[health?.status ?? "unknown"];
  $: explanation = libraryHealthTooltip(health, checking);
</script>

<span class="health-chip {status}" title={explanation} aria-label={explanation}>{label}</span>

<style>
  .health-chip {
    position: absolute;
    z-index: 2;
    top: 12px;
    right: 12px;
    border: 1px solid #66736b;
    border-radius: 999px;
    padding: 3px 7px;
    background: #1d231f;
    color: #dbe6dd;
    font-size: 10px;
    font-weight: 800;
    line-height: 1.2;
  }

  .ready {
    border-color: #4ca47f;
    background: #173c30;
    color: #adf0d4;
  }

  .recoverable {
    border-color: #d09a4e;
    background: #493417;
    color: #ffe0a7;
  }

  .unavailable {
    border-color: #c76d63;
    background: #4a2523;
    color: #ffd0ca;
  }

  .checking {
    border-color: #6697b4;
    background: #213b49;
    color: #ccecff;
  }
</style>
