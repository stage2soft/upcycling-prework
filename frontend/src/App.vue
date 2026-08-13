<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { api, apiError, copyConflictPaths, type AppSettings, type Candidate, type CandidateFile, type CandidatePage, type DirectoryListing, type TextPreview, type VolumeOverview } from './api'
import SelectionViewer from './components/SelectionViewer.vue'

const settings = ref<AppSettings>({ mapping_strategy: 'file_name', json_ref_key: 'data_key', raw_relative_path: '', labeled_relative_path: '', annotation_method_code: 'bbox_2d' })
const page = ref<CandidatePage>({ results: [], count: 0, page: 1, page_size: 20, total_pages: 0, summary: {} })
const filters = ref({ selection_status: '', match_status: '', search: '' }), pageNo = ref(1)
const candidateWidth = ref(480), resizingCandidate = ref(false), resizeStart = ref({ x: 0, width: 480 })
const selected = ref<Candidate | null>(null), loading = ref(false), detailLoading = ref(false)
const folderOpen = ref(false), folderTarget = ref<'raw_relative_path' | 'labeled_relative_path'>('raw_relative_path'), folderLoading = ref(false)
const folders = ref<DirectoryListing>({ root_container_path: '/data/root', root_host_path: '', current: '', parent: '', directories: [] })
const volumesOpen = ref(false), volumesLoading = ref(false)
const volumes = ref<VolumeOverview>({ volumes: [], selected_directories: [] })
const filePreviewOpen = ref(false), filePreview = ref<CandidateFile | null>(null), filePreviewError = ref('')
const textPreviewLoading = ref(false), textPreview = ref<TextPreview>({ previewable: false })
const overwriteConfirmOpen = ref(false), overwriteConflicts = ref<string[]>([])
const notice = ref({ show: false, text: '', color: 'success' }), searchTimer = ref<number>()
const rawFiles = computed(() => selected.value?.files.filter(item => item.file_group === 'raw') || [])
const labelFiles = computed(() => selected.value?.files.filter(item => item.file_group === 'labeled') || [])
const canSelect = computed(() => selected.value?.match_status === 'matched' && selected.value?.selection_status !== 'selected')
const previewIsImage = computed(() => Boolean(filePreview.value?.is_previewable_image))
const previewIsLabelJson = computed(() => filePreview.value?.file_group === 'labeled' && filePreview.value?.extension === '.json')
const statusText: Record<string, string> = { pending: '대기', selected: '선택', rejected: '제외', move_failed: '복사 실패', matched: '매칭', unmatched: '미매칭', conflict: '충돌', error: '오류' }
const statusColor: Record<string, string> = { pending: 'warning', selected: 'success', rejected: 'grey', move_failed: 'error', matched: 'primary', unmatched: 'grey', conflict: 'warning', error: 'error' }
function toast(text: string, color = 'success') { notice.value = { show: true, text, color } }
async function loadList(keepSelection = true) {
  loading.value = true
  try {
    page.value = await api.candidates({ ...filters.value, selection_status: filters.value.selection_status || undefined, match_status: filters.value.match_status || undefined, page: pageNo.value, page_size: 20 })
    if (!keepSelection || (selected.value && !page.value.results.some(item => item.id === selected.value?.id))) selected.value = null
  } catch (e) { toast(apiError(e), 'error') } finally { loading.value = false }
}
async function openCandidate(item: Candidate) { detailLoading.value = true; try { selected.value = await api.candidate(item.id) } catch (e) { toast(apiError(e), 'error') } finally { detailLoading.value = false } }
async function scan() { loading.value = true; try { const result = await api.scan(settings.value); toast(`스캔 완료: 신규 ${result.created}건, 갱신 ${result.updated}건`); pageNo.value = 1; await loadList(false) } catch (e) { toast(apiError(e), 'error') } finally { loading.value = false } }
async function saveSettings() { try { settings.value = await api.saveSettings(settings.value); await scan() } catch (e) { toast(apiError(e), 'error') } }
async function browseFolder(path = '', showError = true): Promise<boolean> { folderLoading.value = true; try { folders.value = await api.directories(path); return true } catch (e) { if (showError) toast(apiError(e), 'error'); return false } finally { folderLoading.value = false } }
async function openFolder(target: 'raw_relative_path' | 'labeled_relative_path') {
  folderTarget.value = target
  folderOpen.value = true
  const selectedPath = settings.value[target]
  if (!selectedPath || !await browseFolder(selectedPath, false)) await browseFolder('')
}
function chooseFolder() { if (!folders.value.current) return toast('최상위 폴더 아래의 데이터 폴더를 선택하세요.', 'error'); settings.value[folderTarget.value] = folders.value.current; folderOpen.value = false }
function folderName(path: string) { return path.split('/').filter(Boolean).at(-1) || '데이터 루트에서 선택' }
function startCandidateResize(event: PointerEvent) {
  if (window.innerWidth <= 760) return
  resizingCandidate.value = true
  resizeStart.value = { x: event.clientX, width: candidateWidth.value }
  ;(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId)
}
function resizeCandidate(event: PointerEvent) {
  if (!resizingCandidate.value) return
  candidateWidth.value = Math.min(480, Math.max(280, resizeStart.value.width + event.clientX - resizeStart.value.x))
}
function stopCandidateResize() { resizingCandidate.value = false }
async function openVolumes() { volumesOpen.value = true; volumesLoading.value = true; try { volumes.value = await api.volumes() } catch (e) { toast(apiError(e), 'error') } finally { volumesLoading.value = false } }
function usagePercent(volume: VolumeOverview['volumes'][number]) { return volume.total_bytes ? Math.round(volume.used_bytes / volume.total_bytes * 100) : 0 }
async function openFilePreview(file: CandidateFile) {
  filePreview.value = file; filePreviewError.value = ''; textPreview.value = { previewable: false }; filePreviewOpen.value = true
  if (!file.is_previewable_image && !(file.file_group === 'labeled' && file.extension === '.json') && selected.value) {
    textPreviewLoading.value = true
    try { textPreview.value = await api.fileText(selected.value.id, file.id) }
    catch (e) { textPreview.value = { previewable: false, reason: apiError(e) } }
    finally { textPreviewLoading.value = false }
  }
}
async function decide(decision: 'selected' | 'rejected', overwrite = false) { if (!selected.value) return; detailLoading.value = true; try { selected.value = await api.decision(selected.value.id, decision, overwrite); overwriteConfirmOpen.value = false; toast(decision === 'selected' ? '원본 폴더 구조를 유지하여 선택 위치로 복사했습니다.' : '대상에서 제외했습니다.'); await loadList() } catch (e) { const conflicts = copyConflictPaths(e); if (decision === 'selected' && conflicts) { overwriteConflicts.value = conflicts; overwriteConfirmOpen.value = true } else { toast(apiError(e), 'error'); await loadList() } } finally { detailLoading.value = false } }
async function resetDecision() { if (!selected.value) return; try { selected.value = await api.reset(selected.value.id); toast('선별 상태를 대기로 복구했습니다.'); await loadList() } catch (e) { toast(apiError(e), 'error') } }
function bytes(size: number) { if (size < 1024) return `${size} B`; if (size < 1048576) return `${(size / 1024).toFixed(1)} KB`; return `${(size / 1048576).toFixed(1)} MB` }
function date(value: number | string) { return new Date(typeof value === 'number' ? value * 1000 : value).toLocaleString('ko-KR') }
watch(() => [filters.value.selection_status, filters.value.match_status], () => { pageNo.value = 1; loadList(false) })
watch(() => filters.value.search, () => { clearTimeout(searchTimer.value); searchTimer.value = window.setTimeout(() => { pageNo.value = 1; loadList(false) }, 350) })
watch(pageNo, () => loadList(false))
onMounted(async () => { try { settings.value = await api.settings() } catch (e) { toast(apiError(e), 'error') } await loadList() })
</script>

