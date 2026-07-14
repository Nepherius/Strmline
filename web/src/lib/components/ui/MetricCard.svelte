<script lang="ts">
  export let label: string;
  export let value: string | number;
  export let variant: "default" | "warn" | "ready" | "env" = "default";
</script>

<div
  class:env={variant === "env"}
  class:ready={variant === "ready"}
  class:warn={variant === "warn"}
  class="metric"
>
  <span>{label}</span>
  <strong>{value}</strong>
</div>

<style>
  .metric {
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 12px;
    background: var(--surface);
  }

  .metric.ready {
    border-color: var(--success-border);
    background: var(--success-surface);
  }

  .metric.env {
    border-color: #58658f;
    background: #30384f;
  }

  .metric.warn {
    border-color: var(--warning-border);
    background: var(--warning-surface);
  }

  span {
    display: block;
    color: var(--text-muted);
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
  }

  strong {
    display: block;
    margin-top: 6px;
    font-size: 24px;
  }
</style>
