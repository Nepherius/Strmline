<script lang="ts">
  export let text: string;
  export let label = "About this setting";
</script>

<span class="help-tooltip">
  <button aria-label={label} type="button">?</button>
  <span role="tooltip">{text}</span>
</span>

<style>
  .help-tooltip {
    position: relative;
    display: inline-flex;
  }

  button {
    display: grid;
    width: 17px;
    height: 17px;
    place-items: center;
    border: 0;
    border-radius: 50%;
    padding: 0;
    background: #1976d2;
    color: #ffffff;
    cursor: help;
    font-size: 12px;
    font-weight: 800;
    line-height: 1;
  }

  button:focus-visible {
    outline: 2px solid #0c4a8a;
    outline-offset: 2px;
  }

  [role="tooltip"] {
    position: absolute;
    z-index: 10;
    bottom: calc(100% + 7px);
    left: 50%;
    display: none;
    width: max-content;
    max-width: min(280px, calc(100vw - 32px));
    transform: translateX(-50%);
    border: 1px solid #0c4a8a;
    border-radius: 5px;
    padding: 8px 10px;
    background: #0f3d70;
    color: #ffffff;
    font-size: 12px;
    font-weight: 500;
    line-height: 1.35;
    text-align: left;
    text-transform: none;
  }

  .help-tooltip:hover [role="tooltip"],
  .help-tooltip:focus-within [role="tooltip"] {
    display: block;
  }
</style>
