<script lang="ts">
	import { getContext } from 'svelte';
	import { decodeString } from '$lib/utils';

	const i18n = getContext('i18n');

	export let id;

	export let number: number | string = '';
	export let title: string = 'N/A';

	export let onClick: Function = () => {};

	// Helper function to return only the domain from a URL
	function getDomain(url: string): string {
		const domain = url.replace('http://', '').replace('https://', '').split(/[/?#]/)[0];

		if (domain.startsWith('www.')) {
			return domain.slice(4);
		}
		return domain;
	}

	// Helper function to check if text is a URL and return the domain
	function formattedTitle(title: string): string {
		if (title.startsWith('http')) {
			return getDomain(title);
		}

		return title;
	}
</script>

{#if title !== 'N/A'}
	<button
		aria-label={$i18n.t('View source: {{title}}', { title: formattedTitle(decodeString(title)) })}
		title={formattedTitle(decodeString(title))}
		class="text-[10px] min-w-[1.1rem] w-fit translate-y-[2px] px-1.5 py-0.5 text-center dark:bg-white/5 dark:text-white/80 dark:hover:text-white bg-gray-50 text-black/80 hover:text-black transition rounded-xl"
		on:click={() => {
			onClick(id);
		}}
	>
		{number}
	</button>
{/if}
