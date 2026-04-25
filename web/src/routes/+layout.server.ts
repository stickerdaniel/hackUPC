import type { LayoutServerLoad } from './$types';
import { api } from '$lib/convex/_generated/api';
import { createServerConvexHttpClient } from '$lib/server/convex-http';

type JwtViewer = {
	_id: string;
	name?: string | null;
	email?: string | null;
	image?: string | null;
	role?: string;
	emailVerified?: boolean;
	createdAt?: number;
	updatedAt?: number;
	banned?: boolean;
	locale?: string;
};

function getViewerFromJwt(token: string | undefined): JwtViewer | null {
	if (!token) return null;

	try {
		const payload = token.split('.')[1];
		if (!payload) return null;

		const decoded = JSON.parse(Buffer.from(payload, 'base64url').toString('utf-8')) as {
			sub?: string;
			name?: string;
			email?: string;
			image?: string | null;
			role?: string;
			emailVerified?: boolean;
			createdAt?: number;
			updatedAt?: number;
			banned?: boolean;
			locale?: string;
		};

		if (!decoded.sub) return null;

		return {
			_id: decoded.sub,
			name: decoded.name ?? null,
			email: decoded.email ?? null,
			image: decoded.image ?? null,
			role: decoded.role,
			emailVerified: decoded.emailVerified,
			createdAt: decoded.createdAt,
			updatedAt: decoded.updatedAt,
			banned: decoded.banned,
			locale: decoded.locale
		};
	} catch {
		return null;
	}
}

export const load: LayoutServerLoad = async (event) => {
	// Enables targeted invalidation when client-side auth state diverges from server state.
	// Prerendered pages bake authState.isAuthenticated: false at build time — when the client
	// recovers a session from cookies, AppAuthProvider detects the mismatch and calls
	// invalidate('app:auth') to re-run this load with fresh cookies.
	event.depends('app:auth');

	// Check if JWT token exists (set by handleAuth in hooks.server.ts)
	const isAuthenticated = !!event.locals.token;
	const authState = { isAuthenticated };
	const fallbackViewer = getViewerFromJwt(event.locals.token);

	let viewer = null;

	if (isAuthenticated) {
		const client = createServerConvexHttpClient({ token: event.locals.token });

		viewer = await client.query(api.auth.getCurrentUser, {}).catch((e) => {
			console.error('[+layout.server.ts] Viewer lookup failed, falling back to JWT payload:', e);
			return fallbackViewer;
		});
	}

	return {
		authState,
		viewer
	};
};
