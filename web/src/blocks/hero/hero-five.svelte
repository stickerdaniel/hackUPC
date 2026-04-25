<script>
	import { T } from '@tolgee/svelte';
	import { localizedHref } from '$lib/utils/i18n';
	import Button from '$lib/components/ui/button/button.svelte';
	import ChevronRight from '@lucide/svelte/icons/chevron-right';
	import printerImg from '../marketing/printer-white.png?url';
</script>

<div class="overflow-hidden">
	<section class="relative flex items-center justify-center">
		<img
			src={printerImg}
			alt=""
			aria-hidden="true"
			loading="lazy"
			class="pointer-events-none absolute -bottom-1/5 hidden h-[550px] w-[550px] object-contain lg:-bottom-1/6 lg:left-[45%] lg:block lg:h-[700px] lg:w-[700px] xl:left-[52%]"
		/>

		<div class="pointer-events-none w-full pt-20 pb-56 lg:pt-40 lg:pb-36">
			<div class="relative mx-auto flex max-w-6xl flex-col px-6 lg:block lg:px-12">
				<div class="mx-auto max-w-lg text-center lg:ml-0 lg:max-w-full lg:text-left">
					<h1 class="mt-8 max-w-4xl text-5xl md:text-6xl lg:mt-16 xl:text-7xl">
						<span class="whitespace-pre-line"><T keyName="hero.tagline" /></span>
					</h1>
					<p class="mt-8 max-w-3xl text-lg text-balance">
						<T keyName="hero.description" />
					</p>
					<div
						class="mt-12 flex flex-col items-center justify-center gap-2 sm:flex-row lg:justify-start"
					>
						<Button
							size="lg"
							href={localizedHref('/signup')}
							class=" pointer-events-auto h-12 rounded-full pr-3 pl-5 text-sm"
						>
							<span class="text-nowrap"><T keyName="hero.cta" /></span>
							<ChevronRight class="ml-1" />
						</Button>
						<Button
							size="lg"
							variant="ghost"
							href="#link"
							class="pointer-events-auto h-12 rounded-full px-5 text-base hover:bg-zinc-950/5 dark:hover:bg-white/5"
						>
							<span class="text-nowrap"><T keyName="hero.cta_demo" /></span>
						</Button>
					</div>
				</div>
			</div>
		</div>
	</section>
</div>
