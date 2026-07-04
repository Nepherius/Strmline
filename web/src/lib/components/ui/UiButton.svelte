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
    border: 1px solid #1c4333;
    border-radius: 6px;
    padding: 0 14px;
    background: #1f5b42;
    color: #ffffff;
    cursor: pointer;
    font-weight: 700;
  }

  button.secondary {
    border-color: #bdc8c2;
    background: #ffffff;
    color: #24352d;
  }

  button:disabled {
    cursor: wait;
    opacity: 0.6;
  }
</style>
