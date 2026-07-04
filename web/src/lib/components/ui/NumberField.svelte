<script lang="ts">
  export let label: string;
  export let value = "";
  export let placeholder = "";
  export let min: string | undefined = "0";
  export let step = "1";

  function updateValue(event: Event): void {
    value = (event.currentTarget as HTMLInputElement).value;
  }
</script>

<label>
  <span>{label}</span>
  <input
    inputmode="numeric"
    {min}
    {placeholder}
    {step}
    type="number"
    {value}
    on:input={updateValue}
  />
</label>

<style>
  label {
    display: grid;
    gap: 6px;
    color: #526057;
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
  }

  input {
    box-sizing: border-box;
    min-width: 260px;
    height: 38px;
    border: 1px solid #bcc8c1;
    border-radius: 6px;
    padding: 0 10px;
    background: #ffffff;
    color: #15201b;
  }

  @media (max-width: 860px) {
    input {
      min-width: 0;
      width: 100%;
    }
  }
</style>