<template>
  <v-app>
    <header class="app-header">
      <div class="brand"><strong>업사이클링 대상 파일 선별</strong></div>
      <div class="header-actions">
        <v-btn variant="text" prepend-icon="mdi-database-outline" @click="openVolumes">Volumes</v-btn>
        <v-btn color="primary" variant="tonal" prepend-icon="mdi-refresh" :loading="loading" @click="scan">재스캔</v-btn>
        <v-btn color="primary" prepend-icon="mdi-microsoft-excel" href="/api/selections/export.xlsx">Excel 다운로드</v-btn>
      </div>
    </header>
    <main class="workspace">
      <section class="summary-row">
        <div v-for="item in [{ key: 'total', label: '전체 후보', icon: 'mdi-layers-outline' }, { key: 'pending', label: '검토 대기', icon: 'mdi-clock-outline' }, { key: 'selected', label: '선택 완료', icon: 'mdi-check-circle-outline' }, { key: 'rejected', label: '제외', icon: 'mdi-minus-circle-outline' }]" :key="item.key" class="summary-card">
          <v-icon :icon="item.icon" /><div><span>{{ item.label }}</span><strong>{{ page.summary[item.key] || 0 }}</strong></div>
        </div>
      </section>
      <div class="work-grid" :class="{ 'resizing-candidate': resizingCandidate }" :style="{ '--candidate-panel-width': `${candidateWidth}px` }">
        <aside class="candidate-panel panel">
          <button class="candidate-resize-handle" type="button" aria-label="선별 후보 패널 폭 조절" @pointerdown="startCandidateResize" @pointermove="resizeCandidate" @pointerup="stopCandidateResize" @pointercancel="stopCandidateResize"><span /></button>
          <div class="panel-title"><div><h2>선별 후보</h2><span>{{ page.count }}건</span></div></div>
          <section class="inline-settings">
            <div class="inline-section-title"><v-icon icon="mdi-tune-variant" size="16"/><strong>데이터 및 매칭 설정</strong></div>
            <button class="path-picker" @click="openFolder('raw_relative_path')"><v-icon icon="mdi-dots-horizontal"/><div><small>원천 데이터 폴더</small><strong :class="{ placeholder: !settings.raw_relative_path }">{{ folderName(settings.raw_relative_path) }}</strong></div><v-icon icon="mdi-chevron-right"/></button>
            <button class="path-picker" @click="openFolder('labeled_relative_path')"><v-icon icon="mdi-dots-horizontal"/><div><small>라벨 데이터 폴더</small><strong :class="{ placeholder: !settings.labeled_relative_path }">{{ folderName(settings.labeled_relative_path) }}</strong></div><v-icon icon="mdi-chevron-right"/></button>
            <v-select v-model="settings.mapping_strategy" density="compact" hide-details label="매칭 방식" :items="[{ title: '파일명(stem)', value: 'file_name' }, { title: 'JSON 참조키', value: 'json_ref_key' }]" />
            <v-text-field v-if="settings.mapping_strategy === 'json_ref_key'" v-model="settings.json_ref_key" density="compact" hide-details label="JSON dot path" placeholder="data_key" />
            <v-radio-group v-model="settings.annotation_method_code" density="compact" hide-details label="어노테이션 방식" inline>
              <v-radio label="BBox 2D" value="bbox_2d" />
              <v-radio label="BBox 3D" value="bbox_3d" />
              <v-radio label="Polygon" value="polygon" />
              <v-radio label="Segmentation" value="segmentation" />
            </v-radio-group>
            <v-btn block size="small" color="primary" variant="tonal" prepend-icon="mdi-refresh" :loading="loading" :disabled="!settings.raw_relative_path || !settings.labeled_relative_path" @click="saveSettings">설정 저장 및 재스캔</v-btn>
          </section>
          <div class="filter-title"><v-icon icon="mdi-filter-variant" size="15"/><span>후보 필터</span></div>
          <div class="filters">
            <v-select v-model="filters.selection_status" density="compact" hide-details label="선별 상태" :items="[{ title: '전체', value: '' }, { title: '대기', value: 'pending' }, { title: '선택', value: 'selected' }, { title: '제외', value: 'rejected' }, { title: '복사 실패', value: 'move_failed' }]" />
            <v-select v-model="filters.match_status" density="compact" hide-details label="매칭 상태" :items="[{ title: '전체', value: '' }, { title: '매칭', value: 'matched' }, { title: '미매칭', value: 'unmatched' }, { title: '충돌', value: 'conflict' }, { title: '오류', value: 'error' }]" />
            <v-text-field v-model="filters.search" density="compact" hide-details clearable label="파일명 또는 매칭 키" prepend-inner-icon="mdi-magnify" />
          </div>
          <div class="candidate-list" :class="{ loading }">
            <button v-for="item in page.results" :key="item.id" class="candidate-item" :class="{ active: selected?.id === item.id }" @click="openCandidate(item)">
              <div class="candidate-name" :title="item.match_key">{{ item.match_key || '(매칭 키 없음)' }}</div>
              <div v-if="item.match_status === 'matched'" class="candidate-files">
                <span v-for="file in item.files.filter(file => file.file_group === 'raw')" :key="file.id" :title="file.original_relative_path">{{ file.original_relative_path }}</span>
              </div>
              <div v-else class="candidate-path">{{ item.files.find(file => file.file_group === 'labeled')?.original_relative_path || '매칭된 파일 없음' }}</div>
              <div class="chips"><v-chip size="x-small" :color="statusColor[item.match_status]">{{ statusText[item.match_status] }}</v-chip><v-chip size="x-small" :color="statusColor[item.selection_status]">{{ statusText[item.selection_status] }}</v-chip><span>{{ item.files.filter(file => file.file_group === 'raw').length }} 원천</span></div>
            </button>
            <div v-if="!loading && !page.results.length" class="list-empty"><v-icon icon="mdi-file-search-outline" /><span>조건에 맞는 후보가 없습니다.</span><small>매칭 설정 후 재스캔하세요.</small></div>
          </div>
          <v-pagination v-if="page.total_pages > 1" v-model="pageNo" density="compact" :length="page.total_pages" :total-visible="5" />
        </aside>
        <section class="viewer-panel panel">
          <SelectionViewer v-if="selected" :files="selected.files" :label-json="selected.label_json" :annotation-method="settings.annotation_method_code" />
          <div v-else class="selection-empty"><div class="empty-illustration"><v-icon icon="mdi-image-search-outline" /></div><h2>검토할 후보를 선택하세요</h2><p>좌측 목록에서 원천·라벨 파일 묶음을 선택하면 렌더링 결과를 확인할 수 있습니다.</p></div>
        </section>
        <aside class="detail-panel panel">
          <template v-if="selected">
            <div class="detail-heading"><div><span>후보 상세</span><h2 :title="selected.match_key">{{ selected.match_key }}</h2></div><v-chip size="small" :color="statusColor[selected.selection_status]">{{ statusText[selected.selection_status] }}</v-chip></div>
            <div v-if="selected.error_message" class="error-box"><v-icon icon="mdi-alert-outline" />{{ selected.error_message }}</div>
            <dl class="meta-grid"><dt>매칭 방식</dt><dd>{{ selected.mapping_strategy === 'file_name' ? '파일명' : 'JSON 참조키' }}</dd><dt>매칭 상태</dt><dd>{{ statusText[selected.match_status] }}</dd><dt>갱신 일시</dt><dd>{{ date(selected.updated_at) }}</dd></dl>
            <div class="detail-section"><div class="section-title"><h3>원천 파일</h3><span>{{ rawFiles.length }}</span></div><div class="file-list"><button v-for="file in rawFiles" :key="file.id" class="file-row" @click="openFilePreview(file)"><v-icon :icon="file.is_previewable_image ? 'mdi-file-image-outline' : 'mdi-cube-outline'" /><div><strong :title="file.original_relative_path">{{ file.original_relative_path }}</strong><span>{{ file.extension || 'file' }} · {{ bytes(file.size) }} · {{ date(file.mtime) }}</span></div><v-icon icon="mdi-eye-outline" size="17" /></button></div></div>
            <div class="detail-section"><div class="section-title"><h3>라벨 파일</h3><span>{{ labelFiles.length }}</span></div><div class="file-list"><button v-for="file in labelFiles" :key="file.id" class="file-row" @click="openFilePreview(file)"><v-icon icon="mdi-code-json" /><div><strong :title="file.original_relative_path">{{ file.original_relative_path }}</strong><span>{{ bytes(file.size) }}</span></div><v-icon icon="mdi-eye-outline" size="17" /></button></div></div>
            <div class="decision-actions">
              <v-btn v-if="selected.selection_status === 'rejected' || selected.selection_status === 'move_failed'" block variant="tonal" prepend-icon="mdi-restore" @click="resetDecision">대기로 복구</v-btn>
              <v-btn block color="error" variant="tonal" prepend-icon="mdi-close" :disabled="selected.selection_status === 'selected'" @click="decide('rejected')">제외</v-btn>
              <v-btn block color="primary" prepend-icon="mdi-content-copy" :loading="detailLoading" :disabled="!canSelect" @click="decide('selected')">대상 선택 및 파일 복사</v-btn>
            </div>
          </template>
          <div v-else class="detail-empty"><v-icon icon="mdi-text-box-search-outline" /><span>후보 상세 정보</span></div>
        </aside>
      </div>
    </main>
    <v-dialog v-model="folderOpen" max-width="620"><v-card><v-card-title>{{ folderTarget === 'raw_relative_path' ? '원천데이터 폴더 선택' : '라벨데이터 폴더 선택' }}</v-card-title><v-card-text><div class="folder-root"><strong>DATA_ROOT_PATH</strong><span>HOST · {{ folders.root_host_path || '호스트 경로 정보 없음' }}</span><span>CONTAINER · {{ folders.root_container_path }}</span></div><div class="folder-location"><v-btn icon="mdi-arrow-up" size="small" variant="tonal" :disabled="!folders.current" @click="browseFolder(folders.parent)"/><v-icon icon="mdi-dots-horizontal"/><div><small>현재 상대 경로</small><strong>/{{ folders.current }}</strong></div></div><div class="folder-list" :class="{ loading: folderLoading }"><button v-for="folder in folders.directories" :key="folder.path" @click="browseFolder(folder.path)"><v-icon icon="mdi-dots-horizontal" color="amber-darken-2"/><span>{{ folder.name }}</span><v-icon icon="mdi-chevron-right"/></button><div v-if="!folders.directories.length" class="folder-empty">하위 폴더가 없습니다.</div></div><small class="folder-help">DATA_ROOT_PATH 이하의 폴더만 선택할 수 있습니다. 폴더로 이동한 후 현재 폴더 선택을 누르세요.</small></v-card-text><v-card-actions><v-spacer/><v-btn variant="text" @click="folderOpen = false">취소</v-btn><v-btn color="primary" :disabled="!folders.current" @click="chooseFolder">현재 폴더 선택</v-btn></v-card-actions></v-card></v-dialog>
    <v-dialog v-model="volumesOpen" max-width="760"><v-card><v-card-title class="dialog-title"><span>Volume 마운트 현황</span><v-btn icon="mdi-refresh" variant="text" :loading="volumesLoading" @click="openVolumes"/></v-card-title><v-card-text><div class="volume-list"><article v-for="volume in volumes.volumes" :key="volume.key" class="volume-card"><div class="volume-heading"><div class="volume-icon"><v-icon icon="mdi-harddisk"/></div><div><strong>{{ volume.label }}</strong><div class="volume-path"><em>HOST</em><span :title="volume.host_path">{{ volume.host_path || '호스트 경로 정보 없음' }}</span></div><div class="volume-path"><em>CONTAINER</em><span :title="volume.container_path">{{ volume.container_path }}</span></div></div><v-chip size="small" :color="volume.exists && volume.readable ? 'success' : 'error'">{{ volume.exists && volume.readable ? '사용 가능' : '확인 필요' }}</v-chip></div><v-progress-linear :model-value="usagePercent(volume)" height="7" rounded color="primary" bg-color="blue-grey-lighten-4"/><div class="volume-meta"><span>사용 {{ bytes(volume.used_bytes) }} / {{ bytes(volume.total_bytes) }}</span><span>여유 {{ bytes(volume.free_bytes) }}</span><span>{{ volume.readable ? '읽기' : '읽기 불가' }} · {{ volume.writable ? '쓰기' : '쓰기 불가' }} · {{ volume.is_mount ? '마운트됨' : '일반 경로' }}</span></div></article></div><div class="selected-folders"><h3>프로그램 선택 폴더</h3><div v-for="folder in volumes.selected_directories" :key="folder.key" class="selected-folder"><v-icon :icon="folder.exists ? 'mdi-folder-check-outline' : 'mdi-folder-alert-outline'" :color="folder.exists ? 'success' : 'error'"/><div><strong>{{ folder.label }}</strong><span>/{{ folder.relative_path }}</span></div><v-chip size="x-small" :color="folder.exists ? 'success' : 'error'">{{ folder.exists ? '연결됨' : '없음' }}</v-chip></div></div></v-card-text><v-card-actions><v-spacer/><v-btn color="primary" variant="tonal" @click="volumesOpen = false">닫기</v-btn></v-card-actions></v-card></v-dialog>
    <v-dialog v-model="filePreviewOpen" max-width="1000"><v-card class="file-preview-dialog"><v-card-title class="dialog-title"><div><span>{{ filePreview?.file_group === 'raw' ? '원천 파일' : '라벨 파일' }} 미리보기</span><small :title="filePreview?.original_relative_path">{{ filePreview?.original_relative_path }}</small></div><v-btn icon="mdi-close" variant="text" @click="filePreviewOpen = false"/></v-card-title><v-card-text><div v-if="filePreviewError" class="preview-error"><v-icon icon="mdi-alert-circle-outline"/>{{ filePreviewError }}</div><div v-if="previewIsImage && filePreview" class="image-file-preview"><img :src="filePreview.file_url" :alt="filePreview.original_relative_path" @error="filePreviewError = '이미지 파일을 불러오지 못했습니다.'"/></div><pre v-else-if="previewIsLabelJson" class="json-view file-json-preview">{{ JSON.stringify(selected?.label_json, null, 2) }}</pre><div v-else-if="textPreviewLoading" class="preview-loading"><v-progress-circular indeterminate color="primary"/><span>텍스트 표시 가능 여부를 확인하고 있습니다.</span></div><template v-else-if="textPreview.previewable"><div class="text-preview-meta"><span>{{ textPreview.encoding?.toUpperCase() }} · {{ bytes(textPreview.size || 0) }}</span><v-chip v-if="textPreview.truncated" size="x-small" color="warning">앞부분 {{ bytes(textPreview.preview_bytes || 0) }}만 표시</v-chip></div><pre class="text-file-preview">{{ textPreview.content }}</pre></template><div v-else-if="filePreview" class="unsupported-preview"><v-icon icon="mdi-file-question-outline" size="58"/><h3>텍스트로 표시할 수 없는 파일입니다.</h3><p>{{ textPreview.reason || '브라우저 미리보기를 지원하지 않습니다.' }}</p><p>{{ filePreview.extension || '확장자 없음' }} · {{ bytes(filePreview.size) }} · {{ date(filePreview.mtime) }}</p><code>{{ filePreview.original_relative_path }}</code></div></v-card-text><v-card-actions><v-btn v-if="filePreview" :href="filePreview.file_url" target="_blank" prepend-icon="mdi-open-in-new" variant="text">새 창에서 열기</v-btn><v-spacer/><v-btn color="primary" variant="tonal" @click="filePreviewOpen = false">닫기</v-btn></v-card-actions></v-card></v-dialog>
    <v-dialog v-model="overwriteConfirmOpen" max-width="640" persistent><v-card><v-card-title class="overwrite-title"><v-icon icon="mdi-alert-outline" color="warning"/>기존 파일 덮어쓰기 확인</v-card-title><v-card-text><p class="overwrite-message">선별 결과 경로에 같은 파일이 있습니다. 아래 파일을 덮어쓰시겠습니까?</p><div class="conflict-list"><code v-for="path in overwriteConflicts" :key="path">{{ path }}</code></div><v-alert type="warning" variant="tonal" density="compact">덮어쓰기 중 오류가 발생하면 기존 파일을 임시 백업에서 복원합니다.</v-alert></v-card-text><v-card-actions><v-spacer/><v-btn variant="text" @click="overwriteConfirmOpen = false">취소</v-btn><v-btn color="warning" variant="flat" prepend-icon="mdi-content-save-alert-outline" :loading="detailLoading" @click="decide('selected', true)">덮어쓰기</v-btn></v-card-actions></v-card></v-dialog>
    <v-snackbar v-model="notice.show" :color="notice.color" timeout="4500">{{ notice.text }}<template #actions><v-btn variant="text" @click="notice.show = false">닫기</v-btn></template></v-snackbar>
  </v-app>
</template>
