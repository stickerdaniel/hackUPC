<script lang="ts">
	import { getTranslate } from '@tolgee/svelte';
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { localizedHref } from '$lib/utils/i18n';
	import { useAuth } from '@mmailaender/convex-better-auth-svelte/svelte';
	import { useConvexClient, useQuery } from 'convex-svelte';
	import { toast } from 'svelte-sonner';
	import { VoiceInput } from '$lib/chat/voice/use-voice-input.svelte';
	import { api } from '$lib/convex/_generated/api';

	const { t } = getTranslate();
	const auth = useAuth();
	const convexClient = useConvexClient();
	const voice = new VoiceInput(convexClient);

	// Shared with ai-chat thread-chat.svelte (reads + clears on mount)
	const PENDING_PROMPT_KEY = 'copilot.pendingPrompt';

	const STATUS_LABELS = {
		FUNCTIONAL: 'functional',
		DEGRADED: 'degraded',
		CRITICAL: 'critical',
		FAILED: 'failed'
	} as const;
	type StatusKey = keyof typeof STATUS_LABELS;

	// Mockup fallback — used for unauthenticated visitors (most marketing
	// traffic). The moment a viewer is signed in AND has at least one run
	// in the historian, the LIVE eyebrow + the KPI pill row are overwritten
	// with real data; the decorative printer-illustration card on the right
	// keeps the mockup so the hero stays visually stable for all visitors.
	const MOCKUP_SCENARIO = {
		label: 'Phoenix',
		duty: 0.62,
		overall: 'CRITICAL' as StatusKey,
		components: {
			recoater_blade: { health: 0.62, status: 'DEGRADED' as StatusKey },
			linear_rail: { health: 0.78, status: 'FUNCTIONAL' as StatusKey },
			nozzle_plate: { health: 0.31, status: 'CRITICAL' as StatusKey },
			cleaning_interface: { health: 0.69, status: 'DEGRADED' as StatusKey },
			heating_elements: { health: 0.48, status: 'CRITICAL' as StatusKey },
			temp_sensor: { health: 0.83, status: 'FUNCTIONAL' as StatusKey }
		}
	} as const;
	// Alias the right-side printer-illustration card to the mockup. That
	// element is decorative; making it live too would force layout shifts
	// every tick and add no information beyond the KPI pills below.
	const scenario = MOCKUP_SCENARIO;

	// ──────────────────────────────────────────────────────────────────────
	// Live wall-clock — replaces the hardcoded TICK 14:08:32 string so the
	// "LIVE" eyebrow is at minimum a real ticking clock for every visitor,
	// not a fake timestamp.
	// ──────────────────────────────────────────────────────────────────────
	let now = $state(new Date());
	$effect(() => {
		const id = setInterval(() => {
			now = new Date();
		}, 1000);
		return () => clearInterval(id);
	});
	const wallClock = $derived(
		`${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}`
	);

	// ──────────────────────────────────────────────────────────────────────
	// Real run data — only fired for authenticated visitors. `useQuery` is
	// safe on prerendered marketing pages: it stays in a loading state on
	// the SSR pass and resubscribes after hydration once the auth cookie
	// is read by the Convex client.
	// ──────────────────────────────────────────────────────────────────────
	const runsQuery = useQuery(api.sim.queries.listMyRuns, () =>
		auth.isAuthenticated ? { limit: 1 } : 'skip'
	);
	const latestRun = $derived(runsQuery.data?.[0] ?? null);
	const stateQuery = useQuery(api.sim.queries.getStateAtTick, () =>
		latestRun && latestRun.lastTick !== undefined && latestRun.lastTick !== null
			? { runId: latestRun._id, tick: latestRun.lastTick }
			: 'skip'
	);
	const liveState = $derived(stateQuery.data);

	function statusFromHealth(h: number): StatusKey {
		if (h >= 0.75) return 'FUNCTIONAL';
		if (h >= 0.4) return 'DEGRADED';
		if (h >= 0.15) return 'CRITICAL';
		return 'FAILED';
	}
	const STATUS_RANK: Record<StatusKey, number> = {
		FUNCTIONAL: 0,
		DEGRADED: 1,
		CRITICAL: 2,
		FAILED: 3
	};
	function worstOf(parts: { health: number; status: StatusKey }[]): {
		health: number;
		status: StatusKey;
	} {
		let worst = parts[0]!;
		for (const p of parts) {
			if (STATUS_RANK[p.status] > STATUS_RANK[worst.status]) worst = p;
		}
		return worst;
	}

	const realScenario = $derived.by(() => {
		if (!latestRun || !liveState) return null;
		const byId: Record<string, { health: number; status: StatusKey }> = {};
		for (const c of liveState.components) {
			const status = (c.status in STATUS_LABELS ? c.status : 'FUNCTIONAL') as StatusKey;
			byId[c.componentId] = { health: c.healthIndex, status };
		}
		const blade = byId.blade ?? { health: 1, status: 'FUNCTIONAL' };
		const rail = byId.rail ?? { health: 1, status: 'FUNCTIONAL' };
		const nozzle = byId.nozzle ?? { health: 1, status: 'FUNCTIONAL' };
		const cleaning = byId.cleaning ?? { health: 1, status: 'FUNCTIONAL' };
		const heater = byId.heater ?? { health: 1, status: 'FUNCTIONAL' };
		const sensor = byId.sensor ?? { health: 1, status: 'FUNCTIONAL' };
		const subsystemMap = {
			recoating: worstOf([blade, rail]),
			printhead: worstOf([nozzle, cleaning]),
			thermal: worstOf([heater, sensor])
		};
		const overall = worstOf([
			subsystemMap.recoating,
			subsystemMap.printhead,
			subsystemMap.thermal
		]).status;
		return {
			label: latestRun.scenarioName,
			overall,
			subsystems: subsystemMap
		};
	});

	// Effective values — real when available, mockup otherwise.
	const overall = $derived<StatusKey>(realScenario?.overall ?? MOCKUP_SCENARIO.overall);
	const scenarioLabel = $derived(realScenario?.label ?? MOCKUP_SCENARIO.label);
	const subsystems = $derived([
		{
			id: 'recoating',
			label: 'Recoating',
			worst: realScenario?.subsystems.recoating ?? {
				health: MOCKUP_SCENARIO.components.recoater_blade.health,
				status: MOCKUP_SCENARIO.components.recoater_blade.status
			}
		},
		{
			id: 'printhead',
			label: 'Printhead',
			worst: realScenario?.subsystems.printhead ?? {
				health: MOCKUP_SCENARIO.components.nozzle_plate.health,
				status: MOCKUP_SCENARIO.components.nozzle_plate.status
			}
		},
		{
			id: 'thermal',
			label: 'Thermal',
			worst: realScenario?.subsystems.thermal ?? {
				health: MOCKUP_SCENARIO.components.heating_elements.health,
				status: MOCKUP_SCENARIO.components.heating_elements.status
			}
		}
	]);

	// Tick line — real `TICK N/HORIZON` when we have a live run, wall-clock
	// otherwise. Either way, never a hardcoded string.
	const tickLabel = $derived.by(() => {
		if (latestRun && latestRun.lastTick !== undefined && latestRun.lastTick !== null) {
			const horizon = latestRun.horizonTicks ?? '?';
			return `TICK ${latestRun.lastTick}/${horizon}`;
		}
		return wallClock;
	});

	const suggestedPromptKeys = [
		'hero.prompt_suggestion_1',
		'hero.prompt_suggestion_2',
		'hero.prompt_suggestion_3',
		'hero.prompt_suggestion_4'
	] as const;

	let prompt = $state('');
	let promptInputEl: HTMLInputElement | null = $state(null);

	function handleMicClick() {
		voice.toggle({
			target: promptInputEl,
			getValue: () => prompt,
			setValue: (next) => {
				prompt = next;
			},
			onError: (kind) =>
				toast.error(
					kind === 'permission'
						? $t('chat.error.mic_permission')
						: $t('chat.error.transcription_failed')
				)
		});
	}

	function handleSubmit(e: Event) {
		e.preventDefault();
		const text = prompt.trim();
		if (!text) return;

		try {
			sessionStorage.setItem(PENDING_PROMPT_KEY, text);
		} catch {
			// sessionStorage unavailable (private mode, etc.) — fall back to query param
			const target = auth.isAuthenticated
				? localizedHref('/app/ai-chat')
				: localizedHref(`/signin?redirectTo=${encodeURIComponent(localizedHref('/app/ai-chat'))}`);
			void goto(
				resolve(`${target}${target.includes('?') ? '&' : '?'}draft=${encodeURIComponent(text)}`)
			);
			return;
		}

		const target = auth.isAuthenticated
			? localizedHref('/app/ai-chat')
			: localizedHref(`/signin?redirectTo=${encodeURIComponent(localizedHref('/app/ai-chat'))}`);
		void goto(resolve(target));
	}

	function pickPrompt(text: string) {
		prompt = text;
	}

	const pct = (n: number) => `${Math.round(n * 100)}%`;

	function printerStatusLabel(status: keyof typeof STATUS_LABELS): string {
		return $t(`printer_status.${STATUS_LABELS[status]}`);
	}
