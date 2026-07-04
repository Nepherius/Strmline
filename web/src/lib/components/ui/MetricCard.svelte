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
    border: 1px solid #d7ded9;
    border-radius: 6px;
    padding: 12px;
    background: #ffffff;
  }

  .metric.ready {
    border-color: #9bc9aa;
    background: #f0fff4;
  }

  .metric.env {
    border-color: #9ebbd0;
    background: #f0f8ff;
  }

  .metric.warn {
    border-color: #d9b66c;
    background: #fff9ea;
  }

  span {
    display: block;
    color: #5b6a61;
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
