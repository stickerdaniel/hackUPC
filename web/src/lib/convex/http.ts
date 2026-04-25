import { httpRouter } from 'convex/server';
import { httpAction } from './_generated/server';
import { authComponent, createAuth } from './auth';
import { resend } from './emails/resend';
import { internal } from './_generated/api';

const http = httpRouter();

// Better Auth routes
authComponent.registerRoutes(http, createAuth);

// Resend webhook endpoint
// Configure this URL in your Resend dashboard: https://your-deployment.convex.site/resend-webhook
// This endpoint receives email events (delivered, bounced, complained, opened, clicked)
http.route({
	path: '/resend-webhook',
	method: 'POST',
	handler: httpAction(async (ctx, req) => {
		return await resend.handleResendEventWebhook(ctx, req);
	})
});

// Constant-time string compare to avoid timing oracle on the ingest secret.
// Both strings are short, but fixed-time comparison is the right default here.
function safeEqual(a: string, b: string): boolean {
	if (a.length !== b.length) return false;
	let mismatch = 0;
	for (let i = 0; i < a.length; i++) mismatch |= a.charCodeAt(i) ^ b.charCodeAt(i);
	return mismatch === 0;
}

// Sim ingest endpoint — Python simulation service POSTs each tick batch here.
// Body shape: { runId: Id<'simRuns'>, batchSeq: number, ticks: TickPayload[] }
// Auth: shared bearer in `x-sim-ingest-secret` header (must match
// SIM_INGEST_SECRET in the Convex env).
http.route({
	path: '/sim-ingest',
	method: 'POST',
	handler: httpAction(async (ctx, req) => {
		const expected = process.env.SIM_INGEST_SECRET;
		if (!expected) {
			return new Response(JSON.stringify({ error: 'ingest disabled' }), {
				status: 503,
				headers: { 'content-type': 'application/json' }
			});
		}
		const presented = req.headers.get('x-sim-ingest-secret') ?? '';
		if (!safeEqual(presented, expected)) {
			return new Response(JSON.stringify({ error: 'unauthorized' }), {
				status: 401,
				headers: { 'content-type': 'application/json' }
			});
		}

		let body: { runId: string; batchSeq: number; ticks: unknown[] };
		try {
			body = (await req.json()) as typeof body;
		} catch {
			return new Response(JSON.stringify({ error: 'invalid json' }), {
				status: 400,
				headers: { 'content-type': 'application/json' }
			});
		}

		try {
			// `ingestBatch` validates the full payload shape via convex/values.
			// Cast keeps the http.ts types loose; runtime validation is the gate.
			const result = await ctx.runMutation(internal.sim.mutations.ingestBatch, {
				runId: body.runId as never,
				batchSeq: body.batchSeq,
				ticks: body.ticks as never
			});
			return new Response(JSON.stringify({ ok: true, ...result }), {
				status: 200,
				headers: { 'content-type': 'application/json' }
			});
		} catch (err) {
			const message = err instanceof Error ? err.message : 'internal error';
			return new Response(JSON.stringify({ error: message }), {
				status: 400,
				headers: { 'content-type': 'application/json' }
			});
		}
	})
});

export default http;
