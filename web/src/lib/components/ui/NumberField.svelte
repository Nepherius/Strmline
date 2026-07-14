<script lang="ts">
  import HelpTooltip from "./HelpTooltip.svelte";

  export let label: string;
  export let helpText: string | undefined = undefined;
  export let value = "";
  export let placeholder = "";
  export let min: string | undefined = "0";
  export let max: string | undefined = undefined;
  export let step = "1";

  function updateValue(event: Event): void {
    value = (event.currentTarget as HTMLInputElement).value;
  }
</script>

<label>
  <span class="label-row"
    >{label}{#if helpText}<HelpTooltip text={helpText} label={`About ${label}`} />{/if}</span
  >
  <input
    inputmode="numeric"
    {min}
    {max}
    {placeholder}
    {step}
    type="number"
    {value}
    on:input={updateValue}
  />
</label>

<style>
  label {
    display: grid;
    gap: 6px;
    color: var(--text-muted);
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
  }

  .label-row {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }

  input {
    box-sizing: border-box;
    min-width: 260px;
    height: 38px;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 0 10px;
    background: var(--surface);
    color: var(--text);
  }

  @media (max-width: 860px) {
    input {
      min-width: 0;
      width: 100%;
    }
  }
</style>
