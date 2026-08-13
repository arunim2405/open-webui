<script lang="ts">
	import { getContext } from 'svelte';
	import { decodeString } from '$lib/utils';

	const i18n = getContext('i18n');

	export let id;

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

	const getDisplayTitle = (title: string) => {
		if (!title) return 'N/A';
		// Favor the title: head-truncate with a single ellipsis so the start of the
		// name is always shown. A trailing "(p. N)" tag naturally drops off when the
		// title is long, which is preferred over letting it crowd out the title.
		const MAX_LENGTH = 40;
		return title.length > MAX_LENGTH ? title.slice(0, MAX_LENGTH - 1).trimEnd() + '…' : title;
	};

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
		class="text-[10px] w-fit translate-y-[2px] px-2 py-0.5 dark:bg-white/5 dark:text-white/80 dark:hover:text-white bg-gray-50 text-black/80 hover:text-black transition rounded-xl"
		on:click={() => {
			onClick(id);
		}}
	>
		<span class="line-clamp-1">
			{getDisplayTitle(formattedTitle(decodeString(title)))}
		</span>
	</button>
{/if}
