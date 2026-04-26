<script lang="ts">
	import SEOHead from '$lib/components/SEOHead.svelte';
	import { getTranslate } from '@tolgee/svelte';
	import HealthTimeline from '$blocks/dashboard/health-timeline.svelte';
	import DriverCoupledDecay from '$blocks/dashboard/driver-coupled-decay.svelte';

	const { t } = getTranslate();
</script>

<SEOHead
	title={$t('meta.app.dashboard.title')}
	description={$t('meta.app.dashboard.description')}
/>

<div class="dashboard-page">
	<HealthTimeline />
	<DriverCoupledDecay />
</div>

<style>
	.dashboard-page {
		min-height: 100%;
		background: #ffffff;
	}
</style>
