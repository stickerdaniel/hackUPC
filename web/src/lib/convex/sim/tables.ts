/**
 * Convex tables for the printer simulation historian.
 *
 * Mirrors the SQLite historian (sim/src/copilot_sim/historian/schema.sql) in
 * document-oriented form. Every row carries `runId` + `tick` so the agent can
 * cite specific telemetry points back to the user.
 *
 * Run IDs are minted by `recordRunStarted` (Convex `Id<'simRuns'>`) and pushed
 * down to the Python service. Python never generates IDs.
 */
import { defineTable } from 'convex/server';
import { v } from 'convex/values';

const componentId = v.union(
	v.literal('blade'),
	v.literal('rail'),
	v.literal('nozzle'),
	v.literal('cleaning'),
	v.literal('heater'),
	v.literal('sensor')
);

const operationalStatus = v.union(
	v.literal('FUNCTIONAL'),
	v.literal('DEGRADED'),
	v.literal('CRITICAL'),
	v.literal('FAILED'),
	v.literal('UNKNOWN')
);

const printOutcome = v.union(v.literal('OK'), v.literal('QUALITY_DEGRADED'), v.literal('HALTED'));

const operatorEventKind = v.union(
	v.literal('TROUBLESHOOT'),
	v.literal('FIX'),
	v.literal('REPLACE')
);

const runStatus = v.union(
	v.literal('pending'),
	v.literal('running'),
	v.literal('completed'),
	v.literal('failed')
);

export const simRuns = defineTable({
	userId: v.string(),
	status: runStatus,
	scenarioName: v.string(),
	seed: v.number(),
	dtSeconds: v.number(),
	horizonTicks: v.number(),
	configJson: v.string(), // serialized RunRequest payload sent to Python
	// Resolved scenario config from Python's /runs response (post-override
	// model_dump). Stringified JSON; parsed at the consumer to keep the schema
	// free of Pydantic's evolving driver shapes.
	scenarioConfig: v.optional(v.string()),
	startedAt: v.number(),
	completedAt: v.optional(v.number()),
	lastTick: v.optional(v.number()),
	lastTickAt: v.optional(v.number()),
	// Idempotent ingest: ingestBatch requires batchSeq === lastIngestedBatchSeq + 1
	lastIngestedBatchSeq: v.number(),
	errorMessage: v.optional(v.string())
})
	.index('by_user', ['userId'])
	.index('by_status', ['status'])
	.index('by_started', ['startedAt']);

export const simTicks = defineTable({
	runId: v.id('simRuns'),
	tick: v.number(),
	simTimeS: v.number(),
	tsIso: v.string(),
	// drivers (raw, normalized 0..1)
	drivers: v.object({
		temperatureStress: v.number(),
		humidityContamination: v.number(),
		operationalLoad: v.number(),
		maintenanceLevel: v.number()
	}),
	// environment snapshot
	env: v.object({
		baseAmbientC: v.number(),
		amplitudeC: v.number(),
		weeklyRuntimeHours: v.number(),
		vibrationLevel: v.number(),
		cumulativeCleanings: v.number(),
		hoursSinceMaintenance: v.number(),
		startStopCycles: v.number()
	}),
	// 10 named coupling factors persisted as a flat object (sparse keys ok)
	couplingFactors: v.record(v.string(), v.number()),
	printOutcome
}).index('by_run_and_tick', ['runId', 'tick']);

export const simComponents = defineTable({
	runId: v.id('simRuns'),
	tick: v.number(),
	componentId,
	healthIndex: v.number(),
	status: operationalStatus,
	ageTicks: v.number(),
	// Physical metrics — keys vary per component (wear_level, clog_pct, etc.)
	metrics: v.record(v.string(), v.number())
}).index('by_run_tick_component', ['runId', 'tick', 'componentId']);

export const simObservedComponents = defineTable({
	runId: v.id('simRuns'),
	tick: v.number(),
	componentId,
	observedHealthIndex: v.optional(v.number()),
	observedStatus: v.optional(operationalStatus),
	sensorNote: v.string(),
	// Per-metric observed value (null = sensor absent / failed for that metric)
	observedMetrics: v.record(v.string(), v.union(v.number(), v.null())),
	sensorHealth: v.record(v.string(), v.union(v.number(), v.null()))
}).index('by_run_tick_component', ['runId', 'tick', 'componentId']);

export const simEvents = defineTable({
	runId: v.id('simRuns'),
	tick: v.number(),
	simTimeS: v.number(),
	tsIso: v.string(),
	kind: operatorEventKind,
	componentId: v.optional(componentId),
	payload: v.record(v.string(), v.union(v.number(), v.string()))
})
	.index('by_run', ['runId'])
	.index('by_run_kind', ['runId', 'kind']);

export const simEnvEvents = defineTable({
	runId: v.id('simRuns'),
	tick: v.number(),
	tsIso: v.string(),
	name: v.string(),
	payload: v.record(v.string(), v.union(v.number(), v.string(), v.boolean()))
}).index('by_run', ['runId']);
