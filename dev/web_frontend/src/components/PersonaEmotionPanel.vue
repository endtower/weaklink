<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowRight, Refresh } from '@element-plus/icons-vue'
import { memoryRequest } from '../api/memory'

/**
 * 情绪词配置面板。
 *
 * 刻意做成「可以内联嵌进人格详情页」的普通组件，而不是弹窗：
 * 它本来就是这个人格的一部分，摆在同一页里展开看，比再弹一层窗口直观，
 * 也不会出现「弹窗里再弹窗」那种焦点和关闭顺序都很别扭的情况。
 *
 * 这里只负责编辑和保存，不弹提示 —— 保存成功后把新的人格数据交给父组件，
 * 由父组件更新列表和吐提示，避免两处各说一遍。
 */

type Axis = 'da' | 'ne'
export type EmotionBand = [number, number, string]
export type EmotionPreset = { id: string; label: string; da: EmotionBand[]; ne: EmotionBand[] }
export type EmotionStyle = {
  preset: string
  overrides: Record<Axis, Record<string, string>>
}

const props = defineProps<{
  personaId: string
  presets: EmotionPreset[]
  styleConfig: EmotionStyle
}>()
const emit = defineEmits<{ saved: [persona: Record<string, any>] }>()

const cloneStyle = (style: EmotionStyle): EmotionStyle => ({
  preset: style.preset,
  overrides: { da: { ...style.overrides.da }, ne: { ...style.overrides.ne } },
})

const draft = ref<EmotionStyle>(cloneStyle(props.styleConfig))
const axis = ref<Axis>('da')
const open = ref(false)
/** 展开后逐档编辑的是哪一档（下界）；0 不是有效下界，所以用 -1 表示没有展开项。 */
const editing = ref(-1)
const busy = ref(false)
const error = ref('')

const preset = computed(() => props.presets.find(item => item.id === draft.value.preset))
const bands = computed(() => preset.value?.[axis.value] ?? [])
const editedCount = computed(() =>
  Object.keys(draft.value.overrides.da).length + Object.keys(draft.value.overrides.ne).length)
const dirty = computed(() => {
  const original = props.styleConfig
  return draft.value.preset !== original.preset
    || JSON.stringify(draft.value.overrides) !== JSON.stringify({
      da: { ...original.overrides.da }, ne: { ...original.overrides.ne },
    })
})
const hasBlank = computed(() => Object.values(draft.value.overrides).some(
  entries => Object.values(entries).some(value => !value.trim())))
const canSave = computed(() => !!preset.value && !hasBlank.value && dirty.value && !busy.value)

const summary = computed(() => {
  const label = preset.value?.label ?? '未知预设'
  return editedCount.value ? `${label} · 已自定义 ${editedCount.value} 档` : label
})
/** 每档的当前文案：改过就是改的，没改就是预设原文。 */
const textOf = (low: number, original: string) => draft.value.overrides[axis.value][String(low)] ?? original
const isEdited = (low: number) => String(low) in draft.value.overrides[axis.value]

function updateBand(low: number, value: string, original: string) {
  const key = String(low)
  if (value === original) delete draft.value.overrides[axis.value][key]
  else draft.value.overrides[axis.value][key] = value
}

function resetBand(low: number) {
  delete draft.value.overrides[axis.value][String(low)]
}

function resetAll() {
  draft.value = { preset: draft.value.preset, overrides: { da: {}, ne: {} } }
  editing.value = -1
  error.value = ''
}

function toggleBand(low: number) {
  editing.value = editing.value === low ? -1 : low
}

async function save() {
  if (!canSave.value) return
  busy.value = true
  error.value = ''
  try {
    const { persona } = await memoryRequest(
      `/memory/personas/${encodeURIComponent(props.personaId)}`,
      'PATCH',
      { emotion_style: draft.value },
    )
    // 服务端可能对档位做了排序/归一，以它返回的为准重建草稿
    if (persona?.emotion_style) draft.value = cloneStyle(persona.emotion_style)
    editing.value = -1
    emit('saved', persona)
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    busy.value = false
  }
}

