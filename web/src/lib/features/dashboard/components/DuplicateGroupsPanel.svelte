<script lang="ts">
  import type { LibraryDuplicateGroup, LibraryFile } from "$lib/domain/library/summary";

  export let groups: LibraryDuplicateGroup[];
  export let disabled = false;
  export let removingKey = "";
  export let onHideFile: (file: LibraryFile) => Promise<void>;
</script>

<section class="duplicates" aria-label="Duplicate groups">
  <h2>Duplicate groups</h2>
  <div class="duplicate-list">
    {#each groups as group (group.key)}
      <article>
        <div class="group-header">
          <strong>{group.files[0]?.title}</strong>
          <span>{group.files.length} files</span>
        </div>
        <div class="file-list">
          {#each group.files as file (file.relative_path)}
            <div class="file-row">
              <code>{file.relative_path}</code>
              <button
                type="button"
                disabled={disabled || removingKey === file.relative_path}
                title="Hide this generated duplicate without removing it from TorBox"
                aria-label="Hide this generated duplicate without removing it from TorBox"
                on:click={() => {
                  void onHideFile(file);
                }}
              >
                <span aria-hidden="true">{removingKey === file.relative_path ? "..." : "×"}</span>
              </button>
            </div>
          {/each}
        </div>
      </article>
    {/each}
  </div>
</section>

<style>
  .duplicates {
    display: grid;
    gap: 10px;
    margin-bottom: 12px;
  }

  .duplicate-list {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 8px;
  }

  article {
    display: grid;
    gap: 8px;
    border: 1px solid #d9b66c;
    border-radius: 6px;
    padding: 10px;
    background: #fff9ea;
  }

  .group-header,
  .file-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
  }

  .group-header span {
    color: #765d1d;
    white-space: nowrap;
  }

  .file-list {
    display: grid;
    gap: 6px;
  }

  code {
    overflow-wrap: anywhere;
    color: #4f5d55;
    font-size: 11px;
  }

  button {
    display: inline-grid;
    flex: 0 0 auto;
    place-items: center;
    width: 28px;
    height: 28px;
    border: 1px solid #d7aca7;
    border-radius: 6px;
    padding: 0;
    background: #fff5f4;
    color: #8d2d23;
    cursor: pointer;
    font-size: 18px;
    font-weight: 800;
    line-height: 1;
  }

  button:disabled {
    cursor: wait;
    opacity: 0.6;
  }
</style>
