<script lang="ts">
  export let checked = false;
  export let label: string;
</script>

<label>
  <input bind:checked type="checkbox" />
  <span>{label}</span>
</label>

<style>
  label {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    color: #24352d;
    font-size: 13px;
    font-weight: 700;
  }

  input {
    width: 16px;
    height: 16px;
    accent-color: #1f5b42;
  }
</style>
