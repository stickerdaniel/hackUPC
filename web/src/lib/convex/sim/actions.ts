/**
 * Single control verb for the printer simulator.
 *
 * `runScenario` is the only mutation entry point clients (and the agent) get.
 * Maintenance schedules and chaos overlays travel as part of the scenario
 * config — there are no live mid-run mutations. A run is a one-shot compute
 * job; what-ifs are new runs.
 *
 * Convex owns runId. We mint via `recordRunStarted`, push that ID to Python
 * in the POST body, and Python uses it for HistorianWriter + IngestClient. If
 * the Python call fails we mark the run failed and re-throw.
 *
 * Two entry points share `_runScenarioForUser`:
 *   - `runScenario` (public action): client `useAction`. Derives userId from
 *     Better Auth via `authComponent.getAuthUser(ctx)`.
 *   - `runScenarioForUser` (internal action): agent createTool path. Receives
 *     userId from `ToolCtx.userId`. Auth identity does NOT cross
 *     `ctx.runAction` boundaries, so the tool MUST pass userId explicitly.
 */
import { ConvexError, v } from 'convex/values';
import { action, internalAction, type ActionCtx } from '../_generated/server';
import { internal } from '../_generated/api';
import { authComponent } from '../auth';

async function _runScenarioForUser(
	ctx: ActionCtx,
	userId: string,
	args: {
		scenario: string;
		seed?: number;
		horizonTicks?: number;
		dtSeconds?: number;
	}
): Promise<{ runId: string; status: 'completed'; tickCount: number }> {
	const baseUrl = process.env.PYTHON_SIM_BASE_URL;
	const apiKey = process.env.PYTHON_SIM_API_KEY;
	if (!baseUrl || !apiKey) {
		throw new ConvexError(
			'Sim service not configured: set PYTHON_SIM_BASE_URL and PYTHON_SIM_API_KEY'
		);
	}

	// Seed/horizon/dt from request override the YAML's run section. We
	// don't know the YAML's defaults here, so persist whatever the user
	// supplied (or fall back to barcelona-baseline's 5-year defaults
	// after Python reflects them in the historian's `runs` row).
	const seed = args.seed ?? 0;
	const horizonTicks = args.horizonTicks ?? 260;
	const dtSeconds = args.dtSeconds ?? 604800;

	const runId = await ctx.runMutation(internal.sim.mutations.recordRunStarted, {
		userId,
		scenarioName: args.scenario,
		seed,
		dtSeconds,
		horizonTicks,
		configJson: JSON.stringify(args)
	});

	try {
		const res = await fetch(`${baseUrl.replace(/\/$/, '')}/runs`, {
			method: 'POST',
			headers: {
				Authorization: `Bearer ${apiKey}`,
				'content-type': 'application/json'
			},
			body: JSON.stringify({
				run_id: runId,
				scenario: args.scenario,
				user_id: userId,
				seed: args.seed,
				horizon_ticks: args.horizonTicks,
				dt_seconds: args.dtSeconds
			})
		});

		if (!res.ok) {
			const text = await res.text();
			const errMsg = `Python /runs returned ${res.status}: ${text.slice(0, 300)}`;
			await ctx.runMutation(internal.sim.mutations.recordRunFailed, {
				runId,
				errorMessage: errMsg
			});
			throw new ConvexError(errMsg);
		}

		const result = (await res.json()) as {
			tick_count: number;
			status: string;
			resolved_config?: {
				run?: { seed?: number; horizon_ticks?: number; dt_seconds?: number };
				[k: string]: unknown;
			};
		};

		// Persist the resolved scenario config + the YAML's actual run defaults.
		// Tolerant of missing resolved_config so older Python images still work.
		if (result.resolved_config) {
			const runCfg = result.resolved_config.run ?? {};
			await ctx.runMutation(internal.sim.mutations.recordRunConfig, {
				runId,
				scenarioConfig: JSON.stringify(result.resolved_config),
				resolvedSeed: runCfg.seed ?? seed,
				resolvedHorizonTicks: runCfg.horizon_ticks ?? horizonTicks,
				resolvedDtSeconds: runCfg.dt_seconds ?? dtSeconds
			});
		}

		await ctx.runMutation(internal.sim.mutations.recordRunCompleted, {
			runId,
			lastTick: Math.max(0, result.tick_count - 1)
		});

		return { runId, status: 'completed' as const, tickCount: result.tick_count };
	} catch (err) {
		if (err instanceof ConvexError) throw err;
		const msg = err instanceof Error ? err.message : String(err);
		await ctx.runMutation(internal.sim.mutations.recordRunFailed, {
			runId,
			errorMessage: msg
		});
		throw new ConvexError(`runScenario failed: ${msg}`);
	}
}

export const runScenario = action({
	args: {
		scenario: v.string(),
		seed: v.optional(v.number()),
		horizonTicks: v.optional(v.number()),
		dtSeconds: v.optional(v.number())
	},
	handler: async (
		ctx,
		args
	): Promise<{ runId: string; status: 'completed'; tickCount: number }> => {
		const user = await authComponent.getAuthUser(ctx);
		if (!user) throw new ConvexError('Authentication required');
		return await _runScenarioForUser(ctx, (user as { _id: string })._id, args);
	}
});

export const runScenarioForUser = internalAction({
	args: {
		userId: v.string(),
		scenario: v.string(),
		seed: v.optional(v.number()),
		horizonTicks: v.optional(v.number()),
		dtSeconds: v.optional(v.number())
	},
	handler: async (
		ctx,
		args
	): Promise<{ runId: string; status: 'completed'; tickCount: number }> => {
		const { userId, ...rest } = args;
		return await _runScenarioForUser(ctx, userId, rest);
	}
});
