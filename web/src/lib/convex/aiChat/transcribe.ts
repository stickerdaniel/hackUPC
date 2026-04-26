import { v, ConvexError } from 'convex/values';
import { action } from '../_generated/server';
import { authComponent } from '../auth';
import { aiChatRateLimiter } from './rateLimit';

const MAX_BYTES = 5 * 1024 * 1024;
const GROQ_URL = 'https://api.groq.com/openai/v1/audio/transcriptions';

/**
 * Transcribe a short audio clip via Groq Whisper.
 *
 * Authenticated + per-user rate-limited. Audio arrives as ArrayBuffer
 * (the runtime type of v.bytes()).
 */
export const transcribeAudio = action({
	args: {
		audio: v.bytes(),
		mimeType: v.string()
	},
	returns: v.string(),
	handler: async (ctx, { audio, mimeType }) => {
		const user = await authComponent.getAuthUser(ctx);
		if (!user) {
			throw new ConvexError('Authentication required');
		}

		const status = await aiChatRateLimiter.limit(ctx, 'aiChatTranscription', {
			key: user._id
		});
		if (!status.ok) {
			throw new ConvexError('Too many transcriptions. Please wait a moment.');
		}

		if (audio.byteLength === 0) {
			throw new ConvexError('Empty audio');
		}
		if (audio.byteLength > MAX_BYTES) {
			throw new ConvexError('Audio too large');
		}

		const apiKey = process.env.GROQ_API_KEY;
		if (!apiKey) {
			throw new ConvexError('GROQ_API_KEY not set');
		}

		const form = new FormData();
		form.append('file', new Blob([audio], { type: mimeType }), 'recording.webm');
		form.append('model', 'whisper-large-v3-turbo');
		form.append('response_format', 'text');
		form.append('temperature', '0');

		const res = await fetch(GROQ_URL, {
			method: 'POST',
			headers: { Authorization: `Bearer ${apiKey}` },
			body: form
		});
		if (!res.ok) {
			throw new ConvexError(`Groq STT ${res.status}: ${await res.text()}`);
		}
		return (await res.text()).trim();
	}
});
