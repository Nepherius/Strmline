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
    border: 1px solid #d7ded9;
    border-radius: 6px;
    padding: 12px;
    background: #ffffff;
  }

  .error {
    border-color: #e1a2a2;
    background: #fff5f4;
    color: #8e251f;
  }

  .success {
    border-color: #9bc9aa;
    background: #f0fff4;
    color: #1f5b42;
  }

  .warning {
    border-color: #d9b66c;
    background: #fff9ea;
    color: #765d1d;
  }
</style>
