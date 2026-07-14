<script lang="ts">
  export let type: "button" | "submit" = "button";
  export let disabled = false;
  export let variant: "primary" | "secondary" = "primary";
</script>

<button {type} {disabled} class:secondary={variant === "secondary"} on:click>
  <slot />
</button>

<style>
  button {
    height: 38px;
    border: 1px solid var(--accent-strong);
    border-radius: 6px;
    padding: 0 14px;
    background: var(--accent);
    color: var(--text);
    cursor: pointer;
    font-weight: 700;
  }

  button.secondary {
    border-color: var(--border);
    background: var(--surface);
    color: var(--text-soft);
  }

  button:disabled {
    cursor: wait;
    opacity: 0.6;
  }
</style>
