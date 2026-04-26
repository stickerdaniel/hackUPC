<script lang="ts">
	import { T } from '@tolgee/svelte';
	import { localizedHref } from '$lib/utils/i18n';
	import { resolve } from '$app/paths';
	import Button from '$lib/components/ui/button/button.svelte';
</script>

<footer class="mt-auto pt-12">
	<div class="mx-auto max-w-[1500px] px-4 lg:px-6">
		<div
			class="w-full rounded-t-xl border-t marketing-shell-panel-footer [mask-image:linear-gradient(to_bottom,black_30%,transparent_100%)] px-5 pt-4 pb-12 lg:px-7"
		>
			<div class="flex items-start justify-between sm:items-center">
				<p class="text-xs text-muted-foreground">
					<T keyName="footer.copyright" params={{ year: new Date().getFullYear().toString() }} />
				</p>
				<!--
				<nav
					class="flex flex-col items-end gap-0 text-xs text-muted-foreground sm:flex-row sm:items-center sm:gap-1"
				>
					<Button
						variant="ghost"
						size="sm"
						href={resolve(localizedHref('/impressum'))}
						class="h-7 text-xs text-muted-foreground"
					>
						<T keyName="footer.impressum" />
					</Button>
					<span class="hidden sm:inline" aria-hidden="true">&middot;</span>
					<Button
						variant="ghost"
						size="sm"
						href={resolve(localizedHref('/terms'))}
						class="h-7 text-xs text-muted-foreground"
					>
						<T keyName="footer.terms" />
					</Button>
					<span class="hidden sm:inline" aria-hidden="true">&middot;</span>
					<Button
						variant="ghost"
						size="sm"
						href={resolve(localizedHref('/privacy'))}
						class="h-7 text-xs text-muted-foreground"
					>
						<T keyName="footer.privacy" />
					</Button>
				</nav>
				-->
			</div>
		</div>
	</div>
</footer>
