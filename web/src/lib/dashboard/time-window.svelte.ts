import { getContext, setContext } from 'svelte';

// Time-window control shared by every chart on the dashboard.
// Sizes are in weekly ticks (dt = 1 week) so they stay aligned with the
// Streamlit panel-1 control vocabulary in sim/.../streamlit_app.py.
export type WindowLabel = '6mo' | '1y' | '3y' | 'all';

export const WINDOW_OPTIONS: ReadonlyArray<{ label: WindowLabel; size: number }> = [
	{ label: '6mo', size: 26 },
	{ label: '1y', size: 52 },
	{ label: '3y', size: 156 },
	{ label: 'all', size: Number.POSITIVE_INFINITY }
];

export class TimeWindow {
	horizon = $state(0);
	windowLabel = $state<WindowLabel>('1y');
	startTick = $state(0);

	constructor(horizon: number) {
		this.horizon = horizon;
	}

	setHorizon(h: number) {
		this.horizon = h;
		// Keep startTick valid when horizon shrinks (e.g. the user switches
		// from a long run to a short one).
		if (this.startTick > this.upperStart) this.startTick = this.upperStart;
	}

	get windowSize(): number {
		const opt = WINDOW_OPTIONS.find((w) => w.label === this.windowLabel);
		const raw = opt?.size ?? this.horizon;
		return Number.isFinite(raw) ? Math.min(raw, this.horizon) : this.horizon;
	}
	get upperStart(): number {
		return Math.max(0, this.horizon - this.windowSize);
	}
	get endTick(): number {
		return Math.min(this.horizon, this.startTick + this.windowSize);
	}
	get panStep(): number {
		return Math.max(1, Math.floor(this.windowSize / 2));
	}
	get atLeft(): boolean {
		return this.startTick <= 0;
	}
	get atRight(): boolean {
		return this.startTick >= this.upperStart;
	}

	setLabel(l: WindowLabel) {
		this.windowLabel = l;
		if (this.startTick > this.upperStart) this.startTick = this.upperStart;
	}
	panPrev() {
		if (this.atLeft) return;
		this.startTick = Math.max(0, this.startTick - this.panStep);
	}
	panNext() {
		if (this.atRight) return;
		this.startTick = Math.min(this.upperStart, this.startTick + this.panStep);
	}
}

const KEY = Symbol('dashboard.timeWindow');

export function provideTimeWindow(tw: TimeWindow): TimeWindow {
	setContext(KEY, tw);
	return tw;
}

// Returns the dashboard-provided TimeWindow when present, otherwise a fresh
// local instance so the chart blocks remain usable in isolation.
export function useTimeWindow(fallbackHorizon: number): TimeWindow {
	return (getContext(KEY) as TimeWindow | undefined) ?? new TimeWindow(fallbackHorizon);
}
