/**
 * Internal mutations for the printer simulation historian.
 *
 * Only callable from the HTTP ingest action and `sim/actions.ts`. Never
 * exposed to clients.
 *
 * `ingestBatch` is **idempotent + ordered**:
 *   - batchSeq === lastIngestedBatchSeq      → no-op (retry of committed batch)
 *   - batchSeq === lastIngestedBatchSeq + 1  → insert + advance pointer
 *   - anything else                          → throw, fail loudly
 *
 * This guards against the "Convex commit succeeded but the response was lost"
 * case while making sure we never silently skip an earlier batch.
 */
import { v, ConvexError } from 'convex/values';
import { internalMutation } from '../_generated/server';

const componentIdLiteral = v.union(
	v.literal('blade'),
	v.literal('rail'),
	v.literal('nozzle'),
	v.literal('cleaning'),
	v.literal('heater'),
	v.literal('sensor')
);

const operationalStatusLiteral = v.union(
	v.literal('FUNCTIONAL'),
	v.literal('DEGRADED'),
	v.literal('CRITICAL'),
	v.literal('FAILED'),
	v.literal('UNKNOWN')
);

const printOutcomeLiteral = v.union(
	v.literal('OK'),
	v.literal('QUALITY_DEGRADED'),
	v.literal('HALTED')
);

const operatorEventKindLiteral = v.union(
	v.literal('TROUBLESHOOT'),
	v.literal('FIX'),
	v.literal('REPLACE')
);

const tickPayload = v.object({
	tick: v.number(),
	simTimeS: v.number(),
	tsIso: v.string(),
	drivers: v.object({
		temperatureStress: v.number(),
		humidityContamination: v.number(),
		operationalLoad: v.number(),
		maintenanceLevel: v.number()
	}),
	env: v.object({
		baseAmbientC: v.number(),
		amplitudeC: v.number(),
		weeklyRuntimeHours: v.number(),
		vibrationLevel: v.number(),
		cumulativeCleanings: v.number(),
		hoursSinceMaintenance: v.number(),
		startStopCycles: v.number()
	}),
	couplingFactors: v.record(v.string(), v.number()),
	printOutcome: printOutcomeLiteral,
	componentsTrue: v.array(
		v.object({
			componentId: componentIdLiteral,
			healthIndex: v.number(),
			status: operationalStatusLiteral,
			ageTicks: v.number(),
			metrics: v.record(v.string(), v.number())
		})
	),
	componentsObserved: v.array(
		v.object({
			componentId: componentIdLiteral,
			observedHealthIndex: v.optional(v.number()),
			observedStatus: v.optional(operationalStatusLiteral),
			sensorNote: v.string(),
			observedMetrics: v.record(v.string(), v.union(v.number(), v.null())),
			sensorHealth: v.record(v.string(), v.union(v.number(), v.null()))
		})
	),
	envEvents: v.array(
		v.object({
			name: v.string(),
			payload: v.record(v.string(), v.union(v.number(), v.string(), v.boolean()))
		})
	),
	operatorEvents: v.array(
		v.object({
			kind: operatorEventKindLiteral,
			componentId: v.optional(componentIdLiteral),
			payload: v.record(v.string(), v.union(v.number(), v.string()))
		})
	)
});

export const recordRunStarted = internalMutation({
	args: {
		userId: v.string(),
		scenarioName: v.string(),
		seed: v.number(),
		dtSeconds: v.number(),
		horizonTicks: v.number(),
		configJson: v.string()
	},
	handler: async (ctx, args) => {
		const runId = await ctx.db.insert('simRuns', {
			userId: args.userId,
			scenarioName: args.scenarioName,
			seed: args.seed,
			dtSeconds: args.dtSeconds,
			horizonTicks: args.horizonTicks,
			configJson: args.configJson,
			status: 'running',
			startedAt: Date.now(),
			lastIngestedBatchSeq: -1
		});
		return runId;
	}
});

/**
 * Persist the resolved scenario config + the YAML's actual run defaults.
 *
 * Called from `_runScenarioForUser` after Python /runs returns. Patches three
 * fields whose pre-Python values in `recordRunStarted` are guesses (`?? 0`
 * etc.) and must be overwritten with what actually ran. Without this the
 * dashboard header would show seed=0 while `scenarioConfig.run.seed` says 7.
 */
