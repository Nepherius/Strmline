<script lang="ts">
  import HelpTooltip from "./HelpTooltip.svelte";

  export let checked = false;
  export let label: string;
  export let helpText: string | undefined = undefined;
</script>

<div class="field">
  <label>
    <input bind:checked type="checkbox" />
    <span>{label}</span>
  </label>
  {#if helpText}<HelpTooltip text={helpText} label={`About ${label}`} />{/if}
</div>

<style>
  .field {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }

  label {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    color: var(--text-soft);
    font-size: 13px;
    font-weight: 700;
  }

  input {
    width: 16px;
    height: 16px;
    accent-color: var(--accent-strong);
  }
</style>
