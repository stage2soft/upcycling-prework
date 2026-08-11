<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import type { CandidateFile } from '../api'
import { parseLabel, type OverlayObject } from '../sourceLabelAdapters'

const props = defineProps<{ files: CandidateFile[]; labelJson: unknown }>()
const images = computed(() => props.files.filter(file => file.file_group === 'raw' && file.is_previewable_image))
const activeImage = ref<CandidateFile | null>(null), imageError = ref(''), natural = ref({ width: 1, height: 1 })
const color = ref('#22d3ee'), scale = ref(1), offset = ref({ x: 0, y: 0 }), dragging = ref(false), moved = ref(false)
const selectedObject = ref<OverlayObject | null>(null), dragStart = ref({ x: 0, y: 0, ox: 0, oy: 0 })
const stage = ref<HTMLElement | null>(null)
const parsed = computed(() => parseLabel(props.labelJson, natural.value.width > 1 ? natural.value : undefined))
const isWorldOnly = computed(() => parsed.value.coordinateSystem === 'world_xy')
const hasWorldOverlay = computed(() => Boolean(parsed.value.worldObjects?.length))
const worldViewBox = computed(() => (parsed.value.viewBox || [0, 0, 1, 1]).join(' '))
const canvasSize = computed(() => ({ width: parsed.value.width || natural.value.width, height: parsed.value.height || natural.value.height }))
const transform = computed(() => `translate(${offset.value.x}px, ${offset.value.y}px) scale(${scale.value})`)
watch(images, value => { activeImage.value = value[0] || null; reset() }, { immediate: true })
watch(() => props.labelJson, () => { selectedObject.value = null })
function reset() { imageError.value = ''; nextTick(fit) }
function fit() {
  if (isWorldOnly.value && !activeImage.value) { scale.value = 1; offset.value = { x: 0, y: 0 }; return }
  if (!stage.value || natural.value.width <= 1) { scale.value = 1; offset.value = { x: 0, y: 0 }; return }
  const next = Math.min(stage.value.clientWidth / natural.value.width, stage.value.clientHeight / natural.value.height) * .94
  scale.value = Math.max(.05, next)
  offset.value = { x: (stage.value.clientWidth - natural.value.width * scale.value) / 2, y: (stage.value.clientHeight - natural.value.height * scale.value) / 2 }
}
function loaded(event: Event) {
  const image = event.target as HTMLImageElement
  natural.value = { width: image.naturalWidth, height: image.naturalHeight }; imageError.value = ''
  try {
    const canvas = document.createElement('canvas'); canvas.width = 32; canvas.height = 32
    const context = canvas.getContext('2d', { willReadFrequently: true }); context?.drawImage(image, 0, 0, 32, 32)
    const pixels = context?.getImageData(0, 0, 32, 32).data
    if (pixels) { let luminance = 0; for (let i = 0; i < pixels.length; i += 4) luminance += .2126 * pixels[i] + .7152 * pixels[i + 1] + .0722 * pixels[i + 2]; color.value = luminance / (pixels.length / 4) > 145 ? '#e11d48' : '#22d3ee' }
  } catch { /* 사용자가 color picker에서 직접 선택할 수 있다. */ }
  nextTick(fit)
}
function wheel(event: WheelEvent) {
  const host = event.currentTarget as HTMLElement, rect = host.getBoundingClientRect()
  const pointerX = event.clientX - rect.left, pointerY = event.clientY - rect.top
  const old = scale.value, next = Math.min(8, Math.max(.2, old * Math.exp(-event.deltaY * .0007)))
  offset.value = { x: pointerX - (pointerX - offset.value.x) * next / old, y: pointerY - (pointerY - offset.value.y) * next / old }; scale.value = next
}
function down(event: PointerEvent) { dragging.value = true; moved.value = false; dragStart.value = { x: event.clientX, y: event.clientY, ox: offset.value.x, oy: offset.value.y }; (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId) }
function move(event: PointerEvent) { if (!dragging.value) return; const dx = event.clientX - dragStart.value.x, dy = event.clientY - dragStart.value.y; moved.value ||= Math.abs(dx) + Math.abs(dy) > 4; offset.value = { x: dragStart.value.ox + dx, y: dragStart.value.oy + dy } }
function up() { dragging.value = false }
async function choose(item: OverlayObject) { if (moved.value) return; await nextTick(); selectedObject.value = item }
const pathPoints = (item: OverlayObject) => item.points.map(p => `${p.x},${p.y}`).join(' ')
const pretty = (value: unknown) => JSON.stringify(value, null, 2)
</script>