export const recordRunConfig = internalMutation({
	args: {
		runId: v.id('simRuns'),
		scenarioConfig: v.string(),
		resolvedSeed: v.number(),
		resolvedHorizonTicks: v.number(),
		resolvedDtSeconds: v.number()
	},
	returns: v.null(),
	handler: async (ctx, args) => {
		const run = await ctx.db.get(args.runId);
		if (!run) throw new ConvexError(`run not found: ${args.runId}`);
		await ctx.db.patch(args.runId, {
			scenarioConfig: args.scenarioConfig,
			seed: args.resolvedSeed,
			horizonTicks: args.resolvedHorizonTicks,
			dtSeconds: args.resolvedDtSeconds
		});
		return null;
	}
});

export const recordRunCompleted = internalMutation({
	args: {
		runId: v.id('simRuns'),
		lastTick: v.number()
	},
	handler: async (ctx, args) => {
		const run = await ctx.db.get(args.runId);
		if (!run) throw new ConvexError(`run not found: ${args.runId}`);
		await ctx.db.patch(args.runId, {
			status: 'completed',
			completedAt: Date.now(),
			lastTick: args.lastTick,
			lastTickAt: Date.now()
		});
	}
});

export const recordRunFailed = internalMutation({
	args: {
		runId: v.id('simRuns'),
		errorMessage: v.string()
	},
	handler: async (ctx, args) => {
		const run = await ctx.db.get(args.runId);
		if (!run) throw new ConvexError(`run not found: ${args.runId}`);
		await ctx.db.patch(args.runId, {
			status: 'failed',
			completedAt: Date.now(),
			errorMessage: args.errorMessage
		});
	}
});

export const ingestBatch = internalMutation({
	args: {
		runId: v.id('simRuns'),
		batchSeq: v.number(),
		ticks: v.array(tickPayload)
	},
	handler: async (ctx, args) => {
		const run = await ctx.db.get(args.runId);
		if (!run) throw new ConvexError(`run not found: ${args.runId}`);

		// Idempotency: replay of a committed batch returns ok with no writes.
		if (args.batchSeq === run.lastIngestedBatchSeq) {
			return { applied: false, reason: 'already-applied' as const };
		}

		// Strict ordering: gaps fail loudly so the run cannot silently lose data.
		const expected = run.lastIngestedBatchSeq + 1;
		if (args.batchSeq !== expected) {
			throw new ConvexError(
				`out-of-order ingest for run ${args.runId}: expected batchSeq=${expected}, got ${args.batchSeq}`
			);
		}

		let maxTick = run.lastTick ?? -1;

		for (const tickPayloadRow of args.ticks) {
			const t = tickPayloadRow.tick;
			if (t > maxTick) maxTick = t;

			await ctx.db.insert('simTicks', {
				runId: args.runId,
				tick: t,
				simTimeS: tickPayloadRow.simTimeS,
				tsIso: tickPayloadRow.tsIso,
				drivers: tickPayloadRow.drivers,
				env: tickPayloadRow.env,
				couplingFactors: tickPayloadRow.couplingFactors,
				printOutcome: tickPayloadRow.printOutcome
			});

			for (const comp of tickPayloadRow.componentsTrue) {
				await ctx.db.insert('simComponents', {
					runId: args.runId,
					tick: t,
					componentId: comp.componentId,
					healthIndex: comp.healthIndex,
					status: comp.status,
					ageTicks: comp.ageTicks,
					metrics: comp.metrics
				});
			}

			for (const obs of tickPayloadRow.componentsObserved) {
				await ctx.db.insert('simObservedComponents', {
					runId: args.runId,
					tick: t,
					componentId: obs.componentId,
					observedHealthIndex: obs.observedHealthIndex,
					observedStatus: obs.observedStatus,
					sensorNote: obs.sensorNote,
					observedMetrics: obs.observedMetrics,
					sensorHealth: obs.sensorHealth
				});
			}

			for (const ev of tickPayloadRow.envEvents) {
				await ctx.db.insert('simEnvEvents', {
					runId: args.runId,
					tick: t,
					tsIso: tickPayloadRow.tsIso,
					name: ev.name,
					payload: ev.payload
				});
			}

			for (const ev of tickPayloadRow.operatorEvents) {
				await ctx.db.insert('simEvents', {
					runId: args.runId,
					tick: t,
					simTimeS: tickPayloadRow.simTimeS,
					tsIso: tickPayloadRow.tsIso,
					kind: ev.kind,
					componentId: ev.componentId,
					payload: ev.payload
				});
			}
		}

		await ctx.db.patch(args.runId, {
			lastIngestedBatchSeq: args.batchSeq,
			lastTick: maxTick,
			lastTickAt: Date.now()
		});

		return { applied: true, ingestedTicks: args.ticks.length, lastTick: maxTick };
	}
});
