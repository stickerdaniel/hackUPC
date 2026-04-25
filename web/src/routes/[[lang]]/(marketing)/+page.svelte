<script>
	import SEOHead from '$lib/components/SEOHead.svelte';
	import { getTranslate } from '@tolgee/svelte';
	import CopilotEmpty from '$blocks/hero/copilot-empty.svelte';
	import HealthTimeline from '$blocks/dashboard/health-timeline.svelte';
	import DriverCoupledDecay from '$blocks/dashboard/driver-coupled-decay.svelte';
	// import IntegrationOne from '$blocks/integration/integration-one.svelte';
	// import LazyCustomerSupport from '$lib/components/customer-support/lazy-customer-support.svelte';
	const { t } = getTranslate();
</script>

<SEOHead title={$t('meta.home.title')} description={$t('meta.home.description')} />
<!-- <LazyCustomerSupport /> -->

<CopilotEmpty />
<HealthTimeline />
<DriverCoupledDecay />
<!-- <IntegrationOne /> -->