<template>
  <section class="viewer-shell">
    <div class="viewer-tools">
      <span v-if="hasWorldOverlay" class="world-mode" :title="parsed.projectionNote"><v-icon icon="mdi-axis-arrow" size="15"/> 3D BBox</span>
      <div class="image-tabs" v-if="images.length">
        <button v-for="file in images" :key="file.id" :class="{ active: activeImage?.id === file.id }" @click="activeImage = file; reset()">{{ file.original_relative_path.split('/').at(-1) }}</button>
      </div>
      <span v-else class="muted">미리보기 가능한 이미지 없음</span>
      <label class="color-control">BBox <input v-model="color" type="color" /></label>
      <button class="icon-button" title="화면 맞춤" @click="reset"><v-icon icon="mdi-fit-to-screen-outline" /></button>
      <span class="zoom">{{ Math.round(scale * 100) }}%</span>
    </div>
    <div ref="stage" class="viewer-stage" :class="{ dragging }" @wheel.prevent="wheel" @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up">
      <div v-if="activeImage" class="transform-layer" :style="{ transform }">
        <img :src="activeImage.file_url" draggable="false" @load="loaded" @error="imageError = '원천 이미지를 불러오지 못했습니다.'" />
        <svg v-if="!isWorldOnly" class="overlay-svg" :viewBox="`0 0 ${canvasSize.width} ${canvasSize.height}`" preserveAspectRatio="none">
          <polygon v-for="item in parsed.objects" :key="item.id" :points="pathPoints(item)" :stroke="color" :class="{ selected: selectedObject?.id === item.id }" @click.stop="choose(item)" />
        </svg>
      </div>
      <div v-if="hasWorldOverlay" :class="activeImage ? 'world-inset' : 'world-transform-layer'" :style="activeImage ? undefined : { transform }" @pointerdown.stop @wheel.stop>
        <svg class="world-overlay-svg" :viewBox="worldViewBox" preserveAspectRatio="xMidYMid meet">
          <pattern id="world-grid" width="1" height="1" patternUnits="userSpaceOnUse"><path d="M 1 0 L 0 0 0 1" fill="none" stroke="rgba(148,163,184,.16)" stroke-width=".025"/></pattern>
          <rect :x="parsed.viewBox?.[0]" :y="parsed.viewBox?.[1]" :width="parsed.viewBox?.[2]" :height="parsed.viewBox?.[3]" fill="url(#world-grid)" />
          <polygon v-for="item in parsed.worldObjects" :key="item.id" :points="pathPoints(item)" :stroke="color" :class="{ selected: selectedObject?.id === item.id }" @click.stop="choose(item)" />
        </svg>
        <div class="world-view-label">XY Top View · quaternion 회전 적용</div>
      </div>
      <div v-if="!activeImage && !hasWorldOverlay" class="empty-state"><v-icon icon="mdi-cube-outline" size="54" /><strong>오브젝트 파일 묶음</strong><span>파일 정보는 우측 상세에서 확인할 수 있습니다.</span></div>
      <div v-if="imageError || parsed.error" class="viewer-alert"><v-icon icon="mdi-alert-circle-outline" /> {{ imageError || parsed.error }}</div>
      <aside v-if="selectedObject" class="object-overlay" @pointerdown.stop>
        <button class="close" @click="selectedObject = null">×</button>
        <h3>{{ selectedObject.title }}</h3>
        <div class="coordinate">x {{ Math.round(selectedObject.bbox[0]) }} · y {{ Math.round(selectedObject.bbox[1]) }} · w {{ Math.round(selectedObject.bbox[2]) }} · h {{ Math.round(selectedObject.bbox[3]) }}</div>
        <pre v-if="selectedObject.properties">{{ pretty(selectedObject.properties) }}</pre>
      </aside>
    </div>
    <div class="viewer-footer"><span>어댑터: {{ parsed.adapter }}</span><span>객체 {{ parsed.objects.length }}개</span><span v-if="parsed.projectionNote" class="projection-note" :title="parsed.projectionNote">이미지 투영: FOV 90° 가정</span><span>휠 확대 · 드래그 이동</span></div>
  </section>
</template>
