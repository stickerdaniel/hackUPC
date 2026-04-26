<script lang="ts">
	import SEOHead from '$lib/components/SEOHead.svelte';
	import { getTranslate } from '@tolgee/svelte';
	import HealthTimeline from '$blocks/dashboard/health-timeline.svelte';
	import DriverCoupledDecay from '$blocks/dashboard/driver-coupled-decay.svelte';

	const { t } = getTranslate();

	// Run metadata. Hardcoded for now; will be sourced from the
	// SQLite historian once the run-selection wiring lands.
	const runMeta = {
		runId: 'barcelona-human-disruption-no-maintenance-42-20260425T191058',
		scenario: 'barcelona',
		profile: 'human-disruption-no-maintenance',
		seed: 42,
		horizon: 260,
		dt: '604800s',
		distribution: { ok: 13, degraded: 33, halted: 53 }
	} as const;
</script>

<SEOHead
	title={$t('meta.app.dashboard.title')}
	description={$t('meta.app.dashboard.description')}
/>

<div class="dashboard-page">
	<header class="dash-intro">
		<div class="dash-intro-eyebrow mono">
			<span class="dash-intro-domain">HPCT.WORK</span>
			<span class="dash-intro-sep">·</span>
			<span class="dash-intro-product">HP METAL JET S100 DIGITAL TWIN</span>
		</div>

		<div class="dash-intro-titlerow">
			<h1 class="dash-intro-title">
				HP <span class="dash-intro-title-accent">CoPilot</span>
				<span class="dash-intro-title-soft">Twin</span>
			</h1>
			<span class="dash-intro-role">
				<span class="dash-intro-role-dot"></span>
				OPERATOR
			</span>
		</div>

		<p class="dash-intro-desc">
			Operator dashboard for the coupled simulation engine — drivers, status decay, cascade
			attribution, sensor trust, and operator response, sourced from the SQLite historian for the
			selected run.
		</p>

		<div class="dash-intro-pills">
			<span class="dash-pill">
				<span class="dash-pill-label">RUN</span>
				<span class="dash-pill-val mono">{runMeta.runId}</span>
			</span>
			<span class="dash-pill">
				<span class="dash-pill-label">SCENARIO</span>
				<span class="dash-pill-val">{runMeta.scenario}</span>
			</span>
			<span class="dash-pill">
				<span class="dash-pill-label">PROFILE</span>
				<span class="dash-pill-val">{runMeta.profile}</span>
			</span>
			<span class="dash-pill">
				<span class="dash-pill-label">SEED</span>
				<span class="dash-pill-val mono">{runMeta.seed}</span>
			</span>
			<span class="dash-pill">
				<span class="dash-pill-label">HORIZON</span>
				<span class="dash-pill-val mono">{runMeta.horizon}</span>
			</span>
			<span class="dash-pill">
				<span class="dash-pill-label">DT</span>
				<span class="dash-pill-val mono">{runMeta.dt}</span>
			</span>
			<span class="dash-pill">
				<span class="dash-pill-label">OK</span>
				<span class="dash-pill-dot" data-sev="ok"></span>
				<span class="dash-pill-val mono">{runMeta.distribution.ok}%</span>
			</span>
			<span class="dash-pill">
				<span class="dash-pill-label">DEGRADED</span>
				<span class="dash-pill-dot" data-sev="degraded"></span>
				<span class="dash-pill-val mono">{runMeta.distribution.degraded}%</span>
			</span>
			<span class="dash-pill">
				<span class="dash-pill-label">HALTED</span>
				<span class="dash-pill-dot" data-sev="halted"></span>
				<span class="dash-pill-val mono">{runMeta.distribution.halted}%</span>
			</span>
		</div>
	</header>

	<HealthTimeline />
	<DriverCoupledDecay />
</div>

<style>
	.dashboard-page {
		min-height: 100%;
		background: #ffffff;
		--accent: #024ad8;
		--fg: #000000;
		--fg-3: #5a5a5a;
		--fg-4: #8a8a8a;
		--line: #e6e6e6;
		--sans: 'Wix Madefor Text', 'HP Simplified', 'Helvetica Neue', Helvetica, Arial, sans-serif;
		--display:
			'Wix Madefor Display', 'HP Simplified', 'Helvetica Neue', Helvetica, Arial, sans-serif;
	}

	.dash-intro {
		max-width: 1280px;
		margin: 0 auto;
		padding: 48px 40px 24px;
		font-family: var(--sans);
		color: var(--fg);
	}

	.mono {
		font-feature-settings:
			'tnum' 1,
			'zero' 1;
		letter-spacing: 0.02em;
	}

	.dash-intro-eyebrow {
		display: inline-flex;
		align-items: center;
		gap: 12px;
		font-size: 12px;
		font-weight: 700;
		letter-spacing: 0.18em;
		text-transform: uppercase;
		margin-bottom: 28px;
	}
	.dash-intro-domain {
		color: var(--accent);
	}
	.dash-intro-sep {
		color: var(--fg-4);
	}
	.dash-intro-product {
		color: var(--fg-3);
	}

	.dash-intro-titlerow {
		display: flex;
		align-items: center;
		gap: 24px;
		flex-wrap: wrap;
	}
	.dash-intro-title {
		font-family: var(--display);
		font-size: clamp(26px, 2.6vw, 36px);
		font-weight: 800;
		letter-spacing: -0.03em;
		line-height: 1;
		margin: 0;
		color: var(--fg);
	}
	.dash-intro-title-accent {
		color: var(--accent);
	}
	.dash-intro-title-soft {
		color: var(--fg-3);
		font-weight: 700;
	}

	.dash-intro-role {
		display: inline-flex;
		align-items: center;
		gap: 10px;
		padding: 9px 18px;
		background: #0a0a0a;
		color: #ffffff;
		font-size: 12px;
		font-weight: 700;
		letter-spacing: 0.16em;
		border-radius: 999px;
		text-transform: uppercase;
	}
	.dash-intro-role-dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: #18a957;
		box-shadow: 0 0 0 3px rgba(24, 169, 87, 0.18);
	}

	.dash-intro-desc {
		margin: 22px 0 28px;
		font-size: 16px;
		line-height: 1.55;
		color: var(--fg-3);
		max-width: 1100px;
	}

	.dash-intro-pills {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
	}
	.dash-pill {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		padding: 7px 16px;
		background: #eff5ff;
		border: 1px solid #cfdcfa;
		border-radius: 999px;
		font-size: 12px;
		line-height: 1;
		white-space: nowrap;
	}
	.dash-pill-label {
		color: var(--accent);
		font-size: 10px;
		font-weight: 700;
		letter-spacing: 0.14em;
		text-transform: uppercase;
	}
	.dash-pill-val {
		color: var(--fg);
		font-weight: 500;
	}
	.dash-pill-val.mono {
		font-feature-settings:
			'tnum' 1,
			'zero' 1;
	}
	.dash-pill-dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		flex-shrink: 0;
	}
	.dash-pill-dot[data-sev='ok'] {
		background: #18a957;
	}
	.dash-pill-dot[data-sev='degraded'] {
		background: #f5a524;
	}
	.dash-pill-dot[data-sev='halted'] {
		background: #e5484d;
	}

	@media (max-width: 720px) {
		.dash-intro {
			padding: 32px 24px 16px;
		}
		.dash-intro-titlerow {
			gap: 14px;
		}
	}
</style>