// 换了一个人格就把草稿重置成它的配置，别把上一个人的改动带过去
watch(() => [props.personaId, props.styleConfig] as const, () => {
  draft.value = cloneStyle(props.styleConfig)
  editing.value = -1
  error.value = ''
})
</script>

<template>
  <section class="emotion-panel" aria-label="情绪词">
    <header class="emotion-head">
      <button
        type="button" class="emotion-toggle" :aria-expanded="open"
        :aria-label="open ? '收起情绪词配置' : '展开情绪词配置'" @click="open = !open"
      >
        <el-icon :size="10" class="emotion-chevron" :class="{ open }"><ArrowRight /></el-icon>
        <span class="emotion-title">情绪词</span>
      </button>
      <span class="emotion-summary">{{ summary }}</span>
      <span v-if="dirty" class="emotion-dirty">有未保存的修改</span>
      <div v-if="dirty" class="emotion-head-actions">
        <el-button size="small" :disabled="busy" @click="resetAll">撤销修改</el-button>
        <el-button size="small" type="primary" :loading="busy" :disabled="!canSave" @click="save">保存</el-button>
      </div>
    </header>

    <div v-if="open" class="emotion-body">
      <p class="emotion-hint">
        选中一个预设后，逐档改写它的文案。没改过的档位跟着预设走，切预设时会一起更新；
        改过的档位会保留，点「恢复预设」可以单独放回。保存后从下一段会话生效。
      </p>

      <div class="emotion-controls">
        <el-select
          v-model="draft.preset" class="emotion-preset" size="small" :disabled="busy"
          aria-label="情绪预设" @change="editing = -1"
        >
          <el-option v-for="item in presets" :key="item.id" :label="item.label" :value="item.id" />
        </el-select>
        <el-radio-group v-model="axis" size="small" aria-label="情绪维度" @change="editing = -1">
          <el-radio-button value="da">DA · 心情与互动</el-radio-button>
          <el-radio-button value="ne">NE · 话语尖锐度</el-radio-button>
        </el-radio-group>
      </div>

      <div class="emotion-bands">
        <div
          v-for="[low, high, original] in bands" :key="`${axis}-${low}`"
          class="emotion-band" :class="{ open: editing === low, edited: isEdited(low) }"
        >
          <button
            type="button" class="emotion-band-head"
            :aria-expanded="editing === low" :aria-label="`编辑 ${low}–${high} 档`"
            @click="toggleBand(low)"
          >
            <span class="emotion-band-range">{{ low }}–{{ high }}</span>
            <span v-if="editing !== low" class="emotion-band-preview">{{ textOf(low, original) }}</span>
            <span v-else class="emotion-band-preview editing">正在编辑…</span>
            <span v-if="isEdited(low)" class="emotion-band-tag">已自定义</span>
            <el-icon :size="10" class="emotion-band-chevron" :class="{ open: editing === low }"><ArrowRight /></el-icon>
          </button>

          <div v-if="editing === low" class="emotion-band-body">
            <el-input
              :model-value="textOf(low, original)" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
              :disabled="busy" :aria-label="`${axis.toUpperCase()} ${low}–${high} 档文案`"
              @update:model-value="updateBand(low, $event as string, original)"
            />
            <div class="emotion-band-actions">
              <span class="emotion-band-count">{{ textOf(low, original).length }} 字</span>
              <el-button v-if="isEdited(low)" size="small" text :icon="Refresh" :disabled="busy" @click="resetBand(low)">
                恢复预设
              </el-button>
            </div>
          </div>
        </div>
      </div>

      <p v-if="error || hasBlank" class="emotion-error" role="alert">
        {{ error || '文案不能为空。要沿用预设，请点这一档的「恢复预设」。' }}
      </p>
      <p v-else class="emotion-foot">
        共 {{ bands.length }} 档；两个维度各自独立。<span v-if="editedCount">当前共自定义 {{ editedCount }} 档。</span>
      </p>
    </div>
  </section>
