import { tick } from 'svelte';
import type { ConvexClient } from 'convex/browser';
import { api } from '$lib/convex/_generated/api';

const MAX_MS = 60_000;

export type VoiceInputState = 'idle' | 'recording' | 'transcribing';

export type VoiceInputErrorKind = 'permission' | 'unsupported' | 'transcribe';

export type ToggleOpts = {
	target: HTMLTextAreaElement | HTMLInputElement | null;
	getValue: () => string;
	setValue: (next: string) => void;
	onError?: (kind: VoiceInputErrorKind, err?: unknown) => void;
};

export class VoiceInput {
	state = $state<VoiceInputState>('idle');

	private rec: MediaRecorder | null = null;
	private chunks: BlobPart[] = [];
	private stream: MediaStream | null = null;
	private autoStopTimer: ReturnType<typeof setTimeout> | null = null;
	private activeOpts: ToggleOpts | null = null;
	private mimeType: string = 'audio/webm';

	constructor(private client: ConvexClient) {}

	async toggle(opts: ToggleOpts) {
		if (this.state === 'transcribing') return;
		if (this.state === 'recording') {
			this.stop();
			return;
		}
		await this.start(opts);
	}

	cancel() {
		this.clearTimer();
		try {
			if (this.rec?.state === 'recording') this.rec.stop();
		} catch {
			// recorder may already be inactive
		}
		this.releaseStream();
		this.rec = null;
		this.chunks = [];
		this.activeOpts = null;
		this.state = 'idle';
	}

	private async start(opts: ToggleOpts) {
		if (typeof MediaRecorder === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
			opts.onError?.('unsupported');
			return;
		}
		try {
			this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
		} catch (err) {
			opts.onError?.('permission', err);
			return;
		}
		this.activeOpts = opts;
		this.chunks = [];
		this.rec = new MediaRecorder(this.stream);
		this.mimeType = this.rec.mimeType || 'audio/webm';
		this.rec.ondataavailable = (e) => {
			if (e.data.size > 0) this.chunks.push(e.data);
		};
		this.rec.onstop = () => void this.transcribeAndInsert();
		this.rec.start();
		this.state = 'recording';
		this.autoStopTimer = setTimeout(() => this.stop(), MAX_MS);
	}

	private stop() {
		this.clearTimer();
		try {
			if (this.rec?.state === 'recording') this.rec.stop();
		} catch {
			// already stopped — onstop will still fire
		}
	}

	private async transcribeAndInsert() {
		const opts = this.activeOpts;
		this.activeOpts = null;
		this.releaseStream();

		const blob = new Blob(this.chunks, { type: this.mimeType });
		this.chunks = [];
		this.rec = null;

		if (!opts || blob.size === 0) {
			this.state = 'idle';
			return;
		}

		this.state = 'transcribing';
		try {
			const audio = await blob.arrayBuffer();
			const text: string = await this.client.action(api.aiChat.transcribe.transcribeAudio, {
				audio,
				mimeType: blob.type || 'audio/webm'
			});
			if (text) await this.insertAtCursor(opts, text);
		} catch (err) {
			opts.onError?.('transcribe', err);
		} finally {
			this.state = 'idle';
		}
	}

	private async insertAtCursor(opts: ToggleOpts, text: string) {
		const ta = opts.target;
		const current = opts.getValue();
		if (!ta) {
			opts.setValue(current ? `${current} ${text}` : text);
			return;
		}
		const start = ta.selectionStart ?? current.length;
		const end = ta.selectionEnd ?? current.length;
		const next = current.slice(0, start) + text + current.slice(end);
		opts.setValue(next);
		await tick();
		ta.focus();
		const pos = start + text.length;
		ta.setSelectionRange(pos, pos);
	}

	private releaseStream() {
		this.stream?.getTracks().forEach((t) => t.stop());
		this.stream = null;
	}

	private clearTimer() {
		if (this.autoStopTimer) {
			clearTimeout(this.autoStopTimer);
			this.autoStopTimer = null;
		}
	}
}
