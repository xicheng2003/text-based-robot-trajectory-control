<script setup lang="ts">
import { computed } from 'vue'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'

const props = defineProps<{
  status: Record<string, any>,
  logs: string[]
}>()

// 计算属性，用于根据不同状态返回不同的 Badge 颜色
const runStatusVariant = computed(() => {
  switch (props.status.run_status) {
    case '正在运行': return 'default'
    case '暂停': return 'secondary'
    case '停止': return 'outline'
    default: return 'secondary'
  }
})

const alarmStatusVariant = computed(() => {
  return props.status.alarm_code === 0 ? 'secondary' : 'destructive'
})
</script>

<template>
  <Card class="w-full">
    <CardHeader>
      <CardTitle>机器人状态与日志</CardTitle>
      <CardDescription>实时监控机器人当前状态</CardDescription>
    </CardHeader>
    <CardContent>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4 text-center">
        <div>
          <h4 class="font-semibold text-sm text-muted-foreground">当前模式</h4>
          <p class="text-lg font-bold">{{ status.mode }}</p>
        </div>
        <div>
          <h4 class="font-semibold text-sm text-muted-foreground">运行状态</h4>
          <Badge :variant="runStatusVariant">{{ status.run_status }}</Badge>
        </div>
        <div>
          <h4 class="font-semibold text-sm text-muted-foreground">报警状态</h4>
          <Badge :variant="alarmStatusVariant">{{ status.alarm_status }}</Badge>
        </div>
        <div>
          <h4 class="font-semibold text-sm text-muted-foreground">GV0 测试值</h4>
          <p class="text-lg font-bold">{{ status.gv0_value?.toFixed(2) ?? 'N/A' }}</p>
        </div>
      </div>

      <div class="bg-muted p-4 rounded-lg border text-sm h-64 overflow-y-auto font-mono">
        <p v-for="(log, index) in logs.slice(0, 100)" :key="index" class="whitespace-pre-wrap break-words">
          {{ log }}
        </p>
      </div>
    </CardContent>
  </Card>
</template>