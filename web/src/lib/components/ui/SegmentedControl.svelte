<script lang="ts">
  interface SegmentOption {
    label: string;
    value: string;
  }

  export let label: string;
  export let value: string;
  export let options: SegmentOption[];
</script>

<fieldset>
  <legend>{label}</legend>
  <div class="segments">
    {#each options as option (option.value)}
      <label class:active={value === option.value}>
        <input bind:group={value} type="radio" value={option.value} />
        <span>{option.label}</span>
      </label>
    {/each}
  </div>
</fieldset>

<style>
  fieldset {
    display: grid;
    gap: 6px;
    min-width: 260px;
    margin: 0;
    border: 0;
    padding: 0;
  }

  legend {
    padding: 0;
    color: #526057;
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
  }

  .segments {
    display: inline-grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    height: 38px;
    border: 1px solid #bcc8c1;
    border-radius: 6px;
    overflow: hidden;
    background: #ffffff;
  }

  label {
    display: grid;
    place-items: center;
    cursor: pointer;
    color: #526057;
    font-size: 13px;
    font-weight: 700;
  }

  label + label {
    border-left: 1px solid #bcc8c1;
  }

  label.active {
    background: #1f5b42;
    color: #ffffff;
  }

  input {
    position: absolute;
    opacity: 0;
    pointer-events: none;
  }

  @media (max-width: 860px) {
    fieldset {
      min-width: 0;
      width: 100%;
    }
  }
</style>