</script>

<section class="copilot">
	<div class="empty-clean">
		<div class="empty-split">
			<div class="empty-left">
				<div class="eyebrow-clean mono">
					<span class="eyebrow-tick"></span>
					<span>DIGITAL TWIN · LIVE · {tickLabel}</span>
				</div>

				<h1 class="hero-title-clean">
					<span class="hero-title-line"
						>{$t('hero.printer_is_prefix')}
						<span class="hero-title-status" data-sev={overall}
							>{printerStatusLabel(overall)}</span
						>.</span
					>
					<span class="hero-title-line hero-title-soft">{$t('hero.ask_why')}</span>
				</h1>

				<p class="hero-sub-clean">
					{$t('hero.description')}
				</p>

				<form class="prompt-clean" onsubmit={handleSubmit}>
					<input
						class="prompt-input-clean"
						placeholder={$t('hero.prompt_placeholder')}
						bind:value={prompt}
						bind:this={promptInputEl}
					/>
					<div class="prompt-actions-clean">
						{#if auth.isAuthenticated}
							<button
								type="button"
								class="mic-btn"
								class:is-on={voice.state === 'recording'}
								disabled={voice.state === 'transcribing'}
								onclick={handleMicClick}
								aria-label={voice.state === 'recording'
									? $t('chat.tooltip.stop_recording')
									: $t('chat.tooltip.start_recording')}
								title={voice.state === 'recording'
									? $t('chat.tooltip.stop_recording')
									: $t('chat.tooltip.start_recording')}
							>
								{#if voice.state === 'recording'}
									<svg width="14" height="14" viewBox="0 0 14 14" fill="none">
										<rect x="2" y="2" width="10" height="10" fill="currentColor" />
									</svg>
								{:else if voice.state === 'transcribing'}
									<svg
										width="16"
										height="16"
										viewBox="0 0 16 16"
										fill="none"
										style="animation: copilot-pulse 1s ease-in-out infinite"
									>
										<circle
											cx="8"
											cy="8"
											r="6"
											stroke="currentColor"
											stroke-width="1.4"
											fill="none"
											stroke-dasharray="20 8"
										/>
									</svg>
								{:else}
									<svg width="16" height="16" viewBox="0 0 16 16" fill="none">
										<rect
											x="6"
											y="2"
											width="4"
											height="8"
											rx="2"
											stroke="currentColor"
											stroke-width="1.4"
										/>
										<path
											d="M3.5 8.5C3.5 11 5.5 13 8 13C10.5 13 12.5 11 12.5 8.5"
											stroke="currentColor"
											stroke-width="1.4"
										/>
										<line x1="8" y1="13" x2="8" y2="15" stroke="currentColor" stroke-width="1.4" />
									</svg>
								{/if}
							</button>
						{/if}
						<button
							type="submit"
							class="send-btn-clean"
							aria-label={$t('a11y.copilot_send')}
							disabled={!prompt.trim()}
						>
							<svg width="14" height="14" viewBox="0 0 14 14" fill="none">
								<path
									d="M2.5 7H11 M7 3 L11 7 L7 11"
									stroke="currentColor"
									stroke-width="1.6"
									stroke-linecap="round"
									stroke-linejoin="round"
								/>
							</svg>
						</button>
					</div>
				</form>

				<div class="chips-row">
					{#each suggestedPromptKeys as key (key)}
						<button type="button" class="chip-clean" onclick={() => pickPrompt($t(key))}>
							{$t(key)}
						</button>
					{/each}
				</div>

				<div class="kpi-row">
					<div class="kpi-pill">
						<span class="kpi-label">Printer</span>
						<span class="kpi-val">S100-01</span>
						<span class="kpi-dot" data-sev={overall}></span>
						<span class="kpi-val kpi-val-strong">{overall}</span>
					</div>
					{#each subsystems as ss (ss.id)}
						<div class="kpi-pill">
							<span class="kpi-label">{ss.label}</span>
							<span class="kpi-dot" data-sev={ss.worst.status}></span>
							<span class="kpi-val">{pct(ss.worst.health)}</span>
						</div>
					{/each}
					<div class="kpi-pill">
						<span class="kpi-label">Scenario</span>
						<span class="kpi-val">{scenarioLabel}</span>
					</div>
				</div>
			</div>

			<div class="empty-right">
				<div class="hero-card">
					<div class="hero-card-meta">
						<div class="hero-card-id mono">
							<span class="hero-card-dot"></span>
							<span>S100-01</span>
						</div>
						<div class="hero-card-loc mono">{scenario.label.toUpperCase()} · BAY 03</div>
					</div>

					<div class="hero-card-img">
						<img src="/printer-cutout.png" alt="HP Metal Jet S100" draggable="false" />

						<div class="pin pin-recoat" data-sev={scenario.components.recoater_blade.status}>
							<span class="pin-dot"></span>
							<span class="pin-line"></span>
							<span class="pin-tag mono">
								<span class="pin-code">RB-001</span>
								<span class="pin-name">Recoater</span>
								<span class="pin-val">{pct(scenario.components.recoater_blade.health)}</span>
							</span>
						</div>

						<div class="pin pin-print" data-sev={scenario.components.nozzle_plate.status}>
							<span class="pin-dot"></span>
							<span class="pin-line"></span>
							<span class="pin-tag mono">
								<span class="pin-code">NP-003</span>
								<span class="pin-name">Nozzle plate</span>
								<span class="pin-val">{pct(scenario.components.nozzle_plate.health)}</span>
							</span>
						</div>

						<div class="pin pin-thermal" data-sev={scenario.components.heating_elements.status}>
							<span class="pin-dot"></span>
							<span class="pin-line"></span>
							<span class="pin-tag mono">
								<span class="pin-code">HE-005</span>
								<span class="pin-name">Heaters</span>
								<span class="pin-val">{pct(scenario.components.heating_elements.health)}</span>
							</span>
						</div>
					</div>

					<div class="hero-card-foot mono">
						<span>HP METAL JET S100</span>
						<span class="hero-card-foot-sep">·</span>
						<span>BUILD VOLUME 430 × 309 × 140 MM</span>
						<span class="hero-card-foot-sep">·</span>
						<span>DUTY {pct(scenario.duty)}</span>
					</div>
				</div>
			</div>
		</div>
	</div>
</section>

<style>
	.copilot {
		--bg: #ffffff;
		--surface: #ffffff;
		--surface-2: #f4f4f4;
		--line: #e6e6e6;
		--line-2: #d4d4d4;
		--line-strong: #1a1a1a;
		--fg: #000000;
		--fg-2: #1a1a1a;
		--fg-3: #5a5a5a;
		--fg-4: #8a8a8a;
		--accent: #024ad8;
		--accent-soft: #e6ebfb;
		--sans: 'Wix Madefor Text', 'HP Simplified', 'Helvetica Neue', Helvetica, Arial, sans-serif;
		--display:
			'Wix Madefor Display', 'HP Simplified', 'Helvetica Neue', Helvetica, Arial, sans-serif;

		background: var(--bg);
		color: var(--fg);
		font-family: var(--sans);
		font-size: 14px;
		line-height: 1.5;
		-webkit-font-smoothing: antialiased;
		display: block;
	}

	.copilot :global(*) {
		box-sizing: border-box;
	}

	.mono {
		font-family: var(--sans);
		font-feature-settings:
			'tnum' 1,
			'zero' 1;
		letter-spacing: 0.02em;
	}

	@keyframes copilot-pulse {
		0%,
		100% {
			opacity: 1;
		}
		50% {
			opacity: 0.4;
		}
	}

	@keyframes copilot-pin-in {
		from {
			opacity: 0;
			transform: translateX(-8px);
		}
		to {
			opacity: 1;
			transform: translateX(0);
		}
	}

	@keyframes copilot-pin-pulse {
		0% {
			transform: scale(1);
			opacity: 0.5;
		}
		100% {
			transform: scale(2.2);
			opacity: 0;
		}
	}

	.empty-clean {
		position: relative;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: flex-start;
		padding: 100px 40px 80px;
		gap: 80px;
	}

	@media (max-width: 1000px) {
		.empty-clean {
			padding: 88px 24px 64px;
		}
	}

	.empty-split {
		width: 100%;
		max-width: 1280px;
		display: grid;
		grid-template-columns: minmax(0, 420px) minmax(320px, 1fr);
		gap: 48px;
		align-items: center;
	}

	.empty-left {
		display: flex;
		flex-direction: column;
		gap: 18px;
		min-width: 0;
	}

	.empty-right {
		position: relative;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	/* eyebrow */
	.eyebrow-clean {
		display: inline-flex;
		align-items: center;
		gap: 10px;
		font-size: 10px;
		letter-spacing: 0.2em;
		color: var(--fg);
		font-weight: 600;
		align-self: flex-start;
		text-transform: uppercase;
	}
	.eyebrow-clean::after {
		content: '';
		width: 32px;
		height: 2px;
		background: var(--accent);
	}
	.eyebrow-tick {
		width: 8px;
		height: 8px;
		background: var(--accent);
		animation: copilot-pulse 2.4s ease-in-out infinite;
	}

	/* headline */
	.hero-title-clean {
		font-family: var(--display);
		font-size: clamp(32px, 4.2vw, 52px);
		line-height: 1;
		font-weight: 800;
		letter-spacing: -0.035em;
		text-align: left;
		margin: 0;
		color: var(--fg);
		text-wrap: balance;
	}
	.hero-title-status {
		font-style: normal;
		font-weight: 700;
		color: var(--fg);
	}
	.hero-title-status[data-sev='DEGRADED'] {
		box-shadow: inset 0 -0.14em 0 var(--accent);
	}
	.hero-title-status[data-sev='CRITICAL'] {
		box-shadow: inset 0 -0.22em 0 var(--accent);
	}
	.hero-title-status[data-sev='FAILED'] {
		box-shadow: inset 0 -0.32em 0 var(--accent);
	}
	.hero-title-status[data-sev='FUNCTIONAL'] {
		box-shadow: inset 0 -0.1em 0 var(--accent);
	}
	.hero-title-line {
		display: block;
	}
	.hero-title-soft {
		color: var(--fg-3);
		font-weight: 400;
		letter-spacing: -0.025em;
	}
	.hero-sub-clean {
		font-size: 16px;
		line-height: 1.5;
		color: var(--fg-3);
		text-align: left;
		margin: 0 0 8px;
		max-width: 460px;
		font-weight: 400;
	}

	/* prompt */
	.prompt-clean {
		display: flex;
		align-items: center;
		gap: 8px;
		background: #ffffff;
		border: 2px solid var(--fg);
		border-radius: 0;
		padding: 10px 10px 10px 18px;
		transition:
			border-color 0.18s,
			box-shadow 0.18s,
			transform 0.18s;
	}
	.prompt-clean:focus-within {
		border-color: var(--accent);
		box-shadow: 4px 4px 0 0 var(--accent);
		transform: translate(-2px, -2px);
	}
	.prompt-input-clean {
		flex: 1;
		background: transparent;
		border: none;
		outline: none;
		color: var(--fg);
		font-family: var(--sans);
		font-size: 16px;
		padding: 8px 0;
	}
	.prompt-input-clean::placeholder {
		color: var(--fg-4);
	}
	.prompt-actions-clean {
		display: flex;
		align-items: center;
		gap: 6px;
	}
	.mic-btn,
	.send-btn-clean {
		width: 36px;
		height: 36px;
		display: flex;
		align-items: center;
		justify-content: center;
		border-radius: 0;
		border: none;
		background: transparent;
		color: var(--fg-3);
		cursor: pointer;
		transition: all 0.15s;
		font-family: inherit;
	}
	.mic-btn:hover {
		color: var(--fg);
		background: var(--surface-2);
	}
	.mic-btn.is-on {
		color: var(--accent);
		background: var(--accent-soft);
	}
	.send-btn-clean {
		background: var(--accent);
		color: #ffffff;
		font-weight: 600;
	}
	.send-btn-clean:hover:not(:disabled) {
		background: #0036a8;
	}
	.send-btn-clean:disabled {
		background: var(--surface-2);
		color: var(--fg-4);
		cursor: not-allowed;
	}

	/* chips */
	.chips-row {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
		justify-content: flex-start;
	}
	.chip-clean {
		padding: 9px 14px;
		background: #ffffff;
		border: 1px solid var(--fg);
		border-radius: 0;
		color: var(--fg);
		font-size: 12px;
		font-family: var(--sans);
		font-weight: 500;
		transition: all 0.12s;
		cursor: pointer;
		white-space: nowrap;
	}
	.chip-clean:hover {
		background: var(--fg);
		color: #ffffff;
	}

	/* KPI pills — capsule-shaped, light blue background */
	.kpi-row {
		margin-top: 8px;
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
	}
	.kpi-pill {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		padding: 6px 14px;
		background: #eff5ff;
		border: 1px solid #cfdcfa;
		border-radius: 999px;
		font-size: 12px;
		line-height: 1;
		white-space: nowrap;
	}
	.kpi-label {
		color: var(--accent);
		font-size: 10px;
		font-weight: 700;
		letter-spacing: 0.12em;
		text-transform: uppercase;
	}
	.kpi-val {
		color: var(--fg);
		font-size: 12px;
		font-weight: 500;
		letter-spacing: 0.01em;
		font-feature-settings:
			'tnum' 1,
			'zero' 1;
	}
	.kpi-val-strong {
		font-weight: 700;
		letter-spacing: 0.06em;
	}
	.kpi-dot {
		width: 7px;
		height: 7px;
		border-radius: 50%;
		flex-shrink: 0;
		background: #18a957;
	}
	.kpi-dot[data-sev='FUNCTIONAL'] {
		background: #18a957;
	}
	.kpi-dot[data-sev='DEGRADED'] {
		background: #f5a524;
	}
	.kpi-dot[data-sev='CRITICAL'] {
		background: #e5484d;
	}
	.kpi-dot[data-sev='FAILED'] {
		background: #b32430;
	}

	/* hero card */
	.hero-card {
		position: relative;
		width: 100%;
		background: transparent;
		border: none;
		box-shadow: none;
	}
	.hero-card-meta {
		position: relative;
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 16px;
		padding: 0 0 14px 0;
		border-bottom: 1px solid var(--line-strong);
		z-index: 2;
	}
	.hero-card-id {
		display: flex;
		align-items: center;
		gap: 10px;
		color: var(--fg);
		font-size: 11px;
		letter-spacing: 0.08em;
		font-weight: 700;
	}
	.hero-card-dot {
		width: 7px;
		height: 7px;
		border-radius: 50%;
		background: var(--accent);
		box-shadow: 0 0 0 4px rgba(0, 36, 219, 0.1);
		animation: copilot-pulse 2.4s ease-in-out infinite;
	}
	.hero-card-loc {
		font-size: 10px;
		letter-spacing: 0.14em;
		color: var(--fg-3);
		font-weight: 600;
	}
	.hero-card-img {
		position: relative;
		width: 110%;
		margin-left: -5%;
		aspect-ratio: 4 / 3;
		display: flex;
		align-items: center;
		justify-content: center;
		overflow: visible;
		margin-top: 12px;
		margin-bottom: 12px;
	}
	.hero-card-img img {
		width: 100%;
		height: auto;
		object-fit: contain;
		object-position: center;
	}
	.hero-card-foot {
		position: relative;
		display: flex;
		flex-wrap: wrap;
		gap: 10px 14px;
		align-items: center;
		padding: 14px 0 0 0;
		border-top: 1px solid var(--line-strong);
		font-size: 10px;
		letter-spacing: 0.12em;
		color: var(--fg-3);
		font-weight: 600;
		z-index: 2;
	}
	.hero-card-foot-sep {
		color: var(--line-strong);
	}

	/* annotation pins */
	.pin {
		position: absolute;
		display: flex;
		align-items: center;
		gap: 0;
		font-size: 10px;
		z-index: 3;
		animation: copilot-pin-in 0.6s ease-out backwards;
	}
	.pin-recoat {
		top: 32%;
		left: 16%;
		animation-delay: 0.1s;
	}
	.pin-print {
		top: 22%;
		left: 52%;
		animation-delay: 0.25s;
	}
	.pin-thermal {
		top: 56%;
		left: 70%;
		animation-delay: 0.4s;
	}
	.pin-dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		flex-shrink: 0;
		position: relative;
	}
	.pin-dot::before {
		content: '';
		position: absolute;
		inset: -4px;
		border-radius: 50%;
		border: 1px solid currentColor;
		opacity: 0.4;
		animation: copilot-pin-pulse 2s ease-out infinite;
	}
	.pin[data-sev='FUNCTIONAL'] {
		color: var(--fg);
	}
	.pin[data-sev='FUNCTIONAL'] .pin-dot {
		background: var(--fg);
		width: 6px;
		height: 6px;
		opacity: 0.45;
	}
	.pin[data-sev='FUNCTIONAL'] .pin-dot::before {
		display: none;
	}
	.pin[data-sev='DEGRADED'] {
		color: var(--fg);
	}
	.pin[data-sev='DEGRADED'] .pin-dot {
		background: var(--fg);
		width: 8px;
		height: 8px;
	}
	.pin[data-sev='CRITICAL'] {
		color: var(--accent);
		font-weight: 700;
	}
	.pin[data-sev='CRITICAL'] .pin-dot {
		background: var(--accent);
		width: 11px;
		height: 11px;
		box-shadow: 0 0 0 3px rgba(2, 74, 216, 0.18);
	}
	.pin[data-sev='FAILED'] {
		color: var(--accent);
		font-weight: 800;
	}
	.pin[data-sev='FAILED'] .pin-dot {
		background: var(--accent);
		width: 13px;
		height: 13px;
		box-shadow: 0 0 0 4px rgba(2, 74, 216, 0.28);
	}
	.pin-line {
		width: 28px;
		height: 1px;
		background: currentColor;
		opacity: 0.6;
	}
	.pin-tag {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 5px 9px;
		background: #ffffff;
		border: 1px solid var(--line-strong);
		border-left: 2px solid currentColor;
		border-radius: 0;
		font-size: 9.5px;
		letter-spacing: 0.06em;
		white-space: nowrap;
	}
	.pin-code {
		color: var(--fg-3);
		font-weight: 500;
	}
	.pin-name {
		color: var(--fg);
		font-weight: 600;
	}
	.pin-val {
		color: currentColor;
		font-weight: 700;
	}

	@media (max-width: 1000px) {
		.empty-split {
			grid-template-columns: 1fr;
			gap: 32px;
			max-width: 720px;
		}
	}
</style>
