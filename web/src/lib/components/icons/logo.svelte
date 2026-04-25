<script lang="ts">
	import type { IconProps } from '@lucide/svelte';
	import { cn } from '$lib/utils';

	// Accept IconProps for compatibility with LucideIcon type, but only use class
	let { class: className }: IconProps = $props();
</script>

<img
	src="/logo.svg"
	alt=""
	aria-hidden="true"
	class={cn('inline-block object-contain', className)}
/>
