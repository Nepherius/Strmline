<script lang="ts">
  import UiButton from "$lib/components/ui/UiButton.svelte";
  import type { SyncError } from "$lib/api/sync";

  export let errors: SyncError[];
  export let dismissingErrorId: number | null;
  export let onDismiss: (errorId: number) => Promise<void>;

  function formatDateTime(value: string): string {
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(value));
  }
</script>

{#if errors.length > 0}
  <section class="sync-errors" aria-label="Recent sync errors">
    <h2>Recent sync errors</h2>
    <div class="error-list">
      {#each errors as syncError (syncError.id)}
        <article>
          <div class="error-heading">
            <div>
              <strong>{syncError.phase}</strong>
              <span
                >Run #{syncError.sync_run_id} &middot; {formatDateTime(syncError.created_at)}</span
              >
            </div>
            <UiButton
              type="button"
              variant="secondary"
              disabled={dismissingErrorId === syncError.id}
              on:click={() => {
                void onDismiss(syncError.id);
              }}
            >
              {dismissingErrorId === syncError.id ? "Dismissing" : "Dismiss"}
            </UiButton>
          </div>
          {#if syncError.item_ref}
            <p class="item-ref">{syncError.item_ref}</p>
          {/if}
          <p>{syncError.message}</p>
        </article>
      {/each}
    </div>
  </section>
{/if}

<style>
  h2 {
    margin: 0;
    letter-spacing: 0;
    font-size: 15px;
  }

  .sync-errors {
    display: grid;
    gap: 10px;
    margin-top: 18px;
  }

  .error-list {
    display: grid;
    gap: 8px;
  }

  .error-list article {
    display: grid;
    gap: 8px;
    border: 1px solid var(--warning-border);
    border-radius: 6px;
    padding: 10px 12px;
    background: var(--warning-surface);
  }

  .error-heading {
    display: flex;
    flex-wrap: wrap;
    align-items: start;
    justify-content: space-between;
    gap: 8px;
  }

  .error-heading div {
    display: grid;
    gap: 4px;
  }

  .error-list strong {
    color: var(--warning-text);
  }

  .error-list span,
  .error-list p {
    margin: 0;
    color: var(--warning-text);
  }

  .error-list .item-ref {
    color: var(--warning-text);
    font-weight: 700;
  }
</style>
