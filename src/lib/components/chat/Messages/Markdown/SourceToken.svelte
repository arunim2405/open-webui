<script lang="ts">
	import Source from './Source.svelte';

	export let id;
	export let token;
	export let sourceIds: string[] = [];
	export let onClick: Function = () => {};
</script>

{#if sourceIds}
	<span class="inline-flex gap-0.5">
		{#each token.ids as sourceNumber, idx}
			{@const identifier = token.citationIdentifiers?.[idx] ?? sourceNumber}
			<Source id={identifier} number={sourceNumber} title={sourceIds[sourceNumber - 1]} {onClick} />
		{/each}
	</span>
{:else}
	<span>{token.raw}</span>
{/if}
