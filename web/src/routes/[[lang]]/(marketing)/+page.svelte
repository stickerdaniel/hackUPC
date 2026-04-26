<script>
	import SEOHead from '$lib/components/SEOHead.svelte';
	import { getTranslate } from '@tolgee/svelte';
	import CopilotEmpty from '$blocks/hero/copilot-empty.svelte';
	const { t } = getTranslate();
</script>

<SEOHead title={$t('meta.home.title')} description={$t('meta.home.description')} />

<CopilotEmpty />