</template>

<style scoped>
.emotion-panel {
  margin-top: 4px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  background: var(--bg-surface);
  overflow: hidden;
}
.emotion-head {
  display: flex;
  align-items: center;
  gap: 8px 10px;
  flex-wrap: wrap;
  padding: 10px 14px;
}
.emotion-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: 0;
  background: transparent;
  color: var(--text-primary);
  font: inherit;
  font-weight: 600;
  padding: 0;
  cursor: pointer;
}
.emotion-chevron { color: var(--text-tertiary); transition: transform 0.12s; }
.emotion-chevron.open { transform: rotate(90deg); }
.emotion-title { font-size: var(--text-md); }
.emotion-summary { font-size: var(--text-xs); color: var(--text-tertiary); }
.emotion-dirty {
  font-size: var(--text-xs);
  color: var(--tag-warning);
  border: 1px solid color-mix(in srgb, var(--tag-warning) 40%, transparent);
  border-radius: var(--radius-pill);
  padding: 0 7px;
}
.emotion-preset { width: 220px; max-width: 100%; }
.emotion-head-actions { display: flex; gap: 8px; margin-left: auto; }

.emotion-body {
  display: grid;
  gap: 10px;
  padding: 0 14px 14px;
  border-top: 1px solid var(--border-subtle);
  padding-top: 12px;
}
.emotion-hint { margin: 0; font-size: var(--text-xs); line-height: 1.7; color: var(--text-tertiary); }
.emotion-controls { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }

.emotion-bands { display: grid; gap: 4px; min-width: 0; }
.emotion-band {
  border: 1px solid transparent;
  border-radius: var(--radius-md);
  background: var(--bg-sunken);
  /* grid/flex 子项默认 min-width:auto，长文案会把整块撑出容器；显式压回 0 才能正常省略号截断 */
  min-width: 0;
}
.emotion-band.open { border-color: var(--border-default); background: var(--bg-surface); }
.emotion-band-head {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  min-width: 0;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  padding: 7px 10px;
  border-radius: var(--radius-md);
  cursor: pointer;
}
.emotion-band-head:hover { background: var(--bg-hover); }
.emotion-band.open > .emotion-band-head { opacity: 0.75; }
.emotion-band.open > .emotion-band-head .emotion-band-preview { color: var(--text-tertiary); }
.emotion-band-range {
  flex: none;
  min-width: 58px;
  font-size: var(--text-xs);
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
  font-weight: 600;
}
.emotion-band-preview {
  flex: 1 1 auto;
  min-width: 0;
  font-size: var(--text-xs);
  color: var(--text-tertiary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.emotion-band.edited .emotion-band-preview { color: var(--text-secondary); }
.emotion-band-preview.editing { color: var(--text-tertiary); font-style: italic; }
.emotion-band-tag {
  flex: none;
  font-size: var(--text-xs);
  color: var(--accent);
  border: 1px solid color-mix(in srgb, var(--accent) 40%, transparent);
  border-radius: var(--radius-pill);
  padding: 0 6px;
}
.emotion-band-chevron { flex: none; color: var(--text-tertiary); transition: transform 0.12s; }
.emotion-band-chevron.open { transform: rotate(90deg); }
.emotion-band-body { display: grid; gap: 6px; padding: 0 10px 10px; min-width: 0; }
.emotion-band-body :deep(.el-textarea),
.emotion-band-body :deep(.el-textarea__inner) { width: 100%; max-width: 100%; box-sizing: border-box; }
.emotion-band-actions { display: flex; align-items: center; gap: 10px; }
.emotion-band-count { font-size: var(--text-xs); color: var(--text-tertiary); font-variant-numeric: tabular-nums; }
.emotion-error,
.emotion-foot { margin: 0; font-size: var(--text-xs); }
.emotion-error { color: var(--tag-danger); }
.emotion-foot { color: var(--text-tertiary); }
</style>
