<script lang="ts">
	import SEOHead from '$lib/components/SEOHead.svelte';
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { useQuery, useConvexClient } from 'convex-svelte';
	import { api } from '$lib/convex/_generated/api';
	import { getTranslate } from '@tolgee/svelte';
	import ThreadChat from './thread-chat.svelte';

	const { t } = getTranslate();

	let { data } = $props();

	const client = useConvexClient();

	// Auth
	const viewer = useQuery(api.users.viewer, {}, () => ({ initialData: data.viewer }));

	// Thread from URL param
	const threadId = $derived(page.url.searchParams.get('thread') ?? '');

	// Fallback: if navigated to /ai-chat without ?thread= (e.g. direct URL), get warm thread.
	let resolvingThread = $state(false);

	$effect(() => {
		if (!threadId && !resolvingThread && viewer.data) {
			resolvingThread = true;
			client
				.mutation(api.aiChat.threads.getOrCreateWarmThread, {})
				.then((result) => {
					const url = new URL(page.url);
					url.searchParams.set('thread', result.threadId);
					goto(resolve(url.pathname + url.search), { noScroll: true, replaceState: true });
				})
				.catch((err) => {
					console.error('[ai-chat] Failed to resolve warm thread:', err);
				})
				.finally(() => {
					resolvingThread = false;
				});
		}
	});
</script>

<SEOHead title={$t('meta.app.ai_chat.title')} description={$t('meta.app.ai_chat.description')} />

{#if viewer.data}
	<div class="flex h-full flex-col">
		<ThreadChat {threadId} />
	</div>
{/if}
