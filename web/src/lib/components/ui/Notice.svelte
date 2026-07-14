<script lang="ts">
  export let variant: "default" | "error" | "success" | "warning" = "default";
</script>

<p
  class:error={variant === "error"}
  class:success={variant === "success"}
  class:warning={variant === "warning"}
  class="notice"
>
  <slot />
</p>

<style>
  .notice {
    margin: 18px 0 0;
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 12px;
    background: var(--surface);
    color: var(--text-soft);
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
