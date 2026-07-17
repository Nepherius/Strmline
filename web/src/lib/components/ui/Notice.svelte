<script lang="ts">
  export let variant: "default" | "error" | "success" | "warning" = "default";
  export let dismissible = true;
  export let resetKey = "";

  let dismissed = false;
  let previousResetKey = resetKey;

  $: if (resetKey !== previousResetKey) {
    previousResetKey = resetKey;
    dismissed = false;
  }
</script>

{#if !dismissed}
  <div
    class:error={variant === "error"}
    class:success={variant === "success"}
    class:warning={variant === "warning"}
    class="notice"
    role={variant === "error" ? "alert" : "status"}
  >
    <div class="notice-content"><slot /></div>
    {#if dismissible}
      <button
        type="button"
        class="dismiss"
        aria-label="Dismiss notification"
        title="Dismiss"
        on:click={() => {
          dismissed = true;
        }}>×</button
      >
    {/if}
  </div>
{/if}

<style>
  .notice {
    display: flex;
    align-items: start;
    justify-content: space-between;
    gap: 12px;
    margin: 18px 0 0;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 12px;
    background: var(--surface);
    color: var(--text-soft);
  }

  .notice-content {
    min-width: 0;
  }

  .notice-content :global(p) {
    margin: 0;
  }

  .dismiss {
    flex: 0 0 auto;
    border: 0;
    padding: 0 2px;
    background: transparent;
    color: currentColor;
    font: inherit;
    font-size: 18px;
    line-height: 1;
    cursor: pointer;
    opacity: 0.75;
  }

  .dismiss:hover,
  .dismiss:focus-visible {
    opacity: 1;
  }

  .error {
    border-color: var(--danger-border);
    background: var(--danger-surface);
    color: var(--danger-text);
  }

  .success {
    border-color: var(--success-border);
    background: var(--success-surface);
    color: var(--success-text);
  }

  .warning {
    border-color: var(--warning-border);
    background: var(--warning-surface);
    color: var(--warning-text);
  }
</style>
