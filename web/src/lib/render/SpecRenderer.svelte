<script lang="ts">
	import { JsonUIProvider, Renderer, type Spec } from '@json-render/svelte';
	import { registry } from './registry';

	let { spec }: { spec: Spec } = $props();
</script>

<JsonUIProvider initialState={spec.state ?? {}}>
	<Renderer {spec} {registry} />
</JsonUIProvider>
