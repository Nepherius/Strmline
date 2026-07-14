<script lang="ts">
  import HelpTooltip from "./HelpTooltip.svelte";

  export let label: string;
  export let helpText: string | undefined = undefined;
  export let value = "";
  export let placeholder = "";
  export let type = "text";
  export let autocomplete: "off" | "on" | undefined = undefined;
  export let disabled = false;
</script>

<label>
  <span class="label-row"
    >{label}{#if helpText}<HelpTooltip text={helpText} label={`About ${label}`} />{/if}</span
  >
  <input bind:value {placeholder} {type} {autocomplete} {disabled} />
</label>

<style>
  label {
    display: grid;
    gap: 6px;
    color: #526057;
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
    border: 1px solid #bcc8c1;
    border-radius: 6px;
    padding: 0 10px;
    background: #ffffff;
    color: #15201b;
  }

  input:disabled {
    border-color: #d7ded9;
    background: #f4f6f4;
    color: #526057;
  }

  @media (max-width: 860px) {
    input {
      min-width: 0;
      width: 100%;
    }
  }
</style>
